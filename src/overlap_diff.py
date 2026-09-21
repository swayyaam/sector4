"""Part 3: row-by-row diff of Kaggle 2024 against Jolpica 2024.

Both sides are keyed on the same natural keys, compared column by column.
Nothing is resolved here -- the point is to surface every disagreement so the
winning source can be chosen per conflict type.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

from load import load_table  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
JOL = ROOT / "data" / "processed" / "jolpica"

KEYS = {
    "results": ["raceId", "driverId"],
    "sprint_results": ["raceId", "driverId"],
    "qualifying": ["raceId", "driverId"],
    "lap_times": ["raceId", "driverId", "lap"],
    "pit_stops": ["raceId", "driverId", "stop"],
    "driver_standings": ["raceId", "driverId"],
    "constructor_standings": ["raceId", "constructorId"],
    "races": ["raceId"],
}
# Surrogate ids are assigned independently on each side, so comparing them is meaningless.
IGNORE = {"resultId", "qualifyId", "driverStandingsId", "constructorStandingsId",
          "constructorResultsId", "source", "regs_era", "pit_lane_start",
          "lap_data_suspect", "red_flag_affected", "championship_points"}


def compare(a: pd.Series, b: pd.Series) -> pd.Series:
    """Element-wise inequality, NA-safe, with both sides coerced the same way.

    Both columns are judged together: if every non-null value on both sides
    parses as a number we compare numerically (so 25 and 25.0 agree),
    otherwise we compare trimmed strings.
    """
    na = pd.Series(a.isna().to_numpy() & b.isna().to_numpy(), index=a.index)
    an, bn = pd.to_numeric(a, errors="coerce"), pd.to_numeric(b, errors="coerce")
    numeric = (an.notna().sum() == a.notna().sum()) and (bn.notna().sum() == b.notna().sum())
    if numeric and (a.notna().any() or b.notna().any()):
        eq = pd.Series((an.to_numpy() == bn.to_numpy()), index=a.index)
    else:
        av = a.astype("string").str.strip().fillna("\x00")
        bv = b.astype("string").str.strip().fillna("\x00")
        eq = pd.Series((av.to_numpy() == bv.to_numpy()), index=a.index)
    return ~(eq | na)


def diff_table(table: str, year: int = 2024) -> dict:
    k = load_table(table)
    j = pd.read_csv(JOL / f"{table}.csv", keep_default_na=False, na_values=[r"\N", ""])
    races = load_table("races")
    ids = set(races.loc[races["year"] == year, "raceId"])
    k = k[k["raceId"].isin(ids)] if "raceId" in k.columns else k[k["year"] == year]
    j = j[j["raceId"].isin(ids)] if "raceId" in j.columns else j[j["year"] == year]

    keys = KEYS[table]
    m = k.merge(j, on=keys, how="outer", suffixes=("_k", "_j"), indicator=True)
    only_k = m[m["_merge"] == "left_only"]
    only_j = m[m["_merge"] == "right_only"]
    both = m[m["_merge"] == "both"]

    cols = [c for c in k.columns if c in j.columns and c not in keys and c not in IGNORE]
    per_col = {}
    examples = {}
    for c in cols:
        neq = compare(both[f"{c}_k"], both[f"{c}_j"])
        n = int(neq.sum())
        if n:
            per_col[c] = n
            ex = both.loc[neq, keys + [f"{c}_k", f"{c}_j"]].head(5)
            examples[c] = ex
    return {"table": table, "kaggle_rows": len(k), "jolpica_rows": len(j),
            "only_kaggle": only_k, "only_jolpica": only_j, "matched": len(both),
            "per_col": per_col, "examples": examples, "keys": keys}


def main() -> int:
    pd.set_option("display.width", 200)
    total_conf = 0
    print("=" * 100)
    print("2024 OVERLAP DIFF — Kaggle vs Jolpica")
    print("=" * 100)
    for table in KEYS:
        try:
            d = diff_table(table)
        except FileNotFoundError:
            print(f"\n### {table}: no Jolpica file yet — skipped")
            continue
        n_conf = sum(d["per_col"].values())
        total_conf += n_conf
        print(f"\n### {table}")
        print(f"    rows: kaggle={d['kaggle_rows']:,}  jolpica={d['jolpica_rows']:,}  matched={d['matched']:,}  "
              f"kaggle-only={len(d['only_kaggle'])}  jolpica-only={len(d['only_jolpica'])}")
        if d["per_col"]:
            print(f"    conflicting values by column ({n_conf:,} cells):")
            for c, n in sorted(d["per_col"].items(), key=lambda x: -x[1]):
                pct = 100.0 * n / max(d["matched"], 1)
                print(f"      {c:<20} {n:>6,}  ({pct:5.1f}% of matched rows)")
            for c in list(d["per_col"])[:4]:
                print(f"\n      -- sample: {c} --")
                print(d["examples"][c].to_string(index=False).replace("\n", "\n      "))
        else:
            print("    no value conflicts")
        if len(d["only_kaggle"]):
            print(f"    ROWS ONLY IN KAGGLE ({len(d['only_kaggle'])}):")
            print(d["only_kaggle"][d["keys"]].head(10).to_string(index=False))
        if len(d["only_jolpica"]):
            print(f"    ROWS ONLY IN JOLPICA ({len(d['only_jolpica'])}):")
            print(d["only_jolpica"][d["keys"]].head(10).to_string(index=False))
    print("\n" + "=" * 100)
    print(f"TOTAL CONFLICTING CELLS: {total_conf:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
