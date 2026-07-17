"""Tests for idempotent backtest persistence routing."""

from unittest.mock import call, patch

import pytest

from vertex.config.backtest_contract import load_backtest_contract
from vertex.evaluation.backtesting import score_baselines
from vertex.evaluation.persistence import persist_backtest_result
from vertex.tests.test_backtest_scoring import _history


@pytest.mark.unit
@patch("vertex.evaluation.persistence.insert_rows_idempotent")
def test_persistence_uses_stable_run_prediction_and_metric_ids(insert_rows):
    contract = load_backtest_contract()
    result = score_baselines(_history(), contract, backtest_run_id="stable-run")

    persist_backtest_result(
        result,
        contract,
        run_table="p.d.runs",
        prediction_table="p.d.predictions",
        metric_table="p.d.metrics",
        project_id="p",
    )

    run_row = insert_rows.call_args_list[0].args[0][0]
    assert run_row["backtest_run_id"] == "stable-run"
    assert run_row["target"] == "demand_units"
    assert run_row["grain"] == "store-day"
    assert '"primary_metric":"wape"' in run_row["metric_policy_json"]
    assert insert_rows.call_args_list == [
        call([run_row], "p.d.runs", id_column="backtest_run_id", project_id="p"),
        call(
            result.predictions,
            "p.d.predictions",
            id_column="prediction_id",
            project_id="p",
        ),
        call(result.metrics, "p.d.metrics", id_column="metric_id", project_id="p"),
    ]
