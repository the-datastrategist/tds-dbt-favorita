"""Training metadata and performance metrics for Vertex models."""

from __future__ import annotations

import json
from datetime import datetime as dt
from typing import Any, Optional

import numpy as np
import pandas as pd
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    median_absolute_error,
    r2_score,
)


def get_performance_metrics(y_actual, y_pred) -> dict[str, float]:
    epsilon = 1e-10
    y_actual = np.asarray(y_actual)
    y_pred = np.asarray(y_pred)

    mae = mean_absolute_error(y_actual, y_pred)
    mse = mean_squared_error(y_actual, y_pred)
    rmse = float(np.sqrt(mse))
    r2 = r2_score(y_actual, y_pred)

    mape = float(np.mean(np.abs((y_actual - y_pred) / (y_actual + epsilon))) * 100)
    wape = float(
        np.sum(np.abs(y_actual - y_pred))
        / (np.sum(np.abs(y_actual)) + epsilon)
        * 100
    )
    smape = float(
        np.mean(
            2 * np.abs(y_actual - y_pred)
            / (np.abs(y_actual) + np.abs(y_pred) + epsilon)
        )
        * 100
    )
    bias = float(np.mean(y_pred - y_actual))
    medae = median_absolute_error(y_actual, y_pred)

    return {
        "mean_pred": float(np.mean(y_pred)),
        "mean_actual": float(np.mean(y_actual)),
        "mae": float(mae),
        "rmse": rmse,
        "mse": float(mse),
        "r2": float(r2),
        "mape": mape,
        "wape": wape,
        "smape": smape,
        "bias": bias,
        "median_ae": float(medae),
    }


def metadata_to_bq_row(metadata: dict[str, Any]) -> dict[str, Any]:
    """Flatten nested training metadata for BigQuery load."""
    run_at = pd.Timestamp(metadata["run_at"])
    if run_at.tzinfo is not None:
        run_at = run_at.tz_convert("UTC").tz_localize(None)
    row: dict[str, Any] = {
        "model_run_id": metadata["model_run_id"],
        "model_id": metadata["model_id"],
        "parameter_id": metadata.get("parameter_id"),
        "config_name": metadata.get("config_name"),
        "model_family": metadata.get("model_family"),
        "model_type": metadata.get("model_type"),
        "run_at": run_at,
        "target_column": metadata.get("target_column"),
        "source_query": metadata.get("source_query"),
        "gcs_uri": metadata.get("gcs_uri"),
        "joblib_gcs_uri": metadata.get("joblib_gcs_uri"),
        "trees_gcs_uri": metadata.get("trees_gcs_uri"),
        "manifest_gcs_uri": metadata.get("manifest_gcs_uri"),
        "boosting_rounds": metadata.get("boosting_rounds"),
        "feature_count": metadata.get("feature_count"),
        "entity_count": metadata.get("entity_count"),
        "entities_fitted": metadata.get("entities_fitted"),
        "train_row_count": metadata.get("train_row_count"),
        "test_row_count": metadata.get("test_row_count"),
        "project_id": metadata.get("project_id"),
        "region": metadata.get("region"),
        "parameters": json.dumps(metadata.get("parameters", {}), default=str),
        "feature_importance": json.dumps(
            metadata.get("feature_importance", {}), default=str
        ),
        "features": metadata.get("features", []),
        "train_performance": json.dumps(
            metadata.get("train_performance", {}), default=str
        ),
        "test_performance": json.dumps(
            metadata.get("test_performance", {}), default=str
        ),
    }
    return {key: value for key, value in row.items() if value is not None}


def build_sklearn_train_metadata(
    model: Any,
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
    y_train: pd.Series,
    y_test: pd.Series,
    *,
    config_name: str,
    model_type: str,
    target_column: str,
    model_family: Optional[str] = None,
    run_at: Optional[dt] = None,
    model_run_id: Optional[str] = None,
    model_id: Optional[str] = None,
    parameter_id: Optional[str] = None,
    source_query: Optional[str] = None,
    gcs_uri: Optional[str] = None,
    joblib_gcs_uri: Optional[str] = None,
    trees_gcs_uri: Optional[str] = None,
    manifest_gcs_uri: Optional[str] = None,
    project_id: Optional[str] = None,
    region: Optional[str] = None,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build training metadata from a fitted sklearn-compatible estimator."""
    from vertex.utils.data_utils import get_hash

    run_at = run_at or dt.utcnow()
    parameters = model.get_params()
    features = list(model.feature_names_in_)
    feature_importance = dict(zip(model.feature_names_in_, model.feature_importances_))

    y_train_pred = model.predict(X_train)
    y_test_pred = model.predict(X_test)
    train_performance = get_performance_metrics(y_train, y_train_pred)
    test_performance = get_performance_metrics(y_test, y_test_pred)

    if parameter_id is None:
        parameter_id = get_hash(parameters)
    if model_id is None:
        model_id = get_hash(
            {
                "model_type": model_type,
                "parameters": parameters,
                "features": sorted(features),
            }
        )
    if model_run_id is None:
        model_run_id = get_hash(f"{model_id}:{run_at.isoformat()}")

    metadata: dict[str, Any] = {
        "model_run_id": model_run_id,
        "model_id": model_id,
        "parameter_id": parameter_id,
        "config_name": config_name,
        "model_family": model_family,
        "model_type": model_type,
        "run_at": run_at,
        "target_column": target_column,
        "source_query": source_query,
        "gcs_uri": gcs_uri,
        "joblib_gcs_uri": joblib_gcs_uri,
        "trees_gcs_uri": trees_gcs_uri,
        "manifest_gcs_uri": manifest_gcs_uri,
        "parameters": parameters,
        "feature_importance": feature_importance,
        "features": features,
        "train_row_count": len(X_train),
        "test_row_count": len(X_test),
        "train_performance": train_performance,
        "test_performance": test_performance,
        "project_id": project_id,
        "region": region,
    }
    if hasattr(model, "get_num_boosting_rounds"):
        metadata["boosting_rounds"] = model.get_num_boosting_rounds()
        booster = model.get_booster()
        metadata["feature_count"] = booster.num_features()
    if extra:
        metadata.update(extra)
    return metadata


def build_timeseries_train_metadata(
    *,
    config_name: str,
    model_type: str,
    model_family: Optional[str],
    target_column: str,
    run_at: dt,
    model_run_id: str,
    model_id: str,
    parameters: dict[str, Any],
    entity_count: int,
    entities_fitted: int,
    train_row_count: int,
    test_row_count: int,
    train_performance: dict[str, float],
    test_performance: dict[str, float],
    source_query: Optional[str] = None,
    joblib_gcs_uri: Optional[str] = None,
    manifest_gcs_uri: Optional[str] = None,
    project_id: Optional[str] = None,
    region: Optional[str] = None,
) -> dict[str, Any]:
    """Build training metadata for classical time-series model bundles."""
    from vertex.utils.data_utils import get_hash

    parameter_id = get_hash(parameters)
    return {
        "model_run_id": model_run_id,
        "model_id": model_id,
        "parameter_id": parameter_id,
        "config_name": config_name,
        "model_family": model_family,
        "model_type": model_type,
        "run_at": run_at,
        "target_column": target_column,
        "source_query": source_query,
        "joblib_gcs_uri": joblib_gcs_uri,
        "manifest_gcs_uri": manifest_gcs_uri,
        "gcs_uri": joblib_gcs_uri,
        "parameters": parameters,
        "features": [],
        "feature_count": 0,
        "entity_count": entity_count,
        "entities_fitted": entities_fitted,
        "train_row_count": train_row_count,
        "test_row_count": test_row_count,
        "train_performance": train_performance,
        "test_performance": test_performance,
        "project_id": project_id,
        "region": region,
    }


def performance_row_from_metadata(
    metadata: dict[str, Any],
    *,
    metric_set: str = "test",
) -> dict[str, Any]:
    """Single performance table row from training metadata."""
    run_at = pd.Timestamp(metadata["run_at"])
    if run_at.tzinfo is not None:
        run_at = run_at.tz_convert("UTC").tz_localize(None)
    perf_key = f"{metric_set}_performance"
    perf = metadata.get(perf_key, {})
    return {
        "model_run_id": metadata["model_run_id"],
        "model_id": metadata["model_id"],
        "config_name": metadata.get("config_name"),
        "model_family": metadata.get("model_family"),
        "model_type": metadata.get("model_type"),
        "run_at": run_at,
        "metric_set": metric_set,
        **perf,
    }
