# Data licences

`LICENSE` covers the code in this repository. It does not cover the motor
racing data, which is not ours to licence. This file records the terms of
every upstream source, read from that source's own licence or terms document
rather than assumed, and what those terms mean for this project.

Quotations below are from the linked documents. Where a source's terms are no
longer reachable at their original address, the archived copy is linked and
labelled as such.

**Last verified: 21 September 2026.** Terms change. Re-read them before any
deployment, any change of hosting, and any commercial decision.

---

## Summary

| Source | What it gives us | Terms | Redistributable? |
|---|---|---|---|
| [Kaggle F1 export](#kaggle-formula-1-world-championship-19502024) | Results, qualifying, grids, laps, pit stops, 1950–2024 | CC0 1.0 (uploader's dedication); upstream Ergast was non-commercial | Yes, non-commercially |
| [Jolpica F1 API](#jolpica-f1-api) | Everything from 2025 onward | **CC BY-NC-SA 4.0** | Yes, with attribution, non-commercially, share-alike |
| [FastF1](#fastf1-and-the-underlying-formula-1-timing-data) | The library itself | MIT | Yes |
| [Formula 1 live timing](#fastf1-and-the-underlying-formula-1-timing-data) | Session timing, telemetry, weather, race control | **© Formula One World Championship Limited. Personal, non-commercial use only. No republication without prior written consent.** | **No** |
| [f1-circuits](#f1-circuits) | Circuit outlines | MIT | Yes |
| [Inter](#typefaces) | Typeface | SIL OFL 1.1 | Yes |

The two binding constraints, in one sentence each:

1. **This project is non-commercial and stays that way.** Two separate sources
   require it, so it is not a preference that can be traded away later.
2. **Nothing derived from Formula 1 live timing may be published.** It stays in
   `data/raw/fastf1/` and `data/enriched/`, both of which are gitignored.

---

## Kaggle: Formula 1 World Championship (1950–2024)

- Author: Rohan Rao (Vopani)
- <https://www.kaggle.com/datasets/rohanrao/formula-1-world-championship-1950-2020>
- Licence as published: **CC0 1.0 Universal (Public Domain Dedication)** —
  <https://creativecommons.org/publicdomain/zero/1.0/>

The dataset page states the data is "compiled from http://ergast.com/mrd/".
The CC0 dedication is the uploader's; the upstream source had its own terms,
which are recorded below because they are the terms the data was originally
released under.

### Upstream: the Ergast Developer API

Ergast stopped being updated after the 2024 season. The `ergast.com` domain no
longer serves the project and now hosts unrelated content, **so nothing in this
repository links to it.** The terms below are quoted from the Internet
Archive's copy:
<https://web.archive.org/web/2023/http://ergast.com/mrd/terms/>

> The Ergast Developer API is an experimental web service which provides a
> historical record of motor racing data for non-commercial purposes.

> You may use this API for personal, non-commercial applications and services
> including educational and research purposes. Use by websites and
> applications supported by advertising is permitted. However, you must not
> charge for any application or service which makes use of this API or for any
> data obtained from it.

> You are not required to attribute this site in applications or services
> using this API. However, an attribution would be appreciated when addressing
> a technical audience. A reference to the "Ergast API" with a link to:
> http://ergast.com/mrd is ideal.

Ergast imposed no share-alike condition and did not require attribution. It did
prohibit charging. Note that it permitted advertising-supported sites — the
stricter rule for this project comes from Jolpica, below.

---

## Jolpica F1 API

- <https://github.com/jolpica/jolpica-f1>
- Code: **Apache-2.0**
- Data: **CC BY-NC-SA 4.0** —
  <https://creativecommons.org/licenses/by-nc-sa/4.0/>
- Terms: <https://github.com/jolpica/jolpica-f1/blob/main/TERMS.md>

Everything from the 2025 season onward reaches this project through Jolpica,
and CC BY-NC-SA 4.0 carries three conditions:

- **BY** — attribution to the source.
- **NC** — no commercial use. Unlike Ergast, this does not carve out
  advertising-supported sites, so the stricter reading governs: no advertising,
  no paid tier, no sponsorship, no data resale.
- **SA** — adaptations must be shared under the same licence.

Because the current season cannot be separated from the historical record in
`data/processed/`, these terms govern the combined dataset, not just the rows
that came from Jolpica.

---

## FastF1 and the underlying Formula 1 timing data

This is the one source where the library's licence and the data's terms are
very different, and the difference matters.

### The library

- Philipp Schäfer and contributors — <https://github.com/theOehrly/Fast-F1>
- **MIT** — <https://github.com/theOehrly/Fast-F1/blob/master/LICENSE>
- Copyright (c) 2026 Philipp Schäfer

The MIT licence covers FastF1's source code. It says nothing about the data the
library retrieves, and it cannot: the FastF1 authors do not own that data.

### The data

FastF1 reads from Formula One's own live timing service. In the installed
package, `fastf1/_api.py` sets `base_url = 'https://livetiming.formula1.com'`
and `fastf1/livetiming/client.py` connects to
`wss://livetiming.formula1.com/signalrcore`. There is no separate licence
attached to that endpoint, so the terms that apply are Formula 1's own.

From the Formula 1 Legal Notices —
<https://www.formula1.com/en/information/legal-notices.7egvZU48hzrypubGBNcQKt>:

> The material and content provided on the Site is for your personal,
> non-commercial use only, save where expressly provided.

> All materials on this Site … are protected by copyrights, database rights,
> trademarks and/or other intellectual property rights owned, or used with
> permission.

> All results, timing data and certain other content are copyright Formula One
> World Championship Limited.

The protected material is enumerated, and it names the thing FastF1 retrieves:

> live timing data, historical race data, photographs, other images,
> illustrations, text, video clips and written and other materials contained in
> this Site

And the prohibition:

> you must not modify, copy, reproduce, republish, upload, frame, post,
> transmit or distribute by any means or in any manner, any material or
> information on or downloaded from the Site

…without prior written consent, which is requested from `admin@formula1.com`.

FastF1's own documentation adds only the trademark disclaimer, which this
project reproduces in the footer of every page:

> FastF1 and this website are unofficial and are not associated in any way with
> the Formula 1 companies. F1, FORMULA ONE, FORMULA 1, FIA FORMULA ONE WORLD
> CHAMPIONSHIP, GRAND PRIX and related marks are trade marks of Formula One
> Licensing B.V.

### What that allows, and what it does not

**Allowed.** Retrieving the data and analysing it locally, for personal and
non-commercial purposes. Fitting a model on it. Discussing what it shows.

**Not allowed.** Republishing it. Lap times, sector times, telemetry channels,
weather readings and race control messages may not be served from this site,
committed to this repository, included in a public dataset, or handed to
anybody else. That covers the raw feed and any file that reproduces it,
including a reformatted or filtered CSV.

Accordingly, `data/raw/fastf1/` and `data/enriched/` are both gitignored and
neither has ever been committed. Anyone rebuilding this project fetches that
data themselves, under their own acceptance of Formula 1's terms.

**Unclear, and treated as restricted.** Whether a model output — a win
probability — counts as a reproduction of the timing data it was fitted on.
A probability is not a lap time, and in some jurisdictions facts are not
copyrightable at all; but Formula 1 is a UK company, the UK and EU recognise a
separate database right over substantial extraction, and the terms above are
contractual as well as copyright-based. This project does not treat the
distinction as settled. The practical rule it follows:

- Publish model outputs — probabilities, expected positions, factor labels.
- Never publish the underlying timing values, and never publish a factor that
  amounts to a timing value with a new name (a "gap to pole" expressed in
  seconds is a timing value; "gap to pole" as a normalised weight is not).
- If the project ever becomes commercial, or wants to display session timing
  directly, get written consent from `admin@formula1.com` first.

This is a description of what the documents say and how this project reads
them. It is not legal advice.

---

## f1-circuits

- Tomislav Bacinger — <https://github.com/bacinger/f1-circuits>
- **MIT** — <https://github.com/bacinger/f1-circuits/blob/master/LICENSE>
- Copyright (c) 2019–2025 Tomislav Bacinger

Circuit geometry, projected to the SVG outlines on each race page.

## Typefaces

- Inter, Rasmus Andersson — <https://rsms.me/inter/>
- **SIL Open Font License 1.1** — <https://openfontlicense.org/>

Self-hosted and redistributed with the site, which the OFL permits.

---

## Scope of share-alike

CC BY-NC-SA's share-alike condition attaches to adaptations of the licensed
material. This project's position on where that line falls:

**Share-alike applies to** the data and to outputs derived from it — the
processed CSVs under `data/processed/`, the enriched tables, the published
prediction files, and any dataset assembled from them.

**Share-alike does not apply to** the code in `src/` and `web/`, which is
independently authored, licensed MIT, and does not incorporate the data. Code
that reads a licensed file is not an adaptation of it.

This is the standard reading of the licence, and it is the reading this project
operates on. It has not been tested in court.

---

## Attribution this project must display

Currently carried in the footer of every page and on `/credits/`:

- Formula One trademark notice (footer, every page).
- Jolpica F1 API, CC BY-NC-SA 4.0, with a link to the licence.
- f1-circuits by Tomislav Bacinger, MIT, beside every circuit outline.
- Kaggle F1 export by Rohan Rao, CC0.
- FastF1, MIT.

If FastF1-derived figures ever appear on a page, the Formula One copyright
notice for results and timing data has to appear with them — and per the
section above, that should not happen without written consent.
