"""Part 1 Section 7: recompute standings from results (+sprint) and diff vs the standings tables."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load import load_all  # noqa: E402

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 60)

d = load_all()
races = d["races"][["raceId", "year", "round", "name", "date"]].copy()
res, spr = d["results"], d["sprint_results"]
ds, cs, cr = d["driver_standings"], d["constructor_standings"], d["constructor_results"]

def hdr(s):
    print("\n" + "=" * 100); print(s); print("=" * 100)

# Final round of each season (by round number).
final_round = races.sort_values(["year", "round"]).groupby("year").tail(1)[["year", "raceId", "round"]]
final_round = final_round.rename(columns={"raceId": "finalRaceId", "round": "finalRound"})

# ---------------------------------------------------------------- drivers
hdr("7A. DRIVERS: sum(results.points + sprint_results.points) per season vs final driver_standings")
rp = res.groupby(["raceId", "driverId"], as_index=False)["points"].sum()
sp = spr.groupby(["raceId", "driverId"], as_index=False)["points"].sum()
per_race = (pd.concat([rp, sp]).groupby(["raceId", "driverId"], as_index=False)["points"].sum()
              .merge(races[["raceId", "year"]], on="raceId"))
calc = per_race.groupby(["year", "driverId"], as_index=False)["points"].sum().rename(columns={"points": "calc_pts"})

fin_ds = ds.merge(final_round, left_on="raceId", right_on="finalRaceId")[["year", "driverId", "points", "position", "wins"]]
fin_ds = fin_ds.rename(columns={"points": "std_pts"})
cmpd = fin_ds.merge(calc, on=["year", "driverId"], how="outer", indicator=True)
cmpd["calc_pts"] = cmpd["calc_pts"].fillna(0.0)
cmpd["std_pts"] = cmpd["std_pts"].fillna(0.0)
cmpd["diff"] = (cmpd["calc_pts"] - cmpd["std_pts"]).round(6)
bad = cmpd[cmpd["diff"] != 0]
print(f"  driver-seasons compared: {len(cmpd):,}   mismatched: {len(bad):,}")
by_year = bad.groupby("year").agg(n_drivers=("driverId", "size"), max_abs=("diff", lambda s: s.abs().max()))
print("\n  mismatched driver-seasons per year:")
print(by_year.to_string())
years_bad = sorted(bad["year"].unique())
print(f"\n  affected years ({len(years_bad)}): {years_bad}")
print(f"  CLEAN years: {sorted(set(races['year'].unique()) - set(years_bad))}")
print("\n  sign of diff (calc - standings): positive => naive sum exceeds official (dropped-scores hypothesis)")
print("  ", dict(bad["diff"].apply(lambda x: "calc>std" if x > 0 else "calc<std").value_counts()))
neg = bad[bad["diff"] < 0]
print(f"  rows where calc < standings (cannot be dropped scores): {len(neg)}")
if len(neg):
    print(neg.sort_values("diff").head(20).to_string(index=False))

# ---------------------------------------------------------------- constructors
hdr("7B. CONSTRUCTORS: sum(constructor_results.points) per season vs final constructor_standings")
crr = cr.merge(races[["raceId", "year"]], on="raceId")
# Exclude rows flagged status='D' (championship exclusion, e.g. 2007 McLaren).
for label, mask in [("INCLUDING status='D' rows", crr["points"].notna()),
                    ("EXCLUDING status='D' rows", crr["status"].isna())]:
    c = crr[mask].groupby(["year", "constructorId"], as_index=False)["points"].sum().rename(columns={"points": "calc_pts"})
    f = cs.merge(final_round, left_on="raceId", right_on="finalRaceId")[["year", "constructorId", "points", "position", "wins"]].rename(columns={"points": "std_pts"})
    m = f.merge(c, on=["year", "constructorId"], how="outer")
    m["calc_pts"] = m["calc_pts"].fillna(0.0); m["std_pts"] = m["std_pts"].fillna(0.0)
    m["diff"] = (m["calc_pts"] - m["std_pts"]).round(6)
    b = m[m["diff"] != 0]
    print(f"\n  [{label}] constructor-seasons: {len(m):,}  mismatched: {len(b):,}  years: {sorted(b['year'].unique())}")
    if label.startswith("EXCLUDING") and len(b):
        print(b.groupby("year").agg(n=("constructorId", "size"), max_abs=("diff", lambda s: s.abs().max())).to_string())

hdr("7C. constructor_results.points vs sum of that team's results.points, per race")
team_race = res.groupby(["raceId", "constructorId"], as_index=False)["points"].sum().rename(columns={"points": "from_results"})
sp_team = spr.groupby(["raceId", "constructorId"], as_index=False)["points"].sum().rename(columns={"points": "sprint_pts"})
tr = team_race.merge(sp_team, on=["raceId", "constructorId"], how="left")
tr["sprint_pts"] = tr["sprint_pts"].fillna(0.0)
tr["from_results_total"] = tr["from_results"] + tr["sprint_pts"]
m = cr.merge(tr, on=["raceId", "constructorId"], how="outer").merge(races[["raceId", "year"]], on="raceId")
m["points"] = m["points"].fillna(0.0); m["from_results_total"] = m["from_results_total"].fillna(0.0)
m["diff"] = (m["from_results_total"] - m["points"]).round(6)
b = m[m["diff"] != 0]
print(f"  team-races compared: {len(m):,}  mismatched: {len(b):,}")
print("  mismatches per year (first 40):")
print(b.groupby("year").size().head(40).to_string())
print(f"\n  year range of mismatches: {b['year'].min()} .. {b['year'].max()}")
print(f"  mismatches in 1979+: {len(b[b['year'] >= 1979])}")
if len(b[b["year"] >= 1979]):
    cons = d["constructors"].set_index("constructorId")["name"]
    print(b[b["year"] >= 1979].assign(team=lambda t: t.constructorId.map(cons))[
        ["raceId", "year", "team", "points", "from_results_total", "diff", "status"]].to_string(index=False))

hdr("7D. PER-ROUND cumulative check (drivers) — does standings == running sum after every race?")
pr = per_race.merge(races[["raceId", "year", "round"]], on=["raceId", "year"])
pr = pr.sort_values(["year", "round"])
pr["cum"] = pr.groupby(["year", "driverId"])["points"].cumsum()
chk = ds.merge(races[["raceId", "year", "round"]], on="raceId").merge(
    pr[["raceId", "driverId", "cum"]], on=["raceId", "driverId"], how="left")
chk["cum"] = chk["cum"].fillna(0.0)
chk["diff"] = (chk["cum"] - chk["points"]).round(6)
b = chk[chk["diff"] != 0]
print(f"  standings snapshots compared: {len(chk):,}  mismatched: {len(b):,}")
print(f"  years affected: {sorted(b['year'].unique())}")
print("  NOTE: a driver who scores in a later round has no standings row until then; "
      "and a driver with 0 points may be absent entirely.")
mod = chk[chk["year"] >= 1991]
bm = mod[mod["diff"] != 0]
print(f"\n  1991+ only: {len(mod):,} snapshots, {len(bm):,} mismatched  years={sorted(bm['year'].unique())}")
if len(bm):
    drv = d["drivers"].set_index("driverId")["surname"]
    print(bm.assign(who=lambda t: t.driverId.map(drv)).sort_values(["year","round"])[
        ["year","round","who","points","cum","diff"]].head(40).to_string(index=False))
