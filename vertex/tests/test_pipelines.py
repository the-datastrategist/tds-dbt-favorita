"""Tests for pipeline config resolution and KFP compile."""

import json
from pathlib import Path

import pytest

from vertex.config.pipelines import (
    load_pipeline_definitions,
    resolve_pipeline_step_configs,
)
from vertex.pipelines.compile import DEFAULT_TRAINING_IMAGE, compile_favorita_pipeline


@pytest.mark.unit
class TestPipelineConfig:
    def test_load_pipelines(self):
        pipelines = load_pipeline_definitions()
        assert "favorita_xgboost" in pipelines
        assert pipelines["favorita_xgboost"]["model_type"] == "xgboost"

    def test_resolve_xgboost_steps(self):
        steps = resolve_pipeline_step_configs("favorita_xgboost")
        assert steps["train"] == "favorita_xgboost_train"
        assert steps["optimize"] == "favorita_xgboost_optimize"
        assert steps["predict"] == "favorita_xgboost_predict"

    def test_arima_pipeline_skips_optimize(self):
        steps = resolve_pipeline_step_configs("favorita_arima")
        assert "optimize" not in steps
        assert steps["train"] == "favorita_arima_train"


@pytest.mark.unit
class TestPipelineCompile:
    def test_compile_writes_json(self, tmp_path):
        out = compile_favorita_pipeline(
            "favorita_arima",
            output_path=tmp_path / "favorita_arima.json",
            training_image=DEFAULT_TRAINING_IMAGE,
            run_optimize=False,
            run_predict=False,
        )
        assert out.is_file()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "pipelineSpec" in data or "components" in data or "root" in data
