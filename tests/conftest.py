from __future__ import annotations

import pytest

from collusiongen.core.env import Services
from collusiongen.core.registry import CollusionModule, get_module
from collusiongen.core.types import Condition, GameInstance, Split
from collusiongen.runner.episode import run_episode
from collusiongen.runner.plan import EpisodeSpec

CORE = ["a1_pricing", "n2_market", "h1_hub", "a2_verify", "n4_relay"]


def small_instance(module: CollusionModule, index: int = 0, **override: object) -> GameInstance:
    """Short episodes so the suite stays fast."""
    defaults: dict[str, object] = {}
    if module.id in ("a1_pricing", "n2_market", "h1_hub"):
        defaults = {"horizon": 12}
    defaults.update(override)
    return module.sample_instance(7, Split.TRAIN, index, defaults)


async def play(
    module_id: str,
    condition: Condition,
    instance: GameInstance | None = None,
    policies: dict | None = None,
) -> dict:
    module = get_module(module_id)
    inst = instance or small_instance(module)
    spec = EpisodeSpec("test", "scripted", module_id, inst, 0, 0, condition, True)
    if policies is None:
        kinds = {Condition.HH: "honest", Condition.OO: "oracle"}[condition]
        policies = {s: getattr(module, kinds)(inst, s) for s in module.seats(inst)}
    result = await run_episode(module, spec, policies, Services())
    return result.record


@pytest.fixture(params=CORE)
def core_module_id(request: pytest.FixtureRequest) -> str:
    return str(request.param)
