"""Tests for append-only stage persistence and atomic draft visibility."""

from unittest.mock import call, patch

import pandas as pd
import pytest

from vertex.config.forecast_contract import load_forecast_contract
from vertex.evaluation.forecast_pipeline import ForecastPipelineResult, ForecastRunPins
from vertex.evaluation.forecast_pipeline_persistence import (
    persist_forecast_pipeline_exception,
    persist_forecast_pipeline_result,
)


@pytest.mark.unit
@patch("vertex.evaluation.forecast_pipeline_persistence.merge_row_to_bigquery")
@patch("vertex.evaluation.forecast_pipeline_persistence.insert_rows_idempotent")
def test_draft_run_record_is_persisted_after_all_evidence(
    insert_rows,
    merge_row,
) -> None:
    rows = pd.DataFrame(
        [
            {
                "forecast_output_id": "output-1",
                "forecast_run_id": "run-1",
                "forecast_origin": pd.Timestamp("2026-07-18"),
                "forecast_status": "draft",
                "model_id": "model-1",
                "config_name": "model-h7",
            }
        ]
    )
    result = ForecastPipelineResult(
        "run-1",
        rows,
        [
            {
                "stage_run_id": "stage-1",
                "started_at": pd.Timestamp("2026-07-18"),
            }
        ],
        [{"validation_check_id": "check-1"}],
    )
    pins = ForecastRunPins(
        champion_candidate_id="candidate-1",
        model_run_id="model-run-1",
        feature_version="features-1",
        feature_availability_hash="availability-1",
        data_cutoff=pd.Timestamp("2026-07-18"),
        source_cutoff_json={"sales": "2026-07-18"},
        eligibility_snapshot_id="eligibility-1",
        code_sha="abc123",
    )

    persist_forecast_pipeline_result(
        result,
        contract=load_forecast_contract("vertex/config/forecast_contract_publication.yaml"),
        pins=pins,
        table_prefix="project.dataset",
        actor="scheduler",
    )

    assert insert_rows.call_args_list[:3] == [
        call(
            result.stage_records,
            "project.dataset.forecast_pipeline_stage_runs",
            id_column="stage_run_id",
            project_id=None,
        ),
        call(
            result.validation_checks,
            "project.dataset.forecast_validation_checks",
            id_column="validation_check_id",
            project_id=None,
        ),
        call(
            result.rows,
            "project.dataset.forecast_outputs",
            id_column="forecast_output_id",
            project_id=None,
        ),
    ]
    assert merge_row.call_args_list[0].args[1] == "project.dataset.forecast_contracts"
    assert merge_row.call_args_list[0].kwargs["update_matched"] is False
    assert merge_row.call_args_list[-1].args[1] == "project.dataset.forecast_runs"
    assert merge_row.call_args_list[-1].args[0]["run_status"] == "draft"
    assert merge_row.call_args_list[-1].args[0]["feature_availability_hash"] == "availability-1"


@pytest.mark.unit
@patch("vertex.evaluation.forecast_pipeline_persistence.insert_rows_idempotent")
def test_failure_exception_is_retry_stable(insert_rows) -> None:
    error = ValueError("quantile gate failed")

    persist_forecast_pipeline_exception(
        forecast_run_id="run-1",
        error=error,
        table_prefix="project.dataset",
        actor="scheduler",
    )
    persist_forecast_pipeline_exception(
        forecast_run_id="run-1",
        error=error,
        table_prefix="project.dataset",
        actor="scheduler",
    )

    first = insert_rows.call_args_list[0].args[0][0]
    second = insert_rows.call_args_list[1].args[0][0]
    assert first["exception_id"] == second["exception_id"]
    assert first["severity"] == "blocking"
