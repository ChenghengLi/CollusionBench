"""Skins: fresh narratives with renamed entities and units (Method 1, "schema x skin x parameters").

A skin changes words, never payoffs. Themes are split deterministically into a training pool and a
held-out pool, so the held-out-skin split contains narratives no prompt was ever tuned on.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from collusiongen.core.types import Skin, Split

NAME_TOKEN = "@name"

_ONSETS = [
    "b",
    "br",
    "c",
    "d",
    "dr",
    "f",
    "g",
    "k",
    "kl",
    "l",
    "m",
    "n",
    "p",
    "qu",
    "r",
    "s",
    "st",
    "t",
    "tr",
    "v",
    "z",
]
_VOWELS = ["a", "e", "i", "o", "u", "ae", "io", "ou"]
_CODAS = ["", "n", "r", "s", "x", "l", "m", "th", "nd", "rk"]


def pseudo_name(rng: np.random.Generator, syllables: int = 2) -> str:
    """Pronounceable invented name, so entities never match a memorised textbook example."""
    parts = [
        _ONSETS[rng.integers(len(_ONSETS))] + _VOWELS[rng.integers(len(_VOWELS))]
        for _ in range(syllables)
    ]
    return ("".join(parts) + _CODAS[rng.integers(len(_CODAS))]).capitalize()


@dataclass(frozen=True)
class SkinTheme:
    """A narrative family. Each vocab key lists the surface forms one may draw.

    The single option "@name" means "invent a fresh proper name".
    """

    name: str
    vocab: Mapping[str, Sequence[str]]


class SkinFactory:
    def __init__(self, themes: Sequence[SkinTheme], heldout_fraction: float = 0.25) -> None:
        if not themes:
            raise ValueError("at least one theme is required")
        keys = {frozenset(t.vocab) for t in themes}
        if len(keys) != 1:
            raise ValueError("all themes of a module must define the same vocab keys")
        ordered = sorted(themes, key=lambda t: hashlib.sha256(t.name.encode()).hexdigest())
        n_heldout = max(1, round(len(ordered) * heldout_fraction)) if len(ordered) > 1 else 0
        self.heldout = ordered[:n_heldout]
        self.train = ordered[n_heldout:] or ordered

    def sample(self, rng: np.random.Generator, split: Split) -> Skin:
        pool = self.heldout if split is Split.HELDOUT_SKIN and self.heldout else self.train
        theme = pool[rng.integers(len(pool))]
        vocab: dict[str, str] = {}
        used_names: set[str] = set()
        for key in sorted(theme.vocab):
            options = theme.vocab[key]
            if list(options) == [NAME_TOKEN]:
                name = pseudo_name(rng)
                while name in used_names:
                    name = pseudo_name(rng)
                used_names.add(name)
                vocab[key] = name
            else:
                vocab[key] = options[int(rng.integers(len(options)))]
        skin_id = hashlib.sha256(
            json.dumps([theme.name, vocab], sort_keys=True).encode()
        ).hexdigest()[:12]
        return Skin(skin_id=skin_id, theme=theme.name, vocab=vocab)
