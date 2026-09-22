"""Part C diagnostics: why nothing beats qualifying order.

Five questions, run before drawing any conclusion about what to do next.

1. Does anything after quali_position move the number at all?
2. Is a linear term in quali_position the problem? P1 to P2 is not P15 to P16.
3. Is LightGBM overfitting, and does heavy regularisation change the verdict?
4. Do the practice and form coefficients actually differ from zero?
5. Are the early folds training on so little that most of the walk-forward is
   measuring a model that has barely learned anything?
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
import features as F  # noqa: E402
import model as M  # noqa: E402

SCORING_TARGETS = ("win", "podium")


def groups(snapshot: str) -> dict[str, list[str]]:
    avail = set(F.features_for(snapshot))
    out: dict[str, list[str]] = {}
    for f in F.FEATURES:
        if f.name in avail:
            out.setdefault(f.group, []).append(f.name)
    return out


def incremental_steps(snapshot: str) -> list[tuple[str, list[str]]]:
    g = groups(snapshot)
    quali_rest = [c for c in g.get("Qualifying", []) if c != "quali_position"]
    steps, cols = [], ["quali_position"]
    steps.append(("1. quali_position alone", list(cols)))
    cols += quali_rest
    steps.append(("2. + quali gaps", list(cols)))
    cols += g.get("Practice", [])
    steps.append(("3. + practice", list(cols)))
    cols += g.get("Driver form", []) + g.get("Team form", []) + g.get("Relative form", [])
    steps.append(("4. + form", list(cols)))
    cols += g.get("Circuit history", []) + g.get("Context", [])
    steps.append(("5. + circuit", list(cols)))
    cols += g.get("Tyre", [])
    steps.append(("6. + tyre (everything)", list(cols)))
    return steps


class Slim(M.LogisticModel):
    """Only the targets the scorer needs, so six walk-forwards stay affordable."""

    name = "slim-logistic"

    def fit_predict(self, train, test):
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        out = {}
        xtr, xte = train[self.cols].astype(float), test[self.cols].astype(float)
        for t in M.TARGETS:
            if t not in SCORING_TARGETS:
                out[t] = pd.Series(0.0, index=test["driverId"].to_numpy())
                continue
            y = train[t].to_numpy()
            pipe = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                                 LogisticRegression(max_iter=1000, C=0.5))
            pipe.fit(xtr, y)
            out[t] = pd.Series(pipe.predict_proba(xte)[:, 1], index=test["driverId"].to_numpy())
        return out


class OneHotQuali(Slim):
    """quali_position as twenty indicators instead of one slope."""

    name = "onehot-quali"

    def fit_predict(self, train, test):
        def widen(df):
            x = df[self.cols].astype(float).copy()
            pos = df["quali_position"].fillna(0).clip(0, 20).astype(int)
            for k in range(1, 21):
                x[f"q_{k}"] = (pos == k).astype(float)
            return x.drop(columns=["quali_position"])

        tmp = Slim(self.cols)
        tmp.cols = self.cols
        train2, test2 = train.copy(), test.copy()
        wtr, wte = widen(train), widen(test)
        for c in wtr.columns:
            train2[c], test2[c] = wtr[c].to_numpy(), wte[c].to_numpy()
        tmp.cols = list(wtr.columns)
        return tmp.fit_predict(train2, test2)


class SplineQuali(Slim):
    """quali_position through a natural cubic spline basis."""

    name = "spline-quali"

    def fit_predict(self, train, test):
        knots = np.array([1, 2, 3, 5, 8, 12, 20], dtype=float)

        def widen(df):
            x = df[self.cols].astype(float).copy()
            pos = df["quali_position"].astype(float).fillna(20.0).clip(1, 22).to_numpy()
            x["q_log"] = np.log(pos)
            for i, k in enumerate(knots[:-1]):
                x[f"q_h{i}"] = np.clip(pos - k, 0, None) ** 3
            return x.drop(columns=["quali_position"])

        tmp = Slim(self.cols)
        train2, test2 = train.copy(), test.copy()
        wtr, wte = widen(train), widen(test)
        for c in wtr.columns:
            train2[c], test2[c] = wtr[c].to_numpy(), wte[c].to_numpy()
        tmp.cols = list(wtr.columns)
        return tmp.fit_predict(train2, test2)


class LgbmRegularised(M.LgbmModel):
    name = "lightgbm-regularised"

    def fit_predict(self, train, test):
        import lightgbm as lgb

        out = {}
        xtr, xte = train[self.cols].astype(float), test[self.cols].astype(float)
        for t in M.TARGETS:
            if t not in SCORING_TARGETS:
                out[t] = pd.Series(0.0, index=test["driverId"].to_numpy())
                continue
            y = train[t].to_numpy()
            m = lgb.LGBMClassifier(n_estimators=150, learning_rate=0.03, num_leaves=4,
                                   min_child_samples=120, reg_lambda=50.0,
                                   colsample_bytree=0.6, subsample=0.7, subsample_freq=1,
                                   verbose=-1, random_state=M.RNG_SEED)
            m.fit(xtr, y)
            out[t] = pd.Series(m.predict_proba(xte)[:, 1], index=test["driverId"].to_numpy())
        return out


# ---------------------------------------------------------------- diagnostics
def run_incremental(df: pd.DataFrame, snapshot: str, bar: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for label, cols in incremental_steps(snapshot):
        preds = M.walk_forward(df, Slim(cols), snapshot, verbose=False)
        _, per_race = M.score_predictions(preds, label)
        mean, lo, hi = M.bootstrap_ci(per_race, "log_loss")
        d = M.paired_difference(per_race, bar, "log_loss")
        rows.append({"step": label, "cols": len(cols), "log_loss": mean,
                     "ci": f"[{lo:.4f}, {hi:.4f}]", "vs_bar": d["mean_difference"],
                     "vs_bar_ci": f"[{d['lo']:+.4f}, {d['hi']:+.4f}]",
                     "beats_bar": d["significant"] and d["mean_difference"] < 0})
        print(f"    {label:<26} {mean:.4f}", flush=True)
    out = pd.DataFrame(rows)
    out["delta_from_previous"] = out["log_loss"].diff()
    return out


def run_quali_shape(df: pd.DataFrame, snapshot: str, bar: pd.DataFrame) -> pd.DataFrame:
    cols = list(F.features_for(snapshot))
    rows = []
    for model in (Slim(cols), OneHotQuali(cols), SplineQuali(cols),
                  Slim(["quali_position"]), OneHotQuali(["quali_position"]),
                  SplineQuali(["quali_position"])):
        label = f"{model.name} ({len(model.cols)} base cols)"
        preds = M.walk_forward(df, model, snapshot, verbose=False)
        _, per_race = M.score_predictions(preds, label)
        mean, lo, hi = M.bootstrap_ci(per_race, "log_loss")
        d = M.paired_difference(per_race, bar, "log_loss")
        rows.append({"variant": label, "log_loss": mean, "ci": f"[{lo:.4f}, {hi:.4f}]",
                     "vs_bar": d["mean_difference"], "vs_bar_ci": f"[{d['lo']:+.4f}, {d['hi']:+.4f}]",
                     "beats_bar": d["significant"] and d["mean_difference"] < 0})
        print(f"    {label:<40} {mean:.4f}", flush=True)
    return pd.DataFrame(rows)


def run_overfit_check(df: pd.DataFrame, snapshot: str) -> pd.DataFrame:
    """Train and test log loss on the same folds, for the plain and heavily
    regularised trees. A large gap means the reported number flatters it."""
    import lightgbm as lgb
    from sklearn.metrics import log_loss as sk_log_loss

    cols = list(F.features_for(snapshot))
    race_ids = df.loc[df["year"] >= M.EVAL_FROM, "raceId"].drop_duplicates().tolist()
    picks = race_ids[::12]
    rows = []
    configs = {
        "lightgbm (as reported)": dict(n_estimators=300, learning_rate=0.05, num_leaves=15,
                                       min_child_samples=30, reg_lambda=1.0),
        "lightgbm (regularised)": dict(n_estimators=150, learning_rate=0.03, num_leaves=4,
                                       min_child_samples=120, reg_lambda=50.0),
    }
    for name, kw in configs.items():
        tr_ll, te_ll = [], []
        for rid in picks:
            order = int(df.loc[df["raceId"] == rid, "order"].iloc[0])
            train, test = df[df["order"] < order], df[df["raceId"] == rid]
            if len(train) < 400:
                continue
            m = lgb.LGBMClassifier(verbose=-1, random_state=M.RNG_SEED, **kw)
            m.fit(train[cols].astype(float), train["win"].to_numpy())
            tr_ll.append(sk_log_loss(train["win"], m.predict_proba(train[cols].astype(float))[:, 1],
                                     labels=[0, 1]))
            te_ll.append(sk_log_loss(test["win"], m.predict_proba(test[cols].astype(float))[:, 1],
                                     labels=[0, 1]))
        rows.append({"model": name, "folds": len(tr_ll),
                     "train_log_loss": float(np.mean(tr_ll)),
                     "test_log_loss": float(np.mean(te_ll)),
                     "gap": float(np.mean(te_ll) - np.mean(tr_ll))})
    return pd.DataFrame(rows)


def coefficients(df: pd.DataFrame, snapshot: str, target: str = "win") -> pd.DataFrame:
    """Standardised logistic coefficients with standard errors.

    Errors come from the observed information matrix, (X'WX)^-1 with
    W = diag(p(1-p)) -- the textbook asymptotic covariance for a logistic fit.
    Ridge shrinkage biases these toward zero, so C is set high enough that the
    penalty is not what makes a coefficient look small.
    """
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    cols = list(F.features_for(snapshot))
    x = SimpleImputer(strategy="median").fit_transform(df[cols].astype(float))
    x = StandardScaler().fit_transform(x)
    y = df[target].to_numpy()
    fit = LogisticRegression(max_iter=4000, C=1e6).fit(x, y)
    p = fit.predict_proba(x)[:, 1]
    xd = np.hstack([np.ones((len(x), 1)), x])
    w = np.clip(p * (1 - p), 1e-10, None)
    try:
        cov = np.linalg.pinv(xd.T * w @ xd)
        se = np.sqrt(np.diag(cov))[1:]
    except np.linalg.LinAlgError:
        se = np.full(len(cols), np.nan)
    beta = fit.coef_[0]
    z = beta / np.where(se > 0, se, np.nan)
    out = pd.DataFrame({"feature": cols, "beta": beta, "se": se, "z": z})
    out["group"] = [next(f.group for f in F.FEATURES if f.name == c) for c in cols]
    out["significant"] = out["z"].abs() > 1.96
    return out.reindex(out["z"].abs().sort_values(ascending=False).index)


def sample_sizes(df: pd.DataFrame) -> pd.DataFrame:
    race_ids = df.loc[df["year"] >= M.EVAL_FROM, "raceId"].drop_duplicates().tolist()
    rows = []
    for label, rid in (("first eval race", race_ids[0]), ("50th", race_ids[49]),
                       ("117th (start of last 50)", race_ids[-50]), ("last", race_ids[-1])):
        order = int(df.loc[df["raceId"] == rid, "order"].iloc[0])
        train = df[df["order"] < order]
        rows.append({"fold": label, "raceId": rid,
                     "training_rows": len(train), "training_races": train["raceId"].nunique(),
                     "wins_in_training": int(train["win"].sum()),
                     "drivers_in_race": int((df["raceId"] == rid).sum())})
    return pd.DataFrame(rows)


def late_window(bar: pd.DataFrame, last_n: int = 50) -> pd.DataFrame:
    """The same models scored on the last 50 races only, where every fold has
    a substantial training set."""
    runs = {k: pd.read_csv(p) for p in sorted(M.OUT.glob("post_qualifying__*.csv"))
            for k in [p.stem.split("__")[1]]}
    any_run = next(iter(runs.values()))
    late_ids = any_run["raceId"].drop_duplicates().tolist()[-last_n:]
    rows = []
    bar_late = bar[bar["raceId"].isin(late_ids)]
    for name, preds in runs.items():
        _, per_race = M.score_predictions(preds[preds["raceId"].isin(late_ids)], name)
        mean, lo, hi = M.bootstrap_ci(per_race, "log_loss")
        d = M.paired_difference(per_race, bar_late, "log_loss")
        rows.append({"model": name, "races": len(per_race), "log_loss": mean,
                     "ci": f"[{lo:.4f}, {hi:.4f}]", "vs_bar": d["mean_difference"],
                     "vs_bar_ci": f"[{d['lo']:+.4f}, {d['hi']:+.4f}]",
                     "beats_bar": d["significant"] and d["mean_difference"] < 0})
    b_mean, b_lo, b_hi = M.bootstrap_ci(bar_late, "log_loss")
    rows.append({"model": "baseline: qualifying order", "races": len(bar_late),
                 "log_loss": b_mean, "ci": f"[{b_lo:.4f}, {b_hi:.4f}]",
                 "vs_bar": 0.0, "vs_bar_ci": "-", "beats_bar": False})
    return pd.DataFrame(rows).sort_values("log_loss")


def main() -> int:
    pd.set_option("display.width", 220)
    snapshot = F.POST
    df = M.dataset(snapshot)
    _, extra = B.run()
    bar = pd.DataFrame(extra["scores"]["qualifying order"]._rows)
    bar_ll = bar["log_loss"].mean()

    print("=" * 108)
    print(f"PART C DIAGNOSTICS — post-qualifying.  The bar is qualifying order at {bar_ll:.4f}.")
    print("=" * 108)

    print("\n### 1. Incremental feature groups (logistic)\n")
    inc = run_incremental(df, snapshot, bar)
    print(inc.to_string(index=False, float_format=lambda v: f"{v:+.4f}"))

    print("\n### 2. The shape of quali_position\n")
    shape = run_quali_shape(df, snapshot, bar)
    print(shape.to_string(index=False, float_format=lambda v: f"{v:+.4f}"))

    print("\n### 3. LightGBM train against test\n")
    print(run_overfit_check(df, snapshot).to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    print("\n### 4. Logistic coefficients for p_win, standardised, with standard errors\n")
    co = coefficients(df, snapshot)
    print(co.head(14).to_string(index=False, float_format=lambda v: f"{v:+.3f}"))
    print(f"\n    {int(co['significant'].sum())} of {len(co)} features differ from zero at 95%.")
    for g in sorted(co["group"].unique()):
        sub = co[co["group"] == g]
        print(f"      {g:<16} {int(sub['significant'].sum())}/{len(sub)} significant, "
              f"max |z| {sub['z'].abs().max():.2f}")

    print("\n### 5. Sample size per fold\n")
    print(sample_sizes(df).to_string(index=False))
    print("\n    The same models on the last 50 races only:\n")
    print(late_window(bar).to_string(index=False, float_format=lambda v: f"{v:+.4f}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
