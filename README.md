# Sector 4

An F1 race prediction project. This repository is currently in its **data phase** — no modelling yet.

## What the data phase does

Builds a single, verified, fully traceable dataset of Formula 1 results from **1950 to the latest completed race**.

1. **Analyse** the Kaggle "Formula 1 World Championship (1950-2024)" dump (an export of the retired Ergast API) — schema, keys, coverage, integrity and internal consistency.
2. **Fetch** 2024 onward from the [Jolpica F1 API](https://api.jolpi.ca/ergast/f1/), which mirrors the Ergast endpoint structure. 2024 is re-fetched deliberately so the overlap can be diffed.
3. **Validate** against official F1 classifications, then merge.

Findings, the overlap diff and the validation pass/fail table are in [`DATA_REPORT.md`](DATA_REPORT.md).

### Ground rules

Enforced in code, not aspirational:

- **Nothing is fabricated, interpolated or back-filled.** A missing value stays null and gets flagged. Where the pit-lane fact cannot be determined for 2025+, `pit_lane_start` is **null**, never `False`.
- **Every row carries a `source` column** (`kaggle` or `jolpica`).
- **Raw CSVs are never edited.** Corrections live in `data/corrections/corrections.csv` and are applied as a separate logged step. Every correction cites an `evidence_source` and is tagged `official` (checked against formula1.com or an FIA document) or `internal` (proven by the data itself, with the argument recorded). A correction whose stated `old_value` no longer matches the data is **refused**, so a stale one cannot silently rewrite the wrong row.
- **Derived columns are added, never substituted** for a raw one.
- **Source conflicts are logged with both values**, never silently resolved. Anything still open is in `data/processed/unresolved_conflicts.csv`.
- **All times are UTC**; original local date fields are preserved.
- **Transforms are deterministic** — same inputs, byte-identical outputs. New IDs are assigned in sorted order after the current maximum.

## Layout

```
data/raw/kaggle/          # the Kaggle CSVs (gitignored — download separately)
data/raw/jolpica/         # cached raw JSON (gitignored, rebuildable)
data/corrections/         # reviewed corrections, with evidence (committed)
data/ground_truth/        # official standings used for validation (committed)
data/processed/           # merged output, 1950 -> latest race (gitignored)
data/processed/id_maps/   # string-ID -> integer-ID maps (committed; small and auditable)
src/                      # client, fetcher, transform, merge, validation
tests/                    # pytest suite
```

## Setup

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
```

Place the 14 Kaggle CSVs in `data/raw/kaggle/`.

## Running the pipeline

Fetch from Jolpica (cached; a rerun only costs new races plus the 30-day provisional window):

```bash
./.venv/bin/python src/fetch_jolpica.py
```

Transform the cached JSON into Kaggle-schema tables:

```bash
./.venv/bin/python src/build_processed.py
```

Regenerate the corrections file from the reviewed overlap diff:

```bash
./.venv/bin/python src/make_corrections.py
```

Merge Kaggle + Jolpica into `data/processed/`:

```bash
./.venv/bin/python src/merge.py
```

Validate the merged dataset:

```bash
./.venv/bin/python src/validate.py
```

Run the tests:

```bash
./.venv/bin/python -m pytest
```

### Useful flags

`src/fetch_jolpica.py --dry-run` shows what would be fetched without pulling data. `--skip-laps` omits lap times, which are roughly 75% of all requests. `--seasons 2026` restricts to one season.

## Notes for modelling

- **Standings are post-race snapshots.** The row for `raceId = R` already includes race R's points. A model predicting race R must use round R−1 or a recomputed pre-race total. See the leakage section of the report.
- **Retirement cause is unavailable from 2025.** Jolpica collapses every retirement to "Retired"; the granular Ergast taxonomy only exists up to 2024.
- **2026 is a regulation reset** (new power units, active aero, Audi and Cadillac entering), so pre-2026 car performance is a weak prior. `races.regs_era` carries the boundary.
