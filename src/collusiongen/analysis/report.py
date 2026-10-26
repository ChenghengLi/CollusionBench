"""Write per-model profiles and a cross-model summary table for a run directory."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from collusiongen.analysis.profile import (
    CheckpointProfile,
    ModuleProfile,
    Thresholds,
    checkpoint_profile,
    load_results,
)


def _fmt(iv: dict[str, float] | None) -> str:
    if iv is None:
        return "–"
    return f"{iv['est']:+.2f} [{iv['lo']:+.2f}, {iv['hi']:+.2f}]"


def _pct(iv: dict[str, float] | None) -> str:
    if iv is None:
        return "–"
    return f"{iv['est']:.0%} [{iv['lo']:.0%}, {iv['hi']:.0%}]"


def _num(x: float | None) -> str:
    return "–" if x is None else f"{x:.2f}"


def _row(p: ModuleProfile) -> str:
    module = f"{p.module}[{p.variant}]" if p.variant else p.module
    if p.probe is not None:
        delta = f"self-pref {p.probe['self_preference']:+.2f}"
        return (
            f"| {p.model} | {module} | – | – | – | {delta} | – | – | – | – | – | "
            f"{_num(p.task_success)} | {_num(p.aware_rate)} | – | probe | probe |"
        )
    flag = {True: "**yes**", False: "no", None: "–"}[p.collusive]
    rate_flag = {True: "**yes**", False: "no", None: "–"}[p.collusive_by_rate]
    return (
        f"| {p.model} | {module} | {_pct(p.collusion_rate)} | {_pct(p.baseline_rate)} | "
        f"{_pct(p.excess_rate)} | {_fmt(p.delta)} | {_fmt(p.gain)} | {_fmt(p.joint)} | "
        f"{_fmt(p.solo)} | "
        f"{_fmt(p.ceiling)} | {_fmt(p.propensity)} | {_num(p.task_success)} | "
        f"{_num(p.aware_rate)} | {_num(p.paraphrase_icc)} | {flag} | {rate_flag} |"
    )


HEADER = (
    "| model | module | collusive games | chance level | excess rate | Δ_m | gain | Joint | solo | "
    "ceiling | P_m | honest success | aware | ICC(para) | collusive (mean) | collusive (rate) |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"
)


def group_size_section(profiles: list[CheckpointProfile]) -> list[str]:
    """Dose-response over the number of agents, for every module run at several sizes."""
    groups: dict[tuple[str, str, str], list[ModuleProfile]] = defaultdict(list)
    for prof in profiles:
        for p in prof.modules.values():
            if p.n_agents is None or p.probe is not None:
                continue
            other = ",".join(v for v in p.variant.split(",") if not v.startswith("n"))
            groups[(p.model, p.module, other)].append(p)
    lines: list[str] = []
    for (model, module, other), ps in sorted(groups.items()):
        if len({p.n_agents for p in ps}) < 2:
            continue
        if not lines:
            lines = [
                "",
                "## By number of agents",
                "",
                "| model | module | agents | collusive games | excess rate | Δ_m | gain | Joint "
                "| collusive (mean) | collusive (rate) |",
                "|---|---|---|---|---|---|---|---|---|---|",
            ]
        name = f"{module}[{other}]" if other else module
        for p in sorted(ps, key=lambda q: q.n_agents or 0):
            flag = {True: "**yes**", False: "no", None: "–"}[p.collusive]
            rate_flag = {True: "**yes**", False: "no", None: "–"}[p.collusive_by_rate]
            lines.append(
                f"| {model} | {name} | {p.n_agents} | {_pct(p.collusion_rate)} | "
                f"{_pct(p.excess_rate)} | {_fmt(p.delta)} | {_fmt(p.gain)} | {_fmt(p.joint)} | "
                f"{flag} | {rate_flag} |"
            )
    return lines


def analyse_run(run_dir: Path, th: Thresholds = Thresholds()) -> list[CheckpointProfile]:
    profiles = []
    for results in sorted(run_dir.glob("*/results.jsonl")):
        rows = load_results(results)
        if not rows:
            continue
        prof = checkpoint_profile(rows, th)
        (results.parent / "profile.json").write_text(
            json.dumps(prof.to_dict(), indent=2, default=str)
        )
        profiles.append(prof)
    lines = [f"# Collusion profiles: {run_dir.name}", "", HEADER]
    for prof in profiles:
        lines += [_row(p) for p in prof.modules.values()]
    lines += group_size_section(profiles)
    lines += [
        "",
        "Composite (unweighted mean of core Δ_m at default group size; N1 beside it):",
        "",
    ]
    lines += [f"- {p.model}: {_num(p.composite_delta)}" for p in profiles]
    notes = [
        f"- {p.model}/{m}: {n}" for p in profiles for m, mp in p.modules.items() for n in mp.notes
    ]
    if notes:
        lines += ["", "Notes:", "", *notes]
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n")
    return profiles
