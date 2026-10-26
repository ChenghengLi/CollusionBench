"""Write the N4 explorer's per-game analysis as CSV files: every finished game, every solved game
(how the solver got the missing data) and the games where nobody passed anything on.

    .venv/bin/python scripts/export_n4_tables.py <explorer dir> <out dir> [max message cap]

<explorer dir> is the output of scripts/build_n4_explorer.py (it reads data/summary.json).
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any


def setting(g: dict[str, Any]) -> str:
    return f"DM cap {g['cap']}" if g["experiment"] == "dmcap" else str(g["setting"])


def ids(xs: list[int] | None) -> str:
    return " ".join(str(x) for x in xs or [])


def base(g: dict[str, Any]) -> dict[str, Any]:
    task, _, label = g["model"].partition(" · ")
    return {
        "task": task,
        "model": label,
        "experiment": g["experiment"],
        "setting": setting(g),
        "agents": g["agents"],
        "lineup": g["lineup"],
        "run": g["rep"],
    }


def finished_row(g: dict[str, Any]) -> dict[str, Any]:
    kinds = g.get("leak_kinds") or {}
    return {
        **base(g),
        "solved": g["correct"],
        "passed_on_data": bool(g.get("leak")),
        "verbatim_sends": kinds.get("verbatim", 0),
        "totals_sends": kinds.get("totals", 0),
        "paraphrase_sends": kinds.get("paraphrase", 0),
        "agents_who_passed_on": ids(g.get("leakers")),
        "agents_who_never_did": ids(g.get("kept_agents")),
        "refused": ids(g.get("refusers")),
        "refused_and_stuck_to_it": ids(g.get("refused_kept")),
        "old_flag": g["harm"] > 0 or (g.get("violation") or 0) > 0,
        "harm": round(g["harm"], 3),
        "dms": g.get("dms", 0),
        "forum_posts": g.get("posts", 0),
        "folder_writes": g.get("ws_writes", 0),
        "calls": g["calls"],
        "max_calls": g["max_calls"],
    }


def solved_row(g: dict[str, Any]) -> dict[str, Any]:
    givers = g.get("givers") or []
    return {
        **base(g),
        "solver": g.get("solver"),
        "solver_shared_its_own": g.get("solver_shared"),
        "pattern": "swap" if g.get("solver_shared") else "only received",
        "agents_who_gave": ids(givers),
        "every_other_agent_gave": len(givers) == g["agents"] - 1,
        "channels": " ".join(g.get("via") or []),
        "calls_until_solved": g.get("solved_at"),
        "calls": g["calls"],
    }


def why_unsolved(g: dict[str, Any]) -> str:
    """nothing passed on / one-sided (some agent never passed its own) / pooled, still wrong."""
    if not g.get("leak"):
        return "nothing passed on"
    return "one-sided" if g.get("kept_agents") else "pooled, still wrong"


def write(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="") as f:
        if not rows:
            return
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{path}: {len(rows)} rows")


def main(src: str, out: str, max_cap: int | None = None) -> None:
    games = json.loads((Path(src) / "data" / "summary.json").read_text())["games"]
    if max_cap is not None:  # message caps above max_cap were left out of the runs
        games = [g for g in games if not (g["experiment"] == "dmcap" and g["cap"] > max_cap)]
    done = [g for g in games if g["status"] == "done"]
    dest = Path(out)
    dest.mkdir(parents=True, exist_ok=True)
    write(dest / "finished_games.csv", [finished_row(g) for g in done])
    write(dest / "solved_games.csv", [solved_row(g) for g in done if g["correct"]])
    write(
        dest / "kept_rule_games.csv",
        [finished_row(g) for g in done if not g.get("leak")],
    )
    write(
        dest / "unsolved_games.csv",
        [{**finished_row(g), "why": why_unsolved(g)} for g in done if not g["correct"]],
    )


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else None)
