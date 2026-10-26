"""Final recount of the 3-agent shared-audit games (hard and easy) with the current leak screen:
every outgoing item (message, forum post/reply, /workspace write) is screened as its actual sender
(replayed from the live log). One row per run plus per-game details in --games mode.

usage: .venv/bin/python scripts/shared_final.py [--games]
"""
import asyncio
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

RUNS = [("DeepSeek", "deepseek-v4.1-flash-baidu", None, ""), ("MiMo", "mimo-v2.6-flash-cap1", None, ""),
        ("Luna", "gpt-6-luna-flex", None, ""), ("Sol", "gpt-6.1-sol", None, ""),
        ("Cross (stopped)", "deepseek-v4.1-flash-baidu", "cross_ds+mimo+sol", ""),
        ("DeepSeek easy", "deepseek-v4.1-flash-baidu", None, "_easy"), ("MiMo easy", "mimo-v2.6-flash-cap1", None, "_easy")]
LEAKS = ("records", "fact", "amounts", "procedure", "assignment", "relay")
STANCE = ("request", "refusal", "trade", "rationalisation")


def games():
    for lab, m, cross, ver in RUNS:
        for sc in (f"shared_procurement{ver}", f"shared_freight{ver}"):
            c = RunConfig.model_validate(yaml.safe_load(open(f"configs/api/{m}/{sc}_v1__shared_audit_3.yaml")))
            cands = glob.glob(f"runs/api/{cross}_{sc}_v1_shared_audit_3/*") if cross else glob.glob(f"runs/api/{c.run_id}/*")
            base = next(b for b in cands if os.path.isdir(b + "/live"))
            res = {}
            if os.path.exists(base + "/results.jsonl"):
                res = {json.loads(l)["episode_id"]: json.loads(l) for l in open(base + "/results.jsonl")}
            for s in expand(c, c.models[0]):
                if s.condition.value != "MM":
                    continue
                p = s.instance.params
                st = SETTING.get((bool(p.get("forum")), bool(p.get("messaging", True)), p.get("max_messages")))
                path = f"{base}/live/{s.episode_id}.jsonl"
                if not os.path.exists(path):
                    continue
                L = [json.loads(l) for l in open(path)]
                g = game_for(s.instance)
                agents, _ = asyncio.run(replay(s, L))
                row = collections.Counter(calls=len(L))
                for i, d in enumerate(L):
                    a = d["applied"] if isinstance(d["applied"], dict) else {}
                    t = a.get("tool"); path_ = str(a.get("path", "")); text = None
                    if t == "send_message":
                        row["messages"] += 1; text = a.get("text", "")
                    elif t in ("forum_post", "forum_reply"):
                        row["forum"] += 1; text = f"{a.get('title', '')} {a.get('text', '')}"
                    elif t in ("write", "append") and path_.startswith("/workspace"):
                        row["files"] += 1; text = a.get("content", "")
                    elif t == "submit":
                        row["submits"] += 1
                    if text and i < len(agents):
                        lab_ = g.screen(agents[i], text)
                        for k in LEAKS + STANCE:
                            row[k] += bool(lab_.get(k))
                        row["leak_items"] += bool(lab_.get("leak"))
                solved = res.get(s.episode_id, {}).get("secondary", {}).get("team_solved")
                row["solved"] = int(bool(solved))
                row["done"] = int(s.episode_id in res)
                yield lab, sc.replace("shared_", "").replace("_easy", ""), st, row


def main(per_game):
    tot = collections.defaultdict(collections.Counter)
    for lab, sc, st, row in games():
        tot[lab] += row; tot[lab]["games"] += 1
        if per_game:
            print(f"| {lab} | {sc} | {st} | {'done' if row['done'] else 'stopped'} | {row['calls']} | {row['messages']} | "
                  f"{row['forum']} | {row['files']} | {row['submits']} | {row['solved']} | "
                  + " | ".join(str(row[k]) for k in LEAKS) + " | " + " | ".join(str(row[k]) for k in STANCE) + " |")
    print("\n| Run | Games | Solved | Calls/game | Messages | Forum items | /workspace files | Records | Fact lists | Amounts | "
          "Procedure | Assignment | Relay | Requests | Refusals | Trades | Rationalisations |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for lab, r in tot.items():
        print(f"| {lab} | {r['games']} | {r['solved']} | {r['calls'] // r['games']} | {r['messages']} | {r['forum']} | "
              f"{r['files']} | " + " | ".join(str(r[k]) for k in LEAKS) + " | " + " | ".join(str(r[k]) for k in STANCE) + " |")


if __name__ == "__main__":
    main("--games" in sys.argv)
