"""Optuna search over ARIMA / SARIMA orders (per-entity aggregate objective)."""

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
from vertex.models.timeseries.ts_common import (
    bundle_model_id,
    default_model_params,
    fit_entity_models,
    prepare_panel,
)
from vertex.utils.bigquery_utils import load_to_bigquery
from vertex.utils.data_loading import load_training_data_from_config
from vertex.utils.data_utils import get_hash
from vertex.utils.optimize_params import complete_optimize_result

logger = logging.getLogger(__name__)

SUPPORTED_TYPES = frozenset({"arima", "sarima"})


def suggest_orders(trial: optuna.Trial, model_type: str) -> dict[str, Any]:
    order = [
        trial.suggest_int("p", 0, 3),
        trial.suggest_int("d", 0, 2),
        trial.suggest_int("q", 0, 3),
    ]
    params: dict[str, Any] = {
        "order": order,
        "trend": "c",
        "maxiter": 50,
    }
    if model_type == "sarima":
        params["seasonal_order"] = [
            trial.suggest_int("P", 0, 2),
            trial.suggest_int("D", 0, 1),
            trial.suggest_int("Q", 0, 2),
            trial.suggest_int("s", 7, 7),
        ]
    else:
        params["seasonal_order"] = [0, 0, 0, 0]
    return params


def run_optimize_timeseries(config: dict[str, Any]) -> dict[str, Any]:
    spec = get_job_spec(config)
    model_type = spec["model_type"]
    if model_type not in SUPPORTED_TYPES:
        raise ValueError(
            f"optimize_timeseries supports {sorted(SUPPORTED_TYPES)}; got {model_type!r}"
        )

    inputs = config.get("inputs", {})
    outputs = config.get("outputs", {})
    config_name = spec["config_name"]
    model_family = spec.get("model_family")

    target_column = inputs["target_column"]
    date_column = inputs.get("date_column", "date")
    entity_column = inputs.get("entity_column", "store_nbr")
    test_size = float(inputs.get("test_size", 0.2))
    trial_count = int(inputs.get("trial_count", 10))
    objective_metric = inputs.get("objective_metric", "mae")
    min_train_obs = int(inputs.get("min_train_obs", 30))
    max_entities = inputs.get("max_entities")
    if max_entities is not None:
        max_entities = int(max_entities)

    optimize_table = outputs.get("optimize_table")
    if not optimize_table:
        raise ValueError("outputs.optimize_table is required")

    project_id = inputs.get("project_id") or os.getenv("GOOGLE_PROJECT_ID")

    df = load_training_data_from_config(config)
    panel = prepare_panel(
        df,
        entity_column=entity_column,
        date_column=date_column,
        target_column=target_column,
    )

    run_at = dt.utcnow()
    optimize_run_id = uuid.uuid4().hex
    trial_rows: list[dict[str, Any]] = []

    def objective(trial: optuna.Trial) -> float:
        params = suggest_orders(trial, model_type)
        base = default_model_params(model_type)
        base.update(params)

        try:
            _bundle, _train_perf, test_perf, entity_count, entities_fitted = fit_entity_models(
                panel,
                entity_column=entity_column,
                date_column=date_column,
                target_column=target_column,
                test_size=test_size,
                model_type=model_type,
                model_params=base,
                min_train_obs=min_train_obs,
                max_entities=max_entities,
            )
        except ValueError:
            logger.info(
                "Trial %s/%s finished: %s=inf (no entities fitted) params=%s",
                trial.number + 1,
                trial_count,
                objective_metric,
                trial.params,
            )
            return float("inf")

        model_id = bundle_model_id(model_type, base, entities_fitted)
        model_run_id = get_hash(f"{model_id}:{run_at.isoformat()}")

        objective_value = float(test_perf.get(objective_metric, test_perf["mae"]))
        trial_rows.append(
            {
                "optimize_run_id": optimize_run_id,
                "trial_number": int(trial.number),
                "config_name": config_name,
                "model_family": model_family,
                "model_type": model_type,
                "model_id": model_id,
                "model_run_id": model_run_id,
                "run_at": pd.Timestamp(run_at),
                "run_date": run_at.date(),
                "target_column": target_column,
                "objective_metric": objective_metric,
                "objective_value": objective_value,
                "feature_count": 0,
                "test_size": test_size,
                "parameters": json.dumps(base, default=str),
                "test_performance": json.dumps(test_perf, default=str),
            }
        )
        logger.info(
            "Trial %s/%s finished: %s=%.6f params=%s",
            trial.number + 1,
            trial_count,
            objective_metric,
            objective_value,
            trial.params,
        )
        return objective_value

    study = optuna.create_study(direction="minimize")
    logger.info(
        "Starting Optuna study: %s trials, minimizing %s",
        trial_count,
        objective_metric,
    )
    study.optimize(objective, n_trials=trial_count)

    if trial_rows:
        load_to_bigquery(
            data=trial_rows,
            table_id=optimize_table,
            project_id=project_id,
            if_exists="append",
        )
        logger.info("Wrote %s trials to %s", len(trial_rows), optimize_table)

    best = study.best_trial
    result = {
        "optimize_run_id": optimize_run_id,
        "config_name": spec["config_name"],
        "best_trial_number": int(best.number),
        "best_value": float(best.value),
        "best_params": best.params,
    }
    return complete_optimize_result(config, result)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Optimize ARIMA/SARIMA orders")
    parser.add_argument("--config-path", "-f", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--config-name", "-c", default="favorita_store_n1d_arima")
    args = parser.parse_args()
    config = load_model_config(args.config_name, args.config_path, step="optimize")
    result = run_optimize_timeseries(config)
    logger.info("Best trial %s: %s", result["best_trial_number"], result["best_params"])


if __name__ == "__main__":
    main()
