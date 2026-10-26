"""Logit-demand Bertrand market (Calvano et al. 2020; Fish et al.) with analytic references.

Demand for firm i:  s_i = exp((a_i - p_i/alpha)/mu) / (sum_j exp((a_j - p_j/alpha)/mu) + exp(a0/mu))
Quantity q_i = beta * s_i, profit pi_i = (p_i - alpha*c_i) * q_i.
`alpha` rescales prices so models cannot pattern-match a textbook price level (Fish et al.).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

import numpy as np
from scipy import optimize


@dataclass(frozen=True)
class LogitMarket:
    quality: tuple[float, ...]
    cost: tuple[float, ...]
    outside: float = 0.0
    mu: float = 0.25
    alpha: float = 1.0
    beta: float = 100.0

    def __post_init__(self) -> None:
        if len(self.quality) != len(self.cost) or len(self.cost) < 2:
            raise ValueError("need matching quality and cost vectors for at least two firms")
        if self.mu <= 0 or self.alpha <= 0 or self.beta <= 0:
            raise ValueError("mu, alpha and beta must be positive")

    @property
    def n(self) -> int:
        return len(self.cost)

    @property
    def unit_cost(self) -> np.ndarray:
        """Marginal cost in displayed price units."""
        return self.alpha * np.asarray(self.cost)

    def shares(self, prices: np.ndarray) -> np.ndarray:
        p = np.asarray(prices, dtype=float) / self.alpha
        u = (np.asarray(self.quality) - p) / self.mu
        u0 = self.outside / self.mu
        m = max(float(np.max(u)), u0)  # stabilise the softmax
        e = np.exp(u - m)
        return np.asarray(e / (e.sum() + np.exp(u0 - m)))

    def quantities(self, prices: np.ndarray) -> np.ndarray:
        return np.asarray(self.beta * self.shares(prices))

    def profits(self, prices: np.ndarray) -> np.ndarray:
        p = np.asarray(prices, dtype=float)
        return np.asarray((p - self.unit_cost) * self.quantities(p))

    @cached_property
    def nash(self) -> np.ndarray:
        """Static Bertrand-Nash prices from the logit first-order condition
        p_i = alpha*c_i + alpha*mu / (1 - s_i(p))."""

        def residual(p: np.ndarray) -> np.ndarray:
            return p - (self.unit_cost + self.alpha * self.mu / (1.0 - self.shares(p)))

        start = self.unit_cost + self.alpha * self.mu * 2
        sol = optimize.root(residual, start, method="hybr", tol=1e-12)
        if not sol.success or np.max(np.abs(residual(sol.x))) > 1e-8:
            raise RuntimeError(f"Nash solve failed: {sol.message}")
        return np.asarray(sol.x)

    @cached_property
    def monopoly(self) -> np.ndarray:
        """Prices maximising joint profit (the fully collusive outcome).

        For logit demand a multi-product monopolist sets the same markup m (in utility units)
        on every product, with m = mu / (1 - S(m)) where S is the total inside share. The
        left-hand side minus the right is increasing in m, so the root is unique; we bracket it
        and solve with brentq. Closed-form and robust for any number of firms, unlike a
        general optimiser.
        """
        cost = np.asarray(self.cost, dtype=float)

        def inside_share(m: float) -> float:
            return float(self.shares(self.alpha * (cost + m)).sum())

        def f(m: float) -> float:
            return m * (1.0 - inside_share(m)) - self.mu

        hi = self.mu
        while f(hi) <= 0:
            hi *= 2.0
            if hi > 1e6:
                raise RuntimeError("monopoly markup bracket not found")
        m = optimize.brentq(f, 0.0, hi, xtol=1e-14, rtol=1e-14, maxiter=500)
        return np.asarray(self.alpha * (cost + m))

    def collusion_index(self, prices: np.ndarray) -> np.ndarray:
        """Per-firm price above Nash as a share of the monopoly-Nash gap (Delta in Fish et al.)."""
        return np.asarray((np.asarray(prices) - self.nash) / (self.monopoly - self.nash))
