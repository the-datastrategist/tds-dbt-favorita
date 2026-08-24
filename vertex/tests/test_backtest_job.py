"""Tests for backtest input mode routing."""

import copy
import json
import sys
from types import SimpleNamespace
from unittest.mock import ANY, patch

import pandas as pd
import pytest

from vertex.config.backtest_contract import BacktestContract, load_backtest_contract
from vertex.jobs.backtest import (
    build_bigquery_history_query,
    build_bigquery_model_history_query,
    main,
    run_backtest,
    run_baseline_backtest,
)
from vertex.tests.test_backtest_scoring import _history


@pytest.mark.unit
@patch("vertex.jobs.backtest.run_query")
def test_bigquery_mode_loads_configured_bounded_history(run_query):
    run_query.return_value = _history()

    result = run_baseline_backtest(use_bigquery=True, project_id="billing-project")

    query = run_query.call_args.args[0]
    assert "`tds-favorita.favorita.forecast_features_store`" in query
    assert "DATE '2015-08-01'" in query
    assert "DATE '2016-09-05'" in query
    assert run_query.call_args.kwargs == {"project_id": "billing-project"}
    assert result.predictions.empty is False


@pytest.mark.unit
def test_bigquery_query_limits_entities_before_loading_history():
    default = load_backtest_contract()
    raw = copy.deepcopy(default.raw)
    raw["backtest"]["max_entities"] = 10
    contract = BacktestContract(
        raw=raw,
        forecast_contract=default.forecast_contract,
        origins=default.origins,
    )

    query = build_bigquery_history_query(contract)

    assert "WITH bounded_history AS" in query
    assert "SELECT DISTINCT `series_key` FROM bounded_history" in query
    assert "ORDER BY `series_key` LIMIT 10" in query
    assert (
        "INNER JOIN selected_entities AS entities "
        "ON history.`series_key` = entities.`series_key`"
    ) in query
    assert "SELECT *" not in query


@pytest.mark.unit
def test_bigquery_query_selects_only_required_deduplicated_columns():
    default = load_backtest_contract()
    raw = copy.deepcopy(default.raw)
    raw["backtest"]["entity_columns"] = ["series_key"]
    raw["backtest"]["segment_columns"] = ["series_key", "store_segment"]
    contract = BacktestContract(
        raw=raw,
        forecast_contract=default.forecast_contract,
        origins=default.origins,
    )

    query = build_bigquery_history_query(contract)

    selected = query.split(" FROM ", maxsplit=1)[0]
    assert selected == (
        "SELECT `series_key`, `entity_key_json`, `store_segment`, "
        "`period_start`, `target_value`"
    )


@pytest.mark.unit
def test_model_history_query_wraps_configured_training_input_and_bounds_dates():
    contract = load_backtest_contract()

    query = build_bigquery_model_history_query(contract)

    assert "from `tds-favorita.favorita.forecast_features_store`" in query
    assert "data_split_source" not in query
    assert "model_history.`period_start` BETWEEN DATE '2015-08-01'" in query
    assert "AND DATE '2016-09-05'" in query


@pytest.mark.unit
def test_csv_mode_remains_available(tmp_path):
    csv_path = tmp_path / "history.csv"
    _history().to_csv(csv_path, index=False)

    result = run_baseline_backtest(csv_path)

    assert result.predictions.empty is False


@pytest.mark.unit
def test_input_is_required_outside_bigquery_mode():
    with pytest.raises(ValueError, match="input_csv is required"):
        run_baseline_backtest()

    with pytest.raises(ValueError, match="input_csv is required"):
        run_backtest()


@pytest.mark.unit
def test_main_dry_run_prints_plan_without_loading_history(capsys):
    plan = [{"origin": "2024-01-01", "horizon": 7}]
    with (
        patch.object(sys, "argv", ["backtest", "--dry-run"]),
        patch("vertex.jobs.backtest.build_backtest_plan", return_value=plan),
        patch("vertex.jobs.backtest.run_backtest") as runner,
    ):
        main()

    assert json.loads(capsys.readouterr().out) == plan
    runner.assert_not_called()


@pytest.mark.unit
def test_main_scores_and_persists_through_shared_contract(capsys):
    result = SimpleNamespace(
        backtest_run_id="run-1",
        predictions=pd.DataFrame([{"prediction_id": "prediction-1"}]),
        metrics=pd.DataFrame([{"metric_name": "wape", "metric_value": 0.1}]),
    )
    argv = [
        "backtest",
        "--input-csv",
        "history.csv",
        "--persist",
        "--project-id",
        "billing-project",
    ]
    with (
        patch.object(sys, "argv", argv),
        patch("vertex.jobs.backtest.build_backtest_plan", return_value=[]),
        patch("vertex.jobs.backtest.load_backtest_contract"),
        patch("vertex.jobs.backtest.run_backtest", return_value=result) as runner,
        patch("vertex.jobs.backtest.persist_backtest_result") as persist,
    ):
        main()

    runner.assert_called_once_with(
        "history.csv", ANY, use_bigquery=False, project_id="billing-project"
    )
    persist.assert_called_once()
    payload = json.loads(capsys.readouterr().out)
    assert payload["backtest_run_id"] == "run-1"
    assert payload["prediction_count"] == 1
