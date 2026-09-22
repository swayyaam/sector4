"""Tests for the Part C model harness.

The models themselves are judged by their scores. What has to be tested is the
machinery around them: that the walk-forward really only ever looks backwards,
that the targets mean what they say, and that the statistics reported are the
statistics computed.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import model as M  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data" / "processed"
needs_data = pytest.mark.skipif(
    not (DATA / "results.csv").exists(),
    reason="the full dataset is gitignored; these run locally and before a release",
)


class SpyModel:
    """Records what it was trained on, so the harness can be audited."""

    name = "spy"

    def __init__(self):
        self.calls = []

    def fit_predict(self, train, test):
        self.calls.append((train["order"].max() if len(train) else None,
                           int(test["order"].iloc[0])))
        ids = test["driverId"].to_numpy()
        return {t: pd.Series(1.0 / len(ids), index=ids) for t in M.TARGETS}


def _synthetic(n_races: int = 12, n_drivers: int = 10) -> pd.DataFrame:
    rows = []
    for r in range(n_races):
        order = 2000 * 100 + r
        for d in range(n_drivers):
            finish = (d + r) % n_drivers + 1
            rows.append({"raceId": 1000 + r, "driverId": d, "year": 2000 + r // 6,
                         "order": order, "finish_order": finish,
                         "win": int(finish == 1), "podium": int(finish <= 3),
                         "top10": int(finish <= 10), "dnf": 0,
                         "f1": float(d), "f2": float(finish % 3)})
    return pd.DataFrame(rows)


# ------------------------------------------------------------- walk-forward
def test_training_never_includes_the_race_being_predicted():
    df = _synthetic()
    spy = SpyModel()
    M.walk_forward(df, spy, "test", eval_from=2000, verbose=False, min_train=10)
    assert spy.calls, "the harness never called the model"
    for train_max, test_order in spy.calls:
        assert train_max is None or train_max < test_order, (
            f"trained on order {train_max} to predict {test_order}"
        )


def test_walk_forward_emits_one_row_per_driver_per_target():
    df = _synthetic(n_races=12, n_drivers=10)
    out = M.walk_forward(df, SpyModel(), "test", eval_from=2000, verbose=False,
                         min_train=10)
    per_race = out.groupby(["raceId", "target"]).size().unique()
    assert set(out["target"]) == set(M.TARGETS)
    assert list(per_race) == [10]


# ------------------------------------------------------------------ targets
@needs_data
def test_target_definitions():
    t = M.targets_frame()
    # Before 1965 two drivers could share a car and both be classified first,
    # so "exactly one winner" is only true from the era the model trains on.
    # score_predictions skips any race that does not have exactly one, which is
    # what makes the historical rows harmless rather than wrong.
    modern = t[t["year"] >= 1965]
    assert modern.groupby("raceId")["win"].sum().max() == 1, "two winners in one race"
    shared = t[t["year"] < 1965].groupby("raceId")["win"].sum()
    assert (shared > 1).any(), "the shared-drive era should show more than one winner somewhere"
    t = modern
    assert (t.loc[t["win"] == 1, "podium"] == 1).all(), "a winner must be on the podium"
    assert (t.loc[t["podium"] == 1, "top10"] == 1).all(), "a podium must be in the top ten"
    assert (t.loc[t["dnf"] == 1, "podium"] == 0).all(), "a retirement is not a podium"
    assert t.groupby("raceId")["podium"].sum().mode().iloc[0] == 3


# --------------------------------------------------------------- statistics
def test_bootstrap_interval_brackets_the_mean():
    per_race = pd.DataFrame({"raceId": range(200),
                             "log_loss": np.random.default_rng(1).normal(1.5, 0.4, 200)})
    mean, lo, hi = M.bootstrap_ci(per_race, "log_loss")
    assert lo < mean < hi
    assert hi - lo < 0.3, "200 races should give a reasonably tight interval"


def test_identical_models_are_not_significantly_different():
    rng = np.random.default_rng(2)
    a = pd.DataFrame({"raceId": range(150), "log_loss": rng.normal(1.4, 0.5, 150)})
    d = M.paired_difference(a, a.copy(), "log_loss")
    assert d["mean_difference"] == pytest.approx(0.0)
    assert not d["significant"]


def test_a_real_difference_is_detected():
    rng = np.random.default_rng(3)
    base = rng.normal(1.5, 0.3, 200)
    a = pd.DataFrame({"raceId": range(200), "log_loss": base - 0.25})
    b = pd.DataFrame({"raceId": range(200), "log_loss": base})
    d = M.paired_difference(a, b, "log_loss")
    assert d["significant"] and d["mean_difference"] < 0


def test_perfect_calibration_scores_zero_error():
    """Predictions that happen exactly as often as they claim."""
    rows = []
    rng = np.random.default_rng(4)
    for p in (0.05, 0.15, 0.35, 0.55, 0.85):
        n = 20_000
        rows.append(pd.DataFrame({"target": "win", "p": p,
                                  "y": rng.binomial(1, p, n), "raceId": 0, "driverId": 0}))
    ece = M.calibration(pd.concat(rows), "win")[1]
    assert ece < 0.01, f"ECE should be near zero for calibrated input, got {ece}"


def test_miscalibration_is_detected():
    """A model that always says 50% when the truth is 10%."""
    n = 10_000
    rng = np.random.default_rng(5)
    df = pd.DataFrame({"target": "win", "p": 0.5, "y": rng.binomial(1, 0.1, n),
                       "raceId": 0, "driverId": 0})
    assert M.calibration(df, "win")[1] > 0.35


# ----------------------------------------------------------------- the ranker
def test_monte_carlo_orders_are_a_proper_distribution():
    df = _synthetic(n_races=14, n_drivers=8)
    train, test = df[df["raceId"] < 1012], df[df["raceId"] == 1012]
    p, dist = M.RankerMonteCarlo(["f1", "f2"], n_estimators=40, draws=2000
                                 ).fit_predict_full(train, test)
    assert np.allclose(dist.sum(axis=1), 1.0), "each driver's position distribution must sum to 1"
    assert np.allclose(dist.sum(axis=0), 1.0), "each position must be filled exactly once"
    assert p["win"].sum() == pytest.approx(1.0, abs=1e-6)
    assert (p["podium"] >= p["win"] - 1e-9).all(), "podium cannot be less likely than a win"
    assert (p["top10"] >= p["podium"] - 1e-9).all()


def test_the_ranker_is_not_a_point_mass():
    """Regression test for the in-sample temperature collapse.

    Fitted on races the ranker had trained on, the temperature went to zero:
    p_win reached 1.000 in most races and the actual winner was given exactly
    zero in 55 of 166, a log loss of 7.57 against a 1.43 baseline. The failure
    is silent in every discrimination metric -- the winner hit rate stayed at
    52% -- so only the probabilities themselves reveal it.
    """
    df = _synthetic(n_races=60, n_drivers=10)
    train, test = df[df["raceId"] < 1055], df[df["raceId"] == 1055]
    p, dist = M.RankerMonteCarlo(["f1", "f2"], n_estimators=80, draws=4000,
                                 calibration_races=10).fit_predict_full(train, test)
    assert p["win"].max() < 0.99, f"collapsed to a point mass at {p['win'].max():.4f}"
    assert p["win"].min() > 0, "a simulated zero is an infinite log loss waiting to happen"
    assert (dist > 0).all().all(), "every cell of the distribution must be representable"


def test_the_temperature_is_fitted_out_of_sample():
    """The calibration races must not be in the ranker's training set."""
    df = _synthetic(n_races=60, n_drivers=10)
    train = df[df["raceId"] < 1055]
    model = M.RankerMonteCarlo(["f1", "f2"], n_estimators=20, draws=500,
                               calibration_races=10)
    seen = {}
    import lightgbm as lgb

    real_fit = lgb.LGBMRanker.fit

    def spy_fit(self, X, y, **kw):
        seen["rows"] = len(X)
        return real_fit(self, X, y, **kw)

    lgb.LGBMRanker.fit = spy_fit
    try:
        model.fit_predict_full(train, df[df["raceId"] == 1055])
    finally:
        lgb.LGBMRanker.fit = real_fit
    assert seen["rows"] < len(train), "the ranker trained on the calibration races too"
