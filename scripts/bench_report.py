#!/usr/bin/env python
"""The one table per model for benchmark v1 (docs/redesign/14_unified_design.md section 7).

    python scripts/bench_report.py runs/api/<run_prefix>_bench_*_<block>
    python scripts/bench_report.py --games runs/api/...      # one line per game as well

Every number is a count of games out of n; joint and solo breaches are always side by side, and
each count carries an exact (Clopper-Pearson) 95% interval. Cells: scenario x route cost x card
condition (x aim, x ladder step). Scripted calibration games (HH, OO) are listed apart.
"""

from __future__ import annotations

import argparse
import glob
import json
import statistics
from collections import defaultdict
from pathlib import Path

from scipy.stats import beta


def ci(k: int, n: int) -> str:
    if n == 0:
        return ""
    lo = 0.0 if k == 0 else beta.ppf(0.025, k, n - k + 1)
    hi = 1.0 if k == n else beta.ppf(0.975, k + 1, n - k)
    return f"{lo:.0%}-{hi:.0%}"


def cell_of(r: dict) -> tuple:
    p = r["params"]
    cond = p.get("card_condition", "mm")
    if r["condition"] in ("HH", "OO"):
        cond = r["condition"].lower()
    extra = []
    if p.get("aim", "team") != "team":
        extra.append(f"aim={p['aim']}")
    if p.get("game") == "card_survey":
        extra.append(f"step={p.get('ladder_step', 5)}")
    return (p["game"].removeprefix("card_"), p.get("route_cost", "moderate"), cond, " ".join(extra))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--games", action="store_true")
    args = ap.parse_args()
    rows: dict[tuple, list[dict]] = defaultdict(list)
    for run in args.runs:
        for f in glob.glob(str(Path(run) / "*" / "results.jsonl")):
            # results_rescored.jsonl (scripts/bench_rescore.py): the same games, today's detector;
            # games finished after the last rescore keep their live scores
            rescored_path = Path(f).with_name("results_rescored.jsonl")
            rescored = ({json.loads(x)["episode_id"]: x for x in open(rescored_path)}
                        if rescored_path.exists() else {})
            for line in open(f):
                line = rescored.get(json.loads(line)["episode_id"], line)
                r = json.loads(line)
                if r.get("error") or "card_joint" not in (r.get("secondary") or {}):
                    continue
                rows[cell_of(r)].append(r)
    cols = ["games", "joint", "solo", "contact", "asked", "supplied", "used", "solved",
            "policy found", "calls/agent", "report false"]
    print(" | ".join(["scenario", "level", "condition", "", *cols]))
    for key in sorted(rows, key=lambda k: (k[0], k[2] in ("hh", "oo"), k[2], k[1], k[3])):
        rs = rows[key]
        n = len(rs)

        def count(name: str) -> str:
            k = sum(r["secondary"].get(name, 0) > 0 for r in rs)
            return f"{k} ({ci(k, n)})"

        calls = statistics.median(r["secondary"]["card_calls_mean"] for r in rs)
        found = statistics.mean(r["secondary"]["card_policy_found_share"] for r in rs)
        # survey steps 1 to 4 keep the rule in the prompt: there is no policy file to find
        found_cell = "n/a" if "step=" in key[3] and "step=5" not in key[3] else f"{found:.0%}"
        print(" | ".join([*key, str(n), count("card_joint"), count("card_solo"),
                          count("card_discovery"), count("card_asked"), count("card_supplied"),
                          count("card_used"), count("card_solved"), found_cell, f"{calls:.0f}",
                          count("rep_false")]))
        if args.games:
            for r in rs:
                s = r["secondary"]
                print(f"    {r['episode_id'][:8]} class C{int(s['card_class'])} joint={s['card_joint']:.0f} "
                      f"req>sup={s['card_joint_request_supply']:.0f} sup>use={s['card_joint_supply_use']:.0f} "
                      f"leaks={s['card_leak_items']:.0f} solved={s['card_solved']:.0f} "
                      f"tier={s.get('card_tier', 0):.2f} calls={s['card_calls_mean']:.0f} "
                      f"route={s['card_route_calls']:.0f} rep_false={s.get('rep_false', 0):.0f} "
                      f"log_edits={s.get('log_edit_agents', 0):.0f}"
                      + (f" posted={s['f_posted']:.0f} flawed_posted={s['f_flawed_posted']:.0f} "
                         f"clean_rejected={s.get('f_clean_rejected', 0):.0f} "
                         f"unchecked={s['f_unchecked_approvals']:.0f}" if "f_posted" in s else ""))


if __name__ == "__main__":
    main()
