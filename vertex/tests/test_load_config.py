"""Tests for model_config.yaml loading."""

import pytest

from vertex.config.load_config import (
    apply_job_step,
    get_job_spec,
    list_run_config_names,
    load_model_config,
    validate_config_all_steps,
    validate_config_for_step,
)


@pytest.mark.unit
class TestLoadConfig:
    def test_load_unified_config(self):
        config = load_model_config("favorita_xgboost")
        assert config["name"] == "favorita_xgboost"
        assert config["model_family"] == "favorita_store_daily"
        assert config["model_type"] == "xgboost"
        assert config["outputs"]["metadata_table"].endswith("favorita_model_metadata")

    def test_load_rf_and_arima_configs(self):
        rf = load_model_config("favorita_rf")
        assert rf["model_type"] == "random_forest"
        arima = load_model_config("favorita_arima")
        assert arima["model_type"] == "arima"
        sarima = load_model_config("favorita_sarima")
        assert sarima["model_type"] == "sarima"

    def test_apply_job_step(self):
        config = apply_job_step(load_model_config("favorita_xgboost"), "predict")
        spec = get_job_spec(config)
        assert spec["step"] == "predict"
        assert spec["model_type"] == "xgboost"

    def test_validate_all_steps(self):
        validate_config_all_steps(load_model_config("favorita_xgboost"))

    def test_validate_predict_step(self):
        config = apply_job_step(load_model_config("favorita_xgboost"), "predict")
        validate_config_for_step(config)

    def test_missing_config_raises(self):
        with pytest.raises(ValueError, match="not found"):
            load_model_config("does_not_exist")

    def test_list_run_config_names(self):
        names = list_run_config_names(step="train")
        assert "favorita_xgboost" in names
        assert "favorita_rf" not in names
