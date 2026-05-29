"""BigQuery helpers for Vertex training and metadata loads."""

from __future__ import annotations

import json
import math
import numbers
import os
import re
from datetime import date, datetime
from functools import lru_cache
from typing import Any, Optional, Union

import numpy as np
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


def _json_safe(value: Any) -> Any:
    """
    Recursively coerce values for BigQuery ``insert_rows_json``.

    Streaming inserts require strict JSON; Python's ``json.dumps`` emits bare
    ``NaN`` / ``Infinity`` for floats, which BigQuery rejects.
    """
    if value is None:
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.floating, float)):
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return number
    if isinstance(value, (np.integer, int)) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat() if hasattr(value, "isoformat") else str(value)
    return value


def _coerce_value_for_bq_type(value: Any, bq_type: str) -> Any:
    if value is None:
        return None
    if bq_type == "JSON":
        if isinstance(value, (dict, list)):
            parsed: Any = value
        elif isinstance(value, str):
            parsed = json.loads(value) if value else None
        else:
            parsed = json.loads(json.dumps(value, default=str))
        safe = _json_safe(parsed) if parsed is not None else None
        # insert_rows_json maps dicts to RECORD; JSON columns need a JSON string.
        return json.dumps(safe) if safe is not None else None
    if bq_type == "TIMESTAMP":
        if isinstance(value, pd.Timestamp):
            ts = value
            if ts.tzinfo is not None:
                ts = ts.tz_convert("UTC").tz_localize(None)
            return ts.to_pydatetime().isoformat(sep=" ", timespec="seconds")
        if isinstance(value, datetime):
            return value.isoformat(sep=" ", timespec="seconds")
        return value
    if bq_type == "DATE":
        if isinstance(value, pd.Timestamp):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        return value
    if bq_type == "ARRAY":
        return list(value) if value is not None else None
    if bq_type in ("INT64", "INTEGER"):
        return int(value)
    if bq_type in ("FLOAT64", "FLOAT"):
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return number
    if bq_type == "BOOL":
        return bool(value)
    return value


def _prepare_row_for_insert(
    row: dict[str, Any],
    schema_types: dict[str, str],
) -> dict[str, Any]:
    prepared: dict[str, Any] = {}
    for column, bq_type in schema_types.items():
        if column not in row:
            continue
        prepared[column] = _coerce_value_for_bq_type(row[column], bq_type)
    return prepared


def load_to_bigquery(
    data: Union[list[dict[str, Any]], pd.DataFrame],
    table_id: str,
    project_id: Optional[str] = None,
    if_exists: str = "append",
) -> None:
    """
    Load rows into BigQuery (append or replace).

    Uses ``insert_rows_json`` so JSON-typed columns and arrays load correctly
    (``load_table_from_dataframe`` does not support JSON fields).
    """
    project_id = project_id or os.getenv("GOOGLE_PROJECT_ID")
    if not project_id:
        raise EnvironmentError("GOOGLE_PROJECT_ID must be set")

    if isinstance(data, list):
        records = data
    else:
        records = data.to_dict(orient="records")

    client = bigquery.Client(project=project_id)
    table = client.get_table(table_id)
    schema_types = {field.name: field.field_type for field in table.schema}

    if if_exists == "replace":
        client.query(f"TRUNCATE TABLE `{table_id}`").result()

    prepared = [_prepare_row_for_insert(row, schema_types) for row in records]
    if not prepared:
        return

    errors = client.insert_rows_json(table, prepared)
    if errors:
        raise RuntimeError(f"BigQuery insert into {table_id} failed: {errors}")


@lru_cache(maxsize=32)
def _table_field_types(table_id: str, project_id: str) -> dict[str, str]:
    client = bigquery.Client(project=project_id)
    table = client.get_table(table_id)
    return {field.name: field.field_type for field in table.schema}


def _bq_param(
    name: str,
    value: Any,
    *,
    bq_type: Optional[str] = None,
) -> bigquery.ScalarQueryParameter:
    if value is None:
        return bigquery.ScalarQueryParameter(name, bq_type or "STRING", None)
    if isinstance(value, bool):
        return bigquery.ScalarQueryParameter(name, "BOOL", value)
    if isinstance(value, numbers.Integral) and not isinstance(value, bool):
        return bigquery.ScalarQueryParameter(name, "INT64", int(value))
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        return bigquery.ScalarQueryParameter(name, "FLOAT64", float(value))
    if isinstance(value, pd.Timestamp):
        return bigquery.ScalarQueryParameter(name, "TIMESTAMP", value.to_pydatetime())
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
    Columns not present on the destination table are ignored.
    """
    project_id = project_id or os.getenv("GOOGLE_PROJECT_ID")
    if not project_id:
        raise EnvironmentError("GOOGLE_PROJECT_ID must be set")

    key_value = row.get(merge_key)
    if not key_value:
        raise ValueError(f"Row must include merge key {merge_key!r}")

    field_types = _table_field_types(table_id, project_id)
    row = {col: value for col, value in row.items() if col in field_types}

    columns = list(row.keys())
    param_names = [f"p_{col}" for col in columns]
    select_params = ", ".join(f"@{pname} AS {col}" for col, pname in zip(columns, param_names))

    update_assignments = [
        f"{col} = S.{col}" for col in columns if col != merge_key and row[col] is not None
    ]
    insert_cols = ", ".join(columns)
    insert_vals = ", ".join(f"S.{col}" for col in columns)

    if update_assignments:
        matched_clause = f"WHEN MATCHED THEN UPDATE SET {', '.join(update_assignments)}"
    else:
        matched_clause = ""

    query = f"""
        MERGE `{table_id}` AS T
        USING (SELECT {select_params}) AS S
        ON T.{merge_key} = S.{merge_key}
        {matched_clause}
        WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals})
    """

    params = [
        _bq_param(pname, row[col], bq_type=field_types.get(col))
        for col, pname in zip(columns, param_names)
    ]
    client = bigquery.Client(project=project_id)
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    client.query(query, job_config=job_config).result()


def vertex_safe_run_id(*parts: str) -> str:
    """Vertex AI run resource IDs: lowercase letters, digits, hyphens only."""
    raw = "-".join(part for part in parts if part)
    safe = re.sub(r"[^a-z0-9-]", "-", raw.lower())
    safe = re.sub(r"-+", "-", safe).strip("-")
    return safe[:128] if safe else "run"
