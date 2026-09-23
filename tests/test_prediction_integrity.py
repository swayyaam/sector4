"""A committed prediction is never modified in place.

This is the property the track record rests on. If a prediction could be edited
after it was published, then a good score proves nothing -- it might have been
edited toward the result. So the rule is enforced against git history, not
against good intentions: every version of every prediction file must carry the
same prediction, and the only thing ever added afterwards is the pair of
pointers that says a newer revision replaced it.

This test exists because the rule was broken once. A prediction was regenerated
in place to fix two bugs, before its race, on an unmerged branch. It was caught
in review, undone, and republished as a second revision -- and
`test_the_audit_catches_an_in_place_rewrite` reproduces that exact mistake to
prove this file would now catch it.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import revisions as R  # noqa: E402

needs_history = pytest.mark.skipif(
    not R.history_is_available(),
    reason="shallow clone; CI checks out full history so this runs there",
)


# ------------------------------------------------------------ the real record
@needs_history
def test_committed_predictions_are_never_modified_in_place():
    problems = []
    for path in R.all_prediction_files():
        problems += R.audit_history(path)
    assert problems == [], "\n".join(problems)


@needs_history
def test_the_working_tree_has_not_rewritten_a_committed_prediction():
    """Catches the mistake before it is committed, not only after."""
    problems = []
    for path in R.all_prediction_files():
        rel = path.relative_to(ROOT).as_posix()
        try:
            committed = json.loads(subprocess.run(
                ["git", "show", f"HEAD:{rel}"], cwd=ROOT, capture_output=True,
                text=True, check=True).stdout)
        except subprocess.CalledProcessError:
            continue                                  # new file, not yet committed
        if R.content_digest(committed) != R.content_digest(json.loads(path.read_text())):
            problems.append(f"{rel}: differs from the committed version beyond its pointers")
    assert problems == [], "\n".join(problems)


def test_revision_links_are_consistent():
    assert R.audit_links() == []


# ------------------------------------------------------- the audit itself works
def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    for cmd in (["init", "-q"], ["config", "user.email", "t@example.com"],
                ["config", "user.name", "t"]):
        subprocess.run(["git", *cmd], cwd=repo, check=True)
    return repo


def _commit(repo: Path, path: Path, data: dict, msg: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    subprocess.run(["git", "add", str(path)], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=repo, check=True)


def _pred(p_dnf: float = 0.0) -> dict:
    return {"season": 2026, "round": 15, "snapshot": "pre_weekend",
            "generated_at": "2026-09-22T20:14:47Z",
            "drivers": [{"driverId": 1, "p_win": 0.5, "p_dnf": p_dnf}]}


def test_the_audit_catches_an_in_place_rewrite(tmp_path):
    """The mistake this file exists to prevent, reproduced."""
    repo = _repo(tmp_path)
    f = repo / "predictions" / "2026" / "15-pre_weekend.json"
    _commit(repo, f, _pred(p_dnf=0.0), "publish")
    _commit(repo, f, _pred(p_dnf=0.14), "fix it in place")
    problems = R.audit_history(f, repo=repo)
    assert len(problems) == 1 and "content changed" in problems[0]


def test_the_audit_allows_only_the_superseding_pointers(tmp_path):
    repo = _repo(tmp_path)
    f = repo / "predictions" / "2026" / "15-pre_weekend.json"
    _commit(repo, f, _pred(), "publish")
    _commit(repo, f, {**_pred(), "superseded_by": "15-pre_weekend-r2.json",
                      "superseded_reason": "bug"}, "supersede")
    assert R.audit_history(f, repo=repo) == []


def test_the_audit_forbids_repointing_a_superseded_file(tmp_path):
    repo = _repo(tmp_path)
    f = repo / "predictions" / "2026" / "15-pre_weekend.json"
    _commit(repo, f, _pred(), "publish")
    _commit(repo, f, {**_pred(), "superseded_by": "15-pre_weekend-r2.json",
                      "superseded_reason": "bug"}, "supersede")
    _commit(repo, f, {**_pred(), "superseded_by": "15-pre_weekend-r3.json",
                      "superseded_reason": "bug"}, "quietly repoint")
    problems = R.audit_history(f, repo=repo)
    assert any("superseded_by changed" in p for p in problems)


# ---------------------------------------------------------- which one counts
UTC = timezone.utc
SCHEDULE = {"Practice 1": datetime(2026, 9, 24, 8, 30, tzinfo=UTC),
            "Qualifying": datetime(2026, 9, 25, 12, 0, tzinfo=UTC),
            "Race": datetime(2026, 9, 26, 11, 0, tzinfo=UTC)}


def _write(out: Path, rev: int, generated_at: str, snapshot: str = "pre_weekend") -> None:
    path = R.revision_path(2026, 15, snapshot, rev, out)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"season": 2026, "round": 15, "snapshot": snapshot, "generated_at": generated_at}
    if rev > 1:
        body |= {"revision": rev, "supersedes": R.revision_path(2026, 15, snapshot, rev - 1).name,
                 "revision_reason": "test"}
    path.write_text(json.dumps(body))


def test_the_latest_on_time_revision_counts(tmp_path):
    _write(tmp_path, 1, "2026-09-22T20:00:00Z")
    _write(tmp_path, 2, "2026-09-23T20:00:00Z")
    _write(tmp_path, 3, "2026-09-24T09:00:00Z")          # after FP1 started
    chosen, late = R.effective(2026, 15, "pre_weekend", tmp_path, SCHEDULE)
    assert chosen[0] == 2
    assert [r[0] for r in late] == [3]


def test_nothing_counts_when_every_revision_is_late(tmp_path):
    _write(tmp_path, 1, "2026-09-24T09:00:00Z")
    chosen, late = R.effective(2026, 15, "pre_weekend", tmp_path, SCHEDULE)
    assert chosen is None and len(late) == 1


def test_each_snapshot_has_its_own_deadline():
    """Pre-weekend claims 'before any car runs'; post-qualifying predicts the race."""
    assert R.deadline(2026, 15, "pre_weekend", SCHEDULE) == SCHEDULE["Practice 1"]
    assert R.deadline(2026, 15, "post_qualifying", SCHEDULE) == SCHEDULE["Race"]


def test_the_pointers_are_outside_the_digest():
    a = _pred()
    b = {**a, "superseded_by": "x.json", "superseded_reason": "y"}
    assert R.content_digest(a) == R.content_digest(b)
    assert R.content_digest(a) != R.content_digest(_pred(p_dnf=0.1))
