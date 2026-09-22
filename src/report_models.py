"""Read the walk-forward predictions and report them properly.

Three things this insists on:

* **Intervals, not point estimates.** Bootstrapped over races, because races are
  the independent unit; resampling driver rows would count one misread car as
  twenty pieces of evidence.
* **A paired comparison against the bar.** Qualifying order is the baseline to
  beat. Paired on the race, so a run of hard races does not decide it.
* **Calibration alongside discrimination.** The site publishes probabilities, so
  a stated 20% has to happen about one time in five. A model with the better
  log loss and worse calibration is the wrong choice here.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import baselines as B  # noqa: E402
import features as F  # noqa: E402
import model as M  # noqa: E402

BAR = "qualifying order"


def _fmt(mean: float, lo: float, hi: float, places: int = 4) -> str:
    return f"{mean:.{places}f}  [{lo:.{places}f}, {hi:.{places}f}]"


def baseline_rows() -> dict[str, pd.DataFrame]:
    _, extra = B.run()
    return {name: pd.DataFrame(s._rows) for name, s in extra["scores"].items()}


def load_runs() -> dict[tuple[str, str], pd.DataFrame]:
    out = {}
    for path in sorted(M.OUT.glob("*.csv")):
        snapshot, name = path.stem.split("__")
        out[(snapshot, name)] = pd.read_csv(path)
    return out


def summarise(per_race: pd.DataFrame, label: str) -> dict:
    ll = M.bootstrap_ci(per_race, "log_loss")
    br = M.bootstrap_ci(per_race, "brier")
    wh = M.bootstrap_ci(per_race, "winner_hit")
    po = M.bootstrap_ci(per_race, "podium_hits")
    return {"model": label, "races": len(per_race),
            "log_loss": _fmt(*ll), "brier": _fmt(*br),
            "winner": _fmt(wh[0] * 100, wh[1] * 100, wh[2] * 100, 1) + "%",
            "podium": _fmt(po[0] / 3 * 100, po[1] / 3 * 100, po[2] / 3 * 100, 1) + "%",
            "_ll_mean": ll[0]}


def main() -> int:
    pd.set_option("display.width", 220)
    base = baseline_rows()
    runs = load_runs()
    if not runs:
        print("no runs found; run src/model.py first")
        return 1

    bar_rows = base[BAR]
    print("=" * 110)
    print("PART C — models against the baselines.  Walk-forward, 2019 onward.")
    print("Mean with a bootstrap 95% interval over races (2,000 resamples).")
    print("=" * 110)

    for snapshot in (F.POST, F.PRE):
        present = {k: v for k, v in runs.items() if k[0] == snapshot}
        if not present:
            continue
        rows, per_race = [], {}
        for name, rdf in base.items():
            rows.append(summarise(rdf, f"baseline: {name}"))
            per_race[f"baseline: {name}"] = rdf
        for (_, name), preds in sorted(present.items()):
            _, pr = M.score_predictions(preds, name)
            rows.append(summarise(pr, name))
            per_race[name] = pr

        print(f"\n### {snapshot}\n")
        table = pd.DataFrame(rows).sort_values("_ll_mean").drop(columns=["_ll_mean"])
        print(table.to_string(index=False))

        print(f"\n  Against the bar ({BAR}, log loss {bar_rows['log_loss'].mean():.4f}).")
        print("  Negative difference means the model is better. Paired on the race.\n")
        for (_, name) in sorted(present.keys()):
            d = M.paired_difference(per_race[name], bar_rows, "log_loss")
            verdict = ("beats the bar" if d["significant"] and d["mean_difference"] < 0
                       else "loses to the bar" if d["significant"]
                       else "indistinguishable from the bar")
            print(f"    {name:<12} {d['mean_difference']:+.4f}  "
                  f"[{d['lo']:+.4f}, {d['hi']:+.4f}]   {verdict}")

        print("\n  Calibration — expected calibration error per target (lower is better):\n")
        cal = []
        for (_, name), preds in sorted(present.items()):
            row = {"model": name}
            for t in M.TARGETS:
                _, ece = M.calibration(preds, t)
                row[t] = round(ece, 4)
            cal.append(row)
        print(pd.DataFrame(cal).to_string(index=False))

        print("\n  Reliability of p_win, best model by log loss:\n")
        best = min(present.items(), key=lambda kv: M.score_predictions(kv[1], "x")[0]["log_loss"])
        tab, ece = M.calibration(best[1], "win")
        tab = tab[tab["n"] > 0]
        print(f"    {best[0][1]}  (ECE {ece:.4f})")
        for _, r in tab.iterrows():
            print(f"      p in [{r['edge_lo']:.1f}, {r['edge_hi']:.1f})  n={int(r['n']):5d}  "
                  f"said {r['predicted']:.3f}  happened {r['observed']:.3f}")

        # 2026 is a regulation reset; averaging it into the rest hides that.
        print("\n  2026 alone (regulation reset, reported separately):\n")
        for (_, name), preds in sorted(present.items()):
            sub = preds[preds["year"] == 2026]
            if sub.empty:
                continue
            _, pr = M.score_predictions(sub, name)
            if len(pr):
                print(f"    {name:<12} {summarise(pr, name)['log_loss']}   ({len(pr)} races)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
