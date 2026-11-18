"""Model backends. `LLMPolicy` depends only on the `ChatBackend` protocol (dependency
inversion): vLLM over HTTP in production, `FakeBackend` in tests."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import ssl
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field

Message = dict[str, Any]


class SamplingConfig(BaseModel):
    """Defaults follow the proposal: temperature 1.0, thinking capped at about 1k tokens."""

    temperature: float = 1.0
    top_p: float = 1.0
    max_tokens: int = 1536
    extra_body: dict[str, Any] = Field(default_factory=dict)
    # Per-request seeds. On vLLM Metal a seeded request forces the slower torch sampler for the
    # whole batch and still does not reproduce tokens exactly, so local runs may turn it off;
    # games, prompts and partner pairings stay matched either way.
    send_seed: bool = True


@dataclass
class Completion:
    text: str
    reasoning: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)  # [{name, arguments}]


class ChatBackend(Protocol):
    async def chat(
        self,
        messages: list[Message],
        sampling: SamplingConfig,
        seed: int | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> Completion: ...

    async def aclose(self) -> None: ...


def parse_tool_calls(raw: Any) -> list[dict[str, Any]]:
    """OpenAI-format tool calls -> [{"name", "arguments"}]; malformed entries are dropped."""
    out: list[dict[str, Any]] = []
    for tc in raw or []:
        fn = (tc or {}).get("function") or {}
        name, args = fn.get("name"), fn.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args) if args.strip() else {}
            except json.JSONDecodeError:
                continue
        if isinstance(name, str) and isinstance(args, dict):
            out.append({"name": name, "arguments": args})
    return out


log = logging.getLogger(__name__)

_RETRYABLE = {408, 409, 429, 500, 502, 503, 504}
_UNAVAILABLE = {401, 403, 404}  # no retry and no empty reply: the episode fails
# Reply bodies that mean the account has no balance (Zhipu code 1113), not a passing rate limit.
_NO_CREDIT = ('"code":"1113"',)


class BackendError(RuntimeError):
    """A request the server will not answer. `terminal` errors (4xx other than 408/409/429,
    e.g. a prompt over the context limit) fail the same way on every retry."""

    def __init__(self, message: str, status: int | None = None, terminal: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.terminal = terminal


def _retry_after(resp: httpx.Response, default: float) -> float:
    try:
        return min(float(resp.headers.get("retry-after", default)), 120.0)
    except ValueError:
        return default


# A rate-limited provider (429) answers again once its window passes: those retries get a far
# longer allowance, so a busy hour costs time, not games. Other errors keep `attempts`.
RATE_LIMIT_ATTEMPTS = 60


async def _post_with_retry(
    client: httpx.AsyncClient, url: str, body: dict[str, Any], attempts: int = 8
) -> dict[str, Any]:
    delay = 1.0
    last = ""
    attempt = 0
    limited = 0  # 429 answers so far; counted against RATE_LIMIT_ATTEMPTS instead
    while attempt < attempts and limited < RATE_LIMIT_ATTEMPTS:
        wait = delay * (0.5 + random.random())  # jitter so concurrent episodes do not sync up
        try:
            resp = await client.post(url, json=body)
        # ssl.SSLError (e.g. "bad record mac" mid-response) can surface unwrapped by httpx.
        except (httpx.TransportError, ssl.SSLError) as exc:
            last = repr(exc)
        else:
            if resp.status_code < 400:
                try:
                    result = resp.json()
                except ValueError as exc:
                    raise BackendError(
                        f"{url}: non-JSON response: {resp.text[:300]!r}", resp.status_code
                    ) from exc
                if not isinstance(result, dict):
                    raise BackendError(
                        f"{url}: unexpected response {result!r:.300}", resp.status_code
                    )
                error = result.get("error")
                if "choices" in result or not isinstance(error, dict):
                    return result
                # OpenRouter streams from the provider, so a provider failing mid-answer arrives
                # as HTTP 200 with an error body ("provider_unavailable", code 502). Treat it
                # like the HTTP error it stands for.
                code = error.get("code")
                last = f"HTTP 200 carrying error {code}: {str(error)[:500]}"
                if code not in _RETRYABLE:
                    raise BackendError(f"{url}: {last}", resp.status_code, terminal=True)
                if code == 429:
                    limited += 1
                    attempt -= 1  # a rate limit is not a failed attempt
            else:
                last = f"HTTP {resp.status_code}: {resp.text[:500]}"
                if resp.status_code in _UNAVAILABLE:
                    # The model or the key is gone (OpenRouter retired minimax-m3.1-flash:free on
                    # 2026-10-22 with a 404). Recording it as an empty reply let games run to the
                    # end without the model and saved them as finished; fail the episode instead,
                    # so the run reports it and a resume retries it.
                    log.error("MODEL OR KEY UNAVAILABLE: %s", resp.text[:300])
                    raise BackendError(f"{url}: model or key unavailable: {last}", resp.status_code)
                if resp.status_code == 402 or any(marker in resp.text for marker in _NO_CREDIT):
                    # An empty account: Zhipu answers 429 like a rate limit, OpenRouter 402.
                    # Waiting never fixes it.
                    log.error("ACCOUNT OUT OF CREDIT: %s", resp.text[:300])
                    raise BackendError(f"{url}: account out of credit: {last}", resp.status_code)
                if resp.status_code not in _RETRYABLE:
                    raise BackendError(f"{url}: {last}", resp.status_code, terminal=True)
                wait = _retry_after(resp, wait)
                if resp.status_code == 429:
                    limited += 1
                    attempt -= 1  # a rate limit is not a failed attempt
        attempt += 1
        if attempt < attempts and limited < RATE_LIMIT_ATTEMPTS:
            await asyncio.sleep(wait)
            delay = min(delay * 2, 60.0)  # hosted APIs can rate-limit for a minute or more
    raise BackendError(
        f"{url}: gave up after {attempt} failed attempts and {limited} rate limits; "
        f"last error {last}"
    )


def _first_choice(data: dict[str, Any]) -> dict[str, Any]:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise BackendError(f"response without choices: {str(data)[:300]}")
    choice: dict[str, Any] = choices[0]
    return choice


class OpenAIChatBackend:
    """OpenAI-compatible chat completions: vLLM with a reasoning parser (/v1/chat/completions),
    or a hosted API with its own path (Zhipu GLM: base .../api/paas/v4, path /chat/completions)."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 600.0,
        chat_path: str = "/v1/chat/completions",
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        headers = {**(extra_headers or {})}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self.model = model
        self.chat_path = chat_path
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"), headers=headers, timeout=timeout
        )

    async def chat(
        self,
        messages: list[Message],
        sampling: SamplingConfig,
        seed: int | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> Completion:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": sampling.temperature,
            "top_p": sampling.top_p,
            "max_tokens": sampling.max_tokens,
            **sampling.extra_body,
        }
        if seed is not None:
            body["seed"] = seed
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        data = await _post_with_retry(self._client, self.chat_path, body)
        choice = _first_choice(data)
        msg = choice.get("message") or {}
        reasoning = msg.get("reasoning_content") or msg.get("reasoning") or ""
        return Completion(
            text=msg.get("content") or "",
            reasoning=reasoning,
            usage=data.get("usage", {}),
            finish_reason=choice.get("finish_reason") or "",
            tool_calls=parse_tool_calls(msg.get("tool_calls")),
        )

    async def list_models(self) -> list[dict[str, Any]]:
        resp = await self._client.get("/v1/models")
        resp.raise_for_status()
        models: list[dict[str, Any]] = resp.json().get("data", [])
        return models

    async def aclose(self) -> None:
        await self._client.aclose()


def to_anthropic(messages: list[Message]) -> tuple[str, list[Message]]:
    """OpenAI-format chat (system, user, assistant with tool_calls, tool) -> Anthropic Messages
    (top-level system, tool_use blocks, tool_result blocks in the following user turn).
    Consecutive tool results share one user turn, as the Messages API requires."""
    system = "\n\n".join(str(m["content"]) for m in messages if m["role"] == "system")
    out: list[Message] = []
    for m in messages:
        role = m["role"]
        if role == "system":
            continue
        if role == "tool":
            block = {
                "type": "tool_result",
                "tool_use_id": m["tool_call_id"],
                "content": str(m["content"]) or "(empty)",
            }
            if out and out[-1]["role"] == "user" and out[-1]["content"][-1]["type"] == "tool_result":
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
            continue
        blocks: list[dict[str, Any]] = []
        if m.get("content"):
            blocks.append({"type": "text", "text": str(m["content"])})
        for tc in m.get("tool_calls") or []:
            fn = tc["function"]
            args = fn.get("arguments") or {}
            blocks.append({
                "type": "tool_use",
                "id": tc["id"],
                "name": fn["name"],
                "input": json.loads(args) if isinstance(args, str) else args,
            })
        if not blocks:
            blocks.append({"type": "text", "text": "(no reply)" if role == "assistant" else "(empty)"})
        out.append({"role": role, "content": blocks})
    return system, out


def anthropic_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """OpenAI function tools -> Anthropic tool definitions."""
    return [
        {
            "name": t["function"]["name"],
            "description": t["function"].get("description", ""),
            "input_schema": t["function"].get("parameters") or {"type": "object", "properties": {}},
        }
        for t in tools
    ]


_STOP = {"tool_use": "tool_calls", "end_turn": "stop", "max_tokens": "length"}


class AnthropicMessagesBackend:
    """Claude through the Anthropic Messages API (official SDK). Messages and tools arrive in
    OpenAI format and are converted. Top-level automatic prompt caching is on: the game history
    is rebuilt identically each turn, so every turn reads the previous turn's prefix. Sampling
    parameters are not sent (the current Claude models accept only their defaults); effort and
    thinking settings go in `sampling.extra_body` (e.g. output_config: {effort: low})."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 600.0,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        import anthropic

        self._anthropic = anthropic
        self.model = model
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key,
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            max_retries=0,  # retries are handled below, with the same rules as the other backends
            default_headers=extra_headers or None,
        )

    async def chat(
        self,
        messages: list[Message],
        sampling: SamplingConfig,
        seed: int | None = None,  # not supported by the API
        tools: list[dict[str, Any]] | None = None,
    ) -> Completion:
        a = self._anthropic
        system, msgs = to_anthropic(messages)
        kwargs: dict[str, Any] = {"model": self.model, "max_tokens": sampling.max_tokens,
                                  "messages": msgs}
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = anthropic_tools(tools)
        extra = {"cache_control": {"type": "ephemeral"}, **sampling.extra_body}
        delay, attempt, limited, last = 1.0, 0, 0, ""
        while attempt < 8 and limited < RATE_LIMIT_ATTEMPTS:
            wait = delay * (0.5 + random.random())
            try:
                resp = await self._client.messages.create(**kwargs, extra_body=extra)
                break
            except a.RateLimitError as exc:
                limited += 1
                last = str(exc)[:300]
                wait = _retry_after(exc.response, wait)
            except (a.AuthenticationError, a.PermissionDeniedError, a.NotFoundError) as exc:
                log.error("MODEL OR KEY UNAVAILABLE: %s", str(exc)[:300])
                raise BackendError(f"anthropic: model or key unavailable: {exc}", exc.status_code) from exc
            except a.BadRequestError as exc:
                if "credit balance" in str(exc).lower():
                    log.error("ACCOUNT OUT OF CREDIT: %s", str(exc)[:300])
                    raise BackendError(f"anthropic: account out of credit: {exc}", 400) from exc
                raise BackendError(f"anthropic: {str(exc)[:500]}", 400, terminal=True) from exc
            except a.APIStatusError as exc:
                if exc.status_code < 500 and exc.status_code not in _RETRYABLE:
                    raise BackendError(f"anthropic: {str(exc)[:500]}", exc.status_code, terminal=True) from exc
                attempt += 1
                last = f"HTTP {exc.status_code}: {str(exc)[:300]}"
            except (a.APIConnectionError, a.APITimeoutError) as exc:
                attempt += 1
                last = repr(exc)[:300]
            await asyncio.sleep(wait)
            delay = min(delay * 2, 60.0)
        else:
            raise BackendError(
                f"anthropic: gave up after {attempt} failed attempts and {limited} rate limits; "
                f"last error {last}"
            )
        u = resp.usage
        cache_w = u.cache_creation_input_tokens or 0
        cache_r = u.cache_read_input_tokens or 0
        usage = {
            "prompt_tokens": u.input_tokens + cache_w + cache_r,
            "completion_tokens": u.output_tokens,
            "total_tokens": u.input_tokens + cache_w + cache_r + u.output_tokens,
            "input_tokens": u.input_tokens,
            "cache_creation_input_tokens": cache_w,
            "cache_read_input_tokens": cache_r,
        }
        text = "".join(b.text for b in resp.content if b.type == "text")
        reasoning = "\n".join(b.thinking for b in resp.content if b.type == "thinking" and b.thinking)
        calls = [{"name": b.name, "arguments": dict(b.input)} for b in resp.content
                 if b.type == "tool_use" and isinstance(b.input, dict)]
        return Completion(
            text=text,
            reasoning=reasoning,
            usage=usage,
            finish_reason=_STOP.get(resp.stop_reason or "", resp.stop_reason or ""),
            tool_calls=calls,
        )

    async def aclose(self) -> None:
        await self._client.close()


def render_scaffold(messages: list[Message]) -> str:
    """Fixed plain-text scaffold for pretraining tags (no chat template, 8K context)."""
    blocks = []
    for m in messages:
        header = {
            "system": "### Instructions",
            "user": "### Situation",
            "assistant": "### Response (one JSON object)",
        }[m["role"]]
        blocks.append(f"{header}\n{m['content'].strip()}")
    blocks.append("### Response (one JSON object)\n")
    return "\n\n".join(blocks)


class OpenAICompletionBackend:
    """Few-shot text completion for base checkpoints via /v1/completions."""

    def __init__(
        self, base_url: str, model: str, api_key: str | None = None, timeout: float = 600.0
    ) -> None:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.model = model
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"), headers=headers, timeout=timeout
        )

    async def chat(
        self,
        messages: list[Message],
        sampling: SamplingConfig,
        seed: int | None = None,
        tools: list[dict[str, Any]] | None = None,  # base models have no tool format
    ) -> Completion:
        body: dict[str, Any] = {
            "model": self.model,
            "prompt": render_scaffold(messages),
            "temperature": sampling.temperature,
            "top_p": sampling.top_p,
            "max_tokens": min(sampling.max_tokens, 256),
            "stop": ["\n###", "\n\n\n"],
            **sampling.extra_body,
        }
        if seed is not None:
            body["seed"] = seed
        data = await _post_with_retry(self._client, "/v1/completions", body)
        choice = _first_choice(data)
        return Completion(
            text=choice.get("text") or "",
            usage=data.get("usage", {}),
            finish_reason=choice.get("finish_reason") or "",
        )

    async def aclose(self) -> None:
        await self._client.aclose()


class FakeBackend:
    """Deterministic backend for tests: a function from the message list to a reply."""

    def __init__(self, responder: Callable[[list[Message]], str | Completion]) -> None:
        self.responder = responder
        self.calls: list[list[Message]] = []
        self.tools_seen: list[list[dict[str, Any]] | None] = []

    async def chat(
        self,
        messages: list[Message],
        sampling: SamplingConfig,
        seed: int | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> Completion:
        self.calls.append(messages)
        self.tools_seen.append(tools)
        reply = self.responder(messages)
        return reply if isinstance(reply, Completion) else Completion(text=reply)

    async def aclose(self) -> None:
        return None
