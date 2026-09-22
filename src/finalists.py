"""The candidates the diagnostics pointed at, scored on the window that matters.

The last fifty races are the primary window. They are what the site will be
predicting into, every fold behind them trains on a substantial history, and
the baseline is measurably harder to beat there than it is across the whole
2019-onward span. The full 166 is reported second, as context rather than as
the verdict.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import baselines as B  # noqa: E402
import diagnose as D  # noqa: E402
import features as F  # noqa: E402
import model as M  # noqa: E402

LAST_N = 50

# The four coefficients that differed from zero at 95%, and nothing else.
MINIMAL = ["quali_position", "practice_best_lap_gap_ms",
           "driver_standing_points", "team_standing_points"]
# The same, with the collinear team-points term replaced by the share it was
# indirectly computing.
MINIMAL_SHARE = ["quali_position", "practice_best_lap_gap_ms",
                 "driver_standing_points", "driver_vs_team_points_share_5"]


def subset(snapshot: str, keep_groups: set[str]) -> list[str]:
    avail = set(F.features_for(snapshot))
    return [f.name for f in F.FEATURES if f.name in avail and f.group in keep_groups]


def candidates(snapshot: str) -> list:
    core = {"Qualifying", "Practice", "Driver form", "Team form"}
    with_rel = core | {"Relative form"}
    out = []

    m = D.SplineQuali(subset(snapshot, with_rel)); m.name = "spline + 22 (with relative form)"
    out.append(m)
    m = D.SplineQuali(subset(snapshot, core)); m.name = "spline + 19 (no relative form)"
    out.append(m)
    m = D.LgbmRegularised(list(F.features_for(snapshot))); m.name = "lightgbm regularised (33)"
    out.append(m)
    m = D.SplineQuali(list(MINIMAL)); m.name = "minimal 4 (significant only)"
    out.append(m)
    m = D.SplineQuali(list(MINIMAL_SHARE)); m.name = "minimal 4, share not team points"
    out.append(m)
    m = D.SplineQuali(list(F.features_for(snapshot))); m.name = "spline + 33 (everything)"
    out.append(m)
    return out


def _window(per_race: pd.DataFrame, ids: list[int] | None) -> pd.DataFrame:
    return per_race if ids is None else per_race[per_race["raceId"].isin(ids)]


def report(rows: list[dict], bar: pd.DataFrame, ids: list[int] | None, title: str) -> None:
    bar_w = _window(bar, ids)
    table = []
    for r in rows:
        pr = _window(r["per_race"], ids)
        if pr.empty:
            continue
        mean, lo, hi = M.bootstrap_ci(pr, "log_loss")
        d = M.paired_difference(pr, bar_w, "log_loss")
        verdict = ("beats the bar" if d["significant"] and d["mean_difference"] < 0
                   else "loses to the bar" if d["significant"]
                   else "indistinguishable")
        table.append({"model": r["name"], "races": len(pr), "log_loss": round(mean, 4),
                      "ci": f"[{lo:.4f}, {hi:.4f}]",
                      "vs_bar": f"{d['mean_difference']:+.4f}",
                      "vs_bar_ci": f"[{d['lo']:+.4f}, {d['hi']:+.4f}]", "verdict": verdict})
    b_mean, b_lo, b_hi = M.bootstrap_ci(bar_w, "log_loss")
    table.append({"model": "baseline: qualifying order", "races": len(bar_w),
                  "log_loss": round(b_mean, 4), "ci": f"[{b_lo:.4f}, {b_hi:.4f}]",
                  "vs_bar": "-", "vs_bar_ci": "-", "verdict": "-"})
    print(f"\n### {title}\n")
    print(pd.DataFrame(table).sort_values("log_loss").to_string(index=False))


def main() -> int:
    pd.set_option("display.width", 230)
    snapshot = F.POST
    df = M.dataset(snapshot)
    _, extra = B.run()
    bar = pd.DataFrame(extra["scores"]["qualifying order"]._rows)

    rows = []
    for model in candidates(snapshot):
        print(f"  fitting {model.name} ...", flush=True)
        preds = M.walk_forward(df, model, snapshot, verbose=False)
        _, per_race = M.score_predictions(preds, model.name)
        rows.append({"name": model.name, "per_race": per_race, "preds": preds})

    all_ids = rows[0]["per_race"]["raceId"].tolist()
    late_ids = all_ids[-LAST_N:]

    print("=" * 118)
    print("FINALISTS — post-qualifying.  Primary window is the last 50 races.")
    print("=" * 118)
    report(rows, bar, late_ids, f"Last {LAST_N} races (primary)")
    report(rows, bar, None, "All 166 races (secondary)")

    print("\n### Calibration on the last 50 races (expected calibration error)\n")
    cal = []
    for r in rows:
        sub = r["preds"][r["preds"]["raceId"].isin(late_ids)]
        row = {"model": r["name"]}
        for t in ("win", "podium"):
            row[t] = round(M.calibration(sub, t)[1], 4)
        cal.append(row)
    print(pd.DataFrame(cal).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
