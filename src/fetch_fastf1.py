"""Pull FastF1 session data for 2018 onward into ./data/enriched/.

Design notes
------------
* Driven off **our own races table**, not FastF1's schedule, so every row is
  keyed to an existing raceId by construction and no not-yet-run event can leak
  in.
* **Reverse chronological** (2026 back to 2018): if the run is interrupted, what
  landed is the most relevant slice.
* FastF1's own limiter allows 4 requests/second (it sleeps) but caps at 500 per
  hour by *raising* ``RateLimitExceededError`` rather than waiting. So the cap
  is caught here and slept off. Roughly 8 requests go out per session.
* Everything is cached under data/raw/fastf1/, and a manifest records finished
  sessions, so a rerun costs nothing for work already done.
* Tyre compound names are stored **as reported**. 2018 uses absolute names
  (SUPERSOFT, ULTRASOFT) and later seasons the relative SOFT/MEDIUM/HARD
  scheme; mapping between them needs each race's Pirelli allocation and is a
  modelling decision, not something to guess at load time.

Usage:
    python src/fetch_fastf1.py [--seasons 2026 2025] [--limit-sessions N] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ff1_map import IdMapper  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "raw" / "fastf1"
OUT = ROOT / "data" / "enriched"
MANIFEST = OUT / "_fetch_manifest.json"

FIRST_SEASON = 2018
RATE_SLEEP = 300        # seconds to wait when the hourly cap is hit
RATE_MAX_WAITS = 24     # give up after two hours of waiting on one session

log = logging.getLogger("ff1")


def td_ms(s: pd.Series) -> pd.Series:
    """Timedelta column -> integer milliseconds, preserving nulls."""
    return (s.dt.total_seconds() * 1000).round().astype("Int64")


def load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text())
    return {"sessions": {}, "failures": {}}


def save_manifest(m: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(m, indent=2, sort_keys=True))


def load_session(fastf1, year: int, event_name: str, session_name: str):
    """Load one session, sleeping off FastF1's hourly rate cap."""
    from fastf1.exceptions import RateLimitExceededError
    for attempt in range(RATE_MAX_WAITS):
        try:
            s = fastf1.get_session(year, event_name, session_name)
            s.load(laps=True, telemetry=False, weather=True, messages=True)
            return s
        except RateLimitExceededError as e:
            log.warning("    hourly rate cap hit (%s) - sleeping %ds (wait %d/%d)",
                        e, RATE_SLEEP, attempt + 1, RATE_MAX_WAITS)
            time.sleep(RATE_SLEEP)
    raise RuntimeError(f"gave up on {year} {event_name} {session_name} after "
                       f"{RATE_MAX_WAITS} rate-limit waits")


LAP_COLS = ["LapNumber", "Stint", "LapTime", "Sector1Time", "Sector2Time", "Sector3Time",
            "PitInTime", "PitOutTime", "SpeedI1", "SpeedI2", "SpeedFL", "SpeedST",
            "IsPersonalBest", "Compound", "TyreLife", "FreshTyre", "TrackStatus",
            "Position", "Deleted", "DeletedReason", "IsAccurate", "LapStartTime"]


def extract(s, race_id: int, year: int, session_name: str, mapper: IdMapper) -> dict:
    """Pull the four tables out of a loaded session, keyed to our IDs."""
    unmapped: list[dict] = []

    # number -> driverId for this session, using the session's own team names
    num_to_id: dict[str, int] = {}
    for _, r in s.results.iterrows():
        did, why = mapper.driver_id(year, r["DriverNumber"], r.get("TeamName"))
        if did is None:
            unmapped.append({"raceId": race_id, "year": year, "session": session_name,
                             "number": str(r["DriverNumber"]), "abbrev": r.get("Abbreviation"),
                             "name": f"{r.get('FirstName')} {r.get('LastName')}".strip(),
                             "team": r.get("TeamName"), "reason": why})
        else:
            num_to_id[str(r["DriverNumber"])] = did
            if not mapper.verify_name(did, r.get("LastName", "")):
                unmapped.append({"raceId": race_id, "year": year, "session": session_name,
                                 "number": str(r["DriverNumber"]), "abbrev": r.get("Abbreviation"),
                                 "name": str(r.get("LastName")), "team": r.get("TeamName"),
                                 "reason": f"number matched driverId {did} but surname disagrees "
                                           f"({mapper.drivers.loc[did, 'surname']!r})"})

    # ---- laps
    laps = pd.DataFrame()
    if s.laps is not None and len(s.laps):
        L = s.laps.copy()
        laps = pd.DataFrame(index=range(len(L)))
        laps["raceId"], laps["year"], laps["session"] = race_id, year, session_name
        laps["driverNumber"] = L["DriverNumber"].astype(str).values
        laps["driverId"] = laps["driverNumber"].map(num_to_id).astype("Int64")
        for c in LAP_COLS:
            if c not in L.columns:
                laps[c] = pd.NA
            elif pd.api.types.is_timedelta64_dtype(L[c]):
                laps[c] = td_ms(L[c])
            else:
                laps[c] = L[c].values
        laps = laps.rename(columns={c: (c + "Ms") for c in
                                    ["LapTime", "Sector1Time", "Sector2Time", "Sector3Time",
                                     "PitInTime", "PitOutTime", "LapStartTime"] if c in laps.columns})

    # ---- weather
    weather = pd.DataFrame()
    if s.weather_data is not None and len(s.weather_data):
        W = s.weather_data.copy()
        weather = pd.DataFrame(index=range(len(W)))
        weather["raceId"], weather["year"], weather["session"] = race_id, year, session_name
        weather["timeMs"] = (td_ms(W["Time"]).values
                             if pd.api.types.is_timedelta64_dtype(W["Time"]) else W["Time"].values)
        for c in ["AirTemp", "TrackTemp", "Humidity", "Pressure", "Rainfall",
                  "WindDirection", "WindSpeed"]:
            weather[c] = W[c].values if c in W.columns else pd.NA

    # ---- session results
    results = pd.DataFrame()
    if s.results is not None and len(s.results):
        R = s.results.copy()
        results = pd.DataFrame(index=range(len(R)))
        results["raceId"], results["year"], results["session"] = race_id, year, session_name
        results["driverNumber"] = R["DriverNumber"].astype(str).values
        results["driverId"] = results["driverNumber"].map(num_to_id).astype("Int64")
        results["teamName"] = R["TeamName"].values
        _cids, _cwhy = [], []
        for _, rr_ in R.iterrows():
            did_ = num_to_id.get(str(rr_["DriverNumber"]))
            cid_, why_ = mapper.constructor_id(race_id, did_, year, rr_.get("TeamName"))
            _cids.append(cid_)
            if cid_ is None:
                _cwhy.append({"raceId": race_id, "year": year, "session": session_name,
                              "number": str(rr_["DriverNumber"]), "abbrev": rr_.get("Abbreviation"),
                              "name": str(rr_.get("LastName")), "team": rr_.get("TeamName"),
                              "reason": "constructor: " + why_})
        results["constructorId"] = pd.array(_cids, dtype="Int64")
        unmapped.extend(_cwhy)
        for c in ["Abbreviation", "Position", "ClassifiedPosition", "GridPosition",
                  "Status", "Points", "Laps"]:
            results[c] = R[c].values if c in R.columns else pd.NA
        for c in ["Q1", "Q2", "Q3", "Time"]:
            if c in R.columns and pd.api.types.is_timedelta64_dtype(R[c]):
                results[c + "Ms"] = td_ms(R[c]).values
            else:
                results[c + "Ms"] = pd.NA

    # ---- race control messages
    rcm = pd.DataFrame()
    if getattr(s, "race_control_messages", None) is not None and len(s.race_control_messages):
        M = s.race_control_messages.copy()
        rcm = pd.DataFrame(index=range(len(M)))
        rcm["raceId"], rcm["year"], rcm["session"] = race_id, year, session_name
        for c in ["Time", "Category", "Message", "Status", "Flag", "Scope", "Sector", "Lap"]:
            rcm[c] = M[c].values if c in M.columns else pd.NA
        if "Time" in rcm.columns:
            rcm["Time"] = rcm["Time"].astype(str)

    return {"laps": laps, "weather": weather, "results": results,
            "race_control": rcm, "unmapped": unmapped}


def append(frames: dict[str, list], out: dict) -> None:
    for k in ("laps", "weather", "results", "race_control"):
        if len(out[k]):
            frames[k].append(out[k])
    frames["unmapped"].extend(out["unmapped"])


def write_season(year: int, frames: dict[str, list]) -> dict[str, int]:
    counts = {}
    for k in ("laps", "weather", "results", "race_control"):
        d = OUT / k
        d.mkdir(parents=True, exist_ok=True)
        df = pd.concat(frames[k], ignore_index=True) if frames[k] else pd.DataFrame()
        df.to_csv(d / f"{year}.csv", index=False)
        counts[k] = len(df)
    if frames["unmapped"]:
        d = OUT / "unmapped"
        d.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(frames["unmapped"]).to_csv(d / f"{year}.csv", index=False)
    counts["unmapped"] = len(frames["unmapped"])
    return counts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="+", type=int)
    ap.add_argument("--limit-sessions", type=int)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
                        datefmt="%H:%M:%S")
    for noisy in ("fastf1", "fastf1.core", "fastf1.req", "fastf1._api", "fastf1.api"):
        logging.getLogger(noisy).setLevel(logging.ERROR)

    import fastf1
    from fastf1 import Cache
    CACHE.mkdir(parents=True, exist_ok=True)
    Cache.enable_cache(str(CACHE))

    mapper = IdMapper()
    races = mapper.races
    races = races[races["year"] >= FIRST_SEASON]
    seasons = args.seasons or sorted(races["year"].unique(), reverse=True)   # newest first
    manifest = load_manifest()
    done = manifest["sessions"]

    total_sessions = 0
    t_start = time.time()
    for year in seasons:
        yr_races = races[races["year"] == year].sort_values("round")
        log.info("=" * 74)
        log.info("SEASON %d  (%d races)", year, len(yr_races))
        try:
            sched = fastf1.get_event_schedule(int(year), include_testing=False)
        except Exception as e:
            log.error("  cannot load schedule: %s", e)
            continue
        frames = {"laps": [], "weather": [], "results": [], "race_control": [], "unmapped": []}
        for rr in yr_races.itertuples():
            ev = sched[sched["RoundNumber"] == int(rr.round)]
            if not len(ev):
                log.warning("  R%-2d %-32s NOT IN FASTF1 SCHEDULE", rr.round, rr.name)
                manifest["failures"][f"{year}-{rr.round}"] = "not in FastF1 schedule"
                continue
            ev = ev.iloc[0]
            names = [ev[f"Session{i}"] for i in range(1, 6) if ev.get(f"Session{i}")]
            got = []
            for sn in names:
                key = f"{year}|{int(rr.round)}|{sn}"
                if key in done and not args.dry_run:
                    got.append(f"{sn}=cached")
                    continue
                if args.dry_run:
                    got.append(sn)
                    continue
                try:
                    sess = load_session(fastf1, int(year), ev["EventName"], sn)
                    out = extract(sess, int(rr.raceId), int(year), sn, mapper)
                    append(frames, out)
                    done[key] = {"raceId": int(rr.raceId), "laps": len(out["laps"]),
                                 "unmapped": len(out["unmapped"])}
                    manifest["failures"].pop(key, None)
                    got.append(f"{sn}({len(out['laps'])})")
                    total_sessions += 1
                except Exception as e:
                    log.warning("    %s / %s FAILED: %s: %s", rr.name, sn, type(e).__name__,
                                str(e)[:110])
                    manifest["failures"][key] = f"{type(e).__name__}: {str(e)[:200]}"
                if args.limit_sessions and total_sessions >= args.limit_sessions:
                    break
            log.info("  R%-2d %-32s %s", rr.round, rr.name, ", ".join(got))
            save_manifest(manifest)
            if args.limit_sessions and total_sessions >= args.limit_sessions:
                break
        if not args.dry_run:
            # Re-read any cached sessions for this season so the season file is complete.
            counts = write_season(int(year), frames)
            log.info("  season %d written: %s", year, counts)
        save_manifest(manifest)
        log.info("  elapsed %.1f min, %d sessions fetched this run", (time.time()-t_start)/60,
                 total_sessions)
        if args.limit_sessions and total_sessions >= args.limit_sessions:
            log.info("session limit reached"); break

    save_manifest(manifest)
    log.info("=" * 74)
    log.info("DONE. %d sessions fetched this run, %d recorded total, %d failures, %.1f min",
             total_sessions, len(done), len(manifest["failures"]), (time.time()-t_start)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
