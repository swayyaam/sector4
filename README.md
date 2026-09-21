# Sector 4

An F1 race prediction project. This repository is currently in its **data phase** — no modelling yet.

## What the data phase does

Builds a single, verified, fully traceable dataset of Formula 1 results from 1950 to the latest completed race.

1. **Analyse** the Kaggle "Formula 1 World Championship (1950-2024)" dump (an export of the now-retired Ergast API) — schema, keys, coverage, integrity and internal consistency. Written up in [`DATA_REPORT.md`](DATA_REPORT.md).
2. **Fetch** everything from 2024 onward from the [Jolpica F1 API](https://api.jolpi.ca/ergast/f1/), which mirrors the Ergast endpoint structure. *(Part 2 — not yet built.)*
3. **Validate** the result against official F1 classifications before anything is merged. *(Part 3 — not yet built.)*

### Ground rules

These are enforced throughout, not aspirational:

- **Nothing is fabricated, interpolated or back-filled.** A missing value stays null and gets flagged.
- **Every processed row carries a `source` column** (`kaggle` or `jolpica`) so provenance is always visible.
- **Source conflicts are logged with both values, never silently resolved.**
- **All times are stored in UTC**; original local date fields are preserved as-is.
- **Transforms are deterministic** — running the pipeline twice on the same inputs produces byte-identical output.

## Layout

```
data/raw/kaggle/       # the Kaggle CSVs (gitignored — download separately)
data/raw/jolpica/      # cached raw JSON responses (gitignored)
data/processed/        # merged output, 1950 -> latest race (gitignored)
data/processed/id_maps/# string-ID -> integer-ID mappings (committed; small and auditable)
src/                   # loaders, analysis, fetcher, transforms
tests/                 # pytest suite
DATA_REPORT.md         # findings, consistency checks, validation
```

Data is kept out of the repo: the Kaggle dump is a download and everything else is rebuildable by the fetcher.

## Setup

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
```

Place the Kaggle CSVs in `data/raw/kaggle/` (14 files: `circuits`, `constructor_results`, `constructor_standings`, `constructors`, `driver_standings`, `drivers`, `lap_times`, `pit_stops`, `qualifying`, `races`, `results`, `seasons`, `sprint_results`, `status`).

## Running

Analyse the Kaggle dump:

```bash
./.venv/bin/python src/profile_kaggle.py
```

Check internal consistency of the standings:

```bash
./.venv/bin/python src/standings_perround.py
```

Fetch new data from Jolpica *(Part 2 — not yet implemented)*:

```bash
./.venv/bin/python src/fetch_jolpica.py
```

Run the tests *(Part 2)*:

```bash
./.venv/bin/python -m pytest
```
