"""
Deprecated: use vertex.utils.artifacts (manifest layout + register_from_manifest).

Kept for backward compatibility; emits DeprecationWarning on import of legacy classes.
"""

from __future__ import annotations

import warnings

from vertex.utils.artifacts import register_from_manifest

__all__ = ["VertexModelSaver", "VertexModelLogger", "register_from_manifest"]


def _deprecation(name: str) -> None:
    warnings.warn(
        f"{name} is deprecated; use vertex.utils.artifacts.register_from_manifest "
        "after save_*_artifacts.",
        DeprecationWarning,
        stacklevel=3,
    )


class VertexModelLogger:
    """Deprecated — see vertex.utils.artifacts.register_from_manifest."""

    def __init__(self, config, saver):
        _deprecation("VertexModelLogger")
        self.config = config
        self.saver = saver

    def log_metrics(self, metrics):
        pass

    def register_model(self):
        inputs = self.config.get("inputs", {}) or {}
        register_from_manifest(
            manifest_uri=getattr(self.saver, "manifest_uri", self.saver.model_artifact_uri),
            display_name=self.saver.model_name,
            project_id=inputs.get("project_id") or self.config.get("project_id"),
            region=inputs.get("region", "us-central1"),
            artifact_uri=self.saver.model_artifact_uri,
        )


class VertexModelSaver:
    """Deprecated — training runners write artifacts via vertex.utils.artifacts."""

    def __init__(self, config, model):
        _deprecation("VertexModelSaver")
        from vertex.utils.data_utils import get_hash_id, get_timestamp

        self.config = config
        self.model = model
        self.config_id = get_hash_id(config)
        try:
            import pickle

            self.model_id = get_hash_id(pickle.dumps(model))
        except Exception:
            self.model_id = get_timestamp()
        self.model_save_datetime = get_timestamp()
        model_name_base = config.get("name", "model")
        self.model_name = (
            f"{model_name_base}_{self.model_save_datetime}_"
            f"{self.config_id[:8]}_{self.model_id[:8]}"
        )
        gcs_model_path = config.get("inputs", {}).get("gcs_model_path", "gs://models/")
        if not gcs_model_path.endswith("/"):
            gcs_model_path += "/"
        self.model_artifact_uri = f"{gcs_model_path}{self.model_name}.joblib"
        self.manifest_uri = getattr(config, "manifest_uri", None)

    def save_model(self):
        _deprecation("VertexModelSaver.save_model")
        if not getattr(self, "manifest_uri", None):
            raise ValueError(
                "VertexModelSaver is deprecated; set manifest_uri or use "
                "register_from_manifest after training."
            )
        VertexModelLogger(config=self.config, saver=self).register_model()
