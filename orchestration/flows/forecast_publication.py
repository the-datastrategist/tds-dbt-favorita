"""Scheduled validation and publication of canonical forecast runs."""

from __future__ import annotations

from typing import Any

from prefect import flow

from vertex.config.forecast_contract import DEFAULT_FORECAST_CONTRACT_PATH, load_forecast_contract
from vertex.utils.forecast_publication import (
    PUBLICATION_MODES,
    build_publication_records,
    load_forecast_run,
    persist_publication_records,
    validate_publication_batch,
)

DEFAULT_TABLE_PREFIX = "tds-favorita.favorita"


def run_forecast_publication_cycle(
    *,
    forecast_run_id: str,
    contract_path: str = str(DEFAULT_FORECAST_CONTRACT_PATH),
    publication_mode: str = "draft_only",
    idempotency_key: str,
    actor: str = "prefect-forecast-publication",
    destination: str = "canonical_bigquery",
    table_prefix: str = DEFAULT_TABLE_PREFIX,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Validate one forecast run and optionally create an automatic publication."""
    if publication_mode not in PUBLICATION_MODES:
        raise ValueError(f"publication_mode must be one of {sorted(PUBLICATION_MODES)}")
    contract = load_forecast_contract(contract_path)
    rows = load_forecast_run(
        forecast_run_id,
        output_table=f"{table_prefix}.forecast_outputs",
        project_id=project_id,
    )
    validate_publication_batch(rows, contract)
    result: dict[str, Any] = {
        "forecast_run_id": forecast_run_id,
        "validated_row_count": len(rows),
        "publication_mode": publication_mode,
        "published": False,
    }
    if publication_mode != "auto_publish":
        return result

    approvals, publications = build_publication_records(
        rows,
        idempotency_key=idempotency_key,
        actor=actor,
        destination=destination,
    )
    persist_publication_records(
        approvals,
        publications,
        approval_table=f"{table_prefix}.forecast_approvals",
        publication_table=f"{table_prefix}.forecast_publications",
        status_table=f"{table_prefix}.forecast_status_history",
        forecast_rows=rows,
        actor=actor,
        project_id=project_id,
    )
    result["published"] = True
    result["publication_count"] = len(publications)
    return result


@flow(
    name="prefect-forecast-publication",
    description="Validate and publish a calibrated, reconciled canonical forecast run.",
    log_prints=True,
    retries=2,
    retry_delay_seconds=60,
)
def prefect_forecast_publication_flow(
    forecast_run_id: str,
    contract_path: str = str(DEFAULT_FORECAST_CONTRACT_PATH),
    publication_mode: str = "draft_only",
    idempotency_key: str = "",
    actor: str = "prefect-forecast-publication",
    destination: str = "canonical_bigquery",
    table_prefix: str = DEFAULT_TABLE_PREFIX,
    project_id: str | None = None,
) -> dict[str, Any]:
    return run_forecast_publication_cycle(
        forecast_run_id=forecast_run_id,
        contract_path=contract_path,
        publication_mode=publication_mode,
        idempotency_key=idempotency_key,
        actor=actor,
        destination=destination,
        table_prefix=table_prefix,
        project_id=project_id,
    )
