"""
Point-in-time SQL and config overrides for walk-forward backfill.

Used by vertex.jobs.backfill and (later) orchestration.flows.backfill.
"""

from __future__ import annotations

import copy
import re
from datetime import date
from typing import Any, Iterator

from vertex.domain.periods import bigquery_interval_unit, shift_period, validate_frequency

# Minimal internal holdout so sklearn trainers can log metrics without dropping much data.
BACKFILL_TRAIN_TEST_SIZE = 1e-6

_FROM_TABLE_RE = re.compile(r"FROM\s+`([^`]+)`", re.IGNORECASE)


def parse_backfill_date(value: str | date) -> date:
    """Parse YYYY-MM-DD or pass through a date."""
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def iter_backfill_dates(
    start: date,
    end: date,
    *,
    interval_days: int | None = None,
    interval_periods: int | None = None,
    frequency: str = "day",
) -> Iterator[date]:
    """Yield calendar-aligned anchor dates from start through end inclusive."""
    frequency = validate_frequency(frequency)
    if interval_days is not None and interval_periods is not None:
        raise ValueError("set either interval_days or interval_periods, not both")
    interval = interval_periods if interval_periods is not None else (interval_days or 1)
    if interval < 1:
        raise ValueError(f"backfill interval must be >= 1, got {interval}")
    if start > end:
        raise ValueError(f"start date {start} must be <= end date {end}")

    current = start
    while current <= end:
        yield current
        current = shift_period(current, int(interval), frequency)


def resolve_feature_table(config: dict[str, Any]) -> str:
    """
    BigQuery table id for int_sales_* features.

    Uses inputs.feature_table when set, otherwise parses the first
    ``FROM `project.dataset.table``` in train_sql_query / predict_sql_query.
    """
    inputs = config.get("inputs") or {}
    explicit = inputs.get("feature_table")
    if explicit:
        return str(explicit)

    for key in ("train_sql_query", "predict_sql_query"):
        query = inputs.get(key) or ""
        match = _FROM_TABLE_RE.search(str(query))
        if match:
            return match.group(1)

    raise ValueError(
        "Cannot resolve feature_table: set inputs.feature_table or include "
        "FROM `project.dataset.table` in train_sql_query / predict_sql_query."
    )


def build_backfill_train_sql(
    feature_table: str,
    as_of_date: date,
    train_days: int | None = None,
    train_periods: int | None = None,
    frequency: str = "day",
    time_column: str = "date",
) -> str:
    """
    Training rows with observed labels for target ``sales_store_n1d``.

    Row at date d uses next-day sales as the label, so through end-of-day
    ``as_of_date`` only dates ``<= as_of_date - 1 day`` are valid for training.
    """
    frequency = validate_frequency(frequency)
    if train_days is not None and train_periods is not None:
        raise ValueError("set either train_days or train_periods, not both")
    window = train_periods if train_periods is not None else (train_days or 0)
    if window < 1:
        raise ValueError(f"training window must be >= 1, got {window}")
    as_of = as_of_date.isoformat()
    unit = bigquery_interval_unit(frequency)
    return f"""SELECT *
FROM `{feature_table}`
WHERE {time_column} > DATE_SUB(DATE '{as_of}', INTERVAL {window} {unit})
  AND {time_column} <= DATE_SUB(DATE '{as_of}', INTERVAL 1 {unit})
"""


def build_backfill_predict_sql(
    feature_table: str, as_of_date: date, *, frequency: str = "day", time_column: str = "date"
) -> str:
    """Scoring rows at the anchor period start."""
    validate_frequency(frequency)
    as_of = as_of_date.isoformat()
    return f"""SELECT *
FROM `{feature_table}`
WHERE {time_column} = DATE '{as_of}'
"""


def apply_backfill_overrides(
    config: dict[str, Any],
    *,
    as_of_date: date,
    train_days: int | None = None,
    train_periods: int | None = None,
    frequency: str = "day",
    feature_table: str | None = None,
) -> dict[str, Any]:
    """Return a copy of config with backfill SQL and training knobs applied."""
    out = copy.deepcopy(config)
    table = feature_table or resolve_feature_table(out)
    inputs = out.setdefault("inputs", {})
    inputs["train_sql_query"] = build_backfill_train_sql(
        table,
        as_of_date,
        train_days=train_days,
        train_periods=train_periods,
        frequency=frequency,
        time_column=str(inputs.get("backfill_time_column", "date")),
    )
    inputs["predict_sql_query"] = build_backfill_predict_sql(
        table,
        as_of_date,
        frequency=frequency,
        time_column=str(inputs.get("backfill_time_column", "date")),
    )
    inputs["backfill_as_of_date"] = as_of_date.isoformat()
    inputs["backfill_frequency"] = frequency
    inputs["test_size"] = BACKFILL_TRAIN_TEST_SIZE
    inputs.pop("model_run_id", None)
    return out
