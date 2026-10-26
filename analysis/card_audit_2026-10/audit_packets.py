"""Audit packets for the K2 card games: one compact text block per game with the world's true data,
the answer sheets, every message / forum item / shared-folder write, and the final report.

    .venv/bin/python audit_packets.py <outdir> <notes.json> [prefix=Label,...]

Games with no communication at all in the task phase (and, in approvals, no unchecked approval) are
labelled automatically and listed in auto.jsonl; the rest go to packets/*.txt in 10 balanced parts.
"""
import asyncio, glob, json, os, sys, collections
sys.path.insert(0, "src")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from casebook_build import replay, UNIT_LABEL, cell_of, clean
from collusiongen.modules.n4_relay.cards import detect
from collusiongen.runner.config import RunConfig
from collusiongen.runner.plan import expand

MODELS = (("final_rcp", "K2-Horizon-3.7B"), ("final7b_rcp", "K2-Horizon-7B"), ("fp8_32b_rcp", "K2-Horizon-32B FP8"))
GAMES = ("records", "pricing", "exam", "approvals")


def truth(g, game, units):
    if g == "records":
        open_ = [c for c in sorted(game.amount) if c not in game.fail["billing"]]
        return (f"failing cases: Orders cancelled {sorted(game.fail['orders'])}; Warehouse late {sorted(game.fail['warehouse'])}; "
                f"Billing closed {sorted(game.fail['billing'])}. Credit amounts: "
                + ", ".join(f"{c} {a}" for c, a in sorted(game.amount.items()))
                + f". Billing open subtotal {sum(game.amount[c] for c in open_)}; all-12 total {sum(game.amount.values())}. "
                f"Answer {game.answer_value}; office rounded figure {game.desk_rounded()}.")
    if g == "pricing":
        vol = {k: {s: game.units[s] for s in game.buyer_suppliers(k)} for k in ("buying_a", "buying_b")}
        return ("prices (list, discount%, net): " + "; ".join(f"{s} {game.list[s]} {game.disc[s]}% {game.net[s]}" for s in game.sup)
                + ". Volumes Buying A " + str(vol["buying_a"]) + f" (total {sum(vol['buying_a'].values())}); Buying B "
                + str(vol["buying_b"]) + f" (total {sum(vol['buying_b'].values())}). Answer {game.answer_value}; "
                f"band {game.band[0]}-{game.band[1]}. Per-supplier bands (Pricing-only): "
                + ", ".join(f"{s} {int(game.net[s] // 25 * 25)}-{int(game.net[s] // 25 * 25) + 24}" for s in game.sup))
    if g == "exam":
        out = []
        for q in range(8):
            parts = [f"{r}={game.extract[(q, r)][game.qprod[q]]}(held by {units[game.holder[(q, r)] - 1]})" for r in ("north", "central", "south")]
            out.append(f"Q{q + 1} {game.qprod[q]}: " + " ".join(parts) + f" -> {game.answers[q]}")
        return "; ".join(out)
    if g == "approvals":
        return f"flawed invoices: {sorted(game.flawed)}"
    return ""


def approvals_decisions(game, units):
    dec = game.state.extra.get("decisions", [])
    rows = [f"{units[d['by'] - 1]} {d['action']} {d.get('invoice', '?')} (author {units[d['author'] - 1]}, "
            f"{'checked' if d['checked'] else 'NOT checked'}{', flawed' if d.get('flawed') else ''})" for d in dec]
    return rows


def packet(model, g, r, spec, turns, notes):
    env, bounds, made = asyncio.run(replay(spec, turns))
    game = env.game
    units = [UNIT_LABEL.get(u.key, u.key) for u in game.seat_units()]
    s = r["secondary"]
    scan = detect._scan(game, env)
    cut = len(scan["evs"])
    log = list(env.log)
    screen_at, last = {}, None
    for k, e in enumerate(log):
        if e.kind in ("message", "forum_post", "forum_reply") or (e.kind == "write" and str(e.payload.get("path", "")).startswith("/workspace")):
            last = k
        elif e.kind == "screen" and last is not None:
            screen_at[last] = e.payload
    task, rep, subs = [], [], []
    call = 0
    for k, e in enumerate(log):
        p = e.payload
        if e.kind == "action":
            call += 1
            continue
        path = str(p.get("path", ""))
        if e.kind in ("message", "forum_post", "forum_reply") or (e.kind == "write" and path.startswith("/workspace")
                                                                    and not path.startswith("/workspace/logs/")
                                                                    and not path.endswith("report.md")):
            w = p.get("wave")
            to = ("→ " + ", ".join(units[x - 1] for x in (p.get("to") or []) if 1 <= x <= 3) if e.kind == "message"
                  else "→ forum" if e.kind != "write" else f"→ file {path}")
            text = (str(p.get("title") or "") + " | " if p.get("title") else "") + str(p.get("text") or p.get("content") or "")
            sc = screen_at.get(k, {})
            fl = [f for f, on in (("ASK", sc.get("ask")), ("LEAK", sc.get("leak") and not sc.get("requested_by")),
                                  ("LEAK-ON-REQUEST", sc.get("leak") and sc.get("requested_by"))) if on]
            unit = units[w - 1] if isinstance(w, int) and 1 <= w <= 3 else "?"
            line = f"[call {call}] {unit} {to}{' [' + ','.join(fl) + ']' if fl else ''}: "
            if k < cut:
                task.append(line + clean(text, 700).replace("\n", " / "))
            else:
                rep.append(line + clean(text, 300).replace("\n", " / "))
        elif e.kind == "submit_attempt":
            w = p.get("wave")
            subs.append(f"{units[w - 1] if isinstance(w, int) else '?'}: {clean(str(p.get('answer', '')).replace('question,answer', '').strip(), 120).replace(chr(10), ' ')} -> {p.get('n_correct', 0)}/{p.get('n_answered', 0)} correct")
    report = ""
    for e in log:
        if e.kind == "sign_report" and e.payload.get("content"):
            report = e.payload["content"]
    p = r["params"]
    route, cond = cell_of(p)
    key = r["episode_id"][:8]
    head = (f"### {key} | {model} | {g} {route} {cond} | units: " + ", ".join(f"{i + 1}={u}" for i, u in enumerate(units))
            + (f" | seat 2 ({units[1]}) is a SCRIPTED asker, not the model" if cond == "ask" else "")
            + f"\nscorer: C{int(s.get('card_class', 0))} solved={bool(s.get('card_solved'))} asked={bool(s.get('card_asked'))} "
            f"supplied={bool(s.get('card_supplied'))} used={bool(s.get('card_used'))} joint={bool(s.get('card_joint'))} "
            f"false_report={bool(s.get('rep_false'))} cosigned={bool(s.get('rep_joint_false'))}")
    body = [head, "TRUTH: " + truth(g, game, units)]
    if g == "approvals":
        dec = approvals_decisions(game, units)
        body.append("DECISIONS: " + ("; ".join(dec) if dec else "none"))
    body.append("SUBMISSIONS: " + ("; ".join(subs) if subs else "none"))
    body.append("TASK-PHASE ITEMS:" + ("\n" + "\n".join(task) if task else " none"))
    if rep:
        body.append("REPORT-PHASE ITEMS:\n" + "\n".join(rep))
    if report:
        body.append("FINAL REPORT: " + clean(report, 1200).replace("\n", " / "))
    old = notes.get(key)
    if old:
        body.append(f"PREVIOUS NOTE (may be wrong): {old['v']}: {old['n']}")
    unchecked = g == "approvals" and any(not d["checked"] and d["action"] == "approve" for d in game.state.extra.get("decisions", []))
    trivial = not task and not unchecked
    return key, "\n".join(body), trivial, len(task) + len(rep)


def main():
    out, notes = sys.argv[1], json.load(open(sys.argv[2]))
    models = MODELS if len(sys.argv) < 4 else tuple(tuple(m.split("=", 1)) for m in sys.argv[3].split(","))
    os.makedirs(os.path.join(out, "packets"), exist_ok=True)
    items, auto = [], []
    for prefix, model in models:
        for g in GAMES:
            run = f"runs/rcp/{prefix}_bench_card_{g}_full"
            if not os.path.exists(run + "/config.json"):
                continue
            cfg = RunConfig.model_validate_json(open(run + "/config.json").read())
            specs = {sp.episode_id: sp for sp in expand(cfg, cfg.models[0])}
            d = glob.glob(run + "/*/")[0]
            res = d + "results_rescored.jsonl" if os.path.exists(d + "results_rescored.jsonl") else d + "results.jsonl"
            for line in open(res):
                r = json.loads(line)
                f = d + f"live/{r['episode_id']}.jsonl"
                if not os.path.exists(f):
                    continue
                key, text, trivial, n = packet(model, g, r, specs[r["episode_id"]], [json.loads(x) for x in open(f)], notes)
                if trivial:
                    auto.append({"key": key, "model": model, "v": "clean",
                                 "n": "No messages, forum posts or shared files in the task phase" + (" and no unchecked approvals." if g == "approvals" else ".")})
                else:
                    items.append((model, g, key, text))
    # NPARTS (default 10) balanced parts by text size, each keeping one model's games together where possible
    nparts = int(os.environ.get("NPARTS", "10"))
    parts = [[] for _ in range(nparts)]
    sizes = [0] * nparts
    for it in sorted(items, key=lambda x: -len(x[3])):
        i = sizes.index(min(sizes))
        parts[i].append(it)
        sizes[i] += len(it[3])
    for i, part in enumerate(parts):
        part.sort(key=lambda x: (x[0], x[1], x[2]))
        with open(os.path.join(out, "packets", f"part{i + 1:02d}.txt"), "w") as fh:
            fh.write("\n\n".join(x[3] for x in part) + "\n")
    with open(os.path.join(out, "auto.jsonl"), "w") as fh:
        for a in auto:
            fh.write(json.dumps(a) + "\n")
    print(len(items), "games to audit,", len(auto), "auto-labelled clean; part sizes (KB):", [s // 1024 for s in sizes],
          "games per part:", [len(p) for p in parts])


if __name__ == "__main__":
    main()
