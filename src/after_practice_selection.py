"""Select the after-practice model, by the protocol in MODEL_REPORT.md §10.

The protocol was committed before this script was run. It carries it out:

* six candidates (Q0-Q5), the same regularised logistic, rows from 2018;
* a walk-forward over 2019-2025 only, on a frame truncated at the end of 2025;
* two bars, championship order and practice order, scored on the same races;
  the site's bar is whichever of the two scores better;
* the lowest mean race-level win log loss is selected, under a calibration
  guard against Q0;
* the frozen choice, Q0 and both bars are scored on 2026 exactly once.

Usage:
    python src/after_practice_selection.py select
    python src/after_practice_selection.py holdout Q2

`holdout` refuses to run twice.
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
import pre_weekend_selection as PW  # noqa: E402

OUT = M.ROOT / "data" / "features" / "runs" / "after_practice_selection"
SELECT_FROM, SELECT_TO = 2019, 2025
HOLDOUT_SEASON = 2026

P4 = list(PW.CANDIDATES["P4"])
BEST_LAP = ["practice_best_lap_gap_ms"]
LONG_RUN = ["practice_long_run_pace_gap_ms", "practice_long_run_laps"]
TYRE = ["practice_compounds_run", "practice_softest_long_run_gap_ms"]

CANDIDATES: dict[str, list[str]] = {
    "Q0": P4,
    "Q1": P4 + BEST_LAP,
    "Q2": P4 + BEST_LAP + LONG_RUN,
    "Q3": P4 + BEST_LAP + LONG_RUN + ["practice_laps"],
    "Q4": P4 + BEST_LAP + LONG_RUN + ["practice_laps"] + TYRE,
    "Q5": list(PW.STANDINGS) + BEST_LAP + ["practice_long_run_pace_gap_ms"],
}
REFERENCE = "Q0"
BARS = ("championship order", "practice order")


def dataset(through: int) -> pd.DataFrame:
    df = M.dataset(F.PRACTICE)
    return df[df["year"] <= through].reset_index(drop=True)


# ------------------------------------------------------------------- bars
def championship_order(eval_from: int, eval_to: int) -> pd.DataFrame:
    _, extra = B.run(eval_from=eval_from)
    rows = pd.DataFrame(extra["scores"]["championship order"]._rows)
    races = pd.read_csv(F.PROCESSED / "races.csv")[["raceId", "year"]]
    rows = rows.merge(races, on="raceId")
    return rows[(rows["year"] >= eval_from) & (rows["year"] <= eval_to)]


def practice_order(eval_from: int, eval_to: int) -> pd.DataFrame:
    """P(win | best-lap rank in the after-practice field), walk-forward.

    Learns from every race with practice data, in order, and predicts the
    starters of each race in the window before observing it -- the same
    discipline as the positional baselines in §1. A starter with no practice
    time has no rank and takes the smoothed rate for an unseen position.
    """
    frame = M.feature_frame(F.PRACTICE)[["raceId", "driverId", "practice_best_lap_gap_ms"]]
    frame["practice_rank"] = frame.groupby("raceId")["practice_best_lap_gap_ms"].rank(method="min")
    races = pd.read_csv(F.PROCESSED / "races.csv")
    races["order"] = races["year"] * 100 + races["round"]
    res = pd.read_csv(F.PROCESSED / "results.csv")
    started = res[res["positionText"].astype(str) != "W"]
    started = started.merge(frame[["raceId", "driverId", "practice_rank"]],
                            on=["raceId", "driverId"], how="left")
    prior = B.PositionPrior("practice_rank")
    score = B.Score()
    for _, race in races[races["raceId"].isin(frame["raceId"])].sort_values("order").iterrows():
        g = (started[started["raceId"] == race["raceId"]]
             .sort_values(["driverId", "positionOrder"]).drop_duplicates("driverId"))
        won = g[g["positionText"].astype(str) == "1"]
        if len(g) >= 5 and len(won) and eval_from <= race["year"] <= eval_to:
            pos = pd.to_numeric(g["positionOrder"], errors="coerce")
            score.add(prior.predict(g), int(won.iloc[0]["driverId"]),
                      set(g.loc[pos <= 3, "driverId"].astype(int)), int(race["raceId"]))
        prior.observe(g)
    rows = pd.DataFrame(score._rows)
    return rows.merge(races[["raceId", "year"]], on="raceId")


def bars(eval_from: int, eval_to: int) -> dict[str, pd.DataFrame]:
    return {"championship order": championship_order(eval_from, eval_to),
            "practice order": practice_order(eval_from, eval_to)}


def _fmt(d: dict) -> str:
    return (f"{d['mean_difference']:+.4f} [{d['lo']:+.4f}, {d['hi']:+.4f}]"
            f"{' significant' if d['significant'] else ''}")


# --------------------------------------------------------------- commands
def select() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    df = dataset(SELECT_TO)
    assert df["year"].max() <= SELECT_TO, "a 2026 row reached the selection frame"
    bar = bars(SELECT_FROM, SELECT_TO)
    results, per_race = [], {}
    for cid, cols in CANDIDATES.items():
        print(f"  {cid}: {len(cols)} inputs ...", flush=True)
        summary, rows, ece = PW.run(df, cols, SELECT_FROM, SELECT_TO)
        rows.to_csv(OUT / f"select__{cid}.csv", index=False)
        per_race[cid] = rows
        results.append({"run": cid, "inputs": len(cols), "races": summary["races"],
                        "log_loss": summary["log_loss"], "winner": summary["winner_hit_rate"],
                        "podium": summary["podium_rate"], "ece_win": ece})

    print(f"\nSelection window {SELECT_FROM}-{SELECT_TO}.")
    for name, rows in bar.items():
        _, lo, hi = M.bootstrap_ci(rows, "log_loss")
        print(f"Bar, {name}: {rows['log_loss'].mean():.4f} [{lo:.4f}, {hi:.4f}] over {len(rows)} races")
    common = set.intersection(*(set(r["raceId"]) for r in per_race.values()))
    means = {n: r[r["raceId"].isin(common)]["log_loss"].mean() for n, r in bar.items()}
    site_bar = min(means, key=means.get)
    print(f"On the {len(common)} races every candidate scored: "
          + ", ".join(f"{n} {v:.4f}" for n, v in means.items()) + f". Site bar: {site_bar}.\n")

    table = pd.DataFrame(results).sort_values("log_loss").reset_index(drop=True)
    for _, r in table.iterrows():
        print(f"  {r['run']:<3} {r['inputs']:>2} inputs  log loss {r['log_loss']:.4f}  "
              f"winner {r['winner']:.1%}  podium {r['podium']:.1%}  ECE {r['ece_win']:.4f}  "
              f"vs {site_bar} {_fmt(M.paired_difference(per_race[r['run']], bar[site_bar], 'log_loss'))}  "
              f"vs Q0 {_fmt(M.paired_difference(per_race[r['run']], per_race[REFERENCE], 'log_loss'))}")

    chosen = table.iloc[0]
    ref_ece = float(table.loc[table["run"] == REFERENCE, "ece_win"].iloc[0])
    guard = chosen["ece_win"] > 2 * ref_ece
    (OUT / "selection.json").write_text(json.dumps({
        "chosen": chosen["run"], "inputs": CANDIDATES[chosen["run"]], "site_bar": site_bar,
        "log_loss": float(chosen["log_loss"]), "ece_win": float(chosen["ece_win"]),
        "reference_ece_win": ref_ece, "calibration_guard_tripped": bool(guard),
        "table": results}, indent=2) + "\n")
    print(f"\nSelected: {chosen['run']}"
          + ("  -- CALIBRATION GUARD TRIPPED: stop and report, do not freeze" if guard else ""))
    return 0


def holdout(name: str) -> int:
    record = OUT / "selection.json"
    if not record.exists():
        raise SystemExit("run `select` first")
    sel = json.loads(record.read_text())
    if name != sel["chosen"]:
        raise SystemExit(f"the protocol selected {sel['chosen']}, not {name}")
    done = OUT / "holdout.json"
    if done.exists():
        raise SystemExit(f"{done} exists: the holdout has been scored, and is scored once")

    df = dataset(HOLDOUT_SEASON)
    bar = bars(HOLDOUT_SEASON, HOLDOUT_SEASON)
    out = {"season": HOLDOUT_SEASON, "site_bar": sel["site_bar"]}
    for n, rows in bar.items():
        _, lo, hi = M.bootstrap_ci(rows, "log_loss")
        out[n] = {"races": len(rows), "log_loss": float(rows["log_loss"].mean()), "lo": lo, "hi": hi}
    scored = {}
    for cid in dict.fromkeys([name, REFERENCE]):
        summary, rows, ece = PW.run(df, CANDIDATES[cid], HOLDOUT_SEASON, HOLDOUT_SEASON)
        _, lo, hi = M.bootstrap_ci(rows, "log_loss")
        scored[cid] = rows
        out[cid] = {"races": summary["races"], "log_loss": summary["log_loss"], "lo": lo, "hi": hi,
                    "winner": summary["winner_hit_rate"], "podium": summary["podium_rate"],
                    "ece_win": ece,
                    **{f"vs {n}": M.paired_difference(rows, b, "log_loss") for n, b in bar.items()}}
    if name != REFERENCE:
        out[name]["vs Q0"] = M.paired_difference(scored[name], scored[REFERENCE], "log_loss")
    done.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))
    return 0


def main() -> int:
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("select")
    sub.add_parser("holdout").add_argument("name")
    args = ap.parse_args()
    return select() if args.cmd == "select" else holdout(args.name)


if __name__ == "__main__":
    raise SystemExit(main())
