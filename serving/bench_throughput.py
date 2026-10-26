"""Throughput of the local server at several concurrency levels, on real game prompts.

    .venv/bin/python serving/bench_throughput.py [served-name] [base_url] [seconds-per-level]

Prints requests/s and prompt/generated tokens/s per level, so the runner's `concurrency` can be
set where throughput stops improving. Results are also written to logs/bench_throughput.json.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

from collusiongen.core.env import Services
from collusiongen.core.log import EventLog
from collusiongen.core.registry import get_module
from collusiongen.core.types import Split, Variant


def sample_prompts() -> list[list[dict[str, str]]]:
    """First-turn prompts of several modules and instances (a realistic length mix)."""
    out = []
    for mid in ("a1_pricing", "n2_market", "a2_verify", "n4_relay"):
        m = get_module(mid)
        for i in range(6):
            inst = m.sample_instance(99, Split.TRAIN, i)
            env = m.make_env(inst, Variant(paraphrase=i % 5), EventLog("b"), Services())
            obs = env.observe(env.next_seat())
            out.append([{"role": "system", "content": obs.system},
                        {"role": "user", "content": obs.prompt}])
    return out


async def level(client: httpx.AsyncClient, served: str, prompts: list, conc: int,
                seconds: float) -> dict[str, float]:
    stats = {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0}
    stop = time.time() + seconds

    async def worker(k: int) -> None:
        i = k
        while time.time() < stop:
            body = {"model": served, "messages": prompts[i % len(prompts)], "temperature": 1.0,
                    "top_p": 0.95, "max_tokens": 1024, "seed": i,
                    "chat_template_kwargs": {"reasoning_effort": "low"}}
            r = (await client.post("/v1/chat/completions", json=body)).json()
            stats["requests"] += 1
            stats["prompt_tokens"] += r["usage"]["prompt_tokens"]
            stats["completion_tokens"] += r["usage"]["completion_tokens"]
            i += conc

    t0 = time.time()
    await asyncio.gather(*(worker(k) for k in range(conc)))
    dt = time.time() - t0
    return {"concurrency": conc, "seconds": round(dt, 1),
            "req_per_s": round(stats["requests"] / dt, 2),
            "prompt_tok_per_s": round(stats["prompt_tokens"] / dt),
            "gen_tok_per_s": round(stats["completion_tokens"] / dt),
            "mean_gen_tokens": round(stats["completion_tokens"] / max(1, stats["requests"]))}


async def main() -> None:
    served = sys.argv[1] if len(sys.argv) > 1 else "k2h-3.7b@final"
    base = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8000"
    seconds = float(sys.argv[3]) if len(sys.argv) > 3 else 45
    prompts = sample_prompts()
    results = []
    async with httpx.AsyncClient(base_url=base, timeout=900) as client:
        for conc in (8, 16, 32, 48, 64):
            res = await level(client, served, prompts, conc, seconds)
            results.append(res)
            print(json.dumps(res), flush=True)
    Path("logs").mkdir(exist_ok=True)
    Path("logs/bench_throughput.json").write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
