"""Stats and conversation digests for the per-model sites.

For every model explorer: per-task figures over the games it played (consts), the game-shape
figures for the dynamics section (dyn), and the same figures over the settings all five models
played (four channels + message caps 1, 3, 5), for the cross-model table (peers.json).
With --digest, also write <key>_digest/<task>.txt: every finished game as a readable log.

    .venv/bin/python nm_stats.py [--digest]
"""
import base64
import collections
import glob
import gzip
import json
import re
import statistics as st
import sys

SP = "/private/tmp/claude-501/-Users-chenghengli-Desktop-semester-project/cf8e5b8d-1387-44e3-b034-6824de9e85b8/scratchpad"
T = ("survey_v1", "depot_v1", "seating_v1")
NON = re.compile(r"unable|cannot|can't|blocked|unsolved|no answer|insufficient|incomplete|not determin|refus|could not|no verified", re.I)
# key: (label, caps played in the message-cap experiment)
MODELS = {
    "ds": ("DeepSeek V4.1 Flash", set(range(1, 11))),
    "hk": ("Claude Haiku 5.5", set(range(1, 7))),
    "mm": ("MiMo V2.6 Flash", {1, 3, 5, 7, 9}),
    "gl": ("GLM-5.3-Flash", {1, 3, 5, 7, 9}),
    "lu": ("GPT-6 Luna", {1, 3, 5, 7, 9}),
}
COMMON = {1, 3, 5}


def load(key):
    s = json.load(open(f"{SP}/{key}_explorer/data/summary.json"))
    detail = {}
    for f in glob.glob(f"{SP}/{key}_explorer/data/g/*.txt"):
        detail.update(json.loads(gzip.decompress(base64.b64decode(open(f).read()))))
    return s, detail


def played(g, caps):
    return g["status"] == "done" and (g["experiment"] != "dmcap" or g["cap"] in caps)


def consts(G, cost_games):
    mv = sum(len(g["seq"]) for g in G)
    stp = sum(g["seq"].count("!") for g in G)
    subs = [x for g in G for x in g["submits"]]
    n = max(1, len(G))
    return dict(
        done=len(G), solved=sum(g["correct"] for g in G), leak=sum(bool(g["leak"]) for g in G),
        verbatim=sum(1 for g in G if (g["leak_kinds"] or {}).get("verbatim")),
        totals=sum(1 for g in G if (g["leak_kinds"] or {}).get("totals")),
        stop=round(100 * stp / max(1, mv)), nonans=round(100 * sum(1 for x in subs if NON.search(str(x))) / max(1, len(subs))),
        refused=sum(bool(g["refused"]) for g in G), contact=round(100 * sum(1 for g in G if g["first_contact"] is not None) / n),
        asks=sum(g["asks"] for g in G), dms=sum(g["dms"] for g in G), posts=sum(g["posts"] for g in G), ws=sum(g["ws_writes"] for g in G),
        cost=round(sum(g["cost"] for g in cost_games), 2), calls=round(sum(g["calls"] for g in G) / n),
    )


def dyn_of(G, detail):
    onset, ever, agents, pas, req = [], 0, 0, [], 0
    ans = collections.Counter()
    fc = [g["first_contact"] / g["calls"] for g in G if g["first_contact"] is not None]
    for g in G:
        stp = detail[g["id"]]["steps"]
        for a in range(1, g["agents"] + 1):
            mv = [x for x in stp if x["a"] == a]
            agents += 1
            k = next((j for j, x in enumerate(mv) if x["t"] == "invalid"), None)
            if k is not None:
                ever += 1
                onset.append(k)
            pas.append(sum(1 for x in mv if x["t"] == "invalid"))
        for x in stp:
            if x["t"] == "send_message" and x.get("rq") and str(x["args"].get("to", "")).isdigit():
                req += 1
                b = int(x["args"]["to"])
                later = [y for y in stp if y["i"] > x["i"] and y["a"] == b and y["t"] in ("send_message", "forum_post", "forum_reply", "write", "append")]
                to_req = [y for y in later if str(y["args"].get("to")) == str(x["a"]) or y["t"] != "send_message"]
                ans["gave" if any(y.get("lk") for y in later) else "refused" if any(y.get("rf") for y in to_req) else "replied" if to_req else "none"] += 1
    told = [g for g in G if g["lineup"] == "told"]
    unp = [g for g in G if g["lineup"] == "unprompted"]
    mean = lambda xs: round(st.mean(xs), 1) if xs else 0
    return dict(
        games=len(G), agents=agents, stopped=ever, onset=round(st.median(onset)) if onset else None, stops_per_agent=round(st.mean(pas)) if pas else 0,
        contact=len(fc), first_contact=round(100 * st.median(fc)) if fc else None, requests=req, gave=ans["gave"], refused=ans["refused"], replied=ans["replied"], none=ans["none"],
        leak_told=sum(1 for g in told if g["leak"]), leak_unp=sum(1 for g in unp if g["leak"]), n_told=len(told), n_unp=len(unp),
        contact_told=sum(1 for g in told if g["first_contact"] is not None), contact_unp=sum(1 for g in unp if g["first_contact"] is not None),
        ws_told=mean([g["ws_writes"] for g in told]), ws_unp=mean([g["ws_writes"] for g in unp]),
        solved=sum(g["correct"] for g in G), solved_told=sum(g["correct"] for g in told), solved_unp=sum(g["correct"] for g in unp),
        solved_by={n: [sum(1 for g in G if g["agents"] == n and g["correct"]), sum(1 for g in G if g["agents"] == n)] for n in (2, 3, 4)},
    )


def clip(x, n):
    x = str(x or "").replace("\n", " / ")
    return x if len(x) <= n else x[:n] + " …"


def digest(G, detail, out_dir):
    import os
    os.makedirs(out_dir, exist_ok=True)
    out = collections.defaultdict(list)
    for g in G:
        task = g["model"].split(" ·")[0]
        d = detail[g["id"]]
        stp = d["steps"]
        setting = f"message cap {g['cap']}" if g["experiment"] == "dmcap" else {"files": "files only", "forum": "forum only", "DM": "direct messages (cap 5)", "forum+DM": "forum + direct messages"}[g["setting"]]
        L = [f"=== GAME {g['id']} | {task} | {setting} | {g['agents']} agents | {g['lineup']} | {'SOLVED' if g['correct'] else 'not solved'} | passed on own data: {('agents ' + ','.join(map(str, g['leakers'])) + ' ' + str({k: v for k, v in g['leak_kinds'].items() if v})) if g['leak'] else 'nobody'} | refusal msgs by: {g['refusers'] or '-'} | calls {g['calls']}/{g['max_calls']}"]
        L.append("ownership: " + "; ".join(f"agent {k}: {len(v)} files" for k, v in d["ownership"].items()))
        seen = collections.defaultdict(set)

        def think(x, why):
            if x.get("think") and why not in seen[x["a"]]:
                seen[x["a"]].add(why)
                L.append(f"   [agent {x['a']} reasoning at #{x['i']} ({why})]: {clip(x['think'], 450)}")

        stops = collections.Counter()
        subs = collections.defaultdict(collections.Counter)
        sent, recv = {}, set()
        for x in stp:
            a = x["args"]
            if x["t"] == "invalid":
                stops[x["a"]] += 1
                if stops[x["a"]] == 1:
                    think(x, "first move with no tool call")
                    L.append(f"#{x['i']} agent {x['a']} NO TOOL CALL (first time) reply text: {clip(x.get('say'), 300)}")
                continue
            if x["t"] in ("send_message", "forum_post", "forum_reply", "write", "append"):
                body = (("[" + a.get("title", "") + "] ") if a.get("title") else "") + (a.get("text") or a.get("content") or "")
                # An agent repeating its own earlier message word for word: one short line instead.
                rkey = (x["a"], x["t"], str(a.get("to") or a.get("path") or ""), body[:300])
                if rkey in sent:
                    L.append(f"#{x['i']} agent {x['a']} {x['t']} (repeats its #{sent[rkey]})")
                    continue
                sent[rkey] = x["i"]
                tags = "".join([" <LEAK:" + x["lk"] + ">" if x.get("lk") else "", " <REFUSAL>" if x.get("rf") else "", " <REQUEST>" if x.get("rq") else ""])
                dest = f" to agent {a.get('to')}" if a.get("to") else (f" {a.get('path')}" if a.get("path") else (f" reply to post {a.get('post')}" if a.get("post") else ""))
                L.append(f"#{x['i']} agent {x['a']} {x['t']}{dest}{tags}: {clip(body, 700)} -> {clip(x['r'], 60)}")
                think(x, "first " + ("refusal" if x.get("rf") else "leak" if x.get("lk") else "request" if x.get("rq") else "communication"))
            elif x["t"] in ("read_messages", "forum_read") and ("agent" in x["r"][:200]) and "no new" not in x["r"].lower():
                if (x["a"], x["r"][:300]) in recv:
                    continue
                recv.add((x["a"], x["r"][:300]))
                L.append(f"#{x['i']} agent {x['a']} {x['t']} received: {clip(x['r'], 500)}")
                think(x, "after first received message")
            elif x["t"] == "read" and str(a.get("path", "")).startswith("/workspace") and x["r"] and not x["r"].startswith("error"):
                L.append(f"#{x['i']} agent {x['a']} read {a.get('path')}: {clip(x['r'], 300)}")
            elif x["t"] == "submit":
                subs[x["a"]][clip(a.get("answer"), 140)] += 1
                if x["r"].startswith("correct"):
                    L.append(f"#{x['i']} agent {x['a']} SUBMIT {clip(a.get('answer'), 140)} -> CORRECT")
                    think(x, "correct submission")
        for ag, c in sorted(subs.items()):
            L.append(f"submissions agent {ag}: " + " | ".join(f"{k} (x{v})" for k, v in c.most_common(4)))
        L.append("moves with no tool call per agent: " + (", ".join(f"agent {k}: {v}" for k, v in sorted(stops.items())) or "none"))
        last = {}
        for x in stp:
            if x.get("think"):
                last[x["a"]] = x
        for ag, x in sorted(last.items()):
            L.append(f"   [agent {ag} last reasoning #{x['i']}]: {clip(x['think'], 350)}")
        out[task].append("\n".join(L) + "\n")
    for t, v in out.items():
        open(f"{out_dir}/{t}.txt", "w").write("\n".join(v))
        print("  digest", out_dir.split("/")[-1], t, len(v), "games", sum(map(len, v)) // 1000, "k chars")


peers = {}
for key, (label, caps) in MODELS.items():
    s, detail = load(key)
    res = {"label": label, "own": {}, "common": {}, "dyn": {}}
    for t in T:
        allg = [g for g in s["games"] if g["model"].startswith(t)]
        G = [g for g in allg if played(g, caps)]
        C = [g for g in allg if played(g, COMMON)]
        res["own"][t] = consts(G, [g for g in allg if g["status"] == "done" and (g["experiment"] != "dmcap" or g["cap"] in caps)])
        res["common"][t] = consts(C, C)
        res["dyn"][t] = dyn_of(G, detail)
    peers[key] = res
    print(key, label, {t: (res["own"][t]["done"], res["own"][t]["solved"], res["own"][t]["leak"], res["own"][t]["cost"]) for t in T})
    if "--digest" in sys.argv and key in ("mm", "gl", "lu"):
        digest([g for g in s["games"] if played(g, caps)], detail, f"{SP}/{key}_digest")
json.dump(peers, open(f"{SP}/peers.json", "w"))
print("wrote peers.json")
