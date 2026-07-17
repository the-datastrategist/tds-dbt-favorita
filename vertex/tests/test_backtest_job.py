"""Tests for backtest input mode routing."""

import copy
from unittest.mock import patch

import pytest

from vertex.config.backtest_contract import BacktestContract, load_backtest_contract
from vertex.jobs.backtest import build_bigquery_history_query, run_baseline_backtest
from vertex.tests.test_backtest_scoring import _history


@pytest.mark.unit
@patch("vertex.jobs.backtest.run_query")
def test_bigquery_mode_loads_configured_bounded_history(run_query):
    run_query.return_value = _history()

    result = run_baseline_backtest(use_bigquery=True, project_id="billing-project")

    query = run_query.call_args.args[0]
    assert "`tds-favorita.favorita.int_sales_store_daily`" in query
    assert "DATE '2016-02-03'" in query
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
    assert "SELECT DISTINCT `store_nbr` FROM bounded_history" in query
    assert "ORDER BY `store_nbr` LIMIT 10" in query
    assert (
        "INNER JOIN selected_entities AS entities " "ON history.`store_nbr` = entities.`store_nbr`"
    ) in query
    assert "SELECT *" not in query


@pytest.mark.unit
def test_bigquery_query_selects_only_required_deduplicated_columns():
    default = load_backtest_contract()
    raw = copy.deepcopy(default.raw)
    raw["backtest"]["entity_columns"] = ["store_nbr"]
    raw["backtest"]["segment_columns"] = ["store_nbr", "store_segment"]
    contract = BacktestContract(
        raw=raw,
        forecast_contract=default.forecast_contract,
        origins=default.origins,
    )

    query = build_bigquery_history_query(contract)

    selected = query.split(" FROM ", maxsplit=1)[0]
    assert selected == "SELECT `store_nbr`, `store_segment`, `date`, `sales_store`"


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
