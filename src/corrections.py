"""Apply reviewed corrections as a separate, logged pipeline step.

Raw CSVs are never edited. Every correction lives in
``data/corrections/corrections.csv`` and must cite an official source (an FIA
classification document or formula1.com). Applying one logs the before/after so
the change is visible in the run output, and a correction whose stated
``old_value`` does not match what is actually in the data is refused rather
than applied -- that mismatch means the correction is stale or targets the
wrong row.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger("corrections")

ROOT = Path(__file__).resolve().parents[1]
CORRECTIONS_CSV = ROOT / "data" / "corrections" / "corrections.csv"

REQUIRED = ["table", "primary_key", "column", "old_value", "new_value", "reason",
            "evidence_type", "evidence_source"]

# Corrections are keyed on *natural* keys, not surrogate ids: surrogate ids are
# reassigned when Jolpica rows are merged in, so a correction keyed on one would
# silently drift onto a different row.
CORRECTION_KEYS = {
    "results": ["raceId", "driverId"],
    "sprint_results": ["raceId", "driverId"],
    "qualifying": ["raceId", "driverId"],
    "pit_stops": ["raceId", "driverId", "stop"],
    "lap_times": ["raceId", "driverId", "lap"],
    "drivers": ["driverId"],
    "constructors": ["constructorId"],
    "circuits": ["circuitId"],
    "races": ["raceId"],
    "driver_standings": ["raceId", "driverId"],
    "constructor_standings": ["raceId", "constructorId"],
    "constructor_results": ["raceId", "constructorId"],
}
# "official" = checked against formula1.com or an FIA classification document.
# "internal" = proven by the data itself, with the argument recorded in `reason`.
VALID_EVIDENCE = {"official", "internal"}


def load_corrections(path: Path = CORRECTIONS_CSV) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=REQUIRED)
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"{path} is missing required columns: {missing}")
    blank = df[df["evidence_source"].str.strip() == ""]
    if len(blank):
        raise ValueError(f"{len(blank)} correction(s) have no evidence_source; every correction must cite one")
    bad = sorted(set(df["evidence_type"]) - VALID_EVIDENCE)
    if bad:
        raise ValueError(f"unknown evidence_type(s) {bad}; must be one of {sorted(VALID_EVIDENCE)}")
    return df


def _same(a: str, b: str) -> bool:
    """Equal as numbers if both are numeric, otherwise byte-identical."""
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return a == b


def apply_corrections(tables: dict[str, pd.DataFrame], corrections: pd.DataFrame,
                      pk_columns: dict[str, list[str]]) -> tuple[dict[str, pd.DataFrame], list[dict]]:
    """Apply each correction, returning the updated tables and an audit log."""
    applied: list[dict] = []
    for _, c in corrections.iterrows():
        table = c["table"]
        if table not in tables:
            raise KeyError(f"correction targets unknown table {table!r}")
        df = tables[table]
        pk_cols = pk_columns[table]
        pk_vals = [v.strip() for v in str(c["primary_key"]).split("|")]
        if len(pk_vals) != len(pk_cols):
            raise ValueError(f"correction for {table} needs {len(pk_cols)} key part(s) {pk_cols}, "
                             f"got {pk_vals!r}")
        mask = pd.Series(True, index=df.index)
        for col, val in zip(pk_cols, pk_vals):
            mask &= df[col].astype(str) == val
        n = int(mask.sum())
        if n != 1:
            raise ValueError(f"correction for {table} key={c['primary_key']!r} matched {n} rows, expected 1")

        col = c["column"]
        current = df.loc[mask, col].iloc[0]
        current_s = "" if pd.isna(current) else str(current)
        # Numbers compare numerically so that 1 matches a float column's 1.0.
        # Everything else compares exactly, not stripped: a correction may
        # legitimately target a whitespace bug (Kaggle stores "Argentinian "
        # with a trailing space), which stripping would make unaddressable.
        expected = str(c["old_value"])
        if expected not in ("", "*") and not _same(current_s, expected):
            raise ValueError(
                f"refusing correction for {table}.{col} key={c['primary_key']}: "
                f"expected old_value={expected!r} but found {current_s!r}. "
                "The correction is stale or targets the wrong row."
            )
        new_raw = str(c["new_value"])
        new_val = None if new_raw.strip() in ("", r"\N") else new_raw
        if new_val is not None:
            new_val = pd.Series([new_val]).astype(df[col].dtype, errors="ignore").iloc[0]
        df.loc[mask, col] = new_val
        log.info("  correction: %s.%s [%s] %r -> %r (%s)", table, col, c["primary_key"],
                 current_s, new_raw, c["reason"])
        applied.append({"table": table, "primary_key": c["primary_key"], "column": col,
                        "old": current_s, "new": new_raw, "reason": c["reason"],
                        "evidence_type": c["evidence_type"],
                        "evidence_source": c["evidence_source"]})
    return tables, applied
