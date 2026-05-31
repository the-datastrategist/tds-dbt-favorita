"""MLflow and Vertex AI Experiment tracking for Vertex model jobs."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

from vertex.config.load_config import get_job_spec
from vertex.utils.bigquery_utils import vertex_safe_run_id
from vertex.utils.mlflow_catalog import log_train_catalog
from vertex.utils.run_context import get_container_image, get_git_sha, get_pipeline_run_id

logger = logging.getLogger(__name__)

_METRIC_PREFIX = {"train": "train_", "test": "test_"}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _safe_str(value: Any, *, max_len: int = 500) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, default=str, sort_keys=True)
    else:
        text = str(value)
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _numeric_metrics(metrics: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, value in metrics.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            out[key] = float(value)
    return out


@dataclass(frozen=True)
class TrackingSettings:
    enabled: bool
    experiment_name: str
    mlflow_tracking_uri: str
    vertex_experiments: bool
    project_id: Optional[str]
    region: str


def resolve_tracking_settings(config: dict[str, Any]) -> TrackingSettings:
    """Resolve tracking settings from config block, defaults.mlflow, and env."""
    mlflow_cfg = dict(config.get("mlflow") or {})
    vertex_cfg = config.get("vertex") or {}
    inputs = config.get("inputs") or {}
    spec = get_job_spec(config)

    experiment_name = (
        mlflow_cfg.get("experiment_name")
        or vertex_cfg.get("experiment")
        or os.getenv("MLFLOW_EXPERIMENT_NAME")
        or f"favorita-{spec.get('model_family') or 'vertex'}"
    )

    enabled = _env_bool("EXPERIMENT_TRACKING_ENABLED", bool(mlflow_cfg.get("enabled", True)))
    tracking_uri = (
        mlflow_cfg.get("tracking_uri") or os.getenv("MLFLOW_TRACKING_URI") or "file:./mlruns"
    )
    vertex_experiments = _env_bool(
        "VERTEX_EXPERIMENT_TRACKING_ENABLED",
        bool(mlflow_cfg.get("vertex_experiments", True)),
    )

    project_id = inputs.get("project_id") or os.getenv("GOOGLE_PROJECT_ID")
    region = inputs.get("region") or os.getenv("VERTEX_AI_REGION", "us-central1")

    return TrackingSettings(
        enabled=enabled,
        experiment_name=experiment_name,
        mlflow_tracking_uri=tracking_uri,
        vertex_experiments=vertex_experiments and bool(project_id),
        project_id=project_id,
        region=region,
    )


class ExperimentRunContext:
    """
    Context manager for one Vertex job run across MLflow and Vertex AI Experiments.

    BigQuery metadata is written by individual runners (train/predict/optimize);
    this class links job_run_id to experiment runs and logs metrics/params from results.
    """

    def __init__(self, config: dict[str, Any], *, job_run_id: str) -> None:
        self.config = config
        self.job_run_id = job_run_id
        self.settings = resolve_tracking_settings(config)
        self._spec = get_job_spec(config)
        self._mlflow_run: Any = None
        self._vertex_run_cm: Any = None
        self._vertex_run: Any = None
        self.mlflow_run_id: Optional[str] = None
        self.vertex_experiment_run_name: Optional[str] = None

    def _run_name(self) -> str:
        return vertex_safe_run_id(self._spec["config_name"], self.job_run_id[:8])

    def _common_tags(self) -> dict[str, str]:
        tags = {
            "job_run_id": self.job_run_id,
            "config_name": self._spec["config_name"] or "",
            "job_step": self._spec["step"],
            "model_type": self._spec["model_type"],
        }
        if self._spec.get("model_family"):
            tags["model_family"] = self._spec["model_family"]
        git_sha = get_git_sha()
        if git_sha:
            tags["git_sha"] = git_sha
        image = get_container_image()
        if image:
            tags["image_uri"] = image
        pipeline_run_id = get_pipeline_run_id()
        if pipeline_run_id:
            tags["pipeline_run_id"] = pipeline_run_id
        return tags

    def __enter__(self) -> ExperimentRunContext:
        if not self.settings.enabled:
            return self
        self._start_vertex_run()
        self._start_mlflow_run()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if not self.settings.enabled:
            return
        status = "FAILED" if exc_type else "FINISHED"
        self._end_mlflow_run(status, exc_val)
        self._end_vertex_run(status, exc_val)

    def log_success(self, result: Any) -> None:
        if not self.settings.enabled:
            return
        try:
            self._log_from_result(result)
        except Exception as exc:
            logger.warning("Experiment tracking log_success failed: %s", exc)

    def log_failure(self, error_message: str) -> None:
        if not self.settings.enabled:
            return
        self._log_params({"error_message": error_message[:500]})

    def job_run_fields(self) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        if self.mlflow_run_id:
            fields["mlflow_run_id"] = self.mlflow_run_id
        if self.vertex_experiment_run_name:
            fields["vertex_experiment_run"] = self.vertex_experiment_run_name
        return fields

    def _start_mlflow_run(self) -> None:
        try:
            import mlflow

            mlflow.set_tracking_uri(self.settings.mlflow_tracking_uri)
            mlflow.set_experiment(self.settings.experiment_name)
            self._mlflow_run = mlflow.start_run(
                run_name=self._run_name(),
                tags=self._common_tags(),
            )
            self._mlflow_run.__enter__()
            active = mlflow.active_run()
            if active:
                self.mlflow_run_id = active.info.run_id
            self._log_params(
                {
                    "job_run_id": self.job_run_id,
                    "experiment_name": self.settings.experiment_name,
                    "tracking_uri": self.settings.mlflow_tracking_uri,
                }
            )
            logger.info(
                "MLflow run started (experiment=%s, run_id=%s)",
                self.settings.experiment_name,
                self.mlflow_run_id,
            )
        except Exception as exc:
            logger.warning("MLflow run failed to start: %s", exc)
            self._mlflow_run = None

    def _start_vertex_run(self) -> None:
        if not self.settings.vertex_experiments:
            return
        try:
            from google.cloud import aiplatform

            aiplatform.init(
                project=self.settings.project_id,
                location=self.settings.region,
                experiment=self.settings.experiment_name,
            )
            self._vertex_run_cm = aiplatform.start_run(run=self._run_name())
            self._vertex_run = self._vertex_run_cm.__enter__()
            self.vertex_experiment_run_name = self._run_name()
            for key, value in self._common_tags().items():
                aiplatform.log_params({key: value})
            logger.info(
                "Vertex AI experiment run started (experiment=%s, run=%s)",
                self.settings.experiment_name,
                self.vertex_experiment_run_name,
            )
        except Exception as exc:
            logger.warning("Vertex AI experiment run failed to start: %s", exc)
            self._vertex_run_cm = None
            self._vertex_run = None

    def _end_mlflow_run(self, status: str, exc_val: BaseException | None) -> None:
        if self._mlflow_run is None:
            return
        try:
            import mlflow

            if exc_val is not None:
                mlflow.set_tag("status", "FAILED")
                mlflow.log_param("error_message", _safe_str(exc_val))
            else:
                mlflow.set_tag("status", status)
            self._mlflow_run.__exit__(None, None, None)
        except Exception as exc:
            logger.warning("MLflow run failed to end: %s", exc)
        finally:
            self._mlflow_run = None

    def _end_vertex_run(self, status: str, exc_val: BaseException | None) -> None:
        if self._vertex_run_cm is None:
            return
        try:
            from google.cloud import aiplatform

            if exc_val is not None:
                aiplatform.log_params({"status": "FAILED", "error_message": _safe_str(exc_val)})
            else:
                aiplatform.log_params({"status": status})
            self._vertex_run_cm.__exit__(None, None, None)
        except Exception as exc:
            logger.warning("Vertex AI experiment run failed to end: %s", exc)
        finally:
            self._vertex_run_cm = None
            self._vertex_run = None

    def _log_params(self, params: dict[str, Any]) -> None:
        for key, value in params.items():
            if value is None:
                continue
            text = _safe_str(value)
            self._mlflow_log_param(key, text)
            self._vertex_log_param(key, text)

    def _log_metrics(self, metrics: dict[str, float]) -> None:
        if not metrics:
            return
        self._mlflow_log_metrics(metrics)
        self._vertex_log_metrics(metrics)

    def _mlflow_log_param(self, key: str, value: str) -> None:
        try:
            import mlflow

            if mlflow.active_run():
                mlflow.log_param(key, value)
        except Exception as exc:
            logger.debug("MLflow log_param %s failed: %s", key, exc)

    def _mlflow_log_metrics(self, metrics: dict[str, float]) -> None:
        try:
            import mlflow

            if mlflow.active_run():
                mlflow.log_metrics(metrics)
        except Exception as exc:
            logger.debug("MLflow log_metrics failed: %s", exc)

    def _vertex_log_param(self, key: str, value: str) -> None:
        if not self.settings.vertex_experiments:
            return
        try:
            from google.cloud import aiplatform

            aiplatform.log_params({key: value})
        except Exception as exc:
            logger.debug("Vertex log_param %s failed: %s", key, exc)

    def _vertex_log_metrics(self, metrics: dict[str, float]) -> None:
        if not self.settings.vertex_experiments:
            return
        try:
            from google.cloud import aiplatform

            aiplatform.log_metrics(metrics)
        except Exception as exc:
            logger.debug("Vertex log_metrics failed: %s", exc)

    def _log_from_result(self, result: Any) -> None:
        if not isinstance(result, dict):
            return

        step = self._spec["step"]
        if step == "train":
            self._log_train_result(result)
        elif step == "predict":
            self._log_predict_result(result)
        elif step == "optimize":
            self._log_optimize_result(result)
        else:
            self._log_generic_result(result)

    def _log_train_result(self, result: dict[str, Any]) -> None:
        metadata = result.get("metadata") or {}
        params: dict[str, Any] = {
            "config_name": result.get("config_name") or metadata.get("config_name"),
            "model_run_id": result.get("model_run_id") or metadata.get("model_run_id"),
            "model_id": result.get("model_id") or metadata.get("model_id"),
            "model_type": metadata.get("model_type"),
            "model_family": metadata.get("model_family"),
            "target_column": metadata.get("target_column"),
            "manifest_gcs_uri": result.get("manifest_gcs_uri") or metadata.get("manifest_gcs_uri"),
            "joblib_gcs_uri": result.get("joblib_gcs_uri") or metadata.get("joblib_gcs_uri"),
            "train_row_count": result.get("train_row_count") or metadata.get("train_row_count"),
            "test_row_count": metadata.get("test_row_count"),
        }
        model_params = metadata.get("parameters")
        if isinstance(model_params, dict):
            for key, value in model_params.items():
                params[f"model_{key}"] = value

        provenance = result.get("params_provenance")
        if isinstance(provenance, dict) and provenance.get("optimize_run_id"):
            params["optimize_run_id"] = provenance["optimize_run_id"]

        self._log_params({k: v for k, v in params.items() if v is not None})

        metrics: dict[str, float] = {}
        for set_name in ("train", "test"):
            perf = metadata.get(f"{set_name}_performance")
            if isinstance(perf, dict):
                prefix = _METRIC_PREFIX[set_name]
                for key, value in _numeric_metrics(perf).items():
                    metrics[f"{prefix}{key}"] = value
        self._log_metrics(metrics)

        manifest_uri = params.get("manifest_gcs_uri")
        if manifest_uri:
            self._mlflow_log_param("artifact_manifest_uri", _safe_str(manifest_uri))

        config_name = str(params.get("config_name") or self._spec["config_name"] or "")
        try:
            catalog_summary = log_train_catalog(
                self.config,
                result,
                config_name=config_name,
                job_run_id=self.job_run_id,
            )
            if catalog_summary:
                self._log_params(catalog_summary)
        except Exception as exc:
            logger.warning("MLflow GCS catalog logging failed: %s", exc)

    def _log_predict_result(self, result: dict[str, Any]) -> None:
        self._log_params(
            {
                "predict_run_id": result.get("predict_run_id"),
                "model_run_id": result.get("model_run_id"),
                "model_id": result.get("model_id"),
                "model_gcs_uri": result.get("model_gcs_uri"),
                "prediction_table": (self.config.get("outputs") or {}).get("prediction_table"),
            }
        )
        count = result.get("prediction_count")
        if count is not None:
            self._log_metrics({"prediction_count": float(count)})

    def _log_optimize_result(self, result: dict[str, Any]) -> None:
        self._log_params(
            {
                "optimize_run_id": result.get("optimize_run_id"),
                "config_name": result.get("config_name"),
                "trial_count": result.get("trial_count"),
                "best_trial_number": result.get("best_trial_number"),
                "best_params": result.get("best_params"),
                "best_params_uri": result.get("best_params_uri"),
            }
        )
        best_value = result.get("best_value")
        if best_value is not None:
            self._log_metrics({"best_objective_value": float(best_value)})

    def _log_generic_result(self, result: dict[str, Any]) -> None:
        for key in ("row_count", "train_row_count", "prediction_count"):
            if result.get(key) is not None:
                self._log_metrics({key: float(result[key])})
