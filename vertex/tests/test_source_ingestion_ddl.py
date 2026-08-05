"""Contract checks for append-only source ingestion evidence."""

from pathlib import Path

import pytest


DDL_PATH = Path(__file__).resolve().parents[1] / "ddl" / "vertex_bq_tables.sql"


@pytest.mark.unit
def test_source_ingestion_table_carries_policy_and_watermark_evidence():
    ddl = DDL_PATH.read_text(encoding="utf-8")
    marker = "CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.source_ingestion_runs`"
    table_ddl = ddl.split(marker, maxsplit=1)[1].split(";", maxsplit=1)[0]

    for column in (
        "ingestion_run_id STRING NOT NULL",
        "source_policy_hash STRING NOT NULL",
        "data_mode STRING NOT NULL",
        "source_watermark TIMESTAMP",
        "expected_interval_hours INT64 NOT NULL",
        "allowed_lateness_hours INT64 NOT NULL",
    ):
        assert column in table_ddl
    assert "PARTITION BY DATE(started_at)" in table_ddl
