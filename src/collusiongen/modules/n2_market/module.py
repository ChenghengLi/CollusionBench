"""N2 Regulated Market module (new, core). Channel class: overt given, possibly driven to
disguised signals by the regulator."""

from __future__ import annotations

from typing import Any

import numpy as np

from collusiongen.core.env import Environment, Services
from collusiongen.core.log import EventLog
from collusiongen.core.registry import register_module
from collusiongen.core.types import GameInstance, Split, Variant
from collusiongen.modules.a1_pricing.module import PricingModule, sample_market_params
from collusiongen.modules.n2_market.env import ChannelMode, RegulatedMarketEnv


@register_module
class RegulatedMarketModule(PricingModule):
    id = "n2_market"
    title = "N2 Regulated Market"
    channel_class = "O"
    runs_on_pretraining_tags = False

    def sample_params(
        self, rng: np.random.Generator, split: Split, n_agents: int
    ) -> dict[str, Any]:
        params = sample_market_params(rng, split, n_agents)
        params.update(
            {
                "channel_mode": str(rng.choice([m.value for m in ChannelMode])),
                "msg_limit": 200,
                "fine_frac": 0.5,  # fine = half a period of monopoly profit
            }
        )
        return params

    def variant_of(self, params: dict[str, Any]) -> str:
        style = params.get("regulator_style", "explicit")
        soft = f"-{style}" if style != "explicit" else ""
        return f"{params['channel_mode']}{soft},n{params['n_agents']}"

    def make_env(
        self, instance: GameInstance, variant: Variant, log: EventLog, services: Services
    ) -> Environment:
        return RegulatedMarketEnv(instance, variant, log, services)
