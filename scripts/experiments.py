"""N4 experiments from three separate parts: the task inventory, the experiment setups and the
model profiles. Add a task (a file in src/collusiongen/modules/n4_relay/tasks/) and `make`
plays it in every setup, for every model, with the same runs as every other task.

    tasks/<id>.yaml           what is played: the survey, a brief problem, ...
    configs/setups/<id>.yaml  how: the settings of one experiment (channels, message caps, ...)
    configs/models/<id>.yaml  who: the model block, where it runs, and its runs (episode offsets)

    .venv/bin/python scripts/experiments.py tasks             # the inventory
    .venv/bin/python scripts/experiments.py make              # write every run config
    .venv/bin/python scripts/experiments.py make --models k2-7b --tasks depot_v1
    .venv/bin/python scripts/experiments.py status            # games planned and finished
    .venv/bin/python scripts/experiments.py status --write    # also tasks/STATUS.md

Each task gets its own run per model, setup and repetition: <run_prefix>_n4_<task>_<setup><suffix>.
A run refuses to resume under a changed config, so one run per task means a task can be run
alone, and adding a task never touches the runs of the others. RCP configs go to
configs/<config_dir><suffix>/tasks/<task>__<setup>.yaml and job.sh n4t runs every config there
at once; API configs go to configs/api/<model id>/<task>__<setup><suffix>.yaml. A profile's
concurrency is per config with two configs side by side; with more configs in one job the same
total is shared between them.
"""

from __future__ import annotations

import argparse
import copy
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from collusiongen.modules.n4_relay import briefs
from collusiongen.runner.config import RunConfig
from collusiongen.runner.plan import expand

ROOT = Path(__file__).resolve().parent.parent
SETUPS = ROOT / "configs" / "setups"
MODELS = ROOT / "configs" / "models"
STATUS_MD = briefs.TASK_DIR / "STATUS.md"
MODEL_GAMES = ("MM", "INST")  # the conditions a model plays (HH and OO are scripted references)


@dataclass(frozen=True)
class Task:
    id: str
    game: str
    title: str
    params: dict[str, Any]  # what goes into params_override to play this task
    legacy: dict[str, str]  # setup id -> run name, for tasks run before the inventory
    setups: tuple[str, ...] = ()  # only these setups play the task (empty: every setup)

    def plays(self, setup: dict[str, Any]) -> bool:
        """A task names the setups it plays (`setups`), a setup the games it takes (`games`);
        either list left out means no restriction."""
        if self.setups and setup["id"] not in self.setups:
            return False
        return not setup.get("games") or self.game in setup["games"]


def load_tasks() -> list[Task]:
    out = []
    for tid in briefs.task_ids():
        raw = briefs.spec(tid)
        game = raw.get("game", "brief")
        params: dict[str, Any] = {"task": tid}
        if game == "brief":
            params.update(game=game, chunk_chars=int(raw.get("chunk_chars", briefs.DEFAULT_CHUNK)))
        elif game != "survey":
            params.update(game=game)
        out.append(
            Task(
                tid,
                game,
                str(raw.get("title", tid)),
                params,
                raw.get("legacy_runs", {}),
                tuple(raw.get("setups", ())),
            )
        )
    # The survey first (the original game), then the other games, each by id.
    return sorted(out, key=lambda t: (t.game != "survey", t.game, t.id))


def load_yaml_dir(folder: Path) -> dict[str, dict[str, Any]]:
    return {p.stem: yaml.safe_load(p.read_text()) for p in sorted(folder.glob("*.yaml"))}


def is_legacy(model: dict[str, Any], task: Task) -> bool:
    """This model played this task before the inventory, under the task's own run names."""
    return task.id in model.get("legacy_tasks", [])


def run_name(setup: dict[str, Any], task: Task, model: dict[str, Any] | None = None) -> str:
    """The middle of a run id: a legacy name for a task the model ran before the inventory,
    else n4_<task>_<setup>."""
    # legacy names exist only for the setups those runs used; newer setups use the standard name
    if model is not None and is_legacy(model, task) and setup["id"] in task.legacy:
        return task.legacy[setup["id"]]
    return f"n4_{task.id}_{setup['id']}"


def config_for(
    model: dict[str, Any], rep: dict[str, Any], setup: dict[str, Any], tasks: list[Task]
) -> dict[str, Any]:
    modules = []
    for task in tasks:
        for s in setup["settings"]:
            m = copy.deepcopy(setup["module"])
            m.update(model.get("module_override", {}))  # e.g. instructed: false for one model
            # the same, for one setup only: {setup id: {key: value}}
            m.update(model.get("setup_module_override", {}).get(setup["id"], {}))
            m["params_override"] = {**setup["shared"], **s["params"], **task.params}
            # a setup may fix its own number of runs per game (e.g. exam_easy: 3)
            m["episodes_per_instance"] = setup.get("episodes", rep["episodes"])
            if rep["episode_offset"]:
                m["episode_offset"] = rep["episode_offset"]
            modules.append(m)
    run = run_name(setup, tasks[0], model) if len(tasks) == 1 else f"n4_tasks_{setup['id']}"
    return {
        "run_id": f"{model['run_prefix']}_{run}{rep['suffix']}",
        **model["run"],
        # run settings for one setup only: {setup id: {key: value}}, e.g. its own skip_params
        **model.get("setup_run_override", {}).get(setup["id"], {}),
        "models": [model["model"]],
        "modules": modules,
    }


def config_path(
    model: dict[str, Any], rep: dict[str, Any], setup: dict[str, Any], task: Task
) -> Path:
    name = f"{task.id}__{setup['id']}"
    if model["config_dir"] == "api":
        return ROOT / "configs" / "api" / model["id"] / f"{name}{rep['suffix']}.yaml"
    return ROOT / "configs" / f"{model['config_dir']}{rep['suffix']}" / "tasks" / f"{name}.yaml"


def cmd_tasks(_: argparse.Namespace) -> None:
    for t in load_tasks():
        extra = f" (ran before the inventory: {', '.join(t.legacy.values())})" if t.legacy else ""
        print(f"{t.id:14s} {t.game:7s} {t.title}{extra}")


def cmd_make(args: argparse.Namespace) -> None:
    every = [t for t in load_tasks() if not args.tasks or t.id in args.tasks]
    setups, models = load_yaml_dir(SETUPS), load_yaml_dir(MODELS)
    for mid, model in models.items():
        if args.models and mid not in args.models:
            continue
        # Tasks this model already played under their own run names are not remade.
        tasks = [t for t in every if not is_legacy(model, t)]
        if not tasks:
            continue
        # The profile's concurrency is per config with two configs side by side (as the survey
        # ran); with more configs in one job the same total is shared between them.
        per_config = max(4, 2 * model["run"]["concurrency"] // (len(tasks) * len(setups)))
        for rep in model["reps"]:
            written: list[Path] = []
            for sid, setup in setups.items():
                if args.setups and sid not in args.setups:
                    continue
                for task in tasks:
                    if not task.plays(setup):
                        continue
                    cfg = config_for(model, rep, setup, [task])
                    own = model.get("setup_run_override", {}).get(sid, {})
                    cfg["concurrency"] = own.get("concurrency", per_config)
                    run = RunConfig.model_validate(cfg)  # fail here, not on the cluster
                    path = config_path(model, rep, setup, task)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    head = (
                        f"# {model['title']} · {task.id} · {setup['title']} · runs "
                        f"{rep['episode_offset'] + 1}-{rep['episode_offset'] + rep['episodes']}\n"
                        "# Written by scripts/experiments.py make from configs/models, "
                        "configs/setups and the task inventory.\n# Edit those and run make "
                        "again; do not edit this file.\n"
                    )
                    path.write_text(head + yaml.safe_dump(cfg, sort_keys=False))
                    written.append(path)
                    games = sum(
                        1 for s in expand(run, run.models[0]) if s.condition.value in MODEL_GAMES
                    )
                    print(f"{path.relative_to(ROOT)}  {cfg['run_id']}  {games} model games")
            if written and model["config_dir"] != "api":
                # job.sh n4t runs every config in tasks/, so that folder holds exactly this job.
                for old in set(written[0].parent.glob("*.yaml")) - set(written):
                    old.unlink()


def finished(model: dict[str, Any], run_id: str) -> Counter[str]:
    """Finished model games of one run, by task."""
    path = ROOT / model["local_runs"] / run_id / model["model"]["name"] / "results.jsonl"
    done: Counter[str] = Counter()
    if not path.exists():
        return done
    for line in path.read_text().splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("condition") in MODEL_GAMES and not r.get("error"):
            done[r["params"].get("task") or "survey_v1"] += 1
    return done


def status_rows() -> tuple[list[str], list[list[str]]]:
    """Header and one row per task and setup: finished/planned model games per model."""
    tasks, setups, models = load_tasks(), load_yaml_dir(SETUPS), load_yaml_dir(MODELS)
    cells = {
        sid: len(s["settings"]) * len(s["module"]["sweep"]["n_agents"]) * 2  # MM and INST
        for sid, s in setups.items()
    }
    rows = []
    for t in tasks:
        for sid, setup in setups.items():
            if not t.plays(setup):
                continue
            row = [t.id, setup["title"]]
            for model in models.values():
                planned = cells[sid] * sum(r["episodes"] for r in model["reps"])
                done = sum(
                    finished(
                        model, f"{model['run_prefix']}_{run_name(setup, t, model)}{r['suffix']}"
                    )[t.id]
                    for r in model["reps"]
                )
                row.append(f"{done}/{planned}")
            rows.append(row)
    return ["Task", "Setup", *[m["title"] for m in models.values()]], rows


def cmd_status(args: argparse.Namespace) -> None:
    head, rows = status_rows()
    widths = [max(len(str(r[i])) for r in [head, *rows]) for i in range(len(head))]
    for r in [head, *rows]:
        print("  ".join(str(c).ljust(w) for c, w in zip(r, widths, strict=True)))
    if args.write:
        md = [
            "# N4 task inventory: status",
            "",
            "Finished model games out of planned (every setting × 2, 3, 4 agents × unprompted",
            "and told × the model's runs). Written by `scripts/experiments.py status --write`",
            "from the local copies of the runs.",
            "",
            "| " + " | ".join(head) + " |",
            "|" + "---|" * len(head),
        ]
        md += ["| " + " | ".join(r) + " |" for r in rows]
        STATUS_MD.write_text("\n".join(md) + "\n")
        print(f"wrote {STATUS_MD.relative_to(ROOT)}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tasks", help="list the task inventory").set_defaults(fn=cmd_tasks)
    mk = sub.add_parser("make", help="write the run configs")
    mk.add_argument("--tasks", nargs="*", help="only these tasks (default: all not yet run)")
    mk.add_argument("--models", nargs="*", help="only these model profiles")
    mk.add_argument("--setups", nargs="*", help="only these setups (default: all)")
    mk.set_defaults(fn=cmd_make)
    st = sub.add_parser("status", help="games planned and finished, per task, setup and model")
    st.add_argument("--write", action="store_true", help="also write tasks/STATUS.md")
    st.set_defaults(fn=cmd_status)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
