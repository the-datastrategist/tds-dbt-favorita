"""BigQuery helpers for Vertex training and metadata loads."""

from __future__ import annotations

import os
from typing import Any, Optional, Union

import pandas as pd
from google.cloud import bigquery


def run_query(
    query: str,
    project_id: Optional[str] = None,
) -> pd.DataFrame:
    """Run a SQL query and return results as a DataFrame."""
    project_id = project_id or os.getenv("GOOGLE_PROJECT_ID")
    client = bigquery.Client(project=project_id)
    return client.query(query).to_dataframe()


def load_to_bigquery(
    data: Union[list[dict[str, Any]], pd.DataFrame],
    table_id: str,
    project_id: Optional[str] = None,
    if_exists: str = "append",
) -> None:
    """Load rows into BigQuery (append or replace)."""
    project_id = project_id or os.getenv("GOOGLE_PROJECT_ID")
    if not project_id:
        raise EnvironmentError("GOOGLE_PROJECT_ID must be set")

    if isinstance(data, list):
        frame = pd.DataFrame(data)
    else:
        frame = data

    write_map = {
        "append": bigquery.WriteDisposition.WRITE_APPEND,
        "replace": bigquery.WriteDisposition.WRITE_TRUNCATE,
    }
    write_disposition = write_map.get(if_exists, bigquery.WriteDisposition.WRITE_APPEND)

    client = bigquery.Client(project=project_id)
    job = client.load_table_from_dataframe(
        frame,
        table_id,
        job_config=bigquery.LoadJobConfig(write_disposition=write_disposition),
    )
    job.result()


def _bq_param(name: str, value: Any) -> bigquery.ScalarQueryParameter:
    if value is None:
        return bigquery.ScalarQueryParameter(name, "STRING", None)
    if isinstance(value, bool):
        return bigquery.ScalarQueryParameter(name, "BOOL", value)
    if isinstance(value, int):
        return bigquery.ScalarQueryParameter(name, "INT64", value)
    if isinstance(value, float):
        return bigquery.ScalarQueryParameter(name, "FLOAT64", value)
    if hasattr(value, "isoformat"):
        return bigquery.ScalarQueryParameter(name, "TIMESTAMP", value)
    return bigquery.ScalarQueryParameter(name, "STRING", str(value))


def merge_row_to_bigquery(
    row: dict[str, Any],
    table_id: str,
    *,
    merge_key: str = "job_run_id",
    project_id: Optional[str] = None,
) -> None:
    """
    Upsert one row via MERGE (single source of truth per job_run_id).

    Only non-None fields in ``row`` participate in UPDATE assignments.
    """
    project_id = project_id or os.getenv("GOOGLE_PROJECT_ID")
    if not project_id:
        raise EnvironmentError("GOOGLE_PROJECT_ID must be set")

    key_value = row.get(merge_key)
    if not key_value:
        raise ValueError(f"Row must include merge key {merge_key!r}")

    columns = list(row.keys())
    param_names = [f"p_{col}" for col in columns]
    select_params = ", ".join(f"@{pname} AS {col}" for col, pname in zip(columns, param_names))

    update_assignments = [
        f"{col} = COALESCE(S.{col}, T.{col})"
        for col in columns
        if col != merge_key
    ]
    insert_cols = ", ".join(columns)
    insert_vals = ", ".join(f"S.{col}" for col in columns)

    query = f"""
        MERGE `{table_id}` AS T
        USING (SELECT {select_params}) AS S
        ON T.{merge_key} = S.{merge_key}
        WHEN MATCHED THEN UPDATE SET {", ".join(update_assignments)}
        WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals})
    """

    params = [_bq_param(pname, row[col]) for col, pname in zip(columns, param_names)]
    client = bigquery.Client(project=project_id)
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    client.query(query, job_config=job_config).result()
