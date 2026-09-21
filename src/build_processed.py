"""Transform cached Jolpica JSON into Kaggle-schema tables and add derived columns.

Output goes to ./data/processed/jolpica/ (Jolpica rows only). Merging with the
Kaggle rows happens in a later step, after the 2024 overlap diff is reviewed.

Derived columns are always *added*, never overwriting a raw value:
  races.regs_era                     regulation era (src/eras.py)
  results.pit_lane_start             grid == 0 is Ergast's pit-lane/no-time code
  results.lap_data_suspect           results.laps disagrees with the lap_times count
  lap_times.red_flag_affected        lap >= 3x the race's median lap
  pit_stops.red_flag_affected        stop >= 180 s
  constructor_standings.championship_points  points after championship penalties
Every row also carries `source`.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

import datetime as dt  # noqa: E402

from eras import era_for  # noqa: E402
from fetch_jolpica import is_finished  # noqa: E402
from id_maps import IDMAP_DIR, audit, write_maps  # noqa: E402
from jolpica_client import JolpicaClient  # noqa: E402
from load import load_table  # noqa: E402
from transform import COLUMNS, SIDECAR_COLUMNS, encode_position, parse_duration_ms, write_table  # noqa: E402

log = logging.getLogger("build")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed" / "jolpica"

# Thresholds derived from the Kaggle distribution (see DATA_REPORT.md):
# safety-car laps top out near 1.7x the race median and the p99.5 -> p99.9 jump
# is 1.71 -> 10.3, so 3.0 sits inside an empty gap.
RED_FLAG_LAP_RATIO = 3.0
# Pit-stop durations have literally no observations between 180 s and 300 s.
RED_FLAG_STOP_MS = 180_000


def _num(v):
    return None if v in (None, "") else v


def build(seasons: list[int], skip_laps: bool = False) -> dict[str, list[dict]]:
    client = JolpicaClient()
    a = audit(seasons)
    write_maps(a)
    now = dt.datetime.now(dt.timezone.utc)

    # Only races that have actually been run. Scheduled future rounds are left
    # out entirely rather than emitted as empty rows.
    completed: dict[int, set[int]] = {}
    for year in seasons:
        completed[year] = {int(r["round"]) for r in client.get_all(f"{year}/races") if is_finished(r, now)}
        log.info("  %d: %d of %d rounds completed", year,
                 len(completed[year]), len(client.get_all(f"{year}/races")))

    dmap, cmap, cirmap = a["drivers"]["map"], a["constructors"]["map"], a["circuits"]["map"]

    # ---- raceId: reuse the existing id for an overlapping (year, round), mint the rest
    k_races = load_table("races")
    race_id = {(int(r.year), int(r.round)): int(r.raceId) for r in k_races.itertuples()}
    nxt = int(k_races["raceId"].max()) + 1
    for r in a["races"]["new"]:
        if r["round"] not in completed[r["year"]]:
            continue
        race_id[(r["year"], r["round"])] = nxt
        nxt += 1

    out: dict[str, list[dict]] = {t: [] for t in COLUMNS}
    sidecar: list[dict] = []

    # ---------------------------------------------------------------- races
    for year in seasons:
        for race in client.get_all(f"{year}/races"):
            rnd = int(race["round"])
            if rnd not in completed[year]:
                continue
            rid = race_id[(year, rnd)]
            row = {"raceId": rid, "year": year, "round": rnd,
                   "circuitId": cirmap[race["Circuit"]["circuitId"]], "name": race["raceName"],
                   "date": race["date"], "time": race.get("time"), "url": race.get("url"),
                   "regs_era": era_for(year), "source": "jolpica"}
            for jkey, prefix in [("FirstPractice", "fp1"), ("SecondPractice", "fp2"),
                                 ("ThirdPractice", "fp3"), ("Qualifying", "quali"), ("Sprint", "sprint")]:
                s = race.get(jkey) or {}
                row[f"{prefix}_date"] = s.get("date")
                row[f"{prefix}_time"] = s.get("time")
            out["races"].append(row)
            # Jolpica field with nowhere to live in the Kaggle schema.
            sq = race.get("SprintQualifying")
            if sq:
                sidecar.append({"raceId": rid, "year": year, "round": rnd, "field": "SprintQualifying",
                                "date": sq.get("date"), "time": sq.get("time")})
        out["seasons"].append({"year": year, "url": f"https://en.wikipedia.org/wiki/{year}_Formula_One_World_Championship",
                               "source": "jolpica"})

    # ---------------------------------------------------------------- status
    for sid, label in sorted(a["entities"]["statuses"].items()):
        out["status"].append({"statusId": sid, "status": label, "source": "jolpica"})
    status_by_label = {label: sid for sid, label in a["entities"]["statuses"].items()}

    # -------------------------------------------------------------- entities
    for ref, jd in sorted(a["entities"]["drivers"].items()):
        out["drivers"].append({
            "driverId": dmap[ref], "driverRef": ref, "number": _num(jd.get("permanentNumber")),
            "code": jd.get("code"), "forename": jd.get("givenName"), "surname": jd.get("familyName"),
            "dob": jd.get("dateOfBirth"), "nationality": jd.get("nationality"), "url": jd.get("url"),
            "source": "jolpica"})
    for ref, jc in sorted(a["entities"]["constructors"].items()):
        out["constructors"].append({
            "constructorId": cmap[ref], "constructorRef": ref, "name": jc.get("name"),
            "nationality": jc.get("nationality"), "url": jc.get("url"), "source": "jolpica"})
    for ref, jc in sorted(a["entities"]["circuits"].items()):
        loc = jc.get("Location", {})
        out["circuits"].append({
            "circuitId": cirmap[ref], "circuitRef": ref, "name": jc.get("circuitName"),
            "location": loc.get("locality"), "country": loc.get("country"),
            "lat": _num(loc.get("lat")), "lng": _num(loc.get("long")),
            "alt": None,  # Jolpica does not expose altitude -- left null, never invented
            "url": jc.get("url"), "source": "jolpica"})

    # --------------------------------------------------------------- results
    rid_seq = 1
    for year in seasons:
        for race in client.get_all(f"{year}/results"):
            if int(race["round"]) not in completed[year]:
                continue
            rid = race_id[(year, int(race["round"]))]
            for r in race.get("Results", []):
                pos, ptext, order = encode_position(r.get("position"), r.get("positionText"))
                t = r.get("Time") or {}
                fl = r.get("FastestLap") or {}
                out["results"].append({
                    "resultId": rid_seq, "raceId": rid, "driverId": dmap[r["Driver"]["driverId"]],
                    "constructorId": cmap[r["Constructor"]["constructorId"]], "number": _num(r.get("number")),
                    "grid": _num(r.get("grid")), "position": pos, "positionText": ptext,
                    "positionOrder": order, "points": float(r.get("points", 0) or 0),
                    "laps": _num(r.get("laps")), "time": t.get("time"), "milliseconds": _num(t.get("millis")),
                    "fastestLap": _num(fl.get("lap")), "rank": _num(fl.get("rank")),
                    "fastestLapTime": (fl.get("Time") or {}).get("time"),
                    "fastestLapSpeed": None,  # Jolpica returns no AverageSpeed
                    "statusId": status_by_label[r["status"]],
                    "pit_lane_start": (str(r.get("grid")) == "0"),
                    "source": "jolpica"})
                rid_seq += 1

    # ------------------------------------------------------------ qualifying
    q_seq = 1
    for year in seasons:
        for race in client.get_all(f"{year}/qualifying"):
            if int(race["round"]) not in completed[year]:
                continue
            rid = race_id[(year, int(race["round"]))]
            for r in race.get("QualifyingResults", []):
                out["qualifying"].append({
                    "qualifyId": q_seq, "raceId": rid, "driverId": dmap[r["Driver"]["driverId"]],
                    "constructorId": cmap[r["Constructor"]["constructorId"]], "number": _num(r.get("number")),
                    "position": _num(r.get("position")), "q1": r.get("Q1"), "q2": r.get("Q2"), "q3": r.get("Q3"),
                    "source": "jolpica"})
                q_seq += 1

    # --------------------------------------------------------- sprint results
    s_seq = 1
    for year in seasons:
        for race in client.get_all(f"{year}/sprint"):
            if int(race["round"]) not in completed[year]:
                continue
            rid = race_id[(year, int(race["round"]))]
            for r in race.get("SprintResults", []):
                pos, ptext, order = encode_position(r.get("position"), r.get("positionText"))
                t = r.get("Time") or {}
                fl = r.get("FastestLap") or {}
                out["sprint_results"].append({
                    "resultId": s_seq, "raceId": rid, "driverId": dmap[r["Driver"]["driverId"]],
                    "constructorId": cmap[r["Constructor"]["constructorId"]], "number": _num(r.get("number")),
                    "grid": _num(r.get("grid")), "position": pos, "positionText": ptext,
                    "positionOrder": order, "points": float(r.get("points", 0) or 0),
                    "laps": _num(r.get("laps")), "time": t.get("time"), "milliseconds": _num(t.get("millis")),
                    "fastestLap": _num(fl.get("lap")), "fastestLapTime": (fl.get("Time") or {}).get("time"),
                    "statusId": status_by_label[r["status"]], "source": "jolpica"})
                s_seq += 1

    # ------------------------------------------------- per-round: standings
    ds_seq = cs_seq = 1
    for year in seasons:
        rounds = sorted(completed[year])
        for rnd in rounds:
            rid = race_id[(year, rnd)]
            try:
                lists = client.get_all(f"{year}/{rnd}/driverstandings")
            except Exception:
                continue
            for sl in lists:
                for s in sl.get("DriverStandings", []):
                    out["driver_standings"].append({
                        "driverStandingsId": ds_seq, "raceId": rid, "driverId": dmap[s["Driver"]["driverId"]],
                        "points": float(s["points"]), "position": _num(s.get("position")),
                        "positionText": s.get("positionText"), "wins": _num(s.get("wins")), "source": "jolpica"})
                    ds_seq += 1
            for sl in client.get_all(f"{year}/{rnd}/constructorstandings"):
                for s in sl.get("ConstructorStandings", []):
                    pts = float(s["points"])
                    out["constructor_standings"].append({
                        "constructorStandingsId": cs_seq, "raceId": rid,
                        "constructorId": cmap[s["Constructor"]["constructorId"]], "points": pts,
                        "position": _num(s.get("position")), "positionText": s.get("positionText"),
                        "wins": _num(s.get("wins")),
                        "championship_points": pts,  # no exclusions in 2024-26; see DATA_REPORT
                        "source": "jolpica"})
                    cs_seq += 1

    # ---------------------------------------------- per-round: pits and laps
    for year in seasons:
        rounds = sorted(completed[year])
        for rnd in rounds:
            rid = race_id[(year, rnd)]
            try:
                races_ps = client.get_all(f"{year}/{rnd}/pitstops")
            except Exception:
                races_ps = []
            for race in races_ps:
                for p in race.get("PitStops", []):
                    ms = parse_duration_ms(p.get("duration"))
                    out["pit_stops"].append({
                        "raceId": rid, "driverId": dmap[p["driverId"]], "stop": _num(p.get("stop")),
                        "lap": _num(p.get("lap")), "time": p.get("time"), "duration": p.get("duration"),
                        "milliseconds": ms,
                        "red_flag_affected": (ms is not None and ms >= RED_FLAG_STOP_MS),
                        "source": "jolpica"})
            races_lp = []
            if not skip_laps:
                try:
                    races_lp = client.get_all(f"{year}/{rnd}/laps")
                except Exception:
                    races_lp = []
            rows = []
            for race in races_lp:
                for lap in race.get("Laps", []):
                    for t in lap.get("Timings", []):
                        rows.append({"raceId": rid, "driverId": dmap[t["driverId"]],
                                     "lap": int(lap["number"]), "position": _num(t.get("position")),
                                     "time": t.get("time"), "milliseconds": parse_duration_ms(t.get("time")),
                                     "source": "jolpica"})
            if rows:
                ms = pd.Series([r["milliseconds"] for r in rows], dtype="float64")
                median = ms.median()
                for r, v in zip(rows, ms):
                    r["red_flag_affected"] = bool(pd.notna(v) and median and v >= RED_FLAG_LAP_RATIO * median)
            out["lap_times"].extend(rows)

    # ---------------------------------------------- derived: constructor_results
    # Jolpica has no constructor-results endpoint. Part 1 established that from
    # 1980 on this table equals the sum of a team's race + sprint points for
    # that race (pre-1979 only the best-placed car scored, which does not apply
    # here). The `status` column stays null: it flags a championship exclusion
    # and there is none in 2024-2026.
    team_pts: dict[tuple[int, int], float] = {}
    for tbl in ("results", "sprint_results"):
        for r in out[tbl]:
            k = (r["raceId"], r["constructorId"])
            team_pts[k] = team_pts.get(k, 0.0) + float(r["points"])
    for i, ((rid, cid), pts) in enumerate(sorted(team_pts.items()), start=1):
        out["constructor_results"].append({
            "constructorResultsId": i, "raceId": rid, "constructorId": cid,
            "points": pts, "status": None, "derived": True, "source": "jolpica"})

    # ------------------------------------ derived: lap_data_suspect on results
    # With no lap data loaded we cannot judge, so the flag is left null rather
    # than defaulting to False, which would assert the laps agree.
    if skip_laps and not out["lap_times"]:
        for r in out["results"]:
            r["lap_data_suspect"] = None
    elif out["lap_times"]:
        lt = pd.DataFrame(out["lap_times"]).groupby(["raceId", "driverId"]).size()
        for r in out["results"]:
            n = lt.get((r["raceId"], r["driverId"]))
            r["lap_data_suspect"] = bool(n is not None and int(r["laps"]) != int(n))
    else:
        for r in out["results"]:
            r["lap_data_suspect"] = False

    out["_sidecar"] = sidecar
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="+", type=int, default=[2024, 2025, 2026])
    ap.add_argument("--skip-laps", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

    OUT.mkdir(parents=True, exist_ok=True)
    data = build(args.seasons, skip_laps=args.skip_laps)
    sidecar = data.pop("_sidecar")

    for table, rows in data.items():
        extra = [c for c in (rows[0].keys() if rows else []) if c not in COLUMNS[table]]
        cols = COLUMNS[table] + extra
        df = pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)
        df.to_csv(OUT / f"{table}.csv", index=False)
        log.info("  %-24s %7d rows  (+derived: %s)", table, len(df), ", ".join(extra) or "-")

    pd.DataFrame(sidecar, columns=SIDECAR_COLUMNS).to_csv(OUT / "race_sessions_extra.csv", index=False)
    log.info("  %-24s %7d rows  (sidecar: fields Kaggle cannot hold)", "race_sessions_extra", len(sidecar))
    log.info("id maps -> %s", IDMAP_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
