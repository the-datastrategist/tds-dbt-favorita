"""Tests for model_config.yaml loading."""

import pytest

from vertex.config.load_config import (
    get_job_spec,
    load_model_config,
    validate_config_for_step,
)


@pytest.mark.unit
class TestLoadConfig:
    def test_load_train_config(self):
        config = load_model_config("favorita_xgboost_train")
        assert config["name"] == "favorita_xgboost_train"
        assert config["model_family"] == "favorita_store_daily"
        assert config["outputs"]["metadata_table"].endswith("favorita_model_metadata")

    def test_load_rf_and_arima_configs(self):
        rf = load_model_config("favorita_rf_train")
        assert rf["job"]["model_type"] == "random_forest"
        arima = load_model_config("favorita_arima_train")
        assert arima["job"]["model_type"] == "arima"
        sarima = load_model_config("favorita_sarima_predict")
        assert sarima["job"]["model_type"] == "sarima"
        assert sarima["inputs"]["artifact_config_name"] == "favorita_sarima_train"

    def test_job_spec(self):
        config = load_model_config("favorita_xgboost_predict")
        spec = get_job_spec(config)
        assert spec["step"] == "predict"
        assert spec["model_type"] == "xgboost"

    def test_validate_train(self):
        config = load_model_config("favorita_xgboost_train")
        validate_config_for_step(config)

    def test_validate_predict_requires_artifact(self):
        config = load_model_config("favorita_xgboost_predict")
        validate_config_for_step(config)

    def test_missing_config_raises(self):
        with pytest.raises(ValueError, match="not found"):
            load_model_config("does_not_exist")
