#!/usr/bin/env python3
"""Keep a campaign of make_jobs.py jobs running on RCP within the project's pod limit.

One pass: list the project's RunAI jobs; every job of the campaign that is not live (missing,
Deleted, Error, Failed or Succeeded) and has unfinished games is (re)submitted, in campaign order,
while fewer than --cap campaign jobs are live. The runner resumes from the finished games and
retries failed ones. Why (2026-11-18): the project allows 500 pods, so queued jobs past that never
start, and a preempted preemptible job ends up Deleted instead of queued again.

    python3 serving/rcp/keep_jobs.py --cap 150 v6_mova:movabf16 v6_k2_37b:3.7b ...   [--dry]

Order: cells in --cells order (blocked first), and within a cell the folders in argument order.
Run from the repository root on the jump host, every few minutes while the campaign runs.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import subprocess
from pathlib import Path

import yaml

LIVE = {"Pending", "Running", "Unknown", "Initializing", "ContainerCreating", "Terminating", "Suspended"}
PROJECT = os.environ.get("PROJECT", "dlab-lichen")


def runai(*args: str) -> str:
    env = {**os.environ, "SUPPRESS_DEPRECATION_MESSAGE": "true"}
    return subprocess.run(["runai", *args], capture_output=True, text=True, env=env).stdout


def prefix_of(model: str) -> str:
    out = subprocess.run(["bash", "serving/rcp/submit.sh", "n4t"], capture_output=True, text=True,
                         env={**os.environ, "MODEL": model, "DRY": "1"}).stdout
    m = re.search(r"--name (\S+)-n4t", out)
    if not m:
        raise SystemExit(f"no RunAI name prefix for MODEL={model}")
    return m.group(1)


def games(job_dir: Path) -> tuple[int, int]:
    """(expected, finished) games of a job folder."""
    want = have = 0
    for f in job_dir.glob("tasks/*.yaml"):
        cfg = yaml.safe_load(f.read_text())
        want += sum(m["n_instances"] for m in cfg["modules"])
        for r in glob.glob(f"runs/{cfg['run_id']}/*/results.jsonl"):
            with open(r) as fh:
                have += sum(1 for _ in fh)
    return want, have


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pairs", nargs="+", help="<configs folder>:<submit.sh MODEL>")
    ap.add_argument("--cap", type=int, default=150, help="most live campaign jobs at once")
    ap.add_argument("--cells", default="blocked,perm,escal,noconv,coord,ask,checks")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    status: dict[str, str] = {}
    for line in runai("list", "jobs", "-p", PROJECT).splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            status[parts[0]] = parts[1]
    jobs = []  # (name, folder, job, model)
    for cell in a.cells.split(","):
        for pair in a.pairs:
            folder, model = pair.split(":")
            prefix = prefix_of(model)
            for job in Path(f"configs/{folder}/jobs.txt").read_text().split():
                if job == cell or job.endswith(f"-{cell}"):
                    jobs.append((f"{prefix}-n4t-{job}", folder, job, model))
    live = sum(status.get(n) in LIVE for n, *_ in jobs)
    done = submitted = 0
    for name, folder, job, model in jobs:
        if status.get(name) in LIVE:
            continue
        want, have = games(Path(f"configs/{folder}/{job}"))
        if have >= want:
            done += 1
            continue
        if live >= a.cap:
            continue
        print(f"submit {name} ({status.get(name, 'missing')}, {have}/{want} games)", flush=True)
        if a.dry:
            live += 1
            continue
        if name in status:
            runai("delete", "job", name, "-p", PROJECT)
        env = {**os.environ, "PREEMPTIBLE": "1", "ROOT_OVERRIDE": os.getcwd(),
               "JOB_SCRIPT": f"{os.getcwd()}/serving/rcp/job.sh", "CONFIG_DIR_OVERRIDE": f"configs/{folder}/{job}",
               "RUN_TAG_OVERRIDE": folder.replace("_", ""), "MODEL": model,
               "POOL": os.environ.get("POOL", "h100"), "JOB_TAG": job}
        r = subprocess.run(["bash", "serving/rcp/submit.sh", "n4t"], capture_output=True, text=True, env=env)
        if r.returncode:
            print(f"  FAILED {name}: {r.stderr.strip()[-200:]}", flush=True)
            continue
        live += 1
        submitted += 1
    print(f"campaign: {len(jobs)} jobs, {done} done, {live} live, {submitted} submitted this pass", flush=True)


if __name__ == "__main__":
    main()
