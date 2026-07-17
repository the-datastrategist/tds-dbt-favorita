"""Idempotent persistence for immutable rolling-origin backtest records."""

from __future__ import annotations

from typing import Any

from vertex.config.backtest_contract import BacktestContract
from vertex.evaluation.backtesting import BaselineBacktestResult
from vertex.utils.bigquery_utils import insert_rows_idempotent


def _run_row(result: BaselineBacktestResult, contract: BacktestContract) -> dict[str, Any]:
    return {
        "backtest_run_id": result.backtest_run_id,
        "backtest_contract_name": contract.name,
        "backtest_contract_hash": contract.hash,
        "model_config_name": contract.model_config_name,
        "origin_start": min(contract.origins),
        "origin_end": max(contract.origins),
        "prediction_count": len(result.predictions),
        "metric_count": len(result.metrics),
        "status": "completed",
    }


def persist_backtest_result(
    result: BaselineBacktestResult,
    contract: BacktestContract,
    *,
    run_table: str,
    prediction_table: str,
    metric_table: str,
    project_id: str | None = None,
) -> None:
    """Persist a completed result using insert-only merges on all stable IDs."""
    insert_rows_idempotent(
        [_run_row(result, contract)],
        run_table,
        id_column="backtest_run_id",
        project_id=project_id,
    )
    insert_rows_idempotent(
        result.predictions,
        prediction_table,
        id_column="prediction_id",
        project_id=project_id,
    )
    insert_rows_idempotent(
        result.metrics,
        metric_table,
        id_column="metric_id",
        project_id=project_id,
    )
