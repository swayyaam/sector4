"""Tests for the Part C baselines and, mostly, for the scorer.

The scorer is the thing every later number depends on. Two bugs in it were
found by the uniform baseline alone: it reported a 99.4% winner hit rate, then
19.9%, against a true 5%. Both came from breaking ties deterministically -- the
first on row order, which carried the finishing order, the second on driverId,
which in this era means Hamilton. These tests pin the fix.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import baselines as B  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data" / "processed"
needs_data = pytest.mark.skipif(
    not (DATA / "results.csv").exists(),
    reason="the full dataset is gitignored; these run locally and before a release",
)


def _race(n: int, winner: int = 0) -> tuple[list[int], int, set[int]]:
    ids = list(range(n))
    return ids, ids[winner], {ids[0], ids[1], ids[2]}


# --------------------------------------------------------------- the scorer
@pytest.mark.parametrize("n", [4, 10, 20, 22, 26])
def test_uniform_scores_exactly_one_over_n(n):
    """Scorer sanity check, permanent and in CI.

    A uniform predictor over N drivers must score exactly 1/N on the winner and
    3/N on the podium, and log(N) in log loss. There is no modelling judgement
    in this -- it is arithmetic, and if it drifts the scorer is broken and every
    model number measured with it is worthless.
    """
    s = B.Score()
    ids, winner, podium = _race(n)
    for i in range(200):
        s.add(pd.Series(1 / n, index=ids), winner, podium, i)
    got = s.as_dict("uniform")
    assert got["winner_hit_rate"] == pytest.approx(1 / n)
    assert got["podium_rate"] == pytest.approx(3 / n)
    assert got["log_loss"] == pytest.approx(math.log(n))


@pytest.mark.parametrize("n", [4, 10, 20, 22, 26])
def test_a_perfect_oracle_scores_one_hundred_percent(n):
    """The other end of the scorer. An oracle that puts all its mass on the
    actual winner and podium must score 100% on both, and ~0 log loss."""
    s = B.Score()
    ids = list(range(n))
    winner, podium = ids[0], {ids[0], ids[1], ids[2]}
    for i in range(50):
        p = pd.Series(1e-12, index=ids)
        for d in podium:
            p[d] = 0.1
        p[winner] = 1.0
        s.add(p, winner, podium, i)
    got = s.as_dict("oracle")
    assert got["winner_hit_rate"] == pytest.approx(1.0)
    assert got["podium_rate"] == pytest.approx(1.0)
    assert got["log_loss"] < 0.3


def test_row_order_cannot_influence_the_score():
    """The first bug: the field arrives sorted by finishing position."""
    ids, winner, podium = _race(20)
    flat = pd.Series(1 / 20, index=ids)
    a, b = B.Score(), B.Score()
    a.add(flat, winner, podium, 1)
    b.add(flat.iloc[::-1], winner, podium, 1)
    assert a.as_dict("a")["winner_hit_rate"] == b.as_dict("b")["winner_hit_rate"]


def test_a_tie_at_the_podium_cut_is_scored_by_expectation():
    """Two certain, four tied for the last slot, one of which is on the podium."""
    p = pd.Series({1: 0.5, 2: 0.3, 3: 0.05, 4: 0.05, 5: 0.05, 6: 0.05})
    s = B.Score()
    s.add(p, 1, {1, 2, 3}, 1)
    # Drivers 1 and 2 are certain and both on the podium; the third slot is a
    # one-in-four draw from {3,4,5,6}, of which only 3 counts.
    assert s.podium_hits == pytest.approx(2 + 1 * 1 / 4)


def test_a_perfect_predictor_scores_near_zero():
    s = B.Score()
    p = pd.Series({1: 0.999_999, 2: 0.000_000_5, 3: 0.000_000_5})
    s.add(p, 1, {1, 2, 3}, 1)
    got = s.as_dict("perfect")
    assert got["log_loss"] < 1e-5
    assert got["winner_hit_rate"] == 1.0


def test_log_loss_stays_finite_when_a_baseline_says_zero():
    s = B.Score()
    s.add(pd.Series({1: 1.0, 2: 0.0}), 2, {1, 2}, 1)
    assert math.isfinite(s.as_dict("x")["log_loss"])


def test_brier_charges_the_full_miss_on_a_winner_outside_the_field():
    """The live scorer can meet a winner the snapshot never listed. Summing
    over the field alone dropped the winner's term and flattered it by 1."""
    p = pd.Series({1: 0.5, 2: 0.3, 3: 0.2})
    inside, outside = B.Score(), B.Score()
    inside.add(p, 1, {1, 2, 3}, 1)
    outside.add(p, 9, {9, 1, 2}, 1)
    assert inside.brier == pytest.approx(0.25 + 0.09 + 0.04)
    assert outside.brier == pytest.approx(0.25 + 0.09 + 0.04 + 1.0)


# ------------------------------------------------------------- the baselines
def test_position_prior_learns_only_from_what_it_has_seen():
    prior = B.PositionPrior("grid_pos")
    field = pd.DataFrame({"driverId": [1, 2], "grid_pos": [1, 2],
                          "positionText": ["1", "2"]})
    before = prior.predict(field)
    assert before[1] == pytest.approx(before[2]), "an unseen prior must not prefer a slot"
    prior.observe(field)
    after = prior.predict(field)
    assert after[1] > after[2], "after one race, pole should be preferred"


def test_position_prior_never_returns_zero():
    """A zero makes log loss infinite the first time a long shot wins."""
    prior = B.PositionPrior("grid_pos")
    for _ in range(50):
        prior.observe(pd.DataFrame({"driverId": [1, 2], "grid_pos": [1, 2],
                                    "positionText": ["1", "2"]}))
    p = prior.predict(pd.DataFrame({"driverId": [2], "grid_pos": [2],
                                    "positionText": ["2"]}))
    assert p[2] > 0


def test_elo_moves_the_winner_up_and_is_zero_sum():
    elo = B.Elo()
    race = pd.DataFrame({"driverId": [1, 2, 3], "positionOrder": [1, 2, 3],
                         "positionText": ["1", "2", "3"]})
    elo.observe(race)
    assert elo.rating[1] > elo.start > elo.rating[3]
    assert sum(elo.rating.values()) == pytest.approx(3 * elo.start)


def test_elo_ignores_retirements_when_rating():
    """A retirement is a reliability event, not evidence the driver is slow."""
    elo = B.Elo()
    race = pd.DataFrame({"driverId": [1, 2], "positionOrder": [1, 2],
                         "positionText": ["1", "R"]})
    elo.observe(race)
    assert elo.rating == {}, "a race with one classified finisher rates nobody"


def test_elo_probabilities_sum_to_one():
    elo = B.Elo()
    elo.rating = {1: 1800.0, 2: 1500.0, 3: 1200.0}
    p = elo.predict(pd.DataFrame({"driverId": [1, 2, 3]}))
    assert p.sum() == pytest.approx(1.0)
    assert p[1] > p[2] > p[3]


# --------------------------------------------------------------- walk-forward
@needs_data
def test_baselines_are_walk_forward():
    """Every baseline must beat uniform, and none may look perfect -- a log loss
    near zero here would mean a baseline had seen the result."""
    table, _ = B.run()
    got = table.set_index("baseline")
    assert got.loc["uniform", "log_loss"] == pytest.approx(math.log(20), abs=0.15)
    for name in ("grid order", "qualifying order", "elo"):
        assert got.loc[name, "log_loss"] < got.loc["uniform", "log_loss"], name
        assert got.loc[name, "log_loss"] > 0.5, f"{name} looks like it saw the answer"
