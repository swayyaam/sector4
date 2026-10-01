"""The two recent-qualifying inputs read only races before the one predicted.

Synthetic tables, so this runs in CI without the dataset. The property is the
same one tests/test_features.py proves for the main frame: nothing from the
race being predicted, or after it, may reach its inputs.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pre_weekend_selection as S  # noqa: E402


def _tables() -> dict:
    # Five races in order. Driver 1 drives for team A, then moves to team B
    # from race 4. Driver 2 is team A throughout.
    races = pd.DataFrame({"raceId": [1, 2, 3, 4, 5], "order": [101, 102, 103, 104, 105]})
    q = pd.DataFrame([
        # raceId, driverId, position, team
        (1, 1, 1, "A"), (1, 2, 4, "A"),
        (2, 1, 3, "A"), (2, 2, 2, "A"),
        (3, 1, 5, "A"), (3, 2, 6, "A"),
        (4, 1, 9, "B"), (4, 2, 1, "A"),
        (5, 1, 20, "B"), (5, 2, 20, "A"),
    ], columns=["raceId", "driverId", "position", "team_entity_id"])
    res = q.rename(columns={"position": "positionOrder"}).assign(positionText="1")
    return {"races": races, "qualifying": q, "results": res}


def _value(df: pd.DataFrame, race: int, driver: int, col: str) -> float:
    return float(df.loc[(df["raceId"] == race) & (df["driverId"] == driver), col].iloc[0])


def test_the_first_race_has_no_history():
    out = S.recent_quali(_tables(), pd.DataFrame({"raceId": [1], "driverId": [1]}))
    assert math.isnan(_value(out, 1, 1, "driver_quali_pos_mean_3"))
    assert math.isnan(_value(out, 1, 1, "team_quali_pos_mean_3"))


def test_driver_mean_is_the_last_three_races_before_this_one():
    out = S.recent_quali(_tables(), pd.DataFrame({"raceId": [4, 5], "driverId": [1, 1]}))
    # Race 4 sees races 1-3 (1, 3, 5). Race 5 sees races 2-4 (3, 5, 9), never its own 20.
    assert _value(out, 4, 1, "driver_quali_pos_mean_3") == 3.0
    assert _value(out, 5, 1, "driver_quali_pos_mean_3") == (3 + 5 + 9) / 3


def test_team_is_the_one_from_the_previous_race():
    out = S.recent_quali(_tables(), pd.DataFrame({"raceId": [4, 5], "driverId": [1, 1]}))
    # At race 4 the driver's last race was for team A, whose best positions in
    # races 1-3 were 1, 2 and 5. The move to B is not known until race 4 has run.
    assert _value(out, 4, 1, "team_quali_pos_mean_3") == (1 + 2 + 5) / 3
    # At race 5 the previous race was for B, which has one race of history: 9.
    assert _value(out, 5, 1, "team_quali_pos_mean_3") == 9.0


def test_nothing_from_the_predicted_race_or_later_is_read():
    t = _tables()
    keys = pd.DataFrame({"raceId": [4], "driverId": [2]})
    before = S.recent_quali(t, keys)
    # Change race 4 and race 5 completely; race 4's inputs must not move.
    t["qualifying"].loc[t["qualifying"]["raceId"].isin([4, 5]), "position"] = 1
    t["results"].loc[t["results"]["raceId"].isin([4, 5]), "team_entity_id"] = "Z"
    after = S.recent_quali(t, keys)
    pd.testing.assert_frame_equal(before, after)


def test_selection_never_reaches_the_holdout_season():
    assert S.SELECT_TO < S.HOLDOUT_SEASON
