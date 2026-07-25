"""Tests for scheduled champion-to-draft orchestration."""

from unittest.mock import Mock, patch

import pandas as pd
import pytest

from orchestration.flows.scheduled_forecast_pipeline import (
    run_scheduled_forecast_pipeline_cycle,
)


@pytest.mark.unit
@patch("orchestration.flows.scheduled_forecast_pipeline.release_forecast_lock")
@patch(
    "orchestration.flows.scheduled_forecast_pipeline.acquire_forecast_lock",
    return_value=True,
)
@patch("orchestration.flows.scheduled_forecast_pipeline.persist_forecast_pipeline_result")
@patch("orchestration.flows.scheduled_forecast_pipeline.execute_forecast_pipeline")
@patch("orchestration.flows.scheduled_forecast_pipeline.get_git_sha", return_value="abc123")
@patch("orchestration.flows.scheduled_forecast_pipeline.load_calibration_history")
@patch("orchestration.flows.scheduled_forecast_pipeline.load_prediction_run")
@patch("orchestration.flows.scheduled_forecast_pipeline.resolve_champion_config_name")
@patch("orchestration.flows.scheduled_forecast_pipeline.resolve_champion_candidate_id")
def test_existing_prediction_run_is_transformed_without_rescoring(
    resolve_candidate: Mock,
    resolve_config: Mock,
    load_predictions: Mock,
    load_calibration: Mock,
    git_sha: Mock,
    execute: Mock,
    persist: Mock,
    acquire_lock: Mock,
    release_lock: Mock,
) -> None:
    resolve_candidate.return_value = "candidate-1"
    resolve_config.return_value = "favorita_store_h7_xgboost"
    load_predictions.return_value = pd.DataFrame(
        [
            {
                "prediction_id": "prediction-1",
                "predict_run_id": "source-run",
                "model_run_id": "model-run-1",
                "date": pd.Timestamp("2026-07-18"),
                "forecast_horizon": 7,
                "store_id": 1,
            }
        ]
    )
    load_calibration.return_value = pd.DataFrame()
    execute.return_value = Mock(
        forecast_run_id="run-1",
        rows=pd.DataFrame([{"forecast_output_id": "output-1"}]),
        stage_records=[{}, {}, {}, {}, {}],
        validation_checks=[{}, {}, {}],
    )

    with patch("orchestration.flows.scheduled_forecast_pipeline.run_job_config") as score:
        result = run_scheduled_forecast_pipeline_cycle(source_predict_run_id="source-run")

    score.assert_not_called()
    execute.assert_called_once()
    persist.assert_called_once()
    acquire_lock.assert_called_once()
    release_lock.assert_called_once()
    assert result["run_status"] == "draft"
    assert result["draft_row_count"] == 1
