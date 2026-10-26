"""Extract a JSON action from free text. Early checkpoints have no tool-use training, so every
agentic module uses the same text protocol: the reply must contain one JSON object."""

from __future__ import annotations

import json
import re
from typing import Any

_THINK = re.compile(r"<think>.*?(</think>|$)", re.DOTALL | re.IGNORECASE)
# K2-Horizon closes reasoning with </ifm|think> or </ifm|think_faster>. Its chat template opens
# the reasoning block inside the prompt, so the reply contains only the closing tag; when the
# server's reasoning parser does not split it off, everything before that tag is reasoning.
_CLOSE = re.compile(r"</(?:ifm\|)?think(?:_[a-z]+)?>", re.IGNORECASE)
_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def strip_reasoning(text: str) -> tuple[str, str]:
    """Split reasoning from the answer. Returns (answer, reasoning).

    Handles closed or unclosed <think> blocks and a bare closing tag (reasoning opened in the
    prompt). A JSON object inside the reasoning must never be taken as the action.
    """
    closes = list(_CLOSE.finditer(text))
    if closes and not _THINK.search(text[: closes[-1].end()]):
        cut = closes[-1]
        return text[cut.end() :].strip(), text[: cut.start()]
    reasoning = "\n".join(m.group(0) for m in _THINK.finditer(text))
    return _THINK.sub("", text).strip(), reasoning


MAX_CHARS = 100_000  # longer replies are truncated from the front; the answer is at the end


def _json_objects(text: str) -> list[dict[str, Any]]:
    """Every JSON object that starts at some '{', in order of position.

    `raw_decode` from each brace tolerates stray braces in prose ("I think {maybe. {...}") and
    nested objects; deeply nested input cannot crash the episode.
    """
    decoder = json.JSONDecoder()
    found: list[dict[str, Any]] = []
    i = text.find("{")
    while i != -1:
        try:
            obj, end = decoder.raw_decode(text, i)
        except (json.JSONDecodeError, RecursionError):
            i = text.find("{", i + 1)
            continue
        if isinstance(obj, dict):
            found.append(obj)
            i = text.find("{", end)
        else:
            i = text.find("{", i + 1)
    return found


def parse_candidates(text: str) -> list[dict[str, Any]]:
    """All JSON objects in the answer (reasoning excluded), fenced blocks last so that they take
    precedence when the runner scans from the end."""
    answer, _ = strip_reasoning(text[-MAX_CHARS:])
    fenced = [o for m in _FENCE.finditer(answer) for o in _json_objects(m.group(1))]
    loose = _json_objects(_FENCE.sub("", answer))
    return loose + fenced


def parse_action(text: str) -> dict[str, Any] | None:
    """The last JSON object in the reply, preferring fenced blocks, or None."""
    answer, _ = strip_reasoning(text[-MAX_CHARS:])
    for block in reversed([m.group(1) for m in _FENCE.finditer(answer)]):
        objs = _json_objects(block)
        if objs:
            return objs[-1]
    objs = _json_objects(answer)
    return objs[-1] if objs else None
