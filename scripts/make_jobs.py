#!/usr/bin/env python
"""Cluster jobs for the core block (scripts/bench.py): one job per (scenario, cell), so each job
plays one cell's worlds on its own GPU(s), plus one job for the route-works checks of all scenarios.

    python scripts/make_jobs.py --model k2-mova-bf16 --games 40 --tag v4 --out configs/v4_mova
    python scripts/make_jobs.py --model qwen3.6-35b-a3b-fp8 --games 40 --tag v4 --out configs/v4_qwenmoe

Writes <out>/<job>/tasks/<scenario>__<cell>.yaml (run id <prefix>_bench_<scenario>_core_<tag>_<cell>)
and <out>/jobs.txt, one job name per line. Submit each with CONFIG_DIR_OVERRIDE=<out>/<job>.
"""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from bench import ALL_SCENARIOS, config_for, load_models  # noqa: E402


def cell_name(params: dict) -> str:
    """A short, job-name-safe name for a cell of the core block."""
    if params.get("route_cost") == "moderate":
        return "works"
    cond = params.get("card_condition")
    if cond in ("perm", "ask", "coord"):
        return cond
    if params.get("escalation"):
        return "escal"
    if params.get("channels") == "noconv":
        return "noconv"
    return "blocked"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--model", required=True)
    ap.add_argument("--games", type=int, default=20, help="worlds per cell (the checks keep 3)")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--concurrency", type=int, default=None, help="games at once per job (default: all of them)")
    args = ap.parse_args()
    model = load_models()[args.model]
    out = ROOT / args.out
    jobs: list[str] = []
    for scenario in ALL_SCENARIOS:
        cfg = config_for(model, scenario, "core", args.games)
        short = scenario.removeprefix("card_")
        for module in cfg["modules"]:
            cell = cell_name(module["params_override"])
            one = copy.deepcopy(cfg)
            one["modules"] = [module]
            one["run_id"] = f"{cfg['run_id']}_{args.tag}_{cell}"
            one["concurrency"] = args.concurrency or module["n_instances"]
            job = "checks" if cell == "works" else f"{short}-{cell}"
            path = out / job / "tasks" / f"{scenario}__{cell}.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {model['title']} · {scenario} · core block, cell {cell} (scripts/make_jobs.py)\n"
                            + yaml.safe_dump(one, sort_keys=False))
            if job not in jobs:
                jobs.append(job)
    (out / "jobs.txt").write_text("".join(f"{j}\n" for j in jobs))
    print(f"{out.relative_to(ROOT)}: {len(jobs)} jobs")


if __name__ == "__main__":
    main()
