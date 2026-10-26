"""Seat assignment: turn an episode spec into one policy per seat (the 2x2 partner design)."""

from __future__ import annotations

import os

from collusiongen.agents.backends import (
    ChatBackend,
    OpenAIChatBackend,
    OpenAICompletionBackend,
)
from collusiongen.agents.llm import LLMPolicy
from collusiongen.agents.trivial import AlwaysDefectAgent, EmptyAgent, RandomAgent
from collusiongen.core.policy import Policy
from collusiongen.core.registry import CollusionModule
from collusiongen.core.seeding import derive_seed
from collusiongen.core.types import PolicyKind, SeatId
from collusiongen.runner.config import BackendConfig, ModelConfig
from collusiongen.runner.plan import EpisodeSpec


def make_backend(cfg: BackendConfig) -> ChatBackend | None:
    """None for trivial backends, which need no model."""
    if cfg.kind == "trivial":
        return None
    api_key = os.environ.get(cfg.api_key_env) if cfg.api_key_env else None
    assert cfg.base_url and cfg.served_model  # checked by BackendConfig
    if cfg.kind == "openai_chat":
        return OpenAIChatBackend(
            cfg.base_url,
            cfg.served_model,
            api_key,
            cfg.timeout_s,
            chat_path=cfg.chat_path,
            extra_headers=cfg.headers,
        )
    return OpenAICompletionBackend(cfg.base_url, cfg.served_model, api_key, cfg.timeout_s)


class PolicyFactory:
    """Builds seat policies for one model. The model's backend is shared across episodes."""

    def __init__(self, model: ModelConfig, backend: ChatBackend | None) -> None:
        self.model = model
        self.backend = backend

    def seats_for(self, module: CollusionModule, spec: EpisodeSpec) -> dict[SeatId, Policy]:
        group_a, group_b = module.seat_groups(spec.instance)
        kind_a, kind_b = spec.condition.kinds
        policies: dict[SeatId, Policy] = {}
        for seats, kind in ((group_a, kind_a), (group_b, kind_b)):
            for seat in seats:
                policies[seat] = self._policy(module, spec, seat, kind)
        return policies

    def _policy(
        self, module: CollusionModule, spec: EpisodeSpec, seat: SeatId, kind: PolicyKind
    ) -> Policy:
        if kind is PolicyKind.HONEST:
            return module.honest(spec.instance, seat)
        if kind is PolicyKind.ORACLE:
            return module.oracle(spec.instance, seat)
        # The seed ignores the condition, so a seat samples identically in MM, MH, HM and INST.
        seed = derive_seed(spec.cell, seat, "sampling")
        cfg = self.model.backend
        if cfg.kind == "trivial":
            if cfg.trivial == "empty":
                return EmptyAgent()
            if cfg.trivial == "random":
                return RandomAgent(seed)
            return AlwaysDefectAgent()
        assert self.backend is not None
        return LLMPolicy(
            self.backend,
            self.model.sampling,
            name=self.model.name,
            seed=seed,
            kind=kind,
            few_shot=module.few_shot if self.model.pretraining else (),
            protocol=self.model.action_protocol,
            system_suffix=self.model.system_suffix or "",
        )
