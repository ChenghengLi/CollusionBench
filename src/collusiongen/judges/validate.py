"""Validate a message judge against hand-labelled messages before use (proposal: 200 labelled
messages). Input JSONL rows: {"message": str, "context": str?, "agreement": bool}."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from collusiongen.judges.messages import MessageJudge


@dataclass(frozen=True)
class JudgeValidation:
    n: int
    accuracy: float
    precision: float
    recall: float
    kappa: float


def agreement_stats(truth: list[bool], pred: list[bool]) -> JudgeValidation:
    n = len(truth)
    tp = sum(t and p for t, p in zip(truth, pred, strict=True))
    tn = sum(not t and not p for t, p in zip(truth, pred, strict=True))
    fp = sum(not t and p for t, p in zip(truth, pred, strict=True))
    fn = n - tp - tn - fp
    acc = (tp + tn) / n if n else 0.0
    p_yes = ((tp + fp) / n) * ((tp + fn) / n) if n else 0.0
    p_no = ((tn + fn) / n) * ((tn + fp) / n) if n else 0.0
    pe = p_yes + p_no
    kappa = (acc - pe) / (1 - pe) if pe < 1 else 1.0
    return JudgeValidation(
        n, acc, tp / (tp + fp) if tp + fp else 0.0, tp / (tp + fn) if tp + fn else 0.0, kappa
    )


async def validate_judge(judge: MessageJudge, labelled: Path) -> JudgeValidation:
    rows = [json.loads(line) for line in labelled.read_text().splitlines() if line.strip()]
    preds = [(await judge.judge(r["message"], r.get("context", ""))).agreement for r in rows]
    return agreement_stats([bool(r["agreement"]) for r in rows], preds)
