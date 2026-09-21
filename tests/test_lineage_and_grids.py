"""Tests for the grid scraper's parsing and the team-lineage table's integrity."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scrape_grids import parse, to_text  # noqa: E402

PROCESSED = ROOT / "data" / "processed"


# --------------------------------------------------------------- grid parsing
GRID_HTML = """
<html><body>
Pos. No. Driver Team Time
1 12 Kimi Antonelli ANT Mercedes 1:27.798
2 3 Max Verstappen VER Red Bull Racing 1:27.964
3 16 Charles Leclerc LEC Ferrari 1:28.143
4 1 Lando Norris NOR McLaren 1:28.183
5 87 Oliver Bearman BEA Haas F1 Team 1:29.567
6 30 Liam Lawson LAW Racing Bulls 1:29.499
Note - Bearman and Lawson required to start from pit lane after cars were
modified under Parc Ferme conditions.
OUR PARTNERS View all
</body></html>
"""

UNNAMED_NOTE_HTML = GRID_HTML.replace(
    "Note - Bearman and Lawson required to start from pit lane after cars were\nmodified under Parc Ferme conditions.",
    "Note - Hadjar granted permission to race after being disqualified from Qualifying. "
    "Required to start from the pit lane after use of additional power unit elements.")

NO_NOTE_HTML = GRID_HTML.replace(
    "Note - Bearman and Lawson required to start from pit lane after cars were\nmodified under Parc Ferme conditions.",
    "")


class TestGridParsing:
    def test_extracts_the_grid_rows(self):
        grid, _, _ = parse(to_text(GRID_HTML))
        assert [g["grid"] for g in grid] == [1, 2, 3, 4, 5, 6]
        assert [g["code"] for g in grid] == ["ANT", "VER", "LEC", "NOR", "BEA", "LAW"]

    def test_keeps_the_car_number_separate_from_the_position(self):
        grid, _, _ = parse(to_text(GRID_HTML))
        antonelli = grid[0]
        assert antonelli["grid"] == 1 and antonelli["number"] == 12

    def test_finds_the_pit_lane_sentence(self):
        _, sentences, _ = parse(to_text(GRID_HTML))
        assert len(sentences) == 1
        assert "pit lane" in sentences[0].lower()

    def test_a_page_with_no_note_yields_no_pit_lane_sentences(self):
        grid, sentences, note = parse(to_text(NO_NOTE_HTML))
        assert len(grid) == 6
        assert sentences == []

    def test_unnamed_pit_lane_sentence_is_detected_as_such(self):
        """The Miami 2026 shape: the sentence names nobody."""
        grid, sentences, note = parse(to_text(UNNAMED_NOTE_HTML))
        assert len(sentences) == 1
        named_in_sentence = [g["code"] for g in grid
                             if g["name"].split()[-1].lower() in sentences[0].lower()]
        assert named_in_sentence == []          # nothing attributable from the sentence alone
        assert "Hadjar" in note                  # but the note block names the subject

    def test_does_not_invent_rows_from_body_text(self):
        grid, _, _ = parse(to_text("<html><body>Nothing to see here</body></html>"))
        assert grid == []


# ------------------------------------------------------------- team lineage
@pytest.fixture(scope="module")
def data():
    import pandas as pd
    return (pd.read_csv(PROCESSED / "team_lineage.csv"),
            pd.read_csv(PROCESSED / "constructors.csv", keep_default_na=False,
                        na_values=[r"\N", ""]))


@pytest.mark.skipif(not (PROCESSED / "team_lineage.csv").exists(),
                    reason="team_lineage.csv not built yet")
class TestTeamLineage:
    def test_every_constructor_id_resolves(self, data):
        lin, cons = data
        ids = set(cons["constructorId"])
        assert set(lin["constructorId"]) <= ids
        preds = set(lin["predecessor_constructorId"].dropna().astype(int))
        assert preds <= ids

    def test_every_row_cites_a_source(self, data):
        lin, _ = data
        assert lin["evidence_source"].notna().all()
        assert (lin["evidence_source"].str.startswith("http")).all()

    def test_relationship_values_are_the_agreed_set(self, data):
        lin, _ = data
        assert set(lin["relationship"]) <= {"rebrand", "takeover", "new_entry"}

    def test_new_entries_have_no_predecessor(self, data):
        lin, _ = data
        new = lin[lin["relationship"] == "new_entry"]
        assert new["predecessor_constructorId"].isna().all()

    def test_successions_do_have_a_predecessor(self, data):
        lin, _ = data
        succ = lin[lin["relationship"] != "new_entry"]
        assert succ["predecessor_constructorId"].notna().all()

    def test_no_constructor_succeeds_itself(self, data):
        lin, _ = data
        same = lin[lin["constructorId"] == lin["predecessor_constructorId"]]
        assert len(same) == 0, f"self-succession rows: {same.to_dict('records')}"

    def test_the_named_modern_lineages_are_present(self, data):
        lin, cons = data
        ref = cons.set_index("constructorId")["constructorRef"]
        pairs = {(r.constructorRef, ref.get(r.predecessor_constructorId))
                 for r in lin.itertuples() if r.predecessor_constructorId == r.predecessor_constructorId}
        for want in [("audi", "sauber"), ("rb", "alphatauri"), ("sauber", "alfa"),
                     ("aston_martin", "racing_point"), ("alpine", "renault")]:
            assert want in pairs, f"missing lineage {want}"

    def test_no_ids_were_merged(self, data):
        """Lineage records succession; it must not collapse two ids into one."""
        lin, cons = data
        assert cons["constructorId"].is_unique
        assert cons["constructorRef"].is_unique
