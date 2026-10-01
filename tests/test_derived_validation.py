"""The rules MODEL_REPORT §11 scores the derived chances against.

Synthetic, so this runs in CI without the dataset.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import derived_validation as V  # noqa: E402


def test_an_unseen_position_sits_at_the_fields_share():
    assert V.PositionRate(10).predict(4) == pytest.approx(0.5)
    assert V.PositionRate(3).predict(float("nan")) == pytest.approx(0.15)


def test_the_rate_learns_only_what_it_has_seen():
    r = V.PositionRate(3)
    for _ in range(18):
        r.observe(1, 1)
    r.observe(1, 0)
    r.observe(1, 0)
    # (18 + 3) / (20 + 20): smoothed towards the field's share, never 18/20.
    assert r.predict(1) == pytest.approx(21 / 40)
    assert r.predict(2) == pytest.approx(0.15), "an unobserved position moved"


def test_the_teammate_rule_favours_the_better_ranked_driver():
    t = V.TeammateRate()
    for _ in range(8):
        t.observe(1, 2, 1)      # better-ranked a finished ahead
    t.observe(1, 2, 0)
    t.observe(5, 3, 1)          # b better-ranked, a ahead: the better one lost
    assert t.rate() == pytest.approx((8 + 1) / (10 + 2))
    assert t.predict(2, 7) == pytest.approx(t.rate())
    assert t.predict(7, 2) == pytest.approx(1 - t.rate())
    assert t.predict(4, 4) == 0.5 and t.predict(float("nan"), 2) == 0.5


def test_pairs_are_teammates_who_both_started_counted_once():
    race = pd.DataFrame({"driverId": [3, 1, 2, 9], "team_entity_id": ["A", "A", "B", "C"]})
    assert V.pairs(race) == [(1, 3)]


def test_the_teammate_chance_is_the_simulations_pairwise_odds():
    """Under the simulation's model, P(a ahead of b) is p_a / (p_a + p_b).
    20,000 draws must agree with that to well inside sampling noise."""
    import predict as P

    p = np.array([0.5, 0.2, 0.2, 0.1])
    draws = 20_000
    rng = np.random.default_rng(P.RNG_SEED)
    z = np.log(p)
    order = np.argsort(-(z[None, :] + rng.gumbel(size=(draws, len(p)))), axis=1)
    rank = np.empty_like(order)
    rank[np.arange(draws)[:, None], order] = np.arange(len(p))[None, :]
    ahead = (rank[:, 1] < rank[:, 3]).mean()
    assert ahead == pytest.approx(0.2 / 0.3, abs=4 * math.sqrt(0.25 / draws))


def test_log_loss_is_finite_at_the_edges():
    got = V._ll(np.array([0.0, 1.0]), np.array([1.0, 0.0]))
    assert np.isfinite(got).all()
