"""Feature-matrix preparation for tabular sklearn models."""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from vertex.domain.periods import period_offset, validate_frequency
from vertex.utils.ml_utils import sanitize_feature_columns


def prepare_feature_matrix(
    df: pd.DataFrame,
    *,
    target_column: str,
    excluded_columns: Optional[list[str]] = None,
    categorical_columns: Optional[list[str]] = None,
    date_column: Optional[str] = None,
) -> tuple[pd.DataFrame, list[str], Optional[pd.Series]]:
    """Build numeric feature matrix and optional date series for chronological split."""
    # Target must stay available for y / metrics even if listed in excluded_columns.
    excluded_columns = [c for c in (excluded_columns or []) if c != target_column]
    categorical_columns = categorical_columns or []

    work = df.copy()
    if date_column and date_column in work.columns:
        work[date_column] = pd.to_datetime(work[date_column])

    cat_cols = [column for column in categorical_columns if column in work.columns]
    if cat_cols:
        work = pd.get_dummies(work, columns=cat_cols, dtype=int)

    drop_cols = set(excluded_columns) | {target_column}
    if date_column and date_column in work.columns:
        dates = pd.to_datetime(work[date_column], errors="coerce")
        drop_cols.discard(date_column)
    else:
        dates = None

    feature_frame = work.drop(
        columns=[column for column in drop_cols if column in work.columns],
        errors="ignore",
    )

    feature_frame = sanitize_feature_columns(feature_frame)
    feature_frame = feature_frame.select_dtypes(include=[np.number])
    feature_frame = feature_frame.apply(pd.to_numeric, errors="coerce")
    feature_frame = feature_frame.dropna(axis=1, how="all")

    target = pd.to_numeric(work[target_column], errors="coerce")
    valid = target.notna() & feature_frame.notna().all(axis=1)
    feature_frame = feature_frame.loc[valid]
    target = target.loc[valid]
    if dates is not None:
        dates = dates.loc[valid]

    features = list(feature_frame.columns)
    out = feature_frame.copy()
    out[target_column] = target.values
    if dates is not None:
        out[date_column] = dates.values
    return out, features, dates


def chronological_train_test_split(
    df: pd.DataFrame,
    feature_list: list[str],
    target_column: str,
    *,
    test_size: float = 0.2,
    date_column: Optional[str] = None,
    purge_days: int | None = None,
    purge_periods: int | None = None,
    frequency: str = "day",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Chronological split with an optional label-horizon purge before validation."""
    frequency = validate_frequency(frequency)
    if purge_days is not None and purge_periods is not None:
        raise ValueError("set either purge_days or purge_periods, not both")
    purge = purge_periods if purge_periods is not None else (purge_days or 0)
    if purge < 0:
        raise ValueError("purge periods must be non-negative")
    work = df.copy()
    if date_column and date_column in work.columns:
        work = work.sort_values(date_column)
    else:
        work = work.sort_index()

    split_index = int(len(work) * (1 - test_size))
    if split_index <= 0 or split_index >= len(work):
        raise ValueError(f"Invalid split: {len(work)} rows with test_size={test_size}")

    if purge and date_column and date_column in work.columns:
        validation_start = pd.Timestamp(work.iloc[split_index][date_column])
        purge_boundary = validation_start - period_offset(frequency, int(purge))
        train = work[pd.to_datetime(work[date_column]) < purge_boundary]
        test = work[pd.to_datetime(work[date_column]) >= validation_start]
        if train.empty or test.empty:
            raise ValueError(
                "Horizon purge left an empty training or validation partition: "
                f"validation_start={validation_start}, purge_periods={purge}, frequency={frequency}"
            )
    else:
        train = work.iloc[:split_index]
        test = work.iloc[split_index:]
    return (
        train[feature_list],
        test[feature_list],
        train[target_column],
        test[target_column],
    )
