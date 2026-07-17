"""Tests for backtest input mode routing."""

from unittest.mock import patch

import pytest

from vertex.jobs.backtest import run_baseline_backtest
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
def test_csv_mode_remains_available(tmp_path):
    csv_path = tmp_path / "history.csv"
    _history().to_csv(csv_path, index=False)

    result = run_baseline_backtest(csv_path)

    assert result.predictions.empty is False


@pytest.mark.unit
def test_input_is_required_outside_bigquery_mode():
    with pytest.raises(ValueError, match="input_csv is required"):
        run_baseline_backtest()
