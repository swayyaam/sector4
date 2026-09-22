"""Leakage tests for the Part B feature layer.

A feature that quietly reads the race it is predicting will look excellent in
backtest and be worthless live, and nothing in the metrics will say so. These
tests are the only thing standing between those two outcomes, so they are
written to fail loudly rather than to pass easily.

The central one is a time-travel test: build the features twice, once from the
full dataset and once from a dataset truncated to the instant before the race,
and require the two to be identical. Any feature that peeked at the race, or at
anything after it, changes under truncation and is caught — including features
nobody thought to check individually.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import pandas as pd
import pytest

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import features as F  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data" / "processed"
pytestmark = pytest.mark.skipif(
    not (DATA / "results.csv").exists(),
    reason="the full dataset is gitignored; these run locally and before a release",
)


@pytest.fixture(scope="module")
def tables():
    return F.load_tables()


@pytest.fixture(scope="module")
def sample(tables):
    """A spread of races: a season opener, a sprint weekend, a recent round."""
    races = tables["races"]
    picks = []
    for year in (2019, 2022, 2024, 2025):
        season = races[races["year"] == year].sort_values("round")
        if len(season) > 6:
            picks += [int(season.iloc[0]["raceId"]), int(season.iloc[5]["raceId"])]
    return picks


def _order_of(tables, race_id: int) -> int:
    return int(tables["races"].set_index("raceId").loc[race_id, "order"])


def truncate(tables: dict, before_order: int, keep_weekend: int | None = None) -> dict:
    """A copy of the data as it stood before `before_order`.

    `keep_weekend` keeps that race's practice and qualifying — everything a
    post-qualifying prediction is allowed to see — while still removing its
    race result and every later race.
    """
    races = tables["races"]
    keep_races = races[races["order"] < before_order]
    keep_ids = set(keep_races["raceId"])
    out = {"races": races.copy()}

    for name in ("results", "driver_standings", "constructor_standings"):
        df = tables[name]
        out[name] = df[df["raceId"].isin(keep_ids)].copy()

    q = tables["qualifying"]
    q_ids = keep_ids | ({keep_weekend} if keep_weekend else set())
    out["qualifying"] = q[q["raceId"].isin(q_ids)].copy()

    laps = tables["laps"]
    if len(laps):
        mask = laps["raceId"].isin(keep_ids)
        if keep_weekend:
            mask |= ((laps["raceId"] == keep_weekend)
                     & laps["session"].isin(["Practice 1", "Practice 2", "Practice 3"]))
        out["laps"] = laps[mask].copy()
    else:
        out["laps"] = laps.copy()
    return out


def _frames_equal(a: pd.DataFrame, b: pd.DataFrame) -> tuple[bool, str]:
    if list(a.columns) != list(b.columns):
        return False, f"columns differ: {set(a.columns) ^ set(b.columns)}"
    if len(a) != len(b):
        return False, f"row counts differ: {len(a)} vs {len(b)}"
    a2 = a.sort_values(list(F.KEYS)).reset_index(drop=True)
    b2 = b.sort_values(list(F.KEYS)).reset_index(drop=True)
    for col in a2.columns:
        x, y = a2[col], b2[col]
        same = (x.eq(y) | (x.isna() & y.isna())).all()
        if not same:
            bad = (~(x.eq(y) | (x.isna() & y.isna()))).sum()
            return False, f"{col} differs on {bad} rows (e.g. {x[~x.eq(y)].head(2).tolist()})"
    return True, ""


# --------------------------------------------------------------- the big one
@pytest.mark.parametrize("snapshot", [F.PRE, F.POST])
def test_features_are_identical_when_the_future_is_removed(tables, sample, snapshot):
    """Time travel. If a feature reads the race it predicts, or anything after
    it, deleting that data changes the answer and this fails."""
    for race_id in sample:
        order = _order_of(tables, race_id)
        cut = truncate(tables, order, keep_weekend=race_id if snapshot == F.POST else None)
        full = F.build([race_id], snapshot, tables)
        past = F.build([race_id], snapshot, cut)
        ok, why = _frames_equal(full, past)
        assert ok, f"race {race_id} at {snapshot}: {why}"


def test_pre_weekend_ignores_this_weekends_running(tables, sample):
    """The pre-weekend snapshot is published before any car runs, so removing
    the weekend's practice and qualifying must change nothing."""
    for race_id in sample:
        order = _order_of(tables, race_id)
        with_weekend = F.build([race_id], F.PRE, truncate(tables, order, keep_weekend=race_id))
        without = F.build([race_id], F.PRE, truncate(tables, order))
        ok, why = _frames_equal(with_weekend, without)
        assert ok, f"race {race_id}: pre-weekend features moved with weekend data: {why}"


def test_post_qualifying_does_use_this_weekend(tables, sample):
    """The converse. If removing practice and qualifying changed nothing, the
    post-qualifying snapshot would be pointless and something is miswired."""
    moved = 0
    for race_id in sample:
        order = _order_of(tables, race_id)
        with_weekend = F.build([race_id], F.POST, truncate(tables, order, keep_weekend=race_id))
        without = F.build([race_id], F.POST, truncate(tables, order))
        ok, _ = _frames_equal(with_weekend, without)
        moved += not ok
    assert moved == len(sample), "post-qualifying features did not react to this weekend's data"


# ---------------------------------------------------------- serving the future
def test_a_race_with_no_result_still_produces_features(tables):
    """The whole point: the same code path has to serve a race that has not
    happened. Simulated by deleting the last race's result entirely."""
    races = tables["races"].sort_values("order")
    race_id = int(races.iloc[-1]["raceId"])
    cut = truncate(tables, _order_of(tables, race_id), keep_weekend=race_id)
    for snapshot in (F.PRE, F.POST):
        got = F.build([race_id], snapshot, cut)
        assert len(got) >= 10, f"{snapshot}: only {len(got)} entrants for an unrun race"
        assert got["snapshot"].eq(snapshot).all()


def test_every_declared_feature_is_produced(tables, sample):
    for snapshot in (F.PRE, F.POST):
        got = F.build(sample[:2], snapshot, tables)
        assert list(got.columns) == list(F.KEYS) + list(F.features_for(snapshot))


def test_pre_weekend_is_a_strict_subset_of_post_qualifying():
    assert set(F.features_for(F.PRE)) < set(F.features_for(F.POST))


def test_no_feature_is_named_after_an_outcome():
    """A crude tripwire, but it catches the obvious mistake of adding
    `finishing_position` or `points_scored` to the feature list."""
    banned = ("position_order", "positionorder", "finished", "result", "points_scored",
              "won", "podium", "classified", "status")
    for f in F.FEATURES:
        low = f.name.lower()
        assert not any(b in low for b in banned), f"{f.name} reads like an outcome"


def test_build_is_deterministic(tables, sample):
    a = F.build(sample, F.POST, tables)
    b = F.build(list(reversed(sample)), F.POST, tables)
    ok, why = _frames_equal(a, b)
    assert ok, f"build depends on input order: {why}"


# ------------------------------------------------------ the recorded decisions
def test_2018_gets_no_compound_features(tables):
    """2018 compound names are absolute and are never mapped. Null, not a guess."""
    ids = list(tables["races"][tables["races"]["year"] == 2018]["raceId"])[:6]
    got = F.build(ids, F.POST, tables)
    for col in ("practice_compounds_run", "practice_softest_long_run_gap_ms"):
        assert got[col].isna().all(), f"{col} is populated for 2018"


def test_lap_unusable_races_get_no_practice_pace_but_keep_their_row(tables):
    """Excluded from lap-derived features only, not from the dataset."""
    races = tables["races"]
    for year, name in F.LAP_UNUSABLE:
        row = races[(races["year"] == year) & (races["name"] == name)]
        if row.empty:
            continue
        race_id = int(row.iloc[0]["raceId"])
        got = F.build([race_id], F.POST, tables)
        assert len(got) > 0, f"{year} {name} lost its rows entirely"
        assert got["practice_best_lap_gap_ms"].isna().all()
        assert got["practice_long_run_pace_gap_ms"].isna().all()
        assert got["quali_position"].notna().any(), "non-lap features should survive"


def test_reserve_drivers_are_out_of_practice_pace(tables):
    """Reserve laps are on a different programme; including them would drag a
    team's practice pace toward whatever the young driver was asked to do.

    Checked by comparing against the same computation with the filter removed:
    the numbers have to move, and the reserve must not appear as a row."""
    laps = tables["laps"]
    flagged = laps["is_race_driver"].astype(str).str.lower() == "false"
    reserves = laps[flagged & laps["session"].isin(["Practice 1", "Practice 2", "Practice 3"])
                    & laps["driverId"].notna()]
    assert len(reserves), "no reserve laps carrying a driverId to exclude"

    race_id = int(reserves["raceId"].value_counts().index[0])
    race = tables["races"].set_index("raceId").loc[race_id]
    race["raceId"] = race_id
    with_filter = F.practice_frame(tables, race)

    unfiltered = dict(tables)
    unfiltered["laps"] = laps.assign(is_race_driver="True")
    without_filter = F.practice_frame(unfiltered, race)

    reserve_ids = set(reserves[reserves["raceId"] == race_id]["driverId"].dropna().astype(int))
    assert reserve_ids, "chosen race has no identifiable reserve"
    assert set(with_filter["driverId"]).isdisjoint(reserve_ids), "a reserve got a pace row"
    assert not set(without_filter["driverId"]).isdisjoint(reserve_ids), (
        "removing the filter changed nothing, so the filter is not doing the work"
    )
