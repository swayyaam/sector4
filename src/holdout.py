"""The 2026 holdout: one clean look, after the selection is frozen.

Every choice made in Parts C and D -- the spline, the feature subsets, the
minimal four -- was made by reading an evaluation window that included 2026.
That is selection on the test set, and it makes the reported margin optimistic
by an unknown amount.

This script does two things in order and does not go back.

1. **Re-runs the selection with 2026 removed.** If the same model would not
   have been chosen from 2019-2025 evidence alone, the holdout is measuring the
   wrong specification and the result means nothing.
2. **Scores the frozen specification on 2026 once.** No tuning afterwards, no
   second variant promoted after seeing the number.

The primary specification is fixed before the holdout runs: a spline on
qualifying position, practice best-lap gap, driver championship points and the
driver's share of the team's points. The collinear-pair variant is reported
beside it for completeness and is explicitly not the one being judged.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import baselines as B  # noqa: E402
import diagnose as D  # noqa: E402
import features as F  # noqa: E402
import finalists as FN  # noqa: E402
import model as M  # noqa: E402

HOLDOUT_SEASON = 2026
PRIMARY = FN.MINIMAL_SHARE          # chosen for explainability; see MODEL_REPORT.md
SECONDARY = FN.MINIMAL


def selection_without_holdout(df: pd.DataFrame, bar: pd.DataFrame) -> None:
    """Would the same model have been chosen without ever seeing 2026?"""
    pre = df[df["year"] < HOLDOUT_SEASON]
    print("\n### Step 1 — the selection, redone with 2026 removed\n")

    co = D.coefficients(pre, F.POST)
    sig = co[co["significant"]]["feature"].tolist()
    print(f"  Coefficients significant at 95% on 2019-2025 data only: {len(sig)}")
    for _, r in co[co["significant"]].iterrows():
        print(f"    {r['feature']:<32} z = {r['z']:+.2f}")
    chosen = {"quali_position", "practice_best_lap_gap_ms",
              "driver_standing_points", "team_standing_points"}
    print(f"\n  Same four as before: {set(sig) == chosen}")

    print("\n  Finalist ranking on 2019-2025 only:\n")
    rows = []
    for model in FN.candidates(F.POST):
        preds = M.walk_forward(df, model, F.POST, verbose=False)
        _, per_race = M.score_predictions(preds, model.name)
        sub = per_race.merge(df[["raceId", "year"]].drop_duplicates(), on="raceId")
        sub = sub[sub["year"] < HOLDOUT_SEASON]
        bar_sub = bar[bar["raceId"].isin(sub["raceId"])]
        mean, lo, hi = M.bootstrap_ci(sub, "log_loss")
        d = M.paired_difference(sub, bar_sub, "log_loss")
        rows.append({"model": model.name, "races": len(sub), "log_loss": round(mean, 4),
                     "ci": f"[{lo:.4f}, {hi:.4f}]", "vs_bar": f"{d['mean_difference']:+.4f}",
                     "significant": d["significant"] and d["mean_difference"] < 0})
    b = bar[bar["raceId"].isin(
        df.loc[df["year"] < HOLDOUT_SEASON, "raceId"].drop_duplicates())]
    bm, bl, bh = M.bootstrap_ci(b, "log_loss")
    rows.append({"model": "baseline: qualifying order", "races": len(b),
                 "log_loss": round(bm, 4), "ci": f"[{bl:.4f}, {bh:.4f}]",
                 "vs_bar": "-", "significant": False})
    print(pd.DataFrame(rows).sort_values("log_loss").to_string(index=False))


def holdout(df: pd.DataFrame, bar: pd.DataFrame) -> pd.DataFrame:
    """Score the frozen specifications on 2026. Once."""
    print(f"\n### Step 2 — {HOLDOUT_SEASON} holdout, scored once\n")
    hold_ids = df.loc[df["year"] == HOLDOUT_SEASON, "raceId"].drop_duplicates().tolist()
    bar_hold = bar[bar["raceId"].isin(hold_ids)]

    rows = []
    for label, cols, role in (("minimal 4 (share) — PRIMARY", PRIMARY, "primary"),
                              ("minimal 4 (team points)", SECONDARY, "secondary")):
        model = D.SplineQuali(list(cols))
        model.name = label
        preds = M.walk_forward(df, model, F.POST, verbose=False)
        _, per_race = M.score_predictions(preds, label)
        sub = per_race[per_race["raceId"].isin(hold_ids)]
        mean, lo, hi = M.bootstrap_ci(sub, "log_loss")
        d = M.paired_difference(sub, bar_hold, "log_loss")
        verdict = ("beats the bar" if d["significant"] and d["mean_difference"] < 0
                   else "loses to the bar" if d["significant"]
                   else "indistinguishable from the bar")
        rows.append({"model": label, "role": role, "races": len(sub),
                     "log_loss": round(mean, 4), "ci": f"[{lo:.4f}, {hi:.4f}]",
                     "vs_bar": f"{d['mean_difference']:+.4f}",
                     "vs_bar_ci": f"[{d['lo']:+.4f}, {d['hi']:+.4f}]", "verdict": verdict,
                     "ece_win": round(M.calibration(
                         preds[preds["raceId"].isin(hold_ids)], "win")[1], 4)})
    bm, bl, bh = M.bootstrap_ci(bar_hold, "log_loss")
    rows.append({"model": "baseline: qualifying order", "role": "bar", "races": len(bar_hold),
                 "log_loss": round(bm, 4), "ci": f"[{bl:.4f}, {bh:.4f}]",
                 "vs_bar": "-", "vs_bar_ci": "-", "verdict": "-", "ece_win": np.nan})
    out = pd.DataFrame(rows)
    print(out.to_string(index=False))
    return out


def main() -> int:
    pd.set_option("display.width", 230)
    df = M.dataset(F.POST)
    _, extra = B.run()
    bar = pd.DataFrame(extra["scores"]["qualifying order"]._rows)

    print("=" * 112)
    print(f"{HOLDOUT_SEASON} HOLDOUT — selection frozen first, then one look.")
    print("=" * 112)
    selection_without_holdout(df, bar)
    holdout(df, bar)
    print(f"\n  {HOLDOUT_SEASON} is a regulation reset season and holds 14 races. "
          "Intervals that wide are weak evidence either way.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
