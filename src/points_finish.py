"""A points-finish chance that survives retirements, by MODEL_REPORT.md §12.

The protocol was committed before this script was run. For each of the three
shipped models it builds three candidate top-ten chances, walk-forward:

* T1, direct: the model's own estimator fitted on the top-ten target;
* T2, T1 rescaled so the field sums to the points places;
* T3, the published simulation with each car first retired at its published
  DNF chance;

selects the lowest 2019-2025 log loss per model under a calibration guard,
and scores the frozen choices on 2026 exactly once.

Usage:
    python src/points_finish.py select
    python src/points_finish.py holdout
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
import features as F  # noqa: E402
import model as M  # noqa: E402
import predict as P  # noqa: E402

OUT = M.ROOT / "data" / "features" / "runs" / "points_finish"
INSAMPLE = (2019, 2025)
HOLDOUT = (2026, 2026)
CANDIDATES = ("T1", "T2", "T3")
SPLINE_KNOTS = np.array([1, 2, 3, 5, 8, 12, 20], dtype=float)


# --------------------------------------------------------------- estimators
def _widen(df: pd.DataFrame, cols: list[str]) -> tuple[pd.DataFrame, list[str]]:
    """The qualifying spline basis, exactly as diagnose.SplineQuali builds it."""
    x = df[cols].astype(float).copy()
    pos = df["quali_position"].astype(float).fillna(20.0).clip(1, 22).to_numpy()
    x["q_log"] = np.log(pos)
    for i, k in enumerate(SPLINE_KNOTS[:-1]):
        x[f"q_h{i}"] = np.clip(pos - k, 0, None) ** 3
    x = x.drop(columns=["quali_position"])
    return x, list(x.columns)


def _logistic(xtr: pd.DataFrame, y: np.ndarray, xte: pd.DataFrame) -> np.ndarray:
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    pipe = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                         LogisticRegression(max_iter=1000, C=0.5))
    pipe.fit(xtr, y)
    return pipe.predict_proba(xte)[:, 1]


class Candidates:
    """The shipped win model, plus a direct top-ten fit and the published DNF fit."""

    name = "points-finish-candidates"

    def __init__(self, snapshot: str):
        self.snapshot = snapshot
        self.cols, self.estimator, _ = V.SPECS[snapshot]
        self.spline = "quali_position" in self.cols

    def fit_predict(self, train: pd.DataFrame, test: pd.DataFrame) -> dict[str, pd.Series]:
        ids = test["driverId"].to_numpy()
        out = self.estimator(list(self.cols)).fit_predict(train, test)
        if self.spline:
            xtr, _ = _widen(train, list(self.cols))
            xte, _ = _widen(test, list(self.cols))
        else:
            xtr, xte = train[list(self.cols)].astype(float), test[list(self.cols)].astype(float)
        out["top10"] = pd.Series(_logistic(xtr, train["top10"].to_numpy(), xte), index=ids)
        out["dnf"] = P._fit_dnf(train, test, list(self.cols))
        return out


# --------------------------------------------------------------- candidates
def sum_to_places(p: np.ndarray) -> np.ndarray:
    places = min(10, len(p))
    q = p * places / p.sum()
    return np.clip(q, 1e-6, 1 - 1e-6)


def simulate_with_retirements(p_win: np.ndarray, p_dnf: np.ndarray,
                              draws: int = P.MC_DRAWS) -> np.ndarray:
    """Top ten among the cars that finish, in the published simulation's order."""
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
    return ((rank < min(10, n)) & ~retired).mean(axis=0)


def evaluate(snapshot: str, window: tuple[int, int]) -> pd.DataFrame:
    """Per driver: the three candidates, the reference, the rule and the outcome."""
    _, _, pos_col = V.SPECS[snapshot]
    df = V.frame(snapshot, window[1])
    preds = M.walk_forward(df, Candidates(snapshot), snapshot, eval_from=window[0], verbose=False)
    wide = preds.pivot_table(index=["raceId", "driverId"], columns="target", values="p").reset_index()
    rule = V.PositionRate(10)
    rows = []
    for _, race in df.groupby("order", sort=True):
        year = int(race["year"].iloc[0])
        rid = int(race["raceId"].iloc[0])
        got = wide[wide["raceId"] == rid]
        if window[0] <= year <= window[1] and len(got) >= 5:
            r = race.merge(got, on=["raceId", "driverId"], suffixes=("", "_p"))
            ref = V.simulate(r.assign(p_win=r["win_p"]))["p_top10"].to_numpy()
            t1 = r["top10_p"].to_numpy(dtype=float)
            t3 = simulate_with_retirements(r["win_p"].to_numpy(dtype=float),
                                           r["dnf_p"].to_numpy(dtype=float))
            for i, (_, d) in enumerate(r.iterrows()):
                rows.append({"raceId": rid, "year": year, "driverId": int(d["driverId"]),
                             "y": int(d["top10"]), "ref": ref[i], "T1": t1[i],
                             "T2": sum_to_places(t1)[i], "T3": t3[i],
                             "rule": rule.predict(d[pos_col])})
        for _, d in race.iterrows():
            rule.observe(d[pos_col], int(d["top10"]))
    return pd.DataFrame(rows)


def score(d: pd.DataFrame, col: str) -> tuple[pd.DataFrame, float]:
    y = d["y"].to_numpy(dtype=float)
    p = d[col].to_numpy(dtype=float)
    per_race = (d[["raceId"]].assign(log_loss=V._ll(p, y), brier=(p - y) ** 2)
                .groupby("raceId", as_index=False)[["log_loss", "brier"]].mean())
    _, ece = M.calibration(pd.DataFrame({"target": "t", "p": p, "y": y}), "t")
    return per_race, ece


def _fmt(d: dict) -> str:
    return (f"{d['mean_difference']:+.4f} [{d['lo']:+.4f}, {d['hi']:+.4f}]"
            f"{' significant' if d['significant'] else ''}")


# ---------------------------------------------------------------- commands
def select() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    record = {}
    for snapshot in V.SPECS:
        print(f"  {snapshot} ...", flush=True)
        d = evaluate(snapshot, INSAMPLE)
        assert d["year"].max() <= INSAMPLE[1], "a 2026 row reached the selection"
        rule_rows, rule_ece = score(d, "rule")
        res = {}
        for c in ("ref",) + CANDIDATES:
            rows, ece = score(d, c)
            res[c] = {"log_loss": float(rows["log_loss"].mean()), "brier": float(rows["brier"].mean()),
                      "ece": ece, "vs_rule": M.paired_difference(rows, rule_rows, "log_loss")}
        chosen = min(CANDIDATES, key=lambda c: res[c]["log_loss"])
        guard = res[chosen]["ece"] > 2 * rule_ece
        record[snapshot] = {"races": int(d["raceId"].nunique()), "rule_log_loss": float(rule_rows["log_loss"].mean()),
                            "rule_ece": rule_ece, "results": res, "chosen": chosen,
                            "calibration_guard_tripped": bool(guard)}
        print(f"\n{snapshot}: {d['raceId'].nunique()} races, rule {rule_rows['log_loss'].mean():.4f} "
              f"(ECE {rule_ece:.4f})")
        for c in ("ref",) + CANDIDATES:
            r = res[c]
            print(f"  {c:<4} log loss {r['log_loss']:.4f}  Brier {r['brier']:.4f}  ECE {r['ece']:.4f}  "
                  f"vs rule {_fmt(r['vs_rule'])}")
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
        rule_rows, rule_ece = score(d, "rule")
        rows, ece = score(d, chosen)
        ref_rows, ref_ece = score(d, "ref")
        out[snapshot] = {"chosen": chosen, "races": int(d["raceId"].nunique()),
                         "chosen_log_loss": float(rows["log_loss"].mean()), "chosen_ece": ece,
                         "rule_log_loss": float(rule_rows["log_loss"].mean()), "rule_ece": rule_ece,
                         "ref_log_loss": float(ref_rows["log_loss"].mean()), "ref_ece": ref_ece,
                         "vs_rule": M.paired_difference(rows, rule_rows, "log_loss")}
        o = out[snapshot]
        print(f"{snapshot}: {chosen} {o['chosen_log_loss']:.4f} (ECE {ece:.4f})  rule {o['rule_log_loss']:.4f}  "
              f"reference {o['ref_log_loss']:.4f}  vs rule {_fmt(o['vs_rule'])}")
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
