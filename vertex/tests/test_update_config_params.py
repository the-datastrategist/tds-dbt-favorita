"""Tests for writing optimized params back to model_config.yaml."""

from pathlib import Path

import pytest
from ruamel.yaml import YAML

from vertex.utils.update_config_params import (
    maybe_update_model_config_params,
    should_update_config_params,
    update_model_config_params,
)

_SAMPLE_CONFIG = """\
defaults:
  project_id: test-project
configs:
  - name: sample_model
    model_type: xgboost
    inputs:
      model_params:
        max_depth: 4
        learning_rate: 0.1
"""


@pytest.mark.unit
class TestUpdateConfigParams:
    def test_should_update_defaults_true(self, monkeypatch):
        monkeypatch.delenv("VERTEX_UPDATE_CONFIG", raising=False)
        assert should_update_config_params({"inputs": {}}) is True

    def test_should_update_respects_env_disable(self, monkeypatch):
        monkeypatch.setenv("VERTEX_UPDATE_CONFIG", "0")
        assert should_update_config_params({"inputs": {"update_config_params": True}}) is False

    def test_should_update_respects_yaml_disable(self, monkeypatch):
        monkeypatch.delenv("VERTEX_UPDATE_CONFIG", raising=False)
        config = {"inputs": {"update_config_params": False}}
        assert should_update_config_params(config) is False

    def test_update_model_config_params_merges_values(self, tmp_path: Path):
        config_path = tmp_path / "model_config.yaml"
        config_path.write_text(_SAMPLE_CONFIG, encoding="utf-8")

        update_model_config_params(
            config_path,
            "sample_model",
            {"max_depth": 9, "n_estimators": 200},
        )

        yaml = YAML()
        with config_path.open(encoding="utf-8") as handle:
            document = yaml.load(handle)

        params = document["configs"][0]["inputs"]["model_params"]
        assert params["max_depth"] == 9
        assert params["learning_rate"] == 0.1
        assert params["n_estimators"] == 200

    def test_maybe_update_skips_when_disabled(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("VERTEX_UPDATE_CONFIG", "no")
        config_path = tmp_path / "model_config.yaml"
        config_path.write_text(_SAMPLE_CONFIG, encoding="utf-8")

        result = maybe_update_model_config_params(
            {"name": "sample_model", "inputs": {}},
            {"max_depth": 9},
            config_path=config_path,
        )
        assert result is None
        assert "max_depth: 4" in config_path.read_text(encoding="utf-8")
