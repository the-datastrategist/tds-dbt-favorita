"""Tests for optimize → train parameter resolution."""

import json

import pytest

from vertex.utils.optimize_params import (
    infer_optimize_config_name,
    persist_best_params,
    resolve_model_parameters,
)


@pytest.mark.unit
class TestOptimizeParams:
    def test_infer_optimize_config_name(self):
        assert infer_optimize_config_name("favorita_xgboost_train") == "favorita_xgboost_optimize"
        assert infer_optimize_config_name("unknown_config") is None

    def test_resolve_model_parameters_config_only(self):
        config = {
            "name": "custom_train",
            "inputs": {
                "use_optimized_params": False,
                "model_params": {"max_depth": 4},
            },
        }
        params, provenance = resolve_model_parameters(config, {"max_depth": 6})
        assert params["max_depth"] == 4
        assert provenance["params_source"] == "config"

    def test_resolve_merges_gcs_best_params(self, monkeypatch):
        best = {
            "optimize_run_id": "abc123",
            "best_params": {"max_depth": 9, "learning_rate": 0.05},
            "best_trial_number": 3,
        }

        def fake_load(uri):
            return best

        monkeypatch.setattr(
            "vertex.utils.optimize_params.load_best_params_from_gcs",
            fake_load,
        )

        config = {
            "name": "favorita_xgboost_train",
            "inputs": {
                "gcs_model_path": "gs://bucket/models/",
                "optimize_config_name": "favorita_xgboost_optimize",
                "model_params": {"max_depth": 6},
            },
            "outputs": {},
        }
        params, provenance = resolve_model_parameters(
            config, {"max_depth": 6, "learning_rate": 0.1}
        )
        assert params["max_depth"] == 9
        assert params["learning_rate"] == 0.05
        assert provenance["params_source"] == "optimize"
        assert provenance["optimize_run_id"] == "abc123"

    def test_persist_best_params_upload(self, monkeypatch):
        uploaded: dict = {}

        class FakeBlob:
            def upload_from_string(self, payload, content_type=None):
                uploaded["payload"] = json.loads(payload)

        class FakeBucket:
            def blob(self, path):
                uploaded["path"] = path
                return FakeBlob()

        class FakeClient:
            def bucket(self, name):
                uploaded["bucket"] = name
                return FakeBucket()

        monkeypatch.setattr(
            "vertex.utils.optimize_params.storage.Client",
            lambda: FakeClient(),
        )
        monkeypatch.setattr(
            "vertex.utils.optimize_params.upload_bytes",
            lambda bucket, path, payload, content_type: uploaded.update(
                {"bytes": json.loads(payload.decode("utf-8"))}
            ),
        )

        config = {
            "name": "favorita_xgboost_optimize",
            "model_family": "favorita_store_daily",
            "job": {"model_type": "xgboost"},
            "inputs": {"gcs_model_path": "gs://bucket/models/"},
        }
        uri = persist_best_params(
            config,
            {
                "optimize_run_id": "run1",
                "best_trial_number": 1,
                "best_value": 0.5,
                "best_params": {"max_depth": 8},
            },
        )
        assert uri.startswith("gs://bucket/")
        assert "optimize/favorita_xgboost_optimize" in uri
        assert uploaded["bytes"]["best_params"]["max_depth"] == 8
