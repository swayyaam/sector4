# Phase 2, Part A — FastF1 enrichment

What was pulled, how far it agrees with the data we already trust, and every
place it does not. Numbers in this document were produced by
`src/crossvalidate_ff1.py` and the scripts named alongside each section; none
of them are estimates.

Verified against the dataset as of 22 September 2026.

---

## 1. Scope

FastF1 session data for every race from 2018 onward, driven off our own
`races.csv` rather than FastF1's schedule, so every row is keyed to an existing
`raceId` by construction.

| Season | Races | Sessions | Lap rows | Results | Weather | Race control |
|---:|---:|---:|---:|---:|---:|---:|
| 2018 | 21 | 104 | 57,075 | 2,080 | 9,608 | 3,529 |
| 2019 | 21 | 104 | 58,946 | 2,080 | 10,535 | 3,676 |
| 2020 | 17 | 80 | 46,500 | 1,603 | 8,685 | 3,337 |
| 2021 | 22 | 109 | 60,294 | 2,180 | 10,536 | 4,992 |
| 2022 | 22 | 110 | 59,565 | 2,200 | 11,285 | 4,654 |
| 2023 | 22 | 110 | 58,965 | 2,200 | 11,038 | 4,781 |
| 2024 | 24 | 120 | 64,041 | 2,397 | 11,502 | 4,885 |
| 2025 | 24 | 120 | 65,652 | 2,399 | 12,028 | 6,030 |
| 2026 | 14 | 70 | 41,158 | 1,540 | 6,819 | 6,197 |
| **Total** | **187** | **927** | **512,196** | **18,679** | **92,036** | **42,081** |

The initial pull ran 24.4 hours; a follow-up run of 33 minutes recovered three
sessions that had failed transiently (§4). Nothing in `data/enriched/` or
`data/raw/fastf1/` is committed; see §6.

A normal weekend is five sessions. Eight rounds needed explaining, and after
the follow-up run only one of them is a defect:

| Season | Round | Sessions held | Why |
|---:|---|---:|---|
| 2020 | Emilia Romagna GP | 3 | Two-day format by design: one 90-minute practice, then qualifying ([formula1.com](https://www.formula1.com/en/latest/article/how-will-the-two-day-format-for-the-emilia-romagna-gp-at-imola-be-different.3ylvzKLbeYW0Yq6rmqpXX3)) |
| 2019 | Japanese GP | 4 | FP3 cancelled |
| 2020 | Styrian GP | 4 | FP3 cancelled |
| 2020 | Eifel GP | 3 | FP1 and FP2 cancelled |
| 2021 | Russian GP | 4 | FP3 cancelled |
| 2021 | United States GP | 5 | Transient failure on the first pull, recovered |
| 2022 | Canadian GP | 5 | Transient failure on the first pull, recovered |
| 2018 | Italian GP | 4 | **Race missing** — §4 |

Everything in that list except the last row is either the schedule as it
actually ran or has been recovered. §4 has the detail.

---

## 2. Cross-validation against our own tables

FastF1 reads the official F1 timing feed. Our lap times and results come from
the Ergast schema by way of the Kaggle export and Jolpica. The two are
genuinely independent, so agreement is evidence rather than tautology.

### Race lap times

186 overlapping races, matched on `(raceId, driverId, lap)`. Rows where either
side has no time are counted as absence, not as agreement — folding them into a
match rate would overstate it.

| | Rows | Share |
|---|---:|---:|
| Comparable (a time on both sides) | 201,218 | |
| Exact match to the millisecond | 200,125 | **99.457%** |
| Within 100 ms | 200,280 | 99.534% |
| Differing by more than 100 ms | 938 | 0.466% |
| No time in FastF1 | 3,105 | |
| No time in ours | 0 | |
| Present only in FastF1 | 414 | |
| Present only in ours | 80 | |

**The disagreement is two races.** Excluding the 2020 Austrian and 2018 Bahrain
Grands Prix, 8 laps differ out of 199,185 — a 0.004% disagreement rate.

| Race | Laps compared | Differing | Share |
|---|---:|---:|---:|
| 2020 Austrian Grand Prix | 1,043 | 788 | 75.6% |
| 2018 Bahrain Grand Prix | 990 | 142 | 14.3% |
| 2023 Italian Grand Prix | 948 | 7 | 0.7% |
| 2021 Styrian Grand Prix | 1,294 | 1 | 0.1% |
| Everything else (182 races) | 196,923 | 0 | **0%** |

It is not a lap-numbering offset. Shifting FastF1's lap numbers by ±1 makes
agreement worse in both races, not better (2020 Austria: 15.5% exact at zero
shift, 0.2% at +1, 0.0% at −1).

Nor is it a safety-car artefact in any simple sense. Across all seasons, laps
run under a flag disagree at 1.432% against 0.349% under green, and laps FastF1
itself marks inaccurate disagree at 1.321% against 0.340% — real signals, but
four-fold on a 0.3% base, nowhere near enough to explain 75% of a race.

What the two feeds do agree on is the total. Summing only the laps both sides
time, for the race winner:

| Race | Ours | FastF1 | Delta |
|---|---:|---:|---:|
| 2020 Austrian | 5,181,424 ms | 5,177,893 ms | −3,531 ms |
| 2018 Bahrain | 5,424,907 ms | 5,425,761 ms | +854 ms |
| 2022 Bahrain (control) | 5,538,374 ms | 5,538,374 ms | 0 |
| 2019 British (control) | 4,698,823 ms | 4,698,823 ms | 0 |
| 2023 Italian (control) | 4,421,143 ms | 4,421,143 ms | 0 |

So in both problem races the race distance is very nearly right while the
individual laps are not: time is being attributed across lap boundaries
differently, and the errors largely cancel. In 2020 Austria the per-lap
disagreement is severe — median 1.3 s, 75th percentile 27 s, 90th 42 s, maximum
69 s. In 2018 Bahrain it is mild, 82% of differing laps under a second, with a
tail to 29 s.

Our side reconstructs the official classified race time exactly in **184 of
the 187** races from 2018 onward. That is not independent proof — Ergast-derived
lap times are built to do this — but it is consistent, and FastF1 is not. The
three exceptions are each a known mechanism rather than an error:

| Race | Official | Sum of laps | Delta | Mechanism |
|---|---:|---:|---:|---|
| 2020 Bahrain GP | 10,787,515 ms | 7,187,515 ms | −3,600,000 ms | Exactly one hour: the red-flag suspension is inside the classified time and outside the laps |
| 2022 Japanese GP | 10,904,004 ms | 3,704,004 ms | −7,200,000 ms | Exactly two hours, same mechanism |
| 2022 Singapore GP | 7,340,238 ms | 7,335,238 ms | −5,000 ms | Exactly the five-second post-race penalty applied to the winner ([FIA / Article 55.10](https://www.racefans.net/2022/10/02/perez-keeps-singapore-grand-prix-win-despite-penalty-for-safety-car-violation/)) |

Round hours and a round penalty, not drift. Any feature that reconstructs race
duration by summing laps has to handle suspensions and post-race penalties
separately.

> **Use.** Treat the 2020 Austrian and 2018 Bahrain Grands Prix as unreliable
> for any lap-level feature derived from FastF1 timing. Race-level aggregates
> are usable in both. The cause is unexplained and has deliberately not been
> guessed at.

The differing rows are written to
`data/enriched/crossvalidation/lap_time_mismatches.csv`.

### Finishing positions

3,239 comparable rows. **Complete agreement — zero disagreements.** Our
`positionOrder` matches FastF1's `ClassifiedPosition` in every race from 2018
onward.

### Grid positions

3,743 comparable rows. 3,718 agree. The remaining 25 are all rows where our
`grid` is 0, which is this project's encoding for a pit-lane start, against
FastF1 reporting the grid slot the driver was classified into. That is a
convention difference established in Phase 1, not a conflict, and it is
reported separately rather than counted as a mismatch. **Zero genuine
disagreements.**

---

## 3. The 362 unmapped rows

Every FastF1 driver-session row that could not be joined to one of our
`driverId`s is written to `data/enriched/unmapped/<year>.csv` rather than
dropped. All 362 are accounted for below, and all 362 come from practice
sessions — 351 from FP1, 9 from FP2, 2 from FP3. No race, qualifying or sprint
row is unmapped in any season.

| Category | Rows | What it is |
|---|---:|---|
| `unmapped_team` | 193 | FastF1 supplied no usable `TeamId` for the entry |
| `practice_participant` | 163 | No `DriverId` and a car number unknown for that season |
| `number_mismatch` | 6 | The car-number fallback landed on a different surname and was refused |
| **Total** | **362** | |

Most participants produce two rows — one for the missing team and one for the
missing driver. 167 `(raceId, session, number)` combinations appear twice and
28 appear once, which is 362 exactly.

### `practice_participant` — 163 rows, 74 people

These are reserve and young drivers in FP1 outings. They are deliberately given
no `driverId`: the drivers table stays race drivers only, matching Ergast.
They get their own identity in `data/enriched/practice_participants.csv`, keyed
on season plus normalised name, with appearances in
`practice_participant_appearances.csv`.

| Season | Participants | Sessions |
|---:|---:|---:|
| 2018 | 6 | 23 |
| 2019 | 2 | 7 |
| 2020 | 5 | 12 |
| 2021 | 4 | 7 |
| 2022 | 12 | 23 |
| 2023 | 10 | 17 |
| 2024 | 10 | 15 |
| 2025 | 15 | 35 |
| 2026 | 10 | 24 |
| **Total** | **74** | **163** |

162 of the 163 appearances have a team resolved through the reviewed
`(FastF1 team name → constructor ref)` map. One does not, and is listed in
`practice_participants_unresolved.csv`: car 46 in FP1 at the 2026 race 1175,
where FastF1 supplied no team and the official classification does not list the
car.

`driverId` was filled for **none** of them. The rule is narrow on purpose — it
fills only where a participant's car number *and* name both match a driver who
actually raced that season, i.e. where FastF1 simply failed to supply a ref for
a regular driver. Lando Norris's seven 2018 FP1 outings are the instructive
case: he is in our drivers table, but he did not race in 2018, so the rule
correctly declines to fill him in rather than inventing a race entry.

### `unmapped_team` — 193 rows

FastF1 returns no `TeamId` for the entry, so there is nothing to join to our
constructors table. 184 are FP1, 7 FP2, 2 FP3. These overlap heavily with the
practice participants above; the team is recovered for them through the
reviewed map, and the row is kept in the unmapped file as the audit trail of
why the automatic join failed.

### `number_mismatch` — 6 rows

The car-number fallback exists because Sprint Qualifying supplies no
`DriverId`. It is guarded: if the number resolves to a driver whose surname
does not match the name FastF1 reports, the match is refused. It fired six
times, and every one is a genuine ambiguity rather than a false alarm.

| Season | Race | Session | Car | FastF1 name | Our driver for that number |
|---:|---:|---|---:|---|---|
| 2020 | 1034 | Practice 1 | 27 | *(none supplied)* | Hülkenberg |
| 2020 | 1034 | Practice 2 | 27 | *(none supplied)* | Hülkenberg |
| 2022 | 1093 | Practice 1 | 45 | Logan Sargeant | de Vries |
| 2022 | 1094 | Practice 1 | 45 | Logan Sargeant | de Vries |
| 2022 | 1095 | Practice 2 | 45 | Logan Sargeant | de Vries |
| 2022 | 1096 | Practice 1 | 45 | Logan Sargeant | de Vries |

Car 45 was used by two different people in 2022, which is exactly the case the
guard exists for. The 2020 rows are FastF1 supplying no name at all, where
accepting the number alone would have been a guess.

---

## 4. Gaps

Nine sessions failed on the first pull (1.0%). Investigating each rather than
counting them together turns out to matter: they are three different things,
and only one is a real loss. After the follow-up run, **six remain missing and
five of those six are sessions that never took place.**

| Season | Race | Session | Status |
|---:|---|---|---|
| 2019 | Japanese GP | Practice 3 | Never ran — Typhoon Hagibis |
| 2020 | Eifel GP | Practice 1 | Never ran — fog |
| 2020 | Eifel GP | Practice 2 | Never ran — fog |
| 2020 | Styrian GP | Practice 3 | Never ran — torrential rain |
| 2021 | Russian GP | Practice 3 | Never ran — heavy rain |
| 2021 | United States GP | Practice 3 | Transient, recovered on re-fetch |
| 2021 | United States GP | Qualifying | Transient, recovered on re-fetch |
| 2022 | Canadian GP | Practice 2 | Transient, recovered on re-fetch |
| 2018 | Italian GP | **Race** | **Permanently unavailable** — see below |

### Five sessions that never happened

These are not gaps in the data. The sessions were cancelled or abandoned, so
there is nothing to fetch, and the absence is correct:

- **2019 Japanese GP, FP3** — all Saturday track activity cancelled as Typhoon
  Hagibis approached Suzuka; qualifying moved to Sunday morning
  ([FIA statement](https://www.fia.com/news/2019-fia-formula-1-japanese-grand-prix-updated-statement-typhoon-hagibis),
  [formula1.com](https://www.formula1.com/en/latest/article/saturday-running-cancelled-in-japan-full-revised-timetable-for-sunday.7bCNvGLXjco9zJUIEKgtvu)).
- **2020 Eifel GP, FP1 and FP2** — both cancelled; low cloud and rain around the
  Nürburgring stopped the medical helicopter flying, which regulations require
  ([Autosport](https://www.autosport.com/f1/news/152657/eifel-gp-first-practice-cancelled-due-to-rain-and-fog),
  [Autosport](https://www.autosport.com/f1/news/152666/second-eifel-gp-practice-session-called-off-amid-fog)).
- **2020 Styrian GP, FP3** — washed out by torrential rain at the Red Bull Ring,
  called off 40 minutes in
  ([Autosport](https://autosport.com/f1/news/150491/styrian-gp-fp3-cancelled-due-to-torrential-rain)).
- **2021 Russian GP, FP3** — abandoned in heavy rain at Sochi
  ([Autosport](https://www.autosport.com/f1/news/final-f1-russian-gp-practice-cancelled-due-to-wet-weather/6674262/)).

### Three transient failures, recovered

2021 United States GP FP3 and Qualifying, and 2022 Canadian GP FP2, failed
during the original pull and loaded without complaint on a re-run. They were
network or rate-limit casualties mid-session, not missing data.

Re-fetching those two seasons recovered all three — 283, 249 and 599 lap rows
respectively — in 33 minutes and 140 requests. The re-read preserved every row
that was already present: across laps, results, weather and race control for
both seasons, **zero rows were lost and every added row belongs to one of the
three recovered sessions.**

That run also confirmed the request budget against FastF1's own tally:

```
rate budget: 140 requests this run, 140 seen by FastF1 (drift +0)
```

### 2018 Italian Grand Prix, race — permanently unavailable

The one real loss, and the only race session missing from the whole enrichment.

Retried once with the cache bypassed (`Cache.enable_cache(..., force_renew=True)`)
as agreed. It failed again, identically. The cause is not missing upstream
data — the raw payloads download fine and are in fact larger than the
neighbouring Belgian GP's — but a parse failure inside FastF1 3.8.3:

```
File "fastf1/core.py", line 1500, in _load_laps_data
File "fastf1/core.py", line 2185, in __fix_tyre_info
IndexError: list index out of range
```

`__fix_tyre_info` indexes a list of stint brackets by a stint number taken from
the data. When a driver's stint counter exceeds the number of brackets found,
the index is out of range. `_load_laps_data` dies with it, `self._laps` is never
assigned, and every later access raises `DataNotLoadedError`. One session in
924 trips it.

**What is lost:** the FastF1-specific lap fields for that race — tyre compound,
stint, tyre life, fresh-tyre flag, track status, sector times, speed traps,
personal-best and deleted-lap flags.

**What is not lost:** the race itself is fully present in `data/processed/`,
from the Kaggle Ergast export — 925 lap-time rows across 19 drivers for all 53
laps, 20 result rows, and 21 pit stops. Note that for 2018 the source is
**Kaggle, not Jolpica**: Jolpica supplies 2025 onward, and the `source` column
on every row says so. Weather, race control and results for the session loaded
normally from FastF1; only the lap table is missing.

**Why "permanently" is the wrong word, strictly.** This is a library defect at
a known line, not an upstream absence. A future FastF1 release that fixes
GH-issue-class bugs in `__fix_tyre_info` would likely recover it. Working
around it here was deliberately not attempted: the failing code is the part
that *corrects* stint attribution, so skipping it would produce lap rows with
tyre and stint fields that are quietly wrong — exactly the kind of plausible
fabrication this project's rules forbid. Recorded as unavailable at the pinned
version, and worth retrying after a FastF1 upgrade.

---

## 5. The tyre naming boundary

2018 is the only season in this dataset that uses Pirelli's absolute compound
names. From 2019 onward the relative three-name scheme applies.

| Season | HYPERSOFT | ULTRASOFT | SUPERSOFT | SOFT | MEDIUM | HARD | INTERMEDIATE | WET |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2018 | 7,817 | 13,985 | 13,551 | 14,201 | 5,160 | 117 | 947 | 256 |
| 2019 | 0 | 0 | 0 | 29,619 | 17,143 | 10,385 | 1,337 | 159 |
| 2020 | 0 | 0 | 0 | 19,073 | 13,728 | 10,446 | 1,197 | 1,088 |
| 2021 | 0 | 0 | 0 | 22,091 | 18,641 | 15,046 | 2,861 | 161 |
| 2022 | 0 | 0 | 0 | 22,863 | 18,241 | 11,429 | 3,699 | 1,315 |
| 2023 | 0 | 0 | 0 | 20,217 | 18,098 | 15,832 | 3,594 | 295 |
| 2024 | 0 | 0 | 0 | 19,444 | 22,425 | 17,353 | 3,824 | 389 |
| 2025 | 0 | 0 | 0 | 22,593 | 24,227 | 16,005 | 2,060 | 282 |
| 2026 | 0 | 0 | 0 | 15,020 | 14,732 | 11,324 | 48 | 0 |

35,353 lap rows in 2018 carry a name that does not exist in any later season.

> **The trap.** A 2018 `SOFT` and a 2019 `SOFT` are not the same rubber. In 2018
> the names were absolute and described a fixed ladder; from 2019 Pirelli
> allocated three compounds from the C1–C5 range per event and relabelled them
> HARD, MEDIUM and SOFT for that weekend. So `SOFT` after 2018 is a *relative*
> position within that weekend's allocation, and the same label covers
> different physical compounds from race to race.

Compound names are stored **exactly as reported**, with no mapping applied.
Translating between the schemes requires each race's Pirelli allocation, which
is a modelling decision with its own evidence requirements, not something to
guess at load time. Any feature that treats compound as a category must either
restrict itself to 2019 onward or carry the season as part of the key.

Small residue worth knowing about: a handful of rows per season carry `TEST`,
`TEST_UNKNOWN`, `UNKNOWN`, `None` or an empty compound. They are left as
reported rather than coerced.

---

## 6. What this data may be used for

FastF1's MIT licence covers the library, not the data it retrieves. The library
reads from `livetiming.formula1.com`, and Formula 1's legal notices name "live
timing data, historical race data" as protected material, state that "All
results, timing data and certain other content are copyright Formula One World
Championship Limited", and prohibit republishing it "by any means or in any
manner" without prior written consent.

The practical consequence for this project, set out in full in
[`DATA_LICENSE.md`](DATA_LICENSE.md):

- **Allowed.** Retrieving this data and analysing it locally. Fitting a model
  on it. Everything Part B onward needs.
- **Not allowed.** Publishing it. No lap time, sector time, tyre field, speed
  trap, weather reading or race control message from this source may be served
  from the site, committed to this repository, or handed to anyone else — not
  raw, and not as a reformatted CSV.

`data/raw/fastf1/` and `data/enriched/` are both gitignored and neither has
ever been committed. Anyone rebuilding this project fetches the data
themselves, under their own acceptance of those terms.

Model outputs — probabilities, expected positions, factor labels — are
publishable. A factor that is a timing value under a new name is not.

---

## 7. Reproducing this

```
python src/fetch_fastf1.py                       # full pull, 2026 back to 2018
python src/fetch_fastf1.py --seasons 2021 2022   # one or more seasons
python src/practice_participants.py              # resolve reserve identities
python src/crossvalidate_ff1.py                  # the comparisons in §2
```

The fetcher is resumable and paces itself against FastF1's hourly cap, which it
never trips: `RateBudget` attaches to FastF1's transport and claims a slot
before each request goes out, counting at the same point the cap counts. A
season already in the manifest is still re-read, because each season CSV is
rewritten whole and skipping a cached session would silently drop its rows.
Cache reads cost about two requests per session, so a re-run of a finished
season is cheap.

Cross-validation writes its disagreements to
`data/enriched/crossvalidation/` — `lap_time_mismatches.csv`,
`position_mismatches.csv` and `grid_mismatches.csv`. The last two are currently
empty, which is the point.

---

## 8. Summary

| | |
|---|---|
| Sessions pulled | 927 across 187 races, 2018–2026 |
| Lap rows | 512,196 |
| Lap times agreeing with our tables | 99.457% exact; 8 laps differ in 199,185 outside two races |
| Finishing positions | 3,239 of 3,239 agree |
| Grid positions | 3,743 of 3,743 agree, 25 pit-lane convention differences reported separately |
| Unmapped rows | 362, all practice, all categorised |
| Sessions missing | 1 race (2018 Italian), 5 that never ran |
| Seasons needing care | 2018 tyre names; 2020 Austria and 2018 Bahrain lap times |

Two things are unexplained and are recorded as such rather than smoothed over:
the lap-time disagreement in the 2020 Austrian and 2018 Bahrain Grands Prix,
and the single doubled lap in the 2021 Styrian Grand Prix (FastF1 reports
142,514 ms against our 71,308 ms for one driver on lap 4 — almost exactly two
laps merged into one).
