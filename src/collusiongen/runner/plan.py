"""Expand a run config into episode specs:
module x instance x paraphrase x episode x condition.

Matching: the instance, paraphrase and episode index fix every seed, and the condition does
not, so MM, MH, HM, HH, OO and INST episodes of one (instance, paraphrase, episode) cell are
matched on environment and sampling seeds."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from collusiongen.core.registry import CollusionModule, get_module
from collusiongen.core.seeding import rng_for
from collusiongen.core.types import Condition, GameInstance
from collusiongen.runner.config import ModelConfig, ModuleRunConfig, RunConfig


@dataclass(frozen=True)
class EpisodeSpec:
    run_id: str
    model: str
    module_id: str
    instance: GameInstance
    paraphrase: int
    episode: int
    condition: Condition
    swap_instance: bool
    model_fingerprint: str = ""
    protocol: str = "json_text"

    @property
    def cell(self) -> str:
        """Matched cell: identical across conditions."""
        return f"{self.instance.instance_id}|p{self.paraphrase}|e{self.episode}"

    @property
    def episode_id(self) -> str:
        """Content address: changes if the model, sampling, revision or game changes, so a
        resumed run can never reuse a result produced under different settings."""
        key = "|".join(
            [self.run_id, self.model, self.model_fingerprint, self.cell, self.condition.value]
        )
        return hashlib.sha256(key.encode()).hexdigest()[:24]


# Model fields added after runs started: left out of the fingerprint while unset, so adding a
# field never changes the episode ids (and so the results) of runs made before it existed.
LATER_FIELDS = ("max_calls_per_reply", "system_suffix")


def model_fingerprint(model: ModelConfig, max_steps: int) -> str:
    unset = {f for f in LATER_FIELDS if getattr(model, f) is None}
    blob = json.dumps(
        {
            "model": model.model_dump(mode="json", exclude={"name", "backend", *unset}),
            "served": model.backend.identity_model or model.backend.served_model,
            "trivial": model.backend.trivial,
            "kind": model.backend.kind,
            "max_steps": max_steps,
        },
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def conditions_for(
    module: CollusionModule,
    mcfg: ModuleRunConfig,
    swap: bool,
    params: dict[str, Any] | None = None,
) -> list[Condition]:
    if mcfg.conditions is not None:
        return [Condition(c) for c in dict.fromkeys(mcfg.conditions)]
    conds = [Condition.HH, Condition.OO, Condition.MM]
    needed = (
        module.partner_swap_needed(params) if params is not None else module.supports_partner_swap
    )
    if swap and needed:
        conds += [Condition.MH, Condition.HM]
    if mcfg.instructed:
        conds.append(Condition.INST)
    return conds


def expand(config: RunConfig, model: ModelConfig) -> list[EpisodeSpec]:
    specs: list[EpisodeSpec] = []
    fingerprint = model_fingerprint(model, config.max_steps_per_episode)
    for mcfg in config.modules:
        module = get_module(mcfg.id)
        bad = [p for p in mcfg.paraphrases if not 0 <= p < module.n_paraphrases]
        if bad:
            raise ValueError(f"{mcfg.id}: paraphrases {bad} outside 0..{module.n_paraphrases - 1}")
        if model.pretraining and not module.runs_on_pretraining_tags:
            continue
        for knobs in mcfg.knob_settings():
            for k in range(module.instance_count(mcfg.n_instances, knobs)):
                index = mcfg.instance_offset + k
                instance = module.sample_instance(config.seed, mcfg.split, index, knobs)
                # Swap assignment depends on the index only, so a swept instance gets partner
                # swaps at every knob value or at none.
                swap = bool(
                    rng_for(config.seed, module.id, "swap", index).random()
                    < mcfg.partner_swap_fraction
                )
                specs += _cell_specs(config, model, module, mcfg, instance, swap, fingerprint)
    return specs


def _cell_specs(
    config: RunConfig,
    model: ModelConfig,
    module: CollusionModule,
    mcfg: ModuleRunConfig,
    instance: GameInstance,
    swap: bool,
    fingerprint: str,
) -> list[EpisodeSpec]:
    """Every (paraphrase, episode, condition) of one instance; conditions share the cell."""
    return [
        EpisodeSpec(
            config.run_id,
            model.name,
            module.id,
            instance,
            p,
            e,
            cond,
            swap,
            fingerprint,
            model.action_protocol,
        )
        for p in mcfg.paraphrases
        for e in range(mcfg.episode_offset, mcfg.episode_offset + mcfg.episodes_per_instance)
        for cond in conditions_for(module, mcfg, swap, instance.params)
    ]
