"""Corrected per-round cumulative standings check (drivers + constructors).

Earlier attempt merged only on races a driver actually entered, so a driver who
skipped a round lost their running total. Here we build a dense driver x round
grid per season, cumulative-sum along rounds, then compare only where the
standings table actually has a row.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load import load_all  # noqa: E402

pd.set_option("display.width", 220)
d = load_all()
races = d["races"][["raceId", "year", "round"]]
res, spr = d["results"], d["sprint_results"]
ds, cs, cr = d["driver_standings"], d["constructor_standings"], d["constructor_results"]


def dense_cumulative(points_df, entity_col):
    """points_df: raceId, <entity>, points  ->  year, round, <entity>, cum"""
    p = points_df.merge(races, on="raceId")
    out = []
    for year, grp in p.groupby("year"):
        wide = grp.pivot_table(index=entity_col, columns="round", values="points",
                               aggfunc="sum", fill_value=0.0)
        all_rounds = sorted(races.loc[races["year"] == year, "round"].unique())
        wide = wide.reindex(columns=all_rounds, fill_value=0.0)
        cum = wide.cumsum(axis=1)
        m = cum.stack().rename("cum").reset_index()
        m["year"] = year
        out.append(m)
    return pd.concat(out, ignore_index=True)


def report(name, calc, table, entity_col, label_map):
    t = table.merge(races, on="raceId")
    m = t.merge(calc, on=["year", "round", entity_col], how="left")
    m["cum"] = m["cum"].fillna(0.0)
    m["diff"] = (m["cum"] - m["points"]).round(6)
    bad = m[m["diff"] != 0]
    print(f"\n### {name}: {len(m):,} snapshots compared, {len(bad):,} mismatched "
          f"({100*len(bad)/len(m):.2f}%)")
    if len(bad):
        print("  mismatching years:", sorted(bad["year"].unique()))
        modern = bad[bad["year"] >= 1991]
        print(f"  1991+: {len(modern)} mismatches, years={sorted(modern['year'].unique())}")
        if len(modern):
            mm = modern.assign(who=modern[entity_col].map(label_map))
            print(mm.sort_values(["year", "round"])[
                ["year", "round", "who", "points", "cum", "diff"]].to_string(index=False))
    return bad


drv = d["drivers"].set_index("driverId")["surname"]
cons = d["constructors"].set_index("constructorId")["name"]

rp = res.groupby(["raceId", "driverId"], as_index=False)["points"].sum()
sp = spr.groupby(["raceId", "driverId"], as_index=False)["points"].sum()
dpts = pd.concat([rp, sp]).groupby(["raceId", "driverId"], as_index=False)["points"].sum()
print("=" * 100); print("7D (corrected). PER-ROUND CUMULATIVE — DRIVERS"); print("=" * 100)
bad_d = report("driver_standings vs running sum of results+sprint", dense_cumulative(dpts, "driverId"),
               ds, "driverId", drv)

print(); print("=" * 100); print("7E. PER-ROUND CUMULATIVE — CONSTRUCTORS"); print("=" * 100)
cpts = cr[["raceId", "constructorId", "points"]]
bad_c = report("constructor_standings vs running sum of constructor_results", dense_cumulative(cpts, "constructorId"),
               cs, "constructorId", cons)

print(); print("=" * 100); print("7F. 'wins' COLUMN CHECK (modern era)"); print("=" * 100)
wins = res[res["positionText"] == "1"].groupby(["raceId", "driverId"]).size().rename("w").reset_index()
wc = dense_cumulative(wins.rename(columns={"w": "points"}), "driverId").rename(columns={"cum": "calc_wins"})
t = ds.merge(races, on="raceId").merge(wc, on=["year", "round", "driverId"], how="left")
t["calc_wins"] = t["calc_wins"].fillna(0)
bw = t[t["calc_wins"] != t["wins"]]
print(f"  driver_standings.wins mismatches: {len(bw):,} of {len(t):,}; years={sorted(bw['year'].unique())[:30]}")
print(f"  1991+: {len(bw[bw['year']>=1991])}")
if len(bw[bw["year"] >= 1991]):
    print(bw[bw["year"] >= 1991].assign(who=lambda x: x.driverId.map(drv))[
        ["year","round","who","wins","calc_wins"]].head(20).to_string(index=False))
