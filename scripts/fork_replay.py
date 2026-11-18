#!/usr/bin/env python
"""Counterfactual fork-and-edit replay of a finished game (src/collusiongen/runner/fork.py).

    # the steps of a game, to choose a fork point (who acted, which tool)
    python scripts/fork_replay.py steps --run-dir runs/api/<run_id> --episode <episode_id>

    # 20 forks at step 140 with the colleague's request removed, and 20 control forks
    python scripts/fork_replay.py fork --run-dir runs/api/<run_id> --episode <id> --at 140 \
        --tag noask --samples 20 --edit '{"op": "drop_unread", "to": 3, "contains": "credit amounts"}'
    python scripts/fork_replay.py fork ... --at 140 --tag control --samples 20 --edit '{"op": "none"}'

Forks are written next to the source run's model folder, under forks/ (results.jsonl,
events.jsonl, transcripts.jsonl, errors.jsonl, live/), one record per fork with record["fork"].
The model is served as for the source run (its config.json), so the same endpoint must be up.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import traceback
from pathlib import Path

from collusiongen.core.log import JsonlSink
from collusiongen.core.registry import get_module
from collusiongen.runner.config import RunConfig
from collusiongen.runner.experiment import make_services, model_paths
from collusiongen.runner.fork import play_fork
from collusiongen.runner.plan import expand
from collusiongen.runner.policies import PolicyFactory, make_backend


def load(run_dir: Path, model_name: str | None):
    config = RunConfig.model_validate_json((run_dir / "config.json").read_text())
    models = [m for m in config.models if model_name in (None, m.name)]
    if len(models) != 1:
        raise SystemExit(f"pick one model with --model: {[m.name for m in config.models]}")
    return config, models[0]


def cmd_steps(a: argparse.Namespace) -> None:
    config, model = load(Path(a.run_dir), a.model)
    journal = model_paths(config, model).root / "live" / f"{a.episode}.jsonl"
    for line in journal.read_text().splitlines():
        e = json.loads(line)
        act = e.get("applied") or {}
        args = {k: (str(v)[:60]) for k, v in act.items() if k != "tool"}
        print(f"{e['step']:5}  seat {e['seat']}  {e['kind']:6}  {act.get('tool', ''):16} {args}")


async def cmd_fork(a: argparse.Namespace) -> None:
    config, model = load(Path(a.run_dir), a.model)
    paths = model_paths(config, model)
    spec = next((s for s in expand(config, model) if s.episode_id == a.episode), None)
    if spec is None:
        raise SystemExit(f"episode {a.episode} is not in {a.run_dir}")
    module = get_module(spec.module_id)
    edit = json.loads(a.edit)
    out = paths.root / "forks"
    sinks = {k: JsonlSink(out / f"{k}.jsonl") for k in ("results", "events", "transcripts", "errors")}
    done = {(r["fork"]["tag"], r["fork"]["sample"], r["fork"]["at"], r["fork"]["source_episode"])
            for r in sinks["results"].iter_rows()}
    services, judge = make_services(config.judge)
    backend = make_backend(model.backend)
    factory = PolicyFactory(model, backend)
    sem = asyncio.Semaphore(a.concurrency)

    async def one(k: int) -> None:
        if (a.tag, k, a.at, a.episode) in done:
            return
        async with sem:
            try:
                res = await play_fork(module, spec, factory.seats_for(module, spec), services,
                                      paths.root / "live" / f"{a.episode}.jsonl", a.at, edit,
                                      a.tag, k, out / "live",
                                      max_steps=config.max_steps_per_episode,
                                      log_prompts=config.log_prompts,
                                      max_calls_per_reply=model.max_calls_per_reply)
            except Exception as exc:  # one bad fork must not stop the others
                sinks["errors"].append_many([{"source_episode": a.episode, "tag": a.tag, "sample": k,
                                              "error": repr(exc), "traceback": traceback.format_exc()}])
                return
            sinks["events"].append_many(e.to_json() for e in res.events)
            sinks["transcripts"].append_many(res.transcript)
            sinks["results"].append_many([res.record])
            s = res.record["secondary"]
            print(f"{a.tag} s{k}: breach={s.get('card_breach')} solved={s.get('card_solved')}")

    try:
        await asyncio.gather(*(one(k) for k in range(a.samples)))
    finally:
        if backend is not None:
            await backend.aclose()
        if judge is not None:
            await judge.aclose()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("steps", "fork"):
        p = sub.add_parser(name)
        p.add_argument("--run-dir", required=True)
        p.add_argument("--model")
        p.add_argument("--episode", required=True)
        if name == "fork":
            p.add_argument("--at", type=int, required=True, help="journal step to fork before")
            p.add_argument("--edit", required=True, help="JSON edit (runner/fork.py)")
            p.add_argument("--tag", required=True, help="name of this arm, e.g. noask or control")
            p.add_argument("--samples", type=int, default=20)
            p.add_argument("--concurrency", type=int, default=8)
    a = ap.parse_args()
    if a.cmd == "steps":
        cmd_steps(a)
    else:
        asyncio.run(cmd_fork(a))


if __name__ == "__main__":
    main()
