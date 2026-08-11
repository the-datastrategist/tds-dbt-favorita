#!/usr/bin/env python3
"""Persist base-versus-reconciled metrics by hierarchy level for one backtest run."""

from __future__ import annotations

import argparse
import json
import re

import pandas as pd

from vertex.evaluation.reconciliation_persistence import (
    build_reconciliation_metric_records,
    persist_reconciliation_metric_records,
)
from vertex.utils.bigquery_utils import run_query

DEFAULT_TABLE_PREFIX = "tds-favorita.favorita"
RUN_ID_PATTERN = re.compile(r"^[a-f0-9]{64}$")
CONFIG_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def evaluate_hierarchical_backtest(
    *,
    backtest_run_id: str,
    model_config_name: str,
    project_id: str,
    table_prefix: str = DEFAULT_TABLE_PREFIX,
) -> pd.DataFrame:
    if not RUN_ID_PATTERN.fullmatch(backtest_run_id):
        raise ValueError("backtest_run_id must be a 64-character lowercase hex digest")
    if not CONFIG_NAME_PATTERN.fullmatch(model_config_name):
        raise ValueError("model_config_name contains unsupported characters")
    rows = run_query(
        f"""
        SELECT forecast_origin, target_date, horizon, entity_key_json, actual, prediction
        FROM `{table_prefix}.backtest_predictions`
        WHERE backtest_run_id = '{backtest_run_id}'
          AND baseline_name = '{model_config_name}'
          AND actual IS NOT NULL
          AND prediction IS NOT NULL
        """,
        project_id=project_id,
    )
    if rows.empty:
        raise RuntimeError("no eligible backtest predictions found")
    rows["store_id"] = rows["entity_key_json"].map(
        lambda value: int(
            (value if isinstance(value, dict) else json.loads(value)).get(
                "store_id",
                (value if isinstance(value, dict) else json.loads(value)).get("store_nbr"),
            )
        )
    )
    stores = rows.assign(
        level_name="store",
        base_prediction_p50=rows["prediction"].astype(float),
        prediction_p50=rows["prediction"].astype(float),
    )
    companies = (
        rows.groupby(["forecast_origin", "target_date", "horizon"], as_index=False)
        .agg(actual=("actual", "sum"), prediction=("prediction", "sum"))
        .assign(level_name="company")
    )
    companies["base_prediction_p50"] = companies["prediction"].astype(float)
    companies["prediction_p50"] = companies["prediction"].astype(float)
    evaluation = pd.concat([stores, companies], ignore_index=True, sort=False)
    metrics = build_reconciliation_metric_records(
        evaluation,
        hierarchy_name="favorita_demand",
        hierarchy_version="v1",
        evaluation_run_id=backtest_run_id,
        model_config_name=model_config_name,
    )
    persist_reconciliation_metric_records(
        metrics,
        table=f"{table_prefix}.forecast_reconciliation_metrics",
        project_id=project_id,
    )
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backtest-run-id", required=True)
    parser.add_argument("--model-config-name", default="favorita_store_h7_xgboost")
    parser.add_argument("--project-id", default="tds-favorita")
    parser.add_argument("--table-prefix", default=DEFAULT_TABLE_PREFIX)
    args = parser.parse_args()
    result = evaluate_hierarchical_backtest(**vars(args))
    print(result.to_json(orient="records", indent=2, date_format="iso"))


if __name__ == "__main__":
    main()
