"""Tests for job run tracking."""

from datetime import datetime as dt
from unittest.mock import patch

import pytest

from vertex.utils.tracking import finish_job_run, start_job_run


@pytest.mark.unit
class TestJobRunTracking:
    @pytest.fixture
    def sample_config(self):
        return {
            "name": "favorita_xgboost_train",
            "model_family": "favorita_store_daily",
            "job": {"step": "train", "model_type": "xgboost"},
            "inputs": {
                "project_id": "test-project",
                "region": "us-central1",
            },
            "outputs": {
                "job_runs_table": "test-project.favorita.favorita_vertex_job_runs",
            },
        }

    @patch("vertex.utils.tracking.merge_row_to_bigquery")
    def test_start_job_run_uses_env_id(self, mock_merge, sample_config, monkeypatch):
        monkeypatch.setenv("VERTEX_JOB_RUN_ID", "preset-id")
        job_run_id, started_at = start_job_run(sample_config)
        assert job_run_id == "preset-id"
        assert isinstance(started_at, dt)
        mock_merge.assert_called_once()
        row = mock_merge.call_args[0][0]
        assert row["status"] == "RUNNING"
        assert row["job_run_id"] == "preset-id"

    @patch("vertex.utils.tracking.merge_row_to_bigquery")
    def test_finish_job_run_includes_duration_and_artifact(self, mock_merge, sample_config):
        started_at = dt(2024, 1, 1, 12, 0, 0)
        finish_job_run(
            sample_config,
            "job-1",
            started_at=started_at,
            status="SUCCEEDED",
            result={
                "manifest_gcs_uri": "gs://bucket/m/manifest.json",
                "train_row_count": 1000,
                "params_provenance": {"optimize_run_id": "opt-1"},
            },
        )
        row = mock_merge.call_args[0][0]
        assert row["status"] == "SUCCEEDED"
        assert row["artifact_uri"] == "gs://bucket/m/manifest.json"
        assert row["row_count"] == 1000
        assert row["optimize_run_id"] == "opt-1"
        assert row["duration_sec"] is not None
