"""Policy contract. Scripted references, trivial agents and LLM agents all implement it, so any
of them can sit in any seat; this is what makes the partner swap a configuration change."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from collusiongen.core.types import Action, Observation, PolicyKind


@dataclass
class Decision:
    """A policy's answer to one observation.

    `action` is None when the policy produced nothing parseable; the runner then substitutes the
    environment's null action and counts a format failure.
    """

    action: Action | None
    raw_text: str = ""
    # Every JSON object in the reply, in order. The runner plays the last one that is legal,
    # so a trailing note ({"plan": ...}) does not hide a valid action written before it.
    candidates: list[Action] = field(default_factory=list)
    reasoning: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Policy(Protocol):
    name: str
    kind: PolicyKind

    async def act(self, obs: Observation) -> Decision: ...


class ScriptedPolicy:
    """Base class for deterministic, model-free policies (H and O references)."""

    name = "scripted"
    kind = PolicyKind.HONEST

    async def act(self, obs: Observation) -> Decision:
        return Decision(action=self.decide(obs), raw_text="<scripted>")

    def decide(self, obs: Observation) -> Action:
        raise NotImplementedError
