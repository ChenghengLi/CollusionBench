"""Where a model's dept_audit run config lives: configs/api/<model>/ for API models, or the
model profile's config_dir (e.g. configs/rcp7b/tasks/) for models served on RCP."""

import os

import yaml


def config_path(model: str, scenario: str, setup: str = "dept_audit") -> str:
    # ring scenarios are named ring_<x> (task ring_<x>_v1); the first audits audit_<x>_v1
    name = (f"{scenario}_v1__{setup}.yaml" if scenario.startswith(("ring_", "shared_"))
            else f"audit_{scenario}_v1__{setup}.yaml")
    api = f"configs/api/{model}/{name}"
    if os.path.exists(api):
        return api
    profile = yaml.safe_load(open(f"configs/models/{model}.yaml"))
    return f"configs/{profile['config_dir']}/tasks/{name}"
