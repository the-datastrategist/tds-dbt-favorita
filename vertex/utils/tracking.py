"""Vertex job run tracking in BigQuery."""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime as dt
from typing import Any, Optional

import pandas as pd

from vertex.config.load_config import get_job_spec
from vertex.utils.bigquery_utils import load_to_bigquery

logger = logging.getLogger(__name__)


def _job_runs_table(config: dict[str, Any]) -> str:
    outputs = config.get("outputs") or {}
    table = outputs.get("job_runs_table")
    if table:
        return table
    defaults_table = (config.get("defaults") or {}).get("outputs", {}).get(
        "job_runs_table"
    )
    if defaults_table:
        return defaults_table
    project = (
        config.get("inputs", {}).get("project_id")
        or os.getenv("GOOGLE_PROJECT_ID")
        or "the-data-strategist"
    )
    return f"{project}.favorita.favorita_vertex_job_runs"


def new_job_run_id() -> str:
    return uuid.uuid4().hex


def vertex_job_resource_from_env() -> Optional[str]:
    return (
        os.getenv("CLOUD_ML_JOB_ID")
        or os.getenv("AIP_TRAINING_JOB_ID")
        or os.getenv("VERTEX_JOB_RESOURCE")
    )


def start_job_run(
    config: dict[str, Any],
    *,
    job_run_id: Optional[str] = None,
    vertex_job_resource: Optional[str] = None,
) -> str:
    """Append a RUNNING row to the job runs table."""
    job_run_id = job_run_id or new_job_run_id()
    spec = get_job_spec(config)
    inputs = config.get("inputs") or {}
    vertex_cfg = config.get("vertex") or {}
    started_at = dt.utcnow()

    row = {
        "job_run_id": job_run_id,
        "config_name": spec["config_name"],
        "model_family": spec.get("model_family"),
        "model_type": spec["model_type"],
        "job_step": spec["step"],
        "status": "RUNNING",
        "vertex_job_resource": vertex_job_resource or vertex_job_resource_from_env(),
        "vertex_experiment": vertex_cfg.get("experiment"),
        "error_message": None,
        "started_at": pd.Timestamp(started_at),
        "finished_at": None,
        "project_id": inputs.get("project_id") or os.getenv("GOOGLE_PROJECT_ID"),
        "region": inputs.get("region", "us-central1"),
    }
    table_id = _job_runs_table(config)
    project_id = row["project_id"]
    try:
        load_to_bigquery(
            data=[row],
            table_id=table_id,
            project_id=project_id,
            if_exists="append",
        )
        logger.info("Started job run %s -> %s", job_run_id, table_id)
    except Exception as exc:
        logger.warning("Could not write job run start to BQ (%s): %s", table_id, exc)
    return job_run_id


def finish_job_run(
    config: dict[str, Any],
    job_run_id: str,
    *,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    """
    Record job completion.

    Appends a terminal row when the table is append-only; for production, prefer
    MERGE on job_run_id via dbt or a stored procedure.
    """
    spec = get_job_spec(config)
    inputs = config.get("inputs") or {}
    vertex_cfg = config.get("vertex") or {}
    finished_at = dt.utcnow()

    row = {
        "job_run_id": job_run_id,
        "config_name": spec["config_name"],
        "model_family": spec.get("model_family"),
        "model_type": spec["model_type"],
        "job_step": spec["step"],
        "status": status,
        "vertex_job_resource": vertex_job_resource_from_env(),
        "vertex_experiment": vertex_cfg.get("experiment"),
        "error_message": error_message,
        "started_at": None,
        "finished_at": pd.Timestamp(finished_at),
        "project_id": inputs.get("project_id") or os.getenv("GOOGLE_PROJECT_ID"),
        "region": inputs.get("region", "us-central1"),
    }
    table_id = _job_runs_table(config)
    project_id = row["project_id"]
    try:
        load_to_bigquery(
            data=[row],
            table_id=table_id,
            project_id=project_id,
            if_exists="append",
        )
        logger.info("Finished job run %s with status=%s", job_run_id, status)
    except Exception as exc:
        logger.warning("Could not write job run finish to BQ (%s): %s", table_id, exc)
