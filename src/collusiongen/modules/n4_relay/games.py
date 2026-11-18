"""What a card game is about: the data in /data, the job, and the answer check.

Card scenarios (cards/) subclass DataGame through CardGame and register themselves with
@register_game("card_<name>"); a config picks one with `game: card_<name>`. The earlier games
(survey, brief, exam, records, school operations, audits) are in deprecated/.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from collusiongen.core.types import GameInstance

GAMES: dict[str, type[DataGame]] = {}


def register_game(name: str) -> Callable[[type[DataGame]], type[DataGame]]:
    def add(cls: type[DataGame]) -> type[DataGame]:
        if name in GAMES:
            raise ValueError(f"game {name!r} is already registered")
        cls.name = name
        GAMES[name] = cls
        return cls

    return add


def game_for(instance: GameInstance) -> DataGame:
    """The game named by `game` in the params."""
    name = instance.params.get("game", "")
    if name not in GAMES:
        raise ValueError(f"unknown game {name!r}; known: {', '.join(sorted(GAMES))}")
    return GAMES[name](instance)


class DataGame:
    """One kind of N4 job. Subclasses fill in the four parts below."""

    name: ClassVar[str] = ""

    def __init__(self, instance: GameInstance) -> None:
        self.instance = instance
        self.params = instance.params

    def files(self) -> dict[str, str]:
        """/data path -> file text. Sorted paths are dealt to agents 1, 2, ..., n, 1, 2, ..."""
        raise NotImplementedError

    def check(self, answer: str) -> bool:
        raise NotImplementedError

    def answer(self) -> str:
        """The right answer, for the scripted pooling reference."""
        raise NotImplementedError

    def data_info(self) -> str:
        """The text of /data/.info."""
        return "Exports from your team's systems. Each person can open only their own team's files."

    def report(self) -> dict[str, Any]:
        """Facts stored with each game's outcome."""
        return {"game": self.name}



# the card scenarios register themselves on import
from collusiongen.modules.n4_relay.cards import pricing as _card_pricing  # noqa: E402,F401
from collusiongen.modules.n4_relay.cards import exam as _card_exam  # noqa: E402,F401
from collusiongen.modules.n4_relay.cards import records as _card_records  # noqa: E402,F401
from collusiongen.modules.n4_relay.cards import template as _card_template  # noqa: E402,F401
from collusiongen.modules.n4_relay.cards import action as _card_action  # noqa: E402,F401
