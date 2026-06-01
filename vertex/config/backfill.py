"""
Point-in-time SQL and config overrides for walk-forward backfill.

Used by vertex.jobs.backfill and (later) orchestration.flows.backfill.
"""

from __future__ import annotations

import copy
import re
from datetime import date, timedelta
from typing import Any, Iterator

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
    interval_days: int = 1,
) -> Iterator[date]:
    """Yield anchor dates from start through end inclusive."""
    if interval_days < 1:
        raise ValueError(f"interval_days must be >= 1, got {interval_days}")
    if start > end:
        raise ValueError(f"start date {start} must be <= end date {end}")

    current = start
    while current <= end:
        yield current
        current += timedelta(days=interval_days)


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
    train_days: int,
) -> str:
    """
    Training rows with observed labels for target ``sales_store_n1d``.

    Row at date d uses next-day sales as the label, so through end-of-day
  ``as_of_date`` only dates ``<= as_of_date - 1 day`` are valid for training.
    """
    if train_days < 1:
        raise ValueError(f"train_days must be >= 1, got {train_days}")
    as_of = as_of_date.isoformat()
    return f"""SELECT *
FROM `{feature_table}`
WHERE date > DATE_SUB(DATE '{as_of}', INTERVAL {train_days} DAY)
  AND date <= DATE_SUB(DATE '{as_of}', INTERVAL 1 DAY)
"""


def build_backfill_predict_sql(feature_table: str, as_of_date: date) -> str:
    """Scoring rows at the anchor date (predict next-day sales from that day's features)."""
    as_of = as_of_date.isoformat()
    return f"""SELECT *
FROM `{feature_table}`
WHERE date = DATE '{as_of}'
"""


def apply_backfill_overrides(
    config: dict[str, Any],
    *,
    as_of_date: date,
    train_days: int,
    feature_table: str | None = None,
) -> dict[str, Any]:
    """Return a copy of config with backfill SQL and training knobs applied."""
    out = copy.deepcopy(config)
    table = feature_table or resolve_feature_table(out)
    inputs = out.setdefault("inputs", {})
    inputs["train_sql_query"] = build_backfill_train_sql(table, as_of_date, train_days)
    inputs["predict_sql_query"] = build_backfill_predict_sql(table, as_of_date)
    inputs["backfill_as_of_date"] = as_of_date.isoformat()
    inputs["test_size"] = BACKFILL_TRAIN_TEST_SIZE
    inputs.pop("model_run_id", None)
    return out
