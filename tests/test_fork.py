"""Counterfactual fork-and-edit replay (runner/fork.py), on scripted card games."""

import asyncio
import json

import pytest
from collusiongen.core.env import Services
from collusiongen.core.types import Condition
from collusiongen.runner.episode import run_episode
from collusiongen.runner.fork import apply_edit, journal_prefix, play_fork
from collusiongen.runner.plan import EpisodeSpec
from tests.test_cards import _inst

V2 = {"report_phase": False}


def _source(tmp_path, game="card_records", level="blocked", cond=Condition.HH, **kw):
    m, inst = _inst(game, level, **V2, **kw)
    kinds = {"H": "honest", "O": "oracle"}
    pol = lambda: {"A": getattr(m, kinds[cond.value[0]])(inst, "A"),  # noqa: E731
                   "B": getattr(m, kinds[cond.value[1]])(inst, "B")}
    spec = EpisodeSpec("t", "scripted", "n4_relay", inst, 0, 0, cond, True)
    journal = tmp_path / "live" / f"{spec.episode_id}.jsonl"
    rec = asyncio.run(run_episode(m, spec, pol(), Services(), max_steps=3000, journal=journal)).record
    return m, spec, pol, journal, rec


def _fork(tmp_path, m, spec, pol, journal, at, edit, tag, sample=0):
    return asyncio.run(play_fork(m, spec, pol(), Services(), journal, at, edit, tag, sample,
                                 tmp_path / "forks", max_steps=3000)).record


def test_a_control_fork_replays_the_source_outcome(tmp_path):
    m, spec, pol, journal, rec = _source(tmp_path)
    fork = _fork(tmp_path, m, spec, pol, journal, 6, {"op": "none"}, "control")
    assert fork["secondary"]["card_solved"] == rec["secondary"]["card_solved"] == 0.0
    assert fork["fork"]["source_episode"] == spec.episode_id and fork["fork"]["at"] == 6
    assert fork["episode_id"] != rec["episode_id"]


def test_restoring_the_route_at_the_fork_lets_the_honest_team_solve(tmp_path):
    m, spec, pol, journal, rec = _source(tmp_path)
    fork = _fork(tmp_path, m, spec, pol, journal, 6, {"op": "route", "level": "cheap"}, "route")
    assert rec["secondary"]["card_solved"] == 0.0 and fork["secondary"]["card_solved"] == 1.0
    assert fork["secondary"]["card_breach"] == 0.0


def test_journal_prefix_stops_at_the_fork_point(tmp_path):
    *_, journal, _ = _source(tmp_path)
    lines = journal_prefix(journal, 10)
    assert len(lines) == 10 and json.loads(lines[-1])["step"] == 9
    with pytest.raises(ValueError):
        journal_prefix(journal, 10**6)


def test_edits_change_inbox_and_history_and_refuse_a_no_op():
    from tests.test_office import _as, _env

    env = _env("card_records")
    _as(env, 1, {"tool": "send_message", "to": "billing", "text": "please send the credit amounts"})
    b = env.game.seat_of("billing")
    assert apply_edit(env, {"op": "drop_unread", "to": b, "contains": "credit amounts"})["changed"] == 1
    assert not env.inbox[b]
    apply_edit(env, {"op": "inject_message", "to": b, "from": 1, "text": "hello"})
    assert env.inbox[b][-1] == (1, "hello")
    reply = _as(env, 1, {"tool": "read", "path": "/tmp/assignment.txt"})
    env.workers[0].calls.append({"call": {"tool": "read", "path": "/tmp/assignment.txt"}, "result": reply})
    apply_edit(env, {"op": "redact_seen", "agent": 1, "contains": "Records Office", "replace": "office"})
    assert "Records Office" not in env.workers[0].calls[-1]["result"]
    with pytest.raises(ValueError):
        apply_edit(env, {"op": "drop_unread", "to": b, "contains": "nothing like this"})
    with pytest.raises(ValueError):
        apply_edit(env, {"op": "teleport"})
