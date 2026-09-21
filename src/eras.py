"""Regulation eras for the `regs_era` column on races.

Boundaries are major technical-regulation resets -- the points at which car
performance stops being comparable across the boundary. Proposed for
confirmation; nothing downstream hard-codes these beyond this table.
"""
from __future__ import annotations

# (first_year, last_year_inclusive_or_None, key, description)
ERAS = [
    (1950, 1953, "1950_f1_f2",        "Founding formula; 1952-53 run to Formula Two rules"),
    (1954, 1960, "1954_2500cc",       "2.5 L naturally aspirated; front-engine giving way to mid-engine"),
    (1961, 1965, "1961_1500cc",       "1.5 L naturally aspirated"),
    (1966, 1976, "1966_3000cc",       "3.0 L 'return to power'; Cosworth DFV era begins"),
    (1977, 1982, "1977_ground_effect", "Ground effect / wing cars, banned for 1983"),
    (1983, 1988, "1983_turbo",        "Flat-bottom cars; turbos dominant, progressively restricted"),
    (1989, 1994, "1989_v10_na",       "Turbos banned; 3.5 L naturally aspirated"),
    (1995, 2005, "1995_3000cc",       "3.0 L; V10s settle as the standard"),
    (2006, 2008, "2006_v8",           "2.4 L V8 mandated"),
    (2009, 2013, "2009_aero_kers",    "Major aero reset, slick tyres return, KERS introduced"),
    (2014, 2021, "2014_v6_hybrid",    "1.6 L V6 turbo-hybrid power units"),
    (2022, 2025, "2022_ground_effect", "Ground-effect aero reset, 18-inch wheels, budget cap"),
    (2026, None, "2026_reset",        "New power units (50% electric, no MGU-H), active aero, Audi and Cadillac enter"),
]


def era_for(year: int) -> str:
    for first, last, key, _ in ERAS:
        if year >= first and (last is None or year <= last):
            return key
    raise ValueError(f"no era defined for year {year}")
