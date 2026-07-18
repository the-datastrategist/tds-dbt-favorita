"""Backtest planning and rolling-origin model/baseline scoring CLI."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import timedelta
from pathlib import Path

import pandas as pd

from vertex.config.backtest_contract import (
    DEFAULT_BACKTEST_CONTRACT_PATH,
    BacktestContract,
    load_backtest_contract,
)
from vertex.evaluation.backtesting import (
    BaselineBacktestResult,
    score_baselines,
    score_model_and_baselines,
)
from vertex.evaluation.persistence import persist_backtest_result
from vertex.utils.bigquery_utils import run_query, validate_bq_identifier
from vertex.utils.data_loading import resolve_training_sql

logger = logging.getLogger(__name__)


def build_backtest_plan(contract_path: str | Path | None = None) -> list[dict[str, object]]:
    """Return one origin/horizon plan row per required backtest score."""
    contract = load_backtest_contract(contract_path)
    return contract.origin_plan_rows()


def build_bigquery_history_query(contract: BacktestContract) -> str:
    """Build a bounded, column-pruned history query for a backtest contract."""
    columns = list(
        dict.fromkeys(
            [
                *contract.entity_columns,
                *contract.segment_columns,
                contract.date_column,
                contract.actual_column,
            ]
        )
    )
    validated_columns = [
        validate_bq_identifier(column, label="history column") for column in columns
    ]
    selected = ", ".join(f"`{column}`" for column in validated_columns)
    date_column = validate_bq_identifier(contract.date_column, label="history date column")
    history_days = contract.train_window_days
    if "same_period_last_year" in contract.baselines:
        history_days = max(history_days, 366)
    history_start = min(contract.origins) - timedelta(days=history_days)
    history_end = max(contract.origins) + timedelta(days=max(contract.horizons))
    bounded_history = (
        f"SELECT {selected} FROM `{contract.history_table}` "
        f"WHERE `{date_column}` BETWEEN DATE '{history_start.isoformat()}' "
        f"AND DATE '{history_end.isoformat()}'"
    )
    if contract.max_entities is None:
        return bounded_history

    entity_columns = [
        validate_bq_identifier(column, label="history entity column")
        for column in contract.entity_columns
    ]
    entity_select = ", ".join(f"`{column}`" for column in entity_columns)
    entity_order = ", ".join(f"`{column}`" for column in entity_columns)
    join_condition = " AND ".join(
        f"history.`{column}` = entities.`{column}`" for column in entity_columns
    )
    return (
        "WITH bounded_history AS ("
        f"{bounded_history}"
        "), selected_entities AS ("
        f"SELECT DISTINCT {entity_select} FROM bounded_history "
        f"ORDER BY {entity_order} LIMIT {contract.max_entities}"
        ") "
        f"SELECT {', '.join(f'history.`{column}`' for column in validated_columns)} "
        "FROM bounded_history AS history "
        f"INNER JOIN selected_entities AS entities ON {join_condition}"
    )


def build_bigquery_model_history_query(contract: BacktestContract) -> str:
    """Build a bounded query over the configured model's complete feature input."""
    model_query = resolve_training_sql(contract.model_config).rstrip(";\n ")
    date_column = validate_bq_identifier(contract.date_column, label="history date column")
    history_days = contract.train_window_days + max(contract.horizons)
    if "same_period_last_year" in contract.baselines:
        history_days = max(history_days, 366)
    history_start = min(contract.origins) - timedelta(days=history_days)
    history_end = max(contract.origins) + timedelta(days=max(contract.horizons))
    bounded_history = (
        "SELECT model_history.* "
        f"FROM ({model_query}) AS model_history "
        f"WHERE model_history.`{date_column}` BETWEEN DATE '{history_start.isoformat()}' "
        f"AND DATE '{history_end.isoformat()}'"
    )
    if contract.max_entities is None:
        return bounded_history

    entity_columns = [
        validate_bq_identifier(column, label="history entity column")
        for column in contract.entity_columns
    ]
    entity_select = ", ".join(f"`{column}`" for column in entity_columns)
    entity_order = ", ".join(f"`{column}`" for column in entity_columns)
    join_condition = " AND ".join(
        f"history.`{column}` = entities.`{column}`" for column in entity_columns
    )
    return (
        "WITH bounded_history AS ("
        f"{bounded_history}"
        "), selected_entities AS ("
        f"SELECT DISTINCT {entity_select} FROM bounded_history "
        f"ORDER BY {entity_order} LIMIT {contract.max_entities}"
        ") SELECT history.* FROM bounded_history AS history "
        f"INNER JOIN selected_entities AS entities ON {join_condition}"
    )


def run_baseline_backtest(
    input_csv: str | Path | None = None,
    contract_path: str | Path | None = None,
    *,
    use_bigquery: bool = False,
    project_id: str | None = None,
) -> BaselineBacktestResult:
    """Load history from CSV or configured BigQuery table and score baselines."""
    contract = load_backtest_contract(contract_path)
    if use_bigquery:
        history = run_query(build_bigquery_history_query(contract), project_id=project_id)
    else:
        if input_csv is None:
            raise ValueError("input_csv is required when BigQuery input is not selected")
        history = pd.read_csv(input_csv)
    return score_baselines(history, contract)


def run_backtest(
    input_csv: str | Path | None = None,
    contract_path: str | Path | None = None,
    *,
    use_bigquery: bool = False,
    project_id: str | None = None,
) -> BaselineBacktestResult:
    """Load full model history and score the configured model plus baselines."""
    contract = load_backtest_contract(contract_path)
    if use_bigquery:
        history = run_query(build_bigquery_model_history_query(contract), project_id=project_id)
    else:
        if input_csv is None:
            raise ValueError("input_csv is required when BigQuery input is not selected")
        history = pd.read_csv(input_csv)
    return score_model_and_baselines(history, contract)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Resolve a backtest contract plan")
    parser.add_argument(
        "--contract-path",
        "-f",
        default=str(DEFAULT_BACKTEST_CONTRACT_PATH),
        help="Path to backtest contract YAML",
    )
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument(
        "--input-csv",
        help="Local historical actuals used to execute deterministic baseline scoring",
    )
    input_group.add_argument(
        "--input-bigquery",
        action="store_true",
        help="Load history from backtest.history_table in BigQuery",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned origin/horizon rows and exit",
    )
    parser.add_argument("--persist", action="store_true", help="Persist records to BigQuery")
    parser.add_argument(
        "--baselines-only",
        action="store_true",
        help="Skip configured ML model fitting and score deterministic baselines only",
    )
    parser.add_argument("--project-id", help="BigQuery billing project (defaults to environment)")
    parser.add_argument("--run-table", default="tds-favorita.favorita.backtest_runs")
    parser.add_argument("--prediction-table", default="tds-favorita.favorita.backtest_predictions")
    parser.add_argument("--metric-table", default="tds-favorita.favorita.backtest_metrics")
    args = parser.parse_args()

    plan = build_backtest_plan(args.contract_path)
    if args.dry_run:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return
    if not args.input_csv and not args.input_bigquery:
        parser.error("--input-csv or --input-bigquery is required unless --dry-run is used")
    contract = load_backtest_contract(args.contract_path)
    runner = run_baseline_backtest if args.baselines_only else run_backtest
    result = runner(
        args.input_csv,
        args.contract_path,
        use_bigquery=args.input_bigquery,
        project_id=args.project_id,
    )
    if args.persist:
        persist_backtest_result(
            result,
            contract,
            run_table=args.run_table,
            prediction_table=args.prediction_table,
            metric_table=args.metric_table,
            project_id=args.project_id,
        )
    metric_records = json.loads(result.metrics.to_json(orient="records"))
    print(
        json.dumps(
            {
                "backtest_run_id": result.backtest_run_id,
                "prediction_count": len(result.predictions),
                "metrics": metric_records,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
