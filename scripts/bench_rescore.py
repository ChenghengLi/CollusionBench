#!/usr/bin/env python
"""Re-score finished benchmark v1 games with the current detector, without calling any model.

    python scripts/bench_rescore.py runs/api/<run_prefix>_bench_<scenario>_<block> [--check]

Each game is rebuilt from its instance seed and played again, turn by turn, from its transcript
journal: a reply with several tool calls runs as one batch for the same agent, as it did live
(review 2026-10-23: replaying one call at a time credited batched calls to the wrong agent). A game
whose journal does not cover every logged call falls back to the logged actions one at a time. The
replayed calls are checked against the logged ones; a game that does not replay exactly keeps its
stored result and is reported. The outcome is computed by today's code; the run's own params
(card_env) keep the environment as it was played, so only scoring changes apply.

The original results.jsonl is never touched: the new records go to results_rescored.jsonl next to
it (an earlier one is kept as results_rescored.<date>.jsonl), and bench_report.py reads it when it
exists. With --check, nothing is written and each game's replay is compared field by field with the
stored result (a replay of unchanged code must match).
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from collusiongen.core.env import Services  # noqa: E402
from collusiongen.core.log import EventLog  # noqa: E402
from collusiongen.core.registry import get_module  # noqa: E402
from collusiongen.runner.config import RunConfig  # noqa: E402
from collusiongen.runner.plan import expand  # noqa: E402
from collusiongen.runner.episode import make_variant  # noqa: E402


def _calls(t: dict) -> list[dict]:
    return t.get("applied_batch") or [t.get("applied")]


async def replay(spec, actions: list[dict], turns: list[dict]) -> tuple[dict, int]:
    """Play the game again; returns (outcome, number of calls that differ from the log). The journal
    can hold a few more calls than the log (calls the environment dropped, e.g. past the budget):
    the batched replay is tried anyway and kept when it reproduces the log exactly (2026-10-24: 19
    such games fell back to one call at a time, which credits batched calls to the wrong agent)."""
    if turns:
        out, diff = await _replay(spec, actions, turns, batched=True)
        if not diff:
            return out, 0
    return await _replay(spec, actions, turns, batched=False)


async def _replay(spec, actions: list[dict], turns: list[dict], batched: bool) -> tuple[dict, int]:
    module = get_module(spec.module_id)
    env = module.make_env(spec.instance, make_variant(module, spec), EventLog(spec.episode_id), Services())
    logged = [e["payload"]["action"] for e in actions]
    played: list[dict] = []
    if batched:
        for t in turns:
            seat = env.next_seat()
            if seat is None or seat != t.get("seat"):
                break
            env.observe(seat)
            batch = t.get("applied_batch")
            if batch:
                await env.apply_batch(seat, batch)
                played += batch
            else:
                await env.apply(seat, t["applied"], substituted=bool(t.get("substituted")))
                played.append(t["applied"])
    else:
        for e in actions:
            seat = env.next_seat()
            if seat is None or seat != e["seat"]:
                break
            env.observe(seat)
            await env.apply(seat, e["payload"]["action"], substituted=bool(e["payload"].get("substituted")))
            played.append(e["payload"]["action"])
    applied = [e.payload["action"] for e in env.log if e.kind == "action"]
    diff = sum(a != b for a, b in zip(applied, logged)) + abs(len(applied) - len(logged))
    out = env.outcome()
    return {"secondary": dict(out.secondary), "extra": dict(out.extra), "task_success": out.task_success}, diff


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    run = Path(args.run)
    cfg = RunConfig.model_validate_json((run / "config.json").read_text())
    for model in cfg.models:
        specs = {s.episode_id: s for s in expand(cfg, model)}
        for res_file in glob.glob(str(run / "*" / "results.jsonl")):
            folder = Path(res_file).parent
            actions: dict[str, list[dict]] = defaultdict(list)
            for line in open(folder / "events.jsonl"):
                e = json.loads(line)
                if e["kind"] == "action":
                    actions[e["episode_id"]].append(e)
            turns: dict[str, dict[int, dict]] = defaultdict(dict)
            if (folder / "transcripts.jsonl").exists():
                for line in open(folder / "transcripts.jsonl"):
                    t = json.loads(line)
                    turns[t["episode_id"]][t["step"]] = t
            rows, diffs, bad = [], 0, []
            for line in open(res_file):
                r = json.loads(line)
                spec = specs.get(r["episode_id"])
                if spec is None or r.get("error"):
                    rows.append(r)
                    continue
                acts = sorted(actions[r["episode_id"]], key=lambda e: e["seq"])
                tt = [turns[r["episode_id"]][k] for k in sorted(turns[r["episode_id"]])]
                new, nd = asyncio.run(replay(spec, acts, tt))
                if nd:
                    bad.append(r["episode_id"][:8])
                    rows.append({**r, "rescore_failed": f"{nd} calls differ from the log"})
                    continue
                if args.check:
                    diff = {k: (r["secondary"].get(k), v) for k, v in new["secondary"].items()
                            if r["secondary"].get(k) != v}
                    if diff:
                        diffs += 1
                        print(r["episode_id"][:8], r["params"].get("card_condition"), diff)
                else:
                    changed = {k: (r["secondary"].get(k), v) for k, v in new["secondary"].items()
                               if k.startswith(("card_joint", "card_solo", "card_class", "card_asked",
                                                "card_supplied", "card_used", "card_solved", "rep_", "f_"))
                               and r["secondary"].get(k) != v}
                    if changed:
                        print(r["episode_id"][:8], r["params"].get("route_cost"),
                              r["params"].get("card_condition"), r["condition"], changed)
                    r = {**r, "secondary": new["secondary"], "extra": new["extra"], "rescored": True}
                rows.append(r)
            if bad:
                print(f"{folder.name}: {len(bad)} games did not replay exactly, kept as stored: {bad}")
            if args.check:
                print(f"{folder.name}: {len(rows)} games, {diffs} differ from the stored result")
            else:
                out = folder / "results_rescored.jsonl"
                if out.exists():
                    shutil.copy(out, folder / f"results_rescored.{time.strftime('%Y%m%d-%H%M%S')}.jsonl")
                with open(out, "w") as fh:
                    for r in rows:
                        fh.write(json.dumps(r) + "\n")
                print(f"{folder.name}: wrote {len(rows)} rescored games")


if __name__ == "__main__":
    main()
