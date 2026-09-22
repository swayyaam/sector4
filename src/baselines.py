"""Phase 2 Part C: baselines, measured before any model is built.

A log loss means nothing on its own. These are the numbers any model has to
beat to have earned its complexity, and they are deliberately cheap:

* **grid order** -- the empirical chance of winning from each grid slot.
* **qualifying order** -- the same, keyed on where the driver qualified.
* **Elo** -- a rating per driver, updated on finishing order, with no knowledge
  of the car, the circuit or the weekend.

All three are walk-forward. Each race is predicted from races strictly before
it and from nothing else, so the comparison against a model trained the same
way is fair. The positional priors are re-estimated at every race rather than
fitted once over the whole history, which would let a 2019 prediction learn
from 2024.

Scoring matches what the site publishes, so a baseline and a model can be read
against each other and against the track record:

* log loss   -- -ln p(actual winner); punishes confident misses
* Brier      -- squared error of the whole win distribution, summed
* winner hit -- did the highest probability win
* podium     -- how many of the top three by probability finished top three
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from features import PROCESSED, _is_dnf, _rd  # noqa: E402

EVAL_FROM_SEASON = 2019      # 2018 is burn-in for the priors and the ratings
FLOOR = 1e-9                 # keeps log loss finite when a baseline says zero


# ------------------------------------------------------------------- scoring
@dataclass
class Score:
    races: int = 0
    log_loss: float = 0.0
    brier: float = 0.0
    winner_hits: float = 0.0
    podium_hits: float = 0.0
    _rows: list = field(default_factory=list)

    def add(self, p: pd.Series, winner: int, podium: set[int], race_id: int) -> None:
        """Score one race.

        Ties are resolved by expectation, not by a tie-break. Any deterministic
        rule correlates with something -- row order hands a tied predictor the
        finishing order, and driverId hands it whoever has the lowest id, which
        in this era is Hamilton. Both flattered the uniform baseline, once to
        99.4% and once to 19.9%, against a true 5%. Taking the expectation over
        a random draw among equals is the only answer that is right for every
        predictor.
        """
        if not p.index.is_unique:
            raise ValueError(
                "the probability series has a duplicated driverId. Before 1965 a "
                "driver could share a car and appear twice in one classification; "
                "deduplicate the field before scoring rather than letting pandas "
                "return a Series where a float is expected."
            )
        p = (p / p.sum()).sort_index()
        pw = float(p.get(winner, 0.0))
        ll = -math.log(max(pw, FLOOR))
        br = float(sum((p.get(d, 0.0) - (1.0 if d == winner else 0.0)) ** 2 for d in p.index))

        top = p.max()
        tied_top = set(p.index[p == top])
        winner_credit = (1.0 / len(tied_top)) if winner in tied_top else 0.0

        podium_credit = self._expected_overlap(p, podium, 3)

        self.races += 1
        self.log_loss += ll
        self.brier += br
        self.winner_hits += winner_credit
        self.podium_hits += podium_credit
        self._rows.append({"raceId": race_id, "log_loss": ll, "brier": br,
                           "winner_hit": winner_credit, "podium_hits": podium_credit})

    @staticmethod
    def _expected_overlap(p: pd.Series, actual: set[int], k: int) -> float:
        """Expected size of (top k by probability) intersected with `actual`,
        averaging over random selection inside any tie at the cut."""
        if len(p) <= k:
            return float(len(set(p.index) & actual))
        ordered = p.sort_values(ascending=False)
        cut = ordered.iloc[k - 1]
        certain = set(ordered.index[ordered > cut])
        tied = set(ordered.index[ordered == cut])
        slots = k - len(certain)
        hit = float(len(certain & actual))
        if slots > 0 and tied:
            hit += slots * len(tied & actual) / len(tied)
        return hit

    def as_dict(self, name: str) -> dict:
        n = max(self.races, 1)
        return {"baseline": name, "races": self.races,
                "log_loss": self.log_loss / n, "brier": self.brier / n,
                "winner_hit_rate": self.winner_hits / n,
                "podium_hits": round(self.podium_hits, 1), "podium_of": self.races * 3,
                "podium_rate": self.podium_hits / (n * 3)}


# ----------------------------------------------------------------- baselines
def uniform(field_ids: list[int], _state) -> pd.Series:
    """Every driver equally likely. The floor nothing may score worse than."""
    return pd.Series(1.0 / len(field_ids), index=field_ids)


class PositionPrior:
    """P(win | starting position), estimated from races already seen.

    Laplace-smoothed, so a position that has never produced a winner is
    unlikely rather than impossible -- a zero here would make log loss
    infinite the first time it happened.
    """

    def __init__(self, column: str, alpha: float = 1.0):
        self.column = column
        self.alpha = alpha
        self.wins: dict[int, float] = {}
        self.starts: dict[int, float] = {}

    def observe(self, race: pd.DataFrame) -> None:
        for _, r in race.iterrows():
            pos = r[self.column]
            if pd.isna(pos) or pos <= 0:
                continue
            pos = int(pos)
            self.starts[pos] = self.starts.get(pos, 0.0) + 1
            if str(r["positionText"]) == "1":
                self.wins[pos] = self.wins.get(pos, 0.0) + 1

    def predict(self, race: pd.DataFrame) -> pd.Series:
        out = {}
        for _, r in race.iterrows():
            pos = r[self.column]
            if pd.isna(pos) or pos <= 0:
                rate = self.alpha / (sum(self.starts.values()) + self.alpha)
            else:
                pos = int(pos)
                rate = ((self.wins.get(pos, 0.0) + self.alpha)
                        / (self.starts.get(pos, 0.0) + self.alpha * 20))
            out[int(r["driverId"])] = max(rate, FLOOR)
        return pd.Series(out)


class Elo:
    """One rating per driver, updated on finishing order.

    Every classified pair in a race is one comparison, which is the standard
    multiplayer extension. K is scaled by the number of comparisons so a
    twenty-car race does not move ratings twenty times as far as a duel.
    Win probability is a softmax over the field, which is Plackett-Luce with
    exponential strengths -- the same family the predictions themselves use.
    """

    def __init__(self, k: float = 24.0, scale: float = 400.0, start: float = 1500.0):
        self.k, self.scale, self.start = k, scale, start
        self.rating: dict[int, float] = {}

    def _r(self, d: int) -> float:
        return self.rating.get(d, self.start)

    def observe(self, race: pd.DataFrame) -> None:
        classified = race[~_is_dnf(race["positionText"])]
        order = classified.sort_values("positionOrder")[["driverId", "positionOrder"]]
        ids = [int(d) for d in order["driverId"]]
        if len(ids) < 2:
            return
        delta = {d: 0.0 for d in ids}
        n_pairs = len(ids) - 1
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                expected = 1.0 / (1.0 + 10 ** ((self._r(b) - self._r(a)) / self.scale))
                adj = self.k / n_pairs
                delta[a] += adj * (1.0 - expected)
                delta[b] -= adj * (1.0 - expected)
        for d, v in delta.items():
            self.rating[d] = self._r(d) + v

    def predict(self, race: pd.DataFrame) -> pd.Series:
        ids = [int(d) for d in race["driverId"]]
        strengths = {d: 10 ** (self._r(d) / self.scale) for d in ids}
        total = sum(strengths.values())
        return pd.Series({d: max(v / total, FLOOR) for d, v in strengths.items()})


# ---------------------------------------------------------------- evaluation
def run(eval_from: int = EVAL_FROM_SEASON) -> tuple[pd.DataFrame, dict]:
    races = _rd(PROCESSED / "races.csv")
    races["order"] = races["year"] * 100 + races["round"]
    races = races.sort_values("order")
    results = _rd(PROCESSED / "results.csv")
    results["grid_pos"] = pd.to_numeric(results["grid"], errors="coerce")
    quali = _rd(PROCESSED / "qualifying.csv")[["raceId", "driverId", "position"]]
    quali = quali.rename(columns={"position": "quali_pos"})
    results = results.merge(quali, on=["raceId", "driverId"], how="left")
    results["quali_pos"] = pd.to_numeric(results["quali_pos"], errors="coerce")

    grid_prior = PositionPrior("grid_pos")
    quali_prior = PositionPrior("quali_pos")
    elo = Elo()
    scores = {"uniform": Score(), "grid order": Score(),
              "qualifying order": Score(), "elo": Score()}
    per_race = []

    for _, race in races.iterrows():
        rid = int(race["raceId"])
        field_rows = results[results["raceId"] == rid]
        if field_rows.empty:
            continue
        # Sorted by driverId so nothing downstream can accidentally read the
        # finishing order out of the row order. Deduplicated because a shared
        # drive before 1965 puts the same driver in one classification twice,
        # and a field is a set of drivers.
        started = (field_rows[field_rows["positionText"].astype(str) != "W"]
                   .sort_values(["driverId", "positionOrder"])
                   .drop_duplicates("driverId", keep="first")
                   .reset_index(drop=True))
        if len(started) < 5:
            continue
        won = started[started["positionText"].astype(str) == "1"]
        if won.empty:
            continue
        winner = int(won.iloc[0]["driverId"])
        pos = pd.to_numeric(started["positionOrder"], errors="coerce")
        podium = set(started.loc[pos <= 3, "driverId"].astype(int))

        if int(race["year"]) >= eval_from:
            ids = [int(d) for d in started["driverId"]]
            preds = {
                "uniform": uniform(ids, None),
                "grid order": grid_prior.predict(started),
                "qualifying order": quali_prior.predict(started),
                "elo": elo.predict(started),
            }
            for name, p in preds.items():
                scores[name].add(p, winner, podium, rid)
            per_race.append({"raceId": rid, "year": int(race["year"]), "name": race["name"]})

        # Learn only after predicting: this is the whole discipline.
        grid_prior.observe(started)
        quali_prior.observe(started)
        elo.observe(started)

    table = pd.DataFrame([s.as_dict(n) for n, s in scores.items()])
    return table, {"elo": elo, "scores": scores, "races": per_race}


def main() -> int:
    table, _ = run()
    pd.set_option("display.width", 200)
    print("=" * 84)
    print(f"BASELINES — walk-forward, {EVAL_FROM_SEASON} onward")
    print("=" * 84)
    print(table.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
