"""Run a whole config: every model x every episode spec, concurrently, resumable.

Output layout (one directory per model):
    <run_dir>/config.json, manifest.json
    <run_dir>/<model>/results.jsonl      one record per finished episode (written last)
    <run_dir>/<model>/events.jsonl       hash-chained environment events
    <run_dir>/<model>/transcripts.jsonl  policy outputs
    <run_dir>/<model>/errors.jsonl       episodes that crashed or timed out (retried on resume)

Every execution of an episode gets a fresh `attempt` id that is stamped on its events,
transcript rows and result. A crash between writes leaves orphan rows of an attempt that has no
result; readers keep only the attempt named in results.jsonl.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import subprocess
import time
import traceback
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from collusiongen.agents.backends import ChatBackend
from collusiongen.core.env import Services
from collusiongen.core.log import JsonlSink
from collusiongen.core.registry import get_module
from collusiongen.judges.messages import KeywordJudge, LLMJudge, MessageJudge, TwoStageJudge
from collusiongen.runner.config import JudgeConfig, ModelConfig, RunConfig, safe_name
from collusiongen.runner.episode import run_episode
from collusiongen.runner.plan import EpisodeSpec, expand
from collusiongen.runner.policies import PolicyFactory, make_backend

log = logging.getLogger("collusiongen")


class ConfigMismatchError(RuntimeError):
    pass


@dataclass
class ModelPaths:
    root: Path

    @property
    def results(self) -> Path:
        return self.root / "results.jsonl"

    @property
    def events(self) -> Path:
        return self.root / "events.jsonl"

    @property
    def transcripts(self) -> Path:
        return self.root / "transcripts.jsonl"

    @property
    def errors(self) -> Path:
        return self.root / "errors.jsonl"


def model_paths(config: RunConfig, model: ModelConfig) -> ModelPaths:
    return ModelPaths(config.run_dir / safe_name(model.name))


def make_services(cfg: JudgeConfig) -> tuple[Services, ChatBackend | None]:
    if cfg.kind == "keyword":
        return Services(judge=KeywordJudge()), None
    if cfg.backend is None:
        raise ValueError(f"judge kind {cfg.kind} needs a backend")
    backend = make_backend(cfg.backend)
    assert backend is not None
    judge: MessageJudge = LLMJudge(backend, extra_body=cfg.extra_body)
    if cfg.kind == "two_stage":
        judge = TwoStageJudge(KeywordJudge(), judge)
    return Services(judge=judge), backend


def _git_commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).parent,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def check_ready(config: RunConfig) -> None:
    """Fail before the first episode, not on every episode, for misconfiguration."""
    for mcfg in config.modules:
        if mcfg.instructed:
            get_module(mcfg.id).instructed_prefix()  # raises with a clear message if missing
    backends = [m.backend for m in config.models] + (
        [config.judge.backend] if config.judge.backend else []
    )
    for b in backends:
        if b.api_key_env and not os.environ.get(b.api_key_env):
            raise RuntimeError(f"environment variable {b.api_key_env} is not set")


def write_snapshot(config: RunConfig) -> None:
    """Write config.json once; on resume, refuse if anything that determines results changed.
    The manifest is append-only: each start adds an entry with its software versions."""
    config.run_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = config.run_dir / "config.json"
    if cfg_path.exists():
        previous = RunConfig.model_validate_json(cfg_path.read_text())
        if previous.content_key() != config.content_key():
            raise ConfigMismatchError(
                f"{cfg_path} was written by a different config (models, modules, seed, judge or "
                "step budget changed). Use a new run_id instead of mixing results."
            )
    else:
        cfg_path.write_text(config.model_dump_json(indent=2))
    import importlib.metadata

    import numpy

    from collusiongen import __version__

    try:  # recorded for provenance only; some serving images (SGLang) ship without scipy
        scipy_version = importlib.metadata.version("scipy")
    except importlib.metadata.PackageNotFoundError:
        scipy_version = "not installed"

    manifest_path = config.run_dir / "manifest.json"
    manifest: dict[str, Any] = (
        json.loads(manifest_path.read_text()) if manifest_path.exists() else {"starts": []}
    )
    manifest["starts"].append(
        {
            "collusiongen": __version__,
            "git_commit": _git_commit(),
            "python": platform.python_version(),
            "numpy": numpy.__version__,
            "scipy": scipy_version,
            "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
    )
    manifest_path.write_text(json.dumps(manifest, indent=2))


def skipped(config: RunConfig, spec: EpisodeSpec) -> bool:
    """The game is left out of this run by config.skip_params."""
    params = spec.instance.params
    return any(params.get(k) in values for k, values in config.skip_params.items())


async def run_model(config: RunConfig, model: ModelConfig, services: Services) -> dict[str, int]:
    paths = model_paths(config, model)
    results = JsonlSink(paths.results)
    events = JsonlSink(paths.events)
    transcripts = JsonlSink(paths.transcripts)
    errors = JsonlSink(paths.errors)
    done = {r["episode_id"] for r in results.iter_rows()}
    plan = expand(config, model)
    todo = [s for s in plan if s.episode_id not in done and not skipped(config, s)]
    modules = {m.id: get_module(m.id) for m in config.modules}
    backend = make_backend(model.backend)
    factory = PolicyFactory(model, backend)
    left_out = sum(1 for s in plan if s.episode_id not in done and skipped(config, s))
    counts = {
        "planned": len(plan),
        "skipped": len(plan) - len(todo) - left_out,
        "left_out": left_out,  # by skip_params, still to play
        "ok": 0,
        "failed": 0,
    }
    step = max(1, len(todo) // 20)
    queue: asyncio.Queue[EpisodeSpec] = asyncio.Queue()
    for spec in todo:
        queue.put_nowait(spec)

    async def one(spec: EpisodeSpec) -> None:
        module = modules[spec.module_id]
        attempt = uuid.uuid4().hex[:12]
        try:
            result = await asyncio.wait_for(
                run_episode(
                    module,
                    spec,
                    factory.seats_for(module, spec),
                    services,
                    max_steps=config.max_steps_per_episode,
                    log_prompts=config.log_prompts,
                    journal=paths.results.parent / "live" / f"{spec.episode_id}.jsonl",
                    max_calls_per_reply=model.max_calls_per_reply,
                ),
                timeout=config.episode_timeout_s,
            )
        except Exception as exc:  # one bad episode must not stop a sweep
            counts["failed"] += 1
            errors.append_many(
                [
                    {
                        "episode_id": spec.episode_id,
                        "attempt": attempt,
                        "cell": spec.cell,
                        "condition": spec.condition.value,
                        "error": repr(exc),
                        "traceback": traceback.format_exc(),
                    }
                ]
            )
            return
        # Sink failures (disk full, permissions) are fatal and propagate to the TaskGroup.
        events.append_many({**e.to_json(), "attempt": attempt} for e in result.events)
        transcripts.append_many({**t, "attempt": attempt} for t in result.transcript)
        results.append_many([{**result.record, "attempt": attempt}])  # last: commit point
        counts["ok"] += 1
        if counts["ok"] % step == 0:
            log.info("%s: %d/%d episodes", model.name, counts["ok"], len(todo))

    async def worker() -> None:
        while True:
            try:
                spec = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            await one(spec)

    try:
        async with asyncio.TaskGroup() as tg:
            for _ in range(min(config.concurrency, max(1, len(todo)))):
                tg.create_task(worker())
    finally:
        if backend is not None:
            await backend.aclose()
    log.info("%s: %s", model.name, counts)
    return counts


async def run_experiment(config: RunConfig) -> dict[str, dict[str, int]]:
    check_ready(config)
    write_snapshot(config)
    services, judge_backend = make_services(config.judge)
    summary: dict[str, dict[str, int]] = {}
    try:
        for model in config.models:
            summary[model.name] = await run_model(config, model, services)
    finally:
        if judge_backend is not None:
            await judge_backend.aclose()
    return summary
