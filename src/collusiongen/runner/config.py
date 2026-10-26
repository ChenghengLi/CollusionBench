"""Run configuration (YAML -> validated pydantic models). Everything a run depends on is in
here, so the config snapshot written next to the results is enough to reproduce it."""

from __future__ import annotations

import itertools
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from collusiongen.agents.backends import SamplingConfig
from collusiongen.core.types import Split

SAFE_ID = re.compile(r"^[A-Za-z0-9_.@-]+$")


def safe_name(name: str) -> str:
    """Directory-safe version of a model name."""
    return re.sub(r"[^A-Za-z0-9_.@-]+", "_", name)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BackendConfig(_Strict):
    kind: Literal["openai_chat", "openai_completion", "trivial"]
    base_url: str | None = None
    served_model: str | None = None
    api_key_env: str | None = None  # name of an env var; keys never live in configs
    # Path of the chat endpoint under base_url: vLLM serves /v1/chat/completions; Zhipu's GLM
    # API is base_url https://open.bigmodel.cn/api/paas/v4 with path /chat/completions.
    chat_path: str = "/v1/chat/completions"
    # Extra HTTP headers, e.g. OpenRouter's app name (X-Title). Never put keys here.
    headers: dict[str, str] = Field(default_factory=dict)
    trivial: Literal["empty", "random", "always_defect"] | None = None
    timeout_s: float = 600.0
    # The served_model a run's episode ids were made with, when the same model's route changed
    # mid-run (2026-10-24: a TokenHarbor free allowance ran out and the games were finished on the
    # paid route, "deepseek-v4.1-flash:free" -> "deepseek-v4.1-flash"); unset everywhere else.
    identity_model: str | None = None

    @model_validator(mode="after")
    def _check(self) -> BackendConfig:
        if self.kind == "trivial" and self.trivial is None:
            raise ValueError("trivial backend needs `trivial: empty|random|always_defect`")
        if self.kind != "trivial" and not (self.base_url and self.served_model):
            raise ValueError(f"{self.kind} backend needs base_url and served_model")
        return self


class ModelConfig(_Strict):
    name: str
    tag: str | None = None
    stage: str | None = None  # pretrain | mid_1..mid_4 | rl | rl_merged | sft | final
    step: int | None = None
    revision: str | None = None  # pinned commit SHA of the tag
    pretraining: bool = False  # few-shot text scaffold; only tool-free modules run
    backend: BackendConfig
    sampling: SamplingConfig = Field(default_factory=SamplingConfig)
    # "native_tools": actions are the model's own tool calls, parsed by the server
    # (vllm --enable-auto-tool-choice --tool-call-parser k2_horizon). "json_text": one JSON
    # object in the reply, for base checkpoints that have no tool format.
    action_protocol: Literal["json_text", "native_tools"] = "json_text"
    # At most this many of a reply's parallel tool calls are run; the rest are dropped (and
    # counted in the journal). None runs them all. For models that emit hundreds of calls in
    # one reply and so spend a whole call budget in a single turn.
    max_calls_per_reply: int | None = Field(None, ge=1)
    # A line appended to every system prompt, for models whose effort is set there rather than by
    # a request field (Muse Glimmer: "Reasoning strength: low", per its model card). None adds nothing.
    system_suffix: str | None = None

    @model_validator(mode="after")
    def _protocol_fits_backend(self) -> ModelConfig:
        if self.action_protocol == "native_tools" and self.backend.kind != "openai_chat":
            raise ValueError(f"{self.name}: native_tools needs an openai_chat backend")
        return self


class ModuleRunConfig(_Strict):
    id: str
    n_instances: int = Field(12, ge=0)  # 0 = one per dataset item (N1)
    split: Split = Split.TRAIN
    paraphrases: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    episodes_per_instance: int = Field(8, ge=1)
    partner_swap_fraction: float = Field(0.25, ge=0.0, le=1.0)
    instructed: bool = True
    params_override: dict[str, Any] = Field(default_factory=dict)
    # Study knobs crossed with every instance, e.g. {"n_agents": [2, 3, 4]}. Each instance
    # index is generated once per combination, with the same seeds, so the values are
    # compared on matched games (a dose-response curve, not a point).
    sweep: dict[str, list[Any]] = Field(default_factory=dict)
    instance_offset: int = Field(0, ge=0)
    # Repetitions of the same games in a later run: episodes offset..offset+n-1. Sampling seeds
    # follow the episode index, so offset 1 continues a run that played episode 0 only.
    episode_offset: int = Field(0, ge=0)
    # Play exactly these conditions (e.g. ["MH"] for a scripted-asker block of the card games),
    # instead of HH, OO, MM plus partner swaps and INST. None keeps the usual set.
    conditions: list[Literal["MM", "MH", "HM", "HH", "OO", "INST"]] | None = None

    @model_validator(mode="after")
    def _unique_paraphrases(self) -> ModuleRunConfig:
        if len(set(self.paraphrases)) != len(self.paraphrases):
            raise ValueError(f"{self.id}: duplicate paraphrase indices {self.paraphrases}")
        for knob, values in self.sweep.items():
            if not values or len({repr(v) for v in values}) != len(values):
                raise ValueError(f"{self.id}: sweep {knob} needs distinct values, got {values}")
            if knob in self.params_override:
                raise ValueError(f"{self.id}: {knob} is both swept and overridden")
        return self

    def knob_settings(self) -> list[dict[str, Any]]:
        """Every combination of swept values, merged over params_override."""
        keys = sorted(self.sweep)
        return [
            {**self.params_override, **dict(zip(keys, combo, strict=True))}
            for combo in itertools.product(*(self.sweep[k] for k in keys))
        ]


class JudgeConfig(_Strict):
    kind: Literal["keyword", "llm", "two_stage"] = "keyword"
    backend: BackendConfig | None = None
    # Extra request fields for the LLM judge, e.g. {"chat_template_kwargs": {"enable_thinking":
    # false}} so Qwen3 answers with the JSON verdict directly instead of a reasoning trace.
    extra_body: dict[str, Any] = Field(default_factory=dict)


class RunConfig(_Strict):
    run_id: str
    output_dir: Path = Path("runs")
    seed: int = 0
    concurrency: int = Field(32, ge=1)
    episode_timeout_s: float = Field(3600.0, gt=0)
    max_steps_per_episode: int = Field(2000, ge=1)
    log_prompts: bool = False
    # Games to leave out of this run for now, by game parameter: {"max_messages": [7, 8, 9, 10]}
    # skips every game whose parameter has one of those values. A scheduling choice, not part
    # of the content key: the games stay in the plan, and removing the entry plays them later.
    skip_params: dict[str, list[Any]] = Field(default_factory=dict)
    models: list[ModelConfig]
    modules: list[ModuleRunConfig]
    judge: JudgeConfig = Field(default_factory=JudgeConfig)

    @model_validator(mode="after")
    def _unique_names(self) -> RunConfig:
        names = [safe_name(m.name) for m in self.models]
        if len(set(names)) != len(names):
            raise ValueError(f"model names collide after sanitising: {names}")
        if any(n in (".", "..") or not n for n in names):
            raise ValueError("model names must not be empty, '.' or '..'")
        if not SAFE_ID.match(self.run_id) or self.run_id in (".", ".."):
            raise ValueError(f"run_id {self.run_id!r} must match {SAFE_ID.pattern}")
        return self

    def content_key(self) -> dict[str, Any]:
        """Fields that determine results. Resuming with a different value is refused;
        scheduling fields (concurrency, timeouts, output_dir) may change freely."""
        key = self.model_dump(
            mode="json", include={"seed", "max_steps_per_episode", "models", "modules", "judge"}
        )
        # a backend's request timeout is scheduling too (2026-10-23: a resume to shorten it for a
        # provider that left requests hanging was refused)
        # and so is the route of a model that kept its identity_model (see BackendConfig)
        for m in key.get("models") or []:
            backend = m.get("backend") or {}
            backend.pop("timeout_s", None)
            identity = backend.pop("identity_model", None)
            if identity:
                backend["served_model"] = identity
        return key

    @property
    def run_dir(self) -> Path:
        return self.output_dir / self.run_id

    @staticmethod
    def load(path: str | Path) -> RunConfig:
        with Path(path).open(encoding="utf-8") as f:
            return RunConfig.model_validate(yaml.safe_load(f))
