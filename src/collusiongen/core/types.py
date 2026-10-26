"""Plain data types shared by every layer. No behaviour lives here."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

SeatId = str
Action = dict[str, Any]


class Split(StrEnum):
    """Generator splits. Headline numbers come from held-out splits only."""

    TRAIN = "train"
    HELDOUT_SKIN = "heldout_skin"
    HELDOUT_PARAMS = "heldout_params"
    HELDOUT_SCHEMA = "heldout_schema"


class PolicyKind(StrEnum):
    MODEL = "M"
    HONEST = "H"
    ORACLE = "O"
    INSTRUCTED = "I"


class Condition(StrEnum):
    """Who sits in seat group A and seat group B (Method 1, 2x2 partner design)."""

    MM = "MM"
    MH = "MH"
    HM = "HM"
    HH = "HH"
    OO = "OO"
    INST = "INST"

    @property
    def kinds(self) -> tuple[PolicyKind, PolicyKind]:
        if self is Condition.INST:
            return PolicyKind.INSTRUCTED, PolicyKind.INSTRUCTED
        return PolicyKind(self.value[0]), PolicyKind(self.value[1])

    @property
    def needs_model(self) -> bool:
        return any(k in (PolicyKind.MODEL, PolicyKind.INSTRUCTED) for k in self.kinds)


@dataclass(frozen=True)
class Skin:
    """Narrative surface of an instance: renamed entities and units, no game content."""

    skin_id: str
    theme: str
    vocab: dict[str, str]

    def __getitem__(self, key: str) -> str:
        return self.vocab[key]


@dataclass(frozen=True)
class GameInstance:
    """One generated game: schema x skin x parameters, with a fixed seed."""

    instance_id: str
    module_id: str
    split: Split
    params: dict[str, Any]
    skin: Skin
    seed: int
    canary: str


@dataclass(frozen=True)
class Variant:
    """Per-episode presentation choices that must not change the game itself."""

    paraphrase: int = 0
    instructed: bool = False
    instructed_prefix: str = ""
    # How the model is asked to act: "json_text" (one JSON object in the reply) or
    # "native_tools" (the model's own trained tool-call format, parsed by the server).
    protocol: str = "json_text"


@dataclass
class Observation:
    """What a seat sees when it must act.

    `prompt` is for language-model policies; `state` is a structured view of the same
    information. Scripted references may additionally use analytic quantities computed from the
    instance (e.g. the Nash price), which they receive at construction, never through `state`.
    """

    seat: SeatId
    phase: str
    system: str
    prompt: str
    state: dict[str, Any]
    action_space: ActionSpace
    # Native tool protocol, multi-step games (N4): earlier calls of this agent's session as
    # [{"name", "arguments", "result"}]; the policy replays them as assistant tool-call and
    # tool-result messages, the conversation shape the model was trained on. `prompt` is then
    # the opening user message.
    tool_history: list[dict[str, Any]] | None = None


class ActionSpace:
    """Legal actions for one decision. Subclasses are defined next to their environment."""

    def null(self) -> Action:
        """Action substituted when a policy produces nothing usable."""
        raise NotImplementedError

    def defect(self) -> Action:
        """The non-cooperative action, used by the always-defect trivial agent."""
        raise NotImplementedError

    def sample(self, rng: Any) -> Action:
        """A uniformly random legal action, used by the random trivial agent."""
        raise NotImplementedError

    def validate(self, action: Any) -> Action | None:
        """Return a normalised action, or None if it is illegal."""
        raise NotImplementedError

    def tools(self) -> list[dict[str, Any]]:
        """Native tool definitions (OpenAI function format) for this decision."""
        return []

    def from_tool_call(self, name: str, arguments: dict[str, Any]) -> Action | None:
        """Map a native tool call to a legal action, or None."""
        return None


def function_tool(
    name: str,
    description: str,
    properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
            },
        },
    }


@dataclass
class Outcome:
    """Result of one episode, on the module's raw scale."""

    victim_loss: float
    colluder_utility: dict[SeatId, float]
    task_success: float
    secondary: dict[str, float] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def mean_utility(self) -> float:
        values = list(self.colluder_utility.values())
        return sum(values) / len(values) if values else 0.0
