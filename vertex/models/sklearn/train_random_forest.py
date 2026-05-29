"""
Train a RandomForestRegressor and publish joblib artifacts to GCS + BigQuery.

  python -m vertex.models.sklearn.train_random_forest --config-name favorita_rf_train
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime as dt
from typing import Any, Optional

import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from vertex.config.load_config import DEFAULT_CONFIG_PATH, get_job_spec, load_model_config
from vertex.utils.artifacts import save_joblib_artifacts
from vertex.utils.bigquery_utils import load_to_bigquery
from vertex.utils.data_loading import load_data_from_config
from vertex.utils.data_utils import get_hash
from vertex.utils.features import (
    chronological_train_test_split,
    prepare_feature_matrix,
)
from vertex.utils.metadata import (
    build_sklearn_train_metadata,
    metadata_to_bq_row,
    performance_row_from_metadata,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL_PARAMETERS = {
    "n_estimators": 200,
    "max_depth": 12,
    "min_samples_split": 4,
    "min_samples_leaf": 2,
    "random_state": 42,
    "n_jobs": -1,
}

ARTIFACT_MODEL_TYPE = "random_forest"


def train_random_forest(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    model_parameters: Optional[dict[str, Any]] = None,
) -> RandomForestRegressor:
    params = (
        model_parameters.copy()
        if model_parameters is not None
        else DEFAULT_MODEL_PARAMETERS.copy()
    )
    model = RandomForestRegressor(**params)
    model.fit(X_train, y_train)
    return model


def run_train_random_forest(
    config: dict[str, Any],
    *,
    register_vertex_model: bool = False,
) -> dict[str, Any]:
    spec = get_job_spec(config)
    if spec["model_type"] != "random_forest":
        raise ValueError(
            f"Config {spec['config_name']!r} has model_type={spec['model_type']!r}; "
            "expected random_forest."
        )

    inputs = config.get("inputs", {})
    outputs = config.get("outputs", {})
    vertex_cfg = config.get("vertex") or {}
    config_name = spec["config_name"]
    model_family = spec.get("model_family")

    target_column = inputs["target_column"]
    test_size = float(inputs.get("test_size", 0.2))
    date_column = inputs.get("date_column", "date")
    excluded_columns = list(inputs.get("excluded_columns", []))
    categorical_columns = list(inputs.get("categorical_columns", []))
    params = dict(inputs.get("model_params", DEFAULT_MODEL_PARAMETERS))
    gcs_model_path = inputs.get("gcs_model_path")
    if not gcs_model_path:
        raise ValueError("inputs.gcs_model_path is required")

    project_id = inputs.get("project_id") or os.getenv("GOOGLE_PROJECT_ID")
    region = inputs.get("region", "us-central1")
    metadata_table = outputs.get("metadata_table")
    if not metadata_table:
        raise ValueError("outputs.metadata_table is required")

    df = load_data_from_config(config)
    logger.info("Loaded %s training rows", len(df))

    df_features, features, _ = prepare_feature_matrix(
        df,
        target_column=target_column,
        excluded_columns=excluded_columns,
        categorical_columns=categorical_columns,
        date_column=date_column,
    )

    sort_column = date_column if date_column in df_features.columns else None
    X_train, X_test, y_train, y_test = chronological_train_test_split(
        df_features,
        features,
        target_column,
        test_size=test_size,
        date_column=sort_column,
    )

    model = train_random_forest(X_train, y_train, model_parameters=params)

    run_at = dt.utcnow()
    model_id = get_hash(
        {
            "model_type": ARTIFACT_MODEL_TYPE,
            "parameters": params,
            "features": sorted(features),
        }
    )
    model_run_id = get_hash(f"{model_id}:{run_at.isoformat()}")

    joblib_uri, manifest_uri = save_joblib_artifacts(
        model,
        model_run_id=model_run_id,
        model_id=model_id,
        config_name=config_name,
        model_family=model_family,
        model_type=ARTIFACT_MODEL_TYPE,
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
        model_type=ARTIFACT_MODEL_TYPE,
        target_column=target_column,
        run_at=run_at,
        gcs_uri=joblib_uri,
        joblib_gcs_uri=joblib_uri,
        manifest_gcs_uri=manifest_uri,
        source_query=inputs.get("sql_query"),
        model_run_id=model_run_id,
        model_id=model_id,
        project_id=project_id,
        region=region,
    )

    load_to_bigquery(
        data=[metadata_to_bq_row(metadata)],
        table_id=metadata_table,
        project_id=project_id,
        if_exists="append",
    )

    performance_table = outputs.get("performance_table")
    if performance_table:
        load_to_bigquery(
            data=[performance_row_from_metadata(metadata, metric_set="test")],
            table_id=performance_table,
            project_id=project_id,
            if_exists="append",
        )

    if register_vertex_model or vertex_cfg.get("register_model"):
        from vertex.utils.vertex_utils import VertexModelSaver

        saver = VertexModelSaver(
            {
                "name": config_name,
                "inputs": {
                    "project_id": project_id,
                    "region": region,
                    "gcs_model_path": gcs_model_path,
                },
            },
            model,
        )
        saver.model_artifact_uri = joblib_uri
        saver.save_model()

    return {
        "config_name": config_name,
        "model_run_id": model_run_id,
        "model_id": model_id,
        "joblib_gcs_uri": joblib_uri,
        "manifest_gcs_uri": manifest_uri,
    }


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Train Random Forest from model_config.yaml")
    parser.add_argument("--config-path", "-f", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--config-name", "-c", default="favorita_rf_train")
    parser.add_argument("--register-vertex-model", action="store_true")
    args = parser.parse_args()

    config = load_model_config(args.config_name, args.config_path)
    run_train_random_forest(
        config,
        register_vertex_model=args.register_vertex_model,
    )


if __name__ == "__main__":
    main()
