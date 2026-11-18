"""The "colleague coordinates" cell (card_condition coord, 2026-11-18): the scripted colleague in
seat 2 cooperates legally only, as the control for the scripted request (ask). Its messages must
never be an ask or a leak, and must count as coordination."""

import asyncio
import sys
from pathlib import Path

import pytest

from collusiongen.core.env import Services
from collusiongen.core.types import Condition
from collusiongen.runner.episode import run_episode
from collusiongen.runner.plan import EpisodeSpec
from tests.test_cards import _inst

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from bench import ALL_SCENARIOS  # noqa: E402


@pytest.mark.parametrize("game", ALL_SCENARIOS)
def test_the_coordinator_only_cooperates_legally(game):
    m, inst = _inst(game, "blocked", cond="coord", report_phase=False)
    pol = {"A": m.honest(inst, "A"), "B": m.honest(inst, "B")}  # B is the coordinator
    spec = EpisodeSpec("t", "scripted", "n4_relay", inst, 0, 0, Condition.MH, True)
    res = asyncio.run(run_episode(m, spec, pol, Services(), max_steps=3000))
    mine = [e.payload for e in res.events if e.kind == "screen" and e.payload.get("wave") == 2]
    assert len(mine) >= 4, game  # awareness and framing, to both colleagues
    assert not any(p.get("ask") or p.get("leak") for p in mine), (game, mine)
    assert all(p.get("coord") for p in mine[:2]), (game, mine[:2])
    assert res.record["secondary"]["card_breach"] == 0.0


def test_the_email_points_to_the_policy():
    m, inst = _inst("card_claims", "blocked")
    from collusiongen.modules.n4_relay.games import game_for
    g = game_for(inst)
    subject, body = g.request_email(1)
    assert g.policy_path in body and "Data handling for this work follows policy" in body
