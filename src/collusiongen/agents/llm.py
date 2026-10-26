"""Language-model policy: renders an observation into messages and reads the model's action."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from collusiongen.agents.backends import BackendError, ChatBackend, Message, SamplingConfig
from collusiongen.agents.parsing import parse_action, parse_candidates, strip_reasoning
from collusiongen.core.policy import Decision
from collusiongen.core.types import Observation, PolicyKind


class LLMPolicy:
    """Stateless across turns: each call is rebuilt from the logged observation alone.

    Two protocols. "native_tools" (chat checkpoints): the game's actions are offered as tools,
    the server parses the model's own trained tool-call format, and only those tool calls
    count. Multi-step games replay earlier calls as tool messages. "json_text" (base
    checkpoints, which have no tool format): the reply must contain one JSON object.
    """

    def __init__(
        self,
        backend: ChatBackend,
        sampling: SamplingConfig,
        name: str,
        seed: int,
        kind: PolicyKind = PolicyKind.MODEL,
        few_shot: Sequence[tuple[str, str]] = (),
        protocol: str = "json_text",
        system_suffix: str = "",
    ) -> None:
        self.backend = backend
        self.sampling = sampling
        self.name = name
        self.kind = kind
        self.few_shot = list(few_shot)
        self.protocol = protocol
        self.system_suffix = system_suffix
        self._seed = seed
        self._calls = 0

    def messages(self, obs: Observation) -> list[Message]:
        system = f"{obs.system}\n\n{self.system_suffix}" if self.system_suffix else obs.system
        msgs: list[Message] = [{"role": "system", "content": system}]
        for prompt, reply in self.few_shot:
            msgs += [{"role": "user", "content": prompt}, {"role": "assistant", "content": reply}]
        msgs.append({"role": "user", "content": obs.prompt})
        if self.protocol == "native_tools" and obs.tool_history:
            msgs += native_history(obs.tool_history)
        return msgs

    def replayed(self) -> None:
        """One decision was restored from a game's live journal instead of asked again: keep the
        per-call seed sequence where an uninterrupted game would have it."""
        self._calls += 1

    async def act(self, obs: Observation) -> Decision:
        seed = (self._seed + self._calls) % (2**31)
        self._calls += 1
        native = self.protocol == "native_tools"
        tools = obs.action_space.tools() if native else None
        try:
            completion = await self.backend.chat(
                self.messages(obs),
                self.sampling,
                seed=seed if self.sampling.send_seed else None,
                tools=tools,
            )
        except BackendError as exc:
            if not exc.terminal:
                raise  # transient: the episode fails and is retried on resume
            # e.g. prompt over the context limit: deterministic, so record a format failure
            return Decision(
                action=None,
                raw_text="",
                meta={"backend_error": str(exc)[:500], "status": exc.status},
            )
        answer, inline_reasoning = strip_reasoning(completion.text)
        reasoning = "\n".join(s for s in (completion.reasoning, inline_reasoning) if s)
        meta: dict[str, Any] = {
            "seed": seed,
            "finish_reason": completion.finish_reason,
            "protocol": self.protocol,
        }
        if native:
            # Only the model's own tool calls count; prose is never parsed for actions.
            meta["tool_calls"] = completion.tool_calls
            actions = [
                a
                for tc in completion.tool_calls
                if (a := obs.action_space.from_tool_call(tc["name"], tc["arguments"])) is not None
            ]
            return Decision(
                action=actions[-1] if actions else None,
                candidates=actions,
                raw_text=completion.text,
                reasoning=reasoning,
                usage=dict(completion.usage),
                meta=meta,
            )
        return Decision(
            action=parse_action(answer),
            candidates=parse_candidates(answer),
            raw_text=completion.text,
            reasoning=reasoning,
            usage=dict(completion.usage),
            meta=meta,
        )


def native_history(history: list[dict[str, Any]]) -> list[Message]:
    """Earlier steps of a tool session as chat messages in OpenAI tool format. The K2 chat
    template requires a thinking field on assistant turns; vLLM forwards it only from the
    `reasoning` key. Past reasoning is not replayed."""
    msgs: list[Message] = []
    for i, step in enumerate(history):
        if step.get("name"):
            msgs.append(
                {
                    "role": "assistant",
                    "content": "",
                    "reasoning": "",
                    "tool_calls": [
                        {
                            "id": f"call_{i}",
                            "type": "function",
                            "function": {
                                "name": step["name"],
                                "arguments": json.dumps(step["arguments"]),
                            },
                        }
                    ],
                }
            )
            msgs.append(
                {"role": "tool", "tool_call_id": f"call_{i}", "content": str(step["result"])}
            )
        else:  # the reply had no usable tool call
            msgs.append({"role": "assistant", "content": "(no tool call)", "reasoning": ""})
            msgs.append({"role": "user", "content": str(step["result"])})
    return msgs
