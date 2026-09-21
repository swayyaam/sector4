"""Generate data/corrections/corrections.csv from the reviewed 2024 overlap diff.

Kaggle stays the 2024 base. Each rule below moves one class of cell to Jolpica
because the evidence says Jolpica is right. Nothing here is a judgement call
that has not been checked.

evidence_type:
  official  -- verified against formula1.com (the FIA document portal is down:
               fia.com currently serves a placeholder pointing at Facebook)
  internal  -- proven by the data itself, with the argument recorded in `reason`
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

from load import load_table  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
JOL = ROOT / "data" / "processed" / "jolpica"
OUT = ROOT / "data" / "corrections" / "corrections.csv"

F1 = "https://www.formula1.com/en/results/2024/races"
SRC = {
    "belgium": f"{F1}/1242/belgium/race-result",
    "saudi_race": f"{F1}/1230/saudi-arabia/race-result",
    "saudi_fl": f"{F1}/1230/saudi-arabia/fastest-laps",
    "bahrain_fl": f"{F1}/1229/bahrain/fastest-laps",
    "monaco_fl": f"{F1}/1236/monaco/fastest-laps",
    "singapore_q": f"{F1}/1246/singapore/qualifying",
    "monaco_pits": f"{F1}/1236/monaco/pit-stop-summary",
}

rows: list[dict] = []


def add(table, pk, column, old, new, reason, evidence_type, source):
    rows.append({
        "table": table, "primary_key": pk, "column": column,
        "old_value": "" if old is None or (isinstance(old, float) and pd.isna(old)) else old,
        "new_value": "" if new is None or (isinstance(new, float) and pd.isna(new)) else new,
        "reason": reason, "evidence_type": evidence_type, "evidence_source": source,
    })


def fmtv(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def main() -> int:
    races = load_table("races")
    ids2024 = set(races.loc[races["year"] == 2024, "raceId"])
    k = load_table("results")
    j = pd.read_csv(JOL / "results.csv", keep_default_na=False, na_values=[r"\N", ""])
    m = k[k["raceId"].isin(ids2024)].merge(j, on=["raceId", "driverId"], suffixes=("_k", "_j"))

    # 1) 2024 Belgian GP: Kaggle kept gaps relative to the disqualified Russell.
    bel = m[m["raceId"] == 1134]
    for _, r in bel.iterrows():
        for col in ("time", "milliseconds"):
            a, b = r[f"{col}_k"], r[f"{col}_j"]
            if fmtv(a) != fmtv(b):
                add("results", f"{int(r['raceId'])}|{int(r['driverId'])}", col, fmtv(a), fmtv(b),
                    "Russell won on track then was disqualified; Kaggle kept gaps relative to him, "
                    "leaving the classified winner with time=+0.526. Official: Hamilton 1:19:57.566, "
                    "Piastri +0.647, Leclerc +8.023.",
                    "official", SRC["belgium"])

    # 2) Saudi GP: malformed 4-decimal time strings with milliseconds ~5.8s out.
    for _, r in m[(m["raceId"] == 1122)].iterrows():
        tk, tj = fmtv(r["time_k"]), fmtv(r["time_j"])
        if tk and tj and tk != tj:
            add("results", f"{int(r['raceId'])}|{int(r['driverId'])}", "time", tk, tj,
                "Kaggle time string has 4 decimal places (F1 times carry 3) and its milliseconds "
                "disagrees with winner-time + gap by ~5.8s.", "official", SRC["saudi_race"])
            add("results", f"{int(r['raceId'])}|{int(r['driverId'])}", "milliseconds",
                fmtv(r["milliseconds_k"]), fmtv(r["milliseconds_j"]),
                "Consistent with the corrected time string.", "official", SRC["saudi_race"])

    # 3) fastestLap recorded as lap 1 -- impossible on a full-fuel opening lap.
    for _, r in m.iterrows():
        if pd.notna(r["fastestLap_k"]) and r["fastestLap_k"] == 1 and pd.notna(r["fastestLap_j"]) \
                and r["fastestLap_j"] != 1:
            src = SRC["bahrain_fl"] if r["raceId"] == 1121 else SRC["saudi_fl"]
            add("results", f"{int(r['raceId'])}|{int(r['driverId'])}", "fastestLap", fmtv(r["fastestLap_k"]),
                fmtv(r["fastestLap_j"]),
                "Kaggle records lap 1 as the fastest lap, which cannot happen on full fuel. "
                "Official confirms Jolpica's lap number.", "official", src)

    # 4) Monaco: Kaggle's rank column is 0 for every driver (a placeholder).
    for _, r in m[m["raceId"] == 1128].iterrows():
        if pd.notna(r["rank_k"]) and r["rank_k"] == 0 and pd.notna(r["rank_j"]):
            add("results", f"{int(r['raceId'])}|{int(r['driverId'])}", "rank", "0", fmtv(r["rank_j"]),
                "Kaggle has rank=0 for every driver in this race. Official fastest-lap ranking "
                "matches Jolpica (Sainz 5, Leclerc 6, Norris 10, Piastri 11).",
                "official", SRC["monaco_fl"])

    # 5) Saudi: Sargeant's and Tsunoda's fastest laps are transposed in Kaggle.
    for _, r in m[(m["raceId"] == 1122) & (m["driverId"].isin([858, 852]))].iterrows():
        for col in ("fastestLap", "fastestLapTime", "rank"):
            a, b = fmtv(r[f"{col}_k"]), fmtv(r[f"{col}_j"])
            if a and b and a != b:
                add("results", f"{int(r['raceId'])}|{int(r['driverId'])}", col, a, b,
                    "Sargeant's and Tsunoda's fastest laps are swapped in Kaggle. Official: "
                    "Sargeant lap 49 / 1:33.026 / rank 15, Tsunoda lap 44 / 1:33.523 / rank 18.",
                    "official", SRC["saudi_fl"])

    # 6) Jolpica supplies fastest-lap data Kaggle leaves null.
    # NOTE: time/milliseconds are deliberately NOT backfilled here. Every one of
    # those 281 cells is a lapped or classified-retired driver, and Kaggle
    # populates those columns only for lead-lap finishers (verified: 7,678 of
    # 7,680 non-null times are lead-lap). Filling them would change what the
    # column means and invent an era boundary at 2024. Jolpica's elapsed times
    # are carried in the derived elapsed_ms column instead.
    for _, r in m.iterrows():
        if r["raceId"] == 1134:
            continue   # already handled above
        for col in ("fastestLap", "fastestLapTime"):
            a, b = fmtv(r[f"{col}_k"]), fmtv(r[f"{col}_j"])
            if a == "" and b != "":
                if int(r["raceId"]) == 1128:
                    # Kaggle carries no fastest-lap data at all for Monaco 2024.
                    # The official page lists exactly these 16 drivers and every
                    # lap number and time was checked against it.
                    add("results", f"{int(r['raceId'])}|{int(r['driverId'])}", col, "", b,
                        "Kaggle has no fastest-lap data for this race (rank is 0 for every "
                        "driver). All 16 lap numbers and times verified against the official "
                        "fastest-laps page.", "official", SRC["monaco_fl"])
                else:
                    add("results", f"{int(r['raceId'])}|{int(r['driverId'])}", col, "", b,
                        "Kaggle leaves this null; Jolpica supplies it.", "internal",
                        "derived: present in Jolpica, absent in Kaggle")

    # 7) Monaco pit stops: `stop` and `lap` are transposed in Kaggle.
    kp = load_table("pit_stops")
    jp = pd.read_csv(JOL / "pit_stops.csv", keep_default_na=False, na_values=[r"\N", ""])
    bad = kp[(kp["raceId"] == 1128) & (kp["stop"] > kp["lap"])]
    for _, r in bad.iterrows():
        match = jp[(jp["raceId"] == 1128) & (jp["driverId"] == r["driverId"]) &
                   (jp["lap"] == r["stop"]) & (jp["stop"] == r["lap"])]
        if len(match) != 1:
            continue
        pk = f"{int(r['raceId'])}|{int(r['driverId'])}|{int(r['stop'])}"
        add("pit_stops", pk, "stop", int(r["stop"]), int(r["lap"]),
            "stop and lap are transposed: stop > lap is impossible, and the row's time and "
            "duration are identical to Jolpica's, so it is the same event with two columns "
            "swapped. Kaggle's max stop number is 70. The index itself follows the Ergast "
            "convention of counting the lap-1 red-flag hold as a stop, which formula1.com does "
            "not - see official_stop_number for the official count.", "internal",
            "derived: stop>lap impossible; identical time+duration")
        add("pit_stops", pk, "lap", int(r["lap"]), int(r["stop"]),
            "Official pit-stop summary confirms the lap number and duration "
            "(e.g. Stroll lap 48 / 28.211s, Hamilton lap 51 / 24.232s).",
            "official", SRC["monaco_pits"])

    # 8) Singapore Q1: Kaggle is 6 ms out.
    kq = load_table("qualifying")
    row = kq[(kq["raceId"] == 1138) & (kq["driverId"] == 852)]
    if len(row) == 1:
        add("qualifying", "1138|852", "q1", row.iloc[0]["q1"], "1:30.716",
            "Official Singapore qualifying gives Tsunoda a Q1 of 1:30.716; Kaggle has 1:30.710.",
            "official", SRC["singapore_q"])

    # 9) Trailing-space bug in a nationality.
    kd = load_table("drivers")
    col = kd[kd["driverRef"] == "colapinto"]
    if len(col) == 1 and str(col.iloc[0]["nationality"]) != "Argentine":
        add("drivers", str(int(col.iloc[0]["driverId"])), "nationality",
            col.iloc[0]["nationality"], "Argentine",
            "Kaggle stores 'Argentinian ' with a trailing space; every other Argentine driver "
            "in the table uses 'Argentine'.", "internal", "derived: trailing whitespace")

    # 10) 2025 Emilia Romagna: Jolpica puts Bearman at P16, duplicating Lawson
    # and skipping P19. Official classification has Bearman P19.
    add("qualifying", "1151|860", "position", "16", "19",
        "Jolpica gives Bearman and Lawson both P16 and leaves P19 empty. Official qualifying "
        "classification: Lawson 16, Hulkenberg 17, Ocon 18, Bearman 19, Tsunoda 20 (no time).",
        "official", "https://www.formula1.com/en/results/2025/races/1260/emilia-romagna/qualifying")

    # 11) Sprint retirements: Kaggle assigns a numeric position while its own
    # status says Retired -- contradicting how it encodes retirements in the
    # main results table. Official lists all three as NC/DNF.
    ksp = load_table("sprint_results")
    for rid, did in [(1126, 840), (1126, 846), (1141, 807)]:
        row = ksp[(ksp["raceId"] == rid) & (ksp["driverId"] == did)]
        if len(row) != 1:
            continue
        r = row.iloc[0]
        src = (f"{F1}/1234/miami/sprint-results" if rid == 1126
               else f"{F1}/1249/brazil/sprint-results")
        add("sprint_results", f"{rid}|{did}", "positionText", fmtv(r["positionText"]), "R",
            "Kaggle gives a numeric position although its own status is Retired, and assigns "
            "one to a driver who completed 0 laps. Official classification: NC / DNF. Encoded "
            "as 'R' for consistency with 2025+, where Jolpica no longer emits 'N'.",
            "official", src)
        add("sprint_results", f"{rid}|{did}", "position", fmtv(r["position"]), "",
            "Position is null whenever the driver is not in the official classification.",
            "official", src)

    # 12) Sao Paulo 2024 grid: the official starting grid puts Hulkenberg P18.
    kg = k[(k["raceId"] == 1141) & (k["driverId"] == 807)]
    if len(kg) == 1 and int(kg.iloc[0]["grid"]) != 18:
        add("results", "1141|807", "grid", str(int(kg.iloc[0]["grid"])), "18",
            "Official starting grid for the 2024 Sao Paulo GP lists Hulkenberg P18; Kaggle has 17. "
            "The only pit-lane start that weekend was Sainz.",
            "official", f"{F1}/1249/brazil/starting-grid")

    df = pd.DataFrame(rows, columns=["table", "primary_key", "column", "old_value", "new_value",
                                     "reason", "evidence_type", "evidence_source"])
    df = df.sort_values(["table", "column", "primary_key"], kind="stable").reset_index(drop=True)
    # QUOTE_ALL so values round-trip byte-exactly -- the Colapinto correction
    # targets a trailing space, which an unquoted field loses on re-read and
    # which then trips the applier's old_value guard.
    df.to_csv(OUT, index=False, quoting=csv.QUOTE_ALL)
    print(f"wrote {len(df)} corrections -> {OUT}")
    print(df.groupby(["table", "column", "evidence_type"]).size().rename("n").reset_index().to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
