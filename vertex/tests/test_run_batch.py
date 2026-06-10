"""Tests for async batch job execution."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from vertex.config.load_config import list_run_config_names
from vertex.jobs.run_batch import resolve_batch_config_names, run_configs


@pytest.mark.unit
class TestListRunConfigNames:
    def test_includes_only_explicit_include_in_run(self) -> None:
        names = list_run_config_names(step="train")
        assert names == ["favorita_store_n1d_xgboost"]

    def test_predict_step_same_configs(self) -> None:
        names = list_run_config_names(step="predict")
        assert names == ["favorita_store_n1d_xgboost"]


@pytest.mark.unit
class TestRunBatch:
    def test_resolve_single_config(self) -> None:
        assert resolve_batch_config_names("favorita_store_n1d_rf") == ["favorita_store_n1d_rf"]

    def test_resolve_default_train_configs(self) -> None:
        names = resolve_batch_config_names(None, step="train")
        assert names == ["favorita_store_n1d_xgboost"]

    @patch("vertex.jobs.run_batch.subprocess.run")
    def test_docker_batch_runs_all_configs(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        run_configs(
            ["favorita_store_n1d_xgboost", "favorita_store_n1d_rf"],
            vertex_mode="docker",
        )
        assert mock_run.call_count == 2
        for call in mock_run.call_args_list:
            assert "--step" in call.args[0]
            assert "train" in call.args[0]

    @patch("vertex.jobs.run_batch.subprocess.run")
    def test_docker_batch_raises_on_failure(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1)
        with pytest.raises(RuntimeError, match="Batch run failed"):
            run_configs(["favorita_store_n1d_xgboost"], vertex_mode="docker")

    @patch("vertex.jobs.run_batch.submit_job")
    def test_vertex_batch_submits_all(self, mock_submit: MagicMock) -> None:
        job = MagicMock()
        job.resource_name = "projects/p/locations/l/customJobs/1"
        mock_submit.return_value = job

        run_configs(["favorita_store_n1d_xgboost", "favorita_store_n1d_rf"], vertex_mode="vertex")

        assert mock_submit.call_count == 2
        job.wait.assert_not_called()

    @patch("vertex.jobs.run_batch.submit_job")
    def test_vertex_batch_sync_waits_for_all(self, mock_submit: MagicMock) -> None:
        job = MagicMock()
        job.resource_name = "projects/p/locations/l/customJobs/1"
        mock_submit.return_value = job

        run_configs(["favorita_store_n1d_xgboost"], vertex_mode="vertex", sync=True)

        job.wait.assert_called_once()
