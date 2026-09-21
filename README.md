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
data/raw/f1_grids/        # cached official starting-grid pages (gitignored)
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

Scrape official starting grids (settles `pit_lane_start`, which Jolpica cannot express):

```bash
./.venv/bin/python src/scrape_grids.py
```

Merge Kaggle + Jolpica into `data/processed/`:

```bash
./.venv/bin/python src/merge.py
```

Build the team lineage and identity-break tables:

```bash
./.venv/bin/python src/team_lineage.py
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

## What the merged output contains

Beyond the 14 Kaggle-schema tables, `data/processed/` carries:

| File | What it is |
|---|---|
| `driver_seasons.csv` | driverId x year x constructorId x car number x races — the per-season truth `drivers.number` cannot express |
| `team_lineage.csv` | 33 verified successions (rebrand / takeover / new_entry). **No IDs are merged** |
| `constructor_identity_breaks.csv` | The opposite hazard: 21 constructorIds covering unrelated teams (Aston Martin 1959-60 vs 2021-26, Mercedes 1954-55 vs 2010-26) |
| `pit_lane_starts.csv` | Per-driver pit-lane fact scraped from 39 official starting grids |
| `corrections_applied.csv` | Audit log of every correction with its evidence |
| `unresolved_conflicts.csv` | Source disagreements still open (currently empty) |
| `lap_data_suspect_2018plus.csv` | Lap-count disagreements inside the likely modelling window |
| `race_sessions_extra.csv` | Sidecar for fields the Kaggle schema cannot hold (Sprint Qualifying) |

Derived columns added to the standard tables: `source`, `regs_era`, `grid_slot`, `pit_lane_start`, `elapsed_ms`, `lap_data_suspect`, `red_flag_affected`, `counts_as_official_stop`, `official_stop_number`, `championship_points`, `conflict_unresolved`.

## Notes for modelling

- **Standings are post-race snapshots.** The row for `raceId = R` already includes race R's points. A model predicting race R must use round R−1 or a recomputed pre-race total. See the leakage section of the report.
- **Retirement cause is unavailable from 2025.** Jolpica collapses every retirement to "Retired"; the granular Ergast taxonomy only exists up to 2024.
- **2026 is a regulation reset** (new power units, active aero, Audi and Cadillac entering), so pre-2026 car performance is a weak prior. `races.regs_era` carries the boundary.
- **`constructorId` is not a stable team identity.** Aston Martin's ID spans 1959-60 and 2021-26 — officially unrelated teams. Check `constructor_identity_breaks.csv` before using it as a categorical.
- **`drivers.number` means "most recent permanent number"**, not the number used in a given season. Use `results.number` or `driver_seasons.csv`.
- **Use `official_stop_number`, not `stop`,** for pit-stop counts: the raw index counts red-flag pit-lane holds.
- The report's **"Known era boundaries"** section lists 18 recording artefacts that are not real signal. Read it before feature engineering.
