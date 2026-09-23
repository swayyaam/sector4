"""Tests for the live prediction pipeline.

The property that matters most is immutability. A track record is only worth
reading if the predictions in it could not have been edited after the result
was known, so the scorer is tested to leave the prediction file byte-identical
and to refuse to score the same race twice.
"""
from __future__ import annotations

import json
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DATA = ROOT / "data" / "processed"
ON_TIME = "2026-09-12T18:00:00Z"     # after R14 qualifying, before the race
LATE = "2026-09-14T09:00:00Z"        # the morning after R14
needs_data = pytest.mark.skipif(
    not (DATA / "results.csv").exists(),
    reason="the full dataset is gitignored; these run locally and before a release",
)


def _run(script: str, *args: str, out_dir: Path) -> subprocess.CompletedProcess:
    env = {**dict(__import__("os").environ), "SECTOR4_PREDICTIONS": str(out_dir)}
    return subprocess.run([sys.executable, str(ROOT / "src" / script), *args],
                          cwd=ROOT, capture_output=True, text=True, env=env)


@pytest.fixture(scope="module")
def prediction(tmp_path_factory):
    """A real prediction for a completed race, written into a temp directory."""
    import predict as P

    out = tmp_path_factory.mktemp("predictions")
    P.OUT = out
    pred = P.build(2026, 14, "post_qualifying")
    # Built today, for a race that ran on the 13th. Stamped as if published the
    # evening before, so the scorer's deadline rule treats it as on time; the
    # rule itself is tested separately below.
    pred["generated_at"] = ON_TIME
    path = P.path_for(2026, 14, "post_qualifying")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pred, indent=2) + "\n")
    return out, path, pred


# ----------------------------------------------------------------- the shape
@needs_data
def test_probabilities_satisfy_the_published_schema(prediction):
    _, _, pred = prediction
    ds = pred["drivers"]
    n = len(ds)
    assert sum(d["p_win"] for d in ds) == pytest.approx(1.0, abs=1e-9)
    assert sum(d["p_podium"] for d in ds) == pytest.approx(min(3, n), abs=1e-9)
    assert sum(d["p_top10"] for d in ds) == pytest.approx(min(10, n), abs=1e-9)
    for d in ds:
        assert d["p_win"] <= d["p_podium"] <= d["p_top10"]
        assert len(d["position_distribution"]) == n
        assert sum(d["position_distribution"]) == pytest.approx(1.0, abs=1e-9)
        assert 0.0 <= d["p_dnf"] <= 1.0


@needs_data
def test_every_driver_has_a_team(prediction):
    """Without it there is no team name, no colour and nothing to group a
    garage by, and the site's validator rejects the file outright."""
    _, _, pred = prediction
    for d in pred["drivers"]:
        assert d["team_entity_id"], f"driver {d['driverId']} has no team"


@needs_data
def test_provenance_is_recorded(prediction):
    """A reader a year from now has to be able to tell which model made this."""
    _, _, pred = prediction
    for key in ("model_version", "model_features", "data_version", "commit_sha",
                "generated_at", "model_note", "training_races"):
        assert pred.get(key), f"{key} is missing or empty"
    assert pred["commit_sha"] != "unknown"
    assert pred["is_mock"] is False
    assert pred["result"] is None, "a fresh prediction carries no result"


@needs_data
def test_top_factors_are_weights_not_timing_values(prediction):
    """Republishing a gap in milliseconds would be redistributing F1 timing
    data. A normalised magnitude is a model output. See DATA_LICENSE.md."""
    _, _, pred = prediction
    for d in pred["drivers"]:
        for f in d["top_factors"]:
            assert 0.0 <= f["magnitude"] <= 1.0
            assert f["direction"] in ("positive", "negative")
            assert "ms" not in f["label"].lower()


# ------------------------------------------------------------- immutability
@needs_data
def test_scoring_leaves_the_prediction_byte_identical(prediction, monkeypatch):
    import predict as P
    import score_race as S

    out, path, _ = prediction
    monkeypatch.setattr(P, "OUT", out)
    monkeypatch.setattr(S, "OUT", out)
    monkeypatch.setattr(S, "LEDGER", out / "track_record.json")
    monkeypatch.setattr(S, "RESULTS_DIR", out / "results")

    before = path.read_bytes()
    monkeypatch.setattr(sys, "argv", ["score_race.py", "--season", "2026", "--round", "14"])
    assert S.main() == 0
    assert path.read_bytes() == before, "the scorer modified a prediction file"


@needs_data
def test_the_ledger_records_the_baseline_beside_the_model(prediction, monkeypatch):
    import predict as P
    import score_race as S

    out, _, _ = prediction
    monkeypatch.setattr(P, "OUT", out)
    monkeypatch.setattr(S, "OUT", out)
    monkeypatch.setattr(S, "LEDGER", out / "track_record.json")
    monkeypatch.setattr(S, "RESULTS_DIR", out / "results")
    monkeypatch.setattr(sys, "argv", ["score_race.py", "--season", "2026", "--round", "14"])
    S.main()

    ledger = json.loads((out / "track_record.json").read_text())
    assert ledger["races"], "nothing was appended"
    entry = ledger["races"][0]
    assert set(entry["model"]) == {"log_loss", "brier", "winner_hit", "podium_hits"}
    assert set(entry["baseline"]) == {"name", "log_loss", "brier", "winner_hit", "podium_hits"}
    # Each snapshot is judged against a baseline that sees what it sees.
    import score_race as S2
    assert entry["baseline"]["name"] == S2.BASELINE_FOR[entry["snapshot"]]
    assert "championship order" in entry["all_baselines"]
    assert entry["prediction_sha256"]
    assert entry["predicted_at"] < entry["scored_at"], "scored before it was predicted"


@needs_data
def test_a_race_is_not_scored_twice(prediction, monkeypatch):
    import predict as P
    import score_race as S

    out, _, _ = prediction
    monkeypatch.setattr(P, "OUT", out)
    monkeypatch.setattr(S, "OUT", out)
    monkeypatch.setattr(S, "LEDGER", out / "track_record.json")
    monkeypatch.setattr(S, "RESULTS_DIR", out / "results")
    monkeypatch.setattr(sys, "argv", ["score_race.py", "--season", "2026", "--round", "14"])
    S.main()
    n_first = len(json.loads((out / "track_record.json").read_text())["races"])
    S.main()
    n_second = len(json.loads((out / "track_record.json").read_text())["races"])
    assert n_first == n_second, "re-running the scorer appended a duplicate"


@needs_data
def test_predictions_are_never_overwritten(prediction, monkeypatch):
    import predict as P

    out, path, _ = prediction
    monkeypatch.setattr(P, "OUT", out)
    monkeypatch.setattr(sys, "argv",
                        ["predict.py", "--season", "2026", "--round", "14",
                         "--snapshot", "post_qualifying"])
    with pytest.raises(SystemExit, match="never overwritten"):
        P.main()
    assert path.exists()


@needs_data
def test_dnf_is_a_real_probability(prediction):
    """A published zero would claim no car can retire. The diagnostic model
    classes fit only the targets the scorer needs and returned exactly that."""
    _, _, pred = prediction
    dnf = [d["p_dnf"] for d in pred["drivers"]]
    assert max(dnf) > 0.01, "every DNF probability is zero"
    assert sum(dnf) > 0.5, f"the whole field sums to {sum(dnf):.3f} retirements"
    assert all(d < 0.9 for d in dnf)


@needs_data
def test_a_revision_published_after_the_race_is_refused(tmp_path, monkeypatch, capsys):
    """A prediction timestamped after its session could have seen the session.
    The scorer reports it and scores nothing."""
    import predict as P
    import score_race as S

    pred = P.build(2026, 14, "post_qualifying")
    pred["generated_at"] = LATE
    monkeypatch.setattr(P, "OUT", tmp_path)
    monkeypatch.setattr(S, "OUT", tmp_path)
    monkeypatch.setattr(S, "LEDGER", tmp_path / "track_record.json")
    monkeypatch.setattr(S, "RESULTS_DIR", tmp_path / "results")
    path = P.path_for(2026, 14, "post_qualifying")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pred, indent=2))

    monkeypatch.setattr(sys, "argv", ["score_race.py", "--season", "2026", "--round", "14"])
    S.main()
    out = capsys.readouterr().out
    assert "IGNORING" in out and "REFUSING" in out
    assert not (tmp_path / "track_record.json").exists(), "a late prediction was scored"


@needs_data
def test_revising_needs_a_reason(prediction, monkeypatch):
    import predict as P

    out, _, _ = prediction
    monkeypatch.setattr(P, "OUT", out)
    monkeypatch.setattr(sys, "argv", ["predict.py", "--season", "2026", "--round", "14",
                                      "--snapshot", "post_qualifying", "--revise"])
    with pytest.raises(SystemExit, match="needs --reason"):
        P.main()


@needs_data
def test_revising_after_the_deadline_is_refused(prediction, monkeypatch):
    """R14 ran on the 13th; a revision now could not be scored, so none is written."""
    import predict as P

    out, _, _ = prediction
    monkeypatch.setattr(P, "OUT", out)
    monkeypatch.setattr(sys, "argv", ["predict.py", "--season", "2026", "--round", "14",
                                      "--snapshot", "post_qualifying", "--revise",
                                      "--reason", "test"])
    with pytest.raises(SystemExit, match="deadline"):
        P.main()
    assert not P.path_for(2026, 14, "post_qualifying", 2).exists()
