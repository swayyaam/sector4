"""Unit tests for the Jolpica -> Kaggle transform functions."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from transform import (  # noqa: E402
    COLUMNS,
    NULL,
    build_ref_map,
    encode_position,
    fmt,
    is_gap,
    parse_duration_ms,
    recompute_constructor_points,
    recompute_driver_points,
    to_csv_line,
)


# ------------------------------------------------------------- time parsing
class TestParseDuration:
    @pytest.mark.parametrize("text,expected", [
        ("38.109", 38_109),                 # seconds only (a pit stop)
        ("26.898", 26_898),
        ("1:38.109", 98_109),               # M:SS.mmm (a lap)
        ("1:42:06.304", 6_126_304),         # H:MM:SS.mmm (a race)
        ("0:00.001", 1),
        ("2:05:07.547", 7_507_547),         # red-flagged lap, needs the hours branch
    ])
    def test_absolute(self, text, expected):
        assert parse_duration_ms(text) == expected

    @pytest.mark.parametrize("text,expected", [
        ("+0.895", 895),
        ("+12.773", 12_773),
        ("+1:03.011", 63_011),
    ])
    def test_gap(self, text, expected):
        assert parse_duration_ms(text) == expected

    @pytest.mark.parametrize("text", [None, "", NULL, "not a time", "DNF", "1:2:3:4.000"])
    def test_unparseable_returns_none_never_guesses(self, text):
        assert parse_duration_ms(text) is None

    def test_fractional_digits_are_left_padded_to_milliseconds(self):
        # "1.5" is 1.5 s = 1500 ms, not 1005 ms.
        assert parse_duration_ms("1.5") == 1_500
        assert parse_duration_ms("1.05") == 1_050
        assert parse_duration_ms("1.005") == 1_005

    def test_is_gap(self):
        assert is_gap("+0.895")
        assert not is_gap("1:42:06.304")
        assert not is_gap(None)

    def test_kaggle_roundtrip_values(self):
        """Values taken straight from the Kaggle CSVs must reparse exactly."""
        assert parse_duration_ms("1:38.109") == 98_109      # lap_times row 1
        assert parse_duration_ms("26.898") == 26_898        # pit_stops row 1
        assert parse_duration_ms("1:34:50.616") == 5_690_616  # results row 1


# --------------------------------------------------------- position encoding
class TestEncodePosition:
    def test_classified_finisher(self):
        assert encode_position("1", "1") == (1, "1", 1)
        assert encode_position("10", "10") == (10, "10", 10)

    def test_retired_has_null_position_but_keeps_order(self):
        # Jolpica reports position=15 with positionText='R'; Kaggle's `position`
        # must be null because the driver is not in the classification.
        assert encode_position("15", "R") == (None, "R", 15)

    @pytest.mark.parametrize("code", ["R", "D", "W", "N", "F", "E"])
    def test_all_non_numeric_codes_null_the_position(self, code):
        pos, pt, order = encode_position("20", code)
        assert pos is None
        assert pt == code
        assert order == 20

    def test_position_order_is_always_populated(self):
        for pt in ["1", "R", "D"]:
            assert encode_position("7", pt)[2] == 7

    def test_missing_position(self):
        assert encode_position(None, "R") == (None, "R", None)


# --------------------------------------------------------------- id mapping
class TestBuildRefMap:
    def test_existing_refs_keep_their_ids(self):
        existing = {"hamilton": 1, "max_verstappen": 830}
        mapping, new = build_ref_map(existing, ["hamilton", "max_verstappen"], start_at=900)
        assert mapping["hamilton"] == 1
        assert mapping["max_verstappen"] == 830
        assert new == []

    def test_new_refs_get_sequential_ids_after_the_max(self):
        mapping, new = build_ref_map({"hamilton": 1}, ["hamilton", "bortoleto", "hadjar"], start_at=862)
        # sorted order: bortoleto, hadjar
        assert mapping["bortoleto"] == 862
        assert mapping["hadjar"] == 863
        assert [n["ref"] for n in new] == ["bortoleto", "hadjar"]

    def test_assignment_is_deterministic_regardless_of_input_order(self):
        a, _ = build_ref_map({}, ["zhou", "albon", "norris"], start_at=10)
        b, _ = build_ref_map({}, ["norris", "zhou", "albon"], start_at=10)
        assert a == b

    def test_duplicates_do_not_consume_extra_ids(self):
        mapping, new = build_ref_map({}, ["a", "a", "b"], start_at=1)
        assert mapping == {"a": 1, "b": 2}
        assert len(new) == 2

    def test_does_not_mutate_the_input(self):
        existing = {"hamilton": 1}
        build_ref_map(existing, ["new_guy"], start_at=5)
        assert existing == {"hamilton": 1}


# --------------------------------------------------------- points recompute
def _res(driver, team, points):
    return {"Driver": {"driverId": driver}, "Constructor": {"constructorId": team}, "points": str(points)}


class TestPointsRecomputation:
    def test_driver_points_sum_race_and_sprint(self):
        results = [_res("norris", "mclaren", 25), _res("max_verstappen", "red_bull", 18)]
        sprints = [_res("max_verstappen", "red_bull", 8)]
        assert recompute_driver_points(results, sprints) == {"norris": 25.0, "max_verstappen": 26.0}

    def test_constructor_points_add_both_cars(self):
        results = [_res("norris", "mclaren", 25), _res("piastri", "mclaren", 18)]
        assert recompute_constructor_points(results, [])["mclaren"] == 43.0

    def test_zero_and_missing_points_are_zero_not_dropped(self):
        results = [_res("bottas", "sauber", 0), {"Driver": {"driverId": "zhou"},
                                                 "Constructor": {"constructorId": "sauber"}}]
        totals = recompute_driver_points(results, [])
        assert totals == {"bottas": 0.0, "zhou": 0.0}

    def test_fractional_points_survive(self):
        """Half-points races must not be rounded away."""
        results = [_res("max_verstappen", "red_bull", 12.5)]
        assert recompute_driver_points(results, [])["max_verstappen"] == 12.5

    def test_a_driver_who_changed_team_still_totals_correctly(self):
        results = [_res("lawson", "red_bull", 0), _res("lawson", "rb", 6)]
        assert recompute_driver_points(results, [])["lawson"] == 6.0


# ------------------------------------------------------------ serialisation
class TestSerialisation:
    def test_none_renders_as_the_kaggle_null_token(self):
        assert fmt(None) == NULL
        assert fmt("") == NULL

    def test_whole_floats_lose_the_trailing_zero(self):
        assert fmt(25.0) == "25"
        assert fmt(12.5) == "12.5"

    def test_strings_quoted_numbers_and_nulls_bare(self):
        row = {"circuitId": 1, "circuitRef": "albert_park", "name": "Albert Park",
               "location": "Melbourne", "country": "Australia", "lat": -37.8497,
               "lng": 144.968, "alt": None, "url": "http://x"}
        line = to_csv_line(row, COLUMNS["circuits"])
        assert line == '1,"albert_park","Albert Park","Melbourne","Australia",-37.8497,144.968,\\N,"http://x"'

    def test_embedded_quotes_are_escaped(self):
        line = to_csv_line({"statusId": 1, "status": 'He said "hi"'}, COLUMNS["status"])
        assert line == '1,"He said ""hi"""'

    def test_column_order_is_the_kaggle_order(self):
        assert COLUMNS["results"][:5] == ["resultId", "raceId", "driverId", "constructorId", "number"]
        assert COLUMNS["results"][-1] == "statusId"
        assert COLUMNS["lap_times"] == ["raceId", "driverId", "lap", "position", "time", "milliseconds"]

    def test_missing_key_becomes_null_not_an_error(self):
        assert to_csv_line({"statusId": 5}, COLUMNS["status"]) == "5,\\N"
