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
