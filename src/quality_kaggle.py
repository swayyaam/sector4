"""Part 1 Section 6: data quality / impossible values / encoding checks."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load import load_all  # noqa: E402

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 60)

d = load_all()
races, results, sprint = d["races"], d["results"], d["sprint_results"]
lt, ps, qual = d["lap_times"], d["pit_stops"], d["qualifying"]
ry = races.set_index("raceId")["year"]

def hdr(s):
    print("\n" + "=" * 100); print(s); print("=" * 100)

hdr("6A. POSITION ENCODING: position vs positionText vs positionOrder")
print("results.positionText value counts:")
vc = results["positionText"].value_counts()
nonnum = vc[~vc.index.str.fullmatch(r"\d+")]
print("  non-numeric codes:", dict(nonnum))
print("  numeric codes: %d distinct, total %d rows" % (len(vc) - len(nonnum), vc[vc.index.str.fullmatch(r'\d+')].sum()))
# Rule: position is null exactly when positionText is non-numeric?
num_pt = results["positionText"].str.fullmatch(r"\d+")
bad = results[(num_pt) & (results["position"].isna())]
print(f"  positionText numeric but position NULL: {len(bad)}")
bad2 = results[(~num_pt) & (results["position"].notna())]
print(f"  positionText non-numeric but position SET: {len(bad2)}")
mism = results[num_pt & results["position"].notna() &
               (results["position"].astype("Float64").astype(str).str.replace(r"\.0$", "", regex=True)
                != results["positionText"])]
print(f"  position != positionText where both numeric: {len(mism)}")
# positionOrder must be a dense 1..N rank within each race
g = results.groupby("raceId")["positionOrder"]
badorder = []
for rid, s in g:
    v = sorted(s.tolist())
    if v != list(range(1, len(v) + 1)):
        badorder.append(rid)
print(f"  races where positionOrder is NOT a dense 1..N: {len(badorder)} {badorder[:10]}")
# classified finishers should have positionOrder == position
cls = results[results["position"].notna()]
print(f"  classified rows where position != positionOrder: {(cls['position'] != cls['positionOrder']).sum()}")
print("\n  status decode for each non-numeric positionText:")
st = d["status"].set_index("statusId")["status"]
for code in nonnum.index:
    sub = results[results["positionText"] == code]
    top = sub["statusId"].map(st).value_counts().head(6)
    print(f"    {code!r:6} n={len(sub):>6}  statuses: {dict(top)}")

print("\nsprint_results.positionText value counts:", dict(sprint["positionText"].value_counts()))

hdr("6B. IMPOSSIBLE / SUSPICIOUS VALUES")
print(f"results.laps < 0            : {(results['laps'] < 0).sum()}")
print(f"results.laps == 0           : {(results['laps'] == 0).sum()}  (legit: retired on formation/lap 1)")
print(f"results.grid < 0            : {(results['grid'] < 0).sum()}")
print(f"results.grid == 0           : {(results['grid'] == 0).sum()}  (Ergast encodes pit-lane start / no time as 0)")
print(f"results.points < 0          : {(results['points'] < 0).sum()}")
print(f"results.milliseconds <= 0   : {(results['milliseconds'] <= 0).sum()}")
# positionOrder beyond number of entrants
ent = results.groupby("raceId")["resultId"].count()
print(f"results.positionOrder > entrants in race: {(results['positionOrder'] > results['raceId'].map(ent)).sum()}")
# grid beyond entrants
gb = results[results["grid"] > results["raceId"].map(ent)]
print(f"results.grid > entrants in race: {len(gb)}")
if len(gb):
    gb = gb.assign(year=gb["raceId"].map(ry), entrants=gb["raceId"].map(ent))
    print(gb[["raceId","year","driverId","grid","entrants","positionOrder","statusId"]].head(25).to_string(index=False))
    print("  affected years:", sorted(gb["year"].unique()))

print("\n-- lap_times --")
print(f"lap < 1                    : {(lt['lap'] < 1).sum()}")
print(f"position < 1               : {(lt['position'] < 1).sum()}")
print(f"milliseconds <= 0          : {(lt['milliseconds'] <= 0).sum()}")
fast = lt[lt["milliseconds"] < 55_000]
print(f"lap time < 55s (implausible): {len(fast)}")
if len(fast):
    f2 = fast.assign(year=fast["raceId"].map(ry))
    print(f2.sort_values("milliseconds").head(15).to_string(index=False))
slow = lt[lt["milliseconds"] > 600_000]
print(f"lap time > 10min           : {len(slow)}")
if len(slow):
    print(slow.assign(year=slow['raceId'].map(ry)).sort_values('milliseconds', ascending=False).head(10).to_string(index=False))
print("lap-time percentiles (s):", {p: round(lt['milliseconds'].quantile(p)/1000,1) for p in [0.001,0.01,0.5,0.99,0.999]})

print("\n-- pit_stops --")
print(f"duration ms <= 0           : {(ps['milliseconds'] <= 0).sum()}")
print(f"stop < 1 / lap < 1         : {(ps['stop']<1).sum()} / {(ps['lap']<1).sum()}")
for lo, hi, lbl in [(0, 10_000, '<10s'), (10_000, 60_000, '10-60s'), (60_000, 180_000, '1-3min'), (180_000, 10**9, '>3min')]:
    print(f"  duration {lbl:>7}: {((ps['milliseconds']>=lo)&(ps['milliseconds']<hi)).sum():>6}")
vfast = ps[ps["milliseconds"] < 10_000]
if len(vfast):
    print("  fastest 10 stops:")
    print(vfast.assign(year=vfast['raceId'].map(ry)).sort_values('milliseconds').head(10).to_string(index=False))
vslow = ps[ps["milliseconds"] > 300_000]
print(f"  stops > 5 min: {len(vslow)}")
if len(vslow):
    print(vslow.assign(year=vslow['raceId'].map(ry)).sort_values('milliseconds',ascending=False).head(8).to_string(index=False))

hdr("6C. TIME STRINGS vs MILLISECONDS")
def parse_lap(s):
    """'1:38.109' or '38.109' -> ms"""
    if not isinstance(s, str) or not s.strip():
        return np.nan
    m = re.fullmatch(r"(?:(\d+):)?(\d+)\.(\d{1,3})", s.strip())
    if not m:
        return np.nan
    mins = int(m.group(1) or 0)
    return mins * 60_000 + int(m.group(2)) * 1000 + int(m.group(3).ljust(3, "0"))

for tbl, df, tcol, mcol in [("lap_times", lt, "time", "milliseconds"),
                            ("pit_stops", ps, "duration", "milliseconds")]:
    calc = df[tcol].map(parse_lap)
    unparsed = calc.isna() & df[tcol].notna()
    diff = (calc - df[mcol]).abs()
    print(f"  {tbl}.{tcol}: unparseable={unparsed.sum()}, mismatch vs {mcol} (>0ms)={int((diff>0).sum())}, max|diff|={diff.max()}")
    if unparsed.any():
        print("    sample unparseable:", df.loc[unparsed, tcol].head(8).tolist())

# results.time is either '1:34:50.616' (winner) or '+12.345' gap
def parse_race_time(s):
    if not isinstance(s, str) or not s.strip():
        return np.nan
    s = s.strip()
    m = re.fullmatch(r"(?:(\d+):)?(?:(\d+):)?(\d+)\.(\d{1,3})", s)
    if not m:
        return np.nan
    h = int(m.group(1) or 0) if m.group(2) else 0
    mi = int(m.group(2) or 0) if m.group(2) else int(m.group(1) or 0)
    return h*3_600_000 + mi*60_000 + int(m.group(3))*1000 + int(m.group(4).ljust(3,'0'))

rt = results[results["time"].notna()]
plus = rt["time"].str.startswith("+")
print(f"  results.time: {len(rt)} non-null; {plus.sum()} are '+gap' strings, {(~plus).sum()} absolute")
abs_rows = rt[~plus]
calc = abs_rows["time"].map(parse_race_time)
diff = (calc - abs_rows["milliseconds"]).abs()
print(f"    absolute times: unparseable={int((calc.isna()).sum())}, mismatch>0ms={int((diff>0).sum())}, max|diff|={diff.max()}")
# do '+gap' rows have milliseconds?
print(f"    '+gap' rows with non-null milliseconds: {abs(rt[plus]['milliseconds'].notna().sum())}")
# Is milliseconds always null when time is null?
print(f"    time null but milliseconds set: {(results['time'].isna() & results['milliseconds'].notna()).sum()}")
print(f"    time set but milliseconds null: {(results['time'].notna() & results['milliseconds'].isna()).sum()}")

hdr("6D. results.laps vs lap_times row counts")
have_lt = set(lt["raceId"].unique())
sub = results[results["raceId"].isin(have_lt)]
cnt = lt.groupby(["raceId", "driverId"]).size().rename("lt_laps")
m = sub.merge(cnt, left_on=["raceId", "driverId"], right_index=True, how="left")
m["lt_laps"] = m["lt_laps"].fillna(0).astype(int)
m["delta"] = m["laps"] - m["lt_laps"]
bad = m[m["delta"] != 0].assign(year=lambda x: x["raceId"].map(ry))
print(f"  driver-races in lap_times coverage: {len(m):,};  mismatched laps: {len(bad):,} ({100*len(bad)/len(m):.2f}%)")
print("  delta distribution:", dict(bad["delta"].value_counts().head(10)))
print("  mismatches by year:"); print(bad.groupby("year").size().to_string())
print("\n  worst 15:")
print(bad.reindex(bad["delta"].abs().sort_values(ascending=False).index)[
    ["raceId","year","driverId","laps","lt_laps","delta","positionText","statusId"]].head(15).to_string(index=False))
# races entirely missing lap_times for a driver who did laps
zero = m[(m["lt_laps"] == 0) & (m["laps"] > 0)]
print(f"\n  driver-races with laps>0 but ZERO lap_times rows: {len(zero)} across {zero['raceId'].nunique()} races")
print("   by year:", dict(zero.assign(y=zero['raceId'].map(ry)).groupby('y').size()))
