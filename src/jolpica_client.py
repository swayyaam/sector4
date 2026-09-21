"""HTTP client for the Jolpica F1 API: throttling, retries, caching, pagination.

Documented limits (docs/rate_limits.md, checked 2026-09-21):
  * burst      4 requests / second
  * sustained  500 requests / hour
  * exceeding either returns HTTP 429
  * max ``limit`` is 100 (docs/README.md); default 30
  * a descriptive User-Agent is mandatory

We stay under both limits with a sliding-window limiter and leave headroom.
Every response is cached to disk so reruns cost nothing.
"""
from __future__ import annotations

import json
import logging
import random
import time
from collections import deque
from pathlib import Path
from urllib.parse import urlencode

import requests

log = logging.getLogger("jolpica")

BASE_URL = "https://api.jolpi.ca/ergast/f1"
USER_AGENT = "sector4-f1/0.1 (https://github.com/swayyaam/sector4)"
CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "raw" / "jolpica"

MAX_LIMIT = 100          # hard API maximum
BURST_PER_SEC = 3.0      # documented 4/s; headroom
SUSTAINED_PER_HOUR = 460  # documented 500/hr; headroom
MAX_RETRIES = 6


class RateLimiter:
    """Sliding-window limiter honouring both a per-second and a per-hour cap."""

    def __init__(self, per_sec: float = BURST_PER_SEC, per_hour: int = SUSTAINED_PER_HOUR):
        self.min_interval = 1.0 / per_sec
        self.per_hour = per_hour
        self._last = 0.0
        self._hour: deque[float] = deque()

    def acquire(self) -> None:
        now = time.monotonic()
        gap = self.min_interval - (now - self._last)
        if gap > 0:
            time.sleep(gap)
        # Sliding one-hour window.
        now = time.monotonic()
        while self._hour and now - self._hour[0] > 3600:
            self._hour.popleft()
        if len(self._hour) >= self.per_hour:
            wait = 3600 - (now - self._hour[0]) + 1
            log.warning("hourly cap reached (%d req) — sleeping %.0fs", self.per_hour, wait)
            time.sleep(wait)
            now = time.monotonic()
            while self._hour and now - self._hour[0] > 3600:
                self._hour.popleft()
        self._last = time.monotonic()
        self._hour.append(self._last)


class JolpicaClient:
    def __init__(self, cache_dir: Path = CACHE_DIR, limiter: RateLimiter | None = None,
                 session: requests.Session | None = None):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.limiter = limiter or RateLimiter()
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
        self.stats = {"cache_hits": 0, "network": 0, "retries": 0}

    # ------------------------------------------------------------------ cache
    def _cache_path(self, path: str, params: dict) -> Path:
        safe = path.strip("/").replace("/", "_") or "root"
        qs = urlencode(sorted(params.items())) if params else "none"
        qs = qs.replace("&", "__").replace("=", "-")
        return self.cache_dir / safe / f"{qs}.json"

    # ------------------------------------------------------------------- http
    def _request(self, path: str, params: dict) -> dict:
        url = f"{BASE_URL}/{path.strip('/')}/"
        delay = 2.0
        last_err: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            self.limiter.acquire()
            try:
                self.stats["network"] += 1
                r = self.session.get(url, params=params, timeout=30)
            except requests.RequestException as exc:      # network blip
                last_err = exc
                log.warning("  network error on %s (attempt %d/%d): %s", url, attempt, MAX_RETRIES, exc)
            else:
                if r.status_code == 200:
                    return r.json()
                if r.status_code == 429 or r.status_code >= 500:
                    last_err = RuntimeError(f"HTTP {r.status_code}")
                    retry_after = r.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after and retry_after.isdigit() else delay
                    log.warning("  HTTP %s on %s — backing off %.1fs (attempt %d/%d)",
                                r.status_code, url, wait, attempt, MAX_RETRIES)
                    time.sleep(wait)
                    delay = min(delay * 2, 120)
                    self.stats["retries"] += 1
                    continue
                # 4xx other than 429 is a real error; don't retry.
                raise RuntimeError(f"HTTP {r.status_code} for {url}?{urlencode(params)}: {r.text[:300]}")
            self.stats["retries"] += 1
            time.sleep(delay + random.uniform(0, 0.5))
            delay = min(delay * 2, 120)
        raise RuntimeError(f"giving up on {url} after {MAX_RETRIES} attempts: {last_err}")

    def get(self, path: str, params: dict | None = None, *, force: bool = False) -> dict:
        """One request, cached. ``force=True`` bypasses (and refreshes) the cache."""
        params = dict(params or {})
        cp = self._cache_path(path, params)
        if cp.exists() and not force:
            self.stats["cache_hits"] += 1
            return json.loads(cp.read_text())
        payload = self._request(path, params)
        cp.parent.mkdir(parents=True, exist_ok=True)
        # sort_keys keeps the cache byte-stable for identical payloads
        cp.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
        return payload

    # ------------------------------------------------------------- pagination
    def get_all(self, path: str, *, force: bool = False, extra: dict | None = None) -> list:
        """Page through an endpoint and return the fully merged row list.

        Two things make this non-trivial, both verified against the live API:

        1. ``total`` counts the *innermost* rows (individual results, pit stops,
           lap timings, standings lines) -- not the race objects wrapping them.
        2. A race can straddle a page boundary. ``/2025/results`` page 1 ends
           with round 11 holding a single result and page 2 continues it; the
           same happens to a lap's timings. Naive concatenation would produce
           duplicate race objects each holding a fragment, so we merge on
           (season, round) -- and, for laps, on lap number.

        Raises if the merged inner-row count disagrees with ``total``, so a
        short read can never pass silently.
        """
        shape = shape_for(path)
        pages = []
        offset, total = 0, None
        while True:
            params = {"limit": MAX_LIMIT, "offset": offset}
            if extra:
                params.update(extra)
            data = self.get(path, params, force=force)["MRData"]
            total = int(data["total"])
            rows = data.get(shape["table"], {}).get(shape["list"], [])
            pages.append(rows)
            offset += MAX_LIMIT
            if offset >= total or not rows:
                break
        merged = merge_pages(pages, shape)
        got = count_rows(merged, shape)
        if got != total:
            raise ValueError(
                f"pagination mismatch for {path}: merged {got} rows but API reported total={total}"
            )
        return merged


# ----------------------------------------------------------------- shapes
# inner  = the list inside each race/standings object that `total` counts
# inner2 = a second level (laps -> timings), keyed by `inner_key`
_SHAPES = {
    "races":                {"table": "RaceTable",        "list": "Races",          "inner": None},
    "results":              {"table": "RaceTable",        "list": "Races",          "inner": "Results"},
    "qualifying":           {"table": "RaceTable",        "list": "Races",          "inner": "QualifyingResults"},
    "sprint":               {"table": "RaceTable",        "list": "Races",          "inner": "SprintResults"},
    "pitstops":             {"table": "RaceTable",        "list": "Races",          "inner": "PitStops"},
    "laps":                 {"table": "RaceTable",        "list": "Races",          "inner": "Laps",
                             "inner2": "Timings", "inner_key": "number"},
    "driverstandings":      {"table": "StandingsTable",   "list": "StandingsLists", "inner": "DriverStandings"},
    "constructorstandings": {"table": "StandingsTable",   "list": "StandingsLists", "inner": "ConstructorStandings"},
    "drivers":              {"table": "DriverTable",      "list": "Drivers",        "inner": None},
    "constructors":         {"table": "ConstructorTable", "list": "Constructors",   "inner": None},
    "circuits":             {"table": "CircuitTable",     "list": "Circuits",       "inner": None},
    "status":               {"table": "StatusTable",      "list": "Status",         "inner": None},
    "seasons":              {"table": "SeasonTable",      "list": "Seasons",        "inner": None},
}


def shape_for(path: str) -> dict:
    tail = path.strip("/").split("/")[-1].lower()
    if tail not in _SHAPES:
        raise KeyError(f"no shape registered for endpoint {tail!r} (path {path!r})")
    return _SHAPES[tail]


def _obj_key(obj: dict) -> tuple:
    """Identity of a race / standings-list object across pages."""
    return (obj.get("season"), obj.get("round"))


def merge_pages(pages: list[list], shape: dict) -> list:
    """Concatenate pages, merging objects split across a page boundary."""
    inner = shape["inner"]
    if inner is None:
        return [row for page in pages for row in page]

    out: list = []
    index: dict = {}
    for page in pages:
        for obj in page:
            k = _obj_key(obj)
            if k not in index:
                copy = dict(obj)
                copy[inner] = list(obj.get(inner, []))
                index[k] = copy
                out.append(copy)
                continue
            target = index[k]
            if "inner2" in shape:
                _merge_inner2(target, obj, shape)
            else:
                target[inner].extend(obj.get(inner, []))
    return out


def _merge_inner2(target: dict, obj: dict, shape: dict) -> None:
    """Merge laps: a single lap's timings can span two pages."""
    inner, inner2, key = shape["inner"], shape["inner2"], shape["inner_key"]
    by_key = {lap.get(key): lap for lap in target[inner]}
    for lap in obj.get(inner, []):
        k = lap.get(key)
        if k in by_key:
            by_key[k][inner2].extend(lap.get(inner2, []))
        else:
            copy = dict(lap)
            copy[inner2] = list(lap.get(inner2, []))
            target[inner].append(copy)
            by_key[k] = copy


def count_rows(merged: list, shape: dict) -> int:
    """Count the rows `total` refers to."""
    inner = shape["inner"]
    if inner is None:
        return len(merged)
    if "inner2" in shape:
        return sum(len(lap.get(shape["inner2"], [])) for obj in merged for lap in obj.get(inner, []))
    return sum(len(obj.get(inner, [])) for obj in merged)
