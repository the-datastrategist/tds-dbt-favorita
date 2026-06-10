"""Tests for pipeline config resolution and KFP compile."""

import json

import pytest

from vertex.config.pipelines import (
    load_pipeline_definitions,
    resolve_pipeline_model_config,
    resolve_pipeline_name,
    resolve_pipeline_step_configs,
)
from vertex.pipelines.compile import DEFAULT_TRAINING_IMAGE, compile_favorita_pipeline


@pytest.mark.unit
class TestPipelineConfig:
    def test_load_pipelines(self):
        pipelines = load_pipeline_definitions()
        assert "favorita_xgboost" in pipelines
        assert pipelines["favorita_xgboost"]["config"] == "favorita_store_n1d_xgboost"

    def test_resolve_model_config(self):
        assert resolve_pipeline_model_config("favorita_xgboost") == "favorita_store_n1d_xgboost"

    def test_resolve_pipeline_name_from_model_config(self):
        assert resolve_pipeline_name("favorita_store_n1d_rf") == "favorita_random_forest"
        assert resolve_pipeline_name("favorita_store_n1d_xgboost") == "favorita_xgboost"
        assert resolve_pipeline_name("favorita_store_n1d_arima") == "favorita_arima"

    def test_resolve_model_config_by_model_name(self):
        assert resolve_pipeline_model_config("favorita_store_n1d_rf") == "favorita_store_n1d_rf"

    def test_resolve_rf_steps_by_model_config_name(self):
        steps = resolve_pipeline_step_configs("favorita_store_n1d_rf")
        assert steps["train"] == "favorita_store_n1d_rf"
        assert steps["optimize"] == "favorita_store_n1d_rf"
        assert steps["predict"] == "favorita_store_n1d_rf"

    def test_resolve_xgboost_steps_same_config(self):
        steps = resolve_pipeline_step_configs("favorita_xgboost")
        assert steps["train"] == "favorita_store_n1d_xgboost"
        assert steps["optimize"] == "favorita_store_n1d_xgboost"
        assert steps["predict"] == "favorita_store_n1d_xgboost"

    def test_arima_pipeline_skips_optimize(self):
        steps = resolve_pipeline_step_configs("favorita_arima")
        assert "optimize" not in steps
        assert steps["train"] == "favorita_store_n1d_arima"


@pytest.mark.unit
class TestPipelineCompile:
    def test_compile_writes_json(self, tmp_path):
        out = compile_favorita_pipeline(
            "favorita_store_n1d_arima",
            output_path=tmp_path / "favorita_store_n1d_arima.json",
            training_image=DEFAULT_TRAINING_IMAGE,
            run_optimize=False,
            run_predict=False,
        )
        assert out.is_file()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "pipelineSpec" in data or "components" in data or "root" in data
