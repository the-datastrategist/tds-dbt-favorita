"""Validation and append-only persistence for forecast publication."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
from google.cloud import bigquery

from vertex.config.forecast_contract import ForecastContract
from vertex.utils.bigquery_utils import insert_rows_idempotent, validate_bq_table_id
from vertex.utils.data_utils import get_hash
from vertex.utils.forecast_lifecycle import build_status_events

PUBLICATION_MODES = frozenset({"draft_only", "require_approval", "auto_publish"})


def load_forecast_run(
    forecast_run_id: str,
    *,
    output_table: str,
    project_id: str | None = None,
) -> pd.DataFrame:
    """Load one canonical forecast run with a parameterized query."""
    if not forecast_run_id:
        raise ValueError("forecast_run_id is required")
    table = validate_bq_table_id(output_table)
    client = bigquery.Client(project=project_id)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("forecast_run_id", "STRING", forecast_run_id)
        ]
    )
    return client.query(
        f"SELECT * FROM `{table}` WHERE forecast_run_id = @forecast_run_id",
        job_config=job_config,
    ).to_dataframe()


def load_prediction_run(
    predict_run_id: str,
    *,
    prediction_table: str,
    project_id: str | None = None,
) -> pd.DataFrame:
    """Load one immutable standard-prediction batch for staged publication."""
    if not predict_run_id:
        raise ValueError("predict_run_id is required")
    table = validate_bq_table_id(prediction_table)
    client = bigquery.Client(project=project_id)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("predict_run_id", "STRING", predict_run_id)]
    )
    return client.query(
        f"SELECT * FROM `{table}` WHERE predict_run_id = @predict_run_id",
        job_config=job_config,
    ).to_dataframe()


def load_calibration_history(
    model_config_name: str,
    *,
    backtest_prediction_table: str,
    project_id: str | None = None,
) -> pd.DataFrame:
    """Load strictly out-of-sample model residual evidence from rolling backtests."""
    if not model_config_name:
        raise ValueError("model_config_name is required")
    table = validate_bq_table_id(backtest_prediction_table)
    client = bigquery.Client(project=project_id)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("model_config_name", "STRING", model_config_name)
        ]
    )
    return client.query(
        f"""
        SELECT actual, prediction, horizon, entity_key_json, forecast_origin, target_date
        FROM `{table}`
        WHERE baseline_name = @model_config_name
          AND actual IS NOT NULL
          AND prediction IS NOT NULL
        """,
        job_config=job_config,
    ).to_dataframe()


def load_hierarchy_version(
    hierarchy_name: str,
    hierarchy_version: str,
    *,
    node_table: str,
    edge_table: str,
    project_id: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load one pinned hierarchy graph with parameterized queries."""
    if not hierarchy_name or not hierarchy_version:
        raise ValueError("hierarchy_name and hierarchy_version are required")
    nodes_id = validate_bq_table_id(node_table)
    edges_id = validate_bq_table_id(edge_table)
    client = bigquery.Client(project=project_id)
    parameters = [
        bigquery.ScalarQueryParameter("hierarchy_name", "STRING", hierarchy_name),
        bigquery.ScalarQueryParameter("hierarchy_version", "STRING", hierarchy_version),
    ]
    nodes = client.query(
        f"""
        SELECT * FROM `{nodes_id}`
        WHERE hierarchy_name = @hierarchy_name AND hierarchy_version = @hierarchy_version
        """,
        job_config=bigquery.QueryJobConfig(query_parameters=parameters),
    ).to_dataframe()
    edges = client.query(
        f"""
        SELECT * FROM `{edges_id}`
        WHERE hierarchy_name = @hierarchy_name AND hierarchy_version = @hierarchy_version
        """,
        job_config=bigquery.QueryJobConfig(query_parameters=parameters),
    ).to_dataframe()
    if nodes.empty or edges.empty:
        raise ValueError(
            f"hierarchy {hierarchy_name!r} version {hierarchy_version!r} is incomplete"
        )
    return nodes, edges


def validate_publication_batch(rows: pd.DataFrame, contract: ForecastContract) -> None:
    """Fail closed unless a draft batch is complete, calibrated, and reconciled."""
    required = {
        "forecast_output_id",
        "forecast_run_id",
        "forecast_contract_hash",
        "entity_key_json",
        "target_date",
        "horizon",
        "prediction_p10",
        "prediction_p50",
        "prediction_p90",
        "forecast_strategy",
        "confidence_flag",
        "calibration_method",
        "calibration_run_id",
        "reconciliation_method",
        "feature_version",
        "code_sha",
        "data_cutoff",
    }
    missing = sorted(required.difference(rows.columns))
    if missing:
        raise ValueError(f"publication rows are missing required columns: {missing}")
    if rows.empty:
        raise ValueError("publication batch cannot be empty")
    if rows["forecast_run_id"].nunique(dropna=False) != 1:
        raise ValueError("publication batch must contain exactly one forecast_run_id")
    if set(rows["forecast_contract_hash"].dropna()) != {contract.hash}:
        raise ValueError("publication batch does not match the forecast contract")
    non_null = required - {"reconciliation_method"}
    if rows[list(non_null)].isna().any(axis=None):
        raise ValueError("publication lineage and forecast values must be non-null")
    if rows["forecast_output_id"].duplicated().any():
        raise ValueError("publication batch contains duplicate forecast_output_id values")
    if (
        (rows["prediction_p10"] > rows["prediction_p50"])
        | (rows["prediction_p50"] > rows["prediction_p90"])
    ).any():
        raise ValueError("publication quantiles must satisfy P10 <= P50 <= P90")

    expected_horizons = set(contract.horizons)
    grouping = rows.groupby("entity_key_json", dropna=False)["horizon"]
    incomplete = [key for key, values in grouping if set(values.astype(int)) != expected_horizons]
    if incomplete:
        raise ValueError(
            f"publication batch has incomplete horizons for {len(incomplete)} entities"
        )

    if contract.reconciliation_policy == "none":
        if set(rows["reconciliation_method"].fillna("none")) != {"none"}:
            raise ValueError("contract without a hierarchy must use reconciliation method 'none'")
    else:
        reconciliation_fields = [
            "hierarchy_version",
            "reconciliation_method",
            "reconciliation_run_id",
        ]
        if any(column not in rows for column in reconciliation_fields) or rows[
            reconciliation_fields
        ].isna().any(axis=None):
            raise ValueError("hierarchical publication requires reconciliation lineage")


def build_publication_records(
    rows: pd.DataFrame,
    *,
    idempotency_key: str,
    actor: str,
    destination: str,
    published_at: datetime | None = None,
    publication_version: int = 1,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build deterministic approval and publication records for an automatic release."""
    if not idempotency_key or not actor or not destination:
        raise ValueError("idempotency_key, actor, and destination are required")
    if publication_version < 1:
        raise ValueError("publication_version must be positive")
    timestamp = published_at or datetime.now(timezone.utc)
    approvals: list[dict[str, Any]] = []
    publications: list[dict[str, Any]] = []
    for row in rows.to_dict(orient="records"):
        approval_id = get_hash(
            {"idempotency_key": idempotency_key, "forecast_output_id": row["forecast_output_id"]}
        )
        publication_id = get_hash(
            {
                "idempotency_key": idempotency_key,
                "forecast_output_id": row["forecast_output_id"],
                "destination": destination,
                "publication_version": publication_version,
            }
        )
        approvals.append(
            {
                "approval_id": approval_id,
                "idempotency_key": idempotency_key,
                "forecast_output_id": row["forecast_output_id"],
                "forecast_run_id": row["forecast_run_id"],
                "override_id": None,
                "decision": "approved",
                "approved_value": float(row["prediction_p50"]),
                "reason_code": "automatic_quality_gates_passed",
                "comment": "Approved by scheduled publication flow",
                "decided_at": timestamp,
                "decided_by": actor,
            }
        )
        publications.append(
            {
                "publication_id": publication_id,
                "idempotency_key": idempotency_key,
                "forecast_output_id": row["forecast_output_id"],
                "forecast_run_id": row["forecast_run_id"],
                "approval_id": approval_id,
                "publication_version": publication_version,
                "published_value": float(row["prediction_p50"]),
                "destination": destination,
                "delivery_status": "pending",
                "delivery_reference": None,
                "published_at": timestamp,
                "published_by": actor,
            }
        )
    return approvals, publications


def persist_publication_records(
    approvals: list[dict[str, Any]],
    publications: list[dict[str, Any]],
    *,
    approval_table: str,
    publication_table: str,
    status_table: str,
    forecast_rows: pd.DataFrame,
    actor: str,
    project_id: str | None = None,
) -> None:
    """Persist approval, publication, and lifecycle events with stable IDs."""
    insert_rows_idempotent(
        approvals, approval_table, id_column="approval_id", project_id=project_id
    )
    approved = forecast_rows.assign(forecast_status="approved")
    insert_rows_idempotent(
        build_status_events(
            approved,
            changed_at=approvals[0]["decided_at"],
            changed_by=actor,
            previous_status="draft",
        ),
        status_table,
        id_column="status_event_id",
        project_id=project_id,
    )
    insert_rows_idempotent(
        publications, publication_table, id_column="publication_id", project_id=project_id
    )
    published = forecast_rows.assign(forecast_status="published")
    insert_rows_idempotent(
        build_status_events(
            published,
            changed_at=publications[0]["published_at"],
            changed_by=actor,
            previous_status="approved",
        ),
        status_table,
        id_column="status_event_id",
        project_id=project_id,
    )
