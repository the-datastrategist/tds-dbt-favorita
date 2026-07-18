"""DDL coverage for hierarchy reconciliation tables."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_reconciliation_tables_are_append_only_and_separate_from_base_outputs():
    ddl = (Path(__file__).parents[1] / "ddl" / "vertex_bq_tables.sql").read_text()
    for table in (
        "forecast_hierarchy_nodes",
        "forecast_hierarchy_edges",
        "forecast_reconciliation_runs",
        "forecast_reconciled_outputs",
    ):
        assert f"CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.{table}`" in ddl
    assert "base_prediction_p50 FLOAT64" in ddl
    assert "reconciliation_method STRING NOT NULL" in ddl
