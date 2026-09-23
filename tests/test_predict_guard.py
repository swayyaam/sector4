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


# ------------------------------------------------------ nothing published late
def _deadline_setup(monkeypatch, tmp_path, *, now_hour: int, existing: list):
    from datetime import datetime, timezone

    monkeypatch.setattr(P, "OUT", tmp_path)
    monkeypatch.setattr(P.REV, "revisions", lambda *a, **k: existing)
    fp1 = datetime(2026, 9, 24, 8, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(P.REV, "deadline", lambda *a, **k: fp1)
    monkeypatch.setattr(P.REV, "now_utc",
                        lambda: datetime(2026, 9, 24, now_hour, 0, tzinfo=timezone.utc))
    monkeypatch.setattr(sys, "argv", ["predict.py", "--season", "2026", "--round", "16",
                                      "--snapshot", "pre_weekend"])


def test_a_first_prediction_after_its_deadline_is_refused(tmp_path, monkeypatch):
    """The scorer would ignore it, so it is never written in the first place."""
    _deadline_setup(monkeypatch, tmp_path, now_hour=9, existing=[])
    monkeypatch.setattr(P, "build", lambda *a, **k: pytest.fail("built after the deadline"))
    with pytest.raises(SystemExit, match="deadline .* a first prediction published now"):
        P.main()
    assert list(tmp_path.rglob("*.json")) == []


def test_a_first_prediction_before_its_deadline_goes_ahead(tmp_path, monkeypatch):
    _deadline_setup(monkeypatch, tmp_path, now_hour=7, existing=[])

    class Built(Exception):
        pass

    def build(*a, **k):
        raise Built()

    monkeypatch.setattr(P, "build", build)
    with pytest.raises(Built):
        P.main()

