# Deploying Sector 4

The site is a static Astro build in `web/`, hosted on Vercel. This file covers
the Vercel project, the domain, what to check after a deploy, and the commands
to run around each race weekend.

**Status:** not deployed. Deployment is held until R15 (Azerbaijan, 2026) has
been scored. Before the first production deploy:

1. `contact_email` and `jurisdiction_city` are set in `web/src/data/legal.json`.
   A production build refuses to run if either is ever removed.
2. The domain is **`sector4.swayam.codes`** (see [Custom domain](#custom-domain)).

---

## Vercel project settings

Create one project from the GitHub repository `swayyaam/sector4`.

| Setting | Value | Where it is pinned |
|---|---|---|
| Root Directory | `web` | Vercel dashboard only |
| Framework Preset | Astro | `web/vercel.json` |
| Install Command | `npm ci` | `web/vercel.json` |
| Build Command | `npm run build` | `web/vercel.json` |
| Output Directory | `dist` | `web/vercel.json` |
| Node.js Version | 22.x | `web/package.json` `engines`, and `web/.nvmrc` locally |
| Plan | Hobby | The privacy policy quotes Hobby's one-hour log retention |

Leave on:

- **Automatically expose System Environment Variables** (Settings → Environment
  Variables). The build reads `VERCEL_PROJECT_PRODUCTION_URL` for canonical
  URLs and `VERCEL_ENV` for the release guard. A Vercel build without them fails
  on purpose.

Leave off, because the privacy policy says they do not exist:

- Web Analytics
- Speed Insights
- The Vercel Toolbar on preview deployments. Its script comes from another
  origin, and the Content Security Policy blocks it anyway.

**Environment variables to add: none. Secrets: none.** The build reads only
Vercel's own system variables.

If the plan changes, update `hosting.plan` and `hosting.runtime_log_retention`
in `web/src/data/legal.json`, and the privacy policy with them, **before** the
change.

## Branches and deployments

- **Production branch: `main`.** Every merge to `main` deploys production. Never
  commit to `main` directly: branch, push, open a PR, let CI run, merge.
- **Every PR gets a preview deployment.** Vercel protects previews behind its
  login and sends `noindex` on them. A preview shows "not yet set" badges on
  the legal pages while facts are missing; production refuses to build.

## What the build refuses to publish

Each of these fails the build, locally, in CI and on Vercel:

| Problem | Caught by |
|---|---|
| A data file that breaks the schema (probabilities that do not sum, a driver who does not exist, a result scored before its prediction) | `web/src/lib/schema.ts`, at build |
| Anything the privacy policy says never happens: a request to another origin, cookies, browser storage, a network call from a script | `web/integrations/publish-guards.mjs`, after build |
| A production deploy without the legal contact or jurisdiction | the same file, before build |
| A Vercel build without the production URL | `web/astro.config.mjs` |

## Headers

Set in `web/vercel.json` and verified locally with a server that applies them:
every page loads with no CSP violation and no console error, and Lighthouse on
the home page scores 100 in all four categories.

| Header | Value and why |
|---|---|
| `Content-Security-Policy` | `default-src 'none'`, then `'self'` only for scripts, styles, images, fonts and connections. Scripts are emitted as files, so there is no inline script allowance. Styles allow `'unsafe-inline'` for the inline stylesheet and the `style` attributes that set bar widths and team colours. `connect-src 'self'` rather than `'none'` so Lighthouse can fetch `robots.txt`; no script on the site makes a request, and the build guard enforces that. No framing, no forms, no `<base>`. |
| `Strict-Transport-Security` | Two years, `includeSubDomains`, **no `preload`**. Preload is hard to undo; add it only deliberately, once the domain is settled. |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY`, alongside `frame-ancestors 'none'` for older browsers |
| `Referrer-Policy` | `strict-origin-when-cross-origin`: other sites learn only which site a visitor came from, as the privacy policy says |
| `Cross-Origin-Opener-Policy` | `same-origin` |
| `Permissions-Policy` | Every feature the site does not use is denied: camera, microphone, geolocation, payment, USB and the rest |

| Path | `Cache-Control` |
|---|---|
| `/_astro/*` (content-hashed scripts) | `public, max-age=31536000, immutable` |
| `/fonts/*` (not hashed) | `public, max-age=2592000, stale-while-revalidate=86400` |
| `/og/*` (cards change as predictions change) | `public, max-age=3600, must-revalidate` |
| Everything else: HTML, sitemap, robots, favicon | `public, max-age=0, must-revalidate` |

The cache rules do not overlap, so no two rules set the same header on the same
path.

## Custom domain

**Decided: `sector4.swayam.codes`,** a subdomain of `swayam.codes`, which is
registered at name.com and already served by Vercel. (`sector4.dev`, the
earlier placeholder, does not resolve and is not used anywhere.)

**Nothing in the repo names a domain.** The site's URL comes from Vercel's
`VERCEL_PROJECT_PRODUCTION_URL`: the shortest custom domain attached to the
project, or its `vercel.app` domain until one is. Attaching a domain needs no
code change.

### Setting up `sector4.swayam.codes`

1. Vercel → project → Settings → Domains → Add `sector4.swayam.codes`.
2. At name.com, DNS for `swayam.codes`, add:

   | Type | Host | Answer |
   |---|---|---|
   | `CNAME` | `sector4` | the target Vercel shows for this project, of the form `<hash>.vercel-dns-0NN.com` |

   The target is unique to the project, so copy it from the dashboard rather
   than from anywhere else. Leave the existing records for `swayam.codes` alone.
3. Wait for Vercel to show the domain as valid. It issues the certificate itself.

### If an apex domain is ever used instead

1. Add both `example.com` and `www.example.com` in Settings → Domains, and set
   one to redirect to the other.
2. At the registrar:

   | Type | Host | Answer |
   |---|---|---|
   | `A` | `@` | the IP on the domain's card in Vercel (Vercel's documentation gives `76.76.21.21`) |
   | `CNAME` | `www` | the project's target from the dashboard |

### Once the domain is live

- **Redeploy production.** The URL is written into the pages at build time, so
  the deploy made before the domain was attached still names the `vercel.app`
  address.
- Check that `view-source:` on any page shows the new domain in
  `<link rel="canonical">` and `og:image`, and that `/sitemap.xml` and
  `/robots.txt` use it too.
- Nothing to edit in the repo.

## First deploy

1. Merge the legal pages PR, then this one.
2. Vercel → Add New → Project → import `swayyaam/sector4` → set Root Directory
   to `web` → Deploy. Everything else comes from `web/vercel.json`.
3. Confirm the settings above, then attach the domain.
4. Run the post-deploy checklist.

## Post-deploy checklist

Replace `$SITE` with the production URL, `https://sector4.swayam.codes` once
the domain is attached.

**Pages.** Open each one and read it:

- `$SITE/`
- the next race, `$SITE/races/2026/<slug>/`
- `$SITE/track-record/`
- `$SITE/methodology/`
- `$SITE/credits/`
- `$SITE/privacy/`
- `$SITE/terms/`
- a URL that does not exist, which should show the 404 page with status 404
- `$SITE/privacy`, without the slash, which should redirect to `/privacy/`

**Console and network.** In desktop DevTools, on each page: zero console
errors, zero CSP violations, and in the Network tab every request goes to the
site's own domain.

**Headers.**

```bash
curl -sI "$SITE/" | grep -iE "content-security|strict-transport|referrer|permissions|x-content|x-frame|cache-control"
```

```bash
curl -sI "$SITE$(curl -s "$SITE/" | grep -o '/_astro/[^"]*\.js' | head -1)" | grep -i cache-control
```

The second should say `immutable`.

**Lighthouse, mobile, on the live URL.** Every category must be 95 or higher.

```bash
npx lighthouse "$SITE/" --only-categories=performance,accessibility,best-practices,seo --output=html --output-path=./lighthouse-home.html
```

Run it for the home page, the next race page and `/privacy/`.

**Link previews.** Paste `$SITE/` and the next race page into a private chat
(or any Open Graph checker). Each preview should show its own card, and the race
card should name the snapshot and when it was generated. Open the `og:image`
URL directly: it must load from the production domain.

**Sitemap and robots.** `$SITE/sitemap.xml` lists the six fixed pages and
every predicted race, all on the production domain. `$SITE/robots.txt` allows
everything and points to that sitemap.

**Real phones.** On an iPhone (Safari) and an Android phone (Chrome), check:

- The layout has no sideways scrolling, and the menu opens and closes.
- Session times show in the phone's own time zone.
- The countdown ticks over at the next minute.
- The snapshot toggle switches.

## After each race weekend

### Rules

- **Never run two fetchers at once.** The fetchers are `fetch_jolpica.py`,
  `fetch_fastf1.py` and `scrape_grids.py`. Jolpica and FastF1 share an upstream
  limit. Start one, wait for its PID to exit, then start the next:
  `until ! ps -p <PID> >/dev/null 2>&1; do sleep 30; done`
- **Pre-weekend** is published before the first session of the weekend,
  which is FP1 on every current weekend format. Publication
  means the prediction file is **committed and pushed**; the commit is the
  proof of when it was public.
- **Post-qualifying** is published after qualifying and before the race
  starts.
- **Scoring** happens after the result is in Jolpica. `fetch_jolpica.py` treats
  a race as finished four hours after its scheduled start, and results within
  30 days are re-fetched in case they are amended.
- `predict.py` refuses to overwrite a prediction, and refuses to write anything
  after its deadline: a first prediction or a revision. The deadline is the
  first session for pre-weekend and the race start for post-qualifying.
- `predict.py` rebuilds its cached features by itself whenever the data is newer
  than the cache. That takes about 100 seconds the first time after new data.
- Session times for every upcoming race are in
  `web/src/data/live/reference.json`, in UTC.

All commands run from the repo root with the project's virtualenv.

### 1. After race N: bring the result in, score it

Once race N has finished and Jolpica has its classification, work on a branch:

```bash
git switch -c score/2026-rN main
```

```bash
./.venv/bin/python src/fetch_jolpica.py --seasons 2026
```

```bash
./.venv/bin/python src/build_processed.py
```

Add race N's official starting-grid page to `RACES` in `src/scrape_grids.py`:
`(N, <id>, "<slug>")`, taken from the race's official result URL,
`https://www.formula1.com/en/results/2026/races/<id>/<slug>/race-result`.
Never infer the id from the sequence; the ids skip numbers. Without the entry,
the race's `pit_lane_start` stays null. `scrape_grids.py` is a fetcher, so run
it only after `fetch_jolpica.py` has exited:

```bash
./.venv/bin/python src/scrape_grids.py
```

```bash
./.venv/bin/python src/merge.py
```

```bash
./.venv/bin/python src/team_lineage.py
```

Refresh `data/ground_truth/official_standings.json` to the standings after
race N, from `https://www.formula1.com/en/results/2026/drivers` and `/team`.
Set `after_round` to N and update `_retrieved_utc` and `_note`. Before using the
new figures, check them against official sources only: the previous standings
plus race N's official result points (and any sprint points) must equal the new
standings for every driver and team. Never copy them from our own data, which
would make the check circular. Then validate:

```bash
./.venv/bin/python src/validate.py
```

Stop unless it reports 0 failed. Then score and rebuild the site data:

```bash
./.venv/bin/python src/score_race.py --season 2026 --round N
```

```bash
./.venv/bin/python src/build_site_data.py
```

If the web build then reports a driver "who has no prediction", the race's field
differed from a snapshot's. `build_site_data.py` declares both directions
(`unpredicted_starters`, `predicted_non_starters`) and the race page states them,
so this should not happen; if it does, stop and look.

Build the site before pushing (`npm run typecheck`, `npx vitest run`,
`npm run build` in `web/`), then commit the pipeline changes and the scoring
separately from any prediction:

```bash
git add src/scrape_grids.py data/ground_truth/official_standings.json
```

```bash
git commit -m "chore: add round N's grid page and the standings after it"
```

```bash
git add predictions/track_record.json predictions/results/ web/src/data/live/
```

```bash
git commit -m "feat: score the 2026 round N predictions"
```

```bash
git push -u origin score/2026-rN
```

Open a PR, let CI pass, merge. Merging deploys. Until the next race's
pre-weekend prediction is published, the site shows no next race.

### 2. Before race N+1: pre-weekend prediction

Before the first session of race N+1:

```bash
./.venv/bin/python src/predict.py --season 2026 --round N+1 --snapshot pre_weekend
```

```bash
git switch -c predict/2026-rN+1-pre main
```

```bash
git add predictions/2026/<N+1>-pre_weekend.json
```

```bash
git commit -m "feat: publish the 2026 round N+1 pre-weekend prediction"
```

```bash
git push -u origin predict/2026-rN+1-pre
```

The push must land before the first session starts. Then rebuild the site data
on the same branch, commit it, open a PR and merge:

```bash
./.venv/bin/python src/build_site_data.py
```

```bash
git add web/src/data/live/ && git commit -m "feat: show the round N+1 prediction" && git push
```

Optional between races: bring in FastF1 data for completed races, which the
model trains on. It is a fetcher, so it runs alone:

```bash
./.venv/bin/python src/fetch_fastf1.py --seasons 2026
```

### 3. After qualifying for race N+1: post-qualifying prediction

Between the end of qualifying and the start of the race. The race has not run,
so its weekend is read straight from the fetched session data rather than from
`data/processed` (see `src/upcoming.py`). The field is the qualifying
classification, never a previous race's.

Wait until qualifying finished at least 90 minutes ago; `fetch_fastf1.py`
will not load a session any sooner, so it is not cached half-written.

Fetch the qualifying classification from Jolpica, and wait for the process to
exit:

```bash
./.venv/bin/python src/fetch_jolpica.py --seasons 2026
```

Fetch the weekend's practice and qualifying sessions from FastF1:

```bash
./.venv/bin/python src/fetch_fastf1.py --upcoming 2026 N+1
```

Its last lines must say `fetched Practice 1(...), Practice 2(...),
Practice 3(...), Qualifying(...)`. On a sprint weekend there is only
Practice 1. Then predict:

```bash
./.venv/bin/python src/predict.py --season 2026 --round N+1 --snapshot post_qualifying
```

If it refuses, the message names what is missing and which command to run. The
usual case is that Jolpica has not published qualifying yet; wait and repeat
the Jolpica fetch. It never fills a gap.

Publish before the race starts:

```bash
git switch -c predict/2026-rN+1-post main
```

```bash
git add predictions/2026/<N+1>-post_qualifying.json
```

```bash
git commit -m "feat: publish the 2026 round N+1 post-qualifying prediction"
```

```bash
git push -u origin predict/2026-rN+1-post
```

Then show it on the site, on the same branch, and open a PR and merge:

```bash
./.venv/bin/python src/build_site_data.py
```

```bash
git add web/src/data/live/ && git commit -m "feat: show the round N+1 post-qualifying prediction" && git push
```

### This weekend: R15, Azerbaijan

All times UTC, from the schedule in `web/src/data/live/reference.json`.

| Session | Starts |
|---|---|
| Practice 1 | Thu 24 Sep, 08:30 |
| Practice 2 | Thu 24 Sep, 12:00 |
| Practice 3 | Fri 25 Sep, 08:30 |
| Qualifying | Fri 25 Sep, 12:00 |
| Race | Sat 26 Sep, 11:00 |

- **Post-qualifying:** from Fri 25 Sep, 13:30 until Sat 26 Sep, 11:00. Run
  section 3 with `N+1` = `15`: the files are
  `predictions/2026/15-post_qualifying.json` and branch
  `predict/2026-r15-post`.
- **Scoring:** Sat 26 Sep, from 15:00, once Jolpica has the result. Run section
  1 with `N` = `15`: score with `--round 15` on branch `score/2026-r15`. Both
  R15 snapshots are scored, and each gets its first row on the track record.
- **Deploy** stays on hold until the scoring is merged.
