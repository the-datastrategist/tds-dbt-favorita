"""Generate ARIMA / SARIMA predictions with unified BigQuery rows."""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime as dt
from typing import Any

import pandas as pd

from vertex.config.load_config import DEFAULT_CONFIG_PATH, get_job_spec, load_model_config
from vertex.models.timeseries.ts_common import (
    bundle_model_id,
    predict_forward_rows,
    predict_holdout_rows,
    prepare_panel,
)
from vertex.utils.artifacts import load_joblib_from_gcs, resolve_latest_artifact
from vertex.utils.bigquery_utils import load_to_bigquery
from vertex.utils.data_loading import load_data_from_config
from vertex.utils.predictions import build_standard_prediction_rows, new_predict_run_id

logger = logging.getLogger(__name__)

SUPPORTED_TYPES = frozenset({"arima", "sarima"})


def run_predict_timeseries(config: dict[str, Any]) -> dict[str, Any]:
    spec = get_job_spec(config)
    model_type = spec["model_type"]
    if model_type not in SUPPORTED_TYPES:
        raise ValueError(
            f"predict_timeseries supports {sorted(SUPPORTED_TYPES)}; got {model_type!r}"
        )

    inputs = config.get("inputs", {})
    outputs = config.get("outputs", {})
    config_name = spec["config_name"]
    model_family = spec.get("model_family")

    target_column = inputs.get("target_column") or "sales"
    date_column = inputs.get("date_column", "date")
    entity_column = inputs.get("entity_column", "store_nbr")
    test_size = float(inputs.get("test_size", 0.2))
    predict_scope = inputs.get("predict_scope", "holdout")
    forecast_horizon = int(inputs.get("forecast_horizon", 7))
    id_columns = list(inputs.get("id_columns", ["store_nbr"]))

    gcs_model_path = inputs.get("gcs_model_path")
    artifact_config_name = inputs.get("artifact_config_name")
    model_run_id = inputs.get("model_run_id")
    prediction_table = outputs.get("prediction_table")
    if not gcs_model_path or not prediction_table:
        raise ValueError("inputs.gcs_model_path and outputs.prediction_table are required")

    project_id = inputs.get("project_id") or os.getenv("GOOGLE_PROJECT_ID")

    artifact_uri, manifest = resolve_latest_artifact(
        gcs_model_path,
        artifact_config_name,
        model_run_id=model_run_id,
    )
    joblib_uri = manifest.get("joblib_gcs_uri") or artifact_uri
    bundle = load_joblib_from_gcs(joblib_uri)

    df = load_data_from_config(config)
    entity_column = manifest.get("entity_column", entity_column)
    date_column = manifest.get("date_column", date_column)
    panel = prepare_panel(
        df,
        entity_column=entity_column,
        date_column=date_column,
        target_column=manifest.get("target_column", target_column),
    )

    if predict_scope == "forward":
        scored = predict_forward_rows(
            panel,
            bundle,
            entity_column=entity_column,
            date_column=date_column,
            target_column=target_column,
            forecast_horizon=forecast_horizon,
            id_columns=id_columns,
        )
    else:
        scored = predict_holdout_rows(
            panel,
            bundle,
            entity_column=entity_column,
            date_column=date_column,
            target_column=target_column,
            test_size=test_size,
        )

    if scored.empty:
        raise ValueError("No prediction rows produced; check entities and predict_scope")

    run_at = dt.utcnow()
    parameters = manifest.get("parameters", {})
    model_id = manifest.get("model_id") or bundle_model_id(
        manifest.get("model_type", model_type),
        parameters,
        int(manifest.get("entities_fitted", 0)),
    )
    resolved_run_id = manifest.get("model_run_id") or model_run_id
    predict_run_id = new_predict_run_id(
        model_id=model_id,
        model_run_id=resolved_run_id,
        run_at=run_at,
        artifact_uri=joblib_uri,
    )

    predictions = pd.Series(scored["prediction"].values, index=scored.index)
    prediction_rows = build_standard_prediction_rows(
        scored,
        predictions,
        predict_run_id=predict_run_id,
        model_id=model_id,
        model_run_id=resolved_run_id,
        config_name=config_name,
        model_family=model_family,
        model_type=manifest.get("model_type", model_type),
        target_column=manifest.get("target_column", target_column),
        run_at=run_at,
        id_columns=id_columns,
        date_column=date_column,
        forecast_horizon=forecast_horizon if predict_scope == "forward" else None,
        model_artifact_uri=joblib_uri,
        actual_column="actual" if "actual" in scored.columns else target_column,
    )
    if "forecast_date" in scored.columns:
        prediction_rows["forecast_date"] = scored["forecast_date"].values

    load_to_bigquery(
        data=prediction_rows,
        table_id=prediction_table,
        project_id=project_id,
        if_exists="append",
    )
    logger.info("Wrote %s %s predictions", len(prediction_rows), predict_scope)

    return {
        "predict_run_id": predict_run_id,
        "prediction_count": len(prediction_rows),
        "predict_scope": predict_scope,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Predict with ARIMA/SARIMA")
    parser.add_argument("--config-path", "-f", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--config-name", "-c", required=True)
    args = parser.parse_args()
    run_predict_timeseries(load_model_config(args.config_name, args.config_path))


if __name__ == "__main__":
    main()
