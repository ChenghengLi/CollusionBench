"""Checkpoint sweep: run one identical game set on every training checkpoint, in order.

For each tag: download the pinned revision, serve it locally (vLLM + vllm-metal), check
greedy parity against mlx-lm, run live preflight, play the games, analyse, stop the server.
The next tag downloads while the current one runs. A finished tag is skipped on restart, so
an interrupted sweep resumes where it stopped.

Everything is logged under logs/<sweep_id>/<tag>/ (download, server, parity, preflight) and
logs/<sweep_id>/sweep.log; results live in runs/<sweep_id>/<model>/ as for any run.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx
import yaml
from pydantic import Field

from collusiongen.agents.backends import SamplingConfig
from collusiongen.runner.config import (
    BackendConfig,
    JudgeConfig,
    ModelConfig,
    ModuleRunConfig,
    RunConfig,
    _Strict,
    safe_name,
)
from collusiongen.runner.plan import expand

log = logging.getLogger("collusiongen.sweep")
ROOT = Path(__file__).resolve().parents[3]


class ServerConfig(_Strict):
    port: int = 8000
    gpu_memory_utilization: float = Field(0.73, gt=0, le=0.95)
    max_num_seqs: int = 64
    max_num_batched_tokens: int = 4096
    max_model_len: int = 16384
    pretrain_max_model_len: int = 8192  # pretraining tags have an 8K context
    ready_timeout_s: float = 1800
    extra_args: str = ""


class SweepConfig(_Strict):
    sweep_id: str
    repo: str
    revisions_file: Path
    served_prefix: str
    tags: list[str]  # in training order
    output_dir: Path = Path("runs")
    logs_dir: Path = Path("logs")
    prefetch: int = Field(1, ge=0)
    parity_check: bool = True
    server: ServerConfig = Field(default_factory=ServerConfig)
    seed: int = 0
    concurrency: int = 48
    episode_timeout_s: float = 28800
    max_steps_per_episode: int = 2000
    log_prompts: bool = True
    chat_sampling: SamplingConfig = Field(default_factory=SamplingConfig)
    pretrain_sampling: SamplingConfig = Field(
        default_factory=lambda: SamplingConfig(max_tokens=256)
    )
    modules: list[ModuleRunConfig]
    judge: JudgeConfig = Field(default_factory=JudgeConfig)

    @staticmethod
    def load(path: str | Path) -> SweepConfig:
        with Path(path).open(encoding="utf-8") as f:
            return SweepConfig.model_validate(yaml.safe_load(f))

    @property
    def sweep_logs(self) -> Path:
        return self.logs_dir / self.sweep_id


def load_revisions(path: Path) -> dict[str, dict[str, Any]]:
    data = yaml.safe_load(path.read_text())
    return {t["tag"]: t for t in data["tags"]}


def build_run_config(sweep: SweepConfig) -> RunConfig:
    """One RunConfig for the whole sweep: one model entry per checkpoint, identical modules."""
    revs = load_revisions(sweep.revisions_file)
    missing = [t for t in sweep.tags if t not in revs]
    if missing:
        raise ValueError(f"tags not in {sweep.revisions_file}: {missing}")
    base_url = f"http://127.0.0.1:{sweep.server.port}"
    models = []
    for tag in sweep.tags:
        r = revs[tag]
        pretraining = r["stage"] == "pretrain"
        name = f"{sweep.served_prefix}{tag}"
        models.append(
            ModelConfig(
                name=name,
                tag=tag,
                stage=r["stage"],
                step=r.get("step"),
                revision=r["sha"],
                pretraining=pretraining,
                backend=BackendConfig(
                    kind="openai_completion" if pretraining else "openai_chat",
                    base_url=base_url,
                    served_model=name,
                    timeout_s=1800,
                ),
                sampling=sweep.pretrain_sampling if pretraining else sweep.chat_sampling,
            )
        )
    return RunConfig(
        run_id=sweep.sweep_id,
        output_dir=sweep.output_dir,
        seed=sweep.seed,
        concurrency=sweep.concurrency,
        episode_timeout_s=sweep.episode_timeout_s,
        max_steps_per_episode=sweep.max_steps_per_episode,
        log_prompts=sweep.log_prompts,
        models=models,
        modules=sweep.modules,
        judge=sweep.judge,
    )


def tag_complete(config: RunConfig, model: ModelConfig) -> bool:
    from collusiongen.runner.experiment import model_paths

    planned = {s.episode_id for s in expand(config, model)}
    path = model_paths(config, model).results
    if not path.exists():
        return False
    done = set()
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                done.add(json.loads(line)["episode_id"])
            except (json.JSONDecodeError, KeyError):
                continue
    return planned <= done


# --- processes ---------------------------------------------------------------------------


def _hf() -> str:
    venv_hf = ROOT / ".venv-vllm" / "bin" / "hf"
    return str(venv_hf) if venv_hf.exists() else "hf"


def start_download(sweep: SweepConfig, model: ModelConfig) -> subprocess.Popen[bytes]:
    d = sweep.sweep_logs / safe_name(model.tag or model.name)
    d.mkdir(parents=True, exist_ok=True)
    out = (d / "download.log").open("ab")
    return subprocess.Popen(
        [_hf(), "download", sweep.repo, "--revision", str(model.revision), "--quiet"],
        stdout=out,
        stderr=subprocess.STDOUT,
        cwd=ROOT,
    )


def snapshot_dir(sweep: SweepConfig, model: ModelConfig) -> str:
    """Blocking: download (or find cached) and return the local snapshot path."""
    out = subprocess.run(
        [_hf(), "download", sweep.repo, "--revision", str(model.revision), "--quiet"],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    return out.stdout.strip().splitlines()[-1]


def start_server(sweep: SweepConfig, model: ModelConfig) -> subprocess.Popen[bytes]:
    s = sweep.server
    max_len = s.pretrain_max_model_len if model.pretraining else s.max_model_len
    env = dict(os.environ)
    env["K2H_REPO"] = sweep.repo
    env["K2H_MAX_MODEL_LEN"] = str(max_len)
    env["K2H_EXTRA_ARGS"] = (
        f"--gpu-memory-utilization {s.gpu_memory_utilization} --max-num-seqs {s.max_num_seqs} "
        f"--max-num-batched-tokens {s.max_num_batched_tokens} {s.extra_args}"
    ).strip()
    d = sweep.sweep_logs / safe_name(model.tag or model.name)
    d.mkdir(parents=True, exist_ok=True)
    out = (d / "server.log").open("ab")
    assert model.backend.served_model
    return subprocess.Popen(
        [
            str(ROOT / "serving" / "serve_local_metal.sh"),
            str(model.revision),
            model.backend.served_model,
            str(s.port),
        ],
        stdout=out,
        stderr=subprocess.STDOUT,
        env=env,
        cwd=ROOT,
    )


async def wait_ready(proc: subprocess.Popen[bytes], port: int, timeout: float) -> None:
    deadline = time.time() + timeout
    async with httpx.AsyncClient(timeout=5) as client:
        while time.time() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f"server exited with code {proc.returncode} before ready")
            try:
                if (await client.get(f"http://127.0.0.1:{port}/v1/models")).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(3)
    raise TimeoutError(f"server not ready after {timeout}s")


def stop_server(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    # vllm forks an engine process; make sure nothing keeps the port or the GPU memory.
    subprocess.run(["pkill", "-f", "vllm serve"], check=False)
    time.sleep(5)


def run_parity(sweep: SweepConfig, model: ModelConfig, model_dir: str) -> bool:
    d = sweep.sweep_logs / safe_name(model.tag or model.name)
    py = ROOT / ".venv-vllm" / "bin" / "python"
    assert model.backend.served_model
    with (d / "parity.log").open("w") as out:
        rc = subprocess.run(
            [
                str(py),
                str(ROOT / "serving" / "parity_check.py"),
                model_dir,
                model.backend.served_model,
                f"http://127.0.0.1:{sweep.server.port}",
            ],
            stdout=out,
            stderr=subprocess.STDOUT,
            cwd=ROOT,
            check=False,
        ).returncode
    return rc == 0


def write_status(sweep: SweepConfig, status: dict[str, Any]) -> None:
    sweep.sweep_logs.mkdir(parents=True, exist_ok=True)
    (sweep.sweep_logs / "status.json").write_text(json.dumps(status, indent=2))


# --- driver ------------------------------------------------------------------------------


async def run_sweep(sweep: SweepConfig, only: list[str] | None = None) -> dict[str, Any]:
    from collusiongen.analysis.report import analyse_run
    from collusiongen.runner import preflight
    from collusiongen.runner.experiment import check_ready, make_services, run_model, write_snapshot

    config = build_run_config(sweep)
    check_ready(config)
    write_snapshot(config)
    services, judge_backend = make_services(config.judge)
    models = [m for m in config.models if not only or m.tag in only]
    status: dict[str, Any] = {"sweep_id": sweep.sweep_id, "tags": {}}
    prefetching: dict[str, subprocess.Popen[bytes]] = {}
    try:
        for i, model in enumerate(models):
            tag = model.tag or model.name
            entry: dict[str, Any] = {"revision": model.revision, "stage": model.stage}
            status["tags"][tag] = entry
            if tag_complete(config, model):
                entry["state"] = "complete (skipped)"
                write_status(sweep, status)
                continue
            for nxt in models[i + 1 : i + 1 + sweep.prefetch]:
                ntag = nxt.tag or nxt.name
                if ntag not in prefetching and not tag_complete(config, nxt):
                    prefetching[ntag] = start_download(sweep, nxt)
            entry["state"] = "downloading"
            write_status(sweep, status)
            model_dir = await asyncio.to_thread(snapshot_dir, sweep, model)
            server = start_server(sweep, model)
            try:
                entry["state"] = "starting server"
                write_status(sweep, status)
                await wait_ready(server, sweep.server.port, sweep.server.ready_timeout_s)
                if sweep.parity_check:
                    entry["parity_ok"] = await asyncio.to_thread(
                        run_parity, sweep, model, model_dir
                    )
                checks = await preflight.check_served_models(
                    config.model_copy(update={"models": [model]})
                )
                checks += preflight.check_served_manifests(
                    config.model_copy(update={"models": [model]}), sweep.logs_dir
                )
                tag_dir = sweep.sweep_logs / safe_name(tag)
                (tag_dir / "preflight.txt").write_text("\n".join(map(str, checks)) + "\n")
                if not all(c.ok for c in checks):
                    entry["state"] = "preflight failed"
                    write_status(sweep, status)
                    continue
                entry["state"] = "running"
                entry["started"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                write_status(sweep, status)
                entry["counts"] = await run_model(config, model, services)
                entry["state"] = "complete" if tag_complete(config, model) else "incomplete"
                entry["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            except Exception as exc:  # one bad checkpoint must not stop the sweep
                log.exception("tag %s failed", tag)
                entry["state"] = f"failed: {exc!r}"
            finally:
                stop_server(server)
                write_status(sweep, status)
            analyse_run(config.run_dir)
    finally:
        for p in prefetching.values():
            if p.poll() is None:
                p.terminate()
        if judge_backend is not None:
            await judge_backend.aclose()
    return status


def dry_run(sweep: SweepConfig) -> str:
    """Plan without touching models or servers."""
    config = build_run_config(sweep)
    lines = [f"sweep {sweep.sweep_id}: {len(config.models)} checkpoints", ""]
    total = 0
    for m in config.models:
        specs = expand(config, m)
        need = sum(s.condition.needs_model for s in specs)
        total += need
        mods = sorted({s.module_id for s in specs})
        lines.append(
            f"  {m.tag:<26} {m.stage:<10} {str(m.revision)[:10]}  "
            f"{'completion' if m.pretraining else 'chat':<10} "
            f"model episodes {need:>5}  modules {','.join(mods)}"
        )
    lines += ["", f"total model episodes: {total}"]
    return "\n".join(lines)
