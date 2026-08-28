"""Tests for calendar-aware forecast period arithmetic."""

from datetime import date

import pandas as pd
import pytest

from vertex.domain.periods import future_period_starts, seasonal_period, shift_period, shift_periods


@pytest.mark.unit
@pytest.mark.parametrize(
    ("frequency", "expected"),
    [
        ("day", date(2026, 2, 1)),
        ("week", date(2026, 2, 7)),
        ("month", date(2026, 2, 28)),
    ],
)
def test_shift_period_uses_contract_frequency(frequency: str, expected: date) -> None:
    assert shift_period(date(2026, 1, 31), 1, frequency) == expected


@pytest.mark.unit
def test_shift_periods_supports_different_horizons() -> None:
    origins = pd.Series(pd.to_datetime(["2026-01-31", "2026-01-31"]))
    horizons = pd.Series([1, 2])

    shifted = shift_periods(origins, horizons, "month")

    assert shifted.dt.date.tolist() == [date(2026, 2, 28), date(2026, 3, 31)]


@pytest.mark.unit
def test_shift_period_rejects_unknown_frequency() -> None:
    with pytest.raises(ValueError, match="unsupported forecast frequency"):
        shift_period(date(2026, 1, 1), 1, "quarter")


@pytest.mark.unit
def test_future_period_frames_and_seasonal_lags_are_frequency_aware() -> None:
    assert future_period_starts("2024-12-30", 2, "week").tolist() == [
        pd.Timestamp("2025-01-06"),
        pd.Timestamp("2025-01-13"),
    ]
    assert future_period_starts("2024-01-31", 2, "month").tolist() == [
        pd.Timestamp("2024-02-01"),
        pd.Timestamp("2024-03-01"),
    ]
    assert [seasonal_period(frequency) for frequency in ("day", "week", "month")] == [7, 52, 12]
