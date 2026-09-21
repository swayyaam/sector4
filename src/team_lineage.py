"""Build data/processed/team_lineage.csv and constructor_identity_breaks.csv.

No constructorIds are merged. The lineage table records *succession* so a model
can optionally treat a chain as one continuing team; the identity-breaks table
records the opposite hazard, where Ergast reuses one constructorId for entities
that have nothing to do with each other.

Every row cites the source used to verify it.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

from entities import year_blocks  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed"

W = "https://en.wikipedia.org/wiki"
SRC_SAUBER = f"{W}/Sauber_Motorsport"
SRC_RB = f"{W}/Racing_Bulls"
SRC_AM = f"{W}/Aston_Martin_in_Formula_One"
SRC_ALPINE = f"{W}/Alpine_F1_Team"
SRC_MERC = f"{W}/Mercedes-Benz_in_Formula_One"
SRC_RBR = f"{W}/Red_Bull_Racing"
SRC_TEAMS = "https://www.formula1.com/en/teams"

# (ref, predecessor_ref, effective_year, relationship, note, source)
LINEAGE = [
    # --- Hinwil: Sauber -> Audi
    ("bmw_sauber", "sauber", 2006, "takeover", "BMW bought the Sauber team at the end of 2005", SRC_SAUBER),
    ("sauber", "bmw_sauber", 2010, "takeover", "BMW withdrew; the team reverted to Sauber ownership", SRC_SAUBER),
    ("alfa", "sauber", 2019, "rebrand", "Alfa Romeo title sponsorship; same Hinwil entity", SRC_SAUBER),
    ("sauber", "alfa", 2024, "rebrand", "Alfa Romeo branding ended; ran as Stake F1 Team Kick Sauber", SRC_SAUBER),
    ("audi", "sauber", 2026, "rebrand",
     "Audi acquired Sauber in 2024 and rebranded the SAME legal entity for 2026 - not a new team", SRC_SAUBER),
    # --- Faenza: Minardi -> Racing Bulls
    ("toro_rosso", "minardi", 2006, "takeover", "Red Bull bought Minardi", SRC_RB),
    ("alphatauri", "toro_rosso", 2020, "rebrand", "Renamed to promote Red Bull's AlphaTauri brand", SRC_RB),
    ("rb", "alphatauri", 2024, "rebrand", "Rebranded to Visa Cash App RB, then Racing Bulls from 2025", SRC_RB),
    # --- Silverstone: Jordan -> Aston Martin
    ("mf1", "jordan", 2006, "takeover", "Midland bought Jordan", SRC_AM),
    ("spyker_mf1", "mf1", 2006, "rebrand", "Mid-2006 renaming to Spyker MF1", SRC_AM),
    ("spyker", "spyker_mf1", 2007, "rebrand", "Full Spyker branding", SRC_AM),
    ("force_india", "spyker", 2008, "takeover", "Vijay Mallya's consortium bought Spyker", SRC_AM),
    ("racing_point", "force_india", 2019, "takeover",
     "Lawrence Stroll's consortium bought the team out of administration; the 59 points scored "
     "as Force India in 2018 were forfeited", SRC_AM),
    ("aston_martin", "racing_point", 2021, "rebrand",
     "Commercial rebranding under the same ownership. NOT related to the 1959-60 Aston Martin team, "
     "which shares this constructorId", SRC_AM),
    # --- Enstone: Toleman -> Alpine
    ("benetton", "toleman", 1986, "takeover", "Benetton Group bought Toleman", SRC_ALPINE),
    ("renault", "benetton", 2002, "takeover",
     "Renault bought the Enstone team in 2000 and renamed it for 2002. A different entity from the "
     "1977-85 Renault works team, which shares this constructorId", SRC_ALPINE),
    ("lotus_f1", "renault", 2012, "rebrand", "Genii Capital ownership, Lotus branding", SRC_ALPINE),
    ("renault", "lotus_f1", 2016, "takeover", "Renault bought the Enstone team back", SRC_ALPINE),
    ("alpine", "renault", 2021, "rebrand", "Renamed to promote Renault's Alpine sports-car brand", SRC_ALPINE),
    # --- Brackley: Tyrrell -> Mercedes
    ("bar", "tyrrell", 1999, "takeover", "BAR bought Tyrrell", SRC_MERC),
    ("honda", "bar", 2006, "takeover",
     "Honda took full ownership of BAR. A different entity from the 1964-68 Honda works team, "
     "which shares this constructorId", SRC_MERC),
    ("brawn", "honda", 2009, "takeover", "Ross Brawn's management buyout after Honda withdrew", SRC_MERC),
    ("mercedes", "brawn", 2010, "takeover",
     "Mercedes bought Brawn GP. NOT related to the 1954-55 Mercedes works team, which shares "
     "this constructorId", SRC_MERC),
    # --- Milton Keynes: Stewart -> Red Bull
    ("jaguar", "stewart", 2000, "takeover", "Ford bought Stewart and rebranded it Jaguar", SRC_RBR),
    ("red_bull", "jaguar", 2005, "takeover", "Red Bull bought Jaguar from Ford", SRC_RBR),
    # --- short-lived 2010s chains
    ("marussia", "virgin", 2012, "rebrand", "Marussia took majority ownership of Virgin Racing", f"{W}/Marussia_F1"),
    ("manor", "marussia", 2015, "takeover", "Team re-entered under Manor after administration", f"{W}/Manor_Motorsport"),
    ("caterham", "lotus_racing", 2012, "rebrand", "Tony Fernandes' team renamed from Lotus to Caterham", f"{W}/Caterham_F1"),
    # --- genuinely new entries
    ("haas", None, 2016, "new_entry", "New American constructor, no predecessor", SRC_TEAMS),
    ("hrt", None, 2010, "new_entry", "Hispania Racing, one of the 2010 new entrants", f"{W}/HRT_Formula_1_Team"),
    ("virgin", None, 2010, "new_entry", "Virgin Racing, one of the 2010 new entrants", f"{W}/Virgin_Racing"),
    ("lotus_racing", None, 2010, "new_entry", "Team Lotus (Fernandes), one of the 2010 new entrants", f"{W}/Team_Lotus_(2010-11)"),
    ("cadillac", None, 2026, "new_entry", "General Motors' Cadillac entered as the 11th team for 2026", SRC_TEAMS),
]


def main() -> int:
    c = pd.read_csv(OUT / "constructors.csv", keep_default_na=False, na_values=[r"\N", ""])
    ids = dict(zip(c["constructorRef"], c["constructorId"]))
    races = pd.read_csv(OUT / "races.csv", keep_default_na=False, na_values=[r"\N", ""])
    res = pd.read_csv(OUT / "results.csv", keep_default_na=False, na_values=[r"\N", ""], low_memory=False)
    yrs = res.merge(races[["raceId", "year"]], on="raceId").groupby("constructorId")["year"]

    rows, missing = [], []
    for ref, pred, year, rel, note, src in LINEAGE:
        if ref not in ids or (pred is not None and pred not in ids):
            missing.append((ref, pred))
            continue
        rows.append({
            "constructorId": ids[ref], "constructorRef": ref,
            "predecessor_constructorId": ids[pred] if pred else None,
            "predecessor_constructorRef": pred, "effective_year": year,
            "relationship": rel, "note": note, "evidence_source": src,
        })
    if missing:
        raise SystemExit(f"unknown constructorRef(s): {missing}")
    df = pd.DataFrame(rows).sort_values(["effective_year", "constructorRef"]).reset_index(drop=True)
    df.to_csv(OUT / "team_lineage.csv", index=False)
    print(f"wrote {len(df)} lineage rows -> team_lineage.csv")
    print(df["relationship"].value_counts().to_string())

    # ---- identity breaks: one constructorId used by unrelated entities
    breaks = []
    for cid, g in yrs:
        blocks = year_blocks(sorted(set(g)))
        if len(blocks) > 1:
            ref = c.loc[c["constructorId"] == cid, "constructorRef"].iloc[0]
            breaks.append({"constructorId": cid, "constructorRef": ref,
                           "n_blocks": len(blocks),
                           "active_blocks": " | ".join(f"{b[0]}-{b[-1]}" for b in blocks),
                           "largest_gap_years": max(b2[0] - b1[-1] for b1, b2 in zip(blocks, blocks[1:]))})
    bdf = pd.DataFrame(breaks).sort_values(["largest_gap_years"], ascending=False).reset_index(drop=True)
    # Flag the ones that matter for modern modelling.
    bdf["affects_modern_era"] = bdf["active_blocks"].str.contains(r"20[12]\d$", regex=True)
    bdf.to_csv(OUT / "constructor_identity_breaks.csv", index=False)
    print(f"\nwrote {len(bdf)} identity-break rows -> constructor_identity_breaks.csv")
    print(bdf[bdf["affects_modern_era"]][["constructorRef", "active_blocks", "largest_gap_years"]]
          .to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
