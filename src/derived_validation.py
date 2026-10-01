"""Test the top-ten, podium and teammate chances, by MODEL_REPORT.md §11.

The protocol was committed before this script was run. Nothing is selected:
each of the three shipped models is run walk-forward exactly as published,
its win chances are simulated exactly as predict.py simulates them, and the
chances that come out are scored against simple positional rules.

Usage:
    python src/derived_validation.py insample     # 2019-2025
    python src/derived_validation.py holdout      # 2026, once
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

import diagnose as D  # noqa: E402
import features as F  # noqa: E402
import model as M  # noqa: E402
import predict as P  # noqa: E402

OUT = M.ROOT / "data" / "features" / "runs" / "derived_validation"
INSAMPLE = (2019, 2025)
HOLDOUT = (2026, 2026)
EPS = 1e-6
ALPHA = 1.0

# snapshot -> (frame, shipped inputs, estimator, the position the rule reads)
SPECS = {
    F.PRE: (P.PRE_WEEKEND_COLS, D.Slim, "driver_standing_position"),
    F.PRACTICE: (P.PRACTICE_COLS, D.Slim, "driver_standing_position"),
    F.POST: (P.SHIPPED, D.SplineQuali, "quali_position"),
}
QUANTITIES = ("top10", "podium", "teammate")


# ------------------------------------------------------------ the simulation
def simulate(race: pd.DataFrame) -> pd.DataFrame:
    """Top-ten and podium chances for one race, exactly as predict.py makes them."""
    ids = race["driverId"].astype(int).to_numpy()
    p_win = np.clip(race["p_win"].to_numpy(dtype=float), 1e-9, None)
    p_win = p_win / p_win.sum()
    dist = P.plackett_luce(p_win)
    n = len(ids)
    return pd.DataFrame({"driverId": ids, "p_win_norm": p_win,
                         "p_top10": dist[:, :min(10, n)].sum(axis=1),
                         "p_podium": dist[:, :min(3, n)].sum(axis=1)})


def pairs(race: pd.DataFrame) -> list[tuple[int, int]]:
    """Teammate pairs among the race's rows, each once, lower driverId first."""
    out = []
    for _, g in race.groupby("team_entity_id"):
        if len(g) == 2:
            a, b = sorted(g["driverId"].astype(int))
            out.append((a, b))
    return out


# ------------------------------------------------------------------ the rules
class PositionRate:
    """P(target | position), learned walk-forward, smoothed like §1's priors:
    (hits + alpha * k) / (seen + alpha * 20), so an unseen position sits at the
    field's share k/20."""

    def __init__(self, k: int):
        self.k, self.hits, self.seen = k, {}, {}

    def predict(self, pos) -> float:
        if pd.isna(pos) or pos <= 0:
            return self.k / 20
        p = int(pos)
        return (self.hits.get(p, 0.0) + ALPHA * self.k) / (self.seen.get(p, 0.0) + ALPHA * 20)

    def observe(self, pos, hit: int) -> None:
        if pd.isna(pos) or pos <= 0:
            return
        p = int(pos)
        self.seen[p] = self.seen.get(p, 0.0) + 1
        self.hits[p] = self.hits.get(p, 0.0) + hit


class TeammateRate:
    """The rate at which the better-ranked teammate finished ahead."""

    def __init__(self):
        self.ahead, self.n = 0.0, 0.0

    def rate(self) -> float:
        return (self.ahead + 1) / (self.n + 2)

    def predict(self, pa, pb) -> float:
        """Chance that a finishes ahead of b."""
        if pd.isna(pa) or pd.isna(pb) or pa == pb:
            return 0.5
        return self.rate() if pa < pb else 1 - self.rate()

    def observe(self, pa, pb, a_ahead: int) -> None:
        if pd.isna(pa) or pd.isna(pb) or pa == pb:
            return
        self.n += 1
        self.ahead += a_ahead if pa < pb else 1 - a_ahead


# ----------------------------------------------------------------- scoring
def _ll(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    p = np.clip(p, EPS, 1 - EPS)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def frame(snapshot: str, through: int) -> pd.DataFrame:
    df = M.dataset(snapshot)
    df = df[df["year"] <= through].copy()
    teams = F._rd(F.PROCESSED / "results.csv")[["raceId", "driverId", "team_entity_id"]]
    return df.merge(teams, on=["raceId", "driverId"], how="left")


def evaluate(snapshot: str, window: tuple[int, int]) -> dict:
    """Model chances and rule chances, per driver and per pair, for every race
    in the window, plus the per-race scores the bootstrap resamples."""
    cols, estimator, pos_col = SPECS[snapshot]
    df = frame(snapshot, window[1])
    preds = M.walk_forward(df, estimator(list(cols)), snapshot, eval_from=window[0], verbose=False)
    win = preds[preds["target"] == "win"][["raceId", "driverId", "p"]].rename(columns={"p": "p_win"})

    rules = {"top10": PositionRate(10), "podium": PositionRate(3)}
    mate = TeammateRate()
    rows, pair_rows = [], []
    for rid, race in df.groupby("order", sort=True):
        race = race.copy()
        year = int(race["year"].iloc[0])
        in_window = window[0] <= year <= window[1]
        r_id = int(race["raceId"].iloc[0])
        got = win[win["raceId"] == r_id]
        if in_window and len(got) >= 5:
            race_p = race.merge(got[["driverId", "p_win"]], on="driverId")
            sim = simulate(race_p).merge(race_p[["driverId", pos_col, "top10", "podium"]],
                                         on="driverId")
            for _, r in sim.iterrows():
                rows.append({"raceId": r_id, "year": year, "driverId": int(r["driverId"]),
                             "m_top10": r["p_top10"], "m_podium": r["p_podium"],
                             "r_top10": rules["top10"].predict(r[pos_col]),
                             "r_podium": rules["podium"].predict(r[pos_col]),
                             "y_top10": int(r["top10"]), "y_podium": int(r["podium"])})
            pw = dict(zip(sim["driverId"], sim["p_win_norm"]))
            pos = dict(zip(race["driverId"].astype(int), race[pos_col]))
            fin = dict(zip(race["driverId"].astype(int), race["finish_order"]))
            for a, b in pairs(race_p):
                pair_rows.append({"raceId": r_id, "year": year, "a": a, "b": b,
                                  "m_teammate": pw[a] / (pw[a] + pw[b]),
                                  "r_teammate": mate.predict(pos[a], pos[b]),
                                  "y_teammate": int(fin[a] < fin[b])})
        # Learn only after predicting, from every race the frame holds.
        for _, r in race.iterrows():
            rules["top10"].observe(r[pos_col], int(r["top10"]))
            rules["podium"].observe(r[pos_col], int(r["podium"]))
        fin = dict(zip(race["driverId"].astype(int), race["finish_order"]))
        pos = dict(zip(race["driverId"].astype(int), race[pos_col]))
        for a, b in pairs(race):
            mate.observe(pos[a], pos[b], int(fin[a] < fin[b]))
    return {"drivers": pd.DataFrame(rows), "pairs": pd.DataFrame(pair_rows)}


def summarise(snapshot: str, ev: dict) -> dict:
    out = {}
    for q in QUANTITIES:
        d = ev["pairs"] if q == "teammate" else ev["drivers"]
        y = d[f"y_{q}"].to_numpy(dtype=float)
        per_race = {}
        for who in ("m", "r"):
            p = d[f"{who}_{q}"].to_numpy(dtype=float)
            t = d[["raceId"]].assign(log_loss=_ll(p, y), brier=(p - y) ** 2)
            per_race[who] = t.groupby("raceId", as_index=False)[["log_loss", "brier"]].mean()
        cal = pd.DataFrame({"target": q, "p": d[f"m_{q}"], "y": y})
        _, ece = M.calibration(cal, q)
        diff = M.paired_difference(per_race["m"], per_race["r"], "log_loss")
        out[q] = {"races": int(per_race["m"]["raceId"].nunique()), "rows": int(len(d)),
                  "model_log_loss": float(per_race["m"]["log_loss"].mean()),
                  "rule_log_loss": float(per_race["r"]["log_loss"].mean()),
                  "model_brier": float(per_race["m"]["brier"].mean()),
                  "rule_brier": float(per_race["r"]["brier"].mean()),
                  "ece": ece, "vs_rule": diff}
    return out


def _print(results: dict, label: str) -> None:
    print(f"\n{label}")
    for snapshot, res in results.items():
        for q, r in res.items():
            d = r["vs_rule"]
            print(f"  {snapshot:<16} {q:<9} races {r['races']:>3}  model {r['model_log_loss']:.4f}  "
                  f"rule {r['rule_log_loss']:.4f}  diff {d['mean_difference']:+.4f} "
                  f"[{d['lo']:+.4f}, {d['hi']:+.4f}]{' significant' if d['significant'] else ''}  "
                  f"Brier {r['model_brier']:.4f} vs {r['rule_brier']:.4f}  ECE {r['ece']:.4f}")


def run(which: str) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    window = INSAMPLE if which == "insample" else HOLDOUT
    path = OUT / f"{which}.json"
    if which == "holdout":
        if not (OUT / "insample.json").exists():
            raise SystemExit("run `insample` first")
        if path.exists():
            raise SystemExit(f"{path} exists: the holdout has been scored, and is scored once")
    results = {}
    for snapshot in SPECS:
        print(f"  {snapshot} ...", flush=True)
        results[snapshot] = summarise(snapshot, evaluate(snapshot, window))
    path.write_text(json.dumps(results, indent=2) + "\n")
    _print(results, f"{which}: {window[0]}-{window[1]}")
    return 0


def main() -> int:
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("which", choices=["insample", "holdout"])
    return run(ap.parse_args().which)


if __name__ == "__main__":
    raise SystemExit(main())
