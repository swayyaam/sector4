"""Fetch everything from 2024 onward from the Jolpica F1 API.

Design notes
------------
* Only races that have actually finished are fetched. A race counts as
  finished when its scheduled start (UTC) is more than FINISH_GRACE_HOURS ago.
  A past race that returns no results is reported as cancelled/postponed
  rather than silently skipped.
* Results get amended after the flag (penalties, disqualifications, appeals),
  so any race within NOT_FINAL_DAYS is treated as provisional: its payloads are
  always re-fetched and diffed against the cached copy, and every change logged.
* Everything else is served from ./data/raw/jolpica/, so a rerun after a new
  race only costs the new race plus the provisional window.
* Season-wide endpoints (results, qualifying, sprint) are paged in one go
  instead of per round -- roughly 5 requests instead of 24 for a season, which
  matters a lot against a 500 requests/hour budget.

Usage:
    python src/fetch_jolpica.py [--seasons 2024 2025 2026] [--skip-laps] [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jolpica_client import CACHE_DIR, JolpicaClient  # noqa: E402

log = logging.getLogger("fetch")

ROOT = Path(__file__).resolve().parents[1]
FINISH_GRACE_HOURS = 4      # a race is "done" this long after lights out
NOT_FINAL_DAYS = 30         # results within this window may still be amended
DEFAULT_SEASONS = [2024, 2025, 2026]


# --------------------------------------------------------------------- timing
def race_start_utc(race: dict) -> dt.datetime:
    """Scheduled start as an aware UTC datetime. Time is optional in the API."""
    d = dt.date.fromisoformat(race["date"])
    t = race.get("time")
    if t:
        return dt.datetime.fromisoformat(f"{race['date']}T{t.replace('Z', '+00:00')}")
    return dt.datetime.combine(d, dt.time(23, 59), tzinfo=dt.timezone.utc)


def is_finished(race: dict, now: dt.datetime) -> bool:
    return race_start_utc(race) + dt.timedelta(hours=FINISH_GRACE_HOURS) <= now


def is_provisional(race: dict, now: dt.datetime) -> bool:
    """Recent enough that the classification could still change."""
    return race_start_utc(race) >= now - dt.timedelta(days=NOT_FINAL_DAYS)


# ---------------------------------------------------------------- diff on refetch
def fetch_with_diff(client: JolpicaClient, path: str, *, force: bool,
                    extra: dict | None = None, changes: list | None = None) -> list:
    """Fetch (optionally forcing a refresh) and log any row that changed."""
    before = None
    if force:
        cp = client._cache_path(path, {"limit": 100, "offset": 0, **(extra or {})})
        if cp.exists():
            try:
                before = client.get_all(path, force=False, extra=extra)
            except Exception:
                before = None
    rows = client.get_all(path, force=force, extra=extra)
    if force and before is not None and changes is not None:
        b = json.dumps(before, sort_keys=True)
        a = json.dumps(rows, sort_keys=True)
        if b != a:
            changes.append({"endpoint": path, "before_rows": len(before), "after_rows": len(rows)})
            log.warning("  CHANGED since cached: %s (%d -> %d rows)", path, len(before), len(rows))
    return rows


# --------------------------------------------------------------------- season
def fetch_season(client: JolpicaClient, year: int, now: dt.datetime,
                 skip_laps: bool = False, dry_run: bool = False) -> dict:
    log.info("=" * 78)
    log.info("SEASON %d", year)
    log.info("=" * 78)

    schedule = client.get_all(f"{year}/races", force=True)
    finished = [r for r in schedule if is_finished(r, now)]
    upcoming = [r for r in schedule if not is_finished(r, now)]
    provisional = [r for r in finished if is_provisional(r, now)]
    log.info("  scheduled=%d  finished=%d  upcoming=%d  provisional(<%dd)=%d",
             len(schedule), len(finished), len(upcoming), NOT_FINAL_DAYS, len(provisional))
    if upcoming:
        log.info("  next up: R%s %s (%s)", upcoming[0]["round"], upcoming[0]["raceName"], upcoming[0]["date"])
    if provisional:
        log.info("  provisional: %s", ", ".join(f"R{r['round']}" for r in provisional))

    out: dict = {"year": year, "schedule": schedule, "finished_rounds": [int(r["round"]) for r in finished],
                 "changes": [], "cancelled": [], "missing": {}}
    if dry_run:
        return out

    force_season = bool(provisional)
    ch = out["changes"]

    # Season-wide tables (cheap: ~5 requests each instead of one per round).
    out["results"] = fetch_with_diff(client, f"{year}/results", force=force_season, changes=ch)
    out["qualifying"] = fetch_with_diff(client, f"{year}/qualifying", force=force_season, changes=ch)
    out["sprint"] = fetch_with_diff(client, f"{year}/sprint", force=force_season, changes=ch)
    out["drivers"] = client.get_all(f"{year}/drivers", force=force_season)
    out["constructors"] = client.get_all(f"{year}/constructors", force=force_season)
    out["circuits"] = client.get_all(f"{year}/circuits", force=force_season)
    out["status"] = client.get_all(f"{year}/status", force=force_season)
    log.info("  season tables: results=%d races, quali=%d, sprint=%d, drivers=%d, constructors=%d, circuits=%d, status=%d",
             len(out["results"]), len(out["qualifying"]), len(out["sprint"]),
             len(out["drivers"]), len(out["constructors"]), len(out["circuits"]), len(out["status"]))

    # A finished race with no results row is cancelled or abandoned.
    have_results = {int(r["round"]) for r in out["results"]}
    for r in finished:
        if int(r["round"]) not in have_results:
            out["cancelled"].append({"round": int(r["round"]), "raceName": r["raceName"], "date": r["date"]})
            log.warning("  NO RESULTS for finished race R%s %s (%s) -- cancelled/abandoned?",
                        r["round"], r["raceName"], r["date"])

    # Per-round tables.
    out["driver_standings"], out["constructor_standings"] = [], []
    out["pit_stops"], out["laps"] = [], []
    for r in finished:
        rnd = int(r["round"])
        if rnd not in have_results:
            continue
        prov = is_provisional(r, now)
        tag = " [provisional]" if prov else ""
        log.info("  R%-2d %-34s%s", rnd, r["raceName"], tag)

        ds = fetch_with_diff(client, f"{year}/{rnd}/driverstandings", force=prov, changes=ch)
        cs = fetch_with_diff(client, f"{year}/{rnd}/constructorstandings", force=prov, changes=ch)
        out["driver_standings"].append({"round": rnd, "lists": ds})
        out["constructor_standings"].append({"round": rnd, "lists": cs})

        ps = fetch_with_diff(client, f"{year}/{rnd}/pitstops", force=prov, changes=ch)
        out["pit_stops"].append({"round": rnd, "races": ps})
        if not ps:
            out["missing"].setdefault("pit_stops", []).append(rnd)

        if not skip_laps:
            lp = fetch_with_diff(client, f"{year}/{rnd}/laps", force=prov, changes=ch)
            out["laps"].append({"round": rnd, "races": lp})
            if not lp:
                out["missing"].setdefault("laps", []).append(rnd)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch F1 data from the Jolpica API into ./data/raw/jolpica/")
    ap.add_argument("--seasons", nargs="+", type=int, default=DEFAULT_SEASONS)
    ap.add_argument("--skip-laps", action="store_true", help="skip lap times (~75%% of all requests)")
    ap.add_argument("--dry-run", action="store_true", help="show what would be fetched, fetch only schedules")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")

    now = dt.datetime.now(dt.timezone.utc)
    log.info("now (UTC): %s", now.isoformat(timespec="seconds"))
    log.info("cache: %s", CACHE_DIR)

    client = JolpicaClient()
    manifest = {"fetched_at_utc": now.isoformat(timespec="seconds"), "seasons": {}}
    all_changes = []
    for year in args.seasons:
        s = fetch_season(client, year, now, skip_laps=args.skip_laps, dry_run=args.dry_run)
        manifest["seasons"][str(year)] = {
            "scheduled": len(s["schedule"]),
            "finished_rounds": s["finished_rounds"],
            "cancelled": s["cancelled"],
            "missing": s["missing"],
            "changes": s["changes"],
        }
        all_changes.extend(s["changes"])

    manifest["request_stats"] = client.stats
    manifest["changes_vs_cache"] = all_changes
    mp = CACHE_DIR / "manifest.json"
    mp.write_text(json.dumps(manifest, indent=2, sort_keys=True))

    log.info("=" * 78)
    log.info("DONE. network=%d  cache_hits=%d  retries=%d",
             client.stats["network"], client.stats["cache_hits"], client.stats["retries"])
    if all_changes:
        log.warning("%d endpoint(s) changed vs cache -- see manifest", len(all_changes))
    log.info("manifest: %s", mp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
