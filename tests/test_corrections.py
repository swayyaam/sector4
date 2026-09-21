"""Tests for the corrections step. It mutates data, so its guard rails matter."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from corrections import apply_corrections, load_corrections  # noqa: E402
from eras import ERAS, era_for  # noqa: E402

PK = {"results": ["resultId"], "lap_times": ["raceId", "driverId", "lap"]}


def _tables():
    return {"results": pd.DataFrame({
        "resultId": [1, 2, 3],
        "milliseconds": [5690616.0, 4797566.0, None],
        "positionText": ["1", "D", "R"],
    })}


def _corr(**over):
    base = {"table": "results", "primary_key": "2", "column": "milliseconds",
            "old_value": "4797566.0", "new_value": "4797040",
            "reason": "test", "evidence_source": "FIA classification doc"}
    base.update(over)
    return pd.DataFrame([base])


class TestApplyCorrections:
    def test_applies_a_matching_correction(self):
        t, log = apply_corrections(_tables(), _corr(), PK)
        assert t["results"].loc[1, "milliseconds"] == 4797040
        assert len(log) == 1
        assert log[0]["evidence_source"] == "FIA classification doc"

    def test_refuses_when_old_value_does_not_match(self):
        """A stale correction must not silently rewrite the wrong value."""
        with pytest.raises(ValueError, match="stale or targets the wrong row"):
            apply_corrections(_tables(), _corr(old_value="999"), PK)

    def test_wildcard_old_value_skips_the_check(self):
        t, _ = apply_corrections(_tables(), _corr(old_value="*"), PK)
        assert t["results"].loc[1, "milliseconds"] == 4797040

    def test_refuses_when_key_matches_no_rows(self):
        with pytest.raises(ValueError, match="matched 0 rows"):
            apply_corrections(_tables(), _corr(primary_key="999"), PK)

    def test_refuses_unknown_table(self):
        with pytest.raises(KeyError):
            apply_corrections(_tables(), _corr(table="nope"), PK)

    def test_composite_key_needs_every_part(self):
        tables = {"lap_times": pd.DataFrame({"raceId": [1], "driverId": [2], "lap": [3], "position": [4]})}
        c = _corr(table="lap_times", primary_key="1|2|3", column="position",
                  old_value="4", new_value="5")
        t, _ = apply_corrections(tables, c, PK)
        assert t["lap_times"].loc[0, "position"] == 5

    def test_composite_key_with_wrong_arity_is_rejected(self):
        tables = {"lap_times": pd.DataFrame({"raceId": [1], "driverId": [2], "lap": [3], "position": [4]})}
        c = _corr(table="lap_times", primary_key="1|2", column="position", old_value="4", new_value="5")
        with pytest.raises(ValueError, match="needs 3 key part"):
            apply_corrections(tables, c, PK)

    def test_new_value_can_be_null(self):
        t, _ = apply_corrections(_tables(), _corr(new_value=r"\N"), PK)
        assert pd.isna(t["results"].loc[1, "milliseconds"])

    def test_empty_corrections_is_a_no_op(self):
        before = _tables()["results"].copy()
        t, log = apply_corrections(_tables(), pd.DataFrame(columns=list(_corr().columns)), PK)
        assert log == []
        pd.testing.assert_frame_equal(t["results"], before)


class TestLoadCorrections:
    def test_missing_file_gives_an_empty_frame(self, tmp_path):
        assert load_corrections(tmp_path / "nope.csv").empty

    def test_rejects_a_correction_with_no_evidence(self, tmp_path):
        p = tmp_path / "c.csv"
        p.write_text("table,primary_key,column,old_value,new_value,reason,evidence_source\n"
                     "results,1,points,10,25,because,\n")
        with pytest.raises(ValueError, match="evidence_source"):
            load_corrections(p)

    def test_rejects_missing_columns(self, tmp_path):
        p = tmp_path / "c.csv"
        p.write_text("table,primary_key\nresults,1\n")
        with pytest.raises(ValueError, match="missing required columns"):
            load_corrections(p)

    def test_the_real_corrections_file_is_valid(self):
        load_corrections()   # raises if malformed


class TestEras:
    def test_every_season_1950_to_2026_maps_to_an_era(self):
        for y in range(1950, 2027):
            assert era_for(y)

    def test_eras_are_contiguous_and_non_overlapping(self):
        for (f1, l1, _, _), (f2, _, _, _) in zip(ERAS, ERAS[1:]):
            assert l1 is not None and l1 + 1 == f2, f"gap or overlap between {f1} and {f2}"

    def test_2026_is_its_own_era(self):
        assert era_for(2026) == "2026_reset"
        assert era_for(2025) != era_for(2026)

    def test_the_last_era_is_open_ended(self):
        assert ERAS[-1][1] is None
        assert era_for(2030) == "2026_reset"
