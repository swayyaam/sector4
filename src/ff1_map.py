"""Map FastF1 entities onto our integer IDs.

Drivers are matched on **car number + season**, with team as a tie-break --
never on name. Names differ in accenting and formatting between sources
("Hulkenberg" vs "Hulkenberg"), and a name match would also silently join two
different drivers who share a surname.
"""
from __future__ import annotations

import unicodedata
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"


def norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


class IdMapper:
    def __init__(self, processed: Path = PROCESSED):
        rd = lambda n: pd.read_csv(processed / f"{n}.csv", keep_default_na=False,  # noqa: E731
                                   na_values=[r"\N", ""], low_memory=False)
        self.races = rd("races")
        self.drivers = rd("drivers").set_index("driverId")
        self.constructors = rd("constructors").set_index("constructorId")
        ds = rd("driver_seasons")
        ds["team"] = ds["constructorId"].map(self.constructors["name"])
        self.driver_seasons = ds
        self._race = {(int(r.year), int(r.round)): int(r.raceId) for r in self.races.itertuples()}
        # (raceId, driverId) -> constructorId, straight from our own results.
        # This is authoritative and needs no team-name matching, which matters
        # because the sources disagree on names: FastF1 says "Racing Bulls"
        # where ours says "RB F1 Team".
        res = rd("results")
        self._team = {(int(r.raceId), int(r.driverId)): int(r.constructorId)
                      for r in res.itertuples() if pd.notna(r.constructorId)}
        spr = rd("sprint_results")
        for r in spr.itertuples():
            self._team.setdefault((int(r.raceId), int(r.driverId)), int(r.constructorId))

    def race_id(self, year: int, rnd: int) -> int | None:
        return self._race.get((int(year), int(rnd)))

    def driver_id(self, year: int, number, team_name: str | None = None) -> tuple[int | None, str]:
        """(driverId, reason). reason is '' on success."""
        try:
            num = int(float(number))
        except (TypeError, ValueError):
            return None, f"unparseable car number {number!r}"
        pool = self.driver_seasons[self.driver_seasons["year"] == int(year)]
        cand = pool[pool["number"] == num]
        if len(cand) == 0:
            return None, f"no driver_seasons row for number {num} in {year}"
        # A driver who changes team mid-season has several rows for the same
        # number (Lawson ran 3 races for Red Bull and 11 for Racing Bulls in
        # 2026). Several rows is not ambiguity -- several *drivers* is.
        ids = sorted({int(x) for x in cand["driverId"]})
        if len(ids) == 1:
            return ids[0], ""
        if team_name:
            t = norm(team_name)
            hits = sorted({int(r.driverId) for r in cand.itertuples()
                           if isinstance(r.team, str)
                           and (norm(r.team) in t or t.split()[0] in norm(r.team))})
            if len(hits) == 1:
                return hits[0], ""
        return None, f"number {num} in {year} maps to {len(ids)} drivers {ids} (team={team_name!r})"

    def constructor_id(self, race_id: int, driver_id: int | None,
                       year: int | None = None, team_name: str | None = None
                       ) -> tuple[int | None, str]:
        """Team for a driver at a race, from our own results table.

        Falls back to the driver's team(s) that season only when the driver has
        no result for the race -- e.g. an FP1-only stand-in.
        """
        if driver_id is not None:
            cid = self._team.get((int(race_id), int(driver_id)))
            if cid is not None:
                return cid, ""
            if year is not None:
                rows = self.driver_seasons[(self.driver_seasons["year"] == int(year))
                                           & (self.driver_seasons["driverId"] == int(driver_id))]
                cids = sorted({int(x) for x in rows["constructorId"]})
                if len(cids) == 1:
                    return cids[0], ""
                if len(cids) > 1:
                    return None, (f"driver {driver_id} has no result at race {race_id} and drove "
                                  f"for {cids} in {year}; cannot attribute")
        return None, (f"no result row for driver {driver_id} at race {race_id} "
                      f"(FastF1 team {team_name!r})")

    def verify_name(self, driver_id: int, last_name: str) -> bool:
        return norm(self.drivers.loc[driver_id, "surname"]) == norm(last_name)
