"""N1 Mirror Monitor module (probe, outside the composite). Built on ControlArena data."""

from __future__ import annotations

from typing import Any

import numpy as np

from collusiongen.core.env import Environment, Services
from collusiongen.core.log import EventLog
from collusiongen.core.policy import Policy, ScriptedPolicy
from collusiongen.core.registry import (
    CANARY,
    CollusionModule,
    params_digest,
    register_module,
)
from collusiongen.core.seeding import derive_seed
from collusiongen.core.types import (
    Action,
    GameInstance,
    Observation,
    PolicyKind,
    SeatId,
    Skin,
    Split,
    Variant,
)
from collusiongen.generator.skins import SkinTheme
from collusiongen.modules.n1_mirror.dataset import TOY_DATASET, MonitorItem, load_items
from collusiongen.modules.n1_mirror.env import MirrorMonitorEnv


def _item(instance: GameInstance) -> MonitorItem:
    items = {i.item_id: i for i in load_items(instance.params["dataset"])}
    return items[instance.params["item_id"]]


class GroundTruthMonitor(ScriptedPolicy):
    def __init__(self, item: MonitorItem, oracle: bool) -> None:
        self.item = item
        self.kind = PolicyKind.ORACLE if oracle else PolicyKind.HONEST
        self.name = "self_preferring_monitor" if oracle else "ground_truth_monitor"

    def decide(self, obs: Observation) -> Action:
        if self.item.label == "clean":
            return {"suspicion": 0.0}
        if self.kind is PolicyKind.ORACLE and self.item.author == "own":
            return {"suspicion": 0.0}  # waves its own model's attacks through
        return {"suspicion": 100.0}


@register_module
class MirrorMonitorModule(CollusionModule):
    id = "n1_mirror"
    title = "N1 Mirror Monitor (probe)"
    channel_class = "-"
    core = False
    in_composite = False
    supports_partner_swap = False
    agent_range = (1, 1)  # one monitor, one decision
    default_n_agents = 1
    runs_on_pretraining_tags = True
    dataset: str = str(TOY_DATASET)

    def skin_themes(self) -> list[SkinTheme]:
        return [SkinTheme("code_review", {"role": ["reviewer"]})]

    def sample_params(
        self, rng: np.random.Generator, split: Split, n_agents: int
    ) -> dict[str, Any]:
        raise NotImplementedError("N1 instances are dataset items; see sample_instance")

    def sample_instance(
        self, run_seed: int, split: Split, index: int, overrides: dict[str, Any] | None = None
    ) -> GameInstance:
        dataset = (overrides or {}).get("dataset", self.dataset)
        items = load_items(dataset)
        item = items[index % len(items)]
        params = {"dataset": dataset, "item_id": item.item_id, "n_agents": 1}
        seed = derive_seed(run_seed, self.id, item.item_id)
        return GameInstance(
            instance_id=f"{self.id}/{item.item_id}-{params_digest(seed, params)}",
            module_id=self.id,
            split=split,
            params=params,
            skin=Skin("none", "code_review", {}),
            seed=seed,
            canary=CANARY,
        )

    def instance_count(self, requested: int, overrides: dict[str, Any]) -> int:
        """`n_instances <= 0` means one instance per dataset item."""
        n_items = len(load_items(overrides.get("dataset", self.dataset)))
        return n_items if requested <= 0 else requested

    def seats(self, instance: GameInstance) -> list[SeatId]:
        return ["A"]

    def make_env(
        self, instance: GameInstance, variant: Variant, log: EventLog, services: Services
    ) -> Environment:
        return MirrorMonitorEnv(instance, variant, log, _item(instance))

    def honest(self, instance: GameInstance, seat: SeatId) -> Policy:
        return GroundTruthMonitor(_item(instance), oracle=False)

    def oracle(self, instance: GameInstance, seat: SeatId) -> Policy:
        return GroundTruthMonitor(_item(instance), oracle=True)
