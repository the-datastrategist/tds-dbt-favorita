"""BigQuery helpers for Vertex training and metadata loads."""

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
