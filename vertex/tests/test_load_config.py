"""Tests for model_config.yaml loading."""

import pytest

from vertex.config.load_config import (
    apply_job_step,
    explain_enabled,
    explain_top_k_features,
    get_job_spec,
    list_run_config_names,
    load_model_config,
    validate_config_all_steps,
    validate_config_for_step,
)


@pytest.mark.unit
class TestLoadConfig:
    def test_load_unified_config(self):
        config = load_model_config("favorita_store_n1d_xgboost")
        assert config["name"] == "favorita_store_n1d_xgboost"
        assert config["model_family"] == "favorita_store_daily"
        assert config["model_type"] == "xgboost"
        assert config["outputs"]["metadata_table"].endswith("favorita_model_metadata")

    def test_load_rf_and_arima_configs(self):
        rf = load_model_config("favorita_store_n1d_rf")
        assert rf["model_type"] == "random_forest"
        arima = load_model_config("favorita_store_n1d_arima")
        assert arima["model_type"] == "arima"
        sarima = load_model_config("favorita_store_n1d_sarima")
        assert sarima["model_type"] == "sarima"

    def test_apply_job_step(self):
        config = apply_job_step(load_model_config("favorita_store_n1d_xgboost"), "predict")
        spec = get_job_spec(config)
        assert spec["step"] == "predict"
        assert spec["model_type"] == "xgboost"

    def test_validate_all_steps(self):
        validate_config_all_steps(load_model_config("favorita_store_n1d_xgboost"))

    def test_validate_predict_step(self):
        config = apply_job_step(load_model_config("favorita_store_n1d_xgboost"), "predict")
        validate_config_for_step(config)

    def test_missing_config_raises(self):
        with pytest.raises(ValueError, match="not found"):
            load_model_config("does_not_exist")

    def test_list_run_config_names(self):
        names = list_run_config_names()
        assert "favorita_store_n1d_xgboost" in names
        assert "favorita_store_n1d_rf" not in names

    def test_job_step_must_be_explicit(self):
        config = load_model_config("favorita_store_n1d_xgboost")
        with pytest.raises(ValueError, match="job.step is required"):
            get_job_spec(config)

    def test_explain_enabled_and_top_k_features(self):
        xgboost_config = load_model_config("favorita_store_n1d_xgboost")
        assert explain_enabled(xgboost_config) is True
        assert explain_top_k_features(xgboost_config) == 20

        rf_config = load_model_config("favorita_store_n1d_rf")
        assert explain_enabled(rf_config) is True
        assert explain_top_k_features(rf_config) == 20

        arima_config = load_model_config("favorita_store_n1d_arima")
        assert explain_enabled(arima_config) is False
        assert explain_top_k_features(arima_config) == 20

    def test_validate_predict_step_with_explain_requires_supported_model_type(self):
        arima_config = dict(load_model_config("favorita_store_n1d_arima"))
        arima_config["explain"] = {"enabled": True}
        arima_config["outputs"] = {**arima_config["outputs"], "explain_table": "p.d.t"}
        with pytest.raises(ValueError, match="explain.enabled requires model_type"):
            validate_config_for_step(arima_config, step="predict")

    def test_validate_predict_step_with_explain_requires_explain_table(self):
        xgboost_config = dict(load_model_config("favorita_store_n1d_xgboost"))
        xgboost_config["outputs"] = {
            key: value for key, value in xgboost_config["outputs"].items() if key != "explain_table"
        }
        with pytest.raises(ValueError, match="outputs.explain_table required"):
            validate_config_for_step(xgboost_config, step="predict")
