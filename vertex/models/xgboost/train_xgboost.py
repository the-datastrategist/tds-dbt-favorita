"""
Train an XGBoost regressor via the scikit-learn API and publish artifacts to GCS + BigQuery.

  python -m vertex.models.xgboost.train_xgboost --config-name favorita_xgboost_train
  python -m vertex.jobs.run --config-name favorita_xgboost_train
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime as dt
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from xgboost import XGBRegressor

from vertex.config.load_config import DEFAULT_CONFIG_PATH, get_job_spec, load_model_config
from vertex.utils.artifacts import (
    VERTEX_SKLEARN_SERVING_IMAGE,
    register_from_manifest,
    save_xgboost_sklearn_artifacts,
)
from vertex.utils.bigquery_utils import load_to_bigquery
from vertex.utils.data_loading import load_data_from_config, resolve_input_sql
from vertex.utils.data_utils import get_hash
from vertex.utils.metadata import (
    build_sklearn_train_metadata,
    metadata_to_bq_row,
    performance_row_from_metadata,
)
from vertex.utils.optimize_params import resolve_model_parameters

__all__ = [
    "metadata_to_bq_row",
    "get_performance_metrics",
    "get_train_metadata",
    "prepare_feature_matrix",
    "chronological_train_test_split",
    "train_sklearn_xgboost",
    "run_train_xgboost",
]
from vertex.utils.features import (
    chronological_train_test_split,
    prepare_feature_matrix,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL_PARAMETERS = {
    "objective": "reg:squarederror",
    "eval_metric": "mae",
    "n_estimators": 100,
    "learning_rate": 0.1,
    "max_depth": 5,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "random_state": 42,
    "n_jobs": -1,
}

# Re-export for tests and legacy imports
from vertex.utils.metadata import get_performance_metrics  # noqa: E402


def train_sklearn_xgboost(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    model_parameters: Optional[dict[str, Any]] = None,
) -> XGBRegressor:
    params = (
        model_parameters.copy() if model_parameters is not None else DEFAULT_MODEL_PARAMETERS.copy()
    )
    model = XGBRegressor(**params)
    model.fit(X_train, y_train)
    return model


def get_train_metadata(
    model: XGBRegressor,
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
    y_train: pd.Series,
    y_test: pd.Series,
    **kwargs: Any,
) -> dict[str, Any]:
    """Backward-compatible wrapper around build_sklearn_train_metadata."""
    kwargs.setdefault("model_type", "xgboost_sklearn")
    kwargs.setdefault(
        "extra",
        {"sklearn_serving_image": VERTEX_SKLEARN_SERVING_IMAGE},
    )
    return build_sklearn_train_metadata(model, X_train, X_test, y_train, y_test, **kwargs)


def run_train_xgboost(
    config: dict[str, Any],
    *,
    register_vertex_model: bool = False,
) -> dict[str, Any]:
    """End-to-end training: BigQuery load, fit, GCS artifacts, metadata to BQ."""
    spec = get_job_spec(config)
    model_type = spec["model_type"]
    if model_type not in ("xgboost", "xgboost_sklearn"):
        raise ValueError(
            f"Config {spec['config_name']!r} has model_type={model_type!r}; "
            "expected xgboost or xgboost_sklearn."
        )

    inputs = config.get("inputs", {})
    outputs = config.get("outputs", {})
    vertex_cfg = config.get("vertex") or {}
    config_name = spec["config_name"]
    model_family = spec.get("model_family")
    artifact_model_type = "xgboost_sklearn"

    target_column = inputs["target_column"]
    test_size = float(inputs.get("test_size", 0.2))
    date_column = inputs.get("date_column", "date")
    excluded_columns = list(inputs.get("excluded_columns", []))
    categorical_columns = list(inputs.get("categorical_columns", []))
    params, params_provenance = resolve_model_parameters(config, DEFAULT_MODEL_PARAMETERS)
    gcs_model_path = inputs.get("gcs_model_path")
    if not gcs_model_path:
        raise ValueError("inputs.gcs_model_path is required")

    project_id = inputs.get("project_id") or os.getenv("GOOGLE_PROJECT_ID")
    region = inputs.get("region", "us-central1")
    metadata_table = outputs.get("metadata_table")
    if not metadata_table:
        raise ValueError("outputs.metadata_table is required for training metadata")

    df = load_data_from_config(config)
    logger.info("Loaded %s training rows", len(df))

    df_features, features, _dates = prepare_feature_matrix(
        df,
        target_column=target_column,
        excluded_columns=excluded_columns,
        categorical_columns=categorical_columns,
        date_column=date_column,
    )
    logger.info("Using %s features", len(features))

    sort_column = date_column if date_column in df_features.columns else None
    X_train, X_test, y_train, y_test = chronological_train_test_split(
        df_features,
        features,
        target_column,
        test_size=test_size,
        date_column=sort_column,
    )

    model = train_sklearn_xgboost(X_train, y_train, model_parameters=params)

    run_at = dt.utcnow()
    model_id = get_hash(
        {
            "model_type": artifact_model_type,
            "parameters": params,
            "features": sorted(features),
        }
    )
    model_run_id = get_hash(f"{model_id}:{run_at.isoformat()}")

    json_uri, joblib_uri, trees_uri, manifest_uri = save_xgboost_sklearn_artifacts(
        model,
        model_run_id=model_run_id,
        model_id=model_id,
        config_name=config_name,
        model_family=model_family,
        model_type=artifact_model_type,
        features=features,
        target_column=target_column,
        parameters=params,
        gcs_model_path=gcs_model_path,
        run_at=run_at,
    )

    metadata = build_sklearn_train_metadata(
        model,
        X_train,
        X_test,
        y_train,
        y_test,
        config_name=config_name,
        model_family=model_family,
        model_type=artifact_model_type,
        target_column=target_column,
        run_at=run_at,
        gcs_uri=json_uri,
        joblib_gcs_uri=joblib_uri,
        trees_gcs_uri=trees_uri,
        manifest_gcs_uri=manifest_uri,
        source_query=resolve_input_sql(config, step="train"),
        model_run_id=model_run_id,
        model_id=model_id,
        project_id=project_id,
        region=region,
        extra={"sklearn_serving_image": VERTEX_SKLEARN_SERVING_IMAGE},
    )

    load_to_bigquery(
        data=[metadata_to_bq_row(metadata)],
        table_id=metadata_table,
        project_id=project_id,
        if_exists="append",
    )
    logger.info("Wrote training metadata to %s", metadata_table)

    performance_table = outputs.get("performance_table")
    if performance_table:
        load_to_bigquery(
            data=[performance_row_from_metadata(metadata, metric_set="test")],
            table_id=performance_table,
            project_id=project_id,
            if_exists="append",
        )
        logger.info("Wrote test performance to %s", performance_table)

    if register_vertex_model or vertex_cfg.get("register_model"):
        register_from_manifest(
            manifest_uri=manifest_uri,
            display_name=config_name,
            project_id=project_id,
            region=region,
            artifact_uri=joblib_uri,
        )
        logger.info("Registered model in Vertex AI Model Registry")

    train_rows = len(df_features)
    return {
        "model": model,
        "config_name": config_name,
        "model_run_id": model_run_id,
        "model_id": model_id,
        "gcs_uri": json_uri,
        "joblib_gcs_uri": joblib_uri,
        "manifest_gcs_uri": manifest_uri,
        "metadata": metadata,
        "params_provenance": params_provenance,
        "train_row_count": train_rows,
        "row_count": train_rows,
    }


def run_train_xgboost_from_yaml(
    config_path: str | Path,
    config_name: Optional[str] = None,
    *,
    register_vertex_model: bool = False,
) -> dict[str, Any]:
    if not config_name:
        raise ValueError("config_name is required")
    config = load_model_config(config_name, config_path)
    return run_train_xgboost(config, register_vertex_model=register_vertex_model)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Train XGBoost from model_config.yaml")
    parser.add_argument(
        "--config-path",
        "-f",
        default=str(DEFAULT_CONFIG_PATH),
    )
    parser.add_argument(
        "--config-name",
        "-c",
        default="favorita_xgboost_train",
    )
    parser.add_argument("--register-vertex-model", action="store_true")
    args = parser.parse_args()

    register_vertex = args.register_vertex_model
    if not register_vertex:
        env_flag = os.getenv("REGISTER_VERTEX_MODEL", "").lower()
        register_vertex = env_flag in ("1", "true", "yes")

    run_train_xgboost_from_yaml(
        config_path=args.config_path,
        config_name=args.config_name,
        register_vertex_model=register_vertex,
    )


if __name__ == "__main__":
    main()
