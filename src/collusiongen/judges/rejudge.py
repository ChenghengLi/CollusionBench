"""Re-judge every board message of a finished run with the LLM judge alone.

The two-stage judge only shows the LLM the messages its keyword filter flags, and that filter
misses wordings it was not built on ("as agreed", "no undercutting", "cooperation"). This pass
sends every non-empty message to the LLM judge, writes one verdict per message to
`<run_dir>/<model>/rejudged.jsonl` (the original results and events are never changed), and
summarises the corrected agreement rate per game.
"""

from __future__ import annotations

import asyncio
import collections
import json
from pathlib import Path
from typing import Any

from collusiongen.judges.messages import LLMJudge
from collusiongen.runner.config import JudgeConfig, RunConfig, safe_name
from collusiongen.runner.policies import make_backend


def _messages(mdir: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    results = {}
    for line in (mdir / "results.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r["module"] == "n2_market":
            results[r["episode_id"]] = r
    msgs = []
    for line in (mdir / "events.jsonl").read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        r = results.get(e["episode_id"])
        if r is None or e.get("attempt") != r.get("attempt") or e["kind"] != "message":
            continue
        text = (e["payload"].get("text") or "").strip()
        if text:
            msgs.append(
                {
                    "episode_id": e["episode_id"],
                    "round": e["payload"]["round"],
                    "seat": e["seat"],
                    "text": text,
                    "product": r["skin_id"],
                }
            )
    return msgs, results


async def rejudge_run(run_dir: Path, judge_cfg: JudgeConfig, concurrency: int = 50) -> str:
    config = RunConfig.model_validate_json((run_dir / "config.json").read_text())
    if judge_cfg.backend is None:
        raise ValueError("re-judging needs an LLM judge backend")
    backend = make_backend(judge_cfg.backend)
    assert backend is not None
    judge = LLMJudge(backend, extra_body=judge_cfg.extra_body)
    sem = asyncio.Semaphore(concurrency)
    lines = [f"# Re-judged board messages: {config.run_id}", ""]
    try:
        for model in config.models:
            mdir = run_dir / safe_name(model.name)
            out = mdir / "rejudged.jsonl"
            done = set()
            if out.exists():  # resumable: skip messages already re-judged
                for line in out.read_text(encoding="utf-8").splitlines():
                    d = json.loads(line)
                    done.add((d["episode_id"], d["round"], d["seat"]))
            msgs, results = _messages(mdir)
            todo = [m for m in msgs if (m["episode_id"], m["round"], m["seat"]) not in done]

            async def one(m: dict[str, Any], sink: Any) -> None:
                async with sem:
                    v = await judge.judge(m["text"], context="market")
                sink.write(
                    json.dumps(
                        {**m, "agreement": v.agreement, "judge": v.judge, "rationale": v.rationale}
                    )
                    + "\n"
                )
                sink.flush()

            with out.open("a", encoding="utf-8") as sink:
                await asyncio.gather(*(one(m, sink) for m in todo))

            verdicts = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()]
            per: dict[str, list[bool]] = collections.defaultdict(list)
            for d in verdicts:
                per[d["episode_id"]].append(bool(d["agreement"]))
            lines += [
                f"## {model.name}",
                "",
                f"Messages re-judged: {len(verdicts)}",
                "",
                "| Setting | Line-up | Messages | Agreements (LLM) | Flagged in the run |",
                "| --- | --- | --- | --- | --- |",
            ]
            for eid, r in sorted(
                results.items(), key=lambda kv: (kv[1]["variant"], kv[1]["condition"])
            ):
                if eid not in per:
                    continue
                v = per[eid]
                old = (
                    r["secondary"].get("agreement_rate", 0.0)
                    * len(r["params"].get("cost", []))
                    * r["params"]["horizon"]
                )
                lines.append(
                    f"| {r['variant']} | {r['condition']} | {len(v)} | {sum(v) / len(v):.0%} | "
                    f"{old / max(1, len(v)):.0%} |"
                )
            lines.append("")
    finally:
        await backend.aclose()
    return "\n".join(lines)
