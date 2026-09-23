"""The upcoming-race path: this weekend's qualifying and practice, before the race.

data/processed holds completed races only, and gives none of them an id until
the race has run. A post-qualifying prediction is made between qualifying and
the race, so the weekend it needs is never there. Rather than mint provisional
ids in data/processed for one edge case, this reads the weekend straight from
the fetched session data, keyed on (season, round):

* **Qualifying** from the Jolpica cache: the season's qualifying endpoint,
  which ``fetch_jolpica.py`` refreshes on every run while any race is still
  provisional. Read offline; this module never fetches.
* **Practice** from ``data/enriched/upcoming/<season>-<round>/laps.csv``, and
  the weekend's **race drivers** from the FastF1 qualifying session's entry
  list in ``results.csv`` beside it, both written by
  ``fetch_fastf1.py --upcoming SEASON ROUND``.

Both are appended to *in-memory copies* of the tables under the race's
in-memory key, the same provisional key ``predict.race_row`` already uses and
which is never written anywhere. The features are then computed by the very
functions the model was trained with -- ``entrants``, ``qualifying_frame`` and
``practice_frame`` -- so the upcoming race is described exactly as every
historical race was.

The field is qualifying's classified participants, never a previous race's,
which is exactly how the field was built for every race in training. Practice
pace is measured against the fastest *race driver*; historically that means
everyone who raced, which cannot be known yet, so it is everyone on the
qualifying session's entry list. At R14 that distinction mattered: two drivers
set no qualifying time, were not classified, and still started the race.

Anything missing raises MissingWeekendData. Nothing is guessed or filled.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import features as F  # noqa: E402
import jolpica_client as J  # noqa: E402

UPCOMING_DIR = F.ENRICHED / "upcoming"
QUALIFYING_COLS = ["qualifyId", "raceId", "driverId", "constructorId", "number", "position",
                   "q1", "q2", "q3", "source", "team_entity_id"]
PRACTICE_SESSIONS = ("Practice 1", "Practice 2", "Practice 3")


class MissingWeekendData(Exception):
    """The weekend's qualifying or practice is not available to read."""


def weekend_dir(season: int, rnd: int, root: Path = UPCOMING_DIR) -> Path:
    return Path(root) / f"{int(season)}-{int(rnd):02d}"


def _num(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _entity_for(entities: pd.DataFrame, constructor_id: int, season: int) -> str | None:
    """The team entity a constructor belongs to in this season: the block
    that already covers it, or the one still running into it."""
    rows = entities[entities["constructorId"] == constructor_id]
    covering = rows[(rows["first_year"] <= season) & (rows["last_year"] >= season)]
    if len(covering) == 1:
        return str(covering.iloc[0]["team_entity_id"])
    return None


def qualifying_rows(races: list[dict], season: int, rnd: int, race_id: int,
                    driver_ids: dict[str, int], constructor_ids: dict[str, int],
                    entities: pd.DataFrame) -> pd.DataFrame:
    """This weekend's qualifying classification, in qualifying.csv's shape."""
    race = next((r for r in races
                 if int(r.get("season", season)) == int(season) and int(r["round"]) == int(rnd)),
                None)
    results = (race or {}).get("QualifyingResults") or []
    if not results:
        raise MissingWeekendData(
            f"no qualifying for {season} round {rnd} in the Jolpica cache. Run "
            "src/fetch_jolpica.py after qualifying; Jolpica can take a while to publish it.")

    rows = []
    for r in results:
        dref, cref = r["Driver"]["driverId"], r["Constructor"]["constructorId"]
        if dref not in driver_ids:
            raise MissingWeekendData(
                f"driver {dref!r} is not in data/processed/id_maps/drivers.csv. A new driver "
                "needs a reviewed id before a prediction can include them.")
        if cref not in constructor_ids:
            raise MissingWeekendData(
                f"constructor {cref!r} is not in data/processed/id_maps/constructors.csv.")
        cid = constructor_ids[cref]
        entity = _entity_for(entities, cid, int(season))
        if entity is None:
            raise MissingWeekendData(
                f"constructor {cref!r} (id {cid}) has no team entity covering {season} in "
                "data/processed/team_entities.csv.")
        rows.append({"qualifyId": None, "raceId": int(race_id), "driverId": driver_ids[dref],
                     "constructorId": cid, "number": _num(r.get("number")),
                     "position": _num(r.get("position")), "q1": r.get("Q1"),
                     "q2": r.get("Q2"), "q3": r.get("Q3"), "source": "jolpica",
                     "team_entity_id": entity})
    out = pd.DataFrame(rows, columns=QUALIFYING_COLS)
    if out["driverId"].duplicated().any():
        raise MissingWeekendData(f"a driver appears twice in {season} round {rnd} qualifying")
    return out


def race_drivers(season: int, rnd: int, classified: set[int],
                 root: Path = UPCOMING_DIR) -> set[int]:
    """The weekend's race drivers: the FastF1 qualifying session's entry list.

    Every driver Jolpica classified must be on it. If one is not, the two
    sources disagree about who is racing, and that is refused, not resolved.
    """
    path = weekend_dir(season, rnd, root) / "results.csv"
    fetch = (f"Run src/fetch_fastf1.py --upcoming {season} {rnd} once qualifying has "
             "finished and settled.")
    if not path.exists():
        raise MissingWeekendData(f"no FastF1 session results for {season} round {rnd} at "
                                 f"{path}. {fetch}")
    res = F._rd(path)
    entry = res[(res["season"] == int(season)) & (res["round"] == int(rnd))
                & (res["session"] == "Qualifying")]
    ids = set(pd.to_numeric(entry["driverId"], errors="coerce").dropna().astype(int))
    if not ids:
        raise MissingWeekendData(f"the FastF1 qualifying session for {season} round {rnd} has "
                                 f"not been fetched. {fetch}")
    missing = sorted(classified - ids)
    if missing:
        raise MissingWeekendData(
            f"driverId {missing} is classified in Jolpica's qualifying but absent from FastF1's "
            "qualifying entry list; the sources disagree about who is racing.")
    return ids


def practice_laps(season: int, rnd: int, race_id: int, race_driver_ids: set[int],
                  root: Path = UPCOMING_DIR) -> pd.DataFrame:
    """This weekend's practice laps, keyed to the in-memory race, with the race
    drivers marked from the qualifying entry list."""
    path = weekend_dir(season, rnd, root) / "laps.csv"
    if not path.exists():
        raise MissingWeekendData(
            f"no practice laps for {season} round {rnd} at {path}. Run "
            f"src/fetch_fastf1.py --upcoming {season} {rnd} after qualifying.")
    laps = F._rd(path)
    laps = laps[(laps["season"] == int(season)) & (laps["round"] == int(rnd))
                & laps["session"].isin(PRACTICE_SESSIONS)].copy()
    if laps.empty:
        raise MissingWeekendData(f"{path} holds no practice laps for {season} round {rnd}")
    laps["raceId"] = int(race_id)
    laps["driverId"] = pd.to_numeric(laps["driverId"], errors="coerce").astype("Int64")
    laps["is_race_driver"] = laps["driverId"].isin(list(race_driver_ids)).fillna(False).astype(bool)
    return laps.drop(columns=["season", "round"])


def augment(tables: dict[str, pd.DataFrame], race: pd.Series, *,
            cache_dir: Path = J.CACHE_DIR, processed: Path = F.PROCESSED,
            upcoming_dir: Path = UPCOMING_DIR) -> dict[str, pd.DataFrame]:
    """A copy of ``tables`` that also holds this weekend's qualifying and
    practice for ``race``. The inputs are not modified."""
    season, rnd, race_id = int(race["year"]), int(race["round"]), int(race["raceId"])
    if (tables["qualifying"]["raceId"] == race_id).any():
        raise ValueError(f"raceId {race_id} already has qualifying rows; the upcoming path is "
                         "only for a race that has not run")
    try:
        payload = J.read_cached_all(f"{season}/qualifying", cache_dir)
    except J.CacheMiss as e:
        raise MissingWeekendData(str(e)) from e

    ids = Path(processed) / "id_maps"
    drivers = pd.read_csv(ids / "drivers.csv")
    constructors = pd.read_csv(ids / "constructors.csv")
    entities = pd.read_csv(Path(processed) / "team_entities.csv")
    q = qualifying_rows(payload, season, rnd, race_id,
                        dict(zip(drivers["driverRef"], drivers["driverId"].astype(int))),
                        dict(zip(constructors["constructorRef"],
                                 constructors["constructorId"].astype(int))),
                        entities)
    drivers_racing = race_drivers(season, rnd, set(q["driverId"].astype(int)), upcoming_dir)
    laps = practice_laps(season, rnd, race_id, drivers_racing, upcoming_dir)

    out = dict(tables)
    out["qualifying"] = pd.concat([tables["qualifying"], q], ignore_index=True)
    out["laps"] = pd.concat([tables["laps"], laps], ignore_index=True) if len(tables["laps"]) \
        else laps.reset_index(drop=True)
    return out
