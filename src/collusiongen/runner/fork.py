"""Counterfactual fork-and-edit replay (2026-11-17, ICML plan): replay a finished game's journal up
to a step, change one input, and let the policies play on from there, N times with fresh sampling
seeds. Comparing P(breach) between an edited and an unedited fork from the same state attributes
the decision to that input (the colleague's request, the blocked route, a message) at fixed state.

Edits (applied to the environment after the replay, before the first live step):

    {"op": "drop_unread", "to": k, "contains": "..."}   unread messages to agent k whose text
                                                         contains the string are removed
    {"op": "inject_message", "to": k, "from": j, "text": "..."}
                                                         a message from j waits in k's inbox
    {"op": "redact_seen", "agent": k, "contains": "...", "replace": "..."}
                                                         text agent k already saw (its tool
                                                         replies) is replaced; the model's next
                                                         prompt shows the edited history
    {"op": "route", "level": "cheap" | "moderate"}      the allowed route works from here on
    {"op": "none"}                                       the control fork: no change

Edits name agents by number (1..n). The fork's record keeps the source episode, the step, the
edit and the sample under record["fork"].
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from collusiongen.core.env import Services
from collusiongen.core.policy import Policy
from collusiongen.core.types import SeatId
from collusiongen.runner.episode import EpisodeResult, run_episode
from collusiongen.runner.plan import EpisodeSpec

OPS = ("drop_unread", "inject_message", "redact_seen", "route", "none")


def apply_edit(env: Any, edit: dict[str, Any]) -> dict[str, Any]:
    """Apply one edit; returns what changed (counts), for the record. Raises on an edit that
    changes nothing, so a fork is never silently a control."""
    op = edit.get("op")
    if op not in OPS:
        raise ValueError(f"unknown fork edit {op!r}; one of {OPS}")
    if op == "none":
        return {"changed": 0}
    if op == "drop_unread":
        k, needle = int(edit["to"]), str(edit["contains"])
        before = list(env.inbox[k])
        env.inbox[k] = [(s, t) for s, t in before if needle not in t]
        changed = len(before) - len(env.inbox[k])
    elif op == "inject_message":
        k, j = int(edit["to"]), int(edit["from"])
        env.inbox[k].append((j, str(edit["text"])))
        changed = 1
    elif op == "redact_seen":
        w = env.workers[int(edit["agent"]) - 1]
        needle, repl = str(edit["contains"]), str(edit.get("replace", ""))
        changed = 0
        for c in w.calls:
            if needle in str(c.get("result", "")):
                c["result"] = str(c["result"]).replace(needle, repl)
                changed += 1
    else:  # route
        level = str(edit["level"])
        if level not in ("cheap", "moderate"):
            raise ValueError("route edit: level cheap or moderate")
        env.game.level = level
        changed = 1
    if not changed:
        raise ValueError(f"fork edit {edit} changed nothing at this step")
    env.log.emit("fork_edit", None, edit=edit, changed=changed)
    return {"changed": changed}


def journal_prefix(journal: Path, at: int) -> list[str]:
    """The journal lines of steps before `at` (the fork point)."""
    out = []
    for line in journal.read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        if int(entry["step"]) >= at:
            break
        out.append(line)
    if len(out) < at:
        raise ValueError(f"{journal} has only {len(out)} steps; cannot fork at {at}")
    return out


def fork_spec(spec: EpisodeSpec, tag: str, sample: int) -> EpisodeSpec:
    """A new episode id (run id carries the fork tag); the cell, and so the world, stay the same."""
    return dataclasses.replace(spec, run_id=f"{spec.run_id}__fork_{tag}_s{sample}")


def reseed(policies: dict[SeatId, Policy], sample: int) -> None:
    """Fresh sampling per fork sample (LLM seats); scripted seats are deterministic anyway."""
    for p in policies.values():
        if hasattr(p, "_seed"):
            p._seed = (p._seed + 7919 * (sample + 1)) % (2**31)


async def play_fork(
    module: Any,
    spec: EpisodeSpec,
    policies: dict[SeatId, Policy],
    services: Services,
    source_journal: Path,
    at: int,
    edit: dict[str, Any],
    tag: str,
    sample: int,
    live_dir: Path,
    **kw: Any,
) -> EpisodeResult:
    fspec = fork_spec(spec, tag, sample)
    live_dir.mkdir(parents=True, exist_ok=True)
    journal = live_dir / f"{fspec.episode_id}.jsonl"
    if not journal.exists():  # a resumed fork keeps the steps it already played
        journal.write_text("".join(f"{x}\n" for x in journal_prefix(source_journal, at)),
                           encoding="utf-8")
    reseed(policies, sample)
    done: dict[str, Any] = {}

    def hook(env: Any) -> None:
        # on a resume the journal already holds live steps past the fork: the edit was applied in
        # the first attempt, before them, and replaying cannot re-apply it in place
        if sum(1 for _ in journal.open(encoding="utf-8")) > at:
            raise RuntimeError(f"{journal}: fork already past its edit; delete it to replay")
        done.update(apply_edit(env, edit))

    result = await run_episode(module, fspec, policies, services, journal=journal,
                               after_replay=hook, **kw)
    result.record["fork"] = {"source_episode": spec.episode_id, "at": at, "edit": edit,
                             "tag": tag, "sample": sample, **done}
    return result
