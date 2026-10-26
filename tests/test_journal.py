"""Live journal: every step is saved as it happens, and an interrupted game resumes from its
journal without asking the policies again for steps already played."""

import json

import pytest

from collusiongen.core.env import Services
from collusiongen.core.policy import Decision
from collusiongen.core.registry import get_module
from collusiongen.core.types import Condition, PolicyKind
from collusiongen.runner.episode import run_episode
from collusiongen.runner.plan import EpisodeSpec
from tests.conftest import small_instance


class Counting:
    """Prices at 1.4 x cost; raises after `crash_after` decisions to simulate a crash."""

    name, kind = "counting", PolicyKind.MODEL

    def __init__(self, crash_after: int | None = None) -> None:
        self.calls = 0
        self.crash_after = crash_after

    async def act(self, obs):
        if self.crash_after is not None and self.calls >= self.crash_after:
            raise RuntimeError("simulated preemption")
        self.calls += 1
        return Decision({"price": obs.action_space.cost * (1.3 + 0.01 * (self.calls % 7))})


async def _run(mid, inst, policies, journal):
    spec = EpisodeSpec("t", "m", mid, inst, 0, 0, Condition.MM, True)
    return await run_episode(get_module(mid), spec, policies, Services(), journal=journal)


@pytest.mark.parametrize("mid", ["a1_pricing", "h1_hub"])
async def test_interrupted_game_resumes_from_its_journal(tmp_path, mid):
    m = get_module(mid)
    inst = small_instance(m, horizon=10)
    # Reference: the same game played straight through.
    ref = await _run(mid, inst, {"A": Counting(), "B": Counting()}, tmp_path / "ref.jsonl")
    # Interrupted after 7 decisions per seat, then resumed with fresh policies.
    journal = tmp_path / "game.jsonl"
    with pytest.raises(RuntimeError):
        await _run(mid, inst, {"A": Counting(7), "B": Counting(7)}, journal)
    assert len(journal.read_text().splitlines()) == 14  # every step was saved as it happened
    a, b = Counting(), Counting()
    a.calls = b.calls = 7  # same per-seat sequence as the uninterrupted game
    res = await _run(mid, inst, {"A": a, "B": b}, journal)
    assert a.calls + b.calls == 2 * 10  # only the 6 missing rounds were asked again
    assert res.record["victim_loss"] == pytest.approx(ref.record["victim_loss"])
    assert res.record["steps"] == ref.record["steps"]
    assert sum(t.get("replayed", False) for t in res.transcript) == 14
    assert len(journal.read_text().splitlines()) == 20


async def test_torn_last_line_is_dropped(tmp_path):
    m = get_module("a1_pricing")
    inst = small_instance(m, horizon=4)
    journal = tmp_path / "game.jsonl"
    with pytest.raises(RuntimeError):
        await _run("a1_pricing", inst, {"A": Counting(2), "B": Counting(2)}, journal)
    with journal.open("a") as f:
        f.write('{"seat": "A", "applied": {"pri')  # crash in the middle of a write
    res = await _run("a1_pricing", inst, {"A": Counting(), "B": Counting()}, journal)
    assert res.record["steps"] == 8
    assert all(json.loads(line) for line in journal.read_text().splitlines())


async def test_n4_tool_game_resumes_from_its_journal(tmp_path):
    m = get_module("n4_relay")
    inst = small_instance(m, final_submit=True, monitor="logs")

    class Crashing:
        """Delegates to the pooling oracle script; raises after `limit` decisions."""

        name, kind = "crashing", PolicyKind.MODEL

        def __init__(self, limit=None):
            self.inner, self.limit, self.calls = m.oracle(inst, "A"), limit, 0

        async def act(self, obs):
            if self.limit is not None and self.calls >= self.limit:
                raise RuntimeError("simulated preemption")
            self.calls += 1
            return await self.inner.act(obs)

    ref = await _run("n4_relay", inst, {"A": Crashing(), "B": Crashing()}, tmp_path / "r.jsonl")
    journal = tmp_path / "n4.jsonl"
    with pytest.raises(RuntimeError):
        await _run("n4_relay", inst, {"A": Crashing(5), "B": Crashing(5)}, journal)
    res = await _run("n4_relay", inst, {"A": Crashing(), "B": Crashing()}, journal)
    assert res.record["victim_loss"] == pytest.approx(ref.record["victim_loss"])
    assert res.record["secondary"] == pytest.approx(ref.record["secondary"])


@pytest.mark.parametrize("cut", [3, 8, 13])
async def test_team_game_with_forum_and_messages_resumes_exactly(tmp_path, cut):
    """A preempted team game (forum, capped direct messages, .info files, stop at the first
    correct answer) resumes from its journal and ends exactly as the uninterrupted game."""
    from collusiongen.modules.n4_relay.team import partition

    m = get_module("n4_relay")
    inst = small_instance(
        m,
        n_agents=3,
        mode="team",
        files_per_worker=2,
        max_tool_calls=30,
        final_submit=True,
        monitor="logs",
        audit_rate=0.5,
        hide_others=True,
        submit_attempts=10,
        rule_style="personal",
        folder_info=True,
        stop_on_correct=True,
        forum=True,
        messaging=True,
        dm_broadcast=False,
        max_messages=2,
    )
    owner = partition(inst)

    class Chatty:
        """Sums its files, posts and messages them, reads the forum, then submits the total
        it can build from what it read; raises after `limit` decisions (a preemption)."""

        name, kind = "chatty", PolicyKind.MODEL

        def __init__(self, limit=None):
            self.limit, self.calls = limit, 0

        async def act(self, obs):
            if self.limit is not None and self.calls >= self.limit:
                raise RuntimeError("simulated preemption")
            self.calls += 1
            k, calls = obs.state["agent"], obs.state["calls"]
            own = sorted(f for f, o in owner.items() if o == k)
            done = {c["call"].get("path") for c in calls if c["call"]["tool"] == "sum_column"}
            todo = [f for f in own if f not in done]
            if todo:
                return Decision({"tool": "sum_column", "path": todo[0]})
            mine = sum(float(c["result"]) for c in calls if c["call"]["tool"] == "sum_column")
            n = len(calls) - len(own)
            plan = [
                {"tool": "forum_post", "title": f"a{k}", "text": f"sum={int(mine)}"},
                {"tool": "send_message", "to": str(k % 3 + 1), "text": f"{int(mine)}"},
                {"tool": "wait"},
                {"tool": "forum_read"},
                {"tool": "read_messages"},
            ]
            if n < len(plan):
                return Decision(plan[n])
            page = next(c["result"] for c in reversed(calls) if c["call"]["tool"] == "forum_read")
            sums = [int(x) for x in __import__("re").findall(r"sum=(\d+)", page)]
            return Decision({"tool": "submit", "answer": str(sum(sums) or int(mine))})

    def seats(limit=None):
        return {"A": Chatty(limit), "B": Chatty(limit)}

    ref = await _run("n4_relay", inst, seats(), tmp_path / "ref.jsonl")
    journal = tmp_path / "team.jsonl"
    with pytest.raises(RuntimeError):
        await _run("n4_relay", inst, seats(cut), journal)
    res = await _run("n4_relay", inst, seats(), journal)
    assert res.record["victim_loss"] == pytest.approx(ref.record["victim_loss"])
    assert res.record["secondary"] == pytest.approx(ref.record["secondary"])
    assert res.record["secondary"]["forum_posts"] >= 1
    assert [(e.kind, e.payload) for e in res.events] == [(e.kind, e.payload) for e in ref.events]
