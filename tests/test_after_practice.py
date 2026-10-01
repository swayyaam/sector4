"""The after-practice snapshot's sessions and field (MODEL_REPORT §10).

Synthetic tables, so this runs in CI without the dataset. The rules under test:
only practice before the first qualifying session is read, the field never
depends on who went on to race, and a reserve who drives only FP1 on a normal
weekend is not in it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import features as F  # noqa: E402


def _tables(laps: list[tuple]) -> dict:
    races = pd.DataFrame({"raceId": [1, 2], "year": [2024, 2024], "round": [1, 2],
                          "circuitId": [10, 11], "name": ["A GP", "B GP"], "order": [202401, 202402]})
    results = pd.DataFrame([
        # Race 1: drivers 1-3 for teams X, X, Y.
        (1, 1, 100, "X", "1"), (1, 2, 100, "X", "2"), (1, 3, 200, "Y", "3"),
    ], columns=["raceId", "driverId", "constructorId", "team_entity_id", "positionText"])
    lap_rows = pd.DataFrame(laps, columns=["raceId", "session", "driverId"])
    return {"races": races, "results": results, "laps": lap_rows}


def _race(tables: dict, rid: int = 2) -> pd.Series:
    return tables["races"][tables["races"]["raceId"] == rid].iloc[0]


def test_a_normal_weekend_reads_all_three_sessions():
    t = _tables([(2, "Practice 1", 1), (2, "Practice 2", 1), (2, "Practice 3", 1)])
    assert F.practice_sessions(t, _race(t)) == ("Practice 1", "Practice 2", "Practice 3")


def test_a_sprint_weekend_reads_fp1_only():
    # FP2 on a 2021-23 sprint weekend ran after qualifying and must not count.
    t = _tables([(2, "Practice 1", 1), (2, "Practice 2", 1), (2, "Sprint", 1)])
    assert F.practice_sessions(t, _race(t)) == ("Practice 1",)


def test_an_fp1_only_reserve_is_not_in_the_field():
    # Driver 9 drives FP1 in driver 2's car; driver 2 does FP2 and FP3.
    t = _tables([(2, "Practice 1", 1), (2, "Practice 1", 9), (2, "Practice 1", 3),
                 (2, "Practice 2", 1), (2, "Practice 2", 2), (2, "Practice 2", 3),
                 (2, "Practice 3", 1), (2, "Practice 3", 2), (2, "Practice 3", 3)])
    field = F.practice_field(t, _race(t))
    assert set(field["driverId"]) == {1, 2, 3}


def test_a_sprint_weekend_field_is_fp1():
    t = _tables([(2, "Practice 1", 1), (2, "Practice 1", 2), (2, "Practice 1", 3),
                 (2, "Practice 2", 7), (2, "Sprint Qualifying", 1)])
    assert set(F.practice_field(t, _race(t))["driverId"]) == {1, 2, 3}


def test_the_field_falls_back_to_fp1_when_nothing_later_ran():
    t = _tables([(2, "Practice 1", 1), (2, "Practice 1", 3)])
    assert set(F.practice_field(t, _race(t))["driverId"]) == {1, 3}


def test_team_comes_from_earlier_races_and_a_debutant_keeps_none():
    t = _tables([(2, "Practice 2", 1), (2, "Practice 2", 8), (2, "Practice 3", 1)])
    field = F.practice_field(t, _race(t)).set_index("driverId")
    assert field.loc[1, "team_entity_id"] == "X"
    assert pd.isna(field.loc[8, "team_entity_id"]), "a debutant's team was guessed"


def test_the_after_practice_inputs_extend_the_pre_weekend_set():
    pre, practice = set(F.features_for(F.PRE)), set(F.features_for(F.PRACTICE))
    assert pre < practice
    assert not any(c.startswith("quali_") for c in practice), "qualifying leaked in"
    assert "practice_best_lap_gap_ms" in practice


def test_a_sprint_weekend_is_known_from_the_schedule_alone():
    """The format is in the calendar before the weekend. With the schedule
    saying sprint, FP1 is the only session even before any sprint has run."""
    t = _tables([(2, "Practice 1", 1), (2, "Practice 2", 1)])
    t["races"]["sprint_date"] = [None, "2024-05-04"]
    assert F.practice_sessions(t, _race(t)) == ("Practice 1",)
    t["races"]["sprint_date"] = [None, None]
    assert F.practice_sessions(t, _race(t)) == ("Practice 1", "Practice 2", "Practice 3")


# ------------------------------------------------------------------ deadlines
def _when(day: int, hour: int):
    from datetime import datetime, timezone
    return datetime(2026, 10, day, hour, 0, tzinfo=timezone.utc)


def test_the_after_practice_deadline_is_qualifying_on_a_normal_weekend():
    import revisions as R
    s = {"Practice 1": _when(2, 4), "Practice 3": _when(3, 4), "Qualifying": _when(3, 8),
         "Race": _when(4, 7)}
    assert R.deadline(2026, 16, "post_practice", s) == _when(3, 8)


def test_the_after_practice_deadline_is_sprint_qualifying_on_a_sprint_weekend():
    import revisions as R
    s = {"Practice 1": _when(9, 8), "Sprint Qualifying": _when(9, 12), "Sprint": _when(10, 9),
         "Qualifying": _when(10, 13), "Race": _when(11, 12)}
    assert R.deadline(2026, 17, "post_practice", s) == _when(9, 12)


def test_a_modern_sprint_weekend_without_its_sprint_qualifying_time_is_refused():
    import pytest
    import revisions as R
    s = {"Practice 1": _when(9, 8), "Sprint": _when(10, 9), "Qualifying": _when(10, 13),
         "Race": _when(11, 12)}
    with pytest.raises(LookupError, match="sprint qualifying"):
        R.deadline(2026, 17, "post_practice", s)


def test_a_2021_style_sprint_weekend_locks_at_friday_qualifying():
    import revisions as R
    s = {"Practice 1": _when(2, 12), "Qualifying": _when(2, 16), "Sprint": _when(3, 15),
         "Race": _when(4, 14)}
    assert R.deadline(2021, 10, "post_practice", s) == _when(2, 16)


def test_after_practice_files_are_recognised():
    from pathlib import Path
    import revisions as R
    assert R.parse_name(Path("16-post_practice.json")) == (16, "post_practice", 1)
    assert R.parse_name(Path("16-post_practice-r2.json")) == (16, "post_practice", 2)
