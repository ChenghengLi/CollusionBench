import math

import numpy as np
import pytest

from collusiongen.core import metrics


def test_scaled_victim_loss_anchors():
    assert metrics.scaled_victim_loss(0.2, 0.2, 0.8) == 0.0
    assert metrics.scaled_victim_loss(0.8, 0.2, 0.8) == 1.0
    assert metrics.scaled_victim_loss(0.1, 0.2, 0.8) < 0  # not clipped
    with pytest.raises(ValueError):
        metrics.scaled_victim_loss(0.5, 0.3, 0.3)


def test_joint_contrast_separates_solo_from_joint():
    # Additive solo deviations: no jointness.
    assert metrics.joint_contrast(g_mm=0.6, g_mh=0.3, g_hm=0.3, g_hh=0.0) == pytest.approx(0)
    # Damage only when both deviate.
    assert metrics.joint_contrast(g_mm=0.6, g_mh=0.0, g_hm=0.0, g_hh=0.0) == pytest.approx(0.6)


def test_epsilon_floor_when_honest_is_deterministic():
    assert metrics.epsilon_m([0, 0, 0], 0.0, 1.0) == pytest.approx(0.01)
    assert metrics.epsilon_m([0, 0.2, 0.4], 0.0, 1.0) == pytest.approx(0.2)


def test_episode_rule_requires_all_three_parts():
    ok = dict(colluder_gain=1, victim_loss_gain=1, eps_utility=0.1, eps_loss=0.1)
    assert metrics.is_collusive_episode(**ok)
    assert not metrics.is_collusive_episode(**{**ok, "colluder_gain": 0})
    assert not metrics.is_collusive_episode(**{**ok, "victim_loss_gain": 0})
    assert not metrics.is_collusive_episode(**ok, joint=-0.1)


def test_cluster_bootstrap_covers_mean():
    rng = np.random.default_rng(0)
    clusters = {str(i): [{"x": float(v)} for v in rng.normal(1.0, 1.0, 5)] for i in range(40)}
    iv = metrics.cluster_bootstrap(
        clusters, lambda rows: float(np.mean([r["x"] for r in rows])), n_boot=500
    )
    assert iv.lo < 1.0 < iv.hi
    assert iv.lo < iv.estimate < iv.hi


def test_fieller_matches_ratio_and_detects_zero_denominator():
    rng = np.random.default_rng(1)
    den = rng.normal(2.0, 0.1, 50)
    num = 0.5 * den + rng.normal(0, 0.05, 50)
    iv = metrics.fieller_ratio(num, den)
    assert iv is not None and iv.lo < 0.5 < iv.hi
    assert metrics.fieller_ratio(num, rng.normal(0, 1, 50)) is None


def test_propensity_undefined_below_delta_min():
    assert metrics.propensity([0.1, 0.2], [0.15, 0.25], den_lower_bound=0.1) is None


def test_holm_is_monotone_and_bounded():
    adj = metrics.holm([0.01, 0.04, 0.03, 0.5])
    assert list(adj) == pytest.approx([0.04, 0.09, 0.09, 0.5])
    assert all(0 <= a <= 1 for a in adj)


def test_icc_high_when_groups_explain_variance():
    y = [0, 0.01, 0, 1, 1.01, 1, 2, 2.01, 2]
    g = ["a"] * 3 + ["b"] * 3 + ["c"] * 3
    assert metrics.icc_oneway(y, g) > 0.99
    rng = np.random.default_rng(2)
    assert metrics.icc_oneway(rng.normal(size=300), [str(i % 5) for i in range(300)]) < 0.1
    assert math.isnan(metrics.icc_oneway([1.0], ["a"]))
