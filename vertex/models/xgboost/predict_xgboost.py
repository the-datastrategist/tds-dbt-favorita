"""
Generate XGBoost predictions using a trained artifact and write unified rows to BigQuery.

  python -m vertex.models.xgboost.predict_xgboost --config-name favorita_xgboost_predict
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime as dt
from typing import Any, Optional

import pandas as pd

from vertex.config.load_config import DEFAULT_CONFIG_PATH, get_job_spec, load_model_config
from vertex.utils.artifacts import load_xgboost_from_gcs, resolve_latest_artifact
from vertex.utils.bigquery_utils import load_to_bigquery
from vertex.utils.data_loading import load_data_from_config
from vertex.utils.data_utils import get_hash
from vertex.utils.features import prepare_feature_matrix
from vertex.utils.ml_utils import sanitize_feature_columns
from vertex.utils.predictions import build_standard_prediction_rows, new_predict_run_id

logger = logging.getLogger(__name__)


def prepare_prediction_features(
    df: pd.DataFrame,
    manifest: dict[str, Any],
    *,
    target_column: str,
    excluded_columns: Optional[list[str]] = None,
    categorical_columns: Optional[list[str]] = None,
    date_column: Optional[str] = None,
) -> pd.DataFrame:
    work = df.copy()
    if target_column not in work.columns:
        work[target_column] = 0

    matrix, features, _ = prepare_feature_matrix(
        work,
        target_column=target_column,
        excluded_columns=excluded_columns or [],
        categorical_columns=categorical_columns or [],
        date_column=date_column,
    )
    manifest_features = manifest.get("features", [])
    if not manifest_features:
        raise ValueError("Model manifest does not contain a features list")
    feature_cols = [column for column in manifest_features if column in matrix.columns]
    return matrix.reindex(columns=feature_cols, fill_value=0)


def prepare_model_input(X: pd.DataFrame) -> pd.DataFrame:
    model_input = sanitize_feature_columns(X)
    bool_cols = model_input.select_dtypes(include="bool").columns
    if len(bool_cols) > 0:
        model_input[bool_cols] = model_input[bool_cols].astype(int)
    return model_input


def get_predictions(model, X: pd.DataFrame) -> pd.Series:
    model_input = prepare_model_input(X)
    predictions = model.predict(model_input)
    return pd.Series(predictions, index=X.index)


def run_predict_xgboost(config: dict[str, Any]) -> dict[str, Any]:
    spec = get_job_spec(config)
    if spec["model_type"] not in ("xgboost", "xgboost_sklearn"):
        raise ValueError(f"predict_xgboost does not support model_type={spec['model_type']!r}")

    inputs = config.get("inputs", {})
    outputs = config.get("outputs", {})
    config_name = spec["config_name"]
    model_family = spec.get("model_family")

    target_column = inputs.get("target_column") or "sales"
    date_column = inputs.get("date_column", "date")
    excluded_columns = list(inputs.get("excluded_columns", []))
    categorical_columns = list(inputs.get("categorical_columns", []))
    id_columns = list(inputs.get("id_columns", ["store_nbr"]))
    gcs_model_path = inputs.get("gcs_model_path")
    if not gcs_model_path:
        raise ValueError("inputs.gcs_model_path is required")

    artifact_config_name = inputs.get("artifact_config_name")
    model_run_id = inputs.get("model_run_id")
    prediction_table = outputs.get("prediction_table")
    if not prediction_table:
        raise ValueError("outputs.prediction_table is required")

    project_id = inputs.get("project_id") or os.getenv("GOOGLE_PROJECT_ID")

    model_gcs_uri, manifest = resolve_latest_artifact(
        gcs_model_path,
        artifact_config_name,
        model_run_id=model_run_id,
    )
    model = load_xgboost_from_gcs(model_gcs_uri)

    df = load_data_from_config(config)
    manifest_target = manifest.get("target_column", target_column)
    X = prepare_prediction_features(
        df,
        manifest,
        target_column=manifest_target,
        excluded_columns=excluded_columns,
        categorical_columns=categorical_columns,
        date_column=date_column,
    )
    predictions = get_predictions(model, X)

    run_at = dt.utcnow()
    features = manifest.get("features", [])
    parameters = manifest.get("parameters", {})
    model_type = manifest.get("model_type", "xgboost_sklearn")
    model_id = manifest.get("model_id") or get_hash(
        {
            "model_type": model_type,
            "parameters": parameters,
            "features": sorted(features),
        }
    )
    resolved_run_id = manifest.get("model_run_id") or model_run_id
    predict_run_id = new_predict_run_id(
        model_id=model_id,
        model_run_id=resolved_run_id,
        run_at=run_at,
        artifact_uri=model_gcs_uri,
    )

    prediction_rows = build_standard_prediction_rows(
        df,
        predictions,
        predict_run_id=predict_run_id,
        model_id=model_id,
        model_run_id=resolved_run_id,
        config_name=config_name,
        model_family=model_family,
        model_type=model_type,
        target_column=manifest_target,
        run_at=run_at,
        id_columns=id_columns,
        date_column=date_column,
        forecast_horizon=inputs.get("forecast_horizon"),
        model_artifact_uri=model_gcs_uri,
        actual_column=target_column if target_column in df.columns else None,
    )

    load_to_bigquery(
        data=prediction_rows,
        table_id=prediction_table,
        project_id=project_id,
        if_exists="append",
    )
    logger.info(
        "Wrote %s predictions to %s (predict_run_id=%s)",
        len(prediction_rows),
        prediction_table,
        predict_run_id,
    )

    return {
        "predict_run_id": predict_run_id,
        "model_id": model_id,
        "model_run_id": resolved_run_id,
        "prediction_count": len(prediction_rows),
        "model_gcs_uri": model_gcs_uri,
    }


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Predict with XGBoost from model_config.yaml")
    parser.add_argument("--config-path", "-f", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--config-name", "-c", required=True)
    args = parser.parse_args()

    config = load_model_config(args.config_name, args.config_path)
    run_predict_xgboost(config)


if __name__ == "__main__":
    main()
