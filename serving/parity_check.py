"""Greedy-decoding parity between the vLLM server and mlx-lm run directly on the same weights.

    .venv-vllm/bin/python serving/parity_check.py <model_dir> <served-name> [base_url]

Run it for every checkpoint before collecting data: a serving bug (dropped prompt, wrong
attention path) shows up as diverging text even when the server looks healthy.
"""

from __future__ import annotations

import sys

import httpx
from mlx_lm import generate, load

PROMPTS = [
    "What is 17 * 23? Answer with the number only.",
    "What is the capital of Australia? One word.",
    "Spell the word 'collusion' backwards.",
    'Marginal cost 4.00, last price 6.10, profit 52.3. Reply with JSON {"price": <number>}.',
    "Name three prime numbers greater than 50.",
]


def main() -> int:
    model_dir, served = sys.argv[1], sys.argv[2]
    base = sys.argv[3] if len(sys.argv) > 3 else "http://127.0.0.1:8000"
    model, tok = load(model_dir, tokenizer_config={"trust_remote_code": True})
    bad = 0
    for q in PROMPTS:
        msgs = [{"role": "user", "content": q}]
        prompt = tok.apply_chat_template(
            msgs, add_generation_prompt=True, tokenize=False, reasoning_effort="low"
        )
        local = generate(model, tok, prompt=prompt, max_tokens=64, verbose=False)
        r = httpx.post(f"{base}/v1/chat/completions", timeout=300, json={
            "model": served, "messages": msgs, "temperature": 0.0, "max_tokens": 64,
            "chat_template_kwargs": {"reasoning_effort": "low"},
            "skip_special_tokens": False,
        }).json()
        m = r["choices"][0]["message"]
        served_text = (m.get("reasoning_content") or m.get("reasoning") or "") + (
            m.get("content") or "")
        norm = lambda s: "".join(s.split()).replace("</ifm|think_faster>", "")  # noqa: E731
        same = norm(local)[:40] == norm(served_text)[:40]
        bad += not same
        print(f"[{'same' if same else 'DIFF'}] {q[:40]!r}\n   mlx : {local[:120]!r}\n"
              f"   vllm: {served_text[:120]!r}")
    print(f"\n{len(PROMPTS) - bad}/{len(PROMPTS)} prompts agree on the first 40 characters")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
