"""Write the brief-game configs from the survey configs, so the brief games run in exactly the same
settings: the same models, sampling, repetitions (episode offsets), channel settings and message
caps. Each survey module entry becomes one entry per brief task.

    .venv/bin/python scripts/make_brief_configs.py            # every brief task in tasks/
    .venv/bin/python scripts/make_brief_configs.py depot_v1   # only some tasks

Survey -> brief, per config directory:
    configs/api/n4_channels.yaml -> configs/api/n4_brief_channels.yaml
    configs/api/n4_dmcap.yaml    -> configs/api/n4_brief_dmcap.yaml
    configs/<rcp dir>/n4c.yaml   -> configs/<rcp dir>/n4pc.yaml   (job.sh experiment n4p)
    configs/<rcp dir>/n4d.yaml   -> configs/<rcp dir>/n4pd.yaml
Rerun it after adding a task; it overwrites only these brief files.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import yaml

from collusiongen.modules.n4_relay import briefs

ROOT = Path(__file__).resolve().parent.parent / "configs"
# The model directories whose survey runs had five repetitions (base, _repra, _reprb; the 0.9B's
# _repra holds four).
RCP_DIRS = ["rcp", "rcp7b", "rcp09b", "rcp32b", "rcpmova"]
PAIRS = {"n4c.yaml": "n4pc.yaml", "n4d.yaml": "n4pd.yaml"}
API_PAIRS = {"n4_channels.yaml": "n4_brief_channels.yaml", "n4_dmcap.yaml": "n4_brief_dmcap.yaml"}
# GLM-5.3-Flash played each survey game once; the brief games get five runs like the K2 models.
API_EPISODES = 5
CHUNK = briefs.DEFAULT_CHUNK


def brief_config(src: Path, tasks: list[str], episodes: int | None = None) -> str:
    cfg = yaml.safe_load(src.read_text())
    run_id = cfg["run_id"]
    for old in ("_n4_channels", "_n4_dmcap"):
        run_id = run_id.replace(old, "_n4_brief" + old.removeprefix("_n4"))
    assert run_id != cfg["run_id"], f"{src}: run_id {run_id!r} has no n4_channels/n4_dmcap part"
    modules = []
    for task in tasks:
        for m in cfg["modules"]:
            m = copy.deepcopy(m)
            m["params_override"].update(game="brief", task=task, chunk_chars=CHUNK)
            if episodes is not None:
                m["episodes_per_instance"] = episodes
            modules.append(m)
    out = {**cfg, "run_id": run_id, "modules": modules}
    head = (
        f"# Brief games ({', '.join(tasks)}) in the settings of {src.relative_to(ROOT.parent)}:\n"
        "# the same model, sampling, repetitions and channel settings; each survey entry is\n"
        f"# repeated once per task, with game: brief and {CHUNK}-character pieces. Written by\n"
        "# scripts/make_brief_configs.py; edit the survey config or the script, not this file.\n"
    )
    return head + yaml.safe_dump(out, sort_keys=False)


def main(tasks: list[str]) -> None:
    written = []
    for name, new in API_PAIRS.items():
        dest = ROOT / "api" / new
        dest.write_text(brief_config(ROOT / "api" / name, tasks, API_EPISODES))
        written.append(dest)
    for base in RCP_DIRS:
        for d in sorted(ROOT.glob(f"{base}")) + sorted(ROOT.glob(f"{base}_rep*")):
            for name, new in PAIRS.items():
                if (d / name).exists():
                    (d / new).write_text(brief_config(d / name, tasks))
                    written.append(d / new)
    for p in written:
        print(p.relative_to(ROOT.parent))


if __name__ == "__main__":
    main(sys.argv[1:] or briefs.task_ids("brief"))
