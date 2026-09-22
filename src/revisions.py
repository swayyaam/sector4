"""Prediction revisions: append-only, and one rule for which one counts.

A committed prediction is part of the record, so it is never rewritten. If one
has to change before its session -- a bug found, a data fix -- the change is a
new file with a revision suffix:

    predictions/2026/15-pre_weekend.json       revision 1
    predictions/2026/15-pre_weekend-r2.json    revision 2, supersedes r1

The new file carries `supersedes` and `revision_reason`. The old one gains
`superseded_by` and `superseded_reason` and nothing else: those two pointers are
the only in-place change ever allowed, and they are excluded from the content
digest so the audit can prove the prediction itself never moved.

**Which revision counts.** The latest one generated before the session starts.
Anything timestamped after that could have seen the session and is ignored --
reported, never scored. The deadline is per snapshot:

* pre_weekend      -> the first session of the weekend. Its whole claim is
                      "before any car runs".
* post_qualifying  -> race start.

Writing, scoring and site-building all go through `effective()`, so the three
cannot disagree about which prediction is the real one.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "predictions"

# The only fields that may be added to a file after it is committed.
HASH_EXCLUDED = ("superseded_by", "superseded_reason")
SNAPSHOTS = ("pre_weekend", "post_qualifying")
_NAME = re.compile(r"^(?P<round>\d{2})-(?P<snapshot>pre_weekend|post_qualifying)"
                   r"(?:-r(?P<rev>\d+))?\.json$")


# --------------------------------------------------------------------- files
def revision_path(season: int, rnd: int, snapshot: str, revision: int = 1,
                  out: Path | None = None) -> Path:
    base = out if out is not None else OUT
    suffix = "" if revision == 1 else f"-r{revision}"
    return base / str(season) / f"{rnd:02d}-{snapshot}{suffix}.json"


def parse_name(path: Path) -> tuple[int, str, int] | None:
    m = _NAME.match(path.name)
    if not m:
        return None
    return int(m["round"]), m["snapshot"], int(m["rev"] or 1)


def revisions(season: int, rnd: int, snapshot: str,
              out: Path | None = None) -> list[tuple[int, Path, dict]]:
    """Every published revision for one race and snapshot, oldest first."""
    base = (out if out is not None else OUT) / str(season)
    found = []
    for path in sorted(base.glob(f"{rnd:02d}-{snapshot}*.json")):
        parsed = parse_name(path)
        if parsed and parsed[0] == rnd and parsed[1] == snapshot:
            found.append((parsed[2], path, json.loads(path.read_text())))
    return sorted(found, key=lambda t: t[0])


def all_prediction_files(out: Path | None = None) -> list[Path]:
    base = out if out is not None else OUT
    return sorted(p for p in base.glob("*/*.json") if parse_name(p))


def content_digest(pred: dict) -> str:
    """sha256 of the prediction with the two late-addable pointers removed."""
    body = {k: v for k, v in pred.items() if k not in HASH_EXCLUDED}
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode()).hexdigest()


# ------------------------------------------------------------------ deadlines
def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _at(date: str | None, time: str | None) -> datetime | None:
    if not date or str(date) in ("nan", "None"):
        return None
    t = time if time and str(time) not in ("nan", "None") else "00:00:00Z"
    t = t if t.endswith("Z") else f"{t}Z"
    return _parse(f"{date}T{t}")


def sessions(season: int, rnd: int) -> dict[str, datetime]:
    """Session start times, from our own table if the race has run, otherwise
    from the Jolpica schedule cache."""
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    import features as F

    races = F._rd(F.PROCESSED / "races.csv")
    row = races[(races["year"] == season) & (races["round"] == rnd)]
    if len(row):
        r = row.iloc[0]
        got = {"Practice 1": _at(r.get("fp1_date"), r.get("fp1_time")),
               "Practice 2": _at(r.get("fp2_date"), r.get("fp2_time")),
               "Practice 3": _at(r.get("fp3_date"), r.get("fp3_time")),
               "Sprint": _at(r.get("sprint_date"), r.get("sprint_time")),
               "Qualifying": _at(r.get("quali_date"), r.get("quali_time")),
               "Race": _at(r.get("date"), r.get("time"))}
        return {k: v for k, v in got.items() if v is not None}

    from jolpica_client import JolpicaClient

    for r in JolpicaClient().get_all(f"{season}/races"):
        if int(r["round"]) != rnd:
            continue
        got = {"Race": _at(r["date"], r.get("time"))}
        for key, label in (("FirstPractice", "Practice 1"), ("SecondPractice", "Practice 2"),
                           ("ThirdPractice", "Practice 3"), ("SprintQualifying", "Sprint Qualifying"),
                           ("Sprint", "Sprint"), ("Qualifying", "Qualifying")):
            if r.get(key):
                got[label] = _at(r[key]["date"], r[key].get("time"))
        return {k: v for k, v in got.items() if v is not None}
    raise LookupError(f"{season} round {rnd} is not in the schedule")


def deadline(season: int, rnd: int, snapshot: str,
             schedule: dict[str, datetime] | None = None) -> datetime:
    s = schedule if schedule is not None else sessions(season, rnd)
    if snapshot == "pre_weekend":
        return min(s.values())
    return s["Race"]


# ------------------------------------------------------------ which one counts
def effective(season: int, rnd: int, snapshot: str, out: Path | None = None,
              schedule: dict[str, datetime] | None = None
              ) -> tuple[tuple[int, Path, dict] | None, list[tuple[int, Path, dict]]]:
    """(the revision that counts, the revisions ignored for being late)."""
    revs = revisions(season, rnd, snapshot, out)
    if not revs:
        return None, []
    cutoff = deadline(season, rnd, snapshot, schedule)
    on_time = [r for r in revs if _parse(r[2]["generated_at"]) < cutoff]
    late = [r for r in revs if _parse(r[2]["generated_at"]) >= cutoff]
    return (on_time[-1] if on_time else None), late


# ----------------------------------------------------------------- the audit
def _git(*args: str, repo: Path | None = None) -> str:
    return subprocess.run(["git", *args], cwd=repo or ROOT, capture_output=True, text=True,
                          check=True).stdout


def history_is_available() -> bool:
    try:
        return _git("rev-parse", "--is-shallow-repository").strip() == "false"
    except Exception:
        return False


def audit_history(path: Path, ref: str = "HEAD", repo: Path | None = None) -> list[str]:
    """Every way this file's committed history breaks the append-only rule.

    Walks each version of the file reachable from `ref` and requires the
    prediction content to be identical in all of them, and `superseded_by` to
    go from absent to a value at most once and never change after. Empty list
    means the file has only ever been appended to.
    """
    root = (repo or ROOT).resolve()
    rel = path.resolve().relative_to(root).as_posix()
    shas = [s for s in _git("log", "--format=%H", ref, "--", rel, repo=root).split() if s]
    problems: list[str] = []
    versions = []
    for sha in reversed(shas):                      # oldest first
        try:
            versions.append((sha, json.loads(_git("show", f"{sha}:{rel}", repo=root))))
        except subprocess.CalledProcessError:
            continue                                 # deleted in this commit
    if not versions:
        return problems
    first_sha, first = versions[0]
    base = content_digest(first)
    pointer = first.get("superseded_by")
    for sha, v in versions[1:]:
        if content_digest(v) != base:
            problems.append(f"{rel}: prediction content changed in {sha[:10]} "
                            f"(first published in {first_sha[:10]})")
        now = v.get("superseded_by")
        if pointer is not None and now != pointer:
            problems.append(f"{rel}: superseded_by changed from {pointer!r} to {now!r} "
                            f"in {sha[:10]}")
        pointer = now if now is not None else pointer
    return problems


def audit_links(out: Path | None = None) -> list[str]:
    """supersedes / superseded_by must point at each other, one to one."""
    problems = []
    groups: dict[tuple[int, int, str], list[tuple[int, Path, dict]]] = {}
    for path in all_prediction_files(out):
        season = int(path.parent.name)
        rnd, snap, rev = parse_name(path)
        groups.setdefault((season, rnd, snap), []).append((rev, path, json.loads(path.read_text())))
    for key, revs in groups.items():
        revs.sort(key=lambda t: t[0])
        numbers = [r[0] for r in revs]
        if numbers != list(range(1, len(revs) + 1)):
            problems.append(f"{key}: revisions {numbers} are not 1..n without gaps")
        for (ra, pa, a), (rb, pb, b) in zip(revs, revs[1:]):
            if a.get("superseded_by") != pb.name:
                problems.append(f"{pa.name} should be superseded_by {pb.name}, "
                                f"has {a.get('superseded_by')!r}")
            if b.get("supersedes") != pa.name:
                problems.append(f"{pb.name} should supersede {pa.name}, has {b.get('supersedes')!r}")
            if not b.get("revision_reason"):
                problems.append(f"{pb.name} has no revision_reason")
        if revs and revs[-1][2].get("superseded_by"):
            problems.append(f"{revs[-1][1].name} is the latest revision but claims to be superseded")
    return problems


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
