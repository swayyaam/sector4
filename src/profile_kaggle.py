"""Part 1 profiling of the Kaggle/Ergast CSVs. Prints a structured text report."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load import FOREIGN_KEYS, PRIMARY_KEYS, TABLES, load_all  # noqa: E402

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 50)

d = load_all()
races = d["races"]
race_year = races.set_index("raceId")["year"]
race_round = races.set_index("raceId")["round"]
race_date = races.set_index("raceId")["date"]

# Tables that reach a season only through raceId.
VIA_RACE = [
    "results", "sprint_results", "qualifying", "lap_times", "pit_stops",
    "driver_standings", "constructor_standings", "constructor_results",
]

print("=" * 100)
print("SECTION 1+2: SCHEMA, DTYPES, NULLS, PRIMARY KEYS")
print("=" * 100)
for t in TABLES:
    df = d[t]
    pk = PRIMARY_KEYS[t]
    print(f"\n### {t}  —  {len(df):,} rows x {len(df.columns)} cols   PK={pk}")
    info = []
    for c in df.columns:
        nulls = df[c].isna().sum()
        pct = 100.0 * nulls / len(df) if len(df) else 0.0
        info.append((c, str(df[c].dtype), nulls, round(pct, 2)))
    w = max(len(c) for c, *_ in info)
    for c, dt, n, p in info:
        flag = "  <-- ALL NULL" if p == 100.0 else ""
        print(f"    {c:<{w}}  {dt:<12} nulls={n:>7,} ({p:>6.2f}%){flag}")
    dup = df.duplicated(subset=pk, keep=False)
    if dup.any():
        print(f"    !! PK NOT UNIQUE: {dup.sum()} rows in duplicate PK groups")
        print(df[dup].sort_values(pk).to_string(max_rows=60))
    else:
        print(f"    PK unique: OK ({df[pk].drop_duplicates().shape[0]:,} distinct)")

print()
print("=" * 100)
print("SECTION 3: FOREIGN KEYS / ORPHANS")
print("=" * 100)
for t, fks in FOREIGN_KEYS.items():
    for col, (ptab, pcol) in fks.items():
        child = d[t][col].dropna().unique()
        parent = set(d[ptab][pcol].dropna().unique())
        orphans = sorted(set(child) - parent)
        status = "OK" if not orphans else f"!! {len(orphans)} ORPHANS: {orphans[:20]}"
        print(f"  {t}.{col} -> {ptab}.{pcol}: {status}")

# Reverse direction: parents never referenced.
print("\n  -- unreferenced parent rows (not an error, but worth knowing) --")
for ptab, pcol, users in [
    ("circuits", "circuitId", [("races", "circuitId")]),
    ("drivers", "driverId", [("results", "driverId")]),
    ("constructors", "constructorId", [("results", "constructorId")]),
    ("status", "statusId", [("results", "statusId"), ("sprint_results", "statusId")]),
    ("races", "raceId", [("results", "raceId")]),
]:
    used = set()
    for ct, cc in users:
        used |= set(d[ct][cc].dropna().unique())
    unused = sorted(set(d[ptab][pcol].dropna().unique()) - used)
    print(f"  {ptab}: {len(unused)} never referenced by {users}" + (f" -> {unused[:15]}" if unused else ""))

print()
print("=" * 100)
print("SECTION 4+5: SEASON / DATE COVERAGE AND LAST RACE PER TABLE")
print("=" * 100)
print(f"  seasons.csv: {d['seasons']['year'].min()} .. {d['seasons']['year'].max()} ({len(d['seasons'])} rows)")
print(f"  races.csv:   {races['year'].min()} .. {races['year'].max()} ({races['year'].nunique()} distinct years, {len(races)} races)")
print(f"  races.date:  {races['date'].min()} .. {races['date'].max()}")

rows = []
for t in VIA_RACE:
    df = d[t]
    yr = df["raceId"].map(race_year)
    last_rid = df.loc[yr.idxmax() if False else yr.index[yr.argmax()], "raceId"] if len(df) else None
    # last race by (year, round)
    key = pd.DataFrame({"raceId": df["raceId"], "year": yr, "round": df["raceId"].map(race_round)})
    key = key.dropna().sort_values(["year", "round"])
    last = key.iloc[-1]
    lr = races[races["raceId"] == last["raceId"]].iloc[0]
    rows.append({
        "table": t,
        "first_season": int(yr.min()),
        "last_season": int(yr.max()),
        "n_races_covered": df["raceId"].nunique(),
        "last_race": f"{int(lr['year'])} R{int(lr['round'])} {lr['name']}",
        "last_race_date": lr["date"],
    })
cov = pd.DataFrame(rows)
print()
print(cov.to_string(index=False))

print("\n  -- 2024 completeness per table --")
r2024 = races[races["year"] == 2024].sort_values("round")
print(f"  races.csv lists {len(r2024)} races for 2024: round {r2024['round'].min()}..{r2024['round'].max()}, "
      f"last = R{int(r2024.iloc[-1]['round'])} {r2024.iloc[-1]['name']} ({r2024.iloc[-1]['date']})")
ids2024 = set(r2024["raceId"])
for t in VIA_RACE:
    present = set(d[t]["raceId"].dropna().unique()) & ids2024
    missing = r2024[~r2024["raceId"].isin(present)]
    mtxt = ", ".join(f"R{int(x.round)} {x.name_}" for x in
                     missing.rename(columns={"name": "name_"}).itertuples()) if len(missing) else "-"
    print(f"    {t:<24} {len(present):>2}/{len(r2024)} races   missing: {mtxt[:120]}")

print("\n  -- sprint coverage (races with sprint_date set vs sprint_results present) --")
spr_sched = races[races["sprint_date"].notna()]
print(f"  races with sprint_date: {len(spr_sched)} ({spr_sched['year'].min()}..{spr_sched['year'].max()})")
spr_have = set(d["sprint_results"]["raceId"].unique())
miss_spr = spr_sched[~spr_sched["raceId"].isin(spr_have)]
print(f"  scheduled sprints WITHOUT sprint_results: {len(miss_spr)}")
if len(miss_spr):
    print(miss_spr[["raceId", "year", "round", "name", "date", "sprint_date"]].to_string(index=False))
extra_spr = spr_have - set(spr_sched["raceId"])
print(f"  sprint_results for races WITHOUT sprint_date: {len(extra_spr)} -> {sorted(extra_spr)[:20]}")
if extra_spr:
    print(races[races["raceId"].isin(extra_spr)][["raceId","year","round","name","date","sprint_date"]].to_string(index=False))
