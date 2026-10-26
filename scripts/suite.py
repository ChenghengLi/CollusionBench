"""Evaluation suites (configs/suites/<id>.yaml): arms of tasks x setups x models x episode offsets
on top of the existing task inventory, setups and model profiles (scripts/experiments.py).

    .venv/bin/python scripts/suite.py plan shared_goal_v1 [--arms replicate breadth]
    .venv/bin/python scripts/suite.py make shared_goal_v1 [--arms ...]
    .venv/bin/python scripts/suite.py launch shared_goal_v1 --arms replicate [--yes]
    .venv/bin/python scripts/suite.py status shared_goal_v1

plan    games per arm, what is already finished, and a cost estimate from finished games
make    writes configs/api/<model>/<task>__<setup>[_rK].yaml (offset K > 0 gets the suffix _rK)
launch  prints the logs/launch_api.sh commands; with --yes it starts them (the key is read from
        ~/.config/collusiongen/openrouter_key by launch_api.sh, never written anywhere)
status  finished model games per arm, cell by cell

Offset 0 is the profile's own run (no suffix), so the runs already done are counted, not redone.
"""

from __future__ import annotations

import argparse
import glob
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from experiments import MODEL_GAMES, MODELS, ROOT, SETUPS, config_for, load_tasks, load_yaml_dir  # noqa: E402

from collusiongen.runner.config import RunConfig  # noqa: E402
from collusiongen.runner.plan import expand  # noqa: E402

SUITES = ROOT / "configs" / "suites"


def cells(suite: dict, arms: list[str] | None):
    """(arm, model, task, setup, offset) for every cell of the chosen arms."""
    for name, arm in suite["arms"].items():
        if arms and name not in arms:
            continue
        for m in arm["models"]:
            for t in arm["tasks"]:
                for s in arm["setups"]:
                    for k in arm["offsets"]:
                        yield name, m, t, s, k


def rep_of(k: int) -> dict:
    return {"suffix": f"_r{k}" if k else "", "episode_offset": k, "episodes": 1}


def build(model: dict, setup: dict, task, k: int) -> tuple[dict, Path]:
    rep = rep_of(k)
    cfg = config_for(model, rep, setup, [task])
    own = model.get("setup_run_override", {}).get(setup["id"], {})
    if "concurrency" not in own:
        raise SystemExit(f"{model['id']} has no setup_run_override for {setup['id']}: add one first")
    cfg["concurrency"] = own["concurrency"]
    path = ROOT / "configs" / "api" / model["id"] / f"{task.id}__{setup['id']}{rep['suffix']}.yaml"
    return cfg, path


def results(model: dict, run_id: str) -> list[dict]:
    path = ROOT / model["local_runs"] / run_id / model["model"]["name"] / "results.jsonl"
    return [json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []


def game_cost(model: dict, run_id: str) -> list[float]:
    out = []
    for f in glob.glob(str(ROOT / model["local_runs"] / run_id / "*" / "live" / "*.jsonl")):
        lines = Path(f).read_text().splitlines()
        if lines and '"kind": "M"' in lines[0]:
            out.append(sum(float((json.loads(l).get("usage") or {}).get("cost") or 0) for l in lines))
    return out


def load(suite_id: str):
    suite = yaml.safe_load((SUITES / f"{suite_id}.yaml").read_text())
    tasks = {t.id: t for t in load_tasks()}
    return suite, tasks, load_yaml_dir(SETUPS), load_yaml_dir(MODELS)


def survey(args) -> list[dict]:
    suite, tasks, setups, models = load(args.suite)
    rows = []
    for arm, mid, tid, sid, k in cells(suite, args.arms):
        model, setup, task = models[mid], setups[sid], tasks[tid]
        if not task.plays(setup):
            raise SystemExit(f"task {tid} does not list setup {sid}")
        cfg, path = build(model, setup, task, k)
        run = RunConfig.model_validate(cfg)
        planned = sum(1 for s in expand(run, run.models[0]) if s.condition.value in MODEL_GAMES)
        done = len([r for r in results(model, cfg["run_id"]) if r.get("condition") in MODEL_GAMES])
        rows.append({"arm": arm, "model": mid, "task": tid, "setup": sid, "offset": k, "cfg": cfg,
                     "path": path, "planned": planned, "done": min(done, planned),
                     "costs": game_cost(model, cfg["run_id"])})
    return rows


def cmd_plan(args) -> None:
    rows = survey(args)
    # cost per game from every finished shared-goal game of the model (clean games first)
    _, _, _, models = load(args.suite)
    per_model: dict[str, list[float]] = {}
    for mid in {r["model"] for r in rows}:
        m = models[mid]
        for pattern in ("_n4_shared_*clean*", "_n4_shared_*"):
            runs = glob.glob(str(ROOT / m["local_runs"] / f"{m['run_prefix']}{pattern}"))
            per_model[mid] = [c for run in runs for c in game_cost(m, Path(run).name)]
            if per_model[mid]:
                break
    by_arm: Counter = Counter()
    todo: Counter = Counter()
    est = 0.0
    for r in rows:
        by_arm[r["arm"]] += r["planned"]
        left = r["planned"] - r["done"]
        todo[r["arm"]] += left
        c = per_model.get(r["model"]) or []
        est += left * (sum(c) / len(c) if c else float("nan"))
    for arm in by_arm:
        runs = len({(r["model"], r["task"], r["setup"], r["offset"]) for r in rows if r["arm"] == arm})
        print(f"{arm:12s} {runs:3d} runs  {by_arm[arm]:4d} games  {todo[arm]:4d} still to play")
    for mid, c in per_model.items():
        print(f"  {mid}: ${sum(c) / len(c):.3f} per game from {len(c)} finished games" if c else f"  {mid}: no finished game")
    print(f"total        {sum(by_arm.values()):4d} games, {sum(todo.values())} to play; "
          f"est. cost ${est:.2f} (nan: no finished game of that model to estimate from)")


def cmd_make(args) -> None:
    for r in survey(args):
        path = r["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        head = (f"# Suite {args.suite} · arm {r['arm']} · {r['task']} · {r['setup']} · offset {r['offset']}\n"
                "# Written by scripts/suite.py make; do not edit this file.\n")
        path.write_text(head + yaml.safe_dump(r["cfg"], sort_keys=False))
        print(f"{path.relative_to(ROOT)}  {r['cfg']['run_id']}  {r['planned']} model games")


def cmd_launch(args) -> None:
    if not args.arms:
        raise SystemExit("name the arms to launch (--arms ...)")
    cmds = []
    for r in survey(args):
        if r["done"] >= r["planned"]:
            continue
        if not r["path"].exists():
            raise SystemExit(f"{r['path'].relative_to(ROOT)} missing: run make first")
        setup_arg = r["setup"] + (f"_r{r['offset']}" if r["offset"] else "")
        cmds.append(["bash", "logs/launch_api.sh", r["model"], r["task"], setup_arg])
    for c in cmds:
        print(" ".join(c))
    if not args.yes:
        print(f"{len(cmds)} runs; nothing started (add --yes to start them)")
        return
    for c in cmds:
        subprocess.Popen(["nohup", "caffeinate", "-i", *c], cwd=ROOT, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    print(f"started {len(cmds)} runs")


def cmd_status(args) -> None:
    for r in survey(args):
        print(f"{r['arm']:11s} {r['model']:28s} {r['task']:34s} {r['setup']:22s} r{r['offset']}  "
              f"{r['done']}/{r['planned']}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("cmd", choices=["plan", "make", "launch", "status"])
    ap.add_argument("suite")
    ap.add_argument("--arms", nargs="*")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()
    {"plan": cmd_plan, "make": cmd_make, "launch": cmd_launch, "status": cmd_status}[args.cmd](args)


if __name__ == "__main__":
    main()
