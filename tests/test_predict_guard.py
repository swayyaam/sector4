"""A post-qualifying prediction must see qualifying, or not be made at all.

Without this, predicting an upcoming race after qualifying silently fell back
to the previous race's field and gave every driver qualifying position 20.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import predict as P  # noqa: E402

RACE = pd.Series({"raceId": 1183, "year": 2026, "round": 15})


def _tables(qualifying_race_ids: list[int]) -> dict[str, pd.DataFrame]:
    return {"qualifying": pd.DataFrame({"raceId": qualifying_race_ids,
                                        "driverId": range(len(qualifying_race_ids))})}


def _feats(quali, practice) -> pd.DataFrame:
    return pd.DataFrame({"driverId": [1, 2, 3], "quali_position": quali,
                         "practice_best_lap_gap_ms": practice})


def test_refuses_when_the_race_has_no_qualifying_results():
    with pytest.raises(SystemExit, match="no qualifying results"):
        P.check_post_qualifying_inputs(_tables([1182, 1182]), RACE,
                                       _feats([1, 2, 3], [0.0, 100.0, 200.0]))


def test_refuses_and_names_drivers_without_a_qualifying_position():
    with pytest.raises(SystemExit, match=r"driverId \[2\]"):
        P.check_post_qualifying_inputs(_tables([1183]), RACE,
                                       _feats([1, None, 3], [0.0, 100.0, 200.0]))


def test_refuses_when_no_driver_has_practice_pace():
    with pytest.raises(SystemExit, match="no practice pace"):
        P.check_post_qualifying_inputs(_tables([1183]), RACE,
                                       _feats([1, 2, 3], [None, None, None]))


def test_allows_a_complete_weekend_with_some_practice_gaps():
    # One driver without a practice lap is ordinary and was seen in training.
    P.check_post_qualifying_inputs(_tables([1183]), RACE,
                                   _feats([1, 2, 3], [0.0, None, 200.0]))
