"""Command-line entry point: `collusiongen <command>`."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from collusiongen.core.log import EventLog
from collusiongen.core.registry import all_modules, get_module
from collusiongen.core.types import Split, Variant


def cmd_modules(_: argparse.Namespace) -> int:
    print(f"{'id':<12} {'channel':<8} {'agents':<8} {'core':<5} {'composite':<9} {'swap':<5} title")
    for m in all_modules():
        lo, hi = m.agent_range
        agents = f"{lo}-{hi}" if hi > lo else str(lo)
        print(
            f"{m.id:<12} {m.channel_class:<8} {agents:<8} {m.core!s:<5} {m.in_composite!s:<9} "
            f"{m.supports_partner_swap!s:<5} {m.title}"
        )
    return 0


def cmd_sample(args: argparse.Namespace) -> int:
    """Print a generated instance and the first observation, for prompt review."""
    from collusiongen.core.env import Services

    module = get_module(args.module)
    overrides = {"n_agents": args.n_agents} if args.n_agents else None
    inst = module.sample_instance(args.seed, Split(args.split), args.index, overrides)
    env = module.make_env(inst, Variant(paraphrase=args.paraphrase), EventLog("sample"), Services())
    print(
        json.dumps(
            {"instance_id": inst.instance_id, "skin": inst.skin.vocab, "params": inst.params},
            indent=2,
            default=str,
        )
    )
    seat = env.next_seat()
    if seat is not None:
        obs = env.observe(seat)
        print(f"\n--- system ({seat}) ---\n{obs.system}\n\n--- prompt ---\n{obs.prompt}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from collusiongen.runner.config import RunConfig
    from collusiongen.runner.experiment import run_experiment

    config = RunConfig.load(args.config)
    if args.output_dir:
        config = config.model_copy(update={"output_dir": Path(args.output_dir)})
    summary = asyncio.run(run_experiment(config))
    print(json.dumps(summary, indent=2))
    failed = sum(c["failed"] for c in summary.values())
    if failed:
        print(f"{failed} episodes failed; see errors.jsonl. Re-run to retry them.")
    return 1 if failed else 0


def cmd_analyze(args: argparse.Namespace) -> int:
    from collusiongen.analysis.profile import Thresholds
    from collusiongen.analysis.report import analyse_run

    run_dir = Path(args.run_dir)
    analyse_run(run_dir, Thresholds(n_boot=args.n_boot))
    print((run_dir / "summary.md").read_text())
    return 0


def cmd_sweep(args: argparse.Namespace) -> int:
    from collusiongen.runner.sweep import SweepConfig, dry_run, run_sweep

    sweep = SweepConfig.load(args.config)
    if args.dry_run:
        print(dry_run(sweep))
        return 0
    status = asyncio.run(run_sweep(sweep, only=args.only))
    print(json.dumps(status, indent=2))
    bad = [
        t for t, e in status["tags"].items() if not str(e.get("state", "")).startswith("complete")
    ]
    return 1 if bad else 0


def cmd_preflight(args: argparse.Namespace) -> int:
    from collusiongen.runner import preflight
    from collusiongen.runner.config import RunConfig

    checks: list[preflight.Check] = []
    modules = [m.id for m in all_modules()]
    if args.config:
        config = RunConfig.load(args.config)
        modules = [m.id for m in config.modules]
        checks += preflight.check_revisions(config)
        if args.live:
            checks += asyncio.run(preflight.check_served_models(config))
            checks += preflight.check_served_manifests(config, Path(args.logs_dir))
    checks.append(preflight.scan_secrets([Path(p) for p in args.scan]))
    if not args.skip_trivial:
        checks += asyncio.run(preflight.check_trivial_agents(modules))
    for c in checks:
        print(c)
    failed = [c for c in checks if not c.ok]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed")
    return 1 if failed else 0


def cmd_progress(args: argparse.Namespace) -> int:
    from collusiongen.analysis.live import progress_report

    print(progress_report(Path(args.run_dir)))
    return 0


def cmd_rejudge(args: argparse.Namespace) -> int:
    from collusiongen.judges.rejudge import rejudge_run
    from collusiongen.runner.config import RunConfig

    judge = RunConfig.load(args.judge_from).judge
    report = asyncio.run(rejudge_run(Path(args.run_dir), judge, args.concurrency))
    print(report)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="collusiongen", description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("modules", help="list registered modules").set_defaults(fn=cmd_modules)

    p = sub.add_parser("sample", help="show a generated instance and its first prompt")
    p.add_argument("module")
    p.add_argument("--split", default="train", choices=[s.value for s in Split])
    p.add_argument("--index", type=int, default=0)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--paraphrase", type=int, default=0)
    p.add_argument("--n-agents", type=int, help="group size (firms, reviewers or waves)")
    p.set_defaults(fn=cmd_sample)

    p = sub.add_parser("run", help="run a config (resumable)")
    p.add_argument("config")
    p.add_argument("--output-dir")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("sweep", help="run one game set on every checkpoint, in training order")
    p.add_argument("config")
    p.add_argument("--dry-run", action="store_true", help="print the plan; touch nothing")
    p.add_argument("--only", nargs="*", help="restrict to these tags")
    p.set_defaults(fn=cmd_sweep)

    p = sub.add_parser("analyze", help="profiles and summary table for a run directory")
    p.add_argument("run_dir")
    p.add_argument("--n-boot", type=int, default=2000)
    p.set_defaults(fn=cmd_analyze)

    p = sub.add_parser("progress", help="live progress of a run: games, rounds, damage, tokens")
    p.add_argument("run_dir")
    p.set_defaults(fn=cmd_progress)

    p = sub.add_parser("rejudge", help="re-judge every N2 board message with the LLM judge alone")
    p.add_argument("run_dir")
    p.add_argument("--judge-from", required=True, help="config whose `judge` backend to use")
    p.add_argument("--concurrency", type=int, default=50)
    p.set_defaults(fn=cmd_rejudge)

    p = sub.add_parser("preflight", help="checks to run before every sweep")
    p.add_argument("--config")
    p.add_argument("--live", action="store_true", help="also query the model servers")
    p.add_argument(
        "--scan", nargs="*", default=["configs", "runs", "logs"], help="paths to scan for secrets"
    )
    p.add_argument("--skip-trivial", action="store_true")
    p.add_argument("--logs-dir", default="logs", help="where serve scripts record revisions")
    p.set_defaults(fn=cmd_preflight)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    return int(args.fn(args))


if __name__ == "__main__":
    sys.exit(main())
