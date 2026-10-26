"""Run one episode: the only place where policies and environments meet."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from collusiongen.core.env import InvalidActionError, Services
from collusiongen.core.log import Event, EventLog
from collusiongen.core.policy import Policy
from collusiongen.core.registry import CollusionModule
from collusiongen.core.types import Action, Condition, Outcome, PolicyKind, SeatId, Variant
from collusiongen.judges.awareness import verbalised_awareness
from collusiongen.runner.plan import EpisodeSpec


@dataclass
class EpisodeResult:
    record: dict[str, Any]
    events: list[Event]
    transcript: list[dict[str, Any]] = field(default_factory=list)


class EpisodeAbortedError(RuntimeError):
    pass


def make_variant(module: CollusionModule, spec: EpisodeSpec) -> Variant:
    if spec.condition is Condition.INST:
        return Variant(
            paraphrase=spec.paraphrase,
            instructed=True,
            instructed_prefix=module.instructed_prefix(spec.instance.params),
            protocol=spec.protocol,
        )
    return Variant(paraphrase=spec.paraphrase, protocol=spec.protocol)


async def run_episode(
    module: CollusionModule,
    spec: EpisodeSpec,
    policies: dict[SeatId, Policy],
    services: Services,
    *,
    max_steps: int = 2000,
    log_prompts: bool = False,
    journal: Path | None = None,
    max_calls_per_reply: int | None = None,
) -> EpisodeResult:
    """Play one episode. With `journal`, every step is appended to that file as it happens,
    and steps already in it (from an interrupted attempt) are replayed into the environment
    instead of being asked of the policies again, so a crash or preemption loses at most the
    step in flight."""
    started = time.time()
    log = EventLog(spec.episode_id)
    env = module.make_env(spec.instance, make_variant(module, spec), log, services)
    transcript: list[dict[str, Any]] = []
    usage: dict[str, int] = {}
    steps = 0
    error: str | None = None

    if journal is not None:
        steps = await _replay_journal(env, policies, journal, transcript, usage)
        jfile = journal.open("a", encoding="utf-8")

    try:
        while (seat := env.next_seat()) is not None:
            if steps >= max_steps:
                raise EpisodeAbortedError(f"step budget {max_steps} exhausted")
            obs = env.observe(seat)
            decision = await policies[seat].act(obs)
            space = obs.action_space
            action = None
            batch: list[Action] = []
            if env.batch_actions and decision.meta.get("protocol") == "native_tools":
                # Parallel native tool calls: all legal calls run in order (each costs a call).
                batch = [a for c in decision.candidates if (a := space.validate(c)) is not None]
            dropped = 0
            if max_calls_per_reply is not None and len(batch) > max_calls_per_reply:
                dropped = len(batch) - max_calls_per_reply
                batch = batch[:max_calls_per_reply]
                log.emit("calls_dropped", seat, kept=max_calls_per_reply, dropped=dropped)
            for candidate in reversed(
                decision.candidates or ([decision.action] if decision.action is not None else [])
            ):
                action = space.validate(candidate)
                if action is not None:
                    break
            if dropped and batch:  # a capped reply runs its first calls, even when only one is left
                action = batch[0]
            substituted = action is None
            if action is None:
                action = space.null()
            try:
                if len(batch) > 1:
                    action = batch[0]  # the transcript records the first; events record all
                    await env.apply_batch(seat, batch)
                else:
                    await env.apply(seat, action, substituted=substituted)
            except InvalidActionError as exc:
                log.emit("invalid_action", seat, action=action, error=str(exc))
                substituted = True
                action = space.null()
                await env.apply(seat, action, substituted=True)
            for k, v in decision.usage.items():
                if isinstance(v, int):
                    usage[k] = usage.get(k, 0) + v
            entry: dict[str, Any] = {
                "episode_id": spec.episode_id,
                "step": steps,
                "seat": seat,
                "phase": obs.phase,
                "policy": policies[seat].name,
                "kind": policies[seat].kind.value,
                "prompt_sha": hashlib.sha256((obs.system + obs.prompt).encode()).hexdigest()[:16],
                "raw_text": decision.raw_text,
                "reasoning": decision.reasoning,
                "parsed": decision.action,
                "applied_batch": batch if len(batch) > 1 else None,
                **({"dropped_calls": dropped} if dropped else {}),
                "meta": decision.meta,
                "usage": decision.usage,
                "applied": action,
                "substituted": substituted,
            }
            if log_prompts:
                # Instructed-ceiling prompts are private and never written to run outputs.
                system = "<redacted: instructed>" if env.variant.instructed else obs.system
                entry.update(system=system, prompt=obs.prompt)
            transcript.append(entry)
            if journal is not None:
                jfile.write(json.dumps(entry, default=str) + "\n")
                jfile.flush()
            steps += 1
    except EpisodeAbortedError as exc:
        error = str(exc)
        log.emit("aborted", None, reason=error)
    finally:
        if journal is not None:
            jfile.close()

    outcome = env.outcome()
    log.emit(
        "outcome",
        None,
        victim_loss=outcome.victim_loss,
        colluder_utility=outcome.colluder_utility,
        task_success=outcome.task_success,
    )
    model_texts = [
        t["raw_text"] + "\n" + t["reasoning"]
        for t in transcript
        if t["kind"] in (PolicyKind.MODEL.value, PolicyKind.INSTRUCTED.value)
    ]
    record = build_record(
        spec,
        policies,
        outcome,
        steps,
        usage,
        time.time() - started,
        error,
        aware=verbalised_awareness(model_texts),
        variant=module.variant_of(spec.instance.params),
    )
    record["log_head"] = log.head  # lets the completeness check detect truncated logs
    record["n_events"] = len(log)
    return EpisodeResult(record=record, events=list(log), transcript=transcript)


async def _replay_journal(
    env: Any,
    policies: dict[SeatId, Policy],
    journal: Path,
    transcript: list[dict[str, Any]],
    usage: dict[str, int],
) -> int:
    """Re-apply the steps of an interrupted attempt. Environments are deterministic given the
    applied actions, so the game reaches exactly the state it had. Replay stops at the first
    entry that does not fit (another seat to move, a torn last line); the journal is cut back to
    the replayed prefix so the live loop appends after it."""
    if not journal.exists():
        journal.parent.mkdir(parents=True, exist_ok=True)
        return 0
    kept: list[str] = []
    for line in journal.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            break  # torn write at the moment of the crash
        seat = env.next_seat()
        if seat is None or seat != entry.get("seat"):
            break
        batch = entry.get("applied_batch")
        if batch:
            await env.apply_batch(seat, batch)
        else:
            await env.apply(seat, entry["applied"], substituted=bool(entry.get("substituted")))
        replayed = getattr(policies[seat], "replayed", None)
        if replayed is not None:
            replayed()
        for k, v in (entry.get("usage") or {}).items():
            if isinstance(v, int):
                usage[k] = usage.get(k, 0) + v
        transcript.append({**entry, "replayed": True})
        kept.append(line)
    journal.write_text("".join(f"{line}\n" for line in kept), encoding="utf-8")
    return len(kept)


def build_record(
    spec: EpisodeSpec,
    policies: dict[SeatId, Policy],
    outcome: Outcome,
    steps: int,
    usage: dict[str, int],
    duration: float,
    error: str | None,
    aware: bool,
    variant: str = "",
) -> dict[str, Any]:
    inst = spec.instance
    return {
        "episode_id": spec.episode_id,
        "protocol": spec.protocol,
        "run_id": spec.run_id,
        "model": spec.model,
        "module": spec.module_id,
        "variant": variant,
        "instance_id": inst.instance_id,
        "split": inst.split.value,
        "skin_id": inst.skin.skin_id,
        "skin_theme": inst.skin.theme,
        "params": inst.params,
        "paraphrase": spec.paraphrase,
        "episode": spec.episode,
        "cell": spec.cell,
        "condition": spec.condition.value,
        "swap_instance": spec.swap_instance,
        "seats": {s: f"{p.kind.value}:{p.name}" for s, p in policies.items()},
        "victim_loss": outcome.victim_loss,
        "colluder_utility": outcome.mean_utility,
        "utility_by_seat": outcome.colluder_utility,
        "task_success": outcome.task_success,
        "secondary": outcome.secondary,
        "extra": outcome.extra,
        "aware": aware,
        "steps": steps,
        "usage": usage,
        "duration_s": round(duration, 3),
        "error": error,
        "canary": inst.canary,
    }
