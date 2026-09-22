"""The validation suite, run against the committed fixture.

The real dataset is 43MB and gitignored, so CI cannot run the suite against it.
The fixture is one complete season, which lets every check that can apply
actually run -- and the ones that cannot are recorded as skipped rather than
quietly dropped, so the total is still 69 either way.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "processed"
sys.path.insert(0, str(ROOT / "src"))

import validate  # noqa: E402


@pytest.fixture
def run(monkeypatch):
    """Run the suite against the fixture and hand back the recorded results."""
    monkeypatch.setattr(validate, "RESULTS", [])
    code = validate.main(["--data", str(FIXTURE)])
    return code, list(validate.RESULTS)


def test_the_fixture_is_committed():
    assert FIXTURE.is_dir(), "tests/fixtures/processed is missing"
    assert (FIXTURE / "races.csv").exists()


def test_no_check_fails_on_the_fixture(run):
    code, results = run
    failed = [(g, n, d) for g, n, ok, d in results if ok is False]
    assert failed == [], f"{len(failed)} checks failed: {failed[:5]}"
    assert code == 0


def test_every_check_is_accounted_for(run):
    """A check that cannot apply must say so. Silently vanishing is the failure
    mode this guards against: it is indistinguishable from never being written."""
    _, results = run
    passed = sum(1 for _, _, ok, _ in results if ok is True)
    skipped = sum(1 for _, _, ok, _ in results if ok is None)
    assert passed + skipped == len(results)
    assert passed >= 50, f"only {passed} checks ran against the fixture"
    assert skipped > 0, "the fixture is one season; some checks cannot apply"


def test_every_skip_explains_itself(run):
    _, results = run
    for group, name, ok, detail in results:
        if ok is None:
            assert detail, f"{group}/{name} was skipped without a reason"


def test_a_failure_produces_a_non_zero_exit(monkeypatch):
    """This used to always return 0, so a failing check could not fail a job."""
    monkeypatch.setattr(validate, "RESULTS", [])
    real_check = validate.check

    def fail_one(group, name, ok, detail=""):
        return real_check(group, name, False if name.startswith("races:") else ok, detail)

    monkeypatch.setattr(validate, "check", fail_one)
    assert validate.main(["--data", str(FIXTURE)]) == 1


# ------------------------------------------------------------------- helpers
def test_covers_and_full_history(monkeypatch):
    monkeypatch.setattr(validate, "YEARS", {2022})
    assert validate.covers(2022)
    assert not validate.covers(2007)
    assert not validate.covers(2022, 2007)
    assert not validate.full_history()

    monkeypatch.setattr(validate, "YEARS", {1950, 2022})
    assert validate.full_history()

    monkeypatch.setattr(validate, "YEARS", set())
    assert not validate.full_history()


def test_skip_is_recorded_separately(monkeypatch):
    monkeypatch.setattr(validate, "RESULTS", [])
    validate.skip("Group", "a check", "because")
    validate.check("Group", "another", True)
    kinds = [ok for _, _, ok, _ in validate.RESULTS]
    assert kinds == [None, True]
