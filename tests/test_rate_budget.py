"""Tests for the FastF1 request budget.

The budget exists because FastF1's limiter counts a refused call against you,
so hitting the cap makes the next attempt worse rather than better. Two runs
lost 7.8 hours to that. These tests pin the two properties that matter: the
count is exact, and the pacing degrades smoothly instead of falling off a
cliff.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import fetch_fastf1 as ff  # noqa: E402
from fetch_fastf1 import RateBudget  # noqa: E402


@pytest.fixture
def budget(tmp_path, monkeypatch):
    """A budget with a small cap, so the interesting boundaries are reachable."""
    monkeypatch.setattr(ff, "RATE_SOFT_FRACTION", 0.7)
    return RateBudget(path=tmp_path / "rate.json", per_hour=10)


class _Clock:
    """A stand-in for time.time() that only moves when told to."""

    def __init__(self, t: float = 1_000_000.0):
        self.t = t
        self.slept = 0.0

    def time(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.slept += seconds
        self.t += seconds


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(ff.time, "time", c.time)
    monkeypatch.setattr(ff.time, "sleep", c.sleep)
    return c


# ------------------------------------------------------------------ accounting
def test_every_request_costs_exactly_one_slot(budget, clock):
    for _ in range(4):
        budget.acquire()
    assert budget.used() == 4


def test_entries_leave_the_window_after_an_hour(budget, clock):
    budget.record(5)
    clock.t += 3599
    assert budget.used() == 5
    clock.t += 2
    assert budget.used() == 0


def test_count_survives_a_restart(budget, clock, tmp_path):
    budget.record(6)
    reloaded = RateBudget(path=tmp_path / "rate.json", per_hour=10)
    assert reloaded.used() == 6


def test_a_corrupt_log_reads_as_spent_not_empty(tmp_path, clock):
    """The dangerous failure is a crash mid-write handing the next run a clean
    budget: it would sprint straight into the cap it was built to avoid."""
    path = tmp_path / "rate.json"
    path.write_text('[1000.0, 1001.0, ')       # truncated mid-write
    b = RateBudget(path=path, per_hour=10)
    assert b.used() == 10


def test_flush_is_atomic(budget, clock, tmp_path):
    budget.record(3)
    assert json.loads((tmp_path / "rate.json").read_text()) == pytest.approx([clock.t] * 3)
    assert not (tmp_path / "rate.tmp").exists()


# --------------------------------------------------------------------- pacing
def test_no_spacing_while_there_is_headroom(budget, clock):
    for _ in range(6):                          # soft threshold is 7 of 10
        budget.acquire()
    assert clock.slept == 0


def test_spacing_ramps_in_as_the_budget_runs_down(budget, clock):
    budget.record(7)                            # exactly at the soft threshold
    first = budget._soft_delay()
    budget.record(2)
    second = budget._soft_delay()
    assert first == 0
    assert 0 < second < ff.RATE_WINDOW / budget.per_hour


def test_spacing_reaches_the_sustainable_interval_at_the_cap(budget, clock):
    budget.record(10)
    assert budget._soft_delay() == pytest.approx(ff.RATE_WINDOW / budget.per_hour)


def test_a_full_budget_waits_for_the_oldest_entry_to_expire(budget, clock):
    budget.record(10)
    clock.t += 1000
    budget.wait_for(1)
    # The oldest entry was 1000s old, so ~2600s remained on its hour.
    assert 2595 <= clock.slept <= 2605
    assert budget.used() < budget.per_hour


def test_the_cap_is_never_exceeded(budget, clock):
    """The property the whole class exists for."""
    for _ in range(40):
        budget.acquire()
        assert budget.used() <= budget.per_hour


# ----------------------------------------------------------------- attachment
class _FakeRequest:
    url = "https://livetiming.formula1.com/static/whatever.jsonStream"


def test_attach_counts_one_slot_per_send(monkeypatch, tmp_path, clock):
    """Counting happens at FastF1's own choke point, so a 404 or a repeat body
    costs the same as a fresh 200 -- which is what the cap actually charges."""
    calls = []

    class FakeSession:
        def send(self, request, **kwargs):
            calls.append(request.url)
            return "response"

    fake_req = type("req", (), {"_SessionWithRateLimiting": FakeSession})
    monkeypatch.setitem(sys.modules, "fastf1", type("fastf1", (), {"req": fake_req}))
    monkeypatch.setitem(sys.modules, "fastf1.req", fake_req)

    b = RateBudget(path=tmp_path / "rate.json", per_hour=10)
    b.attach()
    assert b.attached

    s = FakeSession()
    for _ in range(3):
        assert s.send(_FakeRequest()) == "response"
    assert b.used() == 3
    assert len(calls) == 3


def test_attach_is_idempotent(monkeypatch, tmp_path, clock):
    class FakeSession:
        def send(self, request, **kwargs):
            return "response"

    fake_req = type("req", (), {"_SessionWithRateLimiting": FakeSession})
    monkeypatch.setitem(sys.modules, "fastf1", type("fastf1", (), {"req": fake_req}))
    monkeypatch.setitem(sys.modules, "fastf1.req", fake_req)

    b = RateBudget(path=tmp_path / "rate.json", per_hour=10)
    b.attach()
    b.attach()
    FakeSession().send(_FakeRequest())
    assert b.used() == 1          # wrapped once, not twice


# ------------------------------------------------- the assumptions about FastF1
fastf1 = pytest.importorskip("fastf1", reason="FastF1 not installed")


def test_fastf1_still_has_the_choke_point_we_hook():
    """If a FastF1 upgrade renames any of this, the gate silently stops working.
    Better to fail here than to discover it from a four-hour stall in a log."""
    from fastf1 import req

    cls = req._SessionWithRateLimiting
    assert callable(cls.send)
    assert hasattr(cls, "_RATE_LIMITS")

    limits = [lim for lims in cls._RATE_LIMITS.values() for lim in lims]
    general = [lim for lim in limits if "any API" in getattr(lim, "_info", "")]
    assert general, "the general hourly limiter is gone or renamed"
    assert general[0]._timestamps.maxlen >= ff.RATE_MAX_PER_HOUR, (
        "our cap is no longer below FastF1's"
    )


def test_cached_responses_never_reach_send():
    """The reason wrapping `send` is the right place: requests_cache answers a
    hit before send() runs, and FastF1's limiter never sees it either."""
    from requests_cache import CacheMixin

    from fastf1 import req

    assert issubclass(req._CachedSessionWithRateLimiting, CacheMixin)
    assert req._CachedSessionWithRateLimiting.__mro__.index(CacheMixin) < \
        req._CachedSessionWithRateLimiting.__mro__.index(req._SessionWithRateLimiting)


def test_fastf1_counts_refused_calls_which_is_why_this_class_exists():
    """The behaviour the whole design is a response to: the timestamp is
    appended before the check, so a refusal still costs a slot."""
    from fastf1.exceptions import RateLimitExceededError
    from fastf1.req import _CallsPerIntervalLimitRaise

    lim = _CallsPerIntervalLimitRaise(2, 3600, "test")
    lim.limit()
    with pytest.raises(RateLimitExceededError):
        lim.limit()
    assert len(lim._timestamps) == 2      # the refused call was counted too


def test_reconciliation_compares_only_this_run(tmp_path, clock):
    """The persisted window survives restarts; FastF1's deque does not. Compare
    the wrong pair and a perfectly healthy restart looks like a broken hook."""
    path = tmp_path / "rate.json"
    path.write_text(json.dumps([clock.t - 60] * 200))       # left by a previous run

    b = RateBudget(path=path, per_hour=460)
    assert b.used() == 200          # carried over, as intended
    assert b.spent_here == 0        # but nothing spent by *this* process yet

    b.acquire()
    b.acquire()
    assert b.spent_here == 2
    assert b.used() == 202
