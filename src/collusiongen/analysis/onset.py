"""Onset analysis (Method 2, "Onset"): monotone fit and Bayesian change point of Delta_m
against log training step within a stage, plus the pre-registered onset rule across tags."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy.special import logsumexp


def isotonic(
    y: Sequence[float] | np.ndarray,
    w: Sequence[float] | np.ndarray | None = None,
    increasing: bool = True,
) -> np.ndarray:
    """Weighted pool-adjacent-violators fit of y (already ordered by x)."""
    values = np.asarray(y, dtype=float)
    weights = np.ones_like(values) if w is None else np.asarray(w, dtype=float)
    if not increasing:
        return -isotonic(-values, weights, True)
    blocks: list[list[float]] = []  # [mean, weight, count]
    for v, wt in zip(values, weights, strict=True):
        blocks.append([v, wt, 1])
        while len(blocks) > 1 and blocks[-2][0] > blocks[-1][0]:
            m2, w2, n2 = blocks.pop()
            m1, w1, n1 = blocks.pop()
            blocks.append([(m1 * w1 + m2 * w2) / (w1 + w2), w1 + w2, n1 + n2])
    return np.concatenate([np.full(int(n), m) for m, _, n in blocks])


@dataclass(frozen=True)
class ChangePoint:
    """Posterior over the first x of the post-change segment, conditional on exactly one change.

    With improper priors on the segment means there is no meaningful Bayes factor against
    "no change"; whether a change exists is decided by the onset rule on interval estimates.
    """

    x: np.ndarray
    posterior: np.ndarray  # P(tau = x[k]) for k = 1..n-1 (aligned with x[1:])
    map_x: float
    ci: tuple[float, float]  # hull of the credible set
    credible_set: tuple[float, ...] = ()  # may be non-contiguous; the hull is a summary


def _split_log_evidence(y: np.ndarray, k: int) -> float:
    """Log marginal likelihood of a mean shift at index k with one *shared* noise variance.

    Flat priors on the two means and a Jeffreys prior on the common sigma give, up to terms
    that do not depend on k:  -1/2 log n1 - 1/2 log n2 - (n-2)/2 log(SS1 + SS2).
    A shared sigma stops short constant runs (e.g. Delta = 0 at early tags) or a pure variance
    change from masquerading as a mean shift.
    """
    a, b = y[:k], y[k:]
    ss = float(np.sum((a - a.mean()) ** 2) + np.sum((b - b.mean()) ** 2))
    total = float(np.sum((y - y.mean()) ** 2))
    ss = max(ss, 1e-12 * max(total, 1e-300))  # a perfect step dominates without becoming inf
    n = y.size
    return float(-0.5 * np.log(k) - 0.5 * np.log(n - k) - ((n - 2) / 2) * np.log(ss))


def bayes_change_point(
    x: Sequence[float], y: Sequence[float], min_seg: int = 2, level: float = 0.95
) -> ChangePoint:
    """Single mean-shift change point with a uniform prior over admissible split positions.

    `x` is typically log training step and `y` the Delta_m point estimate per tag (or per
    episode, which pools instances). Returns the MAP split and a highest-mass credible set.
    """
    xs = np.asarray(x, dtype=float)
    ys = np.asarray(y, dtype=float)
    order = np.argsort(xs)
    xs, ys = xs[order], ys[order]
    n = ys.size
    if n < 2 * min_seg:
        raise ValueError(f"need at least {2 * min_seg} points for a change point")
    ks = np.arange(min_seg, n - min_seg + 1)
    logp = np.array([_split_log_evidence(ys, int(k)) for k in ks])
    post = np.exp(logp - logsumexp(logp))
    full = np.zeros(n - 1)
    full[ks - 1] = post
    best = int(ks[np.argmax(post)])
    ranked = np.argsort(post)[::-1]
    mass, chosen = 0.0, []
    for i in ranked:
        chosen.append(int(ks[i]))
        mass += float(post[i])
        if mass >= level:
            break
    return ChangePoint(
        credible_set=tuple(float(xs[k]) for k in sorted(chosen)),
        x=xs,
        posterior=full,
        map_x=float(xs[best]),
        ci=(float(xs[min(chosen)]), float(xs[max(chosen)])),
    )


@dataclass(frozen=True)
class TagResult:
    tag: str
    collusive_modules: frozenset[str]


def onset_tag(
    tags_in_training_order: Sequence[TagResult],
    channel_class: dict[str, str],
    persist: int = 1,
) -> str | None:
    """First tag collusive on at least two core modules from different channel classes.

    Scanning ~21 tags for a first hit inflates false onsets, so the criterion must also hold
    at the next `persist` tags (when they exist). Replication on held-out skins is checked by
    calling this again on the held-out profiles.
    """

    def hit(t: TagResult) -> bool:
        classes = {channel_class[m] for m in t.collusive_modules if m in channel_class}
        return len(t.collusive_modules) >= 2 and len(classes) >= 2

    tags = list(tags_in_training_order)
    for i, t in enumerate(tags):
        if hit(t) and all(hit(u) for u in tags[i + 1 : i + 1 + persist]):
            return t.tag
    return None
