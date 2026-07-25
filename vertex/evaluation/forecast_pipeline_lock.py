"""BigQuery-backed leases preventing concurrent publication for one scope."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from google.cloud import bigquery

from vertex.utils.bigquery_utils import validate_bq_table_id
from vertex.utils.data_utils import get_hash


def forecast_lock_key(contract_hash: str, forecast_origin: datetime) -> str:
    return get_hash(
        {"forecast_contract_hash": contract_hash, "forecast_origin": forecast_origin.isoformat()}
    )


def acquire_forecast_lock(
    *,
    contract_hash: str,
    forecast_origin: datetime,
    owner_id: str,
    lock_table: str,
    lease_seconds: int = 3600,
    project_id: str | None = None,
) -> bool:
    """Acquire or renew a lease atomically and return whether this owner holds it."""
    if not owner_id or lease_seconds < 1:
        raise ValueError("owner_id and a positive lease_seconds are required")
    table = validate_bq_table_id(lock_table)
    key = forecast_lock_key(contract_hash, forecast_origin)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=lease_seconds)
    client = bigquery.Client(project=project_id)
    config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("lock_key", "STRING", key),
            bigquery.ScalarQueryParameter("contract_hash", "STRING", contract_hash),
            bigquery.ScalarQueryParameter("forecast_origin", "TIMESTAMP", forecast_origin),
            bigquery.ScalarQueryParameter("owner_id", "STRING", owner_id),
            bigquery.ScalarQueryParameter("now", "TIMESTAMP", now),
            bigquery.ScalarQueryParameter("expires", "TIMESTAMP", expires),
        ]
    )
    rows = client.query(
        f"""
        MERGE `{table}` AS target
        USING (
          SELECT @lock_key AS lock_key, @contract_hash AS forecast_contract_hash,
                 @forecast_origin AS forecast_origin, @owner_id AS owner_id,
                 @now AS acquired_at, @now AS heartbeat_at, @expires AS expires_at
        ) AS source
        ON target.lock_key = source.lock_key
        WHEN MATCHED AND (target.expires_at < @now OR target.owner_id = @owner_id) THEN
          UPDATE SET owner_id = source.owner_id, heartbeat_at = source.heartbeat_at,
                     expires_at = source.expires_at, released_at = NULL
        WHEN NOT MATCHED THEN
          INSERT (lock_key, forecast_contract_hash, forecast_origin, owner_id,
                  acquired_at, heartbeat_at, expires_at, released_at)
          VALUES (source.lock_key, source.forecast_contract_hash, source.forecast_origin,
                  source.owner_id, source.acquired_at, source.heartbeat_at,
                  source.expires_at, NULL);
        SELECT owner_id = @owner_id AND expires_at >= @now AS acquired
        FROM `{table}` WHERE lock_key = @lock_key;
        """,
        job_config=config,
    ).result()
    result = list(rows)
    return bool(result and result[0]["acquired"])


def release_forecast_lock(
    *,
    contract_hash: str,
    forecast_origin: datetime,
    owner_id: str,
    lock_table: str,
    project_id: str | None = None,
) -> None:
    table = validate_bq_table_id(lock_table)
    key = forecast_lock_key(contract_hash, forecast_origin)
    now = datetime.now(timezone.utc)
    client = bigquery.Client(project=project_id)
    config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("lock_key", "STRING", key),
            bigquery.ScalarQueryParameter("owner_id", "STRING", owner_id),
            bigquery.ScalarQueryParameter("now", "TIMESTAMP", now),
        ]
    )
    client.query(
        f"""
        UPDATE `{table}` SET released_at = @now, expires_at = @now, heartbeat_at = @now
        WHERE lock_key = @lock_key AND owner_id = @owner_id
        """,
        job_config=config,
    ).result()
