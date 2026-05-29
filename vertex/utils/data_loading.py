"""Load training or scoring data from model config inputs."""

from __future__ import annotations

import os
from typing import Any

import pandas as pd

from vertex.utils.bigquery_utils import run_query


def load_data_from_config(config: dict[str, Any]) -> pd.DataFrame:
    """Load rows using config inputs (BigQuery SQL, file, or table)."""
    inputs = config.get("inputs", {})
    project_id = inputs.get("project_id") or os.getenv("GOOGLE_PROJECT_ID")

    if "sql_query" in inputs:
        return run_query(inputs["sql_query"], project_id=project_id)
    if "sql_file" in inputs:
        with open(inputs["sql_file"], encoding="utf-8") as sql_file:
            query = sql_file.read()
        return run_query(query, project_id=project_id)
    if "source_table" in inputs:
        table = inputs["source_table"]
        return run_query(f"SELECT * FROM `{table}`", project_id=project_id)
    raise ValueError(
        "Config must define inputs.sql_query, inputs.sql_file, or inputs.source_table"
    )
