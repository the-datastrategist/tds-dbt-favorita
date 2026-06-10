"""Shared helpers for ARIMA / SARIMA entity-level training and prediction."""

from __future__ import annotations

import logging
from typing import Any, Optional, cast

import numpy as np
import pandas as pd
from statsmodels.tsa.statespace.sarimax import SARIMAX

from vertex.utils.data_utils import get_hash
from vertex.utils.metadata import get_performance_metrics

logger = logging.getLogger(__name__)

TimeSeriesBundle = dict[str, Any]


def normalize_order(value: Any, length: int) -> tuple[int, ...]:
    if isinstance(value, (list, tuple)):
        parts = tuple(int(x) for x in value)
        if len(parts) != length:
            raise ValueError(f"Expected {length} order components, got {value!r}")
        return parts
    raise ValueError(f"order must be a list/tuple, got {value!r}")


def default_model_params(model_type: str) -> dict[str, Any]:
    if model_type == "sarima":
        return {
            "order": [1, 1, 1],
            "seasonal_order": [1, 1, 1, 7],
            "trend": "c",
            "maxiter": 50,
        }
    return {
        "order": [2, 1, 2],
        "seasonal_order": [0, 0, 0, 0],
        "trend": "c",
        "maxiter": 50,
    }


def prepare_panel(
    df: pd.DataFrame,
    *,
    entity_column: str,
    date_column: str,
    target_column: str,
) -> pd.DataFrame:
    work = df.copy()
    work[date_column] = pd.to_datetime(work[date_column])
    work[target_column] = pd.to_numeric(work[target_column], errors="coerce")
    work = work.dropna(subset=[entity_column, date_column, target_column])
    return work.sort_values([entity_column, date_column])


def split_entity_frame(
    entity_df: pd.DataFrame,
    *,
    test_size: float,
    date_column: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    entity_df = entity_df.sort_values(date_column)
    split_index = int(len(entity_df) * (1 - test_size))
    if split_index <= 0 or split_index >= len(entity_df):
        raise ValueError(f"Invalid entity split with {len(entity_df)} rows")
    train = entity_df.iloc[:split_index]
    test = entity_df.iloc[split_index:]
    return train, test


def fit_sarimax(
    endog: pd.Series,
    *,
    order: tuple[int, int, int],
    seasonal_order: tuple[int, int, int, int],
    trend: str,
    maxiter: int,
) -> Any:
    model = SARIMAX(
        endog.astype(float),
        order=order,
        seasonal_order=seasonal_order,
        trend=trend,
        enforce_stationarity=False,
        enforce_invertibility=False,
    )
    return model.fit(disp=False, maxiter=maxiter)


def fit_entity_models(
    panel: pd.DataFrame,
    *,
    entity_column: str,
    date_column: str,
    target_column: str,
    test_size: float,
    model_type: str,
    model_params: dict[str, Any],
    min_train_obs: int,
    max_entities: Optional[int] = None,
) -> tuple[TimeSeriesBundle, dict[str, float], dict[str, float], int, int]:
    """
    Fit one model per entity on the chronological train split; score on test.

    Returns:
        bundle, train_performance, test_performance, entity_count, entities_fitted
    """
    order = cast(tuple[int, int, int], normalize_order(model_params.get("order", [1, 1, 1]), 3))
    seasonal_order = cast(
        tuple[int, int, int, int],
        normalize_order(model_params.get("seasonal_order", [0, 0, 0, 0]), 4),
    )
    trend = str(model_params.get("trend", "c"))
    maxiter = int(model_params.get("maxiter", 50))

    entities = panel[entity_column].drop_duplicates().tolist()
    if max_entities is not None:
        entities = entities[: int(max_entities)]

    entity_models: dict[str, Any] = {}
    entity_meta: dict[str, dict[str, Any]] = {}
    train_actual: list[float] = []
    train_pred: list[float] = []
    test_actual: list[float] = []
    test_pred: list[float] = []

    for entity in entities:
        entity_df = panel[panel[entity_column] == entity]
        if len(entity_df) < min_train_obs:
            logger.debug("Skipping %s: only %s rows", entity, len(entity_df))
            continue
        try:
            train_df, test_df = split_entity_frame(
                entity_df,
                test_size=test_size,
                date_column=date_column,
            )
        except ValueError:
            continue

        train_series = train_df.set_index(date_column)[target_column]
        if len(train_series) < min_train_obs:
            continue

        try:
            fitted = fit_sarimax(
                train_series,
                order=order,
                seasonal_order=seasonal_order,
                trend=trend,
                maxiter=maxiter,
            )
        except Exception as exc:
            logger.warning("Fit failed for entity %s: %s", entity, exc)
            continue

        entity_key = str(entity)
        entity_models[entity_key] = fitted
        entity_meta[entity_key] = {
            "train_end": train_series.index.max().isoformat(),
            "train_obs": int(len(train_series)),
        }

        train_pred_series = fitted.fittedvalues.reindex(train_series.index)
        train_actual.extend(train_series.tolist())
        train_pred.extend(train_pred_series.ffill().tolist())

        if len(test_df) > 0:
            test_series = test_df.set_index(date_column)[target_column]
            steps = len(test_series)
            forecast = fitted.forecast(steps=steps)
            test_actual.extend(test_series.tolist())
            test_pred.extend(np.asarray(forecast).tolist())

    if not entity_models:
        raise ValueError(
            "No entity models were fitted. Check min_train_obs, max_entities, and data volume."
        )

    bundle: TimeSeriesBundle = {
        "entity_models": entity_models,
        "entity_meta": entity_meta,
        "entity_column": entity_column,
        "date_column": date_column,
        "target_column": target_column,
        "model_type": model_type,
        "order": list(order),
        "seasonal_order": list(seasonal_order),
        "trend": trend,
    }

    train_performance = get_performance_metrics(np.asarray(train_actual), np.asarray(train_pred))
    test_performance = get_performance_metrics(np.asarray(test_actual), np.asarray(test_pred))
    return (
        bundle,
        train_performance,
        test_performance,
        len(entities),
        len(entity_models),
    )


def predict_holdout_rows(
    panel: pd.DataFrame,
    bundle: TimeSeriesBundle,
    *,
    entity_column: str,
    date_column: str,
    target_column: str,
    test_size: float,
) -> pd.DataFrame:
    """One prediction per row in each entity's chronological test split."""
    records: list[dict[str, Any]] = []
    entity_models = bundle["entity_models"]

    for entity, entity_df in panel.groupby(entity_column):
        entity_key = str(entity)
        fitted = entity_models.get(entity_key)
        if fitted is None:
            continue
        try:
            _train_df, test_df = split_entity_frame(
                entity_df,
                test_size=test_size,
                date_column=date_column,
            )
        except ValueError:
            continue
        if test_df.empty:
            continue
        test_series = test_df.set_index(date_column)[target_column]
        forecast = np.asarray(fitted.forecast(steps=len(test_series)))
        for idx, (pred_date, actual) in enumerate(test_series.items()):
            row = test_df[test_df[date_column] == pred_date].iloc[0].to_dict()
            row["prediction"] = float(forecast[idx])
            row["actual"] = float(actual)
            records.append(row)

    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def predict_forward_rows(
    panel: pd.DataFrame,
    bundle: TimeSeriesBundle,
    *,
    entity_column: str,
    date_column: str,
    target_column: str,
    forecast_horizon: int,
    id_columns: list[str],
) -> pd.DataFrame:
    """Forecast `forecast_horizon` steps beyond each entity's last observed date."""
    records: list[dict[str, Any]] = []
    entity_models = bundle["entity_models"]
    freq = pd.infer_freq(panel.sort_values(date_column)[date_column].iloc[:10])

    for entity, entity_df in panel.groupby(entity_column):
        entity_key = str(entity)
        fitted = entity_models.get(entity_key)
        if fitted is None:
            continue
        entity_df = entity_df.sort_values(date_column)
        last_date = entity_df[date_column].max()
        if freq:
            future_dates = pd.date_range(
                start=last_date,
                periods=forecast_horizon + 1,
                freq=freq,
            )[1:]
        else:
            future_dates = pd.date_range(
                start=last_date + pd.Timedelta(days=1),
                periods=forecast_horizon,
                freq="D",
            )
        forecast = np.asarray(fitted.forecast(steps=forecast_horizon))
        base_row = entity_df.iloc[-1].to_dict()
        for step, (pred_date, pred_value) in enumerate(zip(future_dates, forecast), start=1):
            row = dict(base_row)
            row[date_column] = last_date
            row["forecast_date"] = pred_date
            row["forecast_horizon"] = step
            row["prediction"] = float(pred_value)
            row["actual"] = None
            for col in id_columns:
                if col not in row:
                    row[col] = base_row.get(col)
            records.append(row)

    return pd.DataFrame(records)


def bundle_model_id(
    model_type: str,
    parameters: dict[str, Any],
    entity_count: int,
) -> str:
    return get_hash(
        {
            "model_type": model_type,
            "parameters": parameters,
            "entity_count": entity_count,
        }
    )
