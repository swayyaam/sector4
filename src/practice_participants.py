"""Build data/enriched/practice_participants.csv.

Drivers who only ever appear in practice are deliberately **not** given a
``driverId``: the drivers table stays race drivers only, matching Ergast. They
get their own identity here instead.

Two things are genuinely hard and are handled explicitly rather than guessed:

* **Identity.** FastF1 supplies no ``DriverId`` for a reserve, and Jolpica lists
  reserves with nothing but a name -- no code, no permanent number, no date of
  birth, no nationality. So there is no shared non-name key, and none is
  invented: a reserve is keyed on season + normalised name, or on where it
  appeared when FastF1 gives no name at all.
* **Team.** With no result row there is nothing authoritative to join to, so the
  team comes from an explicit reviewed map of (FastF1 team name -> constructor
  ref). Anything not in the map is reported, never guessed.

``driverId`` is filled only in the narrow case where a participant's car number
*and* name both match a driver who actually raced that season -- i.e. FastF1
simply failed to supply the ref for a regular driver.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

from ff1_map import IdMapper, norm  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ENRICHED = ROOT / "data" / "enriched"
OUT = ENRICHED / "practice_participants.csv"
APPEAR = ENRICHED / "practice_participant_appearances.csv"
GAPS = ENRICHED / "practice_participants_unresolved.csv"

# Entries FastF1 gives no name for, resolved against the official session
# classification. Keyed (raceId, session, car number) -> (name, constructorRef).
# Barcelona 2026 FP1: FastF1 supplied neither name nor team for seven cars.
OFFICIAL_PRACTICE_IDENTITY = {
    (1175, "Practice 1", "25"): ("Colton Herta", "cadillac"),
    (1175, "Practice 1", "36"): ("Ayumu Iwasa", "red_bull"),
    (1175, "Practice 1", "38"): ("Dino Beganovic", "ferrari"),
    (1175, "Practice 1", "67"): ("Leonardo Fornaroli", "mclaren"),
    (1175, "Practice 1", "72"): ("Frederik Vesti", "mercedes"),
    (1175, "Practice 1", "97"): ("Paul Aron", "audi"),
    # #46 is entered in FastF1's results but set no lap and does not appear in
    # the official classification, so it is deliberately left unresolved.
}
OFFICIAL_SOURCE = ("https://www.formula1.com/en/results/2026/races/1287/"
                   "barcelona-catalunya/practice/1")

# Explicit, reviewed: FastF1 team name -> our constructorRef.
# Names as FastF1 reports them; several differ from ours (FastF1 "Racing Bulls"
# is our "RB F1 Team", ref `rb`). Reviewed rather than heuristic because there
# is no result row to fall back on.
TEAM_NAME_TO_REF = {
    "alfa romeo": "alfa", "alfa romeo racing": "alfa", "alfa romeo ferrari": "alfa",
    "alphatauri": "alphatauri", "scuderia alphatauri": "alphatauri",
    "alpine": "alpine", "alpine renault": "alpine", "alpine f1 team": "alpine",
    "aston martin": "aston_martin", "aston martin aramco mercedes": "aston_martin",
    "audi": "audi",
    "cadillac": "cadillac",
    "ferrari": "ferrari", "scuderia ferrari": "ferrari",
    "force india": "force_india", "racing point force india": "force_india",
    "haas f1 team": "haas", "haas ferrari": "haas",
    "kick sauber": "sauber", "sauber": "sauber", "kick sauber ferrari": "sauber",
    "mclaren": "mclaren", "mclaren mercedes": "mclaren", "mclaren renault": "mclaren",
    "mercedes": "mercedes",
    "racing bulls": "rb", "rb": "rb", "visa cash app rb": "rb",
    "racing point": "racing_point", "racing point bwt mercedes": "racing_point",
    "red bull racing": "red_bull", "red bull": "red_bull",
    "renault": "renault",
    "toro rosso": "toro_rosso", "scuderia toro rosso": "toro_rosso",
    "williams": "williams", "williams mercedes": "williams",
}


def main() -> int:
    files = sorted((ENRICHED / "unmapped").glob("*.csv"))
    if not files:
        print("no unmapped records yet -- run the fetcher first")
        return 0
    u = pd.concat([pd.read_csv(f, keep_default_na=False, na_values=[""]) for f in files],
                  ignore_index=True)
    pp = u[u["kind"] == "practice_participant"].copy()
    if not len(pp):
        print("no practice participants recorded")
        return 0

    mapper = IdMapper()
    cref = {str(r.constructorRef): int(r.constructorId)
            for r in mapper.constructors.itertuples()}

    # ---- one row per appearance: a reserve can drive for more than one team
    # in a season (Paul Aron ran for Alpine and Audi in 2026), so the team is
    # attributed per session, never per participant.
    appearances, gaps = [], []
    identity: dict[str, dict] = {}
    for r in pp.itertuples():
        num = "" if pd.isna(r.number) else str(r.number)
        name = "" if pd.isna(r.name) else str(r.name).strip()
        team_name = "" if pd.isna(r.team) else str(r.team).strip()
        key, src = r.reserve_key, ""
        cid = None

        off = OFFICIAL_PRACTICE_IDENTITY.get((int(r.raceId), str(r.session), num))
        if off and not name:
            name, ref = off
            cid = cref.get(ref)
            key = f"{int(r.year)}_{norm(name).replace(' ', '_')}"
            src = f"official classification: {OFFICIAL_SOURCE}"
        if cid is None and team_name and team_name.lower() != "nan":
            ref = TEAM_NAME_TO_REF.get(norm(team_name))
            if ref and ref in cref:
                cid, src = cref[ref], f"reviewed map: {team_name!r} -> {ref}"
        if cid is None:
            gaps.append({"reserve_key": key, "raceId": int(r.raceId), "session": r.session,
                         "number": num, "name": name, "fastf1_team": team_name,
                         "issue": ("team name not in the reviewed map" if team_name
                                   else "FastF1 supplied no team and the official "
                                        "classification does not list this car")})
            src = "unresolved"
        appearances.append({"reserve_key": key, "raceId": int(r.raceId), "year": int(r.year),
                            "session": r.session, "car_number": num, "name": name,
                            "fastf1_team": team_name, "constructorId": cid,
                            "team_source": src, "is_race_driver": False})
        identity.setdefault(key, {"year": int(r.year), "name": name})
        if name and not identity[key]["name"]:
            identity[key]["name"] = name

    ap = pd.DataFrame(appearances).sort_values(["year", "raceId", "car_number"]).reset_index(drop=True)
    ap.to_csv(APPEAR, index=False)

    rows = []
    for key, info in identity.items():
        g = ap[ap["reserve_key"] == key]
        did = None
        name = info["name"]
        if name:
            pool = mapper.driver_seasons[mapper.driver_seasons["year"] == info["year"]]
            for n in sorted({x for x in g["car_number"] if x}):
                try:
                    num = int(float(n))
                except ValueError:
                    continue
                for c in {int(x) for x in pool.loc[pool["number"] == num, "driverId"]}:
                    if norm(mapper._surname[c]) == norm(name.split()[-1]):
                        did = c
                        break
                if did:
                    break
        rows.append({"reserve_key": key, "year": info["year"], "name": name,
                     "car_numbers": "|".join(sorted({x for x in g["car_number"] if x})),
                     "constructorIds": "|".join(sorted({str(int(x)) for x in
                                                        g["constructorId"].dropna()})),
                     "driverId": did, "is_race_driver": False,
                     "n_sessions": int(len(g)), "n_races": int(g["raceId"].nunique())})

    df = pd.DataFrame(rows).sort_values(["year", "reserve_key"]).reset_index(drop=True)
    df.to_csv(OUT, index=False)
    pd.DataFrame(gaps).to_csv(GAPS, index=False)

    print(f"practice participants: {len(df)}  -> {OUT}")
    print(f"  appearances      : {len(ap)} -> {APPEAR}")
    print(f"  named            : {int((df['name'].fillna('') != '').sum())}")
    print(f"  unnamed          : {int((df['name'].fillna('') == '').sum())}")
    print(f"  team resolved    : {int(ap['constructorId'].notna().sum())} of {len(ap)} appearances")
    print(f"  driverId filled  : {int(df['driverId'].notna().sum())} "
          f"(number+name matched a race driver; FastF1 just omitted the ref)")
    print(f"  unresolved       : {len(gaps)} -> {GAPS}")
    if len(df):
        print()
        print(df.groupby("year").agg(participants=("reserve_key", "size"),
                                     sessions=("n_sessions", "sum")).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
