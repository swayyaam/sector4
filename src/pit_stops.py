"""Pit stop counts, by the protocol in MODEL_REPORT.md §14.

The protocol was committed before this script was run. Each classified
finisher's official stop count falls in one of three classes: one or none,
two, three or more. Four candidates are scored at two information levels
against two simple rules, walk-forward, on 2019-2025; the frozen choices are
scored on 2026 exactly once.

Every input is built from races strictly before the one predicted, except
the position, which is known at the snapshot.

Usage:
    python src/pit_stops.py select
    python src/pit_stops.py holdout
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

import features as F  # noqa: E402
import model as M  # noqa: E402

OUT = M.ROOT / "data" / "features" / "runs" / "pit_stops"
FIRST_PIT_SEASON, FIRST_ROW_SEASON = 2011, 2014
INSAMPLE, HOLDOUT = (2019, 2025), (2026, 2026)
K = 3                       # one or none, two, three or more
EPS = 1e-6

CIRCUIT = ["circuit_le1", "circuit_two", "circuit_three"]
SEASON = ["season_le1", "season_two", "season_three"]
CANDIDATES = {
    "W1": CIRCUIT,
    "W2": CIRCUIT + SEASON,
    "W3": CIRCUIT + SEASON + ["position"],
    "W4": CIRCUIT + SEASON + ["position", "team_mean_stops"],
}
LEVELS = {"before_qualifying": "standing_position", "after_qualifying": "quali_position"}


def stop_class(n: int) -> int:
    return 0 if n <= 1 else (1 if n == 2 else 2)


def shares(counts: np.ndarray) -> np.ndarray:
    total = counts.sum()
    return counts / total if total else np.full(K, np.nan)


def smoothed(counts: np.ndarray) -> np.ndarray:
    """Add-one: every class keeps some chance, however one-sided the history."""
    c = counts + 1.0
    return c / c.sum()


# -------------------------------------------------------------------- frame
def build(tables: dict | None = None) -> pd.DataFrame:
    """One row per classified finisher of every race with pit data from 2014,
    with its inputs, both rules' chances and its class."""
    t = tables if tables is not None else F.load_tables()
    races = t["races"].copy()
    ps = F._rd(F.PROCESSED / "pit_stops.csv")
    ps = ps[ps["counts_as_official_stop"].astype(str).str.lower().isin(["true", "1"])]
    covered = set(ps["raceId"])
    races = races[races["raceId"].isin(covered) & (races["year"] >= FIRST_PIT_SEASON)]
    races = races.sort_values("order").reset_index(drop=True)

    res = t["results"]
    fin = res[pd.to_numeric(res["positionText"], errors="coerce").notna()]
    fin = fin[fin["raceId"].isin(covered)][["raceId", "driverId", "team_entity_id"]].copy()
    stops = ps.groupby(["raceId", "driverId"]).size().rename("stops")
    fin = fin.merge(stops, on=["raceId", "driverId"], how="left").fillna({"stops": 0})
    fin["stops"] = fin["stops"].astype(int)
    fin["cls"] = fin["stops"].map(stop_class)
    fin = fin.merge(races[["raceId", "year", "order", "circuitId"]], on="raceId")

    per_race = {rid: np.bincount(g["cls"], minlength=K).astype(float)
                for rid, g in fin.groupby("raceId")}
    team_race = fin.groupby(["raceId", "team_entity_id"])["stops"].agg(["sum", "count"])

    # Standings entering the race: the previous round of the same season.
    st = t["driver_standings"][["raceId", "driverId", "position"]].rename(
        columns={"position": "standing_position"})
    allr = t["races"].sort_values("order")
    prev = allr[["raceId", "year"]].copy()
    prev["prev_raceId"] = allr.groupby("year")["raceId"].shift(1)
    q = t["qualifying"][["raceId", "driverId", "position"]].rename(columns={"position": "quali_position"})

    rows = []
    for _, r in races.iterrows():
        if r["year"] < FIRST_ROW_SEASON:
            continue
        before = races[races["order"] < r["order"]]
        here = before[before["circuitId"] == r["circuitId"]].tail(3)
        season = before[before["year"] == r["year"]]
        last_season = races[races["year"] == r["year"] - 1]
        c_counts = sum((per_race[i] for i in here["raceId"]), np.zeros(K))
        s_counts = sum((per_race[i] for i in season["raceId"]), np.zeros(K))
        l_counts = sum((per_race[i] for i in last_season["raceId"]), np.zeros(K))
        season_rule = smoothed(s_counts) if s_counts.sum() else smoothed(l_counts)
        circuit_rule = smoothed(c_counts) if c_counts.sum() else season_rule

        g = fin[fin["raceId"] == r["raceId"]]
        tr = team_race[team_race.index.get_level_values(0).isin(season["raceId"])]
        tr = tr.groupby(level=1).sum()
        team_mean = (tr["sum"] / tr["count"]).to_dict()
        cs, ss = shares(c_counts), shares(s_counts)
        for _, d in g.iterrows():
            rows.append({"raceId": int(r["raceId"]), "year": int(r["year"]), "order": int(r["order"]),
                         "driverId": int(d["driverId"]), "cls": int(d["cls"]),
                         **dict(zip(CIRCUIT, cs)), **dict(zip(SEASON, ss)),
                         "team_mean_stops": team_mean.get(d["team_entity_id"], np.nan),
                         **{f"rule_circuit_{k}": circuit_rule[k] for k in range(K)},
                         **{f"rule_season_{k}": season_rule[k] for k in range(K)}})
    df = pd.DataFrame(rows)
    df = df.merge(prev[["raceId", "prev_raceId"]], on="raceId", how="left")
    df = df.merge(st.rename(columns={"raceId": "prev_raceId"}), on=["prev_raceId", "driverId"], how="left")
    df = df.merge(q, on=["raceId", "driverId"], how="left")
    for c in ("standing_position", "quali_position"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.drop(columns=["prev_raceId"]).sort_values(["order", "driverId"]).reset_index(drop=True)


# -------------------------------------------------------------------- model
def fit_predict(train: pd.DataFrame, test: pd.DataFrame, cols: list[str]) -> np.ndarray:
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    pipe = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                         LogisticRegression(max_iter=2000, C=0.5))
    pipe.fit(train[cols].astype(float), train["cls"].to_numpy())
    p = np.zeros((len(test), K))
    p[:, pipe.classes_] = pipe.predict_proba(test[cols].astype(float))
    return p


def walk_forward(df: pd.DataFrame, cols: list[str], window: tuple[int, int]) -> np.ndarray:
    out = np.full((len(df), K), np.nan)
    for order in sorted(df.loc[df["year"].between(*window), "order"].unique()):
        train, test = df[df["order"] < order], df["order"] == order
        if len(train) < 200:
            continue
        out[test.to_numpy()] = fit_predict(train, df[test], cols)
    return out


def per_race(df: pd.DataFrame, p: np.ndarray) -> pd.DataFrame:
    y = df["cls"].to_numpy()
    onehot = np.eye(K)[y]
    ll = -np.log(np.clip(p[np.arange(len(y)), y], EPS, 1))
    brier = ((p - onehot) ** 2).sum(axis=1)
    return (df[["raceId"]].assign(log_loss=ll, brier=brier)
            .groupby("raceId", as_index=False)[["log_loss", "brier"]].mean())


def ece(df: pd.DataFrame, p: np.ndarray) -> float:
    cal = pd.DataFrame({"target": "le1", "p": p[:, 0], "y": (df["cls"] == 0).astype(int)})
    return M.calibration(cal, "le1")[1]


def rule(df: pd.DataFrame, name: str) -> np.ndarray:
    return df[[f"rule_{name}_{k}" for k in range(K)]].to_numpy(dtype=float)


def _fmt(d: dict) -> str:
    return (f"{d['mean_difference']:+.4f} [{d['lo']:+.4f}, {d['hi']:+.4f}]"
            f"{' significant' if d['significant'] else ''}")


# ----------------------------------------------------------------- commands
def select() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    df = build()
    df = df[df["year"] <= INSAMPLE[1]].reset_index(drop=True)
    win = df["year"].between(*INSAMPLE).to_numpy()
    ev = df[win].reset_index(drop=True)
    rules = {n: (per_race(ev, rule(ev, n)), ece(ev, rule(ev, n))) for n in ("circuit", "season")}
    bar = min(rules, key=lambda n: rules[n][0]["log_loss"].mean())
    print(f"2019-2025: {ev['raceId'].nunique()} races, {len(ev)} finishers")
    for n, (rows, e) in rules.items():
        print(f"  {n} rule: log loss {rows['log_loss'].mean():.4f}  Brier {rows['brier'].mean():.4f}  ECE {e:.4f}")
    print(f"  site bar: {bar} rule")
    record = {"bar": bar, "rules": {n: {"log_loss": float(r[0]["log_loss"].mean()), "ece": r[1]}
                                    for n, r in rules.items()}, "levels": {}}
    for level, pos in LEVELS.items():
        data = df.assign(position=df[pos])
        res = {}
        for cid, cols in CANDIDATES.items():
            p = walk_forward(data, cols, INSAMPLE)[win]
            rows = per_race(ev, p)
            res[cid] = {"log_loss": float(rows["log_loss"].mean()), "brier": float(rows["brier"].mean()),
                        "ece": ece(ev, p), "vs_bar": M.paired_difference(rows, rules[bar][0], "log_loss")}
        chosen = min(res, key=lambda c: res[c]["log_loss"])
        guard = res[chosen]["ece"] > 2 * rules[bar][1]
        record["levels"][level] = {"results": res, "chosen": chosen, "calibration_guard_tripped": bool(guard)}
        print(f"\n{level}:")
        for cid, r in res.items():
            print(f"  {cid} log loss {r['log_loss']:.4f}  Brier {r['brier']:.4f}  ECE {r['ece']:.4f}  "
                  f"vs {bar} rule {_fmt(r['vs_bar'])}")
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
    df = build()
    win = df["year"].between(*HOLDOUT).to_numpy()
    ev = df[win].reset_index(drop=True)
    bar = sel["bar"]
    bar_rows = per_race(ev, rule(ev, bar))
    out = {"bar": bar, "races": int(ev["raceId"].nunique()),
           "bar_log_loss": float(bar_rows["log_loss"].mean()), "bar_ece": ece(ev, rule(ev, bar)),
           "other_rule_log_loss": float(per_race(ev, rule(ev, "season" if bar == "circuit" else "circuit"))
                                        ["log_loss"].mean()), "levels": {}}
    print(f"2026: {out['races']} races, {len(ev)} finishers; {bar} rule {out['bar_log_loss']:.4f}")
    for level, pos in LEVELS.items():
        chosen = sel["levels"][level]["chosen"]
        p = walk_forward(df.assign(position=df[pos]), CANDIDATES[chosen], HOLDOUT)[win]
        rows = per_race(ev, p)
        d = M.paired_difference(rows, bar_rows, "log_loss")
        out["levels"][level] = {"chosen": chosen, "log_loss": float(rows["log_loss"].mean()),
                                "ece": ece(ev, p), "vs_bar": d}
        print(f"  {level}: {chosen} {rows['log_loss'].mean():.4f} (ECE {out['levels'][level]['ece']:.4f})  "
              f"vs {bar} rule {_fmt(d)}")
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
