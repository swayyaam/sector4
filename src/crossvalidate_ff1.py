"""Part A step 5: cross-validate FastF1 against our own tables.

FastF1 reads the official F1 timing feed; our lap times and results come from
Ergast/Jolpica. They are genuinely independent, so agreement is evidence and
disagreement is worth reading carefully rather than averaging away.

Compares, for every overlapping race:
  * race lap times      -- lap by lap, keyed on (raceId, driverId, lap)
  * finishing positions -- our positionOrder vs FastF1 ClassifiedPosition
  * grid positions      -- our grid vs FastF1 GridPosition
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
ENRICHED = ROOT / "data" / "enriched"
OUT = ENRICHED / "crossvalidation"

LAP_TOL_MS = 100          # below this, treat as rounding between feeds


def rd(p: Path) -> pd.DataFrame:
    return pd.read_csv(p, keep_default_na=False, na_values=[r"\N", ""], low_memory=False)


def load_enriched(kind: str) -> pd.DataFrame:
    fs = sorted((ENRICHED / kind).glob("*.csv"))
    if not fs:
        return pd.DataFrame()
    return pd.concat([rd(f) for f in fs], ignore_index=True)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 200)

    ff_laps = load_enriched("laps")
    ff_res = load_enriched("results")
    if not len(ff_laps):
        print("no enriched data yet")
        return 0

    ours_laps = rd(PROCESSED / "lap_times.csv")
    ours_res = rd(PROCESSED / "results.csv")
    races = rd(PROCESSED / "races.csv")[["raceId", "year", "name"]]

    print("=" * 96)
    print("CROSS-VALIDATION: FastF1 vs our tables")
    print("=" * 96)

    # ---------------------------------------------------------------- laps
    f = ff_laps[(ff_laps["session"] == "Race") & ff_laps["driverId"].notna()].copy()
    f["driverId"] = f["driverId"].astype(int)
    f = f[["raceId", "driverId", "LapNumber", "LapTimeMs"]].rename(
        columns={"LapNumber": "lap", "LapTimeMs": "ff_ms"})
    f["lap"] = f["lap"].astype("Int64")
    # our side: exclude rows whose driver attribution is known-bad
    o = ours_laps.copy()
    if "driver_attribution_suspect" in o.columns:
        o = o[~o["driver_attribution_suspect"].fillna(False).astype(bool)]
    o = o[["raceId", "driverId", "lap", "milliseconds"]].rename(columns={"milliseconds": "our_ms"})

    shared = sorted(set(f["raceId"]) & set(o["raceId"]))
    f, o = f[f["raceId"].isin(shared)], o[o["raceId"].isin(shared)]
    m = f.merge(o, on=["raceId", "driverId", "lap"], how="outer", indicator=True)
    both = m[m["_merge"] == "both"].copy()
    both["diff"] = (both["ff_ms"] - both["our_ms"]).abs()

    n_both = len(both)
    exact = int((both["diff"] == 0).sum())
    within = int((both["diff"] <= LAP_TOL_MS).sum())
    over = both[both["diff"] > LAP_TOL_MS]
    print(f"\n### Race lap times  ({len(shared)} overlapping races)")
    print(f"    laps compared      : {n_both:,}")
    print(f"    exact match        : {exact:,} ({100*exact/max(n_both,1):.3f}%)")
    print(f"    within {LAP_TOL_MS} ms      : {within:,} ({100*within/max(n_both,1):.3f}%)")
    print(f"    differing > {LAP_TOL_MS} ms : {len(over):,} ({100*len(over)/max(n_both,1):.3f}%)")
    print(f"    only in FastF1     : {int((m['_merge']=='left_only').sum()):,}")
    print(f"    only in ours       : {int((m['_merge']=='right_only').sum()):,}")
    if len(over):
        o2 = over.merge(races, on="raceId")
        by = o2.groupby(["year", "name"]).size().sort_values(ascending=False)
        print("\n    races with the most differing laps:")
        print(by.head(12).to_string())
        over.merge(races, on="raceId").to_csv(OUT / "lap_time_mismatches.csv", index=False)

    # ------------------------------------------------------------- results
    fr = ff_res[(ff_res["session"] == "Race") & ff_res["driverId"].notna()].copy()
    fr["driverId"] = fr["driverId"].astype(int)
    orr = ours_res[["raceId", "driverId", "positionOrder", "grid", "positionText"]]
    mr = fr.merge(orr, on=["raceId", "driverId"], how="inner")

    def as_num(s):
        return pd.to_numeric(s, errors="coerce")

    mr["ff_pos"] = as_num(mr["ClassifiedPosition"])
    pos_cmp = mr[mr["ff_pos"].notna() & mr["positionOrder"].notna()]
    pos_bad = pos_cmp[pos_cmp["ff_pos"] != pos_cmp["positionOrder"]]
    print(f"\n### Finishing position  ({len(pos_cmp):,} comparable rows)")
    print(f"    agree    : {len(pos_cmp)-len(pos_bad):,} ({100*(len(pos_cmp)-len(pos_bad))/max(len(pos_cmp),1):.2f}%)")
    print(f"    disagree : {len(pos_bad):,}")
    if len(pos_bad):
        pos_bad.merge(races, on="raceId").to_csv(OUT / "position_mismatches.csv", index=False)
        print(pos_bad.merge(races, on="raceId").groupby(["year", "name"]).size()
              .sort_values(ascending=False).head(8).to_string())

    grid_cmp = mr[as_num(mr["GridPosition"]).notna() & mr["grid"].notna()].copy()
    grid_cmp["ff_grid"] = as_num(grid_cmp["GridPosition"])
    # our grid uses 0 for a pit-lane start; FastF1 reports the slot
    gb = grid_cmp[(grid_cmp["ff_grid"] != grid_cmp["grid"]) & (grid_cmp["grid"] != 0)]
    gb_pit = grid_cmp[(grid_cmp["ff_grid"] != grid_cmp["grid"]) & (grid_cmp["grid"] == 0)]
    print(f"\n### Grid position  ({len(grid_cmp):,} comparable rows)")
    print(f"    agree                        : {len(grid_cmp)-len(gb)-len(gb_pit):,}")
    print(f"    differ, ours = 0 (pit lane)  : {len(gb_pit):,}  (expected: conventions differ)")
    print(f"    differ otherwise             : {len(gb):,}")
    if len(gb):
        gb.merge(races, on="raceId").to_csv(OUT / "grid_mismatches.csv", index=False)
        print(gb.merge(races, on="raceId")[["year", "name", "driverId", "grid", "ff_grid"]]
              .head(12).to_string(index=False))
    print(f"\nreports -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
