"""Map FastF1 entities onto our integer IDs.

FastF1's ``DriverId`` and ``TeamId`` are the Ergast-style refs
(``max_verstappen``, ``rb``), the same natural keys our own tables use. So the
join is an **exact string match on the ref**, never a name match and never a
guess:

* ``DriverId`` -> ``drivers.driverRef``. This is the only key that works for
  FP1-only reserves and rookies: they have no result row, and 23 of the 25 that
  Jolpica lists carry no permanent number either, so car number cannot identify
  them.
* ``TeamId`` -> ``constructors.constructorRef``. Team *names* disagree between
  sources -- FastF1 says "Racing Bulls" where ours says "RB F1 Team" -- but both
  call it ``rb``.

FastF1 does not always supply the ref: **Sprint Qualifying sessions carry no
``DriverId`` at all**, and the odd individual row is blank elsewhere. So car
number + season is kept as a fallback key. It is safe to use as one -- no
(year, number) pair maps to more than one driver from 2018 on -- but it cannot
identify a reserve, hence ref first. When both keys are available they are
cross-checked, and a disagreement is reported rather than silently resolved.

For a driver who actually raced, the team comes from our own ``results`` row for
that race, which is authoritative and beats any season-level lookup when a
driver changed team mid-season.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"


def reserve_key(year: int, name: str | None, race_id: int, session: str, number) -> str:
    """Stable key for a practice-only participant.

    Practice-only drivers never enter the drivers table (it stays race drivers
    only, as Ergast has it), so they need their own identity. A named reserve is
    keyed on season + normalised name; an entry FastF1 gives no name for is
    keyed on where it appeared, which keeps two different unnamed drivers from
    colliding on a shared car number.
    """
    n = norm(name) if name else ""
    if n and n not in ("nan", "none"):
        return f"{int(year)}_{n.replace(' ', '_')}"
    sess = norm(session).replace(" ", "")
    return f"unknown_{int(year)}_r{int(race_id)}_{sess}_{number}"


def norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


@dataclass
class DriverMatch:
    driver_id: int | None
    is_race_driver: bool
    reason: str = ""
    number_mismatch: str = ""
    via: str = ""          # "ref" or "number" -- which key resolved it


class IdMapper:
    def __init__(self, processed: Path = PROCESSED):
        def rd(n):
            return pd.read_csv(processed / f"{n}.csv", keep_default_na=False,
                               na_values=[r"\N", ""], low_memory=False)

        self.races = rd("races")
        self.drivers = rd("drivers")
        self.constructors = rd("constructors")
        ds = rd("driver_seasons")
        self.driver_seasons = ds

        self._race = {(int(r.year), int(r.round)): int(r.raceId) for r in self.races.itertuples()}
        self._dref = {str(r.driverRef): int(r.driverId) for r in self.drivers.itertuples()}
        self._cref = {str(r.constructorRef): int(r.constructorId)
                      for r in self.constructors.itertuples()}
        self._surname = {int(r.driverId): str(r.surname) for r in self.drivers.itertuples()}

        # (raceId, driverId) -> constructorId, and the set of drivers who
        # actually took part in each race (race or sprint classification).
        self._team: dict[tuple[int, int], int] = {}
        self._raced: set[tuple[int, int]] = set()
        for tbl in ("results", "sprint_results"):
            t = rd(tbl)
            for r in t.itertuples():
                if pd.notna(r.constructorId):
                    self._team.setdefault((int(r.raceId), int(r.driverId)), int(r.constructorId))
                self._raced.add((int(r.raceId), int(r.driverId)))
        # (year, driverId) -> car numbers used that season, for cross-checking
        self._season_num: dict[tuple[int, int], set[int]] = {}
        self._by_num: dict[tuple[int, int], set[int]] = {}
        for r in ds.itertuples():
            if pd.notna(r.number):
                self._season_num.setdefault((int(r.year), int(r.driverId)), set()).add(int(r.number))
                self._by_num.setdefault((int(r.year), int(r.number)), set()).add(int(r.driverId))

    # ------------------------------------------------------------------ races
    def race_id(self, year: int, rnd: int) -> int | None:
        return self._race.get((int(year), int(rnd)))

    # ---------------------------------------------------------------- drivers
    def driver(self, race_id: int, year: int, driver_ref: str,
               number=None, last_name: str | None = None) -> DriverMatch:
        ref = "" if driver_ref is None else str(driver_ref).strip()
        if ref.lower() in ("", "nan", "none"):
            ref = ""
        did = self._dref.get(ref) if ref else None
        via = "ref"

        if did is None:
            # No usable ref (Sprint Qualifying never supplies one) -> fall back
            # to car number + season, which is unique from 2018 on.
            try:
                num = int(float(number))
            except (TypeError, ValueError):
                num = None
            cands = self._by_num.get((int(year), num), set()) if num is not None else set()
            if len(cands) == 1:
                did, via = next(iter(cands)), "number"
            elif ref:
                return DriverMatch(None, False,
                                   f"driverRef {ref!r} is not in our drivers table and car "
                                   f"number {num} did not resolve it (new driver, needs a "
                                   f"reviewed id)")
            elif len(cands) > 1:
                return DriverMatch(None, False,
                                   f"no driverRef supplied and car number {num} in {year} maps "
                                   f"to {sorted(cands)}")
            else:
                return DriverMatch(None, False,
                                   f"no driverRef supplied and car number {num} is unknown in "
                                   f"{year} (likely a reserve; needs a reviewed id)")
        raced = (int(race_id), did) in self._raced
        mismatch = ""
        if number is not None and via == "ref":
            try:
                num = int(float(number))
            except (TypeError, ValueError):
                num = None
            known = self._season_num.get((int(year), did))
            if num is not None and known and num not in known:
                mismatch = (f"FastF1 car number {num} not among {sorted(known)} recorded for "
                            f"driverId {did} in {year}")
        if last_name and norm(self._surname[did]) != norm(last_name):
            mismatch = (mismatch + "; " if mismatch else "") + \
                       f"surname {last_name!r} vs ours {self._surname[did]!r}"
        return DriverMatch(did, raced, "", mismatch, via)

    # ------------------------------------------------------------ constructors
    def constructor(self, race_id: int, driver_id: int | None,
                    team_ref: str | None) -> tuple[int | None, str]:
        """Team for a driver at a race: our own result first, then the ref."""
        if driver_id is not None:
            cid = self._team.get((int(race_id), int(driver_id)))
            if cid is not None:
                return cid, ""
        if team_ref:
            cid = self._cref.get(str(team_ref).strip())
            if cid is not None:
                return cid, ""
            return None, f"teamRef {team_ref!r} is not in our constructors table"
        return None, "no team reference available"
