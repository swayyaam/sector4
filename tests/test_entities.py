"""Tests for splitting shared constructorIds into distinct team entities."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from entities import GAP_YEARS, assign, constructor_blocks, team_entity_map, year_blocks  # noqa: E402


class TestYearBlocks:
    def test_contiguous_years_are_one_block(self):
        assert year_blocks([2024, 2025, 2026]) == [[2024, 2025, 2026]]

    def test_a_long_gap_starts_a_new_block(self):
        """Aston Martin: 1959-60 and 2021-26 are unrelated teams."""
        assert year_blocks([1959, 1960, 2021, 2022]) == [[1959, 1960], [2021, 2022]]

    def test_a_gap_of_exactly_the_threshold_does_not_split(self):
        assert year_blocks([2000, 2000 + GAP_YEARS]) == [[2000, 2000 + GAP_YEARS]]

    def test_a_gap_one_beyond_the_threshold_splits(self):
        assert year_blocks([2000, 2000 + GAP_YEARS + 1]) == [[2000], [2000 + GAP_YEARS + 1]]

    def test_duplicates_and_disorder_are_handled(self):
        assert year_blocks([2026, 2024, 2025, 2024]) == [[2024, 2025, 2026]]

    def test_empty(self):
        assert year_blocks([]) == []

    def test_sauber_three_spells(self):
        ys = list(range(1993, 2006)) + list(range(2010, 2019)) + [2024, 2025]
        assert [(b[0], b[-1]) for b in year_blocks(ys)] == [(1993, 2005), (2010, 2018), (2024, 2025)]


def _frames():
    races = pd.DataFrame({"raceId": [1, 2, 3, 4], "year": [1959, 1960, 2021, 2022]})
    results = pd.DataFrame({"raceId": [1, 2, 3, 4], "constructorId": [117, 117, 117, 117]})
    return races, results


class TestConstructorBlocks:
    def test_splits_a_reused_constructor_id(self):
        races, results = _frames()
        blocks = constructor_blocks([results], races)
        assert [(b[0], b[-1]) for b in blocks[117]] == [(1959, 1960), (2021, 2022)]

    def test_pools_years_across_tables(self):
        """A constructor can appear in standings for a race it has no results in."""
        races = pd.DataFrame({"raceId": [1, 2], "year": [1958, 1959]})
        a = pd.DataFrame({"raceId": [1], "constructorId": [10]})
        b = pd.DataFrame({"raceId": [2], "constructorId": [10]})
        blocks = constructor_blocks([a, b], races)
        assert blocks[10] == [[1958, 1959]]

    def test_ignores_frames_without_a_constructor_column(self):
        races, results = _frames()
        blocks = constructor_blocks([results, pd.DataFrame({"raceId": [1]}), None], races)
        assert 117 in blocks


class TestTeamEntityMap:
    def test_entity_ids_are_distinct_per_block(self):
        races, results = _frames()
        m = team_entity_map(constructor_blocks([results], races))
        assert m[(117, 1959)] == "117-1959"
        assert m[(117, 2021)] == "117-2021"
        assert m[(117, 1959)] != m[(117, 2021)]

    def test_covers_idle_years_inside_a_block(self):
        m = team_entity_map({5: [[2000, 2001, 2004]]})
        assert m[(5, 2002)] == "5-2000"      # gap inside the block still belongs to it

    def test_assign_labels_rows(self):
        races, results = _frames()
        m = team_entity_map(constructor_blocks([results], races))
        got = assign(results, races, m).tolist()
        assert got == ["117-1959", "117-1959", "117-2021", "117-2021"]

    def test_assign_returns_none_for_an_unknown_pair(self):
        races, results = _frames()
        other = pd.DataFrame({"raceId": [1], "constructorId": [999]})
        assert assign(other, races, team_entity_map(constructor_blocks([results], races)))[0] is None


PROCESSED = ROOT / "data" / "processed"


@pytest.mark.skipif(not (PROCESSED / "team_entities.csv").exists(),
                    reason="not built yet")
class TestBuiltEntities:
    def test_no_entity_spans_a_break(self):
        ents = pd.read_csv(PROCESSED / "team_entities.csv")
        assert ents["team_entity_id"].is_unique
        for r in ents.itertuples():
            assert r.last_year - r.first_year + 1 >= r.n_seasons

    def test_identity_breaks_produce_multiple_entities(self):
        ents = pd.read_csv(PROCESSED / "team_entities.csv")
        br = pd.read_csv(PROCESSED / "constructor_identity_breaks.csv")
        counts = ents.groupby("constructorId").size()
        for cid in br["constructorId"]:
            assert counts.get(cid, 0) > 1, f"constructorId {cid} was not split"
