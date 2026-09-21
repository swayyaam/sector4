"""Transform Jolpica JSON into the exact Kaggle/Ergast CSV schema.

Field-mapping decisions, all verified against the live API rather than assumed
(see DATA_REPORT.md "Jolpica vs Kaggle" for the evidence):

* Jolpica's ``position`` is a dense 1..N classification rank -- it is Kaggle's
  ``positionOrder``, *not* Kaggle's ``position``. A retired driver comes back as
  ``position=15, positionText='R'``. Kaggle's ``position`` is null whenever the
  driver is not in the official classification, so we derive it from
  ``positionText`` instead.
* ``Time.millis`` is the driver's **total race time**, not the gap -- matching
  Kaggle. ``Time.time`` is absolute for the winner and ``+gap`` for everyone
  else.
* Jolpica supplies no ``AverageSpeed``, so ``results.fastestLapSpeed`` is null
  for every fetched row. No altitude either, so ``circuits.alt`` is null for
  genuinely new circuits. Neither is invented.
* Pit stops and lap times arrive without a milliseconds field. We derive it by
  parsing the exact time string -- a lossless unit conversion, not an estimate.
  Part 1 verified the two agree on all 600k Kaggle rows.
"""
from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------- null token
NULL = r"\N"

# Exact Kaggle column orders.
COLUMNS: dict[str, list[str]] = {
    "circuits": ["circuitId", "circuitRef", "name", "location", "country", "lat", "lng", "alt", "url"],
    "constructor_results": ["constructorResultsId", "raceId", "constructorId", "points", "status"],
    "constructor_standings": ["constructorStandingsId", "raceId", "constructorId", "points", "position",
                              "positionText", "wins"],
    "constructors": ["constructorId", "constructorRef", "name", "nationality", "url"],
    "driver_standings": ["driverStandingsId", "raceId", "driverId", "points", "position", "positionText", "wins"],
    "drivers": ["driverId", "driverRef", "number", "code", "forename", "surname", "dob", "nationality", "url"],
    "lap_times": ["raceId", "driverId", "lap", "position", "time", "milliseconds"],
    "pit_stops": ["raceId", "driverId", "stop", "lap", "time", "duration", "milliseconds"],
    "qualifying": ["qualifyId", "raceId", "driverId", "constructorId", "number", "position", "q1", "q2", "q3"],
    "races": ["raceId", "year", "round", "circuitId", "name", "date", "time", "url", "fp1_date", "fp1_time",
              "fp2_date", "fp2_time", "fp3_date", "fp3_time", "quali_date", "quali_time", "sprint_date",
              "sprint_time"],
    "results": ["resultId", "raceId", "driverId", "constructorId", "number", "grid", "position", "positionText",
                "positionOrder", "points", "laps", "time", "milliseconds", "fastestLap", "rank", "fastestLapTime",
                "fastestLapSpeed", "statusId"],
    "seasons": ["year", "url"],
    "sprint_results": ["resultId", "raceId", "driverId", "constructorId", "number", "grid", "position",
                       "positionText", "positionOrder", "points", "laps", "time", "milliseconds", "fastestLap",
                       "fastestLapTime", "statusId"],
    "status": ["statusId", "status"],
}

# Extra fields Jolpica provides that the Kaggle schema has nowhere to put.
SIDECAR_COLUMNS = ["raceId", "year", "round", "field", "date", "time"]


# ------------------------------------------------------------------ parsing
_LAP_RE = re.compile(r"^(?:(\d+):)?(\d+)\.(\d{1,3})$")
_FULL_RE = re.compile(r"^(?:(\d+):)?(?:(\d+):)?(\d+)\.(\d{1,3})$")


def parse_duration_ms(s: str | None) -> int | None:
    """``'38.109'`` / ``'1:38.109'`` / ``'1:42:06.304'`` -> milliseconds.

    Handles the optional hours component: 43 Kaggle lap times use ``H:MM:SS.mmm``
    under red flags, and a parser that only understands ``M:SS.mmm`` silently
    drops them.
    """
    if s is None:
        return None
    s = str(s).strip()
    if not s or s == NULL:
        return None
    neg = s.startswith("-")
    s = s.lstrip("+-")
    m = _FULL_RE.match(s)
    if not m:
        return None
    g1, g2, sec, frac = m.groups()
    if g2 is not None:          # H:MM:SS.mmm
        hours, minutes = int(g1), int(g2)
    elif g1 is not None:        # M:SS.mmm
        hours, minutes = 0, int(g1)
    else:                       # SS.mmm
        hours, minutes = 0, 0
    total = hours * 3_600_000 + minutes * 60_000 + int(sec) * 1000 + int(frac.ljust(3, "0"))
    return -total if neg else total


def is_gap(s: str | None) -> bool:
    """True when a results time string is a ``+gap`` rather than an absolute time."""
    return isinstance(s, str) and s.strip().startswith("+")


def encode_position(position: str | int | None, position_text: str | None) -> tuple[Any, str, Any]:
    """Jolpica (position, positionText) -> Kaggle (position, positionText, positionOrder).

    Kaggle's ``position`` is null unless the driver is in the official
    classification; ``positionOrder`` is the dense finishing rank and is always
    present. Jolpica's ``position`` is that dense rank.
    """
    order = int(position) if position is not None and str(position) != "" else None
    pt = str(position_text) if position_text is not None else ""
    pos = int(pt) if pt.isdigit() else None
    return pos, pt, order


# ---------------------------------------------------------------- id mapping
def build_ref_map(existing: dict[str, int], refs: list[str], *, start_at: int) -> tuple[dict[str, int], list[dict]]:
    """Map string refs to integer ids, reusing existing ones and minting the rest.

    New ids are assigned in sorted-ref order starting just after the current
    maximum, so the same inputs always produce the same ids.
    """
    mapping = dict(existing)
    new: list[dict] = []
    nxt = start_at
    for ref in sorted(set(refs)):
        if ref in mapping:
            continue
        mapping[ref] = nxt
        new.append({"ref": ref, "id": nxt})
        nxt += 1
    return mapping, new


# ------------------------------------------------------------------- points
def recompute_driver_points(results: list[dict], sprints: list[dict]) -> dict[str, float]:
    """Total championship points per driverId from race + sprint results."""
    totals: dict[str, float] = {}
    for src in (results, sprints):
        for row in src:
            did = row["Driver"]["driverId"]
            totals[did] = totals.get(did, 0.0) + float(row.get("points", 0) or 0)
    return totals


def recompute_constructor_points(results: list[dict], sprints: list[dict]) -> dict[str, float]:
    """Total points per constructorId from race + sprint results.

    Valid from 1980 on. Part 1 showed this reproduces ``constructor_results``
    exactly for 1980+, while pre-1979 only the best-placed car scored.
    It does **not** include championship penalties -- those live in the
    standings table (2018 Force India, 2020 Racing Point).
    """
    totals: dict[str, float] = {}
    for src in (results, sprints):
        for row in src:
            cid = row["Constructor"]["constructorId"]
            totals[cid] = totals.get(cid, 0.0) + float(row.get("points", 0) or 0)
    return totals


# ------------------------------------------------------------- serialisation
def fmt(value: Any) -> str:
    """Render one value the way the Kaggle CSVs do."""
    if value is None or value == "":
        return NULL
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    return str(value)


def _needs_quotes(raw: Any, rendered: str) -> bool:
    if rendered == NULL:
        return False
    return isinstance(raw, str)


def to_csv_line(row: dict, columns: list[str]) -> str:
    """One CSV line matching Kaggle's style: strings quoted, numbers and \\N bare."""
    out = []
    for c in columns:
        raw = row.get(c)
        rendered = fmt(raw)
        if _needs_quotes(raw, rendered):
            out.append('"' + rendered.replace('"', '""') + '"')
        else:
            out.append(rendered)
    return ",".join(out)


def write_table(path, rows: list[dict], table: str) -> int:
    cols = COLUMNS[table]
    lines = [",".join(cols)]
    lines.extend(to_csv_line(r, cols) for r in rows)
    path.write_text("\n".join(lines) + "\n")
    return len(rows)
