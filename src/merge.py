"""Merge Kaggle (1950-2024, corrected) with Jolpica (2025-2026) into ./data/processed/.

Resolution policy, as reviewed:
  * Kaggle is the base for 1950-2024.
  * The reviewed corrections in data/corrections/corrections.csv move individual
    cells to Jolpica where the evidence says Jolpica is right. Raw CSVs are
    never edited; corrections are applied here as a separate logged step.
  * Jolpica supplies 2025 and 2026-to-date, which Kaggle does not cover.

Derived columns are added, never substituted for a raw one.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

from corrections import CORRECTION_KEYS, apply_corrections, load_corrections  # noqa: E402
from eras import era_for  # noqa: E402
from load import PRIMARY_KEYS, TABLES, load_all  # noqa: E402
from transform import COLUMNS  # noqa: E402

log = logging.getLogger("merge")
ROOT = Path(__file__).resolve().parents[1]
JOL = ROOT / "data" / "processed" / "jolpica"
OUT = ROOT / "data" / "processed"

RED_FLAG_LAP_RATIO = 3.0
RED_FLAG_STOP_MS = 180_000
JOLPICA_FROM_YEAR = 2025          # 2024 comes from Kaggle + corrections

# Surrogate keys restart at 1 on the Jolpica side, so they must be reassigned to
# continue after the Kaggle maximum or they collide. The sort key makes the
# assignment deterministic.
SURROGATE = {
    "results": ("resultId", ["raceId", "positionOrder"]),
    "sprint_results": ("resultId", ["raceId", "positionOrder"]),
    "qualifying": ("qualifyId", ["raceId", "position"]),
    "driver_standings": ("driverStandingsId", ["raceId", "position", "driverId"]),
    "constructor_standings": ("constructorStandingsId", ["raceId", "position", "constructorId"]),
    "constructor_results": ("constructorResultsId", ["raceId", "constructorId"]),
}


def read_jol(t: str) -> pd.DataFrame:
    p = JOL / f"{t}.csv"
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p, keep_default_na=False, na_values=[r"\N", ""])


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    OUT.mkdir(parents=True, exist_ok=True)

    kag = load_all()
    jol = {t: read_jol(t) for t in TABLES}
    jraces = jol["races"]
    keep_rids = set(jraces.loc[jraces["year"] >= JOLPICA_FROM_YEAR, "raceId"]) if len(jraces) else set()

    merged: dict[str, pd.DataFrame] = {}
    unresolved: list[dict] = []

    for t in TABLES:
        k = kag[t].copy()
        k["source"] = "kaggle"
        j = jol[t]
        if len(j):
            if "raceId" in j.columns:
                j = j[j["raceId"].isin(keep_rids)]
            elif t == "seasons":
                j = j[j["year"] >= JOLPICA_FROM_YEAR]
            elif t in ("drivers", "constructors", "circuits", "status"):
                idc = PRIMARY_KEYS[t][0]
                j = j[~j[idc].isin(set(k[idc]))]      # only genuinely new entities
        j = j.copy()
        if len(j):
            j["source"] = "jolpica"
            if t in SURROGATE:
                pk, order = SURROGATE[t]
                j = j.sort_values(order, kind="stable").reset_index(drop=True)
                start = int(k[pk].max()) + 1
                j[pk] = range(start, start + len(j))
        base = COLUMNS[t]
        both = pd.concat([k, j], ignore_index=True) if len(j) else k
        extra = [c for c in both.columns if c not in base]
        merged[t] = both[base + extra]
        log.info("  %-24s kaggle=%6d + jolpica=%6d = %7d", t, len(k), len(j), len(merged[t]))

    # Corrections run on the merged tables, keyed on natural keys, so they can
    # target a Jolpica-sourced row as easily as a Kaggle one.
    corr = load_corrections()
    log.info("applying %d reviewed corrections", len(corr))
    merged, applied = apply_corrections(merged, corr, CORRECTION_KEYS)
    pd.DataFrame(applied).to_csv(OUT / "corrections_applied.csv", index=False)
    by_type = pd.DataFrame(applied)["evidence_type"].value_counts().to_dict() if applied else {}
    log.info("  applied %d (%s); log -> corrections_applied.csv", len(applied), by_type)

    # ---------------------------------------------------------------- derived
    races = merged["races"]
    races["regs_era"] = races["year"].map(era_for)
    ry = races.set_index("raceId")["year"]

    # grid: kept in each source's own semantics (Kaggle 0 = pit lane / no time).
    # grid_slot: the actual starting slot where it is known.
    # pit_lane_start: NULL for Jolpica rows -- Jolpica reports the slot, not the
    # fact, so it genuinely cannot be determined without FIA grid sheets or FastF1.
    res = merged["results"]
    res["grid_slot"] = res["grid"].where(res["grid"] > 0)
    res["pit_lane_start"] = pd.Series(pd.NA, index=res.index, dtype="boolean")
    is_k = res["source"] == "kaggle"
    res.loc[is_k, "pit_lane_start"] = (res.loc[is_k, "grid"] == 0)
    # For 2024 we know the real slot from the Jolpica overlap.
    jres = read_jol("results")
    if len(jres):
        slot = jres.set_index(["raceId", "driverId"])["grid"]
        idx = pd.MultiIndex.from_frame(res[["raceId", "driverId"]])
        known = slot.reindex(idx).to_numpy()
        fill = res["grid_slot"].isna() & pd.notna(known)
        res.loc[fill, "grid_slot"] = pd.Series(known, index=res.index)[fill]
    # Official starting-grid pages settle the pit-lane fact for 2025+, where
    # Jolpica reports only the slot. Scraped by src/scrape_grids.py.
    plp = OUT / "pit_lane_starts.csv"
    if plp.exists():
        g = pd.read_csv(plp)
        rmap = races.set_index(["year", "round"])["raceId"]
        g["raceId"] = pd.MultiIndex.from_frame(g[["year", "round"]]).map(rmap)
        code2id = (merged["drivers"].dropna(subset=["code"])
                   .drop_duplicates("code", keep="last").set_index("code")["driverId"])
        g["driverId"] = g["code"].map(code2id)
        unmapped = g[g["driverId"].isna()]
        if len(unmapped):
            log.warning("  %d scraped grid rows could not be mapped to a driver: %s",
                        len(unmapped), sorted(unmapped["code"].unique()))
        g = g.dropna(subset=["raceId", "driverId"])
        lookup = g.set_index([g["raceId"].astype(int), g["driverId"].astype(int)])["pit_lane_start"]
        lookup = lookup[~lookup.index.duplicated()]
        idx3 = pd.MultiIndex.from_frame(res[["raceId", "driverId"]])
        vals = pd.Series(lookup.reindex(idx3).to_numpy(), index=res.index)
        filled = vals.notna() & res["pit_lane_start"].isna()
        res.loc[filled, "pit_lane_start"] = vals[filled].astype(bool)
        log.info("  pit_lane_start: filled %d rows from official starting grids "
                 "(%d marked as pit-lane starts)", int(filled.sum()),
                 int((vals[filled] == True).sum()))  # noqa: E712

    n_null = int(res["pit_lane_start"].isna().sum())
    log.info("  pit_lane_start: %d True, %d False, %d NULL (undeterminable, 2025+)",
             int((res["pit_lane_start"] == True).sum()),  # noqa: E712
             int((res["pit_lane_start"] == False).sum()), n_null)  # noqa: E712

    # ---- elapsed_ms, and keeping time/milliseconds on Kaggle's convention.
    # Kaggle populates time/milliseconds only for lead-lap classified finishers
    # (verified: 7,678 of 7,680 non-null times are lead-lap). Jolpica populates
    # them for lapped and retired drivers too. Rather than let the columns change
    # meaning at the source boundary, the raw columns are held to Kaggle's rule
    # everywhere and every known elapsed time is carried in elapsed_ms.
    wl = res[res["positionText"] == "1"].groupby("raceId")["laps"].max()
    res["_wlaps"] = res["raceId"].map(wl)
    lead_lap = (res["laps"] == res["_wlaps"]) & res["positionText"].astype(str).str.fullmatch(r"\d+")

    res["elapsed_ms"] = pd.to_numeric(res["milliseconds"], errors="coerce")
    jres_all = read_jol("results")
    if len(jres_all):
        em = jres_all.set_index(["raceId", "driverId"])["milliseconds"]
        em = em[~em.index.duplicated()]
        idx2 = pd.MultiIndex.from_frame(res[["raceId", "driverId"]])
        res["elapsed_ms"] = res["elapsed_ms"].fillna(pd.Series(em.reindex(idx2).to_numpy(), index=res.index))

    off_convention = (res["source"] == "jolpica") & ~lead_lap & res["milliseconds"].notna()
    res.loc[off_convention, ["time", "milliseconds"]] = None
    res.drop(columns=["_wlaps"], inplace=True)
    log.info("  elapsed_ms: %d populated (%d more than raw milliseconds); "
             "cleared time/milliseconds on %d non-lead-lap jolpica rows",
             int(res["elapsed_ms"].notna().sum()),
             int(res["elapsed_ms"].notna().sum() - res["milliseconds"].notna().sum()),
             int(off_convention.sum()))

    # red-flag flags
    lt = merged["lap_times"]
    if len(lt):
        med = lt.groupby("raceId")["milliseconds"].transform("median")
        lt["red_flag_affected"] = lt["milliseconds"] >= RED_FLAG_LAP_RATIO * med
    ps = merged["pit_stops"]
    ps["red_flag_affected"] = ps["milliseconds"] >= RED_FLAG_STOP_MS
    # Ergast counts a red-flag pit-lane hold as a stop; formula1.com does not.
    # The raw `stop` index keeps the Ergast convention (consistent with all
    # 11,371 historical rows); these two columns give the official reading.
    ps["counts_as_official_stop"] = ~ps["red_flag_affected"]
    ps.sort_values(["raceId", "driverId", "stop"], kind="stable", inplace=True)
    real = ps[ps["counts_as_official_stop"]]
    ps["official_stop_number"] = pd.Series(pd.NA, index=ps.index, dtype="Int64")
    ps.loc[real.index, "official_stop_number"] = (
        real.groupby(["raceId", "driverId"]).cumcount() + 1
    ).astype("Int64")
    merged["pit_stops"] = ps
    log.info("  official_stop_number: %d real stops, %d red-flag holds excluded",
             int(ps["counts_as_official_stop"].sum()), int((~ps["counts_as_official_stop"]).sum()))

    # lap_data_suspect: null where there is no lap data to judge against
    cnt = lt.groupby(["raceId", "driverId"]).size() if len(lt) else pd.Series(dtype=int)
    idx = pd.MultiIndex.from_frame(res[["raceId", "driverId"]])
    have = cnt.reindex(idx).to_numpy() if len(cnt) else [None] * len(res)
    have = pd.Series(have, index=res.index)
    res["lap_data_suspect"] = pd.Series(pd.NA, index=res.index, dtype="boolean")
    known = have.notna()
    res.loc[known, "lap_data_suspect"] = (res.loc[known, "laps"] != have[known])
    sus = res[res["lap_data_suspect"] == True]  # noqa: E712
    log.info("  lap_data_suspect: %d True, %d NULL (no lap data)",
             len(sus), int(res["lap_data_suspect"].isna().sum()))
    modern = sus[sus["raceId"].map(ry) >= 2018]
    if len(modern):
        log.warning("  %d suspect driver-races fall in 2018+ (the likely modelling window):", len(modern))
        for _, r in modern.iterrows():
            log.warning("     raceId=%d driverId=%d laps=%s", r["raceId"], r["driverId"], r["laps"])
    modern.to_csv(OUT / "lap_data_suspect_2018plus.csv", index=False)

    # championship_points: 2007 McLaren were excluded and officially scored 0.
    cs = merged["constructor_standings"]
    cs["championship_points"] = cs["points"].astype(float)
    mcl = kag["constructors"].loc[kag["constructors"]["constructorRef"] == "mclaren", "constructorId"]
    if len(mcl):
        r2007 = set(races.loc[races["year"] == 2007, "raceId"])
        m = cs["raceId"].isin(r2007) & (cs["constructorId"] == int(mcl.iloc[0]))
        cs.loc[m, "championship_points"] = 0.0
        log.info("  championship_points: zeroed %d rows for 2007 McLaren (spygate exclusion)", int(m.sum()))

    # ------------------------------------------------------- driver_seasons
    r = merged["results"].merge(races[["raceId", "year"]], on="raceId")
    dsz = (r.groupby(["driverId", "year", "constructorId"], as_index=False)
             .agg(number=("number", lambda s: s.dropna().iloc[0] if s.notna().any() else None),
                  races=("resultId", "size")))
    dsz = dsz.sort_values(["year", "driverId", "constructorId"]).reset_index(drop=True)
    dsz.to_csv(OUT / "driver_seasons.csv", index=False)
    log.info("  driver_seasons           %7d rows (driverId, year, constructorId, number, races)", len(dsz))

    # --------------------------------------------------- unresolved conflicts
    # Recomputed *after* corrections, so anything a correction settled drops out
    # and only genuinely open disagreements remain.
    for tbl, key, cols in [("sprint_results", ["raceId", "driverId"], ["positionText", "position"]),
                           ("results", ["raceId", "driverId"], ["grid"])]:
        j = read_jol(tbl)
        if not len(j):
            continue
        m2 = merged[tbl].merge(j, on=key, suffixes=("_m", "_j"))
        m2 = m2[m2["raceId"].isin(set(races.loc[races["year"] == 2024, "raceId"]))]
        for col in cols:
            a, b = m2[f"{col}_m"], m2[f"{col}_j"]
            neq = ~((a.astype(str) == b.astype(str)) | (a.isna() & b.isna()))
            for _, x in m2[neq].iterrows():
                # grid legitimately differs by convention: Kaggle codes a
                # pit-lane start as 0, Jolpica reports the slot. Not a conflict.
                plso = x.get("pit_lane_start_m", x.get("pit_lane_start"))
                if col == "grid" and int(x[f"{col}_m"]) == 0 and bool(plso):
                    continue
                unresolved.append({"table": tbl, "raceId": int(x["raceId"]),
                                   "driverId": int(x["driverId"]), "column": col,
                                   "kaggle": x[f"{col}_m"], "jolpica": x[f"{col}_j"],
                                   "official": "not checked",
                                   "note": "open disagreement after corrections"})
    pd.DataFrame(unresolved, columns=["table", "raceId", "driverId", "column", "kaggle",
                                      "jolpica", "official", "note"]).to_csv(
        OUT / "unresolved_conflicts.csv", index=False)
    log.info("  unresolved_conflicts     %7d rows", len(unresolved))

    sp = merged["sprint_results"]
    sp["conflict_unresolved"] = False
    res["conflict_unresolved"] = False
    for u in unresolved:
        t = merged[u["table"]]
        t.loc[(t["raceId"] == u["raceId"]) & (t["driverId"] == u["driverId"]),
              "conflict_unresolved"] = True

    # surrogate keys must be unique after the merge
    for t, (pk, _) in SURROGATE.items():
        d = int(merged[t][pk].duplicated().sum())
        if d:
            raise ValueError(f"{t}.{pk} has {d} duplicate ids after merge")
    log.info("  surrogate keys unique in all %d tables", len(SURROGATE))

    # ------------------------------------------------------------------ write
    for t, df in merged.items():
        df.to_csv(OUT / f"{t}.csv", index=False, na_rep=r"\N")
    log.info("wrote %d tables -> %s", len(merged), OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
