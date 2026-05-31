"""Train per-entity ARIMA / SARIMA models and publish artifacts to GCS + BigQuery."""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime as dt
from typing import Any

from vertex.config.load_config import DEFAULT_CONFIG_PATH, get_job_spec, load_model_config
from vertex.models.timeseries.ts_common import (
    bundle_model_id,
    default_model_params,
    fit_entity_models,
    prepare_panel,
)
from vertex.utils.artifacts import save_joblib_artifacts
from vertex.utils.bigquery_utils import load_to_bigquery
from vertex.utils.data_loading import load_data_from_config, resolve_input_sql
from vertex.utils.data_utils import get_hash
from vertex.utils.metadata import (
    build_timeseries_train_metadata,
    metadata_to_bq_row,
    performance_row_from_metadata,
)
from vertex.utils.optimize_params import resolve_model_parameters

logger = logging.getLogger(__name__)

SUPPORTED_TYPES = frozenset({"arima", "sarima"})


def run_train_timeseries(config: dict[str, Any]) -> dict[str, Any]:
    spec = get_job_spec(config)
    model_type = spec["model_type"]
    if model_type not in SUPPORTED_TYPES:
        raise ValueError(f"train_timeseries supports {sorted(SUPPORTED_TYPES)}; got {model_type!r}")

    inputs = config.get("inputs", {})
    outputs = config.get("outputs", {})
    config_name = spec["config_name"]
    model_family = spec.get("model_family")

    target_column = inputs["target_column"]
    date_column = inputs.get("date_column", "date")
    entity_column = inputs.get("entity_column", "store_nbr")
    test_size = float(inputs.get("test_size", 0.2))
    min_train_obs = int(inputs.get("min_train_obs", 30))
    max_entities = inputs.get("max_entities")
    if max_entities is not None:
        max_entities = int(max_entities)

    params, params_provenance = resolve_model_parameters(config, default_model_params(model_type))

    gcs_model_path = inputs.get("gcs_model_path")
    if not gcs_model_path:
        raise ValueError("inputs.gcs_model_path is required")

    project_id = inputs.get("project_id") or os.getenv("GOOGLE_PROJECT_ID")
    region = inputs.get("region", "us-central1")
    metadata_table = outputs.get("metadata_table")
    if not metadata_table:
        raise ValueError("outputs.metadata_table is required")

    df = load_data_from_config(config)
    panel = prepare_panel(
        df,
        entity_column=entity_column,
        date_column=date_column,
        target_column=target_column,
    )
    logger.info(
        "Prepared panel with %s rows, %s entities", len(panel), panel[entity_column].nunique()
    )

    bundle, train_perf, test_perf, entity_count, entities_fitted = fit_entity_models(
        panel,
        entity_column=entity_column,
        date_column=date_column,
        target_column=target_column,
        test_size=test_size,
        model_type=model_type,
        model_params=params,
        min_train_obs=min_train_obs,
        max_entities=max_entities,
    )

    run_at = dt.utcnow()
    artifact_model_type = model_type
    model_id = bundle_model_id(artifact_model_type, params, entities_fitted)
    model_run_id = get_hash(f"{model_id}:{run_at.isoformat()}")

    manifest_params = {
        **params,
        "entity_column": entity_column,
        "date_column": date_column,
        "test_size": test_size,
        "min_train_obs": min_train_obs,
        "training_mode": inputs.get("training_mode", "per_entity"),
    }

    joblib_uri, manifest_uri = save_joblib_artifacts(
        bundle,
        model_run_id=model_run_id,
        model_id=model_id,
        config_name=config_name,
        model_family=model_family,
        model_type=artifact_model_type,
        target_column=target_column,
        parameters=manifest_params,
        gcs_model_path=gcs_model_path,
        run_at=run_at,
        extra_manifest={
            "entity_column": entity_column,
            "date_column": date_column,
            "entities_fitted": entities_fitted,
            "entity_count": entity_count,
            "predict_scope_default": inputs.get("predict_scope", "holdout"),
        },
    )

    metadata = build_timeseries_train_metadata(
        config_name=config_name,
        model_type=artifact_model_type,
        model_family=model_family,
        target_column=target_column,
        run_at=run_at,
        model_run_id=model_run_id,
        model_id=model_id,
        parameters=manifest_params,
        entity_count=entity_count,
        entities_fitted=entities_fitted,
        train_row_count=int(len(panel) * (1 - test_size)),
        test_row_count=int(len(panel) * test_size),
        train_performance=train_perf,
        test_performance=test_perf,
        source_query=resolve_input_sql(config, step="train"),
        joblib_gcs_uri=joblib_uri,
        manifest_gcs_uri=manifest_uri,
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

    logger.info(
        "Fitted %s/%s entities for %s (model_run_id=%s)",
        entities_fitted,
        entity_count,
        model_type,
        model_run_id,
    )
    return {
        "model_run_id": model_run_id,
        "model_id": model_id,
        "joblib_gcs_uri": joblib_uri,
        "manifest_gcs_uri": manifest_uri,
        "entities_fitted": entities_fitted,
        "params_provenance": params_provenance,
        "train_row_count": int(len(panel)),
        "row_count": int(len(panel)),
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Train ARIMA/SARIMA from model_config.yaml")
    parser.add_argument("--config-path", "-f", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--config-name", "-c", default="favorita_arima_train")
    args = parser.parse_args()
    run_train_timeseries(load_model_config(args.config_name, args.config_path))


if __name__ == "__main__":
    main()
