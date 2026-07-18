"""Contract tests for append-only forecast operations tables."""

from pathlib import Path

import pytest

DDL_PATH = Path(__file__).resolve().parents[1] / "ddl" / "vertex_bq_tables.sql"

TABLE_KEYS = {
    "forecast_exceptions": "exception_id STRING NOT NULL",
    "forecast_overrides": "override_id STRING NOT NULL",
    "forecast_approvals": "approval_id STRING NOT NULL",
    "forecast_publications": "publication_id STRING NOT NULL",
    "forecast_revisions": "revision_id STRING NOT NULL",
}


@pytest.mark.unit
@pytest.mark.parametrize(("table_name", "primary_key"), TABLE_KEYS.items())
def test_forecast_operations_tables_have_stable_idempotent_keys(table_name, primary_key):
    ddl = DDL_PATH.read_text(encoding="utf-8")
    table_marker = f"CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.{table_name}`"
    table_ddl = ddl.split(table_marker, maxsplit=1)[1].split(";", maxsplit=1)[0]

    assert primary_key in table_ddl
    assert "idempotency_key STRING NOT NULL" in table_ddl
    assert "forecast_output_id STRING NOT NULL" in table_ddl
    assert "forecast_run_id STRING NOT NULL" in table_ddl
    assert "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP() NOT NULL" in table_ddl


@pytest.mark.unit
def test_override_and_revision_audit_fields_are_required():
    ddl = DDL_PATH.read_text(encoding="utf-8")

    for table_name in ("forecast_overrides", "forecast_revisions"):
        table_marker = f"CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.{table_name}`"
        table_ddl = ddl.split(table_marker, maxsplit=1)[1].split(";", maxsplit=1)[0]
        assert "reason_code STRING NOT NULL" in table_ddl
        assert "comment STRING NOT NULL" in table_ddl
