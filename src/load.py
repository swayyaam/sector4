"""Loading helpers for the Kaggle (Ergast dump) CSVs.

Missing values in these files are the literal two-character string ``\\N``.
We treat *only* that as null so that a genuinely empty field stays visible
as an empty string and gets reported rather than silently becoming NaN.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

RAW_KAGGLE = Path(__file__).resolve().parents[1] / "data" / "raw" / "kaggle"

NULL_TOKEN = r"\N"

TABLES = [
    "circuits",
    "constructor_results",
    "constructor_standings",
    "constructors",
    "driver_standings",
    "drivers",
    "lap_times",
    "pit_stops",
    "qualifying",
    "races",
    "results",
    "seasons",
    "sprint_results",
    "status",
]

# Declared primary keys per the Ergast schema.
PRIMARY_KEYS = {
    "circuits": ["circuitId"],
    "constructor_results": ["constructorResultsId"],
    "constructor_standings": ["constructorStandingsId"],
    "constructors": ["constructorId"],
    "driver_standings": ["driverStandingsId"],
    "drivers": ["driverId"],
    "lap_times": ["raceId", "driverId", "lap"],
    "pit_stops": ["raceId", "driverId", "stop"],
    "qualifying": ["qualifyId"],
    "races": ["raceId"],
    "results": ["resultId"],
    "seasons": ["year"],
    "sprint_results": ["resultId"],
    "status": ["statusId"],
}

# (table, column) -> (parent table, parent column)
FOREIGN_KEYS = {
    "races": {"circuitId": ("circuits", "circuitId"), "year": ("seasons", "year")},
    "results": {
        "raceId": ("races", "raceId"),
        "driverId": ("drivers", "driverId"),
        "constructorId": ("constructors", "constructorId"),
        "statusId": ("status", "statusId"),
    },
    "sprint_results": {
        "raceId": ("races", "raceId"),
        "driverId": ("drivers", "driverId"),
        "constructorId": ("constructors", "constructorId"),
        "statusId": ("status", "statusId"),
    },
    "qualifying": {
        "raceId": ("races", "raceId"),
        "driverId": ("drivers", "driverId"),
        "constructorId": ("constructors", "constructorId"),
    },
    "lap_times": {"raceId": ("races", "raceId"), "driverId": ("drivers", "driverId")},
    "pit_stops": {"raceId": ("races", "raceId"), "driverId": ("drivers", "driverId")},
    "driver_standings": {"raceId": ("races", "raceId"), "driverId": ("drivers", "driverId")},
    "constructor_standings": {
        "raceId": ("races", "raceId"),
        "constructorId": ("constructors", "constructorId"),
    },
    "constructor_results": {
        "raceId": ("races", "raceId"),
        "constructorId": ("constructors", "constructorId"),
    },
}


def load_table(name: str, directory: Path = RAW_KAGGLE) -> pd.DataFrame:
    """Load one CSV with ``\\N`` as the only null token."""
    return pd.read_csv(
        directory / f"{name}.csv",
        na_values=[NULL_TOKEN],
        keep_default_na=False,
        low_memory=False,
    )


def load_all(directory: Path = RAW_KAGGLE) -> dict[str, pd.DataFrame]:
    return {t: load_table(t, directory) for t in TABLES}
