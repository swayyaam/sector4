"""Rebuild tests/fixtures/processed from the real data/processed.

The fixture is one complete season so CI can run the validation suite without
the 43MB dataset, which is gitignored. It is generated rather than hand-made so
it can be refreshed after a pipeline change and reviewed as a diff.

Lap times are truncated to the opening laps of each race: the checks that touch
them are about per-race presence and ordering, and keeping every lap would add
a megabyte to the repository for nothing.

Only Kaggle-sourced seasons are used. That data is published CC0, so committing
a slice of it carries no attribution or share-alike obligation -- see
DATA_LICENSE.md.

Usage:  python tests/fixtures/build_fixture.py [--year 2022]
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "processed"
DST = Path(__file__).resolve().parent / "processed"

LAP_LIMIT = 8
BY_RACE = ["results", "sprint_results", "qualifying", "driver_standings",
           "constructor_standings", "constructor_results", "pit_stops", "lap_times"]
WHOLE = ["circuits", "constructors", "drivers", "status", "seasons", "team_entities",
         "team_lineage", "constructor_identity_breaks", "driver_seasons",
         "corrections_applied", "pit_lane_starts", "race_classification_notes",
         "lap_data_suspect_2018plus", "unresolved_conflicts"]


def read(name: str) -> pd.DataFrame:
    return pd.read_csv(SRC / f"{name}.csv", keep_default_na=False,
                       na_values=[r"\N", ""], low_memory=False)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--year", type=int, default=2022)
    args = ap.parse_args()

    races = read("races")
    keep = races[races["year"] == args.year]
    if keep.empty:
        raise SystemExit(f"no races found for {args.year}")
    sources = set(keep["source"])
    if sources != {"kaggle"}:
        raise SystemExit(f"{args.year} is not purely Kaggle-sourced ({sources}); "
                         "pick a season that is, so the fixture stays CC0")

    DST.mkdir(parents=True, exist_ok=True)
    rids = set(keep["raceId"])
    keep.to_csv(DST / "races.csv", index=False)
    for name in BY_RACE:
        df = read(name)
        out = df[df["raceId"].isin(rids)]
        if name == "lap_times":
            out = out[out["lap"] <= LAP_LIMIT]
        out.to_csv(DST / f"{name}.csv", index=False)
        print(f"  {name:24s} {len(out):6d} rows")
    for name in WHOLE:
        src = SRC / f"{name}.csv"
        if src.exists():
            shutil.copy(src, DST / f"{name}.csv")
    print(f"fixture for {args.year} -> {DST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
