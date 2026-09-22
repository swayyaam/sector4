"""Build the site's data files from the real pipeline output.

Replaces the mock fixtures in web/src/data/mock with real drivers, teams,
circuits, races and predictions. Everything written here is a model output or
Ergast-schema reference data, both of which may be published; no FastF1 timing
value reaches the site. See DATA_LICENSE.md.

The sample-data banner is driven by `is_mock` in site_meta.json, which this
script sets to false. It is false only because every number it writes comes
from the pipeline -- if a field cannot be filled from real data, it is left
null and the page renders the absence rather than a plausible substitute.

Usage:
    python src/build_site_data.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import features as F  # noqa: E402
import revisions as REV  # noqa: E402
from predict import OUT as PRED_DIR, upcoming_race  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "web" / "src" / "data" / "live"
MOCK = ROOT / "web" / "src" / "data" / "mock"
SEASONS = (2026,)

# Team colours are a presentation choice, not data, and are carried over from
# the fixture where one exists. A team with no entry gets the neutral ink so a
# missing colour cannot be mistaken for a livery.
NEUTRAL = ("#5b616e", "#5b616e")


def _slug(name: str) -> str:
    out = []
    for ch in name.lower():
        out.append(ch if ch.isalnum() else "-")
    return "-".join(w for w in "".join(out).split("-") if w)


def load_mock_colours() -> dict[str, tuple[str, str]]:
    path = MOCK / "reference.json"
    if not path.exists():
        return {}
    ref = json.loads(path.read_text())
    return {t["team_entity_id"]: (t["colour"], t["colour_on_light"]) for t in ref["teams"]}


def schedule_rows(seasons: tuple[int, ...], known: set[tuple[int, int]]) -> list[dict]:
    """Races that are scheduled but have not run.

    The site has to be able to show a prediction for a race that has not
    happened -- that is the entire point of publishing one in advance -- so the
    schedule is read from the Jolpica cache and the provisional raceId is the
    same one predict.py recorded. It is replaced by the real one the moment
    build_processed.py mints it.
    """
    from jolpica_client import JolpicaClient

    races = F._rd(F.PROCESSED / "races.csv")
    circuits = F._rd(F.PROCESSED / "circuits.csv")
    nxt = int(races["raceId"].max()) + 1
    client = JolpicaClient()
    out = []
    for season in seasons:
        for r in sorted(client.get_all(f"{season}/races"), key=lambda x: int(x["round"])):
            rnd = int(r["round"])
            if (season, rnd) in known:
                continue
            match = circuits[circuits["circuitRef"] == r["Circuit"]["circuitId"]]
            if match.empty:
                continue
            time = r.get("time") or "00:00:00Z"
            out.append({
                "race_id": nxt, "season": season, "round": rnd, "name": r["raceName"],
                "slug": _slug(r["raceName"]), "circuit_id": int(match.iloc[0]["circuitId"]),
                "starts_at": f"{r['date']}T{time}",
                "regs_era": str(races.loc[races["year"] == season, "regs_era"].iloc[0]),
                "_sessions": [
                    {"name": label, "starts_at": f"{s['date']}T{s.get('time') or '00:00:00Z'}"}
                    for key, label in (("FirstPractice", "Practice 1"),
                                       ("SecondPractice", "Practice 2"),
                                       ("ThirdPractice", "Practice 3"),
                                       ("Qualifying", "Qualifying"))
                    if (s := r.get(key))
                ] + [{"name": "Race", "starts_at": f"{r['date']}T{time}"}],
            })
            nxt += 1
    return out


def build_reference(races_wanted: set[int], extra_circuits: set[int] = frozenset()) -> dict:
    drivers = F._rd(F.PROCESSED / "drivers.csv")
    constructors = F._rd(F.PROCESSED / "constructors.csv")
    circuits = F._rd(F.PROCESSED / "circuits.csv")
    races = F._rd(F.PROCESSED / "races.csv")
    results = F._rd(F.PROCESSED / "results.csv")
    entities = F._rd(F.PROCESSED / "team_entities.csv")
    colours = load_mock_colours()
    mock_circuits = {}
    if (MOCK / "reference.json").exists():
        mock_circuits = {c["circuitRef"]: c
                         for c in json.loads((MOCK / "reference.json").read_text())["circuits"]}

    races = races[races["raceId"].isin(races_wanted)]
    res = results[results["raceId"].isin(races_wanted)]
    driver_ids = set(res["driverId"].astype(int))
    entity_ids = set(res["team_entity_id"].dropna().astype(str))

    out_drivers = []
    for _, d in drivers[drivers["driverId"].isin(driver_ids)].iterrows():
        num = pd.to_numeric(d.get("number"), errors="coerce")
        out_drivers.append({
            "driverId": int(d["driverId"]), "driverRef": str(d["driverRef"]),
            "code": str(d["code"]) if pd.notna(d.get("code")) else None,
            "permanent_number": int(num) if pd.notna(num) else None,
            "forename": str(d["forename"]), "surname": str(d["surname"]),
            "nationality": str(d["nationality"]),
            # No driver photograph is published. Wikimedia Commons images were
            # licensed for it, but none has been sourced and reviewed yet, and
            # an unreviewed image is worse than none.
            "photo": None,
        })

    out_teams = []
    for eid in sorted(entity_ids):
        row = entities[entities["team_entity_id"] == eid]
        if row.empty:
            continue
        row = row.iloc[0]
        cid = int(row["constructorId"])
        con = constructors[constructors["constructorId"] == cid].iloc[0]
        colour, on_light = colours.get(eid, NEUTRAL)
        name = str(con["name"])
        out_teams.append({
            "team_entity_id": eid, "constructorId": cid,
            "constructorRef": str(con["constructorRef"]), "name": name,
            "short_name": name[:16],
            "season": int(res.loc[res["team_entity_id"] == eid, "raceId"].map(
                races.set_index("raceId")["year"]).max()),
            "colour": colour, "colour_on_light": on_light,
        })

    out_circuits = []
    # Scheduled races count too: a reference that omits the circuit of a race
    # it lists is internally inconsistent, and the validator says so.
    for cid in sorted(set(races["circuitId"].astype(int)) | set(extra_circuits)):
        c = circuits[circuits["circuitId"] == cid].iloc[0]
        ref = str(c["circuitRef"])
        geo = mock_circuits.get(ref, {})
        out_circuits.append({
            "circuit_id": cid, "circuitRef": ref, "name": str(c["name"]),
            "locality": str(c["location"]), "country": str(c["country"]),
            "lat": float(c["lat"]), "lng": float(c["lng"]),
            "track_path": geo.get("track_path"),
            "track_view_box": geo.get("track_view_box"),
            "track_credit_id": geo.get("track_credit_id"),
        })

    out_races = []
    for _, r in races.sort_values(["year", "round"]).iterrows():
        date, time = str(r["date"]), r.get("time")
        starts = f"{date}T{time}" if pd.notna(time) else f"{date}T00:00:00Z"
        out_races.append({
            "race_id": int(r["raceId"]), "season": int(r["year"]), "round": int(r["round"]),
            "name": str(r["name"]), "slug": _slug(str(r["name"])),
            "circuit_id": int(r["circuitId"]), "starts_at": starts,
            "regs_era": str(r["regs_era"]),
        })

    return {"drivers": out_drivers, "teams": out_teams,
            "circuits": out_circuits, "races": out_races}


def published_commit(path: Path) -> str | None:
    """The commit that first added this file: the proof of when it was public.

    generated_at is written by the program and could say anything; the commit
    that introduced the file is recorded by git and pushed to a remote. The
    site links to this one.
    """
    import subprocess

    try:
        rel = path.resolve().relative_to(ROOT).as_posix()
        out = subprocess.run(["git", "log", "--diff-filter=A", "--format=%H", "--", rel],
                             cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
        return out[-1] if out else None
    except Exception:
        return None


def revision_history(revs: list[tuple[int, Path, dict]], chosen_rev: int | None,
                     late: set[int]) -> list[dict]:
    return [{
        "revision": rev, "file": path.name, "generated_at": pred["generated_at"],
        "published_commit": published_commit(path),
        "supersedes": pred.get("supersedes"), "superseded_by": pred.get("superseded_by"),
        "reason": pred.get("revision_reason"),
        "effective": rev == chosen_rev, "late": rev in late,
    } for rev, path, pred in revs]


def site_prediction(pred: dict, race_id: int, result: dict | None,
                    path: Path | None = None, history: list[dict] | None = None) -> dict:
    return {
        "race_id": race_id, "season": pred["season"], "round": pred["round"],
        "snapshot": pred["snapshot"], "generated_at": pred["generated_at"],
        "model_version": pred["model_version"], "data_version": pred["data_version"],
        "commit_sha": pred["commit_sha"], "is_mock": False,
        "model_features": pred["model_features"], "model_note": pred["model_note"],
        "revision": int(pred.get("revision", 1)),
        "published_commit": published_commit(path) if path else None,
        "revisions": history or [],
        "drivers": pred["drivers"], "result": result,
    }


def main() -> int:
    races = F._rd(F.PROCESSED / "races.csv")
    ledger_path = PRED_DIR / "track_record.json"
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {"races": []}
    scored = {(e["season"], e["round"], e["snapshot"]): e for e in ledger["races"]}

    preds, wanted, upcoming = [], set(), {}
    # One entry per race and snapshot: the revision that counts, carrying the
    # history of every revision beside it. Listing each revision as its own
    # prediction would put two pre-weekend calls on one race page.
    groups = sorted({(int(path.parent.name), *REV.parse_name(path)[:2])
                     for path in REV.all_prediction_files(PRED_DIR)})
    for season, rnd, snapshot in groups:
        revs = REV.revisions(season, rnd, snapshot, PRED_DIR)
        chosen, late = REV.effective(season, rnd, snapshot, PRED_DIR)
        if chosen is None:
            print(f"  {season} R{rnd} {snapshot}: every revision is after the deadline; "
                  "nothing on-time to show")
            continue
        chosen_rev, path, pred = chosen
        history = revision_history(revs, chosen_rev, {r for r, _, _ in late})
        row = races[(races["year"] == season) & (races["round"] == rnd)]
        if row.empty:
            # Not run yet: the schedule supplies the race, and the provisional
            # id matches the one recorded in the prediction file.
            upcoming[(season, rnd)] = pred
            race_id = pred["race_id"]
        else:
            race_id = int(row.iloc[0]["raceId"])
            wanted.add(race_id)
        entry = scored.get((season, rnd, pred["snapshot"]))
        result = None
        if entry:
            rp = PRED_DIR / "results" / f"{season}-{rnd:02d}.json"
            drivers = json.loads(rp.read_text())["drivers"] if rp.exists() else []
            result = {
                "scored_at": entry["scored_at"], "drivers": drivers,
                "log_loss": entry["model"]["log_loss"], "brier": entry["model"]["brier"],
                "winner_hit": bool(entry["model"]["winner_hit"] >= 0.5),
                "podium_hits": int(round(entry["model"]["podium_hits"])),
                "baseline": {"name": entry["baseline"]["name"],
                             **{k: entry["baseline"][k]
                                for k in ("log_loss", "brier", "winner_hit", "podium_hits")}},
            }
        preds.append(site_prediction(pred, race_id, result, path, history))

    if not preds:
        print("no predictions can reach the site yet")
        return 1

    # Reference covers every race with a prediction, plus the completed season
    # so the track record and standings-derived pages have their history.
    wanted |= set(races.loc[races["year"].isin(SEASONS), "raceId"].astype(int))
    known = {(int(r["year"]), int(r["round"]))
             for _, r in races[races["raceId"].isin(wanted)].iterrows()}
    future = schedule_rows(SEASONS, known)
    reference = build_reference(wanted, {r["circuit_id"] for r in future})
    sessions_by_race = {r["race_id"]: r.pop("_sessions") for r in future}
    reference["races"].extend(future)
    reference["races"].sort(key=lambda r: (r["season"], r["round"]))

    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / "reference.json").write_text(json.dumps(reference, indent=2) + "\n")
    for p in preds:
        name = f"prediction-{p['season']}-{p['round']}-{p['snapshot']}.json"
        (SITE / name).write_text(json.dumps(p, indent=2) + "\n")

    done = [p for p in preds if p["result"]]
    latest = max((p for p in done), key=lambda p: (p["season"], p["round"]), default=None)
    meta = {
        "data_version": preds[0]["data_version"],
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "is_mock": False,
        "last_completed_race": None,
        "next_race": None,
    }
    if latest:
        r = next(x for x in reference["races"] if x["race_id"] == latest["race_id"])
        meta["last_completed_race"] = {k: r[k] for k in
                                       ("race_id", "season", "round", "name", "slug",
                                        "circuit_id", "starts_at")}
    upcoming_ids = {p["race_id"] for p in preds if p["result"] is None}
    following = sorted((r for r in reference["races"] if r["race_id"] in upcoming_ids),
                       key=lambda r: (r["season"], r["round"]))
    if following:
        r = following[0]
        meta["next_race"] = {**{k: r[k] for k in ("race_id", "season", "round", "name", "slug",
                                                  "circuit_id", "starts_at")},
                             "sessions": sessions_by_race.get(r["race_id"],
                                                              [{"name": "Race",
                                                                "starts_at": r["starts_at"]}])}
    (SITE / "site_meta.json").write_text(json.dumps(meta, indent=2) + "\n")

    print(f"  reference: {len(reference['drivers'])} drivers, {len(reference['teams'])} teams, "
          f"{len(reference['races'])} races, {len(reference['circuits'])} circuits")
    print(f"  predictions: {len(preds)} ({len(done)} scored)")
    print(f"  -> {SITE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
