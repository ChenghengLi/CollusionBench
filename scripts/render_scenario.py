#!/usr/bin/env python
"""Render a scenario exactly as an agent sees it, as Markdown.

    python scripts/render_scenario.py card_claims                     # world 0, blocked, team
    python scripts/render_scenario.py card_bids --world 3 --level moderate --seat 2
    python scripts/render_scenario.py card_claims --solo --escalation
    python scripts/render_scenario.py --all --out-dir docs/scenarios   # one file per scenario

Shows, for one seat: the system prompt and the opening screen, the tools, every file the seat can
open (its own team's exports, the policy, the manager's email), then what the office system replies
over three calls (the outage when blocked), the manager's replies to a hand-in, and the reply to an
escalation when the factor is on. The parameters are those of the factorial (scripts/bench.py).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench import ALL_SCENARIOS, BASE, PER_GAME  # noqa: E402

from collusiongen.core.env import Services  # noqa: E402
from collusiongen.core.log import EventLog  # noqa: E402
from collusiongen.core.registry import get_module  # noqa: E402
from collusiongen.core.types import Split, Variant  # noqa: E402


def make_env(game: str, world: int, level: str, solo: bool, escalation: bool):
    m = get_module("n4_relay")
    params = {**BASE, **PER_GAME.get(game, {}), "n_agents": 3, "game": game, "route_cost": level,
              "card_condition": "mm", "card_team": "solo" if solo else "team"}
    if escalation:
        params |= {"escalation": True, "escalate_p": 0.0}
    inst = m.sample_instance(2026, Split.HELDOUT_SKIN, world, params)
    return m.make_env(inst, Variant(protocol="native_tools"), EventLog("render"), Services())


def call(env, k: int, action: dict) -> str:
    env._batch_worker = env.workers[k - 1]
    try:
        return env._run_tool(env.workers[k - 1], action)
    finally:
        env._batch_worker = None


def block(text: str) -> str:
    return "```\n" + text.rstrip() + "\n```\n"


def render(game: str, world: int = 0, level: str = "blocked", seat: int = 1, solo: bool = False,
           escalation: bool = False) -> str:
    env = make_env(game, world, level, solo, escalation)
    g = env.game
    if solo:
        seat = 2  # the model's seat in the solo form
    obs = env.observe(env._seat(env.workers[seat - 1]))
    p = g.person(seat)
    out = [f"# {game} · world {world} · {level} · {'solo' if solo else 'team'}"
           f"{' · escalate' if escalation else ''}\n",
           f"{g.org}, {g.day.text()}. Seat {seat}: {p.name} ({g.unit_of(seat).title}). Manager: {g.boss.name} "
           f"({g.boss.title}). Answer: {g.answer()}.\n",
           "## Team\n", "\n".join(f"- seat {k}: {g.person(k).name}, {g.unit_of(k).title}"
                                  for k in range(1, 4)) + "\n",
           "## System prompt\n", block(obs.system), "## Opening screen\n", block(obs.prompt),
           "## Tools\n",
           "\n".join(f"- `{t['function']['name']}`: {t['function'].get('description', '')}"
                     for t in env._tool_space().tools()) + "\n",
           "## Files this seat can open\n"]
    owners = g.owners(3)
    for path, text in sorted(g.files().items()):
        mine = owners.get(path) in (None, 0, seat) or path in g.public_files or solo
        if mine:
            out += [f"### {path}\n", block(text)]
    if g.TOOL:
        tool = g.TOOL["function"]["name"]
        out.append(f"## {tool}: three calls\n")
        for i in range(3):
            out.append(block(call(env, seat, {"tool": tool, "action": "status"})))
    if escalation:
        out += ["## Escalation\n", block(call(env, seat, {"tool": "escalate",
                                                         "reason": "the office system is down"}))]
    out.append("## Manager's replies to a hand-in\n")
    for outcome in ("correct", "retry", "final", "missing", *(["open"] if escalation else [])):
        out += [f"**{outcome}**\n", block(g.handin_reply(seat, g.request_email(seat)[0], outcome))]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("game", nargs="?")
    ap.add_argument("--world", type=int, default=0)
    ap.add_argument("--level", default="blocked", choices=("cheap", "moderate", "blocked"))
    ap.add_argument("--seat", type=int, default=1, choices=(1, 2, 3))
    ap.add_argument("--solo", action="store_true")
    ap.add_argument("--escalation", action="store_true")
    ap.add_argument("--all", action="store_true", help="every scenario of the factorial")
    ap.add_argument("--out-dir", help="write <game>.md files here instead of printing")
    a = ap.parse_args()
    games = ALL_SCENARIOS if a.all else [a.game]
    if not games[0]:
        ap.error("name a game or pass --all")
    for game in games:
        text = render(game, a.world, a.level, a.seat, a.solo, a.escalation)
        if a.out_dir:
            path = Path(a.out_dir) / f"{game}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            print(path)
        else:
            print(text)


if __name__ == "__main__":
    main()
