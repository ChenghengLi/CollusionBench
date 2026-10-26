"""When a one-question-per-agent game ends (per_agent_questions), played through the episode runner:
it stops as soon as every agent is correct; otherwise it runs until every agent's tool calls are
spent, with correct agents still active (they can help) and wrong ones still active too."""

from collusiongen.core.policy import ScriptedPolicy
from collusiongen.core.registry import get_module
from collusiongen.core.types import Condition
from tests import audit_checks as ac
from tests.conftest import play, small_instance

BUDGET = 8


class Script(ScriptedPolicy):
    """`plan[k]`: what agent k does: "right" (submit the right answer, then wait), "wrong" (submit
    a wrong answer until refused, then wait) or "idle" (only wait). Records what each agent saw."""

    def __init__(self, game, plan, seen):
        self.game, self.plan, self.seen = game, plan, seen

    def decide(self, obs):
        k, calls = obs.state["agent"], obs.state["calls"]
        self.seen[k] = calls
        mode = self.plan[k]
        if mode == "idle" or (mode == "right" and any(c["call"]["tool"] == "submit" for c in calls)):
            return {"tool": "wait"}
        answer = self.game.questions[k - 1].answer if mode == "right" else "nothing"
        if not calls or calls[-1]["call"]["tool"] == "submit":
            return {"tool": "write", "path": "/tmp/answers.csv",
                    "content": f"question,answer\nQ1,{answer}\n"}
        return {"tool": "submit", "path": "/tmp/answers.csv"}


async def _run(plan, game="audit_school", n=3, budget=BUDGET):
    inst = small_instance(get_module("n4_relay"), n_agents=n, game=game,
                          records_budget=budget, **ac.BASE)
    from collusiongen.modules.n4_relay.games import game_for

    seen: dict[int, list] = {}
    pol = Script(game_for(inst), plan, seen)
    out = await play("n4_relay", Condition.MM, inst,
                     policies={s: pol for s in get_module("n4_relay").seats(inst)})
    return out, seen


async def test_stops_once_every_agent_is_correct():
    out, seen = await _run({1: "right", 2: "right", 3: "right"}, budget=60)
    assert out["secondary"]["all_correct"] == 1.0 and out["secondary"]["score_mean"] == 1.0
    # agents take turns, so an early finisher waits a little; the game still ends right after
    # the last correct answer, long before the 60-call budget
    assert all(len(c) < 15 for c in seen.values())
    assert any(c["call"]["tool"] == "submit" for c in seen[2])


async def test_runs_until_calls_run_out_and_correct_agents_stay():
    out, seen = await _run({1: "right", 2: "idle", 3: "wrong"})
    assert out["secondary"]["all_correct"] == 0.0
    assert abs(out["secondary"]["score_mean"] - 1 / 3) < 1e-9
    replies = [c["result"] for c in seen[1] if c["call"]["tool"] == "submit"]
    assert replies[0].startswith("correct") and "session stays open" in replies[0]
    assert len(seen[1]) >= BUDGET - 1  # the correct agent kept going until its calls ran out
    wrong = [c["result"] for c in seen[3] if c["call"]["tool"] == "submit"]
    assert wrong[:3] == [f"incorrect (submission {i} of 3)" for i in (1, 2, 3)]
    assert "no submissions left" in wrong[3]  # out of submissions, but still in the game
    assert len(seen[2]) >= BUDGET - 1


async def test_late_correct_answer_ends_the_game_for_everyone():
    out, seen = await _run({1: "right", 2: "right", 3: "idle"}, game="audit_supply")
    assert out["secondary"]["all_correct"] == 0.0  # agent 3 never answered: game ran to the end
    assert abs(out["secondary"]["score_mean"] - 2 / 3) < 1e-9
