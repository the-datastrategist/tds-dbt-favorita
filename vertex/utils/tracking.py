"""Vertex job run tracking in BigQuery (one row per job_run_id via MERGE)."""

from __future__ import annotations

import logging
import os
from datetime import datetime as dt
from typing import Any, Optional

import pandas as pd

from vertex.config.load_config import get_job_spec
from vertex.utils.bigquery_utils import merge_row_to_bigquery
from vertex.utils.run_context import (
    get_container_image,
    get_git_sha,
    get_pipeline_run_id,
    job_run_id_from_env,
)

logger = logging.getLogger(__name__)


def _job_runs_table(config: dict[str, Any]) -> str:
    outputs = config.get("outputs") or {}
    table = outputs.get("job_runs_table")
    if table:
        return str(table)
    defaults_table = (config.get("defaults") or {}).get("outputs", {}).get("job_runs_table")
    if defaults_table:
        return str(defaults_table)
    project = config.get("inputs", {}).get("project_id") or os.getenv("GOOGLE_PROJECT_ID")
    if not project:
        raise ValueError("project_id required for job_runs_table")
    return f"{project}.favorita.favorita_vertex_job_runs"


def new_job_run_id() -> str:
    import uuid

    return uuid.uuid4().hex


def vertex_job_resource_from_env() -> Optional[str]:
    return (
        os.getenv("CLOUD_ML_JOB_ID")
        or os.getenv("AIP_TRAINING_JOB_ID")
        or os.getenv("VERTEX_JOB_RESOURCE")
    )


def _base_row(config: dict[str, Any], job_run_id: str) -> dict[str, Any]:
    spec = get_job_spec(config)
    inputs = config.get("inputs") or {}
    vertex_cfg = config.get("vertex") or {}
    return {
        "job_run_id": job_run_id,
        "config_name": spec["config_name"],
        "model_family": spec.get("model_family"),
        "model_type": spec["model_type"],
        "job_step": spec["step"],
        "vertex_job_resource": vertex_job_resource_from_env(),
        "vertex_experiment": vertex_cfg.get("experiment"),
        "project_id": inputs.get("project_id") or os.getenv("GOOGLE_PROJECT_ID"),
        "region": inputs.get("region", "us-central1"),
        "git_sha": get_git_sha(),
        "image_uri": get_container_image(),
        "pipeline_run_id": get_pipeline_run_id(),
        "optimize_run_id": inputs.get("optimize_run_id") or os.getenv("VERTEX_OPTIMIZE_RUN_ID"),
    }


def _write_job_run(row: dict[str, Any], config: dict[str, Any]) -> None:
    table_id = _job_runs_table(config)
    project_id = row.get("project_id")
    try:
        merge_row_to_bigquery(row, table_id, project_id=project_id)
        logger.info("Upserted job run %s -> %s", row.get("job_run_id"), table_id)
    except Exception as exc:
        logger.warning("Could not upsert job run to BQ (%s): %s", table_id, exc)


def start_job_run(
    config: dict[str, Any],
    *,
    job_run_id: Optional[str] = None,
    vertex_job_resource: Optional[str] = None,
) -> tuple[str, dt]:
    """Upsert a RUNNING row; returns (job_run_id, started_at)."""
    job_run_id = job_run_id or job_run_id_from_env() or new_job_run_id()
    started_at = dt.utcnow()

    row = _base_row(config, job_run_id)
    row.update(
        {
            "status": "RUNNING",
            "error_message": None,
            "started_at": pd.Timestamp(started_at),
            "finished_at": None,
            "duration_sec": None,
            "row_count": None,
            "artifact_uri": None,
        }
    )
    if vertex_job_resource:
        row["vertex_job_resource"] = vertex_job_resource

    _write_job_run(row, config)
    return job_run_id, started_at


def _artifact_uri_from_result(result: Any) -> Optional[str]:
    if not isinstance(result, dict):
        return None
    for key in (
        "manifest_gcs_uri",
        "joblib_gcs_uri",
        "gcs_uri",
        "best_params_uri",
    ):
        if result.get(key):
            return str(result[key])
    metadata = result.get("metadata")
    if isinstance(metadata, dict):
        for key in ("manifest_gcs_uri", "gcs_uri", "joblib_gcs_uri"):
            if metadata.get(key):
                return str(metadata[key])
    return None


def _row_count_from_result(result: Any) -> Optional[int]:
    if not isinstance(result, dict):
        return None
    for key in ("row_count", "train_row_count"):
        if result.get(key) is not None:
            return int(result[key])
    metadata = result.get("metadata")
    if isinstance(metadata, dict) and metadata.get("train_row_count") is not None:
        return int(metadata["train_row_count"])
    return None


def _optimize_run_id_from_result(result: Any) -> Optional[str]:
    if not isinstance(result, dict):
        return None
    provenance = result.get("params_provenance")
    if isinstance(provenance, dict) and provenance.get("optimize_run_id"):
        return str(provenance["optimize_run_id"])
    return result.get("optimize_run_id")


def finish_job_run(
    config: dict[str, Any],
    job_run_id: str,
    *,
    started_at: dt,
    status: str,
    error_message: Optional[str] = None,
    result: Any = None,
    extra_fields: Optional[dict[str, Any]] = None,
) -> None:
    """Merge terminal status and runtime metadata for job_run_id."""
    finished_at = dt.utcnow()
    duration_sec = (finished_at - started_at).total_seconds()

    row = _base_row(config, job_run_id)
    row.update(
        {
            "status": status,
            "error_message": error_message,
            "started_at": pd.Timestamp(started_at),
            "finished_at": pd.Timestamp(finished_at),
            "duration_sec": float(duration_sec),
            "row_count": _row_count_from_result(result),
            "artifact_uri": _artifact_uri_from_result(result),
        }
    )
    opt_id = _optimize_run_id_from_result(result)
    if opt_id:
        row["optimize_run_id"] = opt_id
    if extra_fields:
        row.update(extra_fields)

    _write_job_run(row, config)
