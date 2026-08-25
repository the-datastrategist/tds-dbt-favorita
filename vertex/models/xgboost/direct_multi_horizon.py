"""Direct multi-horizon XGBoost bundle with one estimator per horizon."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import pandas as pd

from vertex.config.feature_availability import validate_model_features_from_config
from vertex.config.load_config import get_job_spec
from vertex.models.xgboost.predict_xgboost import prepare_model_input, prepare_prediction_features
from vertex.models.xgboost.train_xgboost import DEFAULT_MODEL_PARAMETERS, train_sklearn_xgboost
from vertex.utils.artifacts import (
    load_joblib_from_gcs,
    resolve_latest_artifact,
    save_joblib_artifacts,
)
from vertex.utils.bigquery_utils import load_to_bigquery
from vertex.utils.data_loading import load_data_from_config
from vertex.utils.data_utils import get_hash
from vertex.utils.features import chronological_train_test_split, prepare_feature_matrix
from vertex.utils.optimize_params import resolve_model_parameters
from vertex.utils.predictions import build_standard_prediction_rows, new_predict_run_id


def target_columns_by_horizon(inputs: dict[str, Any]) -> dict[int, str]:
    """Return and validate the direct horizon-to-target mapping."""
    raw = inputs.get("target_columns_by_horizon")
    if not isinstance(raw, dict) or not raw:
        raise ValueError("inputs.target_columns_by_horizon must be a non-empty mapping")
    targets = {int(horizon): str(column) for horizon, column in raw.items()}
    declared = [int(value) for value in inputs.get("prediction_horizons", [])]
    if sorted(targets) != sorted(declared):
        raise ValueError("target_columns_by_horizon must match prediction_horizons")
    return targets


def validate_complete_horizon_batch(
    rows: pd.DataFrame,
    *,
    horizons: list[int],
    entity_columns: list[str],
) -> None:
    """Reject missing or duplicate entity/horizon keys in a logical prediction run."""
    required = {*entity_columns, "forecast_horizon"}
    if missing := sorted(required.difference(rows.columns)):
        raise ValueError(f"prediction batch is missing required columns: {missing}")
    keys = [*entity_columns, "forecast_horizon"]
    if rows.duplicated(keys).any():
        raise ValueError("prediction batch contains duplicate entity/horizon keys")
    expected = set(horizons)
    observed = rows.groupby(entity_columns, dropna=False)["forecast_horizon"].agg(
        lambda values: set(values.astype(int))
    )
    if observed.empty or any(values != expected for values in observed):
        raise ValueError("every eligible entity must contain every configured horizon")


def run_train_direct_xgboost(config: dict[str, Any]) -> dict[str, Any]:
    """Fit and persist one estimator per configured direct horizon."""
    spec = get_job_spec(config)
    inputs = config.get("inputs") or {}
    targets = target_columns_by_horizon(inputs)
    frame = load_data_from_config(config)
    excluded = list(inputs.get("excluded_columns", [])) + list(targets.values())
    parameters, _ = resolve_model_parameters(config, DEFAULT_MODEL_PARAMETERS)
    models: dict[int, Any] = {}
    common_features: list[str] | None = None
    for horizon, target in sorted(targets.items()):
        matrix, features, _ = prepare_feature_matrix(
            frame,
            target_column=target,
            excluded_columns=excluded,
            categorical_columns=list(inputs.get("categorical_columns", [])),
            date_column=inputs.get("date_column", "period_start"),
        )
        if common_features is None:
            common_features = features
        elif features != common_features:
            raise ValueError("direct horizon estimators must use identical feature columns")
        X_train, _, y_train, _ = chronological_train_test_split(
            matrix,
            features,
            target,
            test_size=float(inputs.get("test_size", 0.2)),
            date_column=inputs.get("date_column", "period_start"),
            purge_days=int(inputs.get("validation_purge_days", 0)),
        )
        models[horizon] = train_sklearn_xgboost(X_train, y_train, parameters)
    assert common_features is not None
    validate_model_features_from_config(
        config, common_features, context=f"{spec['config_name']} direct training features"
    )
    model_id = get_hash(
        {
            "model_type": "xgboost_direct",
            "parameters": parameters,
            "features": common_features,
            "targets": targets,
        }
    )
    run_at = datetime.utcnow()
    model_run_id = get_hash({"model_id": model_id, "run_at": run_at.isoformat()})
    artifact_uri, manifest_uri = save_joblib_artifacts(
        models,
        model_run_id=model_run_id,
        model_id=model_id,
        config_name=spec["config_name"],
        model_family=spec.get("model_family"),
        model_type="xgboost_direct",
        target_column="multi_horizon",
        parameters=parameters,
        gcs_model_path=inputs["gcs_model_path"],
        features=common_features,
        run_at=run_at,
        extra_manifest={
            "target_columns_by_horizon": targets,
            "prediction_horizons": sorted(targets),
        },
    )
    return {
        "model_run_id": model_run_id,
        "model_id": model_id,
        "model_gcs_uri": artifact_uri,
        "manifest_gcs_uri": manifest_uri,
        "horizons": sorted(targets),
        "training_row_count": len(frame),
    }


def run_predict_direct_xgboost(config: dict[str, Any]) -> dict[str, Any]:
    """Score all estimators and persist one complete logical horizon batch."""
    spec = get_job_spec(config)
    inputs = config.get("inputs") or {}
    outputs = config.get("outputs") or {}
    targets = target_columns_by_horizon(inputs)
    artifact_uri, manifest = resolve_latest_artifact(
        inputs["gcs_model_path"],
        inputs.get("artifact_config_name") or spec["config_name"],
        model_run_id=inputs.get("model_run_id"),
    )
    models = load_joblib_from_gcs(artifact_uri, expected_sha256=manifest.get("joblib_sha256"))
    if set(int(value) for value in models) != set(targets):
        raise ValueError("direct artifact does not contain every configured horizon")
    frame = load_data_from_config(config)
    first_target = targets[min(targets)]
    features = prepare_prediction_features(
        frame,
        manifest,
        target_column=first_target,
        excluded_columns=list(inputs.get("excluded_columns", [])) + list(targets.values()),
        categorical_columns=list(inputs.get("categorical_columns", [])),
        date_column=inputs.get("date_column", "period_start"),
    )
    model_input = prepare_model_input(features)
    validate_model_features_from_config(
        config,
        list(model_input.columns),
        context=f"{spec['config_name']} direct prediction features",
    )
    run_at = datetime.utcnow()
    predict_run_id = new_predict_run_id(
        model_id=manifest["model_id"],
        model_run_id=manifest["model_run_id"],
        run_at=run_at,
        artifact_uri=artifact_uri,
    )
    batches: list[pd.DataFrame] = []
    id_columns = list(inputs.get("id_columns", ["series_key"]))
    for horizon in sorted(targets):
        batch = build_standard_prediction_rows(
            frame.loc[model_input.index],
            pd.Series(models[horizon].predict(model_input), index=model_input.index),
            predict_run_id=predict_run_id,
            model_id=manifest["model_id"],
            model_run_id=manifest["model_run_id"],
            config_name=spec["config_name"],
            model_family=spec.get("model_family"),
            model_type="xgboost_direct",
            target_column=targets[horizon],
            run_at=run_at,
            id_columns=id_columns,
            date_column=inputs.get("date_column", "period_start"),
            forecast_horizon=horizon,
            model_artifact_uri=artifact_uri,
            actual_column=targets[horizon] if targets[horizon] in frame.columns else None,
        )
        batch["forecast_strategy"] = "entity_model"
        batch["confidence_flag"] = "high"
        batches.append(batch)
    rows = pd.concat(batches, ignore_index=True)
    validate_complete_horizon_batch(
        rows,
        horizons=sorted(targets),
        entity_columns=[*id_columns, inputs.get("date_column", "period_start")],
    )
    project_id = inputs.get("project_id") or os.getenv("GOOGLE_PROJECT_ID")
    load_to_bigquery(rows, outputs["prediction_table"], project_id=project_id, if_exists="append")
    return {
        "predict_run_id": predict_run_id,
        "model_run_id": manifest["model_run_id"],
        "model_id": manifest["model_id"],
        "prediction_count": len(rows),
        "horizons": sorted(targets),
        "model_gcs_uri": artifact_uri,
    }
