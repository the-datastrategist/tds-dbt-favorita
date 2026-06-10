"""Load training or scoring data from model config inputs."""

from __future__ import annotations

import os
from typing import Any

import pandas as pd

from vertex.utils.bigquery_utils import run_query

TRAIN_STEPS = frozenset({"train", "optimize"})
TRAIN_SQL_QUERY_KEY = "train_sql_query"
PREDICT_SQL_QUERY_KEY = "predict_sql_query"


def _config_step(config: dict[str, Any], step: str | None = None) -> str:
    if step:
        return step
    job = config.get("job") or {}
    job_step = job.get("step")
    if not job_step:
        raise ValueError(
            "job.step is required to resolve train_sql_query or predict_sql_query "
            "(pass --step train|predict|optimize or use apply_job_step)"
        )
    return str(job_step)


def _step_sql_query_key(step: str) -> str:
    if step in TRAIN_STEPS:
        return TRAIN_SQL_QUERY_KEY
    if step == "predict":
        return PREDICT_SQL_QUERY_KEY
    raise ValueError(f"Unknown step {step!r}")


def has_step_data_source(inputs: dict[str, Any], step: str) -> bool:
    """True when inputs define enough information to load data for step."""
    if inputs.get("source_table"):
        return True
    if inputs.get("sql_file"):
        return True
    return bool(inputs.get(_step_sql_query_key(step)))


def resolve_input_sql(config: dict[str, Any], *, step: str | None = None) -> str:
    """Build the BigQuery SQL for a config and job step."""
    inputs = config.get("inputs", {})

    if "sql_file" in inputs:
        with open(inputs["sql_file"], encoding="utf-8") as sql_file:
            return sql_file.read().strip()

    if "source_table" in inputs:
        from vertex.utils.bigquery_utils import validate_bq_table_id

        table = validate_bq_table_id(inputs["source_table"])
        return f"SELECT * FROM `{table}`"

    resolved_step = _config_step(config, step)
    sql_key = _step_sql_query_key(resolved_step)
    query = inputs.get(sql_key)
    if not query:
        raise ValueError(
            f"Config must define inputs.{sql_key}, inputs.sql_file, or inputs.source_table "
            f"for step {resolved_step!r}"
        )
    return str(query).strip()


def resolve_training_sql(config: dict[str, Any]) -> str:
    """Resolve inputs.train_sql_query (shared by train and optimize steps)."""
    return resolve_input_sql(config, step="train")


def load_training_data_from_config(config: dict[str, Any]) -> pd.DataFrame:
    """Load training rows for train or optimize (always inputs.train_sql_query)."""
    inputs = config.get("inputs", {})
    project_id = inputs.get("project_id") or os.getenv("GOOGLE_PROJECT_ID")
    query = resolve_training_sql(config)
    return run_query(query, project_id=project_id)


def load_data_from_config(
    config: dict[str, Any],
    *,
    step: str | None = None,
) -> pd.DataFrame:
    """Load rows using config inputs (BigQuery SQL, file, or table)."""
    inputs = config.get("inputs", {})
    project_id = inputs.get("project_id") or os.getenv("GOOGLE_PROJECT_ID")
    query = resolve_input_sql(config, step=step)
    return run_query(query, project_id=project_id)
