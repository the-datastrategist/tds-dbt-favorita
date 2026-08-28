"""Shared helpers for Prophet entity-level training and prediction.

Prophet's fit/predict API (`Prophet().fit(df[['ds','y']])`, `.predict(future_df)` returning a
frame with `yhat`/`yhat_lower`/`yhat_upper`) doesn't fit vertex.models.timeseries.ts_common's
SARIMAX-coupled entity loop (`fitted.forecast(steps=...)`, `fitted.fittedvalues`), so this module
duplicates that loop's shape for Prophet rather than generalizing ts_common — see
docs/specs/prophet_model_family.md § "Shared per-entity loop" for the tradeoff. Model-agnostic
helpers (`prepare_panel`, `split_entity_frame`, `bundle_model_id`) are imported from ts_common
rather than re-implemented.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import numpy as np
import pandas as pd
from prophet import Prophet

from vertex.domain.periods import future_period_starts, validate_frequency
from vertex.models.timeseries.ts_common import TimeSeriesBundle, split_entity_frame
from vertex.utils.metadata import get_performance_metrics

# Prophet/cmdstanpy log an INFO line per chain per entity fit; at max_entities scale that's
# noisy without being actionable.
logging.getLogger("cmdstanpy").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def default_model_params() -> dict[str, Any]:
    """Prophet's own tunables — analogous to ARIMA/SARIMA's order/seasonal_order."""
    return {
        "growth": "linear",
        "seasonality_mode": "additive",
        "yearly_seasonality": "auto",
        "weekly_seasonality": "auto",
        "changepoint_prior_scale": 0.05,
    }


def fit_prophet_entity(train_series: pd.Series, **model_params: Any) -> Prophet:
    df = train_series.rename("y").reset_index()
    df.columns = ["ds", "y"]
    model = Prophet(
        growth=model_params.get("growth", "linear"),
        seasonality_mode=model_params.get("seasonality_mode", "additive"),
        yearly_seasonality=model_params.get("yearly_seasonality", "auto"),
        weekly_seasonality=model_params.get("weekly_seasonality", "auto"),
        changepoint_prior_scale=float(model_params.get("changepoint_prior_scale", 0.05)),
    )
    return model.fit(df)


def fit_entity_models(
    panel: pd.DataFrame,
    *,
    entity_column: str,
    date_column: str,
    target_column: str,
    test_size: float,
    model_params: dict[str, Any],
    min_train_obs: int,
    max_entities: Optional[int] = None,
) -> tuple[TimeSeriesBundle, dict[str, float], dict[str, float], int, int]:
    """
    Fit one Prophet model per entity on the chronological train split; score on test.

    Returns:
        bundle, train_performance, test_performance, entity_count, entities_fitted
    """
    growth = str(model_params.get("growth", "linear"))
    seasonality_mode = str(model_params.get("seasonality_mode", "additive"))
    yearly_seasonality = model_params.get("yearly_seasonality", "auto")
    weekly_seasonality = model_params.get("weekly_seasonality", "auto")
    changepoint_prior_scale = float(model_params.get("changepoint_prior_scale", 0.05))

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
            fitted = fit_prophet_entity(
                train_series,
                growth=growth,
                seasonality_mode=seasonality_mode,
                yearly_seasonality=yearly_seasonality,
                weekly_seasonality=weekly_seasonality,
                changepoint_prior_scale=changepoint_prior_scale,
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

        train_forecast = fitted.predict(pd.DataFrame({"ds": train_series.index}))
        train_actual.extend(train_series.tolist())
        train_pred.extend(train_forecast["yhat"].tolist())

        if len(test_df) > 0:
            test_series = test_df.set_index(date_column)[target_column]
            test_forecast = fitted.predict(pd.DataFrame({"ds": test_series.index}))
            test_actual.extend(test_series.tolist())
            test_pred.extend(test_forecast["yhat"].tolist())

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
        "model_type": "prophet",
        "growth": growth,
        "seasonality_mode": seasonality_mode,
        "yearly_seasonality": yearly_seasonality,
        "weekly_seasonality": weekly_seasonality,
        "changepoint_prior_scale": changepoint_prior_scale,
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
    """One prediction per row in each entity's chronological test split, with Prophet's
    native yhat_lower/yhat_upper uncertainty interval."""
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
        forecast = fitted.predict(pd.DataFrame({"ds": test_series.index}))
        for idx, (pred_date, actual) in enumerate(test_series.items()):
            row = test_df[test_df[date_column] == pred_date].iloc[0].to_dict()
            row["prediction"] = float(forecast["yhat"].iloc[idx])
            row["prediction_lower"] = float(forecast["yhat_lower"].iloc[idx])
            row["prediction_upper"] = float(forecast["yhat_upper"].iloc[idx])
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
    frequency: str = "day",
) -> pd.DataFrame:
    """Forecast `forecast_horizon` steps beyond each entity's last observed date, with
    Prophet's native yhat_lower/yhat_upper uncertainty interval."""
    records: list[dict[str, Any]] = []
    entity_models = bundle["entity_models"]
    validate_frequency(frequency)

    for entity, entity_df in panel.groupby(entity_column):
        entity_key = str(entity)
        fitted = entity_models.get(entity_key)
        if fitted is None:
            continue
        entity_df = entity_df.sort_values(date_column)
        last_date = entity_df[date_column].max()
        future_dates = future_period_starts(last_date, forecast_horizon, frequency)
        forecast = fitted.predict(pd.DataFrame({"ds": future_dates})).set_index("ds")
        base_row = entity_df.iloc[-1].to_dict()
        for step, pred_date in enumerate(future_dates, start=1):
            pred_row = forecast.loc[pred_date]
            row = dict(base_row)
            row[date_column] = last_date
            row["forecast_date"] = pred_date
            row["forecast_horizon"] = step
            row["prediction"] = float(pred_row["yhat"])
            row["prediction_lower"] = float(pred_row["yhat_lower"])
            row["prediction_upper"] = float(pred_row["yhat_upper"])
            row["actual"] = None
            for col in id_columns:
                if col not in row:
                    row[col] = base_row.get(col)
            records.append(row)

    return pd.DataFrame(records)
