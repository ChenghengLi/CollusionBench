"""Cross-model games: each agent of one N4 game is played by a different model (the user's request,
2026-10-10). Agent k is played by the k-th model profile given; a router policy sits in both seats
and hands each agent's turn to that agent's own model. Outputs are written like a normal run
(results.jsonl, events.jsonl, transcripts.jsonl, live/<episode>.jsonl), so the analysis scripts work.

usage:
  OPENROUTER_API_KEY=$(cat ~/.config/collusiongen/openrouter_key) \
  .venv/bin/python scripts/cross_model.py --setup shared_audit_3 \
      --tasks shared_procurement_v1 shared_freight_v1 \
      --models deepseek-v4.1-flash-baidu mimo-v2.6-flash-cap1 gpt-6.1-sol [--concurrency 8]

The games are the setup's model games (condition MM) from the first model's config, so they are the
same games (data, assignment, settings) the single-model runs played.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import traceback
import uuid
from pathlib import Path

import yaml

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")
from collusiongen.core.log import JsonlSink  # noqa: E402
from collusiongen.core.registry import get_module  # noqa: E402
from collusiongen.core.types import PolicyKind  # noqa: E402
from collusiongen.runner.config import RunConfig  # noqa: E402
from collusiongen.runner.episode import run_episode  # noqa: E402
from collusiongen.runner.experiment import make_services  # noqa: E402
from collusiongen.runner.plan import expand  # noqa: E402
from collusiongen.runner.policies import PolicyFactory, make_backend  # noqa: E402

log = logging.getLogger("cross_model")
SHORT = {"deepseek-v4.1-flash-baidu": "ds", "mimo-v2.6-flash-cap1": "mimo", "gpt-6.1-sol": "sol",
         "glm-5.3-flash-wafer": "glm", "gpt-6-luna-flex": "luna"}


class Router:
    """Plays every agent with that agent's own model policy."""

    kind = PolicyKind.MODEL

    def __init__(self, by_agent: dict[int, object]) -> None:
        self.by_agent = by_agent
        self.name = "cross:" + "+".join(p.name for _, p in sorted(by_agent.items()))

    async def act(self, obs):
        return await self.by_agent[obs.state["agent"]].act(obs)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup", required=True)
    ap.add_argument("--tasks", nargs="+", required=True)
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--concurrency", type=int, default=8)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfgs = {m: {t: RunConfig.model_validate(yaml.safe_load(open(f"configs/api/{m}/{t}__{a.setup}.yaml")))
                for t in a.tasks} for m in a.models}
    backends = {m: make_backend(cfgs[m][a.tasks[0]].models[0].backend) for m in a.models}
    factories = {m: PolicyFactory(cfgs[m][a.tasks[0]].models[0], backends[m]) for m in a.models}
    lead = cfgs[a.models[0]]
    services, _ = make_services(lead[a.tasks[0]].judge)
    tag = "+".join(SHORT.get(m, m) for m in a.models)
    jobs = []
    for t in a.tasks:
        cfg = lead[t]
        out = Path("runs/api") / f"cross_{tag}_{t}_{a.setup}" / "cross"
        out.mkdir(parents=True, exist_ok=True)
        (out / "live").mkdir(exist_ok=True)
        done = set()
        if (out / "results.jsonl").exists():
            done = {json.loads(l)["episode_id"] for l in open(out / "results.jsonl")}
        for spec in expand(cfg, cfg.models[0]):
            if spec.condition.value != "MM" or spec.episode_id in done:
                continue
            if spec.instance.params["n_waves"] != len(a.models):
                continue  # one model per agent
            jobs.append((spec, out))
    (Path("runs/api") / f"cross_{tag}_manifest.json").write_text(json.dumps(
        {"agent_models": {str(i + 1): m for i, m in enumerate(a.models)}, "setup": a.setup, "tasks": a.tasks},
        indent=2))
    log.info("%d cross-model games: agents %s", len(jobs), {i + 1: m for i, m in enumerate(a.models)})
    sem = asyncio.Semaphore(a.concurrency)

    async def one(spec, out: Path) -> None:
        module = get_module(spec.module_id)
        by_agent = {i + 1: factories[m]._policy(module, spec, "A" if (i + 1) % 2 else "B", PolicyKind.MODEL)
                    for i, m in enumerate(a.models)}
        router = Router(by_agent)
        attempt = uuid.uuid4().hex[:12]
        async with sem:
            try:
                result = await run_episode(module, spec, {"A": router, "B": router}, services,
                                           max_steps=lead[a.tasks[0]].max_steps_per_episode, log_prompts=True,
                                           journal=out / "live" / f"{spec.episode_id}.jsonl",
                                           max_calls_per_reply=1)
            except Exception as exc:
                JsonlSink(out / "errors.jsonl").append_many([{"episode_id": spec.episode_id, "attempt": attempt,
                                                             "error": repr(exc), "traceback": traceback.format_exc()}])
                log.error("game %s failed: %r", spec.episode_id[:8], exc)
                return
        JsonlSink(out / "events.jsonl").append_many({**e.to_json(), "attempt": attempt} for e in result.events)
        JsonlSink(out / "transcripts.jsonl").append_many({**t, "attempt": attempt} for t in result.transcript)
        JsonlSink(out / "results.jsonl").append_many([{**result.record, "attempt": attempt,
                                                       "agent_models": {str(k): m for k, m in enumerate(a.models, 1)}}])
        log.info("game %s done", spec.episode_id[:8])

    try:
        await asyncio.gather(*(one(s, o) for s, o in jobs))
    finally:
        for b in backends.values():
            if b is not None:
                await b.aclose()
    log.info("all cross-model games finished")
    print("exit 0")


if __name__ == "__main__":
    asyncio.run(main())
