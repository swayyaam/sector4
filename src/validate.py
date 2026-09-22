"""Validation of ./data/processed/ — structure, completeness, standings, ground truth.

Every historical quirk established in Part 1 is encoded here as an *expectation*
with its reason. A check passes when reality matches the documented expectation
and fails when it does not, so a failure always means something genuinely
unexplained rather than a known era difference.
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
GT = ROOT / "data" / "ground_truth" / "official_standings.json"

RESULTS: list[tuple[str, str, bool, str]] = []
# Seasons present in the dataset being validated. A subset fixture cannot
# answer a question about 2007, and pretending it passed would be worse than
# saying so.
YEARS: set[int] = set()

# ---- documented expectations (all established in Part 1) --------------------
SHARED_DRIVE_LAST_YEAR = 1964      # two drivers could share a car until 1964
DROPPED_SCORES_LAST_YEAR = 1990    # "best N results count" ended after 1990
BEST_CAR_ONLY_LAST_YEAR = 1979     # only the leading car scored for the team
COVERAGE = {"results": 1950, "driver_standings": 1950, "constructor_standings": 1958,
            "qualifying": 1994, "lap_times": 1996, "pit_stops": 2011}
QUALI_PARTIAL_UNTIL = 2002         # Ergast qualifying coverage is patchy until 2003
# Constructor championship penalties: season -> (constructorRef, expected delta)
CONSTRUCTOR_PENALTIES = {2007: ("mclaren", "excluded, placed last"),
                         2018: ("force_india", "59 pts forfeited on re-entry"),
                         2020: ("racing_point", "15 pt deduction")}
PITSTOPS_KNOWN_ABSENT = {1063}     # 2021 Belgian GP: 2 laps behind the safety car, no stops
# 1978 Italian GP: Harald Ertl is entered twice under two constructorIds, both
# DNQ. A genuine duplicate, reviewed and left as-is (see DATA_REPORT issue 4).
DUPLICATE_DRIVER_OK = {540}
# Races whose starter count is legitimately outside the normal band.
STARTER_COUNT_OK = {
    79: "2005 US GP: 14 cars withdrew after the formation lap (Michelin tyre boycott), 6 started",
    800: "1954 Indianapolis 500: shared drives mean 55 driver-entries for 33 cars",
    809: "1953 Indianapolis 500: shared drives mean 47 driver-entries for 33 cars",
}


def check(group: str, name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((group, name, ok, detail))
    return ok


def skip(group: str, name: str, why: str) -> None:
    """Record a check that cannot apply to this dataset.

    Reported separately from passes. A check that silently disappears when the
    data it needs is absent is indistinguishable from one that was never
    written.
    """
    RESULTS.append((group, name, None, why))


def covers(*years: int) -> bool:
    return all(y in YEARS for y in years)


def full_history() -> bool:
    """True when this is the whole record, not a slice of it.

    Some checks are statements about the span of the dataset -- that a
    constructor reused across decades splits into separate entities, say. On a
    fixture covering one season they are unanswerable rather than false.
    """
    return bool(YEARS) and min(YEARS) <= 1950


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def load(t: str) -> pd.DataFrame:
    return pd.read_csv(DATA / f"{t}.csv", keep_default_na=False, na_values=[r"\N", ""],
                       low_memory=False)


def main(argv: list[str] | None = None) -> int:
    global DATA
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path, default=DATA,
                    help="directory of processed CSVs to validate (default: data/processed)")
    args = ap.parse_args(argv)
    DATA = args.data

    pd.set_option("display.width", 200)
    print(f"validating: {DATA}\n")
    races, results, sprint = load("races"), load("results"), load("sprint_results")
    quali, ds, cs = load("qualifying"), load("driver_standings"), load("constructor_standings")
    pits, laps = load("pit_stops"), load("lap_times")
    drivers, cons = load("drivers").set_index("driverId"), load("constructors").set_index("constructorId")
    ry = races.set_index("raceId")["year"]
    rids = set(races["raceId"])
    global YEARS
    YEARS = set(races["year"].astype(int))

    # ------------------------------------------------------------ structural
    check("Structural", "races: raceId unique", races["raceId"].is_unique)
    # Surrogate ids restart at 1 on the Jolpica side and must be reassigned on
    # merge; this catches a regression there.
    for t, pk in [("results", "resultId"), ("sprint_results", "resultId"),
                  ("qualifying", "qualifyId"), ("driver_standings", "driverStandingsId"),
                  ("constructor_standings", "constructorStandingsId"),
                  ("constructor_results", "constructorResultsId")]:
        d = load(t)
        n = int(d[pk].duplicated().sum())
        check("Structural", f"{t}.{pk} unique after merge", not n, f"{n} duplicate ids")
    check("Structural", "races: (year, round) unique", not races.duplicated(["year", "round"]).any())
    gaps = [(int(y), sorted(g["round"])) for y, g in races.groupby("year")
            if sorted(g["round"]) != list(range(1, len(g) + 1))]
    check("Structural", "races: rounds contiguous from 1 in every season", not gaps, str(gaps))

    dup = results[results.duplicated(["raceId", "driverId"], keep=False)]
    dup = dup[~dup["raceId"].isin(DUPLICATE_DRIVER_OK)]
    late = sorted({int(ry[r]) for r in dup["raceId"]} - set(range(1950, SHARED_DRIVE_LAST_YEAR + 1)))
    check("Structural",
          f"results: (raceId, driverId) duplicates confined to shared drives (<= {SHARED_DRIVE_LAST_YEAR})",
          not late, f"unexpected duplicate years {late}")
    check("Structural", "qualifying: (raceId, driverId) unique",
          not quali.duplicated(["raceId", "driverId"]).any())
    check("Structural", "pit_stops: (raceId, driverId, stop) unique",
          not pits.duplicated(["raceId", "driverId", "stop"]).any())
    if len(laps):
        check("Structural", "lap_times: (raceId, driverId, lap) unique",
              not laps.duplicated(["raceId", "driverId", "lap"]).any())

    for t, df in [("results", results), ("sprint_results", sprint), ("qualifying", quali),
                  ("driver_standings", ds), ("constructor_standings", cs),
                  ("pit_stops", pits), ("lap_times", laps)]:
        if len(df):
            check("Structural", f"{t}.raceId resolves", not (set(df["raceId"]) - rids))
    check("Structural", "results.driverId resolves", not (set(results["driverId"]) - set(drivers.index)))
    check("Structural", "results.constructorId resolves",
          not (set(results["constructorId"]) - set(cons.index)))
    check("Structural", "results.statusId resolves",
          not (set(results["statusId"]) - set(load("status")["statusId"])))

    modern = races.loc[races["year"] > SHARED_DRIVE_LAST_YEAR, "raceId"]
    bad = [int(r) for r, g in results[results["raceId"].isin(set(modern))].groupby("raceId")
           if sorted(g["positionOrder"]) != list(range(1, len(g) + 1))]
    check("Structural", f"results.positionOrder dense 1..N (post-{SHARED_DRIVE_LAST_YEAR})", not bad, str(bad[:5]))
    badq = [int(r) for r, g in quali.groupby("raceId")
            if sorted(g["position"]) != list(range(1, len(g) + 1))]
    check("Structural", "qualifying.position dense 1..N per race", not badq,
          f"raceIds {badq} — Jolpica ships duplicate/non-dense positions here")

    # ---------------------------------------------------------- completeness
    for t, df in [("results", results), ("qualifying", quali), ("driver_standings", ds),
                  ("constructor_standings", cs), ("pit_stops", pits), ("lap_times", laps)]:
        if not len(df):
            check("Completeness", f"{t}: present for every race in its coverage era", False, "table empty")
            continue
        era = {r for r in rids if ry[r] >= COVERAGE[t]}
        if t == "qualifying":
            era = {r for r in era if ry[r] > QUALI_PARTIAL_UNTIL}
        if t == "pit_stops":
            era -= PITSTOPS_KNOWN_ABSENT
        missing = sorted(era - set(df["raceId"]))
        suffix = {"qualifying": f" (2003+; {QUALI_PARTIAL_UNTIL} and earlier are partial in Ergast)",
                  "pit_stops": " (2021 Belgian GP excluded: 2 laps behind the safety car)"}.get(t, "")
        check("Completeness", f"{t}: present for every race in its coverage era{suffix}",
              not missing, f"missing {len(missing)} raceIds, first: {missing[:6]}")

    # -------------------------------------------------- standings recompute
    per = pd.concat([results.groupby(["raceId", "driverId"], as_index=False)["points"].sum(),
                     sprint.groupby(["raceId", "driverId"], as_index=False)["points"].sum()]) \
        .groupby(["raceId", "driverId"], as_index=False)["points"].sum() \
        .merge(races[["raceId", "year", "round"]], on="raceId")
    modern_bad, dropped_ok = [], []
    for year, g in per.groupby("year"):
        last = races[races["year"] == year].sort_values("round").iloc[-1]["raceId"]
        off = ds[ds["raceId"] == last].set_index("driverId")["points"]
        calc = g.groupby("driverId")["points"].sum().reindex(off.index).fillna(0)
        d = (calc - off).round(6)
        if year > DROPPED_SCORES_LAST_YEAR:
            if (d.abs() > 1e-9).any():
                modern_bad.append(int(year))
        elif (d < -1e-9).any():
            # Dropped scores can only make the official total LOWER than the raw sum.
            dropped_ok.append(int(year))
    check("Recompute", f"driver standings reproduce exactly for {DROPPED_SCORES_LAST_YEAR + 1}+",
          not modern_bad, f"years {modern_bad}")
    check("Recompute",
          f"pre-{DROPPED_SCORES_LAST_YEAR + 1} gaps only ever reduce the total (dropped scores)",
          not dropped_ok, f"years where official EXCEEDS the raw sum: {dropped_ok}")

    perc = pd.concat([results.groupby(["raceId", "constructorId"], as_index=False)["points"].sum(),
                      sprint.groupby(["raceId", "constructorId"], as_index=False)["points"].sum()]) \
        .groupby(["raceId", "constructorId"], as_index=False)["points"].sum() \
        .merge(races[["raceId", "year"]], on="raceId")
    ref = cons["constructorRef"]
    unexplained = []
    for year, g in perc.groupby("year"):
        if year <= BEST_CAR_ONLY_LAST_YEAR:
            continue
        last = races[races["year"] == year].sort_values("round").iloc[-1]["raceId"]
        off = cs[cs["raceId"] == last].set_index("constructorId")["points"]
        calc = g.groupby("constructorId")["points"].sum().reindex(off.index).fillna(0)
        d = (calc - off).round(6)
        for cid in d[d.abs() > 1e-9].index:
            penalty = CONSTRUCTOR_PENALTIES.get(int(year))
            if penalty and ref.get(cid) == penalty[0]:
                continue     # documented championship penalty
            unexplained.append((int(year), ref.get(cid), float(d[cid])))
    check("Recompute",
          f"constructor standings reproduce for {BEST_CAR_ONLY_LAST_YEAR + 1}+ apart from documented penalties",
          not unexplained, str(unexplained[:6]))
    for y, (cref, why) in CONSTRUCTOR_PENALTIES.items():
        if y == 2007:
            if not covers(y):
                skip("Recompute", f"{y} {cref}: championship_points is 0 ({why})",
                     f"{y} is not in this dataset")
                continue
            cid = ref[ref == cref].index[0]
            last = races[races["year"] == y].sort_values("round").iloc[-1]["raceId"]
            row = cs[(cs["raceId"] == last) & (cs["constructorId"] == cid)]
            ok = len(row) == 1 and float(row.iloc[0]["championship_points"]) == 0.0
            check("Recompute", f"{y} {cref}: championship_points is 0 ({why})", ok)

    # ----------------------------------------------------------- ground truth
    gt = json.loads(GT.read_text())
    for year in ("2024", "2025", "2026"):
        if not covers(int(year)):
            for what in ("driver", "constructor"):
                skip("Ground truth", f"{year} {what} points match formula1.com",
                     f"{year} is not in this dataset")
            continue
        last = races[races["year"] == int(year)].sort_values("round").iloc[-1]["raceId"]
        got = ds[ds["raceId"] == last]
        mine: dict[str, float] = {}
        for _, r in got.iterrows():
            d = drivers.loc[r["driverId"]]
            mine[norm(f"{d['forename']} {d['surname']}")] = float(r["points"])
            mine[norm(d["surname"])] = float(r["points"])
        diffs = [(n, p, mine.get(norm(n), mine.get(norm(n.split()[-1]))))
                 for n, p in gt[year]["drivers"]
                 if mine.get(norm(n), mine.get(norm(n.split()[-1]))) != float(p)]
        check("Ground truth", f"{year} driver points match formula1.com", not diffs, str(diffs[:5]))
        gotc = cs[cs["raceId"] == last]
        want = sorted(float(p) for _, p in gt[year]["constructors"])
        have = sorted(float(r["points"]) for _, r in gotc.iterrows())
        check("Ground truth", f"{year} constructor points match formula1.com", want == have,
              f"official={want} ours={have}")

    # ----------------------------------------------------------------- sanity
    # Count starters, not entries: in the pre-qualifying era (to 1992) a race
    # could take 39 entries for 26 places, and the rest are DNQ/DNPQ ('F') or
    # withdrawn ('W') rather than participants.
    started = results[~results["positionText"].isin(["F", "W"])]
    ent = started.groupby("raceId").size().drop(labels=list(STARTER_COUNT_OK), errors="ignore")
    yr = pd.Series({r: int(ry[r]) for r in ent.index})
    mod = ent[yr >= 1990]
    check("Sanity", "1990+ starters per race within 14..28 (documented outliers excluded)", bool(mod.between(14, 28).all()),
          str(mod[~mod.between(14, 28)].to_dict()))
    check("Sanity", "historical starters per race within 5..40 (documented outliers excluded)", bool(ent.between(5, 40).all()),
          str(ent[~ent.between(5, 40)].to_dict()))
    allent = results.groupby("raceId").size()
    check("Sanity", "total entries per race within 5..60 (includes DNQ)",
          bool(allent.between(5, 60).all()), str(allent[~allent.between(5, 60)].to_dict()))
    rc = races.groupby("year").size()
    check("Sanity", "season race counts within 6..25", bool(rc.between(6, 25).all()), str(rc[~rc.between(6, 25)].to_dict()))
    if covers(2026):
        check("Sanity", "2026 partial season has 14 rounds so far",
              int(rc.get(2026, 0)) == 14, str(rc.get(2026)))
    else:
        skip("Sanity", "2026 partial season has 14 rounds so far", "2026 is not in this dataset")
    check("Sanity", "no negative points", bool((results["points"] >= 0).all()))
    check("Sanity", "grid within 0..40", bool(results["grid"].between(0, 40).all()),
          str(results.loc[~results["grid"].between(0, 40), "grid"].unique()[:8]))
    check("Sanity", "every row carries a source", bool(results["source"].isin(["kaggle", "jolpica"]).all()))
    check("Sanity", "pit_lane_start is null only for jolpica rows",
          bool(results.loc[results["pit_lane_start"].isna(), "source"].eq("jolpica").all()))

    # --------------------------------------------- lap completion / attribution
    if len(laps) and "counts_as_completed_lap" in laps.columns:
        cc = laps["counts_as_completed_lap"]
        sus = laps["driver_attribution_suspect"].fillna(False).astype(bool)
        reason = laps["counts_as_completed_lap_reason"]
        check("Lap flags", "counts_as_completed_lap is NULL exactly where the driver is suspect",
              bool((cc.isna() == sus).all()),
              f"{int((cc.isna() != sus).sum())} rows disagree")
        check("Lap flags", "every non-True row carries a reason",
              bool(reason[cc != True].notna().all()),  # noqa: E712
              f"{int(reason[cc != True].isna().sum())} rows without a reason")  # noqa: E712
        check("Lap flags", "every True row carries no reason",
              bool(reason[cc == True].isna().all()),  # noqa: E712
              f"{int(reason[cc == True].notna().sum())} rows with a stray reason")  # noqa: E712
        check("Lap flags", "reasons are from the agreed set",
              set(reason.dropna()) <= {"declared_early", "flagged_mid_lap",
                                       "lap_times_driver_transposed"},
              str(sorted(set(reason.dropna()))))
        check("Lap flags", "suspect rows are all reasoned as transposed",
              bool((reason[sus] == "lap_times_driver_transposed").all()))
        # A False row must actually lie beyond that driver's classified laps.
        lb = (results[["raceId", "driverId", "laps"]].drop_duplicates(["raceId", "driverId"])
              .set_index(["raceId", "driverId"])["laps"])
        f = laps[cc == False]  # noqa: E712
        rl = lb.reindex(pd.MultiIndex.from_frame(f[["raceId", "driverId"]])).to_numpy()
        check("Lap flags", "every False row is beyond the driver's classified laps",
              bool((f["lap"].to_numpy() > rl).all()),
              f"{int((f['lap'].to_numpy() <= rl).sum())} rows are not beyond")
        # declared_early must only appear in races flagged with classified_laps
        de = set(laps.loc[reason == "declared_early", "raceId"])
        cl = set(races.loc[races["classified_laps"].notna(), "raceId"])
        check("Lap flags", "declared_early appears only in races with classified_laps set",
              de <= cl, f"unlisted races: {sorted(de - cl)}")

    if "classified_laps" in races.columns:
        notes_p = DATA / "race_classification_notes.csv"
        n_set = int(races["classified_laps"].notna().sum())
        noted = set(pd.read_csv(notes_p)["raceId"]) if notes_p.exists() else set()
        if noted and not (noted <= rids):
            for name in ("classified_laps is populated only where documented",
                         "every classified_laps note cites a source",
                         "classified_laps matches the winner's classified distance"):
                skip("Lap flags", name, "the documented races are not in this dataset")
            nt = None
        else:
            check("Lap flags", "classified_laps is populated only where documented",
                  notes_p.exists() and n_set == len(noted), f"{n_set} races set")
            nt = pd.read_csv(notes_p) if notes_p.exists() else None
        if nt is not None:
            check("Lap flags", "every classified_laps note cites a source",
                  bool(nt["evidence_source"].notna().all() and
                       nt["evidence_source"].str.startswith("http").all()))
            wl = results[results["positionText"] == "1"].groupby("raceId")["laps"].max()
            ok = all(int(wl.get(r.raceId, -1)) == int(r.classified_laps) for r in nt.itertuples())
            check("Lap flags", "classified_laps matches the winner's classified distance", ok)

    # ------------------------------------------------------- team entities
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from entities import GAP_YEARS, year_blocks  # noqa: E402

    ENTITY_TABLES = ["results", "qualifying", "sprint_results",
                     "constructor_results", "constructor_standings"]
    ryy = races.set_index("raceId")["year"]
    ent_years: dict[str, set[int]] = {}
    ent_cids: dict[str, set[int]] = {}
    for t in ENTITY_TABLES:
        df = load(t)
        check("Team entities", f"{t}: every row has a team_entity_id",
              bool(df["team_entity_id"].notna().all()),
              f"{int(df['team_entity_id'].isna().sum())} null")
        sub = df.dropna(subset=["team_entity_id"])
        for eid, cid, y in zip(sub["team_entity_id"], sub["constructorId"], sub["raceId"].map(ryy)):
            if pd.notna(y):
                ent_years.setdefault(eid, set()).add(int(y))
                ent_cids.setdefault(eid, set()).add(int(cid))

    multi = {e: c for e, c in ent_cids.items() if len(c) > 1}
    check("Team entities", "each team_entity_id maps to exactly one constructorId",
          not multi, str(dict(list(multi.items())[:5])))

    spanning = {e: sorted(ys) for e, ys in ent_years.items()
                if len(year_blocks(sorted(ys))) > 1}
    check("Team entities",
          f"no team_entity_id spans an identity break (>{GAP_YEARS} idle seasons)",
          not spanning, str({k: v for k, v in list(spanning.items())[:3]}))

    breaks_path = DATA / "constructor_identity_breaks.csv"
    if breaks_path.exists():
        br = pd.read_csv(breaks_path)
        per_cid: dict[int, set[str]] = {}
        for eid, cids in ent_cids.items():
            per_cid.setdefault(next(iter(cids)), set()).add(eid)
        if not full_history():
            for name in ("every constructorId with an identity break yields >1 entity",
                         "Aston Martin 1959-60 and 2021-26 are separate entities"):
                skip("Team entities", name, "identity breaks span seasons this dataset omits")
        else:
            unsplit = [int(c) for c in br["constructorId"] if len(per_cid.get(int(c), set())) < 2]
            check("Team entities", "every constructorId with an identity break yields >1 entity",
                  not unsplit, f"not split: {unsplit}")
            # the headline case
            am = br[br["constructorRef"] == "aston_martin"]
            if len(am):
                cid = int(am.iloc[0]["constructorId"])
                got = sorted(per_cid.get(cid, set()))
                check("Team entities",
                      "Aston Martin 1959-60 and 2021-26 are separate entities",
                      len(got) == 2, f"entities={got}")

    # -------------------------------------------------------------- report
    print("=" * 96)
    print("VALIDATION — merged dataset 1950 to latest race")
    print("=" * 96)
    cur, npass, nfail, nskip = None, 0, 0, 0
    for group, name, ok, detail in RESULTS:
        if group != cur:
            print(f"\n{group}")
            cur = group
        if ok is None:
            nskip += 1
            print(f"  [SKIP] {name}\n         -> {detail}")
            continue
        npass += ok
        nfail += not ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"\n         -> {detail}" if detail and not ok else ""))
    print("\n" + "=" * 96)
    tail = f", {nskip} not applicable to this dataset" if nskip else ""
    print(f"{npass} passed, {nfail} failed{tail}")
    # Previously always 0, so a failing check could not fail a script or a CI
    # job -- the suite reported the problem and then said everything was fine.
    return 1 if nfail else 0


if __name__ == "__main__":
    raise SystemExit(main())
