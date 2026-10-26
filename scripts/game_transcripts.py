"""Readable transcripts of N4 games (running or finished), one markdown file per game.

usage: .venv/bin/python scripts/game_transcripts.py <setup> <model profile or cross:tag>:<scenario> [...]
Writes runs/transcripts_readable/<setup>/<model>_<scenario>_<setting>.md and prints a short digest
of everything said on the channels in each game.
"""

import glob
import json
import os
import re
import sys

import yaml

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")
from audit_paths import config_path  # noqa: E402
from audit_progress import SETTING  # noqa: E402
from collusiongen.modules.n4_relay.games import game_for  # noqa: E402
from collusiongen.runner.config import RunConfig  # noqa: E402
from collusiongen.runner.plan import expand  # noqa: E402
from collusiongen.core.env import Services  # noqa: E402
from collusiongen.core.log import EventLog  # noqa: E402
from collusiongen.core.registry import get_module  # noqa: E402
from collusiongen.runner.episode import make_variant  # noqa: E402
import asyncio  # noqa: E402


async def replay(spec, steps):
    """Replay the logged calls in a fresh copy of the game: who acted at each step, and the reply
    each call got (the live log keeps neither for single-company games)."""
    module = get_module(spec.module_id)
    env = module.make_env(spec.instance, make_variant(module, spec), EventLog(spec.episode_id), Services())
    agents, replies = [], []
    for d in steps:
        seat = env.next_seat()
        if seat is None:
            break
        k = env.observe(seat).state["agent"]
        calls = env.workers[k - 1].calls
        before = len(calls)
        if d.get("applied_batch"):
            await env.apply_batch(seat, d["applied_batch"])
        else:
            await env.apply(seat, d["applied"], substituted=bool(d.get("substituted")))
        agents.append(k)
        new = calls[before:]  # the reply to this step's call (the first, for a batch)
        replies.append(str(new[0].get("result", "")) if new else "")
    return agents, replies

CHANNEL = ("send_message", "forum_post", "forum_reply", "submit")


def who(d, g, cross_models):
    """Best guess of the acting agent: the company in the role line (cross-company games); in
    cross-model games also the model."""
    m = re.match(r"You are an employee at (.+?), which takes part", d.get("system") or "")
    name = m.group(1) if m else None
    k = next((i + 1 for i, u in enumerate(g.RING[: g.n]) if u.name == name), None)
    label = f"agent {k} ({name})" if k else f"seat {d.get('seat')}"
    if cross_models and k:
        label += f" [{cross_models.get(str(k), '?')}]"
    return label


def main(setup, pairs):
    outdir = f"runs/transcripts_readable/{setup}"
    os.makedirs(outdir, exist_ok=True)
    for pair in pairs:
        model, sc = pair.rsplit(":", 1)
        cross = model.startswith("cross")
        lead = "deepseek-v4.1-flash-baidu" if cross else model
        cfg = RunConfig.model_validate(yaml.safe_load(open(config_path(lead, sc, setup))))
        specs = {s.episode_id: s for s in expand(cfg, cfg.models[0]) if s.condition.value == "MM"}
        tag = model.split(":", 1)[1] if cross else model
        live = glob.glob(f"runs/api/cross_{tag}_{sc}_v1_{setup}/*/live") if cross else \
            glob.glob(f"runs/**/{cfg.run_id}/*/live", recursive=True)
        if not live:
            continue
        cross_models = json.load(open(f"runs/api/cross_{tag}_manifest.json"))["agent_models"] if cross else {}
        for eid, spec in specs.items():
            p = spec.instance.params
            st = SETTING.get((bool(p.get("forum")), bool(p.get("messaging", True)), p.get("max_messages")))
            g = game_for(spec.instance)
            try:
                steps = [json.loads(l) for l in open(f"{live[0]}/{eid}.jsonl").read().splitlines()]
            except FileNotFoundError:
                continue
            name = f"{'cross-' + tag if cross else model}_{sc[7:]}_{st}"
            lines = [f"# {name}", "", f"Game {eid} · {g.n} agents · {len(steps)} calls · correct answer {g.questions[0].answer}",
                     "", "Agents: " + "; ".join(f"{i + 1} = {u.name}" + (f" [{cross_models.get(str(i + 1))}]" if cross else "")
                                                for i, u in enumerate(g.RING[: g.n])), ""]
            digest = []
            try:
                agents, replies = asyncio.run(replay(spec, steps))
            except Exception as exc:  # keep the transcript even if the replay fails
                print(f"  (replay failed: {exc!r})")
                agents, replies = [], []
            units = list(g.RING[: g.n])
            for i, d in enumerate(steps):
                a = d["applied"] if isinstance(d["applied"], dict) else {}
                t = a.get("tool", "?")
                arg = a.get("path") or a.get("to") or a.get("post") or ""
                text = (str(a.get("title") or "") + " " + str(a.get("text") or a.get("content") or "")).strip()
                reason = (d.get("reasoning") or "").replace("\n", " ").strip()
                if i < len(agents):
                    k = agents[i]
                    speaker = f"agent {k} ({units[k - 1].name})" + (f" [{cross_models.get(str(k), '?')}]" if cross else "")
                else:
                    speaker = who(d, g, cross_models)
                lines.append(f"**{d['step']}** · {speaker} · `{t}` {arg}")
                if text:
                    lines.append(f"> {text[:1500]}")
                if i < len(replies) and replies[i]:
                    lines.append(f"  ↳ {replies[i][:300].replace(chr(10), ' ')}")
                if reason:
                    lines.append(f"  _thinking:_ {reason[-400:]}")
                if t in CHANNEL[:3] or (t in ("write", "append") and str(arg).startswith("/workspace")):
                    digest.append(f"  [{d['step']}] {speaker} {t} {arg}: {text[:260]}")
                if t == "submit" and i < len(replies):
                    digest.append(f"  [{d['step']}] {speaker} submit -> {replies[i][:120]}")
            open(f"{outdir}/{name}.md", "w").write("\n".join(lines) + "\n")
            print(f"\n== {name}: {len(steps)} calls, {len(digest)} items on channels")
            for x in digest[:10]:
                print(x.replace("\n", " "))
            if len(digest) > 10:
                print(f"  ... {len(digest) - 10} more (see {outdir}/{name}.md)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
