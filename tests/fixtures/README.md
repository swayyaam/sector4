# Test fixtures

`processed/` is one complete season (2022) of `data/processed/`, committed so
CI can run the validation suite. The real dataset is 43MB and gitignored.

Rebuild it with:

    python tests/fixtures/build_fixture.py --year 2022

Two things about it are deliberate:

- **Lap times are truncated** to the first 8 laps of each race. The checks that
  read them are about per-race presence and ordering, and the full season would
  add a megabyte for no extra coverage.
- **The season is Kaggle-sourced**, which is published CC0. A slice of it can be
  committed with no attribution or share-alike obligation. The build script
  refuses any season that is not. See `DATA_LICENSE.md`.

Against this fixture the suite reports 56 passed and 13 not applicable. The
thirteen are checks about seasons the fixture omits — the 2007 McLaren penalty,
the 2024–2026 ground-truth comparisons, constructor identity breaks spanning
decades. They are reported as skipped with a reason rather than dropped, so the
total still adds up to the 69 checks the full dataset runs.
