"""Pull FastF1 session data for 2018 onward into ./data/enriched/.

Design notes
------------
* Driven off **our own races table**, not FastF1's schedule, so every row is
  keyed to an existing raceId by construction and no not-yet-run event can leak
  in.
* **Reverse chronological** (2026 back to 2018): if the run is interrupted, what
  landed is the most relevant slice.
* FastF1's own limiter allows 4 requests/second (it sleeps) but caps at 500 per
  hour by *raising* ``RateLimitExceededError`` rather than waiting -- and it
  counts the refused call too, so retrying digs the hole deeper. ``RateBudget``
  attaches to FastF1's transport and claims a slot before each request, so the
  cap is never reached. Roughly 8 requests go out per session.
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
from ff1_map import IdMapper, reserve_key  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "raw" / "fastf1"
OUT = ROOT / "data" / "enriched"
MANIFEST = OUT / "_fetch_manifest.json"

FIRST_SEASON = 2018
RATE_SLEEP = 300        # fallback wait if the cap is somehow still hit
RATE_MAX_WAITS = 24
RATE_LOG = CACHE / "_rate_log.json"
RATE_MAX_PER_HOUR = 460   # FastF1 caps at 500/h; leave headroom
RATE_SOFT_FRACTION = 0.7  # start spacing requests out once this much is spent
RATE_WINDOW = 3600.0

log = logging.getLogger("ff1")


class RateBudget:
    """Pace requests so FastF1's hourly cap is never actually hit.

    FastF1's limiter appends a timestamp *before* deciding whether to raise, so
    a refused call still consumes a slot and retrying pushes recovery further
    away rather than closer. Two of those episodes cost one run 7.8 hours of
    zero progress. The only reliable defence is to never trigger it.

    Counting happens at the point FastF1 itself counts. One call to
    ``_SessionWithRateLimiting.send`` is exactly one append to its deque,
    whether the response is a 200, a 404, or a body identical to one already on
    disk. ``attach`` wraps that method so a slot is claimed immediately before
    the request goes out.

    The previous version inferred the count from new files appearing in the
    cache directory, which missed every re-fetch, every failure, and every HTTP
    call that does not land as a .ff1pkl. After one full pull the cache held
    7,667 files against 8,266 distinct cached responses -- and that gap is a
    floor, because a repeated URL overwrites its row instead of adding one. The
    shortfall surfaced in the logs as ``549/460 used this hour``: a 19%
    overshoot into the very cap the budget existed to stay under.
    """

    def __init__(self, path: Path = RATE_LOG, per_hour: int = RATE_MAX_PER_HOUR):
        self.path = path
        self.per_hour = per_hour
        self.soft = int(per_hour * RATE_SOFT_FRACTION)
        self.stamps: list[float] = []
        self.attached = False
        # Requests this process made. The persisted window spans restarts, so
        # it is the wrong thing to reconcile against FastF1's in-memory deque.
        self.spent_here = 0
        if path.exists():
            try:
                self.stamps = [float(x) for x in json.loads(path.read_text())]
            except Exception:
                # A truncated log must not read as "nothing spent yet": that is
                # how a crash mid-write would hand the next run a clean budget
                # and walk it straight into the cap.
                log.warning("rate log unreadable; assuming the budget is fully spent")
                self.stamps = [time.time()] * per_hour

    # ------------------------------------------------------------- accounting
    def _prune(self) -> None:
        cutoff = time.time() - RATE_WINDOW
        self.stamps = [t for t in self.stamps if t > cutoff]

    def used(self) -> int:
        self._prune()
        return len(self.stamps)

    def record(self, n: int = 1) -> None:
        now = time.time()
        self.stamps.extend([now] * max(n, 0))
        self._prune()
        self._flush()

    def _flush(self) -> None:
        """Persist atomically. A half-written file is worse than a stale one."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps([round(t, 3) for t in self.stamps]))
        tmp.replace(self.path)

    # ----------------------------------------------------------------- pacing
    def _soft_delay(self) -> float:
        """Spacing to apply before the next request.

        Below the soft threshold there is headroom, so requests go out at full
        speed. Above it the interval ramps toward the sustainable one, which
        turns the old pattern -- sprint into the cap, then stop dead for the
        remainder of the hour -- into a glide.
        """
        used = len(self.stamps)
        if used < self.soft:
            return 0.0
        span = max(self.per_hour - self.soft, 1)
        frac = min((used - self.soft) / span, 1.0)
        return frac * (RATE_WINDOW / self.per_hour)

    def wait_for(self, need: int = 1) -> float:
        """Block until `need` slots are free in the trailing hour."""
        total = 0.0
        while True:
            self._prune()
            free = self.per_hour - len(self.stamps)
            if free >= need:
                return total
            # sleep until enough of the oldest entries fall out of the window
            k = need - free
            oldest = sorted(self.stamps)[:k]
            wait = max(1.0, oldest[-1] + RATE_WINDOW - time.time() + 1)
            log.info("    pacing: %d/%d used this hour, need %d slots - waiting %.0fs",
                     len(self.stamps), self.per_hour, need, wait)
            time.sleep(wait)
            total += wait

    def acquire(self) -> None:
        """Claim one slot, blocking as long as necessary, then spend it."""
        self.wait_for(1)
        delay = self._soft_delay()
        if delay > 0:
            time.sleep(delay)
        self.record(1)
        self.spent_here += 1

    # ------------------------------------------------------------- attachment
    def attach(self) -> None:
        """Route every FastF1 network request through this budget.

        Wrapping ``send`` rather than the cached session means cache hits are
        not counted: requests_cache short-circuits them before ``send`` is
        reached, and FastF1's own limiter never sees them either. What is
        counted here is exactly what the cap counts.
        """
        from fastf1 import req

        cls = req._SessionWithRateLimiting
        if getattr(cls.send, "_sector4_budget", None) is not None:
            self.attached = True
            return
        original = cls.send
        budget = self

        def send(self, request, **kwargs):  # noqa: ANN001 - mirrors requests.Session.send
            budget.acquire()
            return original(self, request, **kwargs)

        send._sector4_budget = budget
        cls.send = send
        self.attached = True

    def fastf1_usage(self) -> int | None:
        """What FastF1's own limiter believes has been spent, for reconciliation.

        Private API, so a miss returns None rather than raising: this is a
        cross-check on our own count, never the thing the pacing depends on.
        """
        try:
            from fastf1 import req

            cutoff = time.time() - RATE_WINDOW
            for limiters in req._SessionWithRateLimiting._RATE_LIMITS.values():
                for lim in limiters:
                    info = getattr(lim, "_info", "")
                    stamps = getattr(lim, "_timestamps", None)
                    if stamps is not None and "any API" in info:
                        return sum(1 for t in stamps if t > cutoff)
        except Exception:
            return None
        return None


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


def with_rate_retry(fn, what: str):
    """Run fn(), sleeping off FastF1's hourly cap rather than failing."""
    from fastf1.exceptions import RateLimitExceededError
    for attempt in range(RATE_MAX_WAITS):
        try:
            return fn()
        except RateLimitExceededError as e:
            log.warning("    hourly rate cap hit (%s) - sleeping %ds (wait %d/%d) [%s]",
                        e, RATE_SLEEP, attempt + 1, RATE_MAX_WAITS, what)
            time.sleep(RATE_SLEEP)
    raise RuntimeError(f"gave up on {what} after {RATE_MAX_WAITS} rate-limit waits")


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

    # FastF1's DriverId is the Ergast driverRef, so this is an exact join and
    # works for FP1-only reserves who have no result row and often no number.
    num_to_id: dict[str, int] = {}
    num_is_race: dict[str, bool] = {}
    num_to_ref: dict[str, str] = {}
    num_via: dict[str, str] = {}
    num_reserve: dict[str, str] = {}
    for _, r in s.results.iterrows():
        num = str(r["DriverNumber"])
        ref = r.get("DriverId")
        num_to_ref[num] = ref
        m = mapper.driver(race_id, year, ref, r["DriverNumber"], r.get("LastName"))
        base = {"raceId": race_id, "year": year, "session": session_name, "number": num,
                "driverRef": ref, "abbrev": r.get("Abbreviation"),
                "name": f"{r.get('FirstName')} {r.get('LastName')}".strip(),
                "teamRef": r.get("TeamId"), "team": r.get("TeamName")}
        if m.driver_id is None:
            # Practice-only participant: keyed separately, never given a driverId.
            rk = reserve_key(year, base["name"], race_id, session_name, num)
            num_reserve[num] = rk
            unmapped.append({**base, "kind": "practice_participant",
                             "reserve_key": rk, "reason": m.reason})
            continue
        num_to_id[num] = m.driver_id
        num_is_race[num] = m.is_race_driver
        num_via[num] = m.via
        if m.number_mismatch:
            unmapped.append({**base, "kind": "number_mismatch", "reserve_key": None,
                             "reason": m.number_mismatch})

    # ---- laps
    laps = pd.DataFrame()
    if s.laps is not None and len(s.laps):
        L = s.laps.copy()
        laps = pd.DataFrame(index=range(len(L)))
        laps["raceId"], laps["year"], laps["session"] = race_id, year, session_name
        laps["driverNumber"] = L["DriverNumber"].astype(str).values
        laps["driverId"] = laps["driverNumber"].map(num_to_id).astype("Int64")
        laps["driverRef"] = laps["driverNumber"].map(num_to_ref)
        laps["is_race_driver"] = laps["driverNumber"].map(num_is_race).astype("boolean")
        laps["id_matched_via"] = laps["driverNumber"].map(num_via)
        laps["reserve_key"] = laps["driverNumber"].map(num_reserve)
        laps["is_race_driver"] = laps["is_race_driver"].fillna(False).astype("boolean")
        for c in LAP_COLS:
            if c not in L.columns:
                laps[c] = pd.NA
            elif pd.api.types.is_timedelta64_dtype(L[c]):
                laps[c] = td_ms(L[c]).values
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
        results["driverRef"] = R["DriverId"].values
        results["is_race_driver"] = results["driverNumber"].map(num_is_race).astype("boolean")
        results["id_matched_via"] = results["driverNumber"].map(num_via)
        results["reserve_key"] = results["driverNumber"].map(num_reserve)
        results["is_race_driver"] = results["is_race_driver"].fillna(False).astype("boolean")
        results["teamRef"] = R["TeamId"].values
        results["teamName"] = R["TeamName"].values
        cids = []
        for num, tref in zip(results["driverNumber"], results["teamRef"]):
            cid, why = mapper.constructor(race_id, num_to_id.get(num), tref)
            cids.append(cid)
            if cid is None:
                unmapped.append({"raceId": race_id, "year": year, "session": session_name,
                                 "number": num, "driverRef": num_to_ref.get(num), "abbrev": None,
                                 "name": None, "teamRef": tref, "team": None,
                                 "kind": "unmapped_team", "reserve_key": num_reserve.get(num),
                                 "reason": why})
        results["constructorId"] = pd.array(cids, dtype="Int64")
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

    budget = RateBudget()
    budget.attach()
    log.info("rate budget: %d requests used in the trailing hour (cap %d, spacing from %d)",
             budget.used(), budget.per_hour, budget.soft)
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
            # Wrapped too: losing a whole season to a rate cap on the schedule
            # call would be a silent, expensive gap.
            sched = with_rate_retry(
                lambda: fastf1.get_event_schedule(int(year), include_testing=False),
                f"{year} schedule")
        except Exception as e:
            log.error("  cannot load schedule: %s", e)
            manifest["failures"][f"{year}-schedule"] = f"{type(e).__name__}: {str(e)[:200]}"
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
                # Deliberately NOT skipped when already in the manifest: the
                # season CSV is rewritten whole each run, so skipping a cached
                # session would silently drop its rows from the output. The
                # FastF1 cache makes a re-read ~0.3s, which is the right place
                # for that cost to land.
                already = key in done
                if args.dry_run:
                    got.append(sn)
                    continue
                try:
                    # No reservation here any more. The budget is attached to
                    # FastF1's transport, so every request this call makes --
                    # and only the ones it actually makes -- claims its own
                    # slot on the way out.
                    sess = load_session(fastf1, int(year), ev["EventName"], sn)
                    out = extract(sess, int(rr.raceId), int(year), sn, mapper)
                    append(frames, out)
                    done[key] = {"raceId": int(rr.raceId), "laps": len(out["laps"]),
                                 "unmapped": len(out["unmapped"])}
                    manifest["failures"].pop(key, None)
                    got.append(f"{sn}({len(out['laps'])}{'c' if already else ''})")
                    if not already:
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

    # Reconcile against FastF1's own tally. These should agree exactly; a gap
    # means the hook is no longer sitting where the cap is counted, which is
    # the failure that is otherwise invisible until a run stalls for hours.
    theirs = budget.fastf1_usage()
    if theirs is None:
        log.warning("could not read FastF1's own request count - budget unverified")
    else:
        # Only this process's requests are comparable: our window is restored
        # from disk across restarts, FastF1's deque starts empty every time.
        drift = budget.spent_here - theirs
        level = log.info if abs(drift) <= 1 else log.warning
        level("rate budget: %d requests this run, %d seen by FastF1 (drift %+d); "
              "%d/%d spent in the trailing hour",
              budget.spent_here, theirs, drift, budget.used(), budget.per_hour)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
