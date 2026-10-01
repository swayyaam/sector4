"""The §12 candidates' mechanics, on synthetic numbers. Runs in CI."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import points_finish as PF  # noqa: E402


def test_summed_chances_add_up_to_the_points_places():
    p = np.linspace(0.9, 0.1, 20)
    assert PF.sum_to_places(p).sum() == pytest.approx(10, abs=1e-6)
    assert PF.sum_to_places(np.array([0.5, 0.5, 0.5])).sum() == pytest.approx(3, abs=1e-5)


def test_without_retirements_the_simulation_matches_the_published_one():
    import derived_validation as V
    import pandas as pd

    p = np.linspace(1.0, 0.05, 20)
    p = p / p.sum()
    ours = PF.simulate_with_retirements(p, np.zeros(20))
    published = V.simulate(pd.DataFrame({"driverId": range(20), "p_win": p}))["p_top10"].to_numpy()
    assert np.allclose(ours, published, atol=0.02)


def test_retirements_take_points_places_away_from_the_favourite():
    p = np.linspace(1.0, 0.05, 20)
    without = PF.simulate_with_retirements(p, np.zeros(20))
    with_dnf = PF.simulate_with_retirements(p, np.full(20, 0.15))
    assert with_dnf[0] < without[0] and with_dnf[0] <= 0.85 + 0.02
    # Ten places are still filled whenever ten cars finish.
    assert with_dnf.sum() == pytest.approx(10, abs=0.05)


def test_a_car_that_always_retires_never_scores():
    p = np.full(12, 1 / 12)
    dnf = np.zeros(12)
    dnf[0] = 1.0
    assert PF.simulate_with_retirements(p, dnf)[0] == 0.0
