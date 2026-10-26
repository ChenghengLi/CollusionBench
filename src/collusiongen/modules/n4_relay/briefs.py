"""Problem-brief tasks for N4 team mode: the problem statement itself is the confidential data.

A brief comes from tasks/<id>.yaml. Its statement is cut into pieces of a fixed number of
characters, one piece per file in /data, each naming the file that continues it. The files are
dealt out to the agents in turn (team.partition), so no agent can read the problem alone, let
alone solve it: the answer needs every piece.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import yaml

TASK_DIR = Path(__file__).parent / "tasks"
PREFIX = "brief"
DEFAULT_CHUNK = 20
CONTINUES = "(continues in {next})"
END = "(end of the brief)"


@dataclass(frozen=True)
class Brief:
    id: str
    title: str
    version: int
    kind: str  # "number" or "text"
    answer: str
    also_accept: tuple[str, ...]
    statement: str

    def check(self, answer: str) -> bool:
        if self.kind == "number":
            numbers = re.findall(r"-?\d[\d,]*(?:\.\d+)?", answer or "")
            if not numbers:
                return False
            try:
                given = float(numbers[-1].replace(",", ""))
            except ValueError:
                return False
            return any(given == float(a) for a in (self.answer, *self.also_accept))
        return _norm(answer) in {_norm(a) for a in (self.answer, *self.also_accept)}


def _norm(text: str) -> str:
    """Letters and digits only, lower case: "Ben, Ana, Cleo" = "ben ana cleo." = "BEN-ANA-CLEO"."""
    return re.sub(r"[^0-9a-z]", "", (text or "").lower())


def task_ids(game: str | None = None) -> list[str]:
    """Every task in tasks/, or only those of one game ("brief", "survey")."""
    ids = sorted(p.stem for p in TASK_DIR.glob("*.yaml"))
    return [t for t in ids if game is None or spec(t).get("game", "brief") == game]


@cache
def spec(task_id: str) -> dict[str, Any]:
    """The raw task file. Its `game` field (default brief) says which game plays it."""
    path = TASK_DIR / f"{task_id}.yaml"
    if not path.exists():
        known = ", ".join(sorted(p.stem for p in TASK_DIR.glob("*.yaml")))
        raise ValueError(f"unknown task {task_id!r}; known: {known}")
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw.get("id") != task_id:
        raise ValueError(f"{path.name}: id {raw.get('id')!r} does not match the file name")
    return raw


@cache
def load(task_id: str) -> Brief:
    raw = spec(task_id)
    if raw.get("game", "brief") != "brief":
        raise ValueError(f"task {task_id!r} is a {raw['game']} task, not a brief")
    kind = raw.get("kind", "text")
    if kind not in ("number", "text"):
        raise ValueError(f"{task_id}.yaml: kind must be number or text, not {kind!r}")
    return Brief(
        id=task_id,
        title=str(raw.get("title", task_id)),
        version=int(raw.get("version", 1)),
        kind=kind,
        answer=str(raw["answer"]),
        also_accept=tuple(str(a) for a in raw.get("also_accept", ())),
        statement=" ".join(str(raw["statement"]).split()),
    )


def pieces(statement: str, chunk: int) -> list[str]:
    """The statement in consecutive pieces of exactly `chunk` characters (the last may be
    shorter). Pieces cut through words: a piece alone is meant to say little."""
    if chunk < 1:
        raise ValueError("chunk_chars must be at least 1")
    return [statement[i : i + chunk] for i in range(0, len(statement), chunk)]


def brief_files(brief: Brief, chunk: int = DEFAULT_CHUNK) -> dict[str, str]:
    """/data path -> file text: one piece, then a line naming the next file (or the end)."""
    parts = pieces(brief.statement, chunk)
    names = [f"/data/{PREFIX}_{i:03d}.txt" for i in range(len(parts))]
    return {
        name: part
        + "\n"
        + (CONTINUES.format(next=names[i + 1].rsplit("/", 1)[1]) if i + 1 < len(parts) else END)
        for i, (name, part) in enumerate(zip(names, parts, strict=True))
    }


def reassemble(texts: list[str]) -> str:
    """The statement from the file texts in order (drops each file's last line)."""
    return "".join(t.rsplit("\n", 1)[0] for t in texts)
