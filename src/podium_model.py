"""A podium chance that agrees with the points chance, by MODEL_REPORT.md §13.

The protocol was committed before this script was run. For each of the three
shipped models it builds four candidate podium chances, walk-forward:

* U1, direct: the model's own podium output;
* U2, U1 rescaled so the field sums to the podium places;
* U3, the published simulation with each car first retired at its DNF chance;
* U4, U1 kept between the published win chance and the points chance;

selects the lowest 2019-2025 log loss per model under a calibration guard,
reports how often each candidate contradicts the win or points chance, and
scores the frozen choices on 2026 exactly once.

Usage:
    python src/podium_model.py select
    python src/podium_model.py holdout
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import derived_validation as V  # noqa: E402
import model as M  # noqa: E402
import points_finish as PF  # noqa: E402
import predict as P  # noqa: E402

OUT = M.ROOT / "data" / "features" / "runs" / "podium_model"
INSAMPLE = (2019, 2025)
HOLDOUT = (2026, 2026)
CANDIDATES = ("U1", "U2", "U3", "U4")
PLACES = 3


def sum_to_places(p: np.ndarray, places: int = PLACES) -> np.ndarray:
    k = min(places, len(p))
    return np.clip(p * k / p.sum(), 1e-6, 1 - 1e-6)


def simulate_with_retirements(p_win: np.ndarray, p_dnf: np.ndarray, places: int = PLACES,
                              draws: int = P.MC_DRAWS) -> np.ndarray:
    """Top `places` among the cars that finish, in the published simulation's order."""
    rng = np.random.default_rng(P.RNG_SEED)
    w = np.clip(p_win, 1e-9, None)
    z = np.log(w / w.sum())
    n = len(z)
    keys = z[None, :] + rng.gumbel(size=(draws, n))
    retired = rng.random((draws, n)) < np.clip(p_dnf, 0.0, 1.0)[None, :]
    keys = np.where(retired, -np.inf, keys)
    order = np.argsort(-keys, axis=1)
    rank = np.empty_like(order)
    rank[np.arange(draws)[:, None], order] = np.arange(n)[None, :]
    return ((rank < min(places, n)) & ~retired).mean(axis=0)


def evaluate(snapshot: str, window: tuple[int, int]) -> pd.DataFrame:
    """Per driver: the four candidates, the reference, the rule, the bounds and the outcome."""
    _, _, pos_col = V.SPECS[snapshot]
    df = V.frame(snapshot, window[1])
    # PF.Candidates returns the shipped estimator's win and podium, the direct
    # top-ten fit (the points chance) and the published DNF fit.
    preds = M.walk_forward(df, PF.Candidates(snapshot), snapshot, eval_from=window[0], verbose=False)
    wide = preds.pivot_table(index=["raceId", "driverId"], columns="target", values="p").reset_index()
    rule = V.PositionRate(PLACES)
    rows = []
    for _, race in df.groupby("order", sort=True):
        year = int(race["year"].iloc[0])
        rid = int(race["raceId"].iloc[0])
        got = wide[wide["raceId"] == rid]
        if window[0] <= year <= window[1] and len(got) >= 5:
            r = race.merge(got, on=["raceId", "driverId"], suffixes=("", "_p"))
            sim = V.simulate(r.assign(p_win=r["win_p"]))
            win = sim["p_win_norm"].to_numpy()
            ref = sim["p_podium"].to_numpy()
            u1 = r["podium_p"].to_numpy(dtype=float)
            points = r["top10_p"].to_numpy(dtype=float)
            u2 = sum_to_places(u1)
            u3 = simulate_with_retirements(r["win_p"].to_numpy(dtype=float),
                                           r["dnf_p"].to_numpy(dtype=float))
            u4 = np.minimum(np.maximum(u1, win), points)
            for i, (_, d) in enumerate(r.iterrows()):
                rows.append({"raceId": rid, "year": year, "driverId": int(d["driverId"]),
                             "y": int(d["podium"]), "ref": ref[i], "U1": u1[i], "U2": u2[i],
                             "U3": u3[i], "U4": u4[i], "win": win[i], "points": points[i],
                             "rule": rule.predict(d[pos_col])})
        for _, d in race.iterrows():
            rule.observe(d[pos_col], int(d["podium"]))
    return pd.DataFrame(rows)


def coherence(d: pd.DataFrame, col: str) -> dict:
    """Shares of driver-races where the podium chance contradicts its neighbours."""
    return {"above_points": float((d[col] > d["points"] + 1e-9).mean()),
            "below_win": float((d[col] < d["win"] - 1e-9).mean())}


def _fmt(d: dict) -> str:
    return (f"{d['mean_difference']:+.4f} [{d['lo']:+.4f}, {d['hi']:+.4f}]"
            f"{' significant' if d['significant'] else ''}")


def select() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    record = {}
    for snapshot in V.SPECS:
        print(f"  {snapshot} ...", flush=True)
        d = evaluate(snapshot, INSAMPLE)
        assert d["year"].max() <= INSAMPLE[1], "a 2026 row reached the selection"
        rule_rows, rule_ece = PF.score(d, "rule")
        res = {}
        for c in ("ref",) + CANDIDATES:
            rows, ece = PF.score(d, c)
            res[c] = {"log_loss": float(rows["log_loss"].mean()), "brier": float(rows["brier"].mean()),
                      "ece": ece, "vs_rule": M.paired_difference(rows, rule_rows, "log_loss"),
                      **coherence(d, c)}
        chosen = min(CANDIDATES, key=lambda c: res[c]["log_loss"])
        guard = res[chosen]["ece"] > 2 * rule_ece
        record[snapshot] = {"races": int(d["raceId"].nunique()),
                            "rule_log_loss": float(rule_rows["log_loss"].mean()), "rule_ece": rule_ece,
                            "results": res, "chosen": chosen, "calibration_guard_tripped": bool(guard)}
        print(f"\n{snapshot}: {d['raceId'].nunique()} races, rule {rule_rows['log_loss'].mean():.4f} "
              f"(ECE {rule_ece:.4f})")
        for c in ("ref",) + CANDIDATES:
            r = res[c]
            print(f"  {c:<4} log loss {r['log_loss']:.4f}  Brier {r['brier']:.4f}  ECE {r['ece']:.4f}  "
                  f"vs rule {_fmt(r['vs_rule'])}  above points {r['above_points']:.1%}  "
                  f"below win {r['below_win']:.1%}")
        print(f"  selected {chosen}" + ("  -- CALIBRATION GUARD TRIPPED" if guard else ""))
    (OUT / "selection.json").write_text(json.dumps(record, indent=2) + "\n")
    return 0


def holdout() -> int:
    sel_path, done = OUT / "selection.json", OUT / "holdout.json"
    if not sel_path.exists():
        raise SystemExit("run `select` first")
    if done.exists():
        raise SystemExit(f"{done} exists: the holdout has been scored, and is scored once")
    sel = json.loads(sel_path.read_text())
    out = {}
    for snapshot in V.SPECS:
        chosen = sel[snapshot]["chosen"]
        d = evaluate(snapshot, HOLDOUT)
        rule_rows, rule_ece = PF.score(d, "rule")
        rows, ece = PF.score(d, chosen)
        ref_rows, _ = PF.score(d, "ref")
        out[snapshot] = {"chosen": chosen, "races": int(d["raceId"].nunique()),
                         "chosen_log_loss": float(rows["log_loss"].mean()), "chosen_ece": ece,
                         "rule_log_loss": float(rule_rows["log_loss"].mean()), "rule_ece": rule_ece,
                         "ref_log_loss": float(ref_rows["log_loss"].mean()),
                         "vs_rule": M.paired_difference(rows, rule_rows, "log_loss"),
                         **coherence(d, chosen)}
        o = out[snapshot]
        print(f"{snapshot}: {chosen} {o['chosen_log_loss']:.4f} (ECE {ece:.4f})  rule {o['rule_log_loss']:.4f}  "
              f"reference {o['ref_log_loss']:.4f}  vs rule {_fmt(o['vs_rule'])}  "
              f"above points {o['above_points']:.1%}  below win {o['below_win']:.1%}")
    done.write_text(json.dumps(out, indent=2) + "\n")
    return 0


def main() -> int:
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("which", choices=["select", "holdout"])
    return select() if ap.parse_args().which == "select" else holdout()


if __name__ == "__main__":
    raise SystemExit(main())
