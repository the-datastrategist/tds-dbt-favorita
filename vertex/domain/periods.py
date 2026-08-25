"""Calendar-aware arithmetic for forecast contract periods."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd

SUPPORTED_FREQUENCIES = frozenset({"day", "week", "month"})


def period_offset(frequency: str, periods: int) -> pd.DateOffset:
    """Return a calendar offset for a signed number of contract periods."""
    if frequency not in SUPPORTED_FREQUENCIES:
        raise ValueError(f"unsupported forecast frequency {frequency!r}")
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
