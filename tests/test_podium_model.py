"""The §13 candidates' mechanics, on synthetic numbers. Runs in CI."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import podium_model as PM  # noqa: E402


def test_summed_chances_fill_the_three_places():
    p = np.linspace(0.6, 0.01, 20)
    assert PM.sum_to_places(p).sum() == pytest.approx(3, abs=1e-6)


def test_without_retirements_the_podium_matches_the_published_simulation():
    import derived_validation as V

    p = np.linspace(1.0, 0.05, 20)
    p = p / p.sum()
    ours = PM.simulate_with_retirements(p, np.zeros(20))
    published = V.simulate(pd.DataFrame({"driverId": range(20), "p_win": p}))["p_podium"].to_numpy()
    assert np.allclose(ours, published, atol=0.02)


def test_retirements_lower_the_favourites_podium_chance():
    p = np.linspace(1.0, 0.05, 20)
    assert PM.simulate_with_retirements(p, np.full(20, 0.15))[0] < \
        PM.simulate_with_retirements(p, np.zeros(20))[0]


def test_coherence_counts_contradictions():
    d = pd.DataFrame({"c": [0.5, 0.9, 0.1], "points": [0.8, 0.8, 0.8], "win": [0.1, 0.1, 0.2]})
    got = PM.coherence(d, "c")
    assert got["above_points"] == pytest.approx(1 / 3)
    assert got["below_win"] == pytest.approx(1 / 3)
