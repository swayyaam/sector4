"""Select the pre-weekend model, by the protocol in MODEL_REPORT.md §9.

The protocol was committed before this script was run. This file carries it
out and adds nothing to it:

* six candidate input sets (P0-P5) times two training windows (rows from
  2018, rows from 2014), all the same regularised logistic regression;
* a walk-forward over 2019-2025 only, on a frame truncated at the end of 2025,
  so no 2026 race is predicted during selection;
* the bar is championship order, scored on the same races;
* the lowest mean race-level win log loss is selected, subject to a
  calibration guard;
* the frozen choice is scored on 2026 exactly once.

Usage:
    python src/pre_weekend_selection.py select
    python src/pre_weekend_selection.py holdout P2-2014

`holdout` refuses to run twice: the first result is the result.
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import baselines as B  # noqa: E402
import diagnose as D  # noqa: E402
import features as F  # noqa: E402
import model as M  # noqa: E402

OUT = M.ROOT / "data" / "features" / "runs" / "pre_weekend_selection"
SELECT_FROM, SELECT_TO = 2019, 2025
HOLDOUT_SEASON = 2026
WINDOWS = (2018, 2014)
BAR = "championship order"

DRIVER_FORM = [f.name for f in F.FEATURES if f.group == "Driver form"]
TEAM_FORM = [f.name for f in F.FEATURES if f.group == "Team form"]
RECENT_QUALI = ["driver_quali_pos_mean_3", "team_quali_pos_mean_3"]
STANDINGS = ["driver_standing_position", "driver_standing_points",
             "team_standing_position", "team_standing_points"]

CANDIDATES: dict[str, list[str]] = {
    "P0": ["driver_standing_points", "driver_vs_team_points_share_5"],
    "P1": STANDINGS,
    "P2": STANDINGS + RECENT_QUALI,
    "P3": DRIVER_FORM + TEAM_FORM,
    "P4": DRIVER_FORM + TEAM_FORM + RECENT_QUALI,
    "P5": list(F.features_for(F.PRE, original_only=True)) + RECENT_QUALI,
}
INCUMBENT = "P0-2018"


# ---------------------------------------------------------------- the frame
def _pre_frame(window: int, tables: dict) -> pd.DataFrame:
    """Pre-weekend features for every race from `window` on.

    2018 onward is the cached frame the shipped model trains on. Earlier
    seasons are built by the same code and cached beside it.
    """
    frames = [M.feature_frame(F.PRE)]
    if window < F.FIRST_SEASON:
        path = M.CACHE / f"{F.PRE}_from_{window}.csv"
        if M.cache_is_fresh(path):
            early = pd.read_csv(path)
        else:
            races = tables["races"]
            ids = races.loc[(races["year"] >= window) & (races["year"] < F.FIRST_SEASON),
                            "raceId"].tolist()
            print(f"  building pre-weekend features for {len(ids)} races before "
                  f"{F.FIRST_SEASON} ...", flush=True)
            early = F.build(ids, F.PRE, tables)
            early.to_csv(path, index=False)
        frames.insert(0, early)
    return pd.concat(frames, ignore_index=True)


# The two new inputs. The selection ran this function; it now lives in
# features.py, where the shipped model computes them, so the two cannot drift.
recent_quali = F.recent_quali


def dataset(window: int, through: int, tables: dict) -> pd.DataFrame:
    """Features, the two new inputs and the targets, for races `window`..`through`."""
    # The frame now carries the two inputs itself; they are dropped and
    # recomputed here so the selection reads exactly what it read when it ran.
    x = _pre_frame(window, tables).drop(columns=RECENT_QUALI, errors="ignore")
    y = M.targets_frame()
    df = x.merge(y, on=["raceId", "driverId"], how="inner")
    df = df[(df["year"] >= window) & (df["year"] <= through)]
    df = df.merge(recent_quali(tables, df[["raceId", "driverId"]]),
                  on=["raceId", "driverId"], how="left")
    return df.sort_values(["order", "driverId"]).reset_index(drop=True)


# ----------------------------------------------------------------- scoring
def run(df: pd.DataFrame, cols: list[str], eval_from: int, eval_to: int) -> tuple[dict, pd.DataFrame, float]:
    preds = M.walk_forward(df, D.Slim(cols), F.PRE, eval_from=eval_from, verbose=False)
    preds = preds[preds["year"] <= eval_to]
    summary, per_race = M.score_predictions(preds, "candidate")
    _, ece = M.calibration(preds, "win")
    return summary, per_race, ece


def bar_scores(eval_from: int, eval_to: int) -> pd.DataFrame:
    _, extra = B.run(eval_from=eval_from)
    rows = pd.DataFrame(extra["scores"][BAR]._rows)
    races = pd.read_csv(F.PROCESSED / "races.csv")[["raceId", "year"]]
    rows = rows.merge(races, on="raceId")
    return rows[(rows["year"] >= eval_from) & (rows["year"] <= eval_to)]


def _fmt(d: dict) -> str:
    return (f"{d['mean_difference']:+.4f} [{d['lo']:+.4f}, {d['hi']:+.4f}]"
            f"{' significant' if d['significant'] else ''}")


# ---------------------------------------------------------------- commands
def select() -> int:
    """The twelve runs on 2019-2025, and the choice the protocol makes."""
    OUT.mkdir(parents=True, exist_ok=True)
    tables = F.load_tables()
    bar = bar_scores(SELECT_FROM, SELECT_TO)
    results, per_race = [], {}
    for window in WINDOWS:
        df = dataset(window, SELECT_TO, tables)
        assert df["year"].max() <= SELECT_TO, "a 2026 row reached the selection frame"
        for cid, cols in CANDIDATES.items():
            name = f"{cid}-{window}"
            print(f"  {name}: {len(cols)} inputs ...", flush=True)
            summary, rows, ece = run(df, cols, SELECT_FROM, SELECT_TO)
            rows.to_csv(OUT / f"select__{name}.csv", index=False)
            per_race[name] = rows
            results.append({"run": name, "inputs": len(cols), "window": window,
                            "races": summary["races"], "log_loss": summary["log_loss"],
                            "winner": summary["winner_hit_rate"],
                            "podium": summary["podium_rate"], "ece_win": ece})

    table = pd.DataFrame(results).sort_values("log_loss").reset_index(drop=True)
    _, bar_lo, bar_hi = M.bootstrap_ci(bar, "log_loss")
    common = set.intersection(*(set(r["raceId"]) for r in per_race.values()))
    print(f"\nSelection window {SELECT_FROM}-{SELECT_TO}, {len(common)} races in every run.")
    print(f"Bar ({BAR}): {bar['log_loss'].mean():.4f} [{bar_lo:.4f}, {bar_hi:.4f}] "
          f"over {len(bar)} races\n")
    for _, r in table.iterrows():
        vs_bar = M.paired_difference(per_race[r["run"]], bar, "log_loss")
        vs_inc = M.paired_difference(per_race[r["run"]], per_race[INCUMBENT], "log_loss")
        print(f"  {r['run']:<8} {r['inputs']:>2} inputs  log loss {r['log_loss']:.4f}  "
              f"winner {r['winner']:.1%}  podium {r['podium']:.1%}  ECE {r['ece_win']:.4f}  "
              f"vs bar {_fmt(vs_bar)}  vs P0-2018 {_fmt(vs_inc)}")

    chosen = table.iloc[0]
    incumbent_ece = float(table.loc[table["run"] == INCUMBENT, "ece_win"].iloc[0])
    guard = chosen["ece_win"] > 2 * incumbent_ece
    record = {"chosen": chosen["run"], "inputs": CANDIDATES[chosen["run"].split("-")[0]],
              "window": int(chosen["window"]), "log_loss": float(chosen["log_loss"]),
              "ece_win": float(chosen["ece_win"]), "incumbent_ece_win": incumbent_ece,
              "calibration_guard_tripped": bool(guard), "table": results}
    (OUT / "selection.json").write_text(json.dumps(record, indent=2) + "\n")
    print(f"\nSelected: {chosen['run']}"
          + ("  -- CALIBRATION GUARD TRIPPED: stop and report, do not freeze" if guard else ""))
    return 0


def holdout(name: str) -> int:
    """Score the frozen choice, the incumbent and the bar on 2026. Once."""
    record_path = OUT / "selection.json"
    if not record_path.exists():
        raise SystemExit("run `select` first")
    chosen = json.loads(record_path.read_text())["chosen"]
    if name != chosen:
        raise SystemExit(f"the protocol selected {chosen}, not {name}")
    done = OUT / "holdout.json"
    if done.exists():
        raise SystemExit(f"{done} exists: the holdout has been scored, and is scored once")

    tables = F.load_tables()
    bar = bar_scores(HOLDOUT_SEASON, HOLDOUT_SEASON)
    scored = {}
    for run_name in dict.fromkeys([name, INCUMBENT]):
        cid, window = run_name.split("-")
        df = dataset(int(window), HOLDOUT_SEASON, tables)
        summary, rows, ece = run(df, CANDIDATES[cid], HOLDOUT_SEASON, HOLDOUT_SEASON)
        scored[run_name] = {"summary": summary, "rows": rows, "ece": ece}

    out = {"season": HOLDOUT_SEASON, "bar": {"name": BAR, "races": len(bar)}}
    _, lo, hi = M.bootstrap_ci(bar, "log_loss")
    out["bar"].update(log_loss=float(bar["log_loss"].mean()), lo=lo, hi=hi)
    for run_name, s in scored.items():
        _, lo, hi = M.bootstrap_ci(s["rows"], "log_loss")
        out[run_name] = {"races": s["summary"]["races"], "log_loss": s["summary"]["log_loss"],
                         "lo": lo, "hi": hi, "winner": s["summary"]["winner_hit_rate"],
                         "podium": s["summary"]["podium_rate"], "ece_win": s["ece"],
                         "vs_bar": M.paired_difference(s["rows"], bar, "log_loss")}
    if name != INCUMBENT:
        out[name]["vs_incumbent"] = M.paired_difference(scored[name]["rows"],
                                                        scored[INCUMBENT]["rows"], "log_loss")
    done.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))
    return 0


def main() -> int:
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("select")
    h = sub.add_parser("holdout")
    h.add_argument("name")
    args = ap.parse_args()
    return select() if args.cmd == "select" else holdout(args.name)


if __name__ == "__main__":
    raise SystemExit(main())
