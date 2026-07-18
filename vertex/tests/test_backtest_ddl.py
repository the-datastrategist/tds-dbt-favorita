"""Contract tests for append-only BigQuery backtest tables."""

from pathlib import Path

import pytest

DDL_PATH = Path(__file__).resolve().parents[1] / "ddl" / "vertex_bq_tables.sql"


@pytest.mark.unit
def test_backtest_tables_match_normalized_record_contracts():
    ddl = DDL_PATH.read_text(encoding="utf-8")

    prediction_columns = {
        "prediction_id STRING NOT NULL",
        "backtest_run_id STRING NOT NULL",
        "backtest_contract_name STRING NOT NULL",
        "backtest_contract_hash STRING NOT NULL",
        "forecast_origin DATE NOT NULL",
        "target_date DATE NOT NULL",
        "horizon INT64 NOT NULL",
        "entity_key_json STRING NOT NULL",
        "segment_key_json STRING NOT NULL",
        "baseline_name STRING NOT NULL",
        "actual FLOAT64",
        "prediction FLOAT64",
        "data_cutoff TIMESTAMP NOT NULL",
        "source_cutoff_json JSON NOT NULL",
        "feature_availability_hash STRING",
    }
    metric_columns = {
        "metric_id STRING NOT NULL",
        "eligible_count INT64 NOT NULL",
        "prediction_count INT64 NOT NULL",
        "wape FLOAT64",
        "mae FLOAT64",
        "bias FLOAT64",
        "prediction_completeness FLOAT64",
    }
    run_columns = {
        "target STRING NOT NULL",
        "grain STRING NOT NULL",
        "metric_policy_json STRING NOT NULL",
        "model_family STRING NOT NULL",
        "model_type STRING NOT NULL",
    }

    assert "CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.backtest_predictions`" in ddl
    assert "CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.backtest_metrics`" in ddl
    assert "CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.backtest_runs`" in ddl
    ddl_lines = {line.strip() for line in ddl.replace(",", "").splitlines()}
    assert prediction_columns.issubset(ddl_lines)
    assert metric_columns.issubset(ddl_lines)
    assert run_columns.issubset(ddl_lines)
    assert ddl.count("PARTITION BY forecast_origin") == 2
    assert "PARTITION BY origin_start" in ddl
    assert (
        ddl.count("CLUSTER BY backtest_contract_name, horizon, baseline_name, backtest_run_id") == 2
    )
