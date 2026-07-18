"""Rolling-origin scoring for configured models and deterministic baselines."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from vertex.config.backtest_contract import BacktestContract
from vertex.utils.data_utils import get_hash

SUPPORTED_SCORING_BASELINES = frozenset(
    {
        "zero_demand",
        "last_observation",
        "seasonal_naive_7d",
        "same_period_last_year",
        "moving_average",
        "croston_sba",
        "tsb",
        "croston_sba_tsb",
    }
)

PREDICTION_COLUMNS = [
    "prediction_id",
    "backtest_run_id",
    "backtest_contract_name",
    "backtest_contract_hash",
    "forecast_origin",
    "target_date",
    "horizon",
    "entity_key_json",
    "segment_key_json",
    "baseline_name",
    "actual",
    "prediction",
]

METRIC_COLUMNS = [
    "metric_id",
    "backtest_run_id",
    "backtest_contract_name",
    "backtest_contract_hash",
    "forecast_origin",
    "horizon",
    "baseline_name",
    "segment_key_json",
    "eligible_count",
    "prediction_count",
    "wape",
    "mae",
    "bias",
    "prediction_completeness",
]


@dataclass(frozen=True)
class BaselineBacktestResult:
    """Normalized prediction and metric records from one baseline run."""

    backtest_run_id: str
    predictions: pd.DataFrame
    metrics: pd.DataFrame


ModelFitPredict = Callable[[pd.DataFrame, pd.DataFrame, dict[str, Any]], pd.Series]


def _json_key(values: dict[str, Any]) -> str:
    normalized = {key: _json_scalar(value) for key, value in values.items()}
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"))


def _json_scalar(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (pd.Timestamp, date)):
        return value.isoformat()
    return value


def _validate_input_frame(frame: pd.DataFrame, contract: BacktestContract) -> pd.DataFrame:
    required = {
        contract.date_column,
        contract.actual_column,
        *contract.entity_columns,
        *contract.segment_columns,
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Backtest input is missing required columns: {missing}")

    data = frame.copy()
    data[contract.date_column] = pd.to_datetime(data[contract.date_column], errors="raise").dt.date
    duplicates = data.duplicated([*contract.entity_columns, contract.date_column], keep=False)
    if duplicates.any():
        raise ValueError("Backtest input must have one row per entity and date")
    return data.sort_values([*contract.entity_columns, contract.date_column]).reset_index(drop=True)


def _entity_mask(frame: pd.DataFrame, entity_columns: list[str], row: pd.Series) -> pd.Series:
    mask = pd.Series(True, index=frame.index)
    for column in entity_columns:
        mask &= frame[column].eq(row[column])
    return mask


def _lookup_actual(
    history: pd.DataFrame,
    *,
    entity_columns: list[str],
    date_column: str,
    actual_column: str,
    entity_row: pd.Series,
    lookup_date: date,
) -> float | None:
    matches = history[
        _entity_mask(history, entity_columns, entity_row) & history[date_column].eq(lookup_date)
    ]
    if matches.empty or pd.isna(matches.iloc[0][actual_column]):
        return None
    return float(matches.iloc[0][actual_column])


def _baseline_prediction(
    baseline: str,
    history: pd.DataFrame,
    *,
    origin: date,
    target_date: date,
    entity_row: pd.Series,
    contract: BacktestContract,
) -> float | None:
    if baseline == "zero_demand":
        return 0.0

    entity_history = history[
        _entity_mask(history, contract.entity_columns, entity_row)
        & history[contract.date_column].le(origin)
        & history[contract.date_column].gt(origin - timedelta(days=contract.train_window_days))
    ]
    observed = entity_history.dropna(subset=[contract.actual_column])
    if baseline == "last_observation":
        return None if observed.empty else float(observed.iloc[-1][contract.actual_column])
    if baseline == "seasonal_naive_7d":
        lookup_date = target_date - timedelta(days=7)
        if lookup_date > origin:
            return None
        return _lookup_actual(
            history,
            entity_columns=contract.entity_columns,
            date_column=contract.date_column,
            actual_column=contract.actual_column,
            entity_row=entity_row,
            lookup_date=lookup_date,
        )
    if baseline == "same_period_last_year":
        try:
            lookup_date = target_date.replace(year=target_date.year - 1)
        except ValueError:  # February 29 uses the last valid day in the prior year.
            lookup_date = target_date.replace(year=target_date.year - 1, day=28)
        if lookup_date > origin:
            return None
        return _lookup_actual(
            history,
            entity_columns=contract.entity_columns,
            date_column=contract.date_column,
            actual_column=contract.actual_column,
            entity_row=entity_row,
            lookup_date=lookup_date,
        )
    if baseline == "moving_average":
        if observed.empty:
            return None
        return float(observed.tail(contract.moving_average_window)[contract.actual_column].mean())
    if baseline in {"croston_sba", "tsb", "croston_sba_tsb"}:
        demand = observed[contract.actual_column].astype(float).clip(lower=0).to_numpy()
        if demand.size == 0:
            return None
        sba = _croston_sba(demand)
        tsb = _tsb(demand)
        if baseline == "croston_sba":
            return sba
        if baseline == "tsb":
            return tsb
        return float((sba + tsb) / 2)
    raise ValueError(f"Baseline scoring is not implemented for {baseline!r}")


def _croston_sba(demand: np.ndarray, alpha: float = 0.1) -> float:
    """Return the bias-adjusted Croston forecast for non-negative demand."""
    nonzero = np.flatnonzero(demand > 0)
    if nonzero.size == 0:
        return 0.0
    first = int(nonzero[0])
    size = float(demand[first])
    interval = float(first + 1)
    elapsed = 1
    for value in demand[first + 1 :]:
        if value > 0:
            size += alpha * (float(value) - size)
            interval += alpha * (elapsed - interval)
            elapsed = 1
        else:
            elapsed += 1
    return float((1 - alpha / 2) * size / interval)


def _tsb(demand: np.ndarray, alpha: float = 0.1, beta: float = 0.1) -> float:
    """Return a Teunter-Syntetos-Babai intermittent-demand forecast."""
    nonzero = np.flatnonzero(demand > 0)
    if nonzero.size == 0:
        return 0.0
    first = int(nonzero[0])
    size = float(demand[first])
    probability = 1.0 / float(first + 1)
    for value in demand[first + 1 :]:
        occurrence = 1.0 if value > 0 else 0.0
        probability += beta * (occurrence - probability)
        if occurrence:
            size += alpha * (float(value) - size)
    return float(probability * size)


def _metric_row(group: pd.DataFrame, metadata: dict[str, Any]) -> dict[str, Any]:
    eligible = group["actual"].notna()
    complete = eligible & group["prediction"].notna()
    eligible_count = int(eligible.sum())
    prediction_count = int(complete.sum())
    completeness = prediction_count / eligible_count if eligible_count else None

    if not complete.any():
        wape = mae = bias = None
    else:
        actual = group.loc[complete, "actual"].astype(float)
        prediction = group.loc[complete, "prediction"].astype(float)
        error = prediction - actual
        denominator = float(actual.abs().sum())
        wape = None if denominator == 0 else float(error.abs().sum() / denominator)
        mae = float(error.abs().mean())
        bias = float(error.mean())

    row = {
        **metadata,
        "eligible_count": eligible_count,
        "prediction_count": prediction_count,
        "wape": wape,
        "mae": mae,
        "bias": bias,
        "prediction_completeness": completeness,
    }
    row["metric_id"] = get_hash(row)
    return row


def _build_metrics(predictions: pd.DataFrame, contract: BacktestContract) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    group_columns = ["forecast_origin", "horizon", "baseline_name"]
    for group_key, group in predictions.groupby(group_columns, dropna=False, sort=True):
        origin, horizon, baseline = group_key
        common = {
            "backtest_run_id": group.iloc[0]["backtest_run_id"],
            "backtest_contract_name": contract.name,
            "backtest_contract_hash": contract.hash,
            "forecast_origin": origin,
            "horizon": int(horizon),
            "baseline_name": baseline,
        }
        rows.append(_metric_row(group, {**common, "segment_key_json": "{}"}))
        if contract.segment_columns:
            for segment_json, segment in group.groupby("segment_key_json", dropna=False, sort=True):
                rows.append(_metric_row(segment, {**common, "segment_key_json": segment_json}))
    return pd.DataFrame(rows, columns=METRIC_COLUMNS)


def score_baselines(
    frame: pd.DataFrame,
    contract: BacktestContract,
    *,
    backtest_run_id: str | None = None,
) -> BaselineBacktestResult:
    """Score configured deterministic baselines at every origin and horizon."""
    unsupported = sorted(set(contract.baselines).difference(SUPPORTED_SCORING_BASELINES))
    if unsupported:
        raise ValueError(f"Configured baselines do not have scorers yet: {unsupported}")

    data = _validate_input_frame(frame, contract)
    fingerprint_columns = sorted(
        {
            contract.date_column,
            contract.actual_column,
            *contract.entity_columns,
            *contract.segment_columns,
        }
    )
    row_hashes = pd.util.hash_pandas_object(data[fingerprint_columns], index=False).tolist()
    run_id = backtest_run_id or get_hash(
        {
            "backtest_contract_hash": contract.hash,
            "input_columns": fingerprint_columns,
            "input_row_hashes": [int(value) for value in row_hashes],
        }
    )
    rows: list[dict[str, Any]] = []
    entity_rows = data.drop_duplicates(contract.entity_columns)
    if contract.max_entities is not None:
        entity_rows = entity_rows.head(contract.max_entities)
    for origin in contract.origins:
        for horizon in contract.horizons:
            target_date = origin + timedelta(days=horizon)
            for _, entity_row in entity_rows.iterrows():
                actual = _lookup_actual(
                    data,
                    entity_columns=contract.entity_columns,
                    date_column=contract.date_column,
                    actual_column=contract.actual_column,
                    entity_row=entity_row,
                    lookup_date=target_date,
                )
                entity_key = _json_key(
                    {column: entity_row[column] for column in contract.entity_columns}
                )
                segment_key = _json_key(
                    {column: entity_row[column] for column in contract.segment_columns}
                )
                for baseline in contract.baselines:
                    prediction = _baseline_prediction(
                        baseline,
                        data,
                        origin=origin,
                        target_date=target_date,
                        entity_row=entity_row,
                        contract=contract,
                    )
                    identity = {
                        "backtest_run_id": run_id,
                        "forecast_origin": origin.isoformat(),
                        "target_date": target_date.isoformat(),
                        "horizon": horizon,
                        "entity_key_json": entity_key,
                        "segment_key_json": segment_key,
                        "baseline_name": baseline,
                    }
                    rows.append(
                        {
                            "prediction_id": get_hash(identity),
                            **identity,
                            "backtest_contract_name": contract.name,
                            "backtest_contract_hash": contract.hash,
                            "actual": actual,
                            "prediction": prediction,
                        }
                    )
    predictions = pd.DataFrame(rows, columns=PREDICTION_COLUMNS)
    metrics = _build_metrics(predictions, contract)
    return BaselineBacktestResult(run_id, predictions, metrics)


def _fit_predict_tabular_model(
    train_rows: pd.DataFrame,
    predict_rows: pd.DataFrame,
    model_config: dict[str, Any],
) -> pd.Series:
    """Fit the configured tabular model and predict one origin's entity rows."""
    from vertex.models.xgboost.train_xgboost import (
        DEFAULT_MODEL_PARAMETERS,
        train_sklearn_xgboost,
    )
    from vertex.utils.features import prepare_feature_matrix
    from vertex.utils.optimize_params import resolve_model_parameters

    model_type = str(model_config["model_type"])
    if model_type not in {"xgboost", "xgboost_sklearn"}:
        raise ValueError(
            "Rolling-origin ML scoring currently supports xgboost configurations; "
            f"got {model_type!r}"
        )
    inputs = model_config.get("inputs") or {}
    target_column = str(inputs["target_column"])
    date_column = str(inputs.get("date_column", "date"))
    excluded_columns = list(inputs.get("excluded_columns") or [])
    categorical_columns = list(inputs.get("categorical_columns") or [])

    train_matrix, features, _ = prepare_feature_matrix(
        train_rows,
        target_column=target_column,
        excluded_columns=excluded_columns,
        categorical_columns=categorical_columns,
        date_column=date_column,
    )
    if not features or train_matrix.empty:
        raise ValueError("Rolling-origin model training produced no complete feature rows")

    prediction_input = predict_rows.copy()
    if target_column not in prediction_input.columns:
        prediction_input[target_column] = 0.0
    prediction_matrix, _, _ = prepare_feature_matrix(
        prediction_input,
        target_column=target_column,
        excluded_columns=excluded_columns,
        categorical_columns=categorical_columns,
        date_column=date_column,
    )
    X_predict = prediction_matrix.reindex(columns=features, fill_value=0)
    params, _ = resolve_model_parameters(model_config, DEFAULT_MODEL_PARAMETERS)
    model = train_sklearn_xgboost(
        train_matrix[features],
        train_matrix[target_column],
        model_parameters=params,
    )
    return pd.Series(model.predict(X_predict), index=X_predict.index, dtype=float)


def score_model_and_baselines(
    frame: pd.DataFrame,
    contract: BacktestContract,
    *,
    backtest_run_id: str | None = None,
    fit_predict: ModelFitPredict | None = None,
) -> BaselineBacktestResult:
    """Score the configured ML model and baselines on identical rolling origins."""
    if len(contract.horizons) != 1:
        raise ValueError("Configured ML backtesting currently requires exactly one direct horizon")
    model_config = contract.model_config
    inputs = model_config.get("inputs") or {}
    target_column = str(inputs["target_column"])
    date_column = str(inputs.get("date_column", contract.date_column))
    if date_column != contract.date_column:
        raise ValueError("Model and backtest contracts must use the same date column")
    if target_column not in frame.columns:
        raise ValueError(f"Backtest model input is missing target column {target_column!r}")

    data = _validate_input_frame(frame, contract)
    fingerprint = pd.util.hash_pandas_object(data, index=False).tolist()
    run_id = backtest_run_id or get_hash(
        {
            "backtest_contract_hash": contract.hash,
            "model_config_hash": get_hash(model_config),
            "input_row_hashes": [int(value) for value in fingerprint],
        }
    )
    baseline_result = score_baselines(data, contract, backtest_run_id=run_id)
    horizon = contract.horizons[0]
    predict_fn = fit_predict or _fit_predict_tabular_model
    model_rows: list[dict[str, Any]] = []

    for origin in contract.origins:
        train_start = origin - timedelta(days=contract.train_window_days + horizon)
        train_end = origin - timedelta(days=horizon)
        train_rows = data[
            data[contract.date_column].gt(train_start)
            & data[contract.date_column].le(train_end)
            & data[target_column].notna()
        ]
        predict_rows = data[data[contract.date_column].eq(origin)]
        if contract.max_entities is not None:
            predict_rows = predict_rows.head(contract.max_entities)
        if predict_rows.empty:
            raise ValueError(f"No model feature rows are available at forecast origin {origin}")
        predictions = predict_fn(train_rows, predict_rows, model_config)
        target_date = origin + timedelta(days=horizon)

        for row_index, entity_row in predict_rows.iterrows():
            entity_key = _json_key(
                {column: entity_row[column] for column in contract.entity_columns}
            )
            segment_key = _json_key(
                {column: entity_row[column] for column in contract.segment_columns}
            )
            actual = _lookup_actual(
                data,
                entity_columns=contract.entity_columns,
                date_column=contract.date_column,
                actual_column=contract.actual_column,
                entity_row=entity_row,
                lookup_date=target_date,
            )
            identity = {
                "backtest_run_id": run_id,
                "forecast_origin": origin.isoformat(),
                "target_date": target_date.isoformat(),
                "horizon": horizon,
                "entity_key_json": entity_key,
                "segment_key_json": segment_key,
                "baseline_name": contract.model_config_name,
            }
            model_rows.append(
                {
                    "prediction_id": get_hash(identity),
                    **identity,
                    "backtest_contract_name": contract.name,
                    "backtest_contract_hash": contract.hash,
                    "actual": actual,
                    "prediction": (
                        float(predictions.loc[row_index])
                        if row_index in predictions.index
                        else None
                    ),
                }
            )

    model_predictions = pd.DataFrame(model_rows, columns=PREDICTION_COLUMNS)
    predictions = pd.concat(
        [baseline_result.predictions, model_predictions],
        ignore_index=True,
    )
    return BaselineBacktestResult(run_id, predictions, _build_metrics(predictions, contract))
