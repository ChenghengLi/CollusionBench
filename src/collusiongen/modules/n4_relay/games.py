"""What the N4 team game is about: the data in /data, the job in the prompt, and the answer check.

Every game keeps the rest of team mode unchanged: the files are dealt out to the agents in turn,
each agent can open only its own, the same tools and channels exist, and harm is measured the same
way (an agent using material another agent wrote). A game only decides what the files hold and
what counts as solved.

Add a game type by subclassing DataGame and decorating it with @register_game("name"). A config
picks a game with `task: <id>` (a file in tasks/, which names its game) or with `game: name`.
Brief games also take `chunk_chars`.

    survey  the original: CSV files of counts; the job is the exact total of one column
    brief   a problem statement cut into short pieces, one per file; the job is its answer
    exam    12 questions over company records everyone can read; a budget too small to answer
            them all alone (exam.py, T1 Exam pool)
    records confidential department files, one agent per department; every audit question joins
            two departments (records.py, T3 Company records)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from collusiongen.core.types import GameInstance
from collusiongen.modules.n4_relay import briefs, prompts
from collusiongen.modules.n4_relay.env import data_plan, render_csv

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
    """`game` in the params if set, else the game its `task` file names, else the survey."""
    params = instance.params
    name = params.get("game") or (
        briefs.spec(params["task"]).get("game", "brief") if params.get("task") else "survey"
    )
    if name not in GAMES:
        raise ValueError(f"unknown game {name!r}; known: {', '.join(sorted(GAMES))}")
    return GAMES[name](instance)


class DataGame:
    """One kind of N4 job. Subclasses fill in the four parts below."""

    name: ClassVar[str] = ""
    # Native tools: whether submit takes text (a name, a word) or a number.
    text_answer: ClassVar[bool] = False

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

    def jobs(self) -> list[str]:
        """Hidden-mode job paraphrases, ending with what /data holds. May use {project},
        {n_files}, {dataset} and {field}."""
        raise NotImplementedError

    def data_info(self, style: str) -> str:
        """The text of /data/.info."""
        return prompts.folder_info(style)["/data"]

    def rule(self, style: str) -> str | None:
        """The rule sentence for hidden mode, or None to keep the standard one for the style."""
        return None

    def report(self) -> dict[str, Any]:
        """Facts stored with each game's outcome."""
        return {"game": self.name}


@register_game("survey")
class SurveyGame(DataGame):
    """The original job: the exact total of one column across every CSV file."""

    def __init__(self, instance: GameInstance) -> None:
        super().__init__(instance)
        self.plan = data_plan(instance)

    def files(self) -> dict[str, str]:
        field = self.instance.skin["field"]
        return {p: render_csv(rows, field) for p, rows in self.plan.files.items()}

    def check(self, answer: str) -> bool:
        return briefs.Brief("", "", 1, "number", str(self.plan.total), (), "").check(answer)

    def answer(self) -> str:
        return str(self.plan.total)

    def jobs(self) -> list[str]:
        return [t + prompts.TEAM_ACCESS for t in prompts.TASKS_HIDDEN]

    def report(self) -> dict[str, Any]:
        return {"game": self.name, "total": self.plan.total, "n_files": len(self.plan.files)}


@register_game("brief")
class BriefGame(DataGame):
    """The problem statement is the data: cut into `chunk_chars`-character pieces, one per file,
    each naming the file that continues it."""

    text_answer = True

    def __init__(self, instance: GameInstance) -> None:
        super().__init__(instance)
        task = self.params.get("task")
        if not task:
            raise ValueError(
                "game 'brief' needs a task: one of " + ", ".join(briefs.task_ids("brief"))
            )
        self.brief = briefs.load(task)
        self.chunk = int(self.params.get("chunk_chars", briefs.DEFAULT_CHUNK))

    def files(self) -> dict[str, str]:
        return briefs.brief_files(self.brief, self.chunk)

    def check(self, answer: str) -> bool:
        return self.brief.check(answer)

    def answer(self) -> str:
        return self.brief.answer

    def jobs(self) -> list[str]:
        return prompts.BRIEF_JOBS_HIDDEN

    def data_info(self, style: str) -> str:
        return prompts.brief_data_info(style)

    def rule(self, style: str) -> str | None:
        return prompts.brief_rule(style)

    def report(self) -> dict[str, Any]:
        return {
            "game": self.name,
            "task": self.brief.id,
            "answer": self.brief.answer,
            "chunk_chars": self.chunk,
            "n_files": len(self.files()),
        }


# The exam game lives in its own file; importing it here registers it with the other games.
from collusiongen.modules.n4_relay import exam as _exam  # noqa: E402,F401
from collusiongen.modules.n4_relay import records as _records  # noqa: E402,F401
from collusiongen.modules.n4_relay import school_ops as _school_ops  # noqa: E402,F401
from collusiongen.modules.n4_relay import audits as _audits  # noqa: E402,F401
from collusiongen.modules.n4_relay.cards import pricing as _card_pricing  # noqa: E402,F401
from collusiongen.modules.n4_relay.cards import survey as _card_survey  # noqa: E402,F401
from collusiongen.modules.n4_relay.cards import exam as _card_exam  # noqa: E402,F401
from collusiongen.modules.n4_relay.cards import approvals as _card_approvals  # noqa: E402,F401
from collusiongen.modules.n4_relay.cards import records as _card_records  # noqa: E402,F401
