"""Tests for MLflow GCS catalog (GCS canonical, MLflow as registry pointer)."""

from unittest.mock import MagicMock, patch

import pytest

from vertex.utils.mlflow_catalog import (
    build_catalog_record,
    log_train_catalog,
    resolve_catalog_settings,
    resolve_registered_model_name,
)


@pytest.mark.unit
class TestCatalogSettings:
    def test_defaults(self):
        settings = resolve_catalog_settings({"mlflow": {}})
        assert settings.catalog_artifacts is True
        assert settings.register_model is False
        assert settings.registered_model_prefix == "favorita"

    def test_register_via_env(self, monkeypatch):
        monkeypatch.setenv("MLFLOW_REGISTER_MODEL", "true")
        settings = resolve_catalog_settings({"mlflow": {"register_model": False}})
        assert settings.register_model is True


@pytest.mark.unit
class TestBuildCatalogRecord:
    def test_extracts_gcs_uris(self):
        record = build_catalog_record(
            {
                "config_name": "favorita_store_n1d_xgboost",
                "model_run_id": "run-1",
                "manifest_gcs_uri": "gs://bucket/m/manifest.json",
                "joblib_gcs_uri": "gs://bucket/m/model.joblib",
                "metadata": {"model_type": "xgboost_sklearn", "model_family": "fam"},
            },
            config_name="favorita_store_n1d_xgboost",
            job_run_id="job-abc",
        )
        assert record["storage"] == "gcs"
        assert record["manifest_gcs_uri"] == "gs://bucket/m/manifest.json"
        assert record["job_run_id"] == "job-abc"


@pytest.mark.unit
class TestResolveRegisteredModelName:
    def test_prefix_and_config_name(self):
        settings = resolve_catalog_settings({"mlflow": {"registered_model_prefix": "favorita"}})
        name = resolve_registered_model_name(
            {},
            config_name="favorita_store_n1d_xgboost",
            catalog_settings=settings,
        )
        assert name == "favorita-favorita_store_n1d_xgboost"

    def test_explicit_override(self):
        settings = resolve_catalog_settings(
            {"mlflow": {"registered_model_name": "my-custom-model"}}
        )
        name = resolve_registered_model_name(
            {},
            config_name="ignored",
            catalog_settings=settings,
        )
        assert name == "my-custom-model"


@pytest.mark.unit
class TestLogTrainCatalog:
    def test_logs_dict_without_registry_by_default(self):
        config = {"mlflow": {"catalog_artifacts": True, "register_model": False}}
        result = {
            "manifest_gcs_uri": "gs://b/m/manifest.json",
            "joblib_gcs_uri": "gs://b/m/model.joblib",
            "model_run_id": "r1",
            "metadata": {},
        }
        with (
            patch("mlflow.active_run", return_value=MagicMock()),
            patch("mlflow.log_dict") as mock_log_dict,
            patch("mlflow.pyfunc.log_model") as mock_log_model,
        ):
            summary = log_train_catalog(
                config,
                result,
                config_name="favorita_store_n1d_xgboost",
                job_run_id="job-1",
            )
        mock_log_dict.assert_called_once()
        mock_log_model.assert_not_called()
        assert summary == {}

    def test_registers_when_enabled(self):
        config = {"mlflow": {"catalog_artifacts": True, "register_model": True}}
        result = {
            "manifest_gcs_uri": "gs://b/m/manifest.json",
            "joblib_gcs_uri": "gs://b/m/model.joblib",
            "model_run_id": "r1",
            "metadata": {"model_type": "xgboost_sklearn"},
        }
        mock_version = MagicMock()
        mock_version.version = 3
        mock_info = MagicMock()
        mock_info.registered_model_version = mock_version
        with (
            patch("mlflow.active_run", return_value=MagicMock()),
            patch("mlflow.log_dict"),
            patch("mlflow.pyfunc.log_model", return_value=mock_info) as mock_log_model,
        ):
            summary = log_train_catalog(
                config,
                result,
                config_name="favorita_store_n1d_xgboost",
            )
        mock_log_model.assert_called_once()
        assert summary is not None
        assert summary["mlflow_model_uri"] == "models:/favorita-favorita_store_n1d_xgboost/3"
