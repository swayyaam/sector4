"""Phase 2 Part E: produce a prediction for a race that has not happened.

The shipped model is `minimal 4 (share)` at the post-qualifying snapshot: a
spline on qualifying position, practice best-lap gap, driver championship
points, and the driver's share of the team's points. The pre-weekend snapshot
uses the same specification minus the two features that need the weekend.

Three properties this file is responsible for.

**Provenance.** Every prediction records the model version, the exact feature
list, the data version and the commit the code was at. A reader a year from now
can tell which model made which call without guessing.

**Immutability.** A prediction is written once, before the session it predicts,
and never touched again. `src/score_race.py` writes results to a separate file.
The separation is the point of the track record: a file that can be edited
after the fact proves nothing.

**Keyed on (season, round), not raceId.** An upcoming race has no raceId --
`build_processed.py` mints one only when a race completes. Matching on the pair
that is known in advance means a prediction cannot be orphaned by an id that
turns out differently.

Usage:
    python src/predict.py --season 2026 --round 15 --snapshot pre_weekend
    python src/predict.py --season 2026 --round 15 --snapshot post_practice
    python src/predict.py --season 2026 --round 15 --snapshot post_qualifying
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import diagnose as D  # noqa: E402
import features as F  # noqa: E402
import revisions as REV  # noqa: E402
import upcoming as UP  # noqa: E402
import finalists as FN  # noqa: E402
import model as M  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "predictions"

MODEL_VERSION = "minimal4-share-v1"
MC_DRAWS = 20_000
RNG_SEED = 20260923

# The shipped post-qualifying feature set (MODEL_REPORT §7).
SHIPPED = list(FN.MINIMAL_SHARE)

# The pre-weekend model, selected on its own in MODEL_REPORT §9 (P4-2018):
# driver form, team form and recent qualifying, all from races before this
# one. It replaced the reduction of SHIPPED to its two pre-weekend inputs,
# which scored worse than championship order in sample and on 2026.
PRE_MODEL_VERSION = "pre-form-quali-v1"
PRE_WEEKEND_COLS = [
    "driver_races_started", "driver_finish_pos_mean_5", "driver_points_rate_5",
    "driver_dnf_rate_10", "driver_standing_position", "driver_standing_points",
    "team_finish_pos_mean_5", "team_points_rate_5", "team_dnf_rate_10",
    "team_standing_position", "team_standing_points",
    "driver_quali_pos_mean_3", "team_quali_pos_mean_3",
]

# The after-practice model, selected in MODEL_REPORT §10 (Q3): the pre-weekend
# inputs plus this weekend's practice before qualifying, measured within the
# after-practice field.
PRACTICE_MODEL_VERSION = "practice-form-v1"
PRACTICE_COLS = PRE_WEEKEND_COLS + [
    "practice_best_lap_gap_ms", "practice_long_run_pace_gap_ms",
    "practice_long_run_laps", "practice_laps",
]

COLS_FOR = {F.PRE: PRE_WEEKEND_COLS, F.PRACTICE: PRACTICE_COLS, F.POST: SHIPPED}
VERSION_FOR = {F.PRE: PRE_MODEL_VERSION, F.PRACTICE: PRACTICE_MODEL_VERSION, F.POST: MODEL_VERSION}

# What a race page calls each input. Plain words, and never a timing value.
FACTOR_LABELS = {
    "quali_position": "Qualifying position",
    "practice_best_lap_gap_ms": "Practice pace",
    "driver_standing_points": "Championship points",
    "driver_vs_team_points_share_5": "Share of team points",
    "driver_races_started": "Experience",
    "driver_finish_pos_mean_5": "Recent finishes",
    "driver_points_rate_5": "Recent points",
    "driver_dnf_rate_10": "Recent retirements",
    "driver_standing_position": "Championship position",
    "team_finish_pos_mean_5": "Team's recent finishes",
    "team_points_rate_5": "Team's recent points",
    "team_dnf_rate_10": "Team's recent retirements",
    "team_standing_position": "Team's championship position",
    "team_standing_points": "Team's championship points",
    "driver_quali_pos_mean_3": "Recent qualifying",
    "team_quali_pos_mean_3": "Team's recent qualifying",
    "practice_long_run_pace_gap_ms": "Long-run pace",
    "practice_long_run_laps": "Long-run laps",
    "practice_laps": "Practice laps",
}


def commit_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()[:12]
    except Exception:
        return "unknown"


def data_version() -> str:
    path = ROOT / "data" / "processed" / "races.csv"
    return f"v0.1.1-data+{datetime.fromtimestamp(path.stat().st_mtime, timezone.utc):%Y%m%d}"


def upcoming_race(season: int, rnd: int) -> dict:
    """Schedule metadata for a race that has no row in data/processed yet."""
    from jolpica_client import JolpicaClient

    for r in JolpicaClient().get_all(f"{season}/races"):
        if int(r["round"]) == rnd:
            return r
    raise SystemExit(f"{season} round {rnd} is not in the schedule")


def race_row(tables: dict, season: int, rnd: int) -> tuple[pd.Series, bool]:
    """A race row the feature builder can use, completed or not."""
    races = tables["races"]
    got = races[(races["year"] == season) & (races["round"] == rnd)]
    if len(got):
        return got.iloc[0], True

    sched = upcoming_race(season, rnd)
    circuits = F._rd(F.PROCESSED / "circuits.csv")
    ref = sched["Circuit"]["circuitId"]
    match = circuits[circuits["circuitRef"] == ref]
    if match.empty:
        raise SystemExit(f"circuitRef {ref!r} is not in our circuits table")
    # Provisional only. The authoritative key is (season, round); the scorer
    # resolves the real raceId once build_processed.py has minted one.
    provisional = int(races["raceId"].max()) + 1
    row = pd.Series({
        "raceId": provisional, "year": season, "round": rnd,
        "circuitId": int(match.iloc[0]["circuitId"]), "name": sched["raceName"],
        "date": sched["date"], "regs_era": races.loc[races["year"] == season, "regs_era"].iloc[0],
        "order": season * 100 + rnd,
        # The format is in the schedule before the weekend. The after-practice
        # snapshot reads it to know which practice comes before qualifying.
        "sprint_date": (sched.get("Sprint") or {}).get("date"),
    })
    return row, False


def plackett_luce(strengths: np.ndarray, draws: int = MC_DRAWS) -> np.ndarray:
    """Sample finishing orders, returning each driver's position distribution.

    Strengths are the fitted win probabilities, which makes the first-place
    marginal of the simulation exactly the model's p_win -- the quantity that
    was actually validated. Podium, top ten and the full distribution then come
    from one coherent joint rather than from four marginals that need not agree.
    """
    rng = np.random.default_rng(RNG_SEED)
    z = np.log(np.clip(strengths, 1e-12, None))
    n = len(z)
    order = np.argsort(-(z[None, :] + rng.gumbel(size=(draws, n))), axis=1)
    rank = np.empty_like(order)
    rank[np.arange(draws)[:, None], order] = np.arange(n)[None, :]
    counts = np.stack([np.bincount(rank[:, i], minlength=n) for i in range(n)])
    dist = (counts + 1.0) / (draws + n)
    return dist / dist.sum(axis=1, keepdims=True)


def round_to_total(values: np.ndarray, total: float, places: int = 6) -> list[float]:
    """Round for publication without breaking the sum the schema requires.

    Rounding twenty-two probabilities to six places leaves a residue of about
    1e-6, which is exactly the tolerance the validator allows -- landing on the
    boundary rather than inside it. The residue is pushed onto the largest
    element, where it is invisible at this precision.
    """
    r = np.round(values, places)
    r[int(np.argmax(r))] += round(total - r.sum(), places)
    return [float(v) for v in r]


def top_factors(x: pd.DataFrame, cols: list[str], i: int) -> list[dict]:
    """The inputs moving this driver's number most, as normalised weights.

    Weights, never the underlying values. A gap to the field's best lap
    expressed in milliseconds would be republishing Formula 1 timing data;
    the same gap as a 0-1 magnitude is a model output. See DATA_LICENSE.md.
    """
    z = (x - x.mean()) / x.std(ddof=0).replace(0, np.nan)
    row = z.iloc[i]
    out = []
    for c in cols:
        v = row.get(c)
        if pd.isna(v):
            continue
        better_when_low = c in {"quali_position", "practice_best_lap_gap_ms"}
        helps = (v < 0) if better_when_low else (v > 0)
        out.append({"label": FACTOR_LABELS.get(c, c), "direction": "positive" if helps else "negative",
                    "magnitude": round(float(min(abs(v) / 3.0, 1.0)), 6)})
    return sorted(out, key=lambda d: -d["magnitude"])[:4]


def model_factors(train: pd.DataFrame, feats: pd.DataFrame, cols: list[str]) -> list[list[dict]]:
    """Each input's push on each driver's win chance, read from the model.

    The win logistic is refitted exactly as the model fits it (median
    imputation, standardisation, C = 0.5), and an input's contribution is its
    coefficient times the driver's standardised value. The direction comes
    from the fitted model, so an input where lower is better -- a finishing
    position, a retirement rate -- reads correctly without a hand-kept list.
    Weights only, never the underlying values.
    """
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    pipe = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                         LogisticRegression(max_iter=1000, C=0.5))
    pipe.fit(train[cols].astype(float), train["win"].to_numpy())
    contrib = pipe[:-1].transform(feats[cols].astype(float)) * pipe[-1].coef_[0]
    out = []
    for row in contrib:
        items = [{"label": FACTOR_LABELS.get(c, c),
                  "direction": "positive" if v > 0 else "negative",
                  "magnitude": round(float(min(abs(v) / 3.0, 1.0)), 6)}
                 for c, v in zip(cols, row) if abs(v) > 0]
        out.append(sorted(items, key=lambda d: -d["magnitude"])[:4])
    return out


def points_chance(train: pd.DataFrame, test: pd.DataFrame, cols: list[str]) -> np.ndarray:
    """Each driver's chance of scoring points: T1 from MODEL_REPORT §12.

    The snapshot's own estimator fitted on the top-ten target directly, which
    beat a positional rule for every model, where the simulation's top-ten
    chance did not. It is a separate model, so it need not agree with the
    simulated podium or finishing order. Imported here rather than at the top,
    because points_finish.py imports this module.
    """
    import points_finish as PF

    if "quali_position" in cols:
        xtr, _ = PF._widen(train, cols)
        xte, _ = PF._widen(test, cols)
    else:
        xtr, xte = train[cols].astype(float), test[cols].astype(float)
    return np.clip(PF._logistic(xtr, train["top10"].to_numpy(), xte), 0.0, 1.0)


def _fit_dnf(train: pd.DataFrame, test: pd.DataFrame, cols: list[str]) -> pd.Series:
    """A logistic on the same features, for the retirement marginal."""
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    ids = test["driverId"].to_numpy()
    y = train["dnf"].to_numpy()
    if y.sum() < 20:
        return pd.Series(float(y.mean()), index=ids)
    pipe = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                         LogisticRegression(max_iter=2000, C=0.5))
    pipe.fit(train[cols].astype(float), y)
    return pd.Series(pipe.predict_proba(test[cols].astype(float))[:, 1], index=ids)


def check_after_practice_inputs(feats: pd.DataFrame) -> None:
    """Refuse an after-practice prediction that practice never reached.

    A field with almost no practice times is a prediction from the pre-weekend
    inputs under the after-practice name, which is not what §10 validated.
    """
    timed = int(feats["practice_best_lap_gap_ms"].notna().sum())
    if timed < max(10, len(feats) // 2):
        raise SystemExit(f"only {timed} of {len(feats)} drivers have a practice time; "
                         "refusing to publish an after-practice prediction without practice")


def check_post_qualifying_inputs(tables: dict, race: pd.Series, feats: pd.DataFrame) -> None:
    """Refuse a post-qualifying prediction that cannot see qualifying.

    For a race that has not run, data/processed holds no qualifying result
    (build_processed.py keeps completed races only) and entrants() falls back
    to the previous race's field. The spline then fills every missing
    qualifying position with 20 and practice gaps are median-imputed, so a
    file labelled post-qualifying would carry no qualifying information at
    all. That has to be an error, never a silent substitution.
    """
    q = tables["qualifying"]
    if q[q["raceId"] == int(race["raceId"])].empty:
        raise SystemExit(
            f"{int(race['year'])} round {int(race['round'])}: no qualifying results in "
            "data/processed, so a post-qualifying prediction would not see qualifying. "
            "Refusing. See DEPLOY.md, 'Post-qualifying: blocked'.")
    missing = sorted(feats.loc[feats["quali_position"].isna(), "driverId"].astype(int))
    if missing:
        raise SystemExit(f"no qualifying position for driverId {missing}; refusing rather than "
                         "filling it in")
    if feats["practice_best_lap_gap_ms"].isna().all():
        raise SystemExit("no practice pace for any driver this weekend; run fetch_fastf1.py for "
                         "the weekend first. Refusing rather than imputing the whole field.")


def build(season: int, rnd: int, snapshot: str) -> dict:
    tables = F.load_tables()
    race, completed = race_row(tables, season, rnd)
    cols = COLS_FOR[snapshot]

    # A race that has not run has no weekend in data/processed. Its qualifying
    # and practice are read from the fetched session data instead, onto
    # in-memory copies of the tables; nothing is written or minted.
    if snapshot == F.POST and not completed:
        try:
            tables = UP.augment(tables, race)
        except UP.MissingWeekendData as e:
            raise SystemExit(f"{season} round {rnd}: {e} Refusing.") from e
    if snapshot == F.PRACTICE and not completed:
        try:
            tables = UP.augment_practice(tables, race)
        except UP.MissingWeekendData as e:
            raise SystemExit(f"{season} round {rnd}: {e} Refusing.") from e

    feats = F.build_race(tables, race, snapshot)
    if feats.empty:
        raise SystemExit(f"no entrants resolved for {season} round {rnd} at {snapshot}")
    # build_race returns the keys and the features, and team_entity_id is
    # neither, so it has to be joined back on. Without it a prediction cannot
    # be rendered: no team name, no colour, nothing to group a garage by.
    field = F.entrants(tables, race, snapshot)[["driverId", "team_entity_id"]]
    feats = feats.merge(field, on="driverId", how="left")
    missing = feats["team_entity_id"].isna().sum()
    if missing:
        raise SystemExit(f"{missing} drivers have no team_entity_id; refusing to publish")
    if snapshot == F.POST:
        check_post_qualifying_inputs(tables, race, feats)
    if snapshot == F.PRACTICE:
        check_after_practice_inputs(feats)

    history = M.dataset(snapshot)
    train = history[history["order"] < int(race["order"])]
    if len(train) < 500:
        raise SystemExit(f"only {len(train)} training rows; refusing to predict")

    # The spline only makes sense where qualifying position exists. Before the
    # cars run it does not, so the shipped specification reduces to the two
    # features that are available -- a genuinely weaker model, and the file
    # says so rather than presenting the two as equivalent.
    model = D.SplineQuali(list(cols)) if "quali_position" in cols else D.Slim(list(cols))
    probs = model.fit_predict(train, feats)

    # Those classes fit only the targets the scorer needs, so p_dnf comes back
    # as zero. A published zero would be a claim that no car can retire, which
    # is worse than a rough number. It is fitted here on the same features,
    # separately, and MODEL_REPORT.md validated only p_win -- so this marginal
    # is stated as unvalidated rather than implied to carry the same weight.
    probs["dnf"] = _fit_dnf(train, feats, list(cols))
    p_points = points_chance(train, feats, list(cols))

    ids = feats["driverId"].astype(int).to_numpy()
    p_win = np.clip(probs["win"].reindex(ids).to_numpy(dtype=float), 1e-9, None)
    p_win = p_win / p_win.sum()
    dist = plackett_luce(p_win)
    p_dnf = np.clip(probs["dnf"].reindex(ids).to_numpy(dtype=float), 0.0, 1.0)

    x = feats[[c for c in cols if c in feats.columns]].astype(float)
    # The pre-weekend model's factors come from its own coefficients; the
    # post-qualifying model keeps the method it shipped with.
    factors = model_factors(train, feats, list(cols)) if snapshot != F.POST else None
    n = len(ids)
    win = round_to_total(dist[:, 0], 1.0)
    podium = round_to_total(dist[:, :3].sum(axis=1), min(3.0, n))
    top10 = round_to_total(dist[:, :min(10, n)].sum(axis=1), float(min(10, n)))
    drivers = []
    for i, did in enumerate(ids):
        # A rounded podium below a rounded win would fail the validator even
        # though the simulation cannot produce it, so the ordering is restored
        # after rounding rather than assumed to survive it.
        pw = win[i]
        pp = max(podium[i], pw)
        pt = max(top10[i], pp)
        drivers.append({
            "driverId": int(did),
            "team_entity_id": str(feats.iloc[i]["team_entity_id"]),
            "p_win": pw, "p_podium": pp, "p_top10": pt,
            "p_dnf": round(float(p_dnf[i]), 6),
            "p_points": round(float(p_points[i]), 6),
            "expected_position": round(float((dist[i] * np.arange(1, n + 1)).sum()), 6),
            "position_distribution": round_to_total(dist[i], 1.0),
            "top_factors": factors[i] if factors is not None else top_factors(x, list(cols), i),
        })

    return {
        "season": season, "round": rnd, "race_id": int(race["raceId"]),
        "race_id_is_provisional": not completed,
        "race_name": str(race["name"]),
        "snapshot": snapshot,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model_version": VERSION_FOR[snapshot],
        "model_features": list(cols),
        "model_note": (
            "Shipped specification, validated at this snapshot. The DNF "
            "probability is a separate logistic on the same features and was "
            "not part of that validation."
            if snapshot == F.POST else
            "Selected for this snapshot in MODEL_REPORT.md §10: the pre-weekend "
            "inputs plus this weekend's practice before qualifying, measured "
            "within the drivers who ran in FP2 or FP3 (FP1 on a sprint weekend). "
            "Better than the same inputs without practice in sample and on the "
            "2026 holdout, and not shown to beat championship order. The DNF "
            "probability is a separate logistic on the same features and was "
            "not validated."
            if snapshot == F.PRACTICE else
            "Selected for this snapshot in MODEL_REPORT.md §9: driver and team "
            "form and recent qualifying, from races before this one only. Better "
            "than the previous pre-weekend model in sample and on the 2026 "
            "holdout, and not shown to beat championship order. The DNF "
            "probability is a separate logistic on the same features and was "
            "not validated."
        ),
        "data_version": data_version(),
        "commit_sha": commit_sha(),
        "is_mock": False,
        "training_races": int(train["raceId"].nunique()),
        "drivers": sorted(drivers, key=lambda d: -d["p_win"]),
        "result": None,
    }


def path_for(season: int, rnd: int, snapshot: str, revision: int = 1) -> Path:
    return REV.revision_path(season, rnd, snapshot, revision, OUT)


def _display(path: Path) -> str:
    """Repo-relative where possible, absolute otherwise. A temp directory in a
    test is not under ROOT, and a cosmetic path should never crash a run."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--round", type=int, required=True)
    ap.add_argument("--snapshot", choices=[F.PRE, F.PRACTICE, F.POST], default=F.PRE)
    ap.add_argument("--revise", action="store_true",
                    help="publish a new revision of an existing prediction")
    ap.add_argument("--reason", help="why the revision exists; required with --revise")
    args = ap.parse_args()

    existing = REV.revisions(args.season, args.round, args.snapshot, OUT)
    if existing and not args.revise:
        raise SystemExit(
            f"{existing[-1][1].name} is already published. Predictions are never "
            "overwritten; publish a revision with --revise --reason \"...\".")
    if args.revise and not existing:
        raise SystemExit("--revise given, but there is nothing to revise.")
    if args.revise and not (args.reason and args.reason.strip()):
        raise SystemExit("--revise needs --reason: a revision nobody can explain proves nothing.")

    # Nothing is published after its deadline. A revision then could have seen
    # the session; a first prediction then would be ignored by the scorer and
    # sit in the record as noise. Either way it never reaches the repository.
    cutoff = REV.deadline(args.season, args.round, args.snapshot)
    if REV.now_utc() >= cutoff:
        what = "a revision" if existing else "a first prediction"
        raise SystemExit(f"the {args.snapshot} deadline ({cutoff:%Y-%m-%dT%H:%MZ}) has "
                         f"passed; {what} published now could not be scored.")

    revision = (existing[-1][0] + 1) if existing else 1
    out = path_for(args.season, args.round, args.snapshot, revision)
    if out.exists():
        raise SystemExit(f"{out} already exists. Predictions are never overwritten.")

    pred = build(args.season, args.round, args.snapshot)
    pred["revision"] = revision
    if existing:
        prev_rev, prev_path, prev = existing[-1]
        pred["supersedes"] = prev_path.name
        pred["revision_reason"] = args.reason.strip()

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pred, indent=2) + "\n")

    if existing:
        # The one sanctioned in-place change: two pointers on the file being
        # superseded. The content digest excludes them, and is checked here so
        # a bug in this block cannot quietly become a rewrite.
        before = REV.content_digest(prev)
        prev["superseded_by"] = out.name
        prev["superseded_reason"] = pred["revision_reason"]
        if REV.content_digest(prev) != before:
            raise SystemExit("FATAL: superseding would change prediction content")
        prev_path.write_text(json.dumps(prev, indent=2) + "\n")

    print(f"{args.season} R{args.round} {pred['race_name']} — {args.snapshot}, revision {revision}")
    print(f"  generated {pred['generated_at']}  model {pred['model_version']}  "
          f"commit {pred['commit_sha']}")
    if existing:
        print(f"  supersedes {pred['supersedes']}: {pred['revision_reason']}")
    print(f"  trained on {pred['training_races']} races, {len(pred['model_features'])} features")
    for d in pred["drivers"][:5]:
        print(f"    driver {d['driverId']:>4}  win {d['p_win']:.3f}  podium {d['p_podium']:.3f}")
    print(f"  -> {_display(out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
