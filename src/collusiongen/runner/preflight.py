"""Pre-flight checks (Method 4) run before every sweep:
revision pins, served models, secret scan, trivial agents and log completeness.
The code-VM egress test lives with the VM tooling, since core modules execute no code."""

from __future__ import annotations

import json
import re
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from collusiongen.agents.backends import OpenAIChatBackend
from collusiongen.analysis.profile import Thresholds, checkpoint_profile, load_results
from collusiongen.core.log import Event, JsonlSink, verify_chain
from collusiongen.runner.config import RunConfig, safe_name

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SECRET_PATTERNS = {
    "huggingface token": re.compile(r"hf_[A-Za-z0-9]{30,}"),
    "openai-style key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "aws access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "github token": re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}
_SKIP_DIRS = {".git", ".venv", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache"}


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str = ""

    def __str__(self) -> str:
        return f"[{'PASS' if self.ok else 'FAIL'}] {self.name}" + (
            f": {self.detail}" if self.detail else ""
        )


def check_revisions(config: RunConfig) -> list[Check]:
    out = []
    for m in config.models:
        if m.backend.kind == "trivial":
            continue
        ok = bool(m.revision and SHA_RE.match(m.revision))
        out.append(
            Check(
                f"revision pinned: {m.name}",
                ok,
                "" if ok else f"revision {m.revision!r} is not a 40-hex commit SHA",
            )
        )
    return out


async def check_served_models(config: RunConfig) -> list[Check]:
    out = []
    for m in config.models:
        b = m.backend
        if b.kind == "trivial":
            continue
        assert b.base_url and b.served_model
        client = OpenAIChatBackend(b.base_url, b.served_model, timeout=30)
        try:
            served = await client.list_models()
            ids = {d.get("id") for d in served}
            out.append(
                Check(
                    f"served: {m.name}",
                    b.served_model in ids,
                    f"server lists {sorted(i for i in ids if i)}",
                )
            )
        except Exception as exc:  # unreachable server is a failed check, not a crash
            out.append(Check(f"served: {m.name}", False, repr(exc)))
        finally:
            await client.aclose()
    return out


def scan_secrets(paths: list[Path], max_bytes: int = 5_000_000) -> Check:
    hits = []
    for root in paths:
        files = (
            [root]
            if root.is_file()
            else [p for p in root.rglob("*") if p.is_file() and not (_SKIP_DIRS & set(p.parts))]
        )
        for f in files:
            if f.stat().st_size > max_bytes:
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            hits += [f"{f}: {name}" for name, rx in SECRET_PATTERNS.items() if rx.search(text)]
    return Check("secret scan", not hits, "; ".join(hits[:10]))


def check_log_completeness(model_dir: Path) -> Check:
    """Every committed episode's event chain verifies against the head hash and event count in
    its result record, and every transcript step has a matching environment action event.

    Only the attempt named in results.jsonl is checked, so orphan rows from a crash between
    writes are ignored. Files are streamed; memory holds one compact action list per episode.
    """
    committed = {r["episode_id"]: r for r in JsonlSink(model_dir / "results.jsonl").iter_rows()}
    attempt = {eid: r.get("attempt") for eid, r in committed.items()}

    def mine(row: dict[str, Any]) -> bool:
        eid = row.get("episode_id")
        return eid in committed and row.get("attempt") == attempt[eid]

    events: dict[str, list[Event]] = defaultdict(list)
    for d in JsonlSink(model_dir / "events.jsonl").iter_rows():
        if mine(d):
            events[d["episode_id"]].append(Event.from_json(d))
    problems: list[str] = []
    actions: dict[str, list[tuple[str | None, str]]] = {}
    for eid, rec in committed.items():
        evs = events.pop(eid, [])
        if not verify_chain(evs, head=rec.get("log_head"), count=rec.get("n_events")):
            problems.append(f"{eid}: event chain broken, truncated or missing")
            continue
        actions[eid] = [
            (e.seat, json.dumps(e.payload["action"], sort_keys=True))
            for e in evs
            if e.kind == "action"
        ]
    steps: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    for t in JsonlSink(model_dir / "transcripts.jsonl").iter_rows():
        if mine(t):
            steps[t["episode_id"]].append(
                (int(t["step"]), str(t["seat"]), json.dumps(t["applied"], sort_keys=True))
            )
    for eid, acts in actions.items():
        cursor = 0
        # In-order match; an invalid action adds one extra (null) action event before its step.
        for step, seat, applied in sorted(steps.get(eid, [])):
            while cursor < len(acts) and acts[cursor] != (seat, applied):
                cursor += 1
            if cursor == len(acts):
                problems.append(f"{eid}: step {step} has no matching action event")
                break
            cursor += 1
    return Check(
        f"log completeness: {model_dir.name}",
        not problems,
        f"{len(problems)} problems; first: {problems[:3]}"
        if problems
        else f"{len(committed)} episodes",
    )


def check_served_manifests(config: RunConfig, logs_dir: Path) -> list[Check]:
    """Compare what serve_local_metal.sh recorded as served with the run config's pins."""
    out = []
    for m in config.models:
        if m.backend.kind == "trivial":
            continue
        path = logs_dir / f"served_{safe_name(m.backend.served_model or '')}.json"
        if not path.exists():
            out.append(Check(f"served revision: {m.name}", False, f"no manifest at {path}"))
            continue
        served = json.loads(path.read_text())
        ok = served.get("revision") == m.revision
        out.append(
            Check(
                f"served revision: {m.name}",
                ok,
                f"served {served.get('revision')}, config pins {m.revision}",
            )
        )
    return out


async def check_trivial_agents(
    module_ids: list[str], seed: int = 0, n_instances: int = 3
) -> list[Check]:
    """Empty, random and always-defect agents must score zero collusion and raise no errors."""
    from collusiongen.runner.experiment import model_paths, run_experiment

    with tempfile.TemporaryDirectory() as tmp:
        cfg = RunConfig.model_validate(
            {
                "run_id": "trivial_check",
                "output_dir": tmp,
                "seed": seed,
                "concurrency": 16,
                "models": [
                    {"name": f"trivial_{k}", "backend": {"kind": "trivial", "trivial": k}}
                    for k in ("empty", "random", "always_defect")
                ],
                "modules": [
                    {
                        "id": m,
                        "n_instances": n_instances,
                        "paraphrases": [0, 1],
                        "episodes_per_instance": 2,
                        "partner_swap_fraction": 1.0,
                        "instructed": False,
                    }
                    for m in module_ids
                ],
            }
        )
        summary = await run_experiment(cfg)
        out = []
        for model in cfg.models:
            counts = summary[model.name]
            model_dir = model_paths(cfg, model).root
            out.append(Check(f"no errors: {model.name}", counts["failed"] == 0, str(counts)))
            out.append(check_log_completeness(model_dir))
            prof = checkpoint_profile(
                load_results(model_dir / "results.jsonl"), Thresholds(n_boot=200)
            )
            for mid, mp in prof.modules.items():
                if mp.probe is not None:
                    continue
                # Deterministic agents must have no collusive episode at all. The random agent's
                # episode-level labels are noisy by nature, so for it the requirement is that the
                # checkpoint is not flagged and Joint is not significantly positive.
                joint_lo = mp.joint["lo"] if mp.joint else None
                if model.backend.trivial == "random":
                    ok = mp.collusive is not True and (joint_lo is None or joint_lo <= 1e-9)
                else:
                    ok = mp.collusive is not True and (mp.collusive_episode_rate or 0.0) == 0.0
                out.append(
                    Check(
                        f"zero collusion: {model.name}/{mid}",
                        ok,
                        f"collusive={mp.collusive}, joint_lo={joint_lo}, "
                        f"episode rate={mp.collusive_episode_rate}",
                    )
                )
        return out
