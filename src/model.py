"""Phase 2 Part C: models, measured against the baselines.

Three models, in increasing order of what they assume:

1. **Logistic regression**, one per target. Linear, transparent, and the thing
   to beat before reaching for anything with trees in it.
2. **LightGBM**, one per target. Handles the missing values natively, which
   matters when a fifth of the circuit-history column is legitimately absent.
3. **A ranking model with Monte Carlo.** Learns a strength per driver, then
   samples full finishing orders from a Plackett-Luce model built on those
   strengths. This is the only one that produces a coherent joint
   distribution -- the others give four marginals that need not agree with each
   other, and the site publishes a position distribution that has to sum to one.

Everything is walk-forward by race: to predict race R the model is fitted on
races strictly before R and on nothing else. That is slow and it is the only
honest way to compare against the baselines, which work the same way.

Results are reported with bootstrap confidence intervals over races, because a
two-point difference in win rate over 166 races is usually noise, and with
calibration as well as discrimination. A model with a better log loss and worse
calibration is the wrong choice here: the site publishes the probabilities
themselves, so they have to mean what they say.
"""
from __future__ import annotations

import sys
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import features as F  # noqa: E402
from baselines import FLOOR, Score  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "features"
EVAL_FROM = 2019
MC_DRAWS = 10_000
RNG_SEED = 20260922

TARGETS = ("win", "podium", "top10", "dnf")


# -------------------------------------------------------------------- inputs
def targets_frame() -> pd.DataFrame:
    """One row per (race, driver) with the four binary targets and the order."""
    res = F._rd(F.PROCESSED / "results.csv")
    races = F._rd(F.PROCESSED / "races.csv")
    races["order"] = races["year"] * 100 + races["round"]
    res = res.merge(races[["raceId", "year", "round", "order"]], on="raceId")
    res = res[res["positionText"].astype(str) != "W"].copy()
    pos = pd.to_numeric(res["positionOrder"], errors="coerce")
    res["finish_order"] = pos
    res["win"] = (res["positionText"].astype(str) == "1").astype(int)
    res["podium"] = ((pos <= 3) & ~F._is_dnf(res["positionText"])).astype(int)
    res["top10"] = ((pos <= 10) & ~F._is_dnf(res["positionText"])).astype(int)
    res["dnf"] = F._is_dnf(res["positionText"]).astype(int)
    return res[["raceId", "driverId", "year", "order", "finish_order", *TARGETS]]


def feature_inputs() -> list[Path]:
    """Everything a cached feature frame is computed from: the processed tables,
    the FastF1 season laps, and the code that turns them into features."""
    return (sorted(F.PROCESSED.glob("*.csv")) + sorted((F.ENRICHED / "laps").glob("*.csv"))
            + [Path(F.__file__)])


def cache_is_fresh(path: Path, inputs: list[Path] | None = None) -> bool:
    """True when the cache exists and nothing it was built from has changed since.

    A frame built before the latest race was merged would otherwise be served
    forever, and a prediction trained on it would silently leave that race out.
    """
    if not path.exists():
        return False
    built = path.stat().st_mtime
    return all(p.stat().st_mtime <= built for p in (inputs or feature_inputs()) if p.exists())


def feature_frame(snapshot: str, rebuild: bool = False) -> pd.DataFrame:
    """Features, cached because a full build is a hundred seconds, and rebuilt
    whenever the data or the feature code is newer than the cache."""
    CACHE.mkdir(parents=True, exist_ok=True)
    # CSV rather than parquet: the frame is four thousand rows, and parquet
    # would mean adding pyarrow for no benefit at this size.
    path = CACHE / f"{snapshot}.csv"
    if not rebuild and cache_is_fresh(path):
        return pd.read_csv(path)
    if path.exists() and not rebuild:
        print(f"  {path.name}: the data is newer than the cached features; rebuilding",
              file=sys.stderr)
    df = F.build(None, snapshot)
    df.to_csv(path, index=False)
    return df


def dataset(snapshot: str, rebuild: bool = False) -> pd.DataFrame:
    x = feature_frame(snapshot, rebuild)
    y = targets_frame()
    df = x.merge(y, on=["raceId", "driverId"], how="inner")
    return df.sort_values(["order", "driverId"]).reset_index(drop=True)


# -------------------------------------------------------------------- models
@dataclass
class Prediction:
    race_id: int
    year: int
    p: dict[str, pd.Series]      # target -> Series indexed by driverId
    position_distribution: pd.DataFrame | None = None


def _normalise(p: pd.Series, total: float) -> pd.Series:
    s = p.clip(lower=FLOOR)
    return s / s.sum() * min(total, len(s))


class LogisticModel:
    """One regularised logistic regression per target.

    Median imputation and standardisation are fitted on the training fold only.
    Using statistics from the whole dataset would leak the future through the
    scaler, which is a quieter version of the same mistake the feature tests
    exist to catch.
    """

    name = "logistic"

    def __init__(self, cols: list[str]):
        self.cols = cols

    def fit_predict(self, train: pd.DataFrame, test: pd.DataFrame) -> dict[str, pd.Series]:
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.impute import SimpleImputer
        from sklearn.preprocessing import StandardScaler

        out = {}
        xtr, xte = train[self.cols].astype(float), test[self.cols].astype(float)
        for t in TARGETS:
            y = train[t].to_numpy()
            if y.sum() == 0 or y.sum() == len(y):
                out[t] = pd.Series(float(y.mean()), index=test["driverId"].to_numpy())
                continue
            pipe = make_pipeline(
                SimpleImputer(strategy="median"),
                StandardScaler(),
                LogisticRegression(max_iter=2000, C=0.5),
            )
            pipe.fit(xtr, y)
            out[t] = pd.Series(pipe.predict_proba(xte)[:, 1], index=test["driverId"].to_numpy())
        return out


class LgbmModel:
    """Gradient-boosted trees per target. Missing values go in as missing."""

    name = "lightgbm"

    def __init__(self, cols: list[str], n_estimators: int = 300):
        self.cols = cols
        self.n = n_estimators

    def fit_predict(self, train: pd.DataFrame, test: pd.DataFrame) -> dict[str, pd.Series]:
        import lightgbm as lgb

        out = {}
        xtr, xte = train[self.cols].astype(float), test[self.cols].astype(float)
        for t in TARGETS:
            y = train[t].to_numpy()
            if y.sum() < 5 or y.sum() > len(y) - 5:
                out[t] = pd.Series(float(y.mean()), index=test["driverId"].to_numpy())
                continue
            m = lgb.LGBMClassifier(n_estimators=self.n, learning_rate=0.05, num_leaves=15,
                                   min_child_samples=30, subsample=0.9, subsample_freq=1,
                                   colsample_bytree=0.8, reg_lambda=1.0, verbose=-1,
                                   random_state=RNG_SEED)
            m.fit(xtr, y)
            out[t] = pd.Series(m.predict_proba(xte)[:, 1], index=test["driverId"].to_numpy())
        return out


class RankerMonteCarlo:
    """Learn a strength per driver, then simulate the race.

    LightGBM's ranker gives a score per driver. Those scores become
    Plackett-Luce strengths, and finishing orders are sampled from them by the
    Gumbel trick -- adding Gumbel noise to each log-strength and sorting is an
    exact draw from the Plackett-Luce ordering, with no sequential sampling
    loop.

    The advantage over four separate classifiers is coherence. Win, podium and
    top-ten probabilities all fall out of the same set of simulated orders, so
    they cannot contradict one another, and the full position distribution the
    site publishes comes free. A temperature is fitted on the training fold,
    because a ranker's raw scores carry the right order but an arbitrary scale,
    and the scale is what turns an order into a probability.
    """

    name = "ranker+mc"

    def __init__(self, cols: list[str], n_estimators: int = 300, draws: int = MC_DRAWS,
                 calibration_races: int = 25):
        self.cols = cols
        self.n = n_estimators
        self.draws = draws
        self.calibration_races = calibration_races

    @staticmethod
    def _log_loss_at(z: np.ndarray, groups: list[np.ndarray], winners: list[int],
                     temperature: float) -> float:
        total = 0.0
        for idx, w in zip(groups, winners):
            s = z[idx] / temperature
            s = s - s.max()
            p = np.exp(s)
            p /= p.sum()
            total -= np.log(max(p[w], FLOOR))
        return total / max(len(groups), 1)

    def _fit_temperature(self, z: np.ndarray, train: pd.DataFrame) -> float:
        groups, winners = [], []
        pos = 0
        for _, g in train.groupby("raceId", sort=False):
            idx = np.arange(pos, pos + len(g))
            pos += len(g)
            w = np.argmax(g["win"].to_numpy())
            if g["win"].sum() == 1:
                groups.append(idx)
                winners.append(int(w))
        if not groups:
            return 1.0
        best, best_ll = 1.0, float("inf")
        for t in np.geomspace(0.05, 20.0, 40):
            ll = self._log_loss_at(z, groups, winners, float(t))
            if ll < best_ll:
                best, best_ll = float(t), ll
        return best

    def fit_predict(self, train: pd.DataFrame, test: pd.DataFrame) -> dict[str, pd.Series]:
        p, _ = self.fit_predict_full(train, test)
        return p

    def fit_predict_full(self, train: pd.DataFrame,
                         test: pd.DataFrame) -> tuple[dict[str, pd.Series], pd.DataFrame]:
        import lightgbm as lgb

        ordered = train.sort_values(["order", "raceId"])
        # The temperature has to be fitted on races the ranker did not see.
        # Fitted in-sample it collapses toward zero, because a ranker puts the
        # winner first on its own training data almost every time, and the
        # likelihood is then maximised by making the distribution a point mass.
        # That is exactly what happened: p_win hit 1.000 in most races and the
        # actual winner was given exactly zero in 55 of 166, for a log loss of
        # 7.57 against a 1.43 baseline.
        race_order = ordered["raceId"].drop_duplicates().tolist()
        n_hold = max(self.calibration_races, 1)
        holdout = set(race_order[-n_hold:]) if len(race_order) > n_hold * 2 else set()
        tr = ordered[~ordered["raceId"].isin(holdout)] if holdout else ordered
        cal = ordered[ordered["raceId"].isin(holdout)] if holdout else ordered
        sizes = tr.groupby("raceId", sort=False).size().to_numpy()
        # lambdarank wants "bigger is better", so the finishing order is flipped
        # and clipped: the difference between 18th and 19th is not information.
        rel = (25 - tr["finish_order"].clip(upper=25)).astype(int).to_numpy()
        ranker = lgb.LGBMRanker(objective="lambdarank", n_estimators=self.n,
                                learning_rate=0.05, num_leaves=15, min_child_samples=30,
                                colsample_bytree=0.8, reg_lambda=1.0, verbose=-1,
                                random_state=RNG_SEED)
        ranker.fit(tr[self.cols].astype(float), rel, group=sizes)

        temperature = self._fit_temperature(
            ranker.predict(cal[self.cols].astype(float)), cal)
        z = ranker.predict(test[self.cols].astype(float)) / temperature

        rng = np.random.default_rng(RNG_SEED)
        n = len(z)
        gumbel = rng.gumbel(size=(self.draws, n))
        order = np.argsort(-(z[None, :] + gumbel), axis=1)      # best first
        rank = np.empty_like(order)
        rows = np.arange(self.draws)[:, None]
        rank[rows, order] = np.arange(n)[None, :]               # 0 = winner

        ids = test["driverId"].to_numpy()
        counts = np.stack([np.bincount(rank[:, i], minlength=n) for i in range(n)])
        # Laplace smoothing. Ten thousand draws cannot represent anything below
        # one in ten thousand, and a simulated zero for a driver who then wins
        # is an infinite log loss rather than a confident miss.
        dist = (counts + 1.0) / (self.draws + n)
        dist = dist / dist.sum(axis=1, keepdims=True)
        out = {
            "win": pd.Series(dist[:, 0], index=ids),
            "podium": pd.Series(dist[:, :3].sum(axis=1), index=ids),
            "top10": pd.Series(dist[:, :min(10, n)].sum(axis=1), index=ids),
        }
        # The ranker orders the field; it says nothing about retirement, so the
        # DNF probability comes from the same gradient-boosted classifier the
        # other model uses. Stated rather than hidden.
        out["dnf"] = LgbmModel(self.cols, self.n).fit_predict(train, test)["dnf"]
        return out, pd.DataFrame(dist, index=ids)


# -------------------------------------------------------------- walk-forward
def walk_forward(df: pd.DataFrame, model, snapshot: str, eval_from: int = EVAL_FROM,
                 verbose: bool = True, min_train: int = 200) -> pd.DataFrame:
    """Fit on everything before each race, predict that race, move on.

    Slow by construction. Any faster scheme -- one fit, or refitting once a season --
    lets a race learn from its own future, which is the thing the baselines do
    not do and so would not be a fair comparison.
    """
    rows = []
    race_ids = df.loc[df["year"] >= eval_from, "raceId"].drop_duplicates().tolist()
    for i, rid in enumerate(race_ids, 1):
        order = int(df.loc[df["raceId"] == rid, "order"].iloc[0])
        train = df[df["order"] < order]
        test = df[df["raceId"] == rid]
        if len(train) < min_train or len(test) < 5:
            continue
        p = model.fit_predict(train, test)
        for t in TARGETS:
            rows.append(pd.DataFrame({
                "raceId": rid, "year": int(test["year"].iloc[0]), "target": t,
                "driverId": test["driverId"].to_numpy(),
                "p": p[t].reindex(test["driverId"].to_numpy()).to_numpy(),
                "y": test[t].to_numpy(),
            }))
        if verbose and i % 20 == 0:
            print(f"    {model.name} {snapshot}: {i}/{len(race_ids)} races", flush=True)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


# ------------------------------------------------------------------- scoring
def score_predictions(preds: pd.DataFrame, name: str) -> tuple[dict, pd.DataFrame]:
    """Race-level scores, plus the per-race rows the bootstrap resamples."""
    s = Score()
    wins = preds[preds["target"] == "win"]
    for rid, g in wins.groupby("raceId", sort=False):
        if g["y"].sum() != 1:
            continue
        p = pd.Series(g["p"].to_numpy(), index=g["driverId"].to_numpy())
        winner = int(g.loc[g["y"] == 1, "driverId"].iloc[0])
        pod = preds[(preds["raceId"] == rid) & (preds["target"] == "podium")]
        podium = set(pod.loc[pod["y"] == 1, "driverId"].astype(int))
        s.add(p, winner, podium, int(rid))
    return s.as_dict(name), pd.DataFrame(s._rows)


def bootstrap_ci(per_race: pd.DataFrame, column: str, draws: int = 2000,
                 seed: int = RNG_SEED) -> tuple[float, float, float]:
    """Percentile interval from resampling races, not rows.

    Races are the independent unit here. Resampling driver-rows would treat
    twenty drivers in one race as twenty pieces of evidence, which they are
    not -- if the model misreads the car, it misreads all twenty at once.
    """
    v = per_race[column].to_numpy(dtype=float)
    if len(v) == 0:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    means = v[rng.integers(0, len(v), size=(draws, len(v)))].mean(axis=1)
    return float(v.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def paired_difference(a: pd.DataFrame, b: pd.DataFrame, column: str,
                      draws: int = 2000, seed: int = RNG_SEED) -> dict:
    """Is a better than b, or is it noise?

    Paired on the race, so the comparison is not swamped by the fact that some
    races are simply harder to predict than others.
    """
    m = a[["raceId", column]].merge(b[["raceId", column]], on="raceId", suffixes=("_a", "_b"))
    d = (m[f"{column}_a"] - m[f"{column}_b"]).to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    means = d[rng.integers(0, len(d), size=(draws, len(d)))].mean(axis=1)
    lo, hi = float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))
    return {"mean_difference": float(d.mean()), "lo": lo, "hi": hi,
            "significant": (lo > 0) or (hi < 0), "races": len(d)}


def calibration(preds: pd.DataFrame, target: str, bins: int = 10) -> tuple[pd.DataFrame, float]:
    """Reliability table and expected calibration error.

    Discrimination says whether the ordering is right. Calibration says whether
    a stated 20% happens one time in five. The site publishes the number, so
    the second one is not optional.
    """
    g = preds[preds["target"] == target].copy()
    if g.empty:
        return pd.DataFrame(), float("nan")
    edges = np.linspace(0, 1, bins + 1)
    g["bin"] = np.clip(np.digitize(g["p"], edges) - 1, 0, bins - 1)
    table = g.groupby("bin").agg(n=("p", "size"), predicted=("p", "mean"),
                                 observed=("y", "mean")).reset_index()
    table["edge_lo"] = edges[table["bin"]]
    table["edge_hi"] = edges[table["bin"] + 1]
    ece = float((table["n"] / table["n"].sum() * (table["predicted"] - table["observed"]).abs()).sum())
    return table, ece


# --------------------------------------------------------------------- runner
OUT = ROOT / "data" / "features" / "runs"


def run_all(snapshots=(F.POST, F.PRE), eval_from: int = EVAL_FROM) -> None:
    """Fit every model at every snapshot and persist the per-race predictions."""
    OUT.mkdir(parents=True, exist_ok=True)
    for snapshot in snapshots:
        df = dataset(snapshot)
        cols = list(F.features_for(snapshot))
        for model in (LogisticModel(cols), LgbmModel(cols), RankerMonteCarlo(cols)):
            path = OUT / f"{snapshot}__{model.name}.csv"
            if path.exists():
                print(f"  {path.name} already present, skipping", flush=True)
                continue
            print(f"  fitting {model.name} at {snapshot} ...", flush=True)
            preds = walk_forward(df, model, snapshot, eval_from)
            preds.to_csv(path, index=False)
            print(f"  wrote {path.name}: {len(preds):,} rows", flush=True)


def main() -> int:
    run_all()
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
