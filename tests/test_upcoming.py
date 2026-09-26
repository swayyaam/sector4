"""The upcoming-race path: a post-qualifying prediction for a race not yet run.

The fixture is R15, the 2026 Azerbaijan Grand Prix, as it will look on the
Friday evening: qualifying in the Jolpica cache, practice fetched, no row in
data/processed. The field must be qualifying's participants and nobody else,
and every gap must be refused rather than filled.
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import pandas as pd
import pytest

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import features as F  # noqa: E402
import jolpica_client as J  # noqa: E402
import upcoming as UP  # noqa: E402

DATA = ROOT / "data" / "processed"
needs_data = pytest.mark.skipif(
    not (DATA / "results.csv").exists(),
    reason="the full dataset is gitignored; these run locally and before a release",
)

SEASON, ROUND, RACE_ID = 2026, 15, 1183   # the in-memory key predict.race_row gives R15
R15 = pd.Series({"raceId": RACE_ID, "year": SEASON, "round": ROUND, "circuitId": 73,
                 "name": "Azerbaijan Grand Prix", "order": SEASON * 100 + ROUND,
                 "regs_era": "2026_reset"})

# R15 qualifying, in the order Jolpica publishes it. Real refs, so they
# resolve through the committed id maps.
R15_QUALI = [("russell", "mercedes", "1:41.100"), ("antonelli", "mercedes", "1:41.250"),
             ("norris", "mclaren", "1:41.300"), ("piastri", "mclaren", "1:41.420"),
             ("leclerc", "ferrari", "1:41.500"), ("hamilton", "ferrari", "1:41.610")]
# Raced R14, absent from R15 qualifying: must never reach the R15 field.
CARRIED_OVER = ("sainz", "williams")
# Entered for R15 and in the qualifying session, but set no time, so Jolpica
# does not classify him -- as happened to two drivers at R14. Not in the field,
# but a race driver, so his practice lap is the reference, as in training.
NO_TIME = ("bearman", "haas")


def _maps() -> tuple[dict[str, int], dict[str, int]]:
    """The committed id maps: the same ones the pipeline reads."""
    d = pd.read_csv(DATA / "id_maps" / "drivers.csv")
    c = pd.read_csv(DATA / "id_maps" / "constructors.csv")
    return dict(zip(d["driverRef"], d["driverId"])), dict(zip(c["constructorRef"], c["constructorId"]))


def _race(rnd: int, name: str, rows: list[tuple[str, str, str]]) -> dict:
    return {"season": str(SEASON), "round": str(rnd), "raceName": name,
            "QualifyingResults": [
                {"number": str(i + 1), "position": str(i + 1),
                 "Driver": {"driverId": d}, "Constructor": {"constructorId": c},
                 "Q1": t, "Q2": t, "Q3": t} for i, (d, c, t) in enumerate(rows)]}


def _write_cache(cache: Path, races: list[dict]) -> None:
    total = sum(len(r["QualifyingResults"]) for r in races)
    path = J.cache_file(cache, f"{SEASON}/qualifying", {"limit": J.MAX_LIMIT, "offset": 0})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"MRData": {"total": str(total),
                                           "RaceTable": {"Races": races}}}))


@pytest.fixture()
def weekend(tmp_path):
    """Jolpica cache, processed id maps and entities, and upcoming practice laps."""
    drivers, constructors = _maps()
    cache, processed, upcoming = tmp_path / "jolpica", tmp_path / "processed", tmp_path / "up"
    _write_cache(cache, [
        _race(14, "Spanish Grand Prix", [R15_QUALI[0][:2] + ("1:12.000",), CARRIED_OVER + ("1:12.500",)]),
        _race(ROUND, "Azerbaijan Grand Prix", R15_QUALI),
    ])

    (processed / "id_maps").mkdir(parents=True)
    for name in ("drivers", "constructors"):
        (processed / "id_maps" / f"{name}.csv").write_text(
            (DATA / "id_maps" / f"{name}.csv").read_text())
    teams = {c for _, c, _ in R15_QUALI} | {CARRIED_OVER[1], NO_TIME[1]}
    pd.DataFrame([{"constructorId": constructors[t], "team_entity_id": f"{constructors[t]}-2014",
                   "first_year": 2014, "last_year": 2026, "n_seasons": 13} for t in sorted(teams)]
                 ).to_csv(processed / "team_entities.csv", index=False)

    rows = []
    for i, (ref, _, _) in enumerate(R15_QUALI):
        for session, ms in (("Practice 1", 104_000), ("Practice 2", 103_000), ("Practice 3", 102_000)):
            rows.append({"session": session, "driverId": drivers[ref], "reserve_key": None,
                         "LapTimeMs": ms + i * 150, "IsAccurate": True, "TrackStatus": 1,
                         "Stint": 1, "Compound": "SOFT"})
    # The fastest race driver: sets the reference although he is not classified.
    rows.append({"session": "Practice 3", "driverId": drivers[NO_TIME[0]], "reserve_key": None,
                 "LapTimeMs": 101_000, "IsAccurate": True, "TrackStatus": 1, "Stint": 1,
                 "Compound": "SOFT"})
    # Faster than everyone, and must not count: not entered this weekend.
    rows.append({"session": "Practice 2", "driverId": drivers[CARRIED_OVER[0]], "reserve_key": None,
                 "LapTimeMs": 90_000, "IsAccurate": True, "TrackStatus": 1, "Stint": 1,
                 "Compound": "SOFT"})
    # An FP1 reserve with no driverId, also faster, also excluded.
    rows.append({"session": "Practice 1", "driverId": None, "reserve_key": "2026_reserve",
                 "LapTimeMs": 91_000, "IsAccurate": True, "TrackStatus": 1, "Stint": 1,
                 "Compound": "SOFT"})
    # A qualifying lap: this path reads practice only.
    rows.append({"session": "Qualifying", "driverId": drivers["russell"], "reserve_key": None,
                 "LapTimeMs": 95_000, "IsAccurate": True, "TrackStatus": 1, "Stint": 1,
                 "Compound": "SOFT"})
    laps = pd.DataFrame(rows)
    laps.insert(0, "round", ROUND)
    laps.insert(0, "season", SEASON)
    d = UP.weekend_dir(SEASON, ROUND, upcoming)
    d.mkdir(parents=True)
    laps.to_csv(d / "laps.csv", index=False)
    # FastF1's qualifying session results: the weekend's entry list.
    entry = [ref for ref, _, _ in R15_QUALI] + [NO_TIME[0]]
    pd.DataFrame([{"season": SEASON, "round": ROUND, "session": "Qualifying",
                   "driverId": drivers[ref]} for ref in entry]
                 ).to_csv(d / "results.csv", index=False)

    # The tables as data/processed has them on the Friday: R14 is the latest race.
    tables = {
        "races": pd.DataFrame([{"raceId": 1182, "year": SEASON, "round": 14, "circuitId": 81,
                                "name": "Spanish Grand Prix", "order": SEASON * 100 + 14,
                                "regs_era": "2026_reset"}]),
        "results": pd.DataFrame([{"raceId": 1182, "driverId": drivers[r], "constructorId":
                                  constructors[c], "team_entity_id": f"{constructors[c]}-2014",
                                  "positionText": "1", "positionOrder": 1, "grid": 1}
                                 for r, c in (R15_QUALI[0][:2], CARRIED_OVER)]),
        "qualifying": pd.DataFrame(columns=UP.QUALIFYING_COLS),
        "laps": pd.DataFrame(),
    }
    return {"tables": tables, "cache": cache, "processed": processed, "upcoming": upcoming,
            "drivers": drivers}


def _augment(w, **over):
    kw = {"cache_dir": w["cache"], "processed": w["processed"], "upcoming_dir": w["upcoming"]}
    kw.update(over)
    return UP.augment(w["tables"], R15, **kw)


def test_r15_field_is_qualifying_participants_and_nobody_else(weekend):
    aug = _augment(weekend)
    field = F.entrants(aug, R15, F.POST)
    expected = {weekend["drivers"][r] for r, _, _ in R15_QUALI}
    assert set(field["driverId"].astype(int)) == expected
    assert weekend["drivers"][CARRIED_OVER[0]] not in set(field["driverId"].astype(int))


def test_r15_qualifying_positions_come_from_the_session(weekend):
    q = F.qualifying_frame(_augment(weekend), R15).set_index("driverId")
    for pos, (ref, _, _) in enumerate(R15_QUALI, start=1):
        assert q.loc[weekend["drivers"][ref], "quali_position"] == pos
    assert q["quali_gap_to_pole_ms"].min() == 0


def test_r15_practice_is_measured_against_every_race_driver(weekend):
    p = F.practice_frame(_augment(weekend), R15).set_index("driverId")
    drivers = weekend["drivers"]
    racing = {drivers[r] for r, _, _ in R15_QUALI} | {drivers[NO_TIME[0]]}
    assert set(p.index) == racing
    # The reference is the unclassified race driver's 101.0s: not the 90.0s of
    # a driver who is not entered, the reserve's 91.0s, or a qualifying lap.
    assert p.loc[drivers[NO_TIME[0]], "practice_best_lap_gap_ms"] == 0
    assert p.loc[drivers["russell"], "practice_best_lap_gap_ms"] == 1_000
    assert p.loc[drivers["hamilton"], "practice_best_lap_gap_ms"] == 1_000 + 5 * 150
    assert p.loc[drivers["russell"], "practice_laps"] == 3


def test_the_unclassified_race_driver_is_not_in_the_field(weekend):
    field = set(F.entrants(_augment(weekend), R15, F.POST)["driverId"].astype(int))
    assert weekend["drivers"][NO_TIME[0]] not in field


def test_augment_leaves_its_inputs_alone(weekend):
    before = {k: len(v) for k, v in weekend["tables"].items()}
    _augment(weekend)
    assert {k: len(v) for k, v in weekend["tables"].items()} == before


def test_refuses_when_r15_qualifying_is_not_in_the_cache(weekend, tmp_path):
    cache = tmp_path / "only-r14"
    _write_cache(cache, [_race(14, "Spanish Grand Prix", [R15_QUALI[0][:2] + ("1:12.000",)])])
    with pytest.raises(UP.MissingWeekendData, match="no qualifying for 2026 round 15"):
        _augment(weekend, cache_dir=cache)


def test_refuses_when_the_cache_has_never_been_fetched(weekend, tmp_path):
    with pytest.raises(UP.MissingWeekendData, match="fetch_jolpica.py"):
        _augment(weekend, cache_dir=tmp_path / "empty")


def test_refuses_a_driver_without_a_reviewed_id(weekend, tmp_path):
    cache = tmp_path / "rookie"
    _write_cache(cache, [_race(ROUND, "Azerbaijan Grand Prix",
                               R15_QUALI + [("new_rookie", "mercedes", "1:42.000")])])
    with pytest.raises(UP.MissingWeekendData, match="new_rookie"):
        _augment(weekend, cache_dir=cache)


def test_refuses_when_the_weekend_has_not_been_fetched(weekend, tmp_path):
    with pytest.raises(UP.MissingWeekendData, match="fetch_fastf1.py --upcoming 2026 15"):
        _augment(weekend, upcoming_dir=tmp_path / "nothing")


def test_refuses_when_fastf1_qualifying_is_missing(weekend):
    path = UP.weekend_dir(SEASON, ROUND, weekend["upcoming"]) / "results.csv"
    res = pd.read_csv(path)
    res.assign(session="Practice 3").to_csv(path, index=False)
    with pytest.raises(UP.MissingWeekendData, match="qualifying session .* has not been fetched"):
        _augment(weekend)


def test_refuses_when_the_sources_disagree_about_who_is_racing(weekend):
    path = UP.weekend_dir(SEASON, ROUND, weekend["upcoming"]) / "results.csv"
    res = pd.read_csv(path)
    res[res["driverId"] != weekend["drivers"]["piastri"]].to_csv(path, index=False)
    with pytest.raises(UP.MissingWeekendData, match="disagree about who is racing"):
        _augment(weekend)


def test_refuses_to_treat_a_run_race_as_upcoming(weekend):
    tables = dict(weekend["tables"])
    tables["qualifying"] = pd.DataFrame([{c: None for c in UP.QUALIFYING_COLS} | {"raceId": RACE_ID}])
    with pytest.raises(ValueError, match="already has qualifying"):
        UP.augment(tables, R15, cache_dir=weekend["cache"], processed=weekend["processed"],
                   upcoming_dir=weekend["upcoming"])


# ------------------------------------------------------------- real data
@needs_data
def test_upcoming_path_reproduces_the_trained_features_for_r14(tmp_path):
    """Treat R14, which has run, as if it had not: strip its weekend from the
    tables, rebuild it through the upcoming path from the real Jolpica cache and
    the real FastF1 laps, and the features must match what training saw.

    R14 is the hard case: two drivers set no qualifying time, are not in the
    field, and still started -- so they count as race drivers for practice."""
    import fetch_fastf1 as FF

    tables = F.load_tables()
    races = tables["races"]
    race = races[(races["year"] == 2026) & (races["round"] == 14)].iloc[0]
    rid = int(race["raceId"])

    laps = tables["laps"][tables["laps"]["raceId"] == rid]
    results = F._rd(F.ENRICHED / "results" / "2026.csv")
    results = results[results["raceId"] == rid]
    d = UP.weekend_dir(2026, 14, tmp_path)
    d.mkdir(parents=True)
    FF.upcoming_frame([laps], 2026, 14).to_csv(d / "laps.csv", index=False)
    FF.upcoming_frame([results], 2026, 14).to_csv(d / "results.csv", index=False)

    stripped = dict(tables)
    stripped["qualifying"] = tables["qualifying"][tables["qualifying"]["raceId"] != rid]
    stripped["laps"] = tables["laps"][tables["laps"]["raceId"] != rid]
    aug = UP.augment(stripped, race, upcoming_dir=tmp_path)

    def same(a: pd.DataFrame, b: pd.DataFrame, cols: list[str]) -> None:
        a = a.sort_values("driverId").reset_index(drop=True)[cols].astype("Float64")
        b = b.sort_values("driverId").reset_index(drop=True)[cols].astype("Float64")
        pd.testing.assert_frame_equal(a, b, check_dtype=False)

    same(F.entrants(tables, race, F.POST), F.entrants(aug, race, F.POST), ["driverId"])
    same(F.qualifying_frame(tables, race), F.qualifying_frame(aug, race),
         ["driverId", "quali_position", "quali_gap_to_pole_ms", "quali_reached_q3"])
    same(F.practice_frame(tables, race), F.practice_frame(aug, race),
         ["driverId", "practice_laps", "practice_best_lap_gap_ms"])


@needs_data
def test_r15_is_never_predicted_from_a_carried_over_field():
    """Whatever the cache holds today: either R15 is refused for want of its
    weekend, or its field is exactly R15's qualifying participants. Once R15
    has run it is no longer upcoming, and this path no longer applies."""
    import predict as P

    races = F._rd(DATA / "races.csv")
    if ((races["year"] == SEASON) & (races["round"] == ROUND)).any():
        pytest.skip("R15 has run; the upcoming path no longer applies to it")

    try:
        pred = P.build(SEASON, ROUND, F.POST)
    except SystemExit as e:
        assert "Refusing" in str(e) and "2026 round 15" in str(e)
        return
    quali = next(r for r in J.read_cached_all(f"{SEASON}/qualifying")
                 if int(r["round"]) == ROUND)
    drivers, _ = _maps()
    assert {d["driverId"] for d in pred["drivers"]} == {
        drivers[r["Driver"]["driverId"]] for r in quali["QualifyingResults"]}
