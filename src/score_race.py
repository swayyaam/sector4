"""Phase 2 Part E: score a committed prediction after the race.

Run after a race completes and the incremental fetchers have brought in its
result. It reads the prediction, scores it, scores the qualifying-order
baseline on the same race, and appends both to the track record.

**It never writes to a prediction file.** Results go to a separate file and to
the ledger. A prediction that can be edited after the fact proves nothing, and
the separation is visible in the git history: one commit before the session,
one after.

The prediction is matched on (season, round) rather than raceId, because an
upcoming race has no raceId until it completes and the one recorded at
prediction time is provisional.

Usage:
    python src/score_race.py --season 2026 --round 15
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import baselines as B  # noqa: E402
import features as F  # noqa: E402
import revisions as REV  # noqa: E402
from predict import OUT, ROOT  # noqa: E402

LEDGER = OUT / "track_record.json"
RESULTS_DIR = OUT / "results"


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def actual(season: int, rnd: int) -> tuple[int, pd.DataFrame]:
    races = F._rd(F.PROCESSED / "races.csv")
    got = races[(races["year"] == season) & (races["round"] == rnd)]
    if got.empty:
        raise SystemExit(f"{season} round {rnd} has no row in data/processed/races.csv yet. "
                         "Run the incremental fetchers first.")
    race_id = int(got.iloc[0]["raceId"])
    res = F._rd(F.PROCESSED / "results.csv")
    rows = res[(res["raceId"] == race_id) & (res["positionText"].astype(str) != "W")]
    if rows.empty:
        raise SystemExit(f"raceId {race_id} has no results yet")
    return race_id, rows.sort_values("driverId").reset_index(drop=True)


def _season_of(race_id: int) -> int:
    races = F._rd(F.PROCESSED / "races.csv")
    return int(races.loc[races["raceId"] == race_id, "year"].iloc[0])


# Each snapshot is judged against a baseline that sees what it sees. Scoring a
# pre-weekend prediction against qualifying order would measure it on
# information it does not have; championship order is the fair comparison for a
# model that is, in effect, a standings model.
BASELINE_FOR = {F.PRE: "championship order", F.POST: "qualifying order"}


def baseline_probabilities(race_id: int) -> dict[str, dict]:
    """Every baseline's score on this race, fitted only on races before it.

    Recomputed from scratch each time rather than cached, so the numbers beside
    the model on the track record are produced by exactly the code in
    src/baselines.py and cannot drift from it.
    """
    # eval_from only controls which races are scored, never what the prior has
    # observed -- run() walks the whole history in order either way. Scoring
    # one season is the cheap way to reach this race's number.
    _, extra = B.run(eval_from=_season_of(race_id))
    out = {}
    for name, score in extra["scores"].items():
        for row in score._rows:
            if int(row["raceId"]) == race_id:
                out[name] = row
    if not out:
        raise SystemExit(f"no baseline scored raceId {race_id}")
    return out


# Why a snapshot's log loss can be undefined. It is -log of the probability
# the snapshot gave the winner, so a winner given nothing has no log loss. The
# baselines' floor would turn that into a number (20.72 at 1e-9) that measures
# the floor rather than the prediction, so it is left null and the reason kept.
WINNER_NOT_IN_FIELD = "winner_not_in_field"
WINNER_AT_ZERO = "winner_at_zero"


def log_loss_undefined(p: pd.Series, winner: int) -> str | None:
    """Why the snapshot has no log loss on this race, or None when it has one."""
    if winner not in p.index:
        return WINNER_NOT_IN_FIELD
    if float(p[winner]) <= 0.0:
        # p_win is published to six places, so a driver below 5e-7 is a 0.0.
        return WINNER_AT_ZERO
    return None


def score_one(p: pd.Series, winner: int, podium: set[int],
              race_id: int) -> tuple[dict, str | None]:
    """The snapshot's scores, and why its log loss is undefined if it is.

    Only the log loss is withheld. The winner was still missed, the podium
    places still count, and the Brier score is still defined: it charges the
    full miss on the winner.
    """
    s = B.Score()
    s.add(p, winner, podium, race_id)
    r = s._rows[0]
    undefined = log_loss_undefined(p, winner)
    return {"log_loss": None if undefined else round(r["log_loss"], 6),
            "brier": round(r["brier"], 6),
            "winner_hit": round(float(r["winner_hit"]), 4),
            "podium_hits": round(float(r["podium_hits"]), 4)}, undefined


def _display(path: Path) -> str:
    """Repo-relative where possible, absolute otherwise. A temp directory in a
    test is not under ROOT, and a cosmetic path should never crash a run."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--round", type=int, required=True)
    args = ap.parse_args()

    race_id, rows = actual(args.season, args.round)
    won = rows[rows["positionText"].astype(str) == "1"]
    if won.empty:
        raise SystemExit("no classified winner; cannot score")
    winner = int(won.iloc[0]["driverId"])
    pos = pd.to_numeric(rows["positionOrder"], errors="coerce")
    podium = set(rows.loc[pos <= 3, "driverId"].astype(int))

    ledger = json.loads(LEDGER.read_text()) if LEDGER.exists() else {"races": []}
    already = {(r["season"], r["round"], r["snapshot"]) for r in ledger["races"]}
    bars = baseline_probabilities(race_id)
    written = 0

    schedule = REV.sessions(args.season, args.round)
    for snapshot in (F.PRE, F.POST):
        published = REV.revisions(args.season, args.round, snapshot, OUT)
        if not published:
            continue
        key = (args.season, args.round, snapshot)
        if key in already:
            print(f"  {snapshot}: already scored, leaving it alone")
            continue

        # The latest revision generated before the session started, and only
        # that one. A revision timestamped after the deadline could have seen
        # the session, so it is reported and never scored.
        chosen, late = REV.effective(args.season, args.round, snapshot, OUT, schedule)
        for rev, lpath, lpred in late:
            print(f"  {snapshot}: IGNORING {lpath.name} -- generated {lpred['generated_at']}, "
                  f"after the {REV.deadline(args.season, args.round, snapshot, schedule):%Y-%m-%dT%H:%MZ} "
                  "deadline")
        if chosen is None:
            print(f"  {snapshot}: REFUSING to score -- no revision was published before the "
                  "session started")
            continue
        revision, path, pred = chosen

        before = file_digest(path)
        p = pd.Series({int(d["driverId"]): float(d["p_win"]) for d in pred["drivers"]})
        # Drivers who were predicted but did not start are dropped, and the
        # rest renormalised: scoring a driver who was never on the grid would
        # punish the model for the entry list rather than for the prediction.
        p = p[p.index.isin(rows["driverId"].astype(int))]
        model_score, undefined = score_one(p, winner, podium, race_id)

        entry = {
            "season": args.season, "round": args.round, "race_id": race_id,
            "race_name": pred.get("race_name"), "snapshot": snapshot,
            "predicted_at": pred["generated_at"],
            "scored_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "model_version": pred["model_version"], "commit_sha": pred["commit_sha"],
            "data_version": pred["data_version"],
            "prediction_sha256": before,
            "revision": revision, "revision_file": path.name,
            "revisions_published": len(published),
            "ignored_late_revisions": [lp.name for _, lp, _ in late],
            "model": model_score,
            # Set only when model.log_loss is null, and never filled in later.
            "log_loss_undefined": undefined,
            "baseline": {
                "name": BASELINE_FOR[snapshot],
                "log_loss": round(float(bars[BASELINE_FOR[snapshot]]["log_loss"]), 6),
                "brier": round(float(bars[BASELINE_FOR[snapshot]]["brier"]), 6),
                "winner_hit": round(float(bars[BASELINE_FOR[snapshot]]["winner_hit"]), 4),
                "podium_hits": round(float(bars[BASELINE_FOR[snapshot]]["podium_hits"]), 4),
            },
            # Every baseline, so the track record can show more than one and a
            # later question does not need a rescore.
            "all_baselines": {
                name: {"log_loss": round(float(r["log_loss"]), 6),
                       "brier": round(float(r["brier"]), 6),
                       "winner_hit": round(float(r["winner_hit"]), 4),
                       "podium_hits": round(float(r["podium_hits"]), 4)}
                for name, r in bars.items()
            },
            "winner_driverId": winner, "podium_driverIds": sorted(podium),
            "starters": int(len(rows)),
        }
        ledger["races"].append(entry)
        written += 1

        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        (RESULTS_DIR / f"{args.season}-{args.round:02d}.json").write_text(
            json.dumps({
                "season": args.season, "round": args.round, "race_id": race_id,
                "scored_at": entry["scored_at"],
                "drivers": [{"driverId": int(r["driverId"]),
                             "actual_position": None if str(r["positionText"]) == "R"
                             else int(r["positionOrder"]),
                             "status": str(r["positionText"])}
                            for _, r in rows.iterrows()],
            }, indent=2) + "\n")

        after = file_digest(path)
        if before != after:
            raise SystemExit(f"FATAL: {path} changed during scoring. Predictions are immutable.")
        mine = (f"undefined ({undefined})" if undefined
                else f"{model_score['log_loss']:.4f}")
        print(f"  {snapshot}: model log loss {mine}  "
              f"vs {entry['baseline']['name']} {entry['baseline']['log_loss']:.4f}")

    if written:
        ledger["races"].sort(key=lambda r: (r["season"], r["round"], r["snapshot"]))
        ledger["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        LEDGER.write_text(json.dumps(ledger, indent=2) + "\n")
        print(f"  appended {written} entries -> {_display(LEDGER)}")
    else:
        print("  nothing new to score")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
