"""Final leak-monitor results per model game of one shared-audit run (results.jsonl), by setting.

usage: .venv/bin/python scripts/shared_results.py <model profile> <task id> [setup]
"""
import glob
import json
import sys

import yaml

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")
from audit_progress import SETTING  # noqa: E402
from collusiongen.runner.config import RunConfig  # noqa: E402
from collusiongen.runner.plan import expand  # noqa: E402

KEYS = ("leak_procedure", "leak_fact", "leak_records", "leak_amounts", "items_request", "items_refusal",
        "items_rationalisation", "assignment_quoted")


def main(model, task, setup="shared_audit_3"):
    c = RunConfig.model_validate(yaml.safe_load(open(f"configs/api/{model}/{task}__{setup}.yaml")))
    st = {s.episode_id: SETTING.get((bool(s.instance.params.get("forum")), bool(s.instance.params.get("messaging", True)),
                                     s.instance.params.get("max_messages")))
          for s in expand(c, c.models[0]) if s.condition.value == "MM"}
    print(f"| {model} {task} | solved | leaks | procedure | fact | records | amounts | requests | refusals | rationalisations | assignment quoted |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for f in glob.glob(f"runs/api/{c.run_id}/*/results.jsonl"):
        rows = {}
        for line in open(f):
            r = json.loads(line)
            if r["episode_id"] in st:
                s = r["secondary"]
                rows[st[r["episode_id"]]] = [s.get("team_solved", 0), s.get("leak_items", 0)] + [s.get(k, 0) for k in KEYS]
        for name in ("folder", "folder_msg5", "folder_forum", "all"):
            if name in rows:
                print(f"| {name} | " + " | ".join(str(int(v or 0)) for v in rows[name]) + " |")


if __name__ == "__main__":
    main(*sys.argv[1:])
