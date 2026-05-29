"""Standard prediction row schema for all Vertex model families."""

from __future__ import annotations

from datetime import datetime as dt
from typing import Any, Optional

import pandas as pd

from vertex.utils.data_utils import get_hash

STANDARD_PREDICTION_COLUMNS = [
    "prediction_id",
    "predict_run_id",
    "model_run_id",
    "model_id",
    "config_name",
    "model_family",
    "model_type",
    "run_at",
    "run_date",
    "target_column",
    "entity_id",
    "store_id",
    "product_id",
    "date",
    "forecast_date",
    "forecast_horizon",
    "actual",
    "prediction",
    "prediction_lower",
    "prediction_upper",
    "model_artifact_uri",
]


def _optional_series(df: pd.DataFrame, column: str, index: pd.Index) -> list[Any]:
    if column not in df.columns:
        return [None] * len(index)
    return df.loc[index, column].tolist()


def prediction_ids(predict_run_id: str, index: pd.Index) -> list[str]:
    return [
        get_hash(
            {
                "predict_run_id": predict_run_id,
                "row_position": row_position,
                "source_index": str(source_index),
            }
        )
        for row_position, source_index in enumerate(index)
    ]


def build_standard_prediction_rows(
    df: pd.DataFrame,
    predictions: pd.Series,
    *,
    predict_run_id: str,
    model_id: str,
    model_run_id: Optional[str],
    config_name: str,
    model_family: Optional[str],
    model_type: str,
    target_column: str,
    run_at: dt,
    id_columns: Optional[list[str]] = None,
    date_column: str = "date",
    forecast_horizon: Optional[int] = None,
    model_artifact_uri: Optional[str] = None,
    actual_column: Optional[str] = None,
) -> pd.DataFrame:
    """
    Build prediction rows with a consistent schema across model types.

    Entity columns default to store_nbr (mapped to store_id / entity_id for BQ).
    """
    index = predictions.index
    id_columns = id_columns or ["store_nbr"]
    entity_cols = [col for col in id_columns if col in df.columns]

    run_at_ts = pd.Timestamp(run_at)
    if run_at_ts.tzinfo is not None:
        run_at_ts = run_at_ts.tz_convert("UTC").tz_localize(None)

    rows: dict[str, Any] = {
        "prediction_id": prediction_ids(predict_run_id, index),
        "predict_run_id": predict_run_id,
        "model_run_id": model_run_id,
        "model_id": model_id,
        "config_name": config_name,
        "model_family": model_family,
        "model_type": model_type,
        "run_at": run_at_ts,
        "run_date": run_at_ts.date() if isinstance(run_at_ts, pd.Timestamp) else run_at,
        "target_column": target_column,
        "forecast_horizon": forecast_horizon,
        "prediction": predictions.tolist(),
        "model_artifact_uri": model_artifact_uri,
        "forecast_date": [None] * len(index),
        "prediction_lower": [None] * len(index),
        "prediction_upper": [None] * len(index),
    }

    for col in entity_cols:
        rows[col] = _optional_series(df, col, index)
    for col in ("entity_id", "store_id", "product_id"):
        if col not in rows:
            rows[col] = _optional_series(df, col, index)
    if "store_nbr" in df.columns:
        store_vals = rows.get("store_id")
        if store_vals is None or all(v is None for v in store_vals):
            rows["store_id"] = _optional_series(df, "store_nbr", index)
        entity_vals = rows.get("entity_id")
        if entity_vals is None or all(v is None for v in entity_vals):
            rows["entity_id"] = df.loc[index, "store_nbr"].astype(str).tolist()

    rows["date"] = _optional_series(df, date_column, index)
    actual_col = actual_column or target_column
    if actual_col in df.columns and actual_col != target_column:
        rows["actual"] = _optional_series(df, actual_col, index)
    elif actual_col in df.columns:
        rows["actual"] = _optional_series(df, actual_col, index)
    else:
        rows["actual"] = [None] * len(index)

    frame = pd.DataFrame(rows)
    return frame[STANDARD_PREDICTION_COLUMNS]


def new_predict_run_id(
    *,
    model_id: str,
    model_run_id: Optional[str],
    run_at: dt,
    artifact_uri: Optional[str] = None,
) -> str:
    payload = {
        "model_id": model_id,
        "model_run_id": model_run_id,
        "run_at": run_at.isoformat(),
        "artifact_uri": artifact_uri,
    }
    return get_hash(payload)
