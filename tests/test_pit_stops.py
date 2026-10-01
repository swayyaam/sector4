"""The §14 helpers, on synthetic numbers. Runs in CI."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pit_stops as PS  # noqa: E402


def test_classes_are_one_or_none_two_and_three_plus():
    assert [PS.stop_class(n) for n in (0, 1, 2, 3, 5)] == [0, 0, 1, 2, 2]


def test_add_one_smoothing_keeps_every_class_possible():
    got = PS.smoothed(np.array([10.0, 0.0, 0.0]))
    assert got.sum() == pytest.approx(1)
    assert got[1] > 0 and got[2] > 0
    assert got[0] == pytest.approx(11 / 13)


def test_no_history_gives_no_shares():
    assert np.isnan(PS.shares(np.zeros(3))).all()


def test_scores_are_per_finisher_then_per_race():
    df = pd.DataFrame({"raceId": [1, 1, 2], "cls": [0, 2, 1]})
    p = np.array([[0.5, 0.3, 0.2], [0.2, 0.3, 0.5], [0.1, 0.8, 0.1]])
    got = PS.per_race(df, p).set_index("raceId")
    assert got.loc[1, "log_loss"] == pytest.approx(-math.log(0.5))
    assert got.loc[2, "log_loss"] == pytest.approx(-math.log(0.8))
    assert got.loc[2, "brier"] == pytest.approx(0.01 + 0.04 + 0.01)


def test_a_class_never_seen_in_training_gets_no_chance_but_keeps_its_column():
    train = pd.DataFrame({"x": np.linspace(0, 1, 300), "cls": [0, 1] * 150})
    test = pd.DataFrame({"x": [0.2, 0.8]})
    p = PS.fit_predict(train, test, ["x"])
    assert p.shape == (2, 3)
    assert np.allclose(p[:, 2], 0) and np.allclose(p.sum(axis=1), 1)
