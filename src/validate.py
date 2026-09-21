"""Part 3 validation: structure, completeness, standings recomputation, ground truth."""
from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

from load import load_table  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
JOL = ROOT / "data" / "processed" / "jolpica"
GT = ROOT / "data" / "ground_truth" / "official_standings.json"

RESULTS: list[tuple[str, str, bool, str]] = []


def check(group: str, name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((group, name, ok, detail))
    return ok


def norm_name(s: str) -> str:
    """Compare driver names without accents or case."""
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def load_jol(t: str) -> pd.DataFrame:
    return pd.read_csv(JOL / f"{t}.csv", keep_default_na=False, na_values=[r"\N", ""])


def main() -> int:
    pd.set_option("display.width", 200)
    races = load_jol("races")
    results = load_jol("results")
    sprint = load_jol("sprint_results")
    quali = load_jol("qualifying")
    ds = load_jol("driver_standings")
    cs = load_jol("constructor_standings")
    pits = load_jol("pit_stops")
    laps = load_jol("lap_times")
    drivers = load_jol("drivers").set_index("driverId")
    cons = load_jol("constructors").set_index("constructorId")

    # ---------------------------------------------------------- structural
    check("Structural", "races: no duplicate raceId", races["raceId"].is_unique)
    check("Structural", "races: no duplicate (year, round)", not races.duplicated(["year", "round"]).any())
    gaps = []
    for y, g in races.groupby("year"):
        r = sorted(g["round"])
        if r != list(range(1, len(r) + 1)):
            gaps.append((int(y), r))
    check("Structural", "races: round numbers contiguous from 1", not gaps, str(gaps))
    check("Structural", "results: (raceId, driverId) unique",
          not results.duplicated(["raceId", "driverId"]).any())
    check("Structural", "qualifying: (raceId, driverId) unique",
          not quali.duplicated(["raceId", "driverId"]).any())
    check("Structural", "pit_stops: (raceId, driverId, stop) unique",
          not pits.duplicated(["raceId", "driverId", "stop"]).any())
    if len(laps):
        check("Structural", "lap_times: (raceId, driverId, lap) unique",
              not laps.duplicated(["raceId", "driverId", "lap"]).any())

    rids = set(races["raceId"])
    for t, df in [("results", results), ("sprint_results", sprint), ("qualifying", quali),
                  ("driver_standings", ds), ("constructor_standings", cs), ("pit_stops", pits),
                  ("lap_times", laps)]:
        if not len(df):
            continue
        orphan = set(df["raceId"]) - rids
        check("Structural", f"{t}.raceId resolves", not orphan, str(sorted(orphan)[:5]))
    for t, df, col, idx in [("results", results, "driverId", drivers.index),
                            ("results", results, "constructorId", cons.index)]:
        orphan = set(df[col]) - set(idx)
        check("Structural", f"{t}.{col} resolves", not orphan, str(sorted(orphan)[:5]))

    # positionOrder must be a dense rank (no shared drives in the modern era)
    bad = [int(r) for r, g in results.groupby("raceId")
           if sorted(g["positionOrder"]) != list(range(1, len(g) + 1))]
    check("Structural", "results.positionOrder dense 1..N per race", not bad, str(bad[:5]))
    # Jolpica's qualifying position rank
    badq = [int(r) for r, g in quali.groupby("raceId")
            if sorted(g["position"]) != list(range(1, len(g) + 1))]
    check("Structural", "qualifying.position dense 1..N per race", not badq,
          f"broken in raceIds {badq}")

    # -------------------------------------------------------- completeness
    for t, df, label in [(results, results, "results"), (quali, quali, "qualifying"),
                         (ds, ds, "driver_standings"), (cs, cs, "constructor_standings")]:
        missing = sorted(rids - set(df["raceId"]))
        check("Completeness", f"every race has {label}", not missing, f"missing raceIds {missing[:8]}")
    missing_p = sorted(rids - set(pits["raceId"]))
    check("Completeness", "every race has pit_stops", not missing_p, f"missing {missing_p[:8]}")
    if len(laps):
        missing_l = sorted(rids - set(laps["raceId"]))
        check("Completeness", "every race has lap_times", not missing_l, f"missing {missing_l[:8]}")
    else:
        check("Completeness", "every race has lap_times", False, "lap_times not fetched yet")

    # ------------------------------------------------ standings recompute
    per = pd.concat([
        results.groupby(["raceId", "driverId"], as_index=False)["points"].sum(),
        sprint.groupby(["raceId", "driverId"], as_index=False)["points"].sum(),
    ]).groupby(["raceId", "driverId"], as_index=False)["points"].sum()
    per = per.merge(races[["raceId", "year", "round"]], on="raceId")
    for year, g in per.groupby("year"):
        calc = g.groupby("driverId")["points"].sum()
        last = races[races["year"] == year].sort_values("round").iloc[-1]["raceId"]
        off = ds[ds["raceId"] == last].set_index("driverId")["points"]
        both = calc.reindex(off.index).fillna(0)
        bad = (both - off).abs() > 1e-9
        check("Recompute", f"{int(year)} driver standings == sum(results+sprint)", not bad.any(),
              f"{int(bad.sum())} drivers differ")

    perc = pd.concat([
        results.groupby(["raceId", "constructorId"], as_index=False)["points"].sum(),
        sprint.groupby(["raceId", "constructorId"], as_index=False)["points"].sum(),
    ]).groupby(["raceId", "constructorId"], as_index=False)["points"].sum()
    perc = perc.merge(races[["raceId", "year", "round"]], on="raceId")
    for year, g in perc.groupby("year"):
        calc = g.groupby("constructorId")["points"].sum()
        last = races[races["year"] == year].sort_values("round").iloc[-1]["raceId"]
        off = cs[cs["raceId"] == last].set_index("constructorId")["points"]
        both = calc.reindex(off.index).fillna(0)
        bad = (both - off).abs() > 1e-9
        check("Recompute", f"{int(year)} constructor standings == sum(results+sprint)", not bad.any(),
              f"{int(bad.sum())} teams differ")

    # ---------------------------------------------------------- ground truth
    gt = json.loads(GT.read_text())
    for year in ("2024", "2025", "2026"):
        if year not in gt:
            continue
        last = races[races["year"] == int(year)].sort_values("round").iloc[-1]["raceId"]
        got = ds[ds["raceId"] == last].copy()
        got["name"] = got["driverId"].map(lambda i: f"{drivers.loc[i, 'forename']} {drivers.loc[i, 'surname']}")
        # Match on surname: sources style given names differently
        # ("Andrea Kimi Antonelli" vs "Kimi Antonelli", "Perez" vs "Pérez").
        mine = {}
        for _, r in got.iterrows():
            mine[norm_name(r["name"])] = float(r["points"])
            mine[norm_name(drivers.loc[r["driverId"], "surname"])] = float(r["points"])
        diffs = []
        for n, p in gt[year]["drivers"]:
            got_pts = mine.get(norm_name(n))
            if got_pts is None:
                got_pts = mine.get(norm_name(n.split()[-1]))
            if got_pts != float(p):
                diffs.append((n, p, got_pts))
        check("Ground truth", f"{year} drivers match formula1.com", not diffs, str(diffs[:6]))

        gotc = cs[cs["raceId"] == last].copy()
        gotc["name"] = gotc["constructorId"].map(lambda i: cons.loc[i, "name"])
        minec = {norm_name(r["name"]): float(r["points"]) for _, r in gotc.iterrows()}
        # team names differ in styling between sources; compare the multiset of points
        want = sorted(float(p) for _, p in gt[year]["constructors"])
        have = sorted(minec.values())
        check("Ground truth", f"{year} constructor point totals match formula1.com", want == have,
              f"official={want} ours={have}" if want != have else "")

    # --------------------------------------------------------------- sanity
    ent = results.groupby("raceId").size()
    check("Sanity", "every race has 18-24 entrants", bool(((ent >= 18) & (ent <= 24)).all()),
          str(ent[(ent < 18) | (ent > 24)].to_dict()))
    per_season = races.groupby("year").size()
    check("Sanity", "season race counts plausible",
          bool(((per_season >= 10) & (per_season <= 30)).all()), str(per_season.to_dict()))
    check("Sanity", "no negative points", bool((results["points"] >= 0).all()))
    grid_ok = results["grid"].between(0, 26).all()
    check("Sanity", "grid within 0..26", bool(grid_ok))

    # ------------------------------------------------------------- report
    print("=" * 96)
    print("VALIDATION — Jolpica-derived tables (2024-2026)")
    print("=" * 96)
    cur = None
    npass = nfail = 0
    for group, name, ok, detail in RESULTS:
        if group != cur:
            print(f"\n{group}")
            cur = group
        mark = "PASS" if ok else "FAIL"
        npass += ok
        nfail += not ok
        print(f"  [{mark}] {name}" + (f"  — {detail}" if detail and not ok else ""))
    print("\n" + "=" * 96)
    print(f"{npass} passed, {nfail} failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
