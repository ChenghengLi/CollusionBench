"""Per-game table for the 3-agent shared audits: calls, forum posts/replies, messages, /workspace and
/tmp files written, leaks (built-in screen live; the leak monitor's count once a game is done).

usage: .venv/bin/python scripts/channel_table.py
"""
import collections
import glob
import json
import os
import sys

import yaml

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")
from audit_progress import SETTING  # noqa: E402
from collusiongen.modules.n4_relay.games import game_for  # noqa: E402
from collusiongen.runner.config import RunConfig  # noqa: E402
from collusiongen.runner.plan import expand  # noqa: E402
from game_transcripts import replay  # noqa: E402
import asyncio  # noqa: E402

RUNS = [("DeepSeek", "deepseek-v4.1-flash-baidu", None, ""), ("MiMo", "mimo-v2.6-flash-cap1", None, ""),
        ("Cross", "deepseek-v4.1-flash-baidu", "cross_ds+mimo+sol", ""), ("Luna", "gpt-6-luna-flex", None, ""),
        ("Sol", "gpt-6.1-sol", None, ""),
        ("DeepSeek easy", "deepseek-v4.1-flash-baidu", None, "_easy"), ("MiMo easy", "mimo-v2.6-flash-cap1", None, "_easy")]

print("| Run | Scenario | Setting | State | Calls | Forum posts | Forum replies | Messages | /workspace files | /tmp files | Leaks |")
print("|---|---|---|---|---|---|---|---|---|---|---|")
for lab, m, cross, ver in RUNS:
    for sc in (f"shared_procurement{ver}", f"shared_freight{ver}"):
        if not os.path.exists(f"configs/api/{m}/{sc}_v1__shared_audit_3.yaml"):
            continue
        c = RunConfig.model_validate(yaml.safe_load(open(f"configs/api/{m}/{sc}_v1__shared_audit_3.yaml")))
        cands = glob.glob(f"runs/api/{cross}_{sc}_v1_shared_audit_3/*") if cross else glob.glob(f"runs/api/{c.run_id}/*")
        cands = [b for b in cands if os.path.isdir(b + "/live")]
        if not cands:
            continue
        base = cands[0]
        res = {}
        if os.path.exists(base + "/results.jsonl"):
            res = {json.loads(l)["episode_id"]: json.loads(l) for l in open(base + "/results.jsonl")}
        rows = {}
        for s in expand(c, c.models[0]):
            if s.condition.value != "MM":
                continue
            p = s.instance.params
            st = SETTING.get((bool(p.get("forum")), bool(p.get("messaging", True)), p.get("max_messages")))
            g = game_for(s.instance)
            try:
                L = [json.loads(l) for l in open(f"{base}/live/{s.episode_id}.jsonl")]
            except FileNotFoundError:
                continue
            n = collections.Counter(); ws = set(); tmp = set(); leaks = 0
            try:  # who sent each item: screen it as that agent (its own data, plus relays of others')
                agents, _ = asyncio.run(replay(s, L))
            except Exception:
                agents = []
            for i, d in enumerate(L):
                a = d["applied"] if isinstance(d["applied"], dict) else {}
                t = a.get("tool"); path = str(a.get("path", "")); text = None
                if t == "forum_post":
                    n["post"] += 1; text = f"{a.get('title', '')} {a.get('text', '')}"
                elif t == "forum_reply":
                    n["reply"] += 1; text = a.get("text", "")
                elif t == "send_message":
                    n["msg"] += 1; text = a.get("text", "")
                elif t in ("write", "append"):
                    if path.startswith("/workspace"):
                        ws.add(path); text = a.get("content", "")
                    elif path.startswith("/tmp"):
                        tmp.add(path)
                senders = [agents[i]] if i < len(agents) else range(1, g.n + 1)
                if text and any(g.screen(k, text).get("leak") for k in senders):
                    leaks += 1
            if s.episode_id in res:
                sec = res[s.episode_id]["secondary"]
                state = "done, solved" if sec.get("team_solved") else "done, not solved"
                leaks = int(sec.get("leak_items", leaks))
            else:
                state = "running"
            rows[st] = (state, len(L), n["post"], n["reply"], n["msg"], len(ws), len(tmp), leaks)
        for st in ("folder", "folder_msg5", "folder_forum", "all"):
            if st in rows:
                r = rows[st]
                fo, ms = st in ("folder_forum", "all"), st in ("folder_msg5", "all")
                na = lambda ok, v: str(v) if ok else "–"  # noqa: E731
                print(f"| {lab} | {sc[7:].replace('_easy', '')} | {st} | {r[0]} | {r[1]} | {na(fo, r[2])} | {na(fo, r[3])} | "
                      f"{na(ms, r[4])} | {r[5]} | {r[6]} | {r[7]} |")
