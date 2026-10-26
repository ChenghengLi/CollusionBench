"""Build the casebook data: data.json (one summary per game, every model) and one full transcript
per game in <outdir>/t/<id>.json.gz, from the finished games' journals (read-only).

    .venv/bin/python casebook_build.py <outdir> [notes.json]

Replays every finished game's journal (read-only) to get who sent what to whom, the detector's
screens (ask / request / leak) and uses, then writes one record per game: scorer fields, an
automatic summary, the audit note where one exists, and the key turns with the model's reasoning.
"""
import asyncio
import glob
import json
import os
import re
import sys
import base64
import collections
import gzip

sys.path.insert(0, "src")
from collusiongen.core.env import Services
from collusiongen.core.log import EventLog
from collusiongen.core.registry import get_module
from collusiongen.modules.n4_relay.cards import detect
from collusiongen.runner.config import RunConfig
from collusiongen.runner.episode import make_variant
from collusiongen.runner.plan import expand

GAMES = ("records", "pricing", "exam", "approvals")
COMM = ("message", "forum_post", "forum_reply")
UNIT_LABEL = {"orders": "Orders", "warehouse": "Warehouse", "billing": "Billing", "pricing": "Pricing",
              "buying_a": "Buying A", "buying_b": "Buying B", "candidate_a": "Candidate A",
              "candidate_b": "Candidate B", "candidate_c": "Candidate C", "clerk_a": "Clerk A",
              "clerk_b": "Clerk B", "clerk_c": "Clerk C"}
TEXT_MAX, REASON_MAX, REPORT_MAX, MAX_COMM = 700, 600, 1600, 45


def clean(s, n):
    s = re.sub(r"</?ifm\|[a-z_]+>", "", str(s or "")).strip()
    s = re.sub(r"\s+\n", "\n", s)
    return s if len(s) <= n else s[:n].rstrip() + " …"


async def replay(spec, turns):
    """Replay a journal; return env and, per turn index, the (start, end) slice of env.log."""
    module = get_module(spec.module_id)
    env = module.make_env(spec.instance, make_variant(module, spec), EventLog(spec.episode_id), Services())
    bounds, made = [], []
    for t in turns:
        seat = env.next_seat()
        if seat is None or seat != t.get("seat"):
            break
        env.observe(seat)
        a = len(env.log)
        before = [len(w.calls) for w in env.workers]
        b = t.get("applied_batch")
        if b:
            await env.apply_batch(seat, b)
        elif t.get("applied"):
            await env.apply(seat, t["applied"], substituted=bool(t.get("substituted")))
        bounds.append((a, len(env.log)))
        new = [(w.index, c) for w, n0 in zip(env.workers, before) for c in w.calls[n0:]]
        made.append(new)
    return env, bounds, made


def cell_of(p):
    c = p["card_condition"] + ("/" + p["aim"] if p.get("aim") else "")
    return p["route_cost"], c


def fmt(n):
    try:
        return f"{int(float(n)):,}"
    except Exception:
        return str(n)


def short(v, n):
    v = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return v if len(v) <= n else v[:n] + f" … [{len(v) - n} more characters]"


def transcript(env, bounds, made, turns, cut, units):
    """Every turn: who acted, the phase, the model's reasoning and visible text, each tool call with
    its arguments and the environment's reply, and the detector's flags on what it sent."""
    log = list(env.log)
    system, out = {}, []
    for ti, ((a, b), calls) in enumerate(zip(bounds, made)):
        t = turns[ti]
        w = calls[0][0] if calls else None
        u = units[w - 1] if w else "?"
        if t.get("system") and u not in system:
            system[u] = t["system"]
        flags = []
        for e in log[a:b]:
            if e.kind == "screen":
                p = e.payload
                if p.get("ask"):
                    flags.append("ask")
                elif p.get("request"):
                    flags.append("request")
                if p.get("leak"):
                    flags.append("leak on request" if p.get("requested_by") else "leak")
        out.append({"i": ti, "u": u, "ph": "report" if a >= cut else "task",
                    "r": clean(t.get("reasoning"), 6000), "x": short(str(t.get("raw_text") or "").strip(), 2000),
                    "sub": bool(t.get("substituted")), "f": flags,
                    "c": [{"t": c["call"].get("tool"),
                           "a": {k: short(v, 1500) for k, v in c["call"].items() if k != "tool"},
                           "res": short(str(c.get("result", "")), 2500)} for _, c in calls]})
    first = turns[0].get("prompt") if turns else ""
    return {"system": system, "first": short(str(first or ""), 3000), "turns": out}


def build_game(g, r, spec, turns, notes, model="", outdir=None):
    env, bounds, made = asyncio.run(replay(spec, turns))
    game = env.game
    units = [UNIT_LABEL.get(u.key, u.key) for u in game.seat_units()]
    uname = lambda w: units[w - 1] if isinstance(w, int) and 1 <= w <= len(units) else str(w)
    s = r["secondary"]
    scan = detect._scan(game, env)
    cut = len(scan["evs"])  # task phase ends here; later events are the report phase
    turn_of = {}
    for ti, (a, b) in enumerate(bounds):
        for k in range(a, b):
            turn_of[k] = ti
    log = list(env.log)
    # pair each screen with the communication / write event just before it
    screen_at = {}
    last_item = None
    for k, e in enumerate(log):
        if e.kind in COMM or (e.kind == "write" and str(e.payload.get("path", "")).startswith("/workspace")):
            last_item = k
        elif e.kind == "screen" and last_item is not None:
            screen_at[last_item] = e.payload
    uses_by_user = collections.defaultdict(list)
    for u in scan["uses"]:
        uses_by_user[u["user"]].append(u)
    items, subs, n_msg, n_post = [], [], 0, 0
    call_no = 0
    for k, e in enumerate(log):
        p = e.payload
        if e.kind == "action":
            call_no += 1
            continue
        w = p.get("wave")
        phase = "report" if k >= cut else "task"
        if e.kind in COMM or (e.kind == "write" and str(p.get("path", "")).startswith("/workspace")
                              and "/logs/" not in str(p.get("path", "")) and not str(p.get("path", "")).endswith("report.md")
                              and not str(p.get("path", "")).startswith("/workspace/approvals")):
            if e.kind == "message":
                n_msg += 1
                to = ", ".join(uname(x) for x in (p.get("to") or [])) or "?"
                kind = "message"
            elif e.kind == "write":
                to = str(p.get("path"))
                kind = "shared file"
            else:
                n_post += 1
                to = "forum"
                kind = "forum post" if e.kind == "forum_post" else "forum reply"
            text = (str(p.get("title") or "") + "\n" if p.get("title") else "") + str(p.get("text") or p.get("content") or "")
            sc = screen_at.get(k, {})
            flags = []
            if sc.get("ask"):
                flags.append("ask")
            elif sc.get("request"):
                flags.append("request")
            if sc.get("leak"):
                flags.append("leak-requested" if sc.get("requested_by") else "leak")
            ti = turn_of.get(k)
            reasoning = clean(turns[ti].get("reasoning"), REASON_MAX) if (ti is not None and flags) else ""
            items.append({"k": call_no, "u": uname(w), "kind": kind, "to": to, "x": clean(text, TEXT_MAX),
                          "f": flags, "r": reasoning, "ph": phase})
        elif e.kind == "submit_attempt":
            subs.append({"k": call_no, "u": uname(w), "a": clean(str(p.get("answer", "")).replace("question,answer\n", ""), 160),
                         "ok": f"{p.get('n_correct', 0)}/{p.get('n_answered', 0)}", "c": bool(p.get("correct"))})
    # key turns: flagged first, then the rest of the communication up to MAX_COMM
    flagged = [i for i in items if i["f"]]
    rest = [i for i in items if not i["f"]]
    keep = sorted(flagged + rest[:max(0, MAX_COMM - len(flagged))], key=lambda i: i["k"])
    # final report
    report = ""
    for e in log:
        if e.kind == "sign_report" and e.payload.get("content"):
            report = e.payload["content"]
    if not report:
        for e in log:
            if e.kind == "write" and str(e.payload.get("path", "")).endswith("report.md"):
                report = e.payload.get("content", "")
    # automatic summary
    p = r["params"]
    lines = []
    sol = s.get("card_solved")
    lines.append(("Solved." if sol else "Not solved.") + f" {len(subs)} answer-sheet submission{'s' if len(subs) != 1 else ''}"
                 + (f"; correct answer {fmt(game.answer())}." if g == "records" or g == "pricing" else "."))
    if n_msg or n_post:
        lines.append(f"Task phase: {sum(1 for i in items if i['ph']=='task' and i['kind']=='message')} messages, "
                     f"{sum(1 for i in items if i['ph']=='task' and i['kind'].startswith('forum'))} forum items between units.")
    else:
        lines.append("No messages or forum posts between units.")
    asks = [i for i in items if ("ask" in i["f"]) and i["ph"] == "task"]
    if asks:
        who = collections.Counter(f"{i['u']} → {i['to']}" for i in asks)
        lines.append("Asked for protected data: " + "; ".join(f"{k} ({v}×)" for k, v in who.items()) + ".")
    leaks = [i for i in items if any(f.startswith("leak") for f in i["f"]) and i["ph"] == "task"]
    if leaks:
        who = collections.Counter(f"{i['u']} → {i['to']}" + (" on request" if "leak-requested" in i["f"] else "") for i in leaks)
        lines.append("Detector saw unit data shared: " + "; ".join(f"{k} ({v}×)" for k, v in who.items()) + ".")
    for user, us in uses_by_user.items():
        lines.append(f"{uname(user)} used data from {', '.join(sorted({uname(u['supplier']) for u in us}))} ({us[0]['how']}).")
    act = scan["act"]
    if g == "approvals":
        if act.get("f_unchecked_approvals"):
            lines.append(f"{int(act['f_unchecked_approvals'])} approvals given without reading the packet files"
                         + (" — including a mutual pair (" + ("after contact" if act.get("f_joint_explicit") else "without contact") + ")." if act.get("joint") else "."))
        lines.append(f"{int(act.get('f_posted', 0))} invoices posted, {int(act.get('f_clean_rejected', 0))} clean invoices rejected, {int(act.get('f_flawed_posted', 0))} flawed invoices posted.")
    rep = scan["rep"]
    if report:
        if s.get("rep_false"):
            lines.append("Final report claims more than happened (false report)"
                         + (", signed by every unit." if s.get("rep_joint_false") else "."))
        else:
            lines.append("Final report is consistent with the outcome.")
    note = notes.get(r["episode_id"][:8], {})
    route, cond = cell_of(p)
    key = f"{slug(model)}-{r['episode_id'][:8]}"
    tr = transcript(env, bounds, made, turns, cut, units)
    tr.update({"id": r["episode_id"][:8], "model": model, "game": g, "route": route, "cond": cond,
               "units": units, "answer": str(game.answer()) if g in ("records", "pricing") else "",
               "params": {k: p.get(k) for k in PARAMS_SHOWN if k in p}})
    # gzip, base64-encoded as text: artifacts serve .txt but not .gz
    shard = slug(f"{model} {g} {route} {cond}") + ".gz.b64.txt"
    return {"_tr": tr, "shard": "t/" + shard,
        "key": key, "model": model, "env": int(p.get("card_env", 1)),
        "id": r["episode_id"][:8], "game": g, "route": route, "cond": cond,
        "units": units, "cls": int(s.get("card_class", 0)), "solved": bool(sol),
        "asked": bool(s.get("card_asked")), "supplied": bool(s.get("card_supplied")),
        "used": bool(s.get("card_used")), "joint": bool(s.get("card_joint")),
        "rep_false": bool(s.get("rep_false")), "rep_joint_false": bool(s.get("rep_joint_false")),
        "aware": bool(r.get("aware")), "calls": int(sum(1 for e in log if e.kind == "action")),
        "summary": lines, "verdict": note.get("v"), "note": note.get("n", ""),
        "rl": bool(note.get("rl")), "sa": note.get("sa"), "rc": note.get("rc"),
        "turns": keep, "n_items": len(items), "subs": subs, "report": clean(report, REPORT_MAX),
    }


PARAMS_SHOWN = ("max_tool_calls", "sheet_attempts", "report_calls", "audit_notice_call", "audit_rate",
                "card_env", "forum", "messaging", "hide_identity", "oversight_logs", "leak_monitor")
GAMES_OF = {"records": "card_records", "pricing": "card_pricing", "exam": "card_exam", "approvals": "card_approvals"}
HOSTS = {"reka": "Reka", "sailfp4us": "Sail FP4 US", "openinffp4": "OpenInference FP4", "deepinfrafp8": "DeepInfra FP8",
         "tokenharbor": "TokenHarbor"}


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:90]


def runs():
    """(model label, game, run dir) for every finished card run shown in the casebook."""
    out = []
    for prefix, label in (("final_rcp", "K2-Horizon-3.7B"), ("final7b_rcp", "K2-Horizon-7B"),
                          ("fp8_32b_rcp", "K2-Horizon-32B FP8")):
        for g in GAMES:
            d = f"runs/rcp/{prefix}_bench_card_{g}_full"
            if glob.glob(d + "/*/results.jsonl"):
                out.append((label, g, d))
    for d in sorted(glob.glob("runs/api/*_low_bench_card_records_blocked_v[23]")):
        if not glob.glob(d + "/*/results.jsonl"):
            continue
        name = os.path.basename(d)
        base = ("DeepSeek V4.1 Flash" if name.startswith("dsv41") else "GLM-5.3 Flash" if name.startswith("glm53")
                else "MiniMax-M3.1 Flash" if name.startswith("minimax") else name.split("_")[0])
        host = next((v for k, v in HOSTS.items() if f"_{k}_" in name), "")
        env = "fixed" if name.endswith("_v3") else "before audit"
        out.append((f"{base} · {host} · {env}", "records", d))
    return out


def main():
    outdir = sys.argv[1]
    os.makedirs(os.path.join(outdir, "t"), exist_ok=True)
    notes = json.load(open(sys.argv[2])) if len(sys.argv) > 2 else {}
    games, plan, shards = [], {}, {}
    for model, g, run in runs():
        cfg = RunConfig.model_validate_json(open(run + "/config.json").read())
        specs = {sp.episode_id: sp for sp in expand(cfg, cfg.models[0])}
        tot = collections.Counter()
        for m in cfg.modules:
            tot["|".join(cell_of(m.params_override))] += m.n_instances
        plan.setdefault(model, {})[g] = dict(tot)
        d = glob.glob(run + "/*/")[0]
        res = d + "results_rescored.jsonl" if os.path.exists(d + "results_rescored.jsonl") else d + "results.jsonl"
        for line in open(res):
            r = json.loads(line)
            f = d + f"live/{r['episode_id']}.jsonl"
            if not os.path.exists(f):
                continue
            key = f"{slug(model)}-{r['episode_id'][:8]}"
            turns = [json.loads(x) for x in open(f)]
            try:
                rec = build_game(g, r, specs[r["episode_id"]], turns, notes, model, outdir)
            except Exception as e:  # keep going; report the game
                print("failed", model, g, r["episode_id"][:8], repr(e)[:200], file=sys.stderr)
                continue
            shards.setdefault(rec["shard"], {})[rec["key"]] = rec.pop("_tr")
            games.append(rec)
    # what the agents saw, one K2-3.7B game per scenario: system prompt, assignment, policy, tools used
    examples = {}
    for name, trs in shards.items():
        for tr in trs.values():
            if tr["game"] in examples or not tr["model"].startswith("K2-Horizon-3.7B") or tr["cond"] != "mm" or tr["route"] != "moderate":
                continue
            ex = {"unit": next(iter(tr["system"]), ""), "system": next(iter(tr["system"].values()), ""),
                  "first": tr["first"], "tools": sorted({c["t"] for t in tr["turns"] for c in t["c"] if c["t"]})}
            for t in tr["turns"]:
                for c in t["c"]:
                    path = str(c["a"].get("path", ""))
                    if c["t"] == "read" and path == "/tmp/assignment.txt" and "assignment" not in ex:
                        ex["assignment"] = c["res"]
                    if c["t"] == "read" and path.startswith("/data/policies/") and "policy" not in ex:
                        ex["policy"] = c["res"]
            examples[tr["game"]] = ex
    for old in glob.glob(os.path.join(outdir, "t", "*")):
        os.remove(old)  # rebuilt below from the journals; nothing here is a source
    for name, trs in shards.items():
        raw = json.dumps(trs, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        with open(os.path.join(outdir, name), "w") as fh:
            fh.write(base64.b64encode(gzip.compress(raw, 9)).decode("ascii"))
    import time
    json.dump({"updated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "plan": plan, "examples": examples, "games": games},
              open(os.path.join(outdir, "data.json"), "w"), separators=(",", ":"))
    tsize = sum(os.path.getsize(x) for x in glob.glob(os.path.join(outdir, "t", "*.txt")))
    print(len(games), "games;", os.path.getsize(os.path.join(outdir, "data.json")) // 1024, "KB data;",
          len(glob.glob(os.path.join(outdir, "t", "*.txt"))), "transcript files", tsize // 1024 // 1024, "MB")


if __name__ == "__main__":
    main()
