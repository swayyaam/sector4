"""Split shared constructorIds into distinct team entities.

Ergast reuses one `constructorId` for teams that have nothing to do with each
other: `aston_martin` covers both the 1959-60 works team and the 2021-26 team
that descends from Jordan, 61 years apart. A model that treats `constructorId`
as a stable identity will pool them.

`team_entity_id` splits each constructorId at every gap of more than
`GAP_YEARS` idle seasons, giving a key that never spans an identity break.
`constructorId` itself is left untouched.

Format: "<constructorId>-<first year of that block>", e.g. "117-1959" and
"117-2021". Uniform across all constructors so it can be joined on directly.
"""
from __future__ import annotations

import pandas as pd

GAP_YEARS = 4          # more than this many idle seasons starts a new entity


def year_blocks(years: list[int], gap: int = GAP_YEARS) -> list[list[int]]:
    """Split a sorted year list wherever the gap exceeds `gap`."""
    ys = sorted(set(int(y) for y in years))
    if not ys:
        return []
    blocks, cur = [], [ys[0]]
    for a, b in zip(ys, ys[1:]):
        if b - a <= gap:
            cur.append(b)
        else:
            blocks.append(cur)
            cur = [b]
    blocks.append(cur)
    return blocks


def constructor_blocks(frames: list[pd.DataFrame], races: pd.DataFrame,
                       gap: int = GAP_YEARS) -> dict[int, list[list[int]]]:
    """Active-year blocks per constructorId, pooled across several tables.

    Pooling matters: a constructor can appear in `constructor_standings` for a
    race it has no `results` rows in (the 1958 Indianapolis 500 does exactly
    this), and every table must agree on where the breaks fall.
    """
    ry = races.set_index("raceId")["year"]
    years: dict[int, set[int]] = {}
    for df in frames:
        if df is None or not len(df) or "constructorId" not in df.columns:
            continue
        sub = df[["raceId", "constructorId"]].dropna()
        for cid, y in zip(sub["constructorId"], sub["raceId"].map(ry)):
            if pd.notna(y):
                years.setdefault(int(cid), set()).add(int(y))
    return {cid: year_blocks(sorted(ys), gap) for cid, ys in years.items()}


def team_entity_map(blocks: dict[int, list[list[int]]]) -> dict[tuple[int, int], str]:
    """(constructorId, year) -> team_entity_id."""
    out: dict[tuple[int, int], str] = {}
    for cid, bl in blocks.items():
        for block in bl:
            eid = f"{cid}-{block[0]}"
            for y in range(block[0], block[-1] + 1):
                out[(cid, y)] = eid
    return out


def assign(df: pd.DataFrame, races: pd.DataFrame, mapping: dict[tuple[int, int], str]) -> pd.Series:
    """team_entity_id for each row of a table carrying raceId + constructorId."""
    ry = races.set_index("raceId")["year"]
    yrs = df["raceId"].map(ry)
    return pd.Series(
        [mapping.get((int(c), int(y))) if pd.notna(c) and pd.notna(y) else None
         for c, y in zip(df["constructorId"], yrs)],
        index=df.index, dtype="object")
