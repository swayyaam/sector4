# Phase 2, Parts C and D — modelling

What was tried, what it scored, and what that means. Every number here comes
from a walk-forward run: to predict a race the model is fitted on races
strictly before it and on nothing else, the same discipline the baselines
follow, so the comparison is fair.

Reproduce with `src/baselines.py`, `src/model.py`, `src/diagnose.py` and
`src/finalists.py`. Verified 23 September 2026.

---

> **Read §6 before quoting any margin from this document.** Every comparison in
> §§1–5 was made by reading an evaluation window that included 2026. That is
> selection on the test set. On a clean 2026 holdout the chosen model does
> **not** beat the baseline, and the site does not claim that it does.

## The finding

**Qualifying position is close to a sufficient statistic for this problem, and
almost everything else is variance.**

A model with four features beats the qualifying-order baseline. A model with
thirty-three does not. The ordering on the primary window is exact and goes the
wrong way for anyone hoping a richer feature set helps:

| Features | Log loss, last 50 races |
|---:|---:|
| 4 | **1.1864** |
| 19 | 1.2017 |
| 22 | 1.2370 |
| 33 | 1.2480 |
| *baseline (qualifying order)* | *1.3235* |

The value a model adds here is **the probability, not the ordering**. The
baseline calls more winners than most of the models; what the model does better
is say how likely each one was, which is what the site publishes.

That last sentence is the whole claim. On a clean 2026 holdout the model does
not beat the baseline on log loss either (§6); what survives out of sample is
the calibration, not the margin.

---

## 1. Baselines

166 races, 2019 onward, walk-forward. Positional priors are re-estimated at
every race rather than fitted once, which would let a 2019 prediction learn
from 2024.

| Baseline | Log loss | Brier | Winner | Podium |
|---|---:|---:|---:|---:|
| Uniform | 2.9964 | 0.950 | 5.0% | 15.0% |
| Elo | 2.0256 | 0.794 | 39.8% | 51.6% |
| Grid order | 1.5112 | 0.660 | 54.2% | 68.9% |
| **Qualifying order** | **1.4340** | 0.637 | 56.0% | 67.5% |

Elo is weak, and that is informative: a rating that sees only the driver cannot
see the car, and in this sport the car is most of the answer. Qualifying order
beats grid order because grid encodes penalties, which move a car without
saying anything about its pace.

### The scorer bug the uniform baseline caught

Uniform reported a **99.4% winner hit rate**. The field arrives from a results
table sorted by finishing position, so an argmax that falls back on row order
hands a tied predictor the winner every time. Sorting by driverId instead gave
19.9% — still wrong, because the lowest driverId in this era is Hamilton, who
won a fifth of these races.

Ties are now resolved by expectation, since any deterministic rule correlates
with something. Uniform scores exactly 1/N and 3/N, which is arithmetic rather
than judgement, and both failures have regression tests that run in CI.

---

## 2. First pass: three model families

| Model | Log loss (95% CI) | Winner | ECE (win) | vs bar |
|---|---|---:|---:|---|
| Logistic, 33 linear | 1.3765 [1.2186, 1.5495] | 51.2% | 0.0049 | indistinguishable |
| LightGBM, 33 | 1.5532 [1.2787, 1.8338] | 51.2% | 0.0254 | indistinguishable |
| Ranker + Monte Carlo | 2.1697 [1.8191, 2.5608] | 45.2% | 0.0168 | loses |

None beat the bar. That result stood until the diagnostics explained why, and
it turned out to be about functional form rather than about the features.

### The ranker bug

The ranking model first scored **7.5745** — five times worse than a uniform
guess. It was assigning p_win = 1.000 to one driver in most races and giving
the actual winner **exactly zero in 55 of 166**.

The Plackett-Luce temperature was being fitted on the same races the ranker had
trained on. A ranker puts the winner first on its own training data almost
every time, so the in-sample likelihood is maximised by collapsing to a point
mass, and it did.

Every discrimination metric looked healthy throughout: the winner hit rate was
52.4%, alongside the other models. Only the probabilities showed it. That is
the argument for reporting calibration rather than log loss alone, and it is
why calibration appears beside every number in this document.

Fixed with a 25-race holdout for the temperature and Laplace-smoothed Monte
Carlo counts — ten thousand draws cannot represent anything below one in ten
thousand, and a simulated zero for a driver who then wins is an infinite
penalty rather than a confident miss.

---

## 3. Diagnostics

### Incremental feature groups

| Step | Cols | Log loss | Change |
|---|---:|---:|---:|
| quali_position alone | 1 | 1.5006 | — |
| + quali gaps | 4 | 1.5080 | +0.007 |
| + practice | 8 | 1.4463 | −0.062 |
| **+ form** | 22 | **1.3286** | **−0.118** |
| + circuit | 31 | 1.3480 | +0.019 |
| + tyre | 33 | 1.3765 | +0.029 |

The features are not inert — form is worth −0.118, the largest single move.
But circuit and tyre features **actively hurt**, and the thirty-three-column
model is worse than a twenty-two-column subset.

### The shape of qualifying position — the thing that mattered

| Variant | Log loss | vs bar |
|---|---:|---|
| **Spline, quali_position alone** | **1.4103** | **−0.0236 [−0.0466, −0.0013] — beats the bar** |
| Linear, quali_position alone | 1.5006 | +0.0666 [+0.0082, +0.1205] — loses |
| One-hot, quali_position alone | 1.4880 | +0.0541 — loses |
| Spline + all 33 | 1.3194 | −0.1145 — indistinguishable |

The same single feature goes from significantly **worse** than the baseline to
significantly **better**, purely by changing its functional form. P1 to P2 is
not P15 to P16, and a slope cannot express that. This was worth more than any
feature added in Part B.

One-hot is worse than a spline at both sizes: twenty indicators is too many
parameters for this much data.

### LightGBM was memorising

| Model | Train | Test | Gap |
|---|---:|---:|---:|
| As reported | 0.0069 | 0.2155 | 0.2086 |
| Heavily regularised | 0.1119 | 0.1376 | 0.0256 |

Per-row log loss on the win target. The reported model had essentially
memorised its training set.

### Coefficients — four of thirty-three differ from zero

| Feature | β | z |
|---|---:|---:|
| quali_position | −3.210 | −7.65 |
| driver_standing_points | +1.436 | +3.79 |
| team_standing_points | −0.995 | −2.45 |
| practice_best_lap_gap_ms | −0.672 | −2.28 |

By group: Qualifying 1/4, Driver form 1/6, Team form 1/5, Practice 1/4, and
**zero significant** in Context (0/5), Circuit history (0/4), Relative form
(0/3) and Tyre (0/2).

`team_standing_points` carries a negative sign beside the driver's positive
one. The pair is collinear and is effectively computing the driver's share of
the team's points.

### Sample size

| Fold | Training rows | Races | Wins available |
|---|---:|---:|---:|
| First eval race | **420** | 21 | **21** |
| 50th | 1,394 | 70 | 70 |
| 117th | 2,726 | 137 | 137 |
| Last | 3,715 | 186 | 186 |

The first fold fits thirty-three features on 420 rows containing twenty-one
wins. A meaningful share of the 166-race average was measuring a model that had
barely learned anything — which is why the last fifty races are the primary
window from here on.

---

## 4. Finalists — last 50 races, the window the site predicts into

| Model | Log loss | 95% CI | vs bar | Verdict |
|---|---:|---|---|---|
| **Minimal 4** | **1.1864** | [0.9696, 1.4299] | −0.1370 [−0.2730, −0.0261] | **beats the bar** |
| Spline + 19 | 1.2017 | [0.9853, 1.4342] | −0.1217 [−0.3057, +0.0625] | indistinguishable |
| **Minimal 4, share variant** | 1.2052 | [0.9879, 1.4475] | −0.1183 [−0.2492, −0.0113] | **beats the bar** |
| Spline + 22 | 1.2370 | [1.0212, 1.4656] | −0.0865 | indistinguishable |
| Spline + 33 | 1.2480 | [1.0325, 1.4901] | −0.0755 | indistinguishable |
| *Baseline* | *1.3235* | [1.0480, 1.6332] | — | — |
| LightGBM regularised | 1.4098 | [1.2437, 1.5861] | +0.0863 | indistinguishable |

Across all 166 races the same ordering holds and the margins widen: minimal 4
at 1.2790, −0.1549 [−0.2272, −0.0898], and spline + 19 at 1.2370, −0.1969
[−0.3076, −0.0856]. Regularised LightGBM **loses to the bar** over the full
window, +0.1323 [+0.0050, +0.2529].

**Minimal 4** is `spline(quali_position)` plus `practice_best_lap_gap_ms`,
`driver_standing_points` and `team_standing_points` — the four coefficients
that differed from zero, and nothing else.

### Calibration, last 50 races

| Model | ECE (win) | ECE (podium) |
|---|---:|---:|
| Minimal 4, share variant | **0.0095** | 0.0253 |
| Minimal 4 | 0.0099 | 0.0231 |
| Spline + 33 | 0.0120 | 0.0221 |
| Spline + 19 | 0.0188 | **0.0153** |
| LightGBM regularised | 0.0214 | 0.0352 |

The small models are better calibrated as well as better discriminating. There
is no trade-off to argue about here.

### Two questions the finalists settle

**Relative form is out.** Spline + 19, which drops it, beats spline + 22, which
keeps it, on both windows. That answers the question raised when those two
features were added at a mutual correlation of −0.639.

**The direct points share is a wash.** Replacing the collinear
`team_standing_points` with `driver_vs_team_points_share_5` costs 0.019 in log
loss and gains 0.0004 in calibration error. Both beat the bar. The collinear
pair is kept because it scores marginally better, not because it is tidier.

---

## 5. Ablation: reserve drivers in practice pace

Reserve and FP1-only runners are excluded from practice pace by default. The
ablation flips that and changes **nothing at all** — the same log loss to four
decimal places on both windows.

The reason is worth recording, because the rule looks load-bearing and is not:

- 4,346 reserve practice laps exist. **3,725 of them carry no `driverId`**, so
  the join already drops them whatever the flag says.
- Of the 621 that do carry one, spread over 20 races, **no reserve ever set the
  reference lap** in any of those races.

`practice_best_lap_gap_ms` is a gap to the field's best lap, and reserves are
never the fastest, so the field minimum does not move. The exclusion rule is
currently redundant. It would start to matter for a team-aggregated pace
feature, which does not exist yet — so the rule stays, as a guard against a
feature that has not been written rather than as something that does work now.

---

---

## 6. The 2026 holdout, and what it costs the headline

Everything above chose between models by reading an evaluation window that
included 2026. The spline, the feature subsets and the minimal four were all
picked that way, so the margins in §4 are optimistic by an unknown amount.
This section is the correction.

The procedure was fixed before looking: re-run the selection with 2026 removed,
freeze one specification, score it on 2026 once. No tuning afterwards.

### Step 1 — the selection is contaminated

Redone on 2019–2025 alone, the answer changes.

**Only three coefficients are significant, not four.** `team_standing_points`
(z = −2.45 with 2026 included) drops out. The other three hold:
`quali_position` z = −7.31, `driver_standing_points` z = +3.22,
`practice_best_lap_gap_ms` z = −2.25.

And the finalist ranking flips (152 races, baseline 1.4572):

| Model | Log loss | vs bar |
|---|---:|---|
| **Spline + 19** | **1.2489** | −0.2083, significant |
| Spline + 22 | 1.2884 | −0.1688, significant |
| Minimal 4 | 1.2993 | −0.1579, significant |
| Minimal 4, share | 1.3069 | −0.1503, significant |
| Spline + 33 | 1.3331 | −0.1241, not significant |
| *Baseline* | *1.4572* | — |

**An uncontaminated selection would have chosen spline + 19, not minimal 4.**
The "fewer features win" ordering in §4 was partly an artefact of including
2026 in the comparison.

### Step 2 — the holdout, scored once

14 races. The frozen primary is the share variant, chosen for explainability.

| Model | Log loss | 95% CI | vs bar | Verdict | ECE (win) |
|---|---:|---|---|---|---:|
| **Minimal 4 (share) — primary** | 1.0901 | [0.7052, 1.5576] | −0.0917 [−0.3078, +0.1179] | **indistinguishable** | 0.0188 |
| Minimal 4 (team points) | 1.0594 | [0.6900, 1.5069] | −0.1223 [−0.3323, +0.0678] | indistinguishable | 0.0146 |
| *Baseline: qualifying order* | *1.1817* | [0.8076, 1.7592] | — | — | — |

**The model does not beat the baseline out of sample.** The point estimate
favours it by 0.09 in log loss, and the interval comfortably contains zero.

Two caveats that cut in both directions. 2026 is a **regulation reset**, so
prior seasons are weaker evidence about it than usual — which handicaps the
model more than the baseline, since the baseline only needs the grid to keep
meaning what it meant. And **fourteen races is very little**: the baseline's own
interval spans 0.81 to 1.76, so almost nothing could have been resolved here.

### What is not being done

Spline + 19 is the model an honest selection would have picked, and it has
**not** been scored on 2026. Its predictions exist, but looking at them now —
after seeing that minimal 4 failed to clear the bar — would repeat exactly the
error this section exists to correct. It stays unevaluated until there is a
fresh holdout, which means 2027.

### What the site may say

- It **may** say the model is well calibrated, and show the reliability table.
- It **may** publish the margin over the baseline on 2019–2025 as an in-sample
  figure, labelled as one.
- It **may not** claim to beat qualifying order. There is no out-of-sample
  evidence for that claim.

## 7. What to ship

**`minimal 4 (share)` at the post-qualifying snapshot**: a spline on qualifying
position, practice best-lap gap, driver championship points, and the driver's
share of the team's points.

The share term replaces `team_standing_points` deliberately. The two score
within noise of each other, the direct version is explainable in one sentence
on the methodology page, and the term it replaces turned out not to be
significant once 2026 was removed from the fit — so it was the weaker of the
two on every ground that matters.

- It is well calibrated: ECE 0.0099 on p_win over the last fifty races, 0.0188
  on the holdout, the best of anything tested.
- Four inputs, so the methodology page can state exactly what the model uses
  and a race-page factor breakdown will be honest rather than decorative.
- A logistic regression, so the published coefficients *are* the model.

**It does not beat qualifying order out of sample, and the site will not say it
does.** See §6. What the model offers over the baseline is a calibrated
probability rather than an ordering — the baseline calls more winners, and only
the model says how likely each one was.

## 8. What would actually move this

Ranked by what the diagnostics suggest, not by what sounds interesting:

1. **A grid feed.** Qualifying position dominates every model, and grid
   position is strictly better information — it includes penalties. It is
   currently excluded because there is no feed that would let us serve it as
   well as train on it, which would be train/serve skew. This is the single
   highest-value addition.
2. **More seasons.** Every diagnostic points at variance rather than bias. The
   feature set is bounded at 2018 by FastF1 coverage; the non-FastF1 features
   already reach back to 1950, and a model built only on those could train on
   far more races.
3. **Weather at race time.** Named in ENRICHMENT_REPORT.md §2 as a large part
   of the residual, and genuinely absent from the inputs rather than merely
   unmodelled.
4. **Nothing involving more features of the kind already tried.** Circuit
   history, tyre and relative form were all measured, and all three made the
   model worse.

---

## 9. The pre-weekend model

Everything above selects the **post-qualifying** model. The pre-weekend
snapshot was never selected on its own. It shipped as whatever the
post-qualifying specification reduces to once qualifying and practice are
removed: a logistic regression on `driver_standing_points` and
`driver_vs_team_points_share_5`. This section selects it properly.

### Protocol — fixed before any result was seen

Committed on its own, before the selection script was run, so the history
shows the procedure came first.

**Data.** The pre-weekend feature frame (`F.build(..., snapshot="pre_weekend")`),
targets from `results.csv`, walk-forward exactly as in §1: every race is
predicted by a model fitted only on races strictly before it.

**Two new inputs, computed from prior races only.** Neither existing group
reads qualifying, and qualifying is the cleanest read on a car's pace that
exists before a weekend starts. Both of the new inputs use only races
strictly before the one being predicted:

- `driver_quali_pos_mean_3`: the driver's mean qualifying position over
  their last three races.
- `team_quali_pos_mean_3`: the team entity's best qualifying position at
  each of its last three races, averaged.

They are computed inside the selection script. They are added to
`src/features.py` only if a candidate that uses them is chosen to ship, so
nothing in §§1–8 changes until then.

**Candidates.** All are the same regularised logistic regression (`Slim`,
C = 0.5, median imputation, standardisation fitted per fold), with no tuning:

| Id | Inputs | Count |
|---|---|---:|
| P0 | incumbent: driver points, driver's share of team points | 2 |
| P1 | standings: driver and team standing position and points | 4 |
| P2 | P1 + the two recent-qualifying inputs | 6 |
| P3 | driver form and team form groups (§B of `features.py`) | 11 |
| P4 | P3 + the two recent-qualifying inputs | 13 |
| P5 | every pre-weekend feature + the two recent-qualifying inputs | 25 |

**Two training windows.** Rows from 2018 (the current frame) and rows from
2014, the start of the hybrid era. The second follows §8's second point: none
of these inputs needs FastF1, so more seasons are available. Both windows use
the same points system. Twelve runs in all.

**Selection window: 2019–2025 only.** The walk-forward is run on a frame
truncated at the end of 2025, so no 2026 row is ever predicted during
selection.

**The bar.** Championship order (§1, `baselines.py`), scored on exactly the
same races.

**Selection rule.**
1. Primary metric: mean race-level win log loss over 2019–2025.
2. The candidate with the lowest mean is selected. Accuracy is the brief for
   this snapshot, so there is no tie-break towards fewer inputs. The report
   states whether its margin over P0 and over the bar is significant (paired
   race bootstrap, 95%).
3. **Calibration guard:** if the selected candidate's win ECE on 2019–2025 is
   more than twice P0's, stop and report instead of freezing.

**Holdout: 2026, scored once.** The selected specification is frozen,
including window, inputs and estimator. Then it, P0 and the bar are scored on
every completed 2026 race at the time of freezing.

Two caveats are stated now, not discovered later:
- Part C printed pre-weekend scores for the three full-feature model families
  pooled over 2019–2026. No pre-weekend decision was made from them, and they
  are not opened here.
- P0's live R15 result has been seen. It lost to championship order, 2.2568
  against 1.5893.

**What the result allows.**
- Recommend shipping the selected model if its holdout log loss is no worse
  than P0's.
- Otherwise, recommend keeping P0.
- Either way, the site may say the pre-weekend model beats championship order
  only if the holdout paired interval excludes zero.
- Shipping is a separate decision, made after review.

### Selection — 2019–2025

Run with `python src/pre_weekend_selection.py select`, after the protocol and
the script were committed. There were 151 races in every run, and the bar was
scored on 152. Paired comparisons use the races both sides scored.

**Bar, championship order: 1.7920** [1.6711, 1.9234].

| Run | Inputs | Log loss | Winner | Podium | ECE (win) | vs bar | vs P0-2018 |
|---|---:|---:|---:|---:|---:|---|---|
| **P4-2018** | 13 | **1.5170** | 49.7% | 57.8% | 0.0086 | −0.2656 [−0.3699, −0.1545] | −0.4969 [−0.6168, −0.3725] |
| P4-2014 | 13 | 1.5219 | 49.0% | 58.9% | 0.0065 | −0.2607 [−0.3692, −0.1502] | −0.4920 [−0.6161, −0.3623] |
| P3-2014 | 11 | 1.5320 | 51.0% | 57.4% | 0.0087 | −0.2506 [−0.3530, −0.1424] | −0.4819 [−0.6072, −0.3531] |
| P3-2018 | 11 | 1.5339 | 51.0% | 56.7% | 0.0089 | −0.2488 [−0.3530, −0.1376] | −0.4800 [−0.6021, −0.3538] |
| P5-2014 | 25 | 1.5608 | 49.0% | 58.3% | 0.0084 | −0.2218 [−0.3442, −0.0929] | −0.4531 [−0.5913, −0.3088] |
| P5-2018 | 25 | 1.5696 | 51.0% | 57.8% | 0.0103 | −0.2131 [−0.3342, −0.0849] | −0.4443 [−0.5829, −0.3019] |
| P2-2018 | 6 | 1.5911 | 44.4% | 58.5% | 0.0062 | −0.1915 [−0.2762, −0.0984] | −0.4227 [−0.5213, −0.3173] |
| P2-2014 | 6 | 1.5994 | 43.0% | 58.3% | 0.0017 | −0.1832 [−0.2857, −0.0739] | −0.4145 [−0.5279, −0.2903] |
| P1-2014 | 4 | 1.6863 | 48.0% | 57.8% | 0.0111 | −0.0963 [−0.1686, −0.0095] | −0.3275 [−0.4454, −0.1984] |
| P1-2018 | 4 | 1.6875 | 48.0% | 56.9% | 0.0123 | −0.0951 [−0.1601, −0.0212] | −0.3263 [−0.4306, −0.2116] |
| P0-2014 | 2 | 1.9994 | 45.7% | 55.8% | 0.0105 | +0.2168 [+0.1323, +0.3027] | −0.0145 [−0.0225, −0.0063] |
| *P0-2018, incumbent* | 2 | *2.0139* | 46.4% | 53.4% | 0.0103 | +0.2312 [+0.1423, +0.3195] | — |

Every interval in the table is significant at 95%.

(P3 is the "Driver form" and "Team form" groups in `features.py`. The
protocol's "§B" was a loose reference to them.)

**The model that shipped was worse than championship order.** In sample,
over seven seasons, P0 scored 0.23 worse than the bar, and the interval
excludes zero. The live R15 result (2.2568 against 1.5893) was not bad luck;
it was this.

**What helps.**
- Form beats standings alone: P3 against P1 is −0.15.
- The two recent-qualifying inputs help wherever they are added: P1 to P2 is
  −0.10, and P3 to P4 is −0.02.
- Everything (P5) is worse than form plus qualifying (P4), the same pattern
  §4 found for the post-qualifying model.
- The extra 2014–2017 seasons make little difference. Within each input set
  the two windows are at most 0.015 apart, in both directions. Only P0's
  gap, 0.0145 in favour of 2014, is significant, and P0 is the weakest set.

**Selected and frozen: P4-2018.**
- Inputs: the six driver-form inputs, the five team-form inputs,
  `driver_quali_pos_mean_3` and `team_quali_pos_mean_3`.
- Estimator: the same `Slim` logistic regression, C = 0.5.
- Training rows: from 2018.
- Calibration guard: ECE 0.0086 against P0's 0.0103, so not tripped.

This entry was committed before the holdout was run.

### Holdout — 2026, scored once

Run with `python src/pre_weekend_selection.py holdout P4-2018`, after the
freeze was committed. It covered all 15 completed 2026 races, R1 to R15. The
script refuses a second run.

| Model | Log loss | 95% CI | vs bar | Winner | Podium | ECE (win) |
|---|---:|---|---|---:|---:|---:|
| *Bar: championship order* | *1.8007* | [1.4569, 2.2030] | — | — | — | — |
| **P4-2018 — selected** | 1.8983 | [1.4632, 2.3937] | +0.0976 [−0.1335, +0.3445], **indistinguishable** | 33.3% | 44.4% | 0.0286 |
| P0-2018 — incumbent | 2.3951 | [2.1527, 2.6400] | +0.5945 [+0.3344, +0.8491], **worse** | 40.0% | 40.0% | 0.0179 |

P4-2018 against the incumbent: **−0.4968 [−0.8309, −0.1570], better.**

**What this says.**
- **The incumbent is worse than championship order out of sample too.** On
  2026 it was 0.59 worse than the simple rule, and the interval is well clear
  of zero. The pre-weekend predictions published so far have been worse than
  ranking drivers by the standings.
- **The selected model is much better than the incumbent:** half a unit of log
  loss, significant on fifteen races.
- **It does not beat championship order on 2026.** The point estimate is 0.10
  worse, and the interval spans zero on both sides. In sample it was 0.27
  better. 2026 is a regulation reset, which hurts any model that learns from
  earlier seasons more than it hurts a rule that only reads this season's
  table. And fifteen races is very little; the bar's own interval spans 1.46
  to 2.20.
- **Calibration is weaker out of sample:** win ECE 0.0286 against 0.0086 in
  sample. On fifteen races this is noisy, but it is reported, not explained
  away.

**Under the protocol:**
- The selected model's holdout log loss (1.8983) is no worse than the
  incumbent's (2.3951), so the recommendation is to **ship P4-2018 in place of
  the incumbent.**
- The site **may not** say the pre-weekend model beats championship order.
- Shipping needs the two recent-qualifying inputs added to `src/features.py`,
  under the same cut tests as every other feature, and the site's description
  of the before-practice prediction rewritten to match. That is a separate
  change, made after review.

### Shipped — `pre-form-quali-v1`

After review, P4-2018 replaces the incumbent for pre-weekend predictions made
from 2026 round 16 onward. Predictions already published are unchanged, and
each keeps the model version that made it.

- **Inputs.** The two recent-qualifying inputs are now in `src/features.py`,
  in a group of their own, and the selection's function moved with them, so
  the shipped model computes exactly what the selection measured. They are
  tagged `added="§9"`. Everything that reproduces §§1–8 asks for
  `features_for(..., original_only=True)`, so those sections still measure the
  same 33 and 23 columns.
- **Factors.** The new model's factors come from its own fitted win
  coefficients: each input's coefficient times the driver's standardised
  value. The post-qualifying model's method assumes higher is better except
  for a named list, and about half of these thirteen inputs run the other way.
  Because the inputs overlap, the model can weigh one against another. With
  driver points held fixed, more team points means a stronger teammate, and
  that counts against the driver. The race page says so beside the factors.
- **Labels.** `driver_standing_points` had been labelled "Championship
  position" on post-qualifying factors. It is now "Championship points", and
  the new model's position input takes "Championship position".
- **Site.** Each prediction is described by the model that made it
  (`web/src/lib/models.ts`, and the build fails for an undescribed version).
  The track record says when a table covers more than one model. The
  methodology page states that the earlier pre-weekend model did worse than
  championship order.

---

## 10. The after-practice model

A third prediction, published after the last practice session that runs
before the weekend's first qualifying session. That deadline is qualifying on
a normal weekend, and sprint qualifying (or the 2021–23 Friday qualifying) on
a sprint weekend. It is scored separately and never pooled with the other
two.

### Protocol — fixed before any model was run

**Data definitions.** These were checked against the data, not against any
model result, before this was written.

- **Sessions.** Practice 1 only on a sprint weekend; Practice 1–3 otherwise.
  On every sprint weekend from 2021 to 2026, FP1 is the only practice before
  the first qualifying session: in 2021–23 Friday qualifying came straight
  after FP1, and since 2024 sprint qualifying does. The session list comes
  from the FastF1 laps. On the 2024 sprint weekends, the races table's
  `fp2_date` is sprint qualifying, so it is not used.
- **The field.** Drivers with laps in FP2 or FP3; drivers with laps in FP1 on
  a sprint weekend; FP1 also when neither FP2 nor FP3 ran. Against the actual
  starters, 2018–2026:

  | Field rule | Extra drivers | Missing starters | Races missing a starter |
  |---|---:|---:|---:|
  | **FP2/FP3 (FP1 on sprint weekends)** | 28 | 2 | 2 of 187 |
  | Previous race's starters (the pre-weekend rule) | 75 | 77 | 46 of 187 |
  | Previous starters, swapped by practice | 48 | 22 | 19 of 187 |

  Extra drivers are dropped at scoring and the rest renormalised, as for any
  prediction.
- **Practice inputs at this snapshot.** These use the same definitions as
  the post-qualifying practice inputs, with two differences. They read only
  the sessions above. And they are measured against the fastest driver in this
  field, never against who went on to race.
- **Pre-weekend inputs** are computed for this field, not the
  previous race's starters.

**Candidates.** All use the same `Slim` logistic regression, C = 0.5, trained
on rows from 2018, when the practice data starts. There is no tuning.

| Id | Inputs | Count |
|---|---|---:|
| Q0 | the pre-weekend model's 13 (§9), no practice | 13 |
| Q1 | Q0 + best-lap gap | 14 |
| Q2 | Q1 + long-run pace gap + long-run laps | 16 |
| Q3 | Q2 + practice laps | 17 |
| Q4 | Q3 + compounds run + softest long-run gap | 19 |
| Q5 | standings only (§9 P1) + best-lap gap + long-run pace gap | 6 |

**Selection window: 2019–2025,** on a frame truncated at the end of 2025.

**Two bars:**
- **Championship order** (§1).
- **Practice order:** a positional prior on each starter's best-lap rank
  within the field, estimated walk-forward and Laplace-smoothed exactly like
  the qualifying-order baseline.

The site will compare the model with whichever bar scores better on
2019–2025, so it is never measured against the weaker of two available rules.

**Selection rule.** The candidate with the lowest mean race-level win log loss
on 2019–2025 is selected. If its win ECE is more than twice Q0's, stop and
report instead of freezing.

**Holdout: 2026, scored once.** Every 2026 race in the enriched season laps at
the time of freezing: R1–R14. R15's practice exists only in the upcoming-race
fetch. The selected model, Q0 and both bars are scored.

**Caveat, stated now.** Practice pace was part of the post-qualifying
selection, which was made with 2026 in view (§6). So the value of practice
pace on 2026 is not entirely unseen.

**What the result allows.**
- Recommend publishing the after-practice prediction only if the selected
  model's holdout log loss is below Q0's. Q0 is the pre-weekend inputs on the
  same field: a third prediction that knows more but scores no better adds
  nothing worth publishing.
- Any claim against the bar needs the holdout interval to exclude zero.
- Shipping needs:
  - a practice-only fetch;
  - a deadline in `revisions.py`;
  - a scoring bar;
  - a third series on the site.

  It is a separate decision, made after review.

### Selection — 2019–2025

Run with `python src/after_practice_selection.py select`, after the protocol,
the snapshot code and the script were committed. There were 152 races in
every run.

**The bars:**
- **Championship order: 1.7920** [1.6711, 1.9234].
- **Practice order: 2.1216** [1.9669, 2.2817].

Practice order is much the weaker rule. A single lap in practice says less
about the result than the standings do. So the site's bar for this snapshot
is **championship order**.

| Run | Inputs | Log loss | Winner | Podium | ECE (win) | vs championship order | vs Q0 |
|---|---:|---:|---:|---:|---:|---|---|
| **Q3** | 17 | **1.4811** | 48.7% | 58.6% | 0.0065 | −0.3109 [−0.4145, −0.2081] | −0.0577 [−0.0933, −0.0242] |
| Q1 | 14 | 1.4814 | 48.7% | 58.1% | 0.0075 | −0.3106 [−0.4138, −0.2055] | −0.0574 [−0.0902, −0.0269] |
| Q2 | 16 | 1.4838 | 49.3% | 57.7% | 0.0069 | −0.3082 [−0.4141, −0.2027] | −0.0550 [−0.0893, −0.0231] |
| Q4 | 19 | 1.5128 | 46.1% | 58.6% | 0.0077 | −0.2793 [−0.3889, −0.1668] | −0.0260 [−0.0752, +0.0260], not significant |
| *Q0, no practice* | 13 | *1.5388* | 49.3% | 57.9% | 0.0085 | −0.2532 [−0.3604, −0.1431] | — |
| Q5 | 6 | 1.6091 | 48.7% | 61.3% | 0.0132 | −0.1829 [−0.2470, −0.1185] | +0.0703 [−0.0500, +0.1767], not significant |

Unless marked, every interval is significant at 95%.

**What it says.**
- **Practice adds information.** Adding the best-lap gap alone (Q1) improves
  on the pre-weekend inputs by 0.057, and that is significant.
- **The rest adds almost nothing.** Long runs and the lap count (Q2, Q3) are
  within 0.003 of Q1.
- **Tyre inputs make it worse,** as §4 found for the post-qualifying model.
- **The pre-weekend inputs matter.** Standings alone plus practice (Q5)
  scores worse than the pre-weekend inputs with no practice at all (Q0), by
  0.07, though not significantly.

**Selected and frozen: Q3.**
- **Inputs:** the 13 pre-weekend inputs, plus `practice_best_lap_gap_ms`,
  `practice_long_run_pace_gap_ms`, `practice_long_run_laps` and
  `practice_laps`.
- **Estimator:** the same `Slim` logistic regression, C = 0.5, rows from 2018.
- **The rule picks it over Q1 by 0.0003.** That is far inside the noise, but
  the protocol has no tie-break, by design.
- **Calibration guard:** ECE 0.0065 against Q0's 0.0085, so not tripped.

This entry was committed before the holdout was run.

### Holdout — 2026, scored once

Run with `python src/after_practice_selection.py holdout Q3`, after the freeze
was committed. It covered the 14 races with practice in the season laps, R1 to
R14. The script refuses a second run.

| Model | Log loss | 95% CI | vs championship order | vs Q0 | Winner | Podium | ECE (win) |
|---|---:|---|---|---|---:|---:|---:|
| **Q3 — selected** | **1.6828** | [1.1923, 2.2092] | −0.1329 [−0.4907, +0.2044] | −0.1678 [−0.3532, +0.0056] | 35.7% | 45.2% | 0.0177 |
| Q0 — no practice | 1.8506 | [1.3701, 2.3443] | +0.0349 [−0.1935, +0.2798] | — | 35.7% | 45.2% | 0.0204 |
| *Practice order* | *1.8531* | [1.4260, 2.3813] | — | — | — | — | — |
| *Championship order* | *1.8157 on the same 14 races* (1.8007 on all 15) | | — | — | — | — | — |

None of the holdout comparisons is significant at 95%.

**What this says.**
- **Practice helps on 2026 as it did before.** Q3 is 0.17 better than the
  same model without practice. The interval just reaches zero (+0.0056) on
  fourteen races, so it is suggestive, not established.
- **It is the first of the three predictions to be ahead of its simple rule on
  2026,** by 0.13 on average. The interval spans zero, so the site still
  cannot claim it beats the rule.
- **Calibration holds better than the pre-weekend model's did.** Win ECE is
  0.0177 on the holdout, against 0.0065 in sample.

**Under the protocol:**
- Q3's holdout log loss (1.6828) is below Q0's (1.8506), so the
  recommendation is to **publish the after-practice prediction, using Q3.**
- The site **may not** say it beats championship order.
- Shipping needs:
  - a practice-only fetch for an upcoming race;
  - a deadline at the first qualifying session in `revisions.py`;
  - the after-practice field from that fetch;
  - championship order as the scoring bar;
  - a third, never-pooled series on the site.

  That is a separate change, made after review.

**A correction after the holdout, with no effect on it.**
- **The bug.** The sessions rule decided whether a weekend was a sprint
  weekend by looking for sprint sessions in the laps. Those run after this
  snapshot's deadline.
- **The fix.** The format is in the calendar beforehand, so it now comes from
  the race's `sprint_date`.
- **No effect on the result.** The rebuilt after-practice frame (3,770 rows)
  is byte-identical to the one selected on, so nothing above changes.
- **Test coverage.** The time-travel test in `tests/test_features.py` now
  covers this snapshot. Qualifying and any practice after it are removed.
