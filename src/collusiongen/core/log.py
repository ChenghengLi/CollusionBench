"""Append-only, hash-chained event log written by environments (Method 4: "log everything").

Metrics are computed from these events, never from the transcript. Each record carries the hash
of the previous record, so any edit or deletion after the fact breaks `verify_chain`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GENESIS = "0" * 64
log = logging.getLogger(__name__)


def _digest(prev_hash: str, body: dict[str, Any]) -> str:
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256((prev_hash + payload).encode()).hexdigest()


@dataclass(frozen=True)
class Event:
    seq: int
    episode_id: str
    kind: str
    seat: str | None
    payload: dict[str, Any]
    t: float
    prev_hash: str
    hash: str

    def to_json(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "episode_id": self.episode_id,
            "kind": self.kind,
            "seat": self.seat,
            "payload": self.payload,
            "t": self.t,
            "prev_hash": self.prev_hash,
            "hash": self.hash,
        }

    @staticmethod
    def from_json(d: dict[str, Any]) -> Event:
        fields = ("seq", "episode_id", "kind", "seat", "payload", "t", "prev_hash", "hash")
        return Event(**{k: d[k] for k in fields})


class EventLog:
    """In-memory log for one episode; flushed to a shared JSONL file when the episode ends."""

    def __init__(self, episode_id: str) -> None:
        self.episode_id = episode_id
        self._events: list[Event] = []

    def emit(self, kind: str, seat: str | None = None, **payload: Any) -> Event:
        prev = self._events[-1].hash if self._events else GENESIS
        t = time.time()
        body = {
            "seq": len(self._events),
            "episode_id": self.episode_id,
            "kind": kind,
            "seat": seat,
            "payload": payload,
            "t": t,
        }
        event = Event(
            seq=len(self._events),
            episode_id=self.episode_id,
            kind=kind,
            seat=seat,
            payload=payload,
            t=t,
            prev_hash=prev,
            hash=_digest(prev, body),
        )
        self._events.append(event)
        return event

    def __iter__(self) -> Iterator[Event]:
        return iter(self._events)

    def __len__(self) -> int:
        return len(self._events)

    def of_kind(self, *kinds: str) -> list[Event]:
        return [e for e in self._events if e.kind in kinds]

    @property
    def head(self) -> str:
        return self._events[-1].hash if self._events else GENESIS


def verify_chain(
    events: Iterable[Event], head: str | None = None, count: int | None = None
) -> bool:
    """Check links and hashes. Truncation or deletion is only detectable against an expected
    `head` hash and `count`, which the episode's result record stores."""
    prev = GENESIS
    n = 0
    for e in events:
        body = {
            "seq": e.seq,
            "episode_id": e.episode_id,
            "kind": e.kind,
            "seat": e.seat,
            "payload": e.payload,
            "t": e.t,
        }
        if e.seq != n or e.prev_hash != prev or e.hash != _digest(prev, body):
            return False
        prev = e.hash
        n += 1
    if head is not None and prev != head:
        return False
    return count is None or n == count


class JsonlSink:
    """Thread-safe append-only JSONL writer shared by concurrent episodes.

    Each call writes all rows of one episode in a single fsynced append, so rows of one episode
    are contiguous and a crash can only tear the final line, which readers skip.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def append_many(self, rows: Iterable[dict[str, Any]]) -> None:
        text = "".join(json.dumps(r, default=str) + "\n" for r in rows)
        if not text:
            return
        with self._lock, self.path.open("a+b") as f:
            # Never glue a record onto a line torn by an earlier crash.
            if f.tell() > 0:
                f.seek(-1, os.SEEK_END)
                if f.read(1) != b"\n":
                    text = "\n" + text
            f.write(text.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())

    def iter_rows(self) -> Iterator[dict[str, Any]]:
        """Stream rows; a torn (unparseable) line from a crash is skipped with a warning."""
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                if not line.strip():
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    log.warning("%s:%d: skipping torn line", self.path, lineno)

    def read(self) -> list[dict[str, Any]]:
        return list(self.iter_rows())
