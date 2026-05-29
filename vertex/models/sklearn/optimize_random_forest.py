"""Optuna hyperparameter search for RandomForestRegressor."""

from __future__ import annotations

import argparse
import json
import logging
import os
import uuid
from datetime import datetime as dt
from typing import Any

import optuna
import pandas as pd

from vertex.config.load_config import DEFAULT_CONFIG_PATH, get_job_spec, load_model_config
from vertex.models.sklearn.train_random_forest import (
    ARTIFACT_MODEL_TYPE,
    DEFAULT_MODEL_PARAMETERS,
    train_random_forest,
)
from vertex.utils.bigquery_utils import load_to_bigquery
from vertex.utils.data_loading import load_data_from_config
from vertex.utils.data_utils import get_hash
from vertex.utils.features import (
    chronological_train_test_split,
    prepare_feature_matrix,
)
from vertex.utils.metadata import get_performance_metrics

logger = logging.getLogger(__name__)


def suggest_rf_params(trial: optuna.Trial) -> dict[str, Any]:
    return {
        "n_estimators": trial.suggest_int("n_estimators", 50, 500),
        "max_depth": trial.suggest_int("max_depth", 3, 24),
        "min_samples_split": trial.suggest_int("min_samples_split", 2, 20),
        "min_samples_leaf": trial.suggest_int("min_samples_leaf", 1, 10),
        "random_state": 42,
        "n_jobs": -1,
    }


def _as_bq_timestamp(value: dt) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts


def run_optimize_random_forest(config: dict[str, Any]) -> dict[str, Any]:
    spec = get_job_spec(config)
    if spec["model_type"] != "random_forest":
        raise ValueError(
            f"optimize_random_forest does not support model_type={spec['model_type']!r}"
        )

    inputs = config.get("inputs", {})
    outputs = config.get("outputs", {})
    config_name = spec["config_name"]
    model_family = spec.get("model_family")

    target_column = inputs["target_column"]
    test_size = float(inputs.get("test_size", 0.2))
    date_column = inputs.get("date_column", "date")
    trial_count = int(inputs.get("trial_count", 10))
    objective_metric = inputs.get("objective_metric", "mae")
    excluded_columns = list(inputs.get("excluded_columns", []))
    categorical_columns = list(inputs.get("categorical_columns", []))

    optimize_table = outputs.get("optimize_table")
    if not optimize_table:
        raise ValueError("outputs.optimize_table is required")

    project_id = inputs.get("project_id") or os.getenv("GOOGLE_PROJECT_ID")

    df = load_data_from_config(config)
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

    run_at = dt.utcnow()
    optimize_run_id = uuid.uuid4().hex
    trial_rows: list[dict[str, Any]] = []

    def objective(trial: optuna.Trial) -> float:
        params = suggest_rf_params(trial)
        model = train_random_forest(X_train, y_train, model_parameters=params)
        test_metrics = get_performance_metrics(y_test, model.predict(X_test))

        model_id = get_hash(
            {
                "model_type": ARTIFACT_MODEL_TYPE,
                "parameters": params,
                "features": sorted(features),
            }
        )
        model_run_id = get_hash(f"{model_id}:{run_at.isoformat()}")

        trial_rows.append(
            {
                "optimize_run_id": optimize_run_id,
                "trial_number": int(trial.number),
                "config_name": config_name,
                "model_family": model_family,
                "model_type": ARTIFACT_MODEL_TYPE,
                "model_id": model_id,
                "model_run_id": model_run_id,
                "run_at": _as_bq_timestamp(run_at),
                "run_date": run_at.date(),
                "target_column": target_column,
                "objective_metric": objective_metric,
                "objective_value": float(
                    test_metrics.get(objective_metric, test_metrics["mae"])
                ),
                "feature_count": len(features),
                "test_size": test_size,
                "parameters": json.dumps(params, default=str),
                "test_performance": json.dumps(test_metrics, default=str),
            }
        )
        return float(test_metrics.get(objective_metric, test_metrics["mae"]))

    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=trial_count)

    if trial_rows:
        load_to_bigquery(
            data=trial_rows,
            table_id=optimize_table,
            project_id=project_id,
            if_exists="append",
        )

    best = study.best_trial
    return {
        "optimize_run_id": optimize_run_id,
        "best_trial_number": int(best.number),
        "best_params": best.params,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Optimize Random Forest hyperparameters")
    parser.add_argument("--config-path", "-f", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--config-name", "-c", default="favorita_rf_optimize")
    args = parser.parse_args()
    result = run_optimize_random_forest(load_model_config(args.config_name, args.config_path))
    logger.info("Best params: %s", result["best_params"])


if __name__ == "__main__":
    main()
