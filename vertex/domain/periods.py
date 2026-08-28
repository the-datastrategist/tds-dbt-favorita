"""Calendar-aware arithmetic for forecast contract periods."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd

SUPPORTED_FREQUENCIES = frozenset({"day", "week", "month"})

_PANDAS_FREQUENCIES = {"day": "D", "week": "W-MON", "month": "MS"}
_BIGQUERY_INTERVAL_UNITS = {"day": "DAY", "week": "WEEK", "month": "MONTH"}
_SEASONAL_PERIODS = {"day": 7, "week": 52, "month": 12}


def validate_frequency(frequency: str) -> str:
    """Return a supported frequency or raise a consistent configuration error."""
    if frequency not in SUPPORTED_FREQUENCIES:
        raise ValueError(f"unsupported forecast frequency {frequency!r}")
    return frequency


def pandas_frequency(frequency: str) -> str:
    """Pandas period-start alias for a forecast contract frequency."""
    return _PANDAS_FREQUENCIES[validate_frequency(frequency)]


def bigquery_interval_unit(frequency: str) -> str:
    """BigQuery DATE_ADD/DATE_SUB interval unit for a contract frequency."""
    return _BIGQUERY_INTERVAL_UNITS[validate_frequency(frequency)]


def seasonal_period(frequency: str) -> int:
    """Default one-cycle seasonal lag expressed in forecast periods."""
    return _SEASONAL_PERIODS[validate_frequency(frequency)]


def period_offset(frequency: str, periods: int) -> pd.DateOffset:
    """Return a calendar offset for a signed number of contract periods."""
    validate_frequency(frequency)
    if not isinstance(periods, int):
        raise TypeError("periods must be an integer")
    if frequency == "day":
        return pd.DateOffset(days=periods)
    if frequency == "week":
        return pd.DateOffset(weeks=periods)
    return pd.DateOffset(months=periods)


def shift_period(value: Any, periods: int, frequency: str) -> Any:
    """Shift one date-like value while retaining date inputs as dates."""
    shifted = pd.Timestamp(value) + period_offset(frequency, periods)
    if isinstance(value, date) and not isinstance(value, (datetime, pd.Timestamp)):
        return shifted.date()
    return shifted


def shift_periods(values: pd.Series, periods: pd.Series, frequency: str) -> pd.Series:
    """Shift paired date-like values and period counts with calendar semantics."""
    if len(values) != len(periods):
        raise ValueError("values and periods must have equal length")
    timestamps = pd.to_datetime(values, errors="raise")
    counts = periods.astype(int)
    return pd.Series(
        [
            timestamp + period_offset(frequency, int(count))
            for timestamp, count in zip(timestamps, counts)
        ],
        index=values.index,
    )


def future_period_starts(value: Any, periods: int, frequency: str) -> pd.DatetimeIndex:
    """Return the next ``periods`` aligned starts after an observed period."""
    if periods < 1:
        raise ValueError("periods must be positive")
    start = pd.Timestamp(value)
    if frequency == "month":
        start = start.to_period("M").to_timestamp()
    elif frequency == "week":
        start = start.normalize() - pd.Timedelta(days=start.weekday())
    return pd.date_range(
        start=start,
        periods=periods + 1,
        freq=pandas_frequency(frequency),
    )[1:]
