"""Deterministic seed derivation. Every random draw in a run is a function of the run seed and
the names of the things being drawn, so episodes are matched across conditions and checkpoints."""

from __future__ import annotations

import hashlib

import numpy as np


def derive_seed(*parts: object) -> int:
    digest = hashlib.sha256("\x1f".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)


def rng_for(*parts: object) -> np.random.Generator:
    return np.random.default_rng(derive_seed(*parts))
