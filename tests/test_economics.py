import numpy as np
import pytest

from collusiongen.modules.a1_pricing.economics import LogitMarket


def test_calvano_reference_prices():
    m = LogitMarket(quality=(2.0, 2.0), cost=(1.0, 1.0), mu=0.25)
    assert m.nash == pytest.approx([1.4729, 1.4729], abs=1e-4)
    assert m.monopoly == pytest.approx([1.9250, 1.9250], abs=1e-4)


def test_price_scale_is_neutral():
    a = LogitMarket((2.0, 2.0), (1.0, 1.0), alpha=1.0)
    b = LogitMarket((2.0, 2.0), (1.0, 1.0), alpha=3.2)
    assert b.nash == pytest.approx(3.2 * a.nash)
    assert b.collusion_index(b.monopoly) == pytest.approx([1.0, 1.0])


def test_nash_is_a_best_response():
    m = LogitMarket((2.0, 2.0, 2.0), (1.0, 1.05, 0.95), mu=0.3)
    for i in range(m.n):
        grid = np.linspace(m.unit_cost[i], 3 * m.nash[i], 2001)

        def profit(p, i=i):
            prices = m.nash.copy()
            prices[i] = p
            return m.profits(prices)[i]

        best = grid[np.argmax([profit(p) for p in grid])]
        assert best == pytest.approx(m.nash[i], abs=2e-3)


def test_monopoly_beats_nash_jointly():
    m = LogitMarket((2.0, 2.0), (1.0, 1.0))
    assert m.profits(m.monopoly).sum() > m.profits(m.nash).sum()
