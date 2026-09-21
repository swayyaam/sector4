"""Build and audit the Jolpica(string) -> Kaggle(integer) ID mappings.

Matching is on the natural keys the two datasets share: ``driverRef``,
``constructorRef``, ``circuitRef``, and the status label. Anything that does not
match becomes a *candidate* new entity -- reported for review, never silently
assigned in the merged output.

Entity sets come from rows that actually appear in a classification (results,
sprint results, qualifying), **not** from ``/{year}/drivers``. That endpoint
includes FP1-only drivers: 2025 lists 36 for a 20-car grid.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

from jolpica_client import JolpicaClient  # noqa: E402
from load import load_table  # noqa: E402
from transform import build_ref_map  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
IDMAP_DIR = ROOT / "data" / "processed" / "id_maps"


def collect_entities(client: JolpicaClient, seasons: list[int]) -> dict:
    """Gather every ref that appears in an actual classification."""
    drivers: dict[str, dict] = {}
    constructors: dict[str, dict] = {}
    circuits: dict[str, dict] = {}
    statuses: dict[int, str] = {}
    fp_only_drivers: dict[str, dict] = {}
    races: list[dict] = []

    for year in seasons:
        for race in client.get_all(f"{year}/races"):
            c = race["Circuit"]
            circuits[c["circuitId"]] = c
            races.append({"year": year, "round": int(race["round"]), "circuitRef": c["circuitId"],
                          "name": race["raceName"], "date": race["date"]})
        for endpoint, key in [(f"{year}/results", "Results"),
                              (f"{year}/sprint", "SprintResults"),
                              (f"{year}/qualifying", "QualifyingResults")]:
            for race in client.get_all(endpoint):
                for row in race.get(key, []):
                    drivers[row["Driver"]["driverId"]] = row["Driver"]
                    constructors[row["Constructor"]["constructorId"]] = row["Constructor"]
        for s in client.get_all(f"{year}/status"):
            statuses[int(s["statusId"])] = s["status"]
        # Anyone listed for the season but never classified = practice/test only.
        for d in client.get_all(f"{year}/drivers"):
            if d["driverId"] not in drivers:
                fp_only_drivers[d["driverId"]] = d

    return {"drivers": drivers, "constructors": constructors, "circuits": circuits,
            "statuses": statuses, "races": races, "fp_only_drivers": fp_only_drivers}


def audit(seasons: list[int] = (2024, 2025, 2026)) -> dict:
    client = JolpicaClient()
    ents = collect_entities(client, list(seasons))

    k_drivers = load_table("drivers")
    k_cons = load_table("constructors")
    k_circ = load_table("circuits")
    k_status = load_table("status")
    k_races = load_table("races")

    out: dict = {"entities": ents}

    # ---- drivers
    existing = dict(zip(k_drivers["driverRef"], k_drivers["driverId"]))
    mapping, new = build_ref_map(existing, list(ents["drivers"]), start_at=int(k_drivers["driverId"].max()) + 1)
    out["drivers"] = {"map": mapping, "new": new, "matched": len(ents["drivers"]) - len(new),
                      "total": len(ents["drivers"])}

    # ---- constructors
    existing = dict(zip(k_cons["constructorRef"], k_cons["constructorId"]))
    mapping, new = build_ref_map(existing, list(ents["constructors"]), start_at=int(k_cons["constructorId"].max()) + 1)
    out["constructors"] = {"map": mapping, "new": new, "matched": len(ents["constructors"]) - len(new),
                           "total": len(ents["constructors"])}

    # ---- circuits
    existing = dict(zip(k_circ["circuitRef"], k_circ["circuitId"]))
    mapping, new = build_ref_map(existing, list(ents["circuits"]), start_at=int(k_circ["circuitId"].max()) + 1)
    out["circuits"] = {"map": mapping, "new": new, "matched": len(ents["circuits"]) - len(new),
                       "total": len(ents["circuits"])}

    # ---- statuses: Jolpica reuses Ergast's integer ids, so this should be identity
    k_status_map = dict(zip(k_status["statusId"], k_status["status"]))
    same, conflict, brand_new = [], [], []
    for sid, label in sorted(ents["statuses"].items()):
        if sid in k_status_map:
            (same if k_status_map[sid] == label else conflict).append((sid, label, k_status_map.get(sid)))
        else:
            brand_new.append((sid, label))
    out["statuses"] = {"same": same, "conflict": conflict, "new": brand_new}

    # ---- races: new (year, round) pairs
    have = {(int(r.year), int(r.round)) for r in k_races.itertuples()}
    new_races = [r for r in ents["races"] if (r["year"], r["round"]) not in have]
    out["races"] = {"new": sorted(new_races, key=lambda r: (r["year"], r["round"])),
                    "overlap": len(ents["races"]) - len(new_races),
                    "start_at": int(k_races["raceId"].max()) + 1}

    # ---- metadata conflicts on entities that DO match
    conflicts = []
    kd = k_drivers.set_index("driverRef")
    for ref, jd in sorted(ents["drivers"].items()):
        if ref not in kd.index:
            continue
        row = kd.loc[ref]
        for kcol, jkey in [("forename", "givenName"), ("surname", "familyName"),
                           ("dob", "dateOfBirth"), ("nationality", "nationality"), ("code", "code")]:
            kv, jv = row[kcol], jd.get(jkey)
            if pd.isna(kv):
                kv = None
            if jv is not None and kv is not None and str(kv) != str(jv):
                conflicts.append({"entity": "driver", "ref": ref, "field": kcol,
                                  "kaggle": str(kv), "jolpica": str(jv)})
        knum = row["number"]
        jnum = jd.get("permanentNumber")
        if jnum is not None and not pd.isna(knum) and int(knum) != int(jnum):
            conflicts.append({"entity": "driver", "ref": ref, "field": "number",
                              "kaggle": str(int(knum)), "jolpica": str(jnum)})
    kc = k_cons.set_index("constructorRef")
    for ref, jc in sorted(ents["constructors"].items()):
        if ref not in kc.index:
            continue
        for kcol, jkey in [("name", "name"), ("nationality", "nationality")]:
            kv, jv = kc.loc[ref][kcol], jc.get(jkey)
            if jv is not None and str(kv) != str(jv):
                conflicts.append({"entity": "constructor", "ref": ref, "field": kcol,
                                  "kaggle": str(kv), "jolpica": str(jv)})
    out["metadata_conflicts"] = conflicts
    return out


def write_maps(a: dict) -> None:
    IDMAP_DIR.mkdir(parents=True, exist_ok=True)
    for kind, refcol, idcol in [("drivers", "driverRef", "driverId"),
                                ("constructors", "constructorRef", "constructorId"),
                                ("circuits", "circuitRef", "circuitId")]:
        used = set(a["entities"][kind])
        rows = [{refcol: r, idcol: i, "is_new": r in {n["ref"] for n in a[kind]["new"]}}
                for r, i in sorted(a[kind]["map"].items()) if r in used]
        pd.DataFrame(rows).to_csv(IDMAP_DIR / f"{kind}.csv", index=False)


if __name__ == "__main__":
    a = audit()
    for kind in ("drivers", "constructors", "circuits"):
        d = a[kind]
        print(f"=== {kind}: {d['matched']}/{d['total']} matched an existing ref, {len(d['new'])} new ===")
        for n in d["new"]:
            print(f"    NEW  {n['ref']:<24} -> id {n['id']}")
    print()
    print("=== statuses ===")
    print(f"    identical id+label : {len(a['statuses']['same'])}")
    print(f"    id reused, label differs: {len(a['statuses']['conflict'])} {a['statuses']['conflict']}")
    print(f"    genuinely new      : {a['statuses']['new']}")
    print()
    r = a["races"]
    print(f"=== races: {r['overlap']} overlap existing, {len(r['new'])} new (ids from {r['start_at']}) ===")
    for x in r["new"][:6]:
        print(f"    {x['year']} R{x['round']:<2} {x['name']}")
    print(f"    ... {len(r['new'])} total")
    print()
    print(f"=== metadata conflicts on matched entities: {len(a['metadata_conflicts'])} ===")
    for c in a["metadata_conflicts"][:40]:
        print(f"    {c['entity']:<12} {c['ref']:<20} {c['field']:<12} kaggle={c['kaggle']!r:<28} jolpica={c['jolpica']!r}")
    print()
    print(f"=== FP1/test-only drivers (listed for a season, never classified): {len(a['entities']['fp_only_drivers'])} ===")
    print("   ", ", ".join(sorted(a["entities"]["fp_only_drivers"])))
