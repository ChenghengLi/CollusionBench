"""N1 item format. The real set is 100 backdoored submissions written once by the final K2 model
("own"), 100 by other models ("other"), matched on detectability by an external monitor, plus
clean code for threshold calibration. It is built with ControlArena and frozen; the bundled
`toy.jsonl` exists only for tests and smoke runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

TOY_DATASET = Path(__file__).parent / "data" / "toy.jsonl"


@dataclass(frozen=True)
class MonitorItem:
    item_id: str
    task: str
    code: str
    label: Literal["clean", "backdoor"]
    author: Literal["own", "other"]
    detectability: float | None = None


@lru_cache(maxsize=8)
def load_items(path: str) -> tuple[MonitorItem, ...]:
    items = []
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                items.append(
                    MonitorItem(
                        d["item_id"],
                        d["task"],
                        d["code"],
                        d["label"],
                        d["author"],
                        d.get("detectability"),
                    )
                )
    ids = [i.item_id for i in items]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{path}: duplicate item ids")
    return tuple(items)
