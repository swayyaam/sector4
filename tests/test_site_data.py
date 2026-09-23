"""Tests for the figures the site derives rather than the model predicts.

Circuit history is shown on the race page beside the prediction. It must use
the same window as the model's features -- only races before this one -- and
say nothing at all when there is no history, rather than a stand-in figure.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import build_site_data as S  # noqa: E402


def _tables() -> dict[str, pd.DataFrame]:
    """Three races at circuit 7, one at circuit 9, then the race being predicted."""
    races = pd.DataFrame([
        {"raceId": 1, "year": 2023, "round": 1, "circuitId": 7, "name": "A", "order": 202301},
        {"raceId": 2, "year": 2024, "round": 1, "circuitId": 7, "name": "A", "order": 202401},
        {"raceId": 3, "year": 2024, "round": 2, "circuitId": 9, "name": "B", "order": 202402},
        {"raceId": 4, "year": 2025, "round": 1, "circuitId": 7, "name": "A", "order": 202501},
        {"raceId": 5, "year": 2026, "round": 1, "circuitId": 7, "name": "A", "order": 202601},
    ])
    rows = []
    # race 1: grid 1 wins; one retirement out of three
    rows += [(1, 10, 1, 1, "1"), (1, 11, 2, 2, "2"), (1, 12, 3, 3, "R")]
    # race 2: grid 2 wins, grid 1 second; nobody retires
    rows += [(2, 10, 2, 1, "1"), (2, 11, 1, 2, "2"), (2, 12, 3, 3, "3")]
    # race 3 is elsewhere and must not count
    rows += [(3, 10, 1, 3, "R"), (3, 11, 2, 1, "1"), (3, 12, 3, 2, "2")]
    # race 4: pit-lane start (grid 0) wins; no grid-1 winner
    rows += [(4, 10, 0, 1, "1"), (4, 11, 1, 2, "2"), (4, 12, 2, 3, "R")]
    # race 5 is the one being predicted: its result must never be read
    rows += [(5, 10, 3, 1, "1"), (5, 11, 1, 2, "R"), (5, 12, 2, 3, "R")]
    results = pd.DataFrame(rows, columns=["raceId", "driverId", "grid", "positionOrder",
                                          "positionText"])
    return {"races": races, "results": results}


def test_history_uses_only_earlier_races_at_the_same_circuit():
    t = _tables()
    race = t["races"].iloc[4]
    h = S.circuit_history(t, race, race_id=5)
    assert h["prior_races"] == 3
    assert (h["first_season"], h["last_season"]) == (2023, 2025)
    # |grid - finish| over starters with a grid slot:
    # race 1: 0,0,0  race 2: 1,1,0  race 4: (grid 0 excluded) 1,1  -> 4/8
    assert h["mean_position_change"] == 0.5
    # retired: one in race 1, one in race 4, out of nine entries
    assert h["retirement_rate"] == round(2 / 9, 4)
    # grid slot one started all three and won only race 1
    assert (h["grid_one_wins"], h["grid_one_races"]) == (1, 3)


def test_history_is_null_where_there_is_none():
    t = _tables()
    first = t["races"].iloc[0]
    h = S.circuit_history(t, first, race_id=1)
    assert h["prior_races"] == 0
    for key in ("first_season", "last_season", "mean_position_change", "retirement_rate",
                "grid_one_wins", "grid_one_races"):
        assert h[key] is None, key


def test_history_matches_the_model_features_it_describes():
    """Same window and definitions as circuit_overtaking_difficulty and
    circuit_dnf_rate, so the page cannot disagree with what the model saw."""
    import features as F

    t = _tables()
    race = t["races"].iloc[4]
    prior = F._prior(t, int(race["order"]))
    here = prior[prior["circuitId"] == 7]
    grid = pd.to_numeric(here["grid"])
    moved = (grid - pd.to_numeric(here["positionOrder"])).abs()[grid > 0]
    h = S.circuit_history(t, race, race_id=5)
    assert h["mean_position_change"] == round(float(moved.mean()), 4)
    assert h["retirement_rate"] == round(float(here["is_dnf"].mean()), 4)


def test_last_completed_is_the_latest_race_with_results(tmp_path, monkeypatch):
    races = _tables()["races"]
    (tmp_path / "results.csv").write_text("raceId,driverId\n1,10\n2,10\n4,10\n")
    monkeypatch.setattr(S.F, "PROCESSED", tmp_path)
    got = S.last_completed(races)
    assert int(got["raceId"]) == 4
