"""Tests for MLflow and Vertex experiment tracking."""

from unittest.mock import patch

import pytest

from vertex.utils.experiment_tracking import (
    ExperimentRunContext,
    resolve_tracking_settings,
)


@pytest.mark.unit
class TestResolveTrackingSettings:
    def test_merges_config_and_vertex_experiment(self):
        config = {
            "name": "favorita_xgboost_train",
            "job": {"step": "train", "model_type": "xgboost"},
            "model_family": "favorita_store_daily",
            "vertex": {"experiment": "custom-experiment"},
            "mlflow": {"enabled": True},
            "inputs": {"project_id": "proj", "region": "us-east1"},
        }
        settings = resolve_tracking_settings(config)
        assert settings.enabled is True
        assert settings.experiment_name == "custom-experiment"
        assert settings.project_id == "proj"
        assert settings.region == "us-east1"

    def test_disabled_via_env(self, monkeypatch):
        monkeypatch.setenv("EXPERIMENT_TRACKING_ENABLED", "false")
        config = {
            "name": "favorita_xgboost_train",
            "job": {"step": "train", "model_type": "xgboost"},
            "mlflow": {"enabled": True},
            "inputs": {},
        }
        settings = resolve_tracking_settings(config)
        assert settings.enabled is False


@pytest.mark.unit
class TestExperimentRunContext:
    @pytest.fixture
    def train_config(self):
        return {
            "name": "favorita_xgboost_train",
            "model_family": "favorita_store_daily",
            "job": {"step": "train", "model_type": "xgboost"},
            "mlflow": {
                "enabled": True,
                "experiment_name": "test-exp",
                "vertex_experiments": False,
            },
            "inputs": {"project_id": "test-project"},
        }

    def test_log_train_result_metrics(self, train_config):
        ctx = ExperimentRunContext(train_config, job_run_id="job-123")
        with (
            patch.object(ctx, "_log_params") as mock_params,
            patch.object(ctx, "_log_metrics") as mock_metrics,
        ):
            ctx.log_success(
                {
                    "config_name": "favorita_xgboost_train",
                    "model_run_id": "run-1",
                    "metadata": {
                        "model_type": "xgboost_sklearn",
                        "test_performance": {"mae": 1.5, "rmse": 2.0},
                        "train_performance": {"mae": 1.0},
                        "parameters": {"n_estimators": 100},
                    },
                }
            )
        mock_params.assert_called_once()
        mock_metrics.assert_called_once()
        logged = mock_metrics.call_args[0][0]
        assert logged["test_mae"] == 1.5
        assert logged["train_mae"] == 1.0

    def test_job_run_fields(self, train_config):
        ctx = ExperimentRunContext(train_config, job_run_id="job-123")
        ctx.mlflow_run_id = "mlflow-abc"
        ctx.vertex_experiment_run_name = "favorita_xgboost_train-deadbeef"
        fields = ctx.job_run_fields()
        assert fields["mlflow_run_id"] == "mlflow-abc"
        assert fields["vertex_experiment_run"] == "favorita_xgboost_train-deadbeef"

    def test_disabled_skips_start(self, train_config, monkeypatch):
        monkeypatch.setenv("EXPERIMENT_TRACKING_ENABLED", "false")
        ctx = ExperimentRunContext(train_config, job_run_id="job-123")
        with patch.object(ctx, "_start_mlflow_run") as mock_start:
            with ctx:
                ctx.log_success({"prediction_count": 10})
        mock_start.assert_not_called()
