"""DDL coverage for scheduled forecast stage and validation contracts."""

from pathlib import Path

import pytest

DDL = Path("vertex/ddl/vertex_bq_tables.sql").read_text()


@pytest.mark.unit
def test_scheduled_pipeline_tables_and_run_pins_are_declared() -> None:
    assert "forecast_pipeline_stage_runs" in DDL
    assert "forecast_validation_checks" in DDL
    assert "forecast_pipeline_locks" in DDL
    assert "champion_candidate_id STRING" in DDL
    assert "eligibility_snapshot_id STRING" in DDL
    assert "stage_run_id STRING NOT NULL" in DDL
    assert "validation_check_id STRING NOT NULL" in DDL
