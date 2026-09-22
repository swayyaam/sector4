# Sector 4 — working rules

Standing rules for this repository. They exist because each one has already
cost something.

## Waiting on a process

Key every wait and every status check to a specific PID:

```bash
until ! ps -p 55100 >/dev/null 2>&1; do sleep 30; done
```

**Never** `pgrep -f <pattern>` or any pattern match on a command line. The
waiting shell's own command line contains the pattern, so pgrep matches
itself, the loop never exits, and every "still running" check comes back true
whether the process is alive or not.

## Git

- Identity: `swayyaam <swayyaam@gmail.com>`.
- **No `Co-Authored-By` lines and no AI attribution** in commit messages or PR
  descriptions.
- Small conventional commits (`feat:`, `fix:`, `docs:`, `test:`, `ci:`,
  `chore:`). Push after each.
- **Never `git add -A`.** Stage every path explicitly. A blanket add once
  committed an unrelated design document that happened to be sitting untracked
  in the worktree, and only CI's format check noticed.
- **Never commit to `main`.** Branch, push, open a PR, let CI run.

## Data accuracy

- **Never guess, infer, or silently fill a value.** Missing stays null and gets
  flagged.
- Every correction cites evidence — an official source or a documented internal
  derivation — in `corrections.csv` with its `evidence_type`.
- **Raw data is never modified.** Corrections are applied downstream and
  recorded.
- Where two sources disagree, record both values and the resolution. Do not
  pick one quietly.
- Times are stored in UTC. Original local date fields are kept as they are.
- Transforms are deterministic: the same inputs produce byte-identical outputs.

## Rate limits

Jolpica and FastF1 share an upstream limit, and FastF1's limiter counts refused
calls, so hitting the cap makes the next attempt worse.

- **Never run two fetchers at once.**
- CI never calls an external API. `tests/conftest.py` denies outbound
  connections, and `tests/test_no_network.py` proves it.
- The budget is `RateBudget` in `src/fetch_fastf1.py`. It counts where FastF1
  counts. Do not replace it with a proxy.

## Web

- **Run `npm run typecheck` in `web/` before pushing any web change.**
  `astro check` only reads `.astro` files and vitest does not typecheck at all,
  so a broken import in a `.ts` file passes both and fails in CI.
- **Measure Lighthouse against the production preview, identified by port:**

  ```bash
  lsof -nP -iTCP:4323 -sTCP:LISTEN -t     # never a process-name pattern
  ```

  Then confirm the served HTML contains no Vite client before trusting any
  score. An `astro dev` server holding the port once produced a Performance
  score of 83 with a 326 KB `@vite/client` in the trace, where the production
  build scored 100. A dev-server score is not a number, it is a mistake.

## Checkpoints

Stop and ask at every **STOP** in a phase prompt, and before any decision that
changes data — dropping rows, reassigning IDs, resolving a source conflict,
mapping one identifier onto another.

## Sources of truth

| Area | Document |
|---|---|
| Phase 1 data: schema, coverage, era boundaries, corrections | [`DATA_REPORT.md`](DATA_REPORT.md) |
| Phase 2 enrichment: FastF1 scope, cross-validation, gaps, tyre naming | [`ENRICHMENT_REPORT.md`](ENRICHMENT_REPORT.md) |
| Phase 2 modelling: baselines, models, diagnostics, what to ship | [`MODEL_REPORT.md`](MODEL_REPORT.md) |
| Web design system: tokens, contrast, components | [`DESIGN.md`](DESIGN.md) |
| Licensing: code, data, and what may be published | [`DATA_LICENSE.md`](DATA_LICENSE.md) |

**`DESIGN.md` exists exactly once, at the repository root.** A second copy
anywhere — `web/DESIGN.md`, another worktree, a branch — is a drift hazard:
whichever one a reader opens first wins, and the contrast test parses only the
root file. The same rule removed a duplicate prettier config earlier.

Update the document in the same PR as the change it describes.
