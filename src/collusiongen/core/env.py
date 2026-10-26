"""Environment contract. Environments simulate the game and log state; they never call a model."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from collusiongen.core.log import EventLog
from collusiongen.core.types import Action, GameInstance, Observation, Outcome, SeatId, Variant
from collusiongen.judges.messages import KeywordJudge, MessageJudge


@dataclass
class Services:
    """External services injected into environments (dependency inversion). Tests use the
    defaults; production runs pass the validated LLM judge."""

    judge: MessageJudge = field(default_factory=KeywordJudge)


class InvalidActionError(ValueError):
    """Raised by an environment when an action is illegal in the current state."""


class Environment(ABC):
    """A turn-based multi-agent game.

    The runner drives it with a simple loop::

        while (seat := env.next_seat()) is not None:
            obs = env.observe(seat)
            await env.astep(seat, action_for(obs))
        outcome = env.outcome()

    Simultaneous moves (e.g. a pricing round) are implemented by buffering actions until every
    seat has acted; observations must not reveal buffered actions of other seats.
    """

    def __init__(self, instance: GameInstance, variant: Variant, log: EventLog) -> None:
        self.instance = instance
        self.variant = variant
        self.log = log
        self.params: dict[str, Any] = instance.params
        log.emit(
            "reset",
            instance_id=instance.instance_id,
            params=instance.params,
            skin=instance.skin.skin_id,
            paraphrase=variant.paraphrase,
            instructed=variant.instructed,
        )

    @property
    @abstractmethod
    def seats(self) -> list[SeatId]:
        """All seats, in a fixed order."""

    @abstractmethod
    def next_seat(self) -> SeatId | None:
        """Seat that must act next, or None when the episode is over."""

    @abstractmethod
    def observe(self, seat: SeatId) -> Observation:
        """Observation for `seat`. Must be side-effect free apart from logging."""

    @abstractmethod
    def step(self, seat: SeatId, action: Action) -> None:
        """Apply a validated action. Raise InvalidActionError for illegal actions."""

    @abstractmethod
    def outcome(self) -> Outcome:
        """Score the finished episode from logged state."""

    async def apply(self, seat: SeatId, action: Action, *, substituted: bool = False) -> None:
        """Entry point used by the runner: log the action, then apply it.

        `substituted` marks a null action played because the policy's output was unusable.
        """
        self.log.emit("action", seat, action=action, substituted=substituted)
        await self.astep(seat, action)

    batch_actions: bool = False  # environments that run several tool calls from one reply

    async def apply_batch(self, seat: SeatId, actions: list[Action]) -> int:
        """Apply several actions from one reply (native parallel tool calls). Returns how many
        were applied. By default only the first counts; environments that set
        `batch_actions` apply them in order for the same agent."""
        await self.apply(seat, actions[0])
        return 1

    async def astep(self, seat: SeatId, action: Action) -> None:
        """Async hook for environments that consult an async service (e.g. an LLM regulator)."""
        self.step(seat, action)

    def format_failure_rate(self, seat: SeatId | None = None) -> float:
        actions = [e for e in self.log.of_kind("action") if seat is None or e.seat == seat]
        if not actions:
            return 0.0
        return sum(bool(e.payload.get("substituted")) for e in actions) / len(actions)

    def system_prompt(self, seat: SeatId, body: str) -> str:
        """Prefix the instructed-ceiling text in the INST condition; neutral otherwise."""
        if self.variant.instructed and self.variant.instructed_prefix:
            return f"{self.variant.instructed_prefix.strip()}\n\n{body}"
        return body
