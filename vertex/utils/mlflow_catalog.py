"""MLflow Model Registry catalog pointers to GCS artifacts (GCS remains canonical)."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

_CATALOG_ARTIFACT = "gcs_model_catalog.json"
_PYFUNC_ARTIFACT_PATH = "gcs_catalog_model"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _sanitize_registry_name(name: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_\-.]", "-", name.strip())
    safe = re.sub(r"-+", "-", safe).strip("-")
    return safe[:256] if safe else "favorita-model"


@dataclass(frozen=True)
class CatalogSettings:
    catalog_artifacts: bool
    register_model: bool
    registered_model_name: Optional[str]
    registered_model_prefix: str


def resolve_catalog_settings(config: dict[str, Any]) -> CatalogSettings:
    mlflow_cfg = dict(config.get("mlflow") or {})
    register_default = bool(mlflow_cfg.get("register_model", False))
    return CatalogSettings(
        catalog_artifacts=bool(mlflow_cfg.get("catalog_artifacts", True)),
        register_model=_env_bool("MLFLOW_REGISTER_MODEL", register_default),
        registered_model_name=mlflow_cfg.get("registered_model_name"),
        registered_model_prefix=str(mlflow_cfg.get("registered_model_prefix") or "favorita"),
    )


def resolve_registered_model_name(
    config: dict[str, Any],
    *,
    config_name: str,
    catalog_settings: CatalogSettings,
) -> str:
    if catalog_settings.registered_model_name:
        return _sanitize_registry_name(str(catalog_settings.registered_model_name))
    base = config_name or config.get("name") or "model"
    if catalog_settings.registered_model_prefix:
        return _sanitize_registry_name(f"{catalog_settings.registered_model_prefix}-{base}")
    return _sanitize_registry_name(base)


def build_catalog_record(
    result: dict[str, Any],
    *,
    config_name: str,
    job_run_id: Optional[str] = None,
) -> dict[str, str]:
    metadata = result.get("metadata") or {}
    record: dict[str, str] = {
        "storage": "gcs",
        "config_name": str(result.get("config_name") or metadata.get("config_name") or config_name),
        "model_run_id": str(result.get("model_run_id") or metadata.get("model_run_id") or ""),
        "model_id": str(result.get("model_id") or metadata.get("model_id") or ""),
        "model_type": str(metadata.get("model_type") or ""),
        "model_family": str(metadata.get("model_family") or ""),
        "manifest_gcs_uri": str(
            result.get("manifest_gcs_uri") or metadata.get("manifest_gcs_uri") or ""
        ),
        "joblib_gcs_uri": str(result.get("joblib_gcs_uri") or metadata.get("joblib_gcs_uri") or ""),
        "gcs_uri": str(result.get("gcs_uri") or metadata.get("gcs_uri") or ""),
    }
    if job_run_id:
        record["job_run_id"] = job_run_id
    return {key: value for key, value in record.items() if value}


class GcsCatalogModel:
    """
    Lightweight MLflow pyfunc that records GCS URIs only.

    Production scoring uses vertex.jobs.run predict + manifest on GCS, not mlflow.load_model.
    """

    def __init__(self, catalog: dict[str, str]) -> None:
        self.catalog = dict(catalog)

    def predict(
        self,
        context: Any,
        model_input: Any,
        params: Optional[dict[str, Any]] = None,
    ) -> Any:
        raise NotImplementedError(
            "GCS catalog model: load artifacts from manifest_gcs_uri / joblib_gcs_uri "
            "via vertex predict (make vertex-predict). "
            f"manifest={self.catalog.get('manifest_gcs_uri')!r}"
        )


def _pyfunc_catalog_model(catalog: dict[str, str]) -> Any:
    import mlflow.pyfunc

    class _Model(mlflow.pyfunc.PythonModel):
        def __init__(self, catalog: dict[str, str]) -> None:
            self.catalog = dict(catalog)

        def predict(self, context: Any, model_input: Any, params: Optional[dict[str, Any]] = None) -> Any:
            return GcsCatalogModel(self.catalog).predict(context, model_input, params)

    return _Model(catalog)


def log_train_catalog(
    config: dict[str, Any],
    result: dict[str, Any],
    *,
    config_name: str,
    job_run_id: Optional[str] = None,
) -> Optional[dict[str, str]]:
    """
    Log GCS pointer artifact and optionally register in MLflow Model Registry.

    Returns summary dict (registered_model_name, model_version, model_uri) when registered.
    """
    catalog_settings = resolve_catalog_settings(config)
    if not catalog_settings.catalog_artifacts and not catalog_settings.register_model:
        return None

    catalog = build_catalog_record(result, config_name=config_name, job_run_id=job_run_id)
    if not catalog.get("manifest_gcs_uri"):
        logger.warning("Skipping MLflow catalog: train result has no manifest_gcs_uri")
        return None

    try:
        import mlflow
    except ImportError as exc:
        logger.warning("MLflow not available for catalog: %s", exc)
        return None

    if not mlflow.active_run():
        logger.warning("Skipping MLflow catalog: no active MLflow run")
        return None

    summary: dict[str, str] = {}

    if catalog_settings.catalog_artifacts:
        mlflow.log_dict(catalog, _CATALOG_ARTIFACT)
        logger.info("Logged MLflow catalog artifact %s", _CATALOG_ARTIFACT)

    if not catalog_settings.register_model:
        return summary

    registered_name = resolve_registered_model_name(
        config,
        config_name=config_name,
        catalog_settings=catalog_settings,
    )
    pyfunc_model = _pyfunc_catalog_model(catalog)
    model_info = mlflow.pyfunc.log_model(
        artifact_path=_PYFUNC_ARTIFACT_PATH,
        python_model=pyfunc_model,
        registered_model_name=registered_name,
    )
    summary["mlflow_registered_model_name"] = registered_name
    if model_info.registered_model_version:
        version = str(model_info.registered_model_version.version)
        summary["mlflow_model_version"] = version
        summary["mlflow_model_uri"] = f"models:/{registered_name}/{version}"
        logger.info(
            "Registered MLflow catalog model %s (version %s); artifacts on GCS",
            registered_name,
            version,
        )
    return summary
