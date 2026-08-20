"""BigQuery-backed retrieval for complete, immutable forecast publication versions."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import random
from argparse import Namespace
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol

import pandas as pd
from google.cloud import bigquery

from vertex.jobs.forecast_operations import run as run_forecast_operation
from vertex.utils.bigquery_utils import validate_bq_table_id
from vertex.utils.forecast_delivery import (
    build_delivery_event,
    build_publication_event,
    persist_delivery_event,
    persist_publication_event,
)
from vertex.utils.forecast_operations import (
    build_approval_records,
    build_override_record,
    build_publication_records,
    persist_operation_records,
)
from vertex.utils.forecast_webhook import (
    WebhookDeliveryError,
    WebhookTransport,
    deliver_publication_webhook,
)

FORECAST_COLUMNS = (
    "publication_id",
    "forecast_run_id",
    "forecast_contract_name",
    "forecast_contract_hash",
    "publication_version",
    "destination",
    "entity_key_json",
    "forecast_origin",
    "target_date",
    "horizon",
    "grain",
    "target",
    "target_unit",
    "published_value",
    "prediction_p10",
    "prediction_p50",
    "prediction_p90",
    "forecast_strategy",
    "confidence_flag",
    "calibration_method",
    "calibration_run_id",
    "hierarchy_version",
    "reconciliation_method",
    "reconciliation_run_id",
    "model_run_id",
    "model_id",
    "config_name",
    "model_family",
    "model_type",
    "feature_version",
    "feature_availability_hash",
    "code_sha",
    "data_cutoff",
    "published_at",
    "published_by",
)


@dataclass(frozen=True)
class ForecastExplorerOptions:
    runs: list[dict[str, Any]]
    entities: list[dict[str, Any]]
    models: list[dict[str, Any]]
    horizons: list[int]


@dataclass(frozen=True)
class ForecastExplorerResult:
    run: dict[str, Any]
    entity: dict[str, Any]
    model: dict[str, Any]
    rows: list[dict[str, Any]]
    provenance: dict[str, Any]
    next_page_token: str | None = None


@dataclass(frozen=True)
class ExperimentOptions:
    runs: list[dict[str, Any]]
    models: list[dict[str, Any]]
    model_families: list[str]
    feature_versions: list[str]
    statuses: list[str]
    horizons: list[int]


@dataclass(frozen=True)
class ExperimentResult:
    runs: list[dict[str, Any]]
    missing_run_ids: list[str]


@dataclass(frozen=True)
class PublicationScope:
    forecast_run_id: str
    forecast_contract_name: str
    forecast_contract_hash: str
    publication_version: int
    destination: str
    publication_row_count: int
    published_at: datetime
    delivery_status: str


@dataclass(frozen=True)
class ForecastFilters:
    entity_key_json: str | None = None
    target_start: date | None = None
    target_end: date | None = None
    horizons: tuple[int, ...] = ()


@dataclass(frozen=True)
class ForecastPageResult:
    scope: PublicationScope
    rows: list[dict[str, Any]]
    next_page_token: str | None


class MutationNotFoundError(ValueError):
    """The requested run or output does not exist."""


class MutationConflictError(ValueError):
    """A mutation conflicts with persisted immutable state."""


class ForecastRepository(Protocol):
    def experiment_options(self) -> ExperimentOptions:
        """Return filters for persisted rolling-origin experiment evidence."""

    def experiment_runs(
        self,
        *,
        run_ids: tuple[str, ...] = (),
        model_id: str | None = None,
        model_family: str | None = None,
        feature_version: str | None = None,
        status: str | None = None,
        horizon: int | None = None,
    ) -> ExperimentResult:
        """Return immutable rolling-origin experiment evidence."""

    def operations_snapshot(self) -> list[dict[str, Any]]:
        """Return lifecycle, exception, delivery, and FVA evidence by run."""

    def pipeline_runs(self) -> list[dict[str, Any]]:
        """Return scheduled pipeline stages and fail-closed validation gates."""

    def hierarchy_snapshot(self, hierarchy_version: str) -> dict[str, Any] | None:
        """Return one hierarchy version with reconciliation and coherence evidence."""

    def forecast_explorer_options(
        self, *, forecast_run_id: str | None = None
    ) -> ForecastExplorerOptions:
        """Return filter values drawn only from completely delivered publications."""

    def forecast_explorer_result(
        self,
        *,
        forecast_run_id: str,
        entity_key_json: str,
        model_id: str,
        horizon: int | None,
        exception_state: str | None,
        target_start: date | None = None,
        target_end: date | None = None,
        limit: int = 100,
        page_token: str | None = None,
    ) -> ForecastExplorerResult | None:
        """Return one UI-shaped immutable delivered forecast selection."""

    def resolve_current(self, *, contract_name: str, destination: str) -> PublicationScope | None:
        """Resolve the latest completely delivered version for a contract/destination."""

    def resolve_version(
        self,
        *,
        forecast_run_id: str,
        publication_version: int,
        destination: str,
    ) -> PublicationScope | None:
        """Resolve one explicit immutable publication version."""

    def fetch_page(
        self,
        scope: PublicationScope,
        *,
        filters: ForecastFilters,
        limit: int,
        page_token: str | None,
    ) -> ForecastPageResult:
        """Fetch one deterministic page from a validated publication version."""

    def create_override(
        self,
        *,
        forecast_run_id: str,
        forecast_output_id: str,
        override_value: float,
        reason_code: str,
        comment: str,
        actor: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Append one idempotent planner override."""

    def approve_run(
        self,
        *,
        forecast_run_id: str,
        reason_code: str,
        comment: str,
        actor: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Append one complete idempotent approval decision set."""

    def publish_run(
        self,
        *,
        forecast_run_id: str,
        approval_idempotency_key: str,
        destination: str,
        publication_version: int,
        actor: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Publish one complete explicit approval set idempotently."""

    def supersede_run(
        self,
        *,
        forecast_run_id: str,
        prior_version: int,
        publication_version: int,
        destination: str,
        reason_code: str,
        comment: str,
        actor: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Supersede a complete version with a newly approved immutable version."""

    def rollback_run(
        self,
        *,
        forecast_run_id: str,
        prior_version: int,
        publication_version: int,
        destination: str,
        reason_code: str,
        comment: str,
        actor: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Republish a complete prior version as a new immutable version."""


def canonical_entity_key(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("entity_key must be valid JSON") from exc
    if not isinstance(parsed, dict) or not parsed:
        raise ValueError("entity_key must be a non-empty JSON object")
    return json.dumps(parsed, sort_keys=True, separators=(",", ":"))


def encode_page_token(row: dict[str, Any]) -> str:
    payload = {
        "entity_key_json": row["entity_key_json"],
        "target_date": str(row["target_date"]),
        "horizon": int(row["horizon"]),
        "publication_id": row["publication_id"],
    }
    return base64.urlsafe_b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")


def decode_page_token(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        raw = json.loads(base64.urlsafe_b64decode(value.encode("ascii")).decode("utf-8"))
        required = {"entity_key_json", "target_date", "horizon", "publication_id"}
        if not isinstance(raw, dict) or set(raw) != required:
            raise ValueError
        payload: dict[str, Any] = {
            "entity_key_json": str(raw["entity_key_json"]),
            "target_date": date.fromisoformat(str(raw["target_date"])),
            "horizon": int(raw["horizon"]),
            "publication_id": str(raw["publication_id"]),
        }
    except (
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
        binascii.Error,
        UnicodeDecodeError,
    ) as exc:
        raise ValueError("invalid page_token") from exc
    return payload


class BigQueryForecastRepository:
    def __init__(
        self,
        *,
        project_id: str,
        table_prefix: str,
        webhook_url: str | None = None,
        webhook_signing_secret: str | None = None,
        webhook_name: str = "default",
        webhook_transport: WebhookTransport | None = None,
    ) -> None:
        if bool(webhook_url) != bool(webhook_signing_secret):
            raise ValueError("webhook URL and signing secret must be configured together")
        if webhook_url and not webhook_name:
            raise ValueError("webhook name is required when webhook delivery is configured")
        self.client = bigquery.Client(project=project_id)
        self.project_id = project_id
        self.table_prefix = table_prefix
        self.delivery_table = validate_bq_table_id(f"{table_prefix}.forecast_delivery_current")
        self.publication_table = validate_bq_table_id(f"{table_prefix}.published_forecasts_by_run")
        self.outputs_table = validate_bq_table_id(f"{table_prefix}.forecast_outputs")
        self.overrides_table = validate_bq_table_id(f"{table_prefix}.forecast_overrides")
        self.approvals_table = validate_bq_table_id(f"{table_prefix}.forecast_approvals")
        self.publications_table = validate_bq_table_id(f"{table_prefix}.forecast_publications")
        self.delivery_events_table = validate_bq_table_id(
            f"{table_prefix}.forecast_delivery_events"
        )
        self.demand_table = validate_bq_table_id(f"{table_prefix}.int_demand_store_daily")
        self.backtest_runs_table = validate_bq_table_id(f"{table_prefix}.backtest_runs")
        self.backtest_metrics_table = validate_bq_table_id(f"{table_prefix}.backtest_metrics")
        self.backtest_predictions_table = validate_bq_table_id(
            f"{table_prefix}.backtest_predictions"
        )
        self.forecast_runs_table = validate_bq_table_id(f"{table_prefix}.forecast_runs")
        self.operations_fva_table = validate_bq_table_id(
            f"{table_prefix}.forecast_value_added_operations"
        )
        self.pipeline_health_table = validate_bq_table_id(
            f"{table_prefix}.forecast_pipeline_health"
        )
        self.pipeline_stages_table = validate_bq_table_id(
            f"{table_prefix}.forecast_pipeline_stage_runs"
        )
        self.validation_checks_table = validate_bq_table_id(
            f"{table_prefix}.forecast_validation_checks"
        )
        self.hierarchy_nodes_table = validate_bq_table_id(
            f"{table_prefix}.forecast_hierarchy_nodes"
        )
        self.hierarchy_edges_table = validate_bq_table_id(
            f"{table_prefix}.forecast_hierarchy_edges"
        )
        self.reconciliation_runs_table = validate_bq_table_id(
            f"{table_prefix}.forecast_reconciliation_runs"
        )
        self.reconciled_outputs_table = validate_bq_table_id(
            f"{table_prefix}.forecast_reconciled_outputs"
        )
        self.webhook_url = webhook_url
        self.webhook_signing_secret = webhook_signing_secret
        self.webhook_name = webhook_name
        self.webhook_transport = webhook_transport

    @staticmethod
    def _scope(row: Any) -> PublicationScope:
        return PublicationScope(
            forecast_run_id=row["forecast_run_id"],
            forecast_contract_name=row["forecast_contract_name"],
            forecast_contract_hash=row["forecast_contract_hash"],
            publication_version=int(row["publication_version"]),
            destination=row["destination"],
            publication_row_count=int(row["publication_row_count"]),
            published_at=row["published_at"],
            delivery_status=row["delivery_status"],
        )

    def _resolve(self, query: str, parameters: list[Any]) -> PublicationScope | None:
        config = bigquery.QueryJobConfig(query_parameters=parameters)
        rows = list(self.client.query(query, job_config=config).result())
        return self._scope(rows[0]) if rows else None

    def _dataframe(self, query: str, parameters: list[Any]) -> pd.DataFrame:
        config = bigquery.QueryJobConfig(query_parameters=parameters)
        return self.client.query(query, job_config=config).to_dataframe()

    def _run_rows(self, forecast_run_id: str) -> pd.DataFrame:
        rows = self._dataframe(
            f"SELECT * FROM `{self.outputs_table}` WHERE forecast_run_id = @forecast_run_id",
            [bigquery.ScalarQueryParameter("forecast_run_id", "STRING", forecast_run_id)],
        )
        if rows.empty:
            raise MutationNotFoundError("forecast run has no canonical output rows")
        return rows

    def _deliver_webhook(self, event: dict[str, Any], *, actor: str) -> dict[str, Any]:
        if not self.webhook_url or not self.webhook_signing_secret:
            return {"webhook_delivery_status": "disabled"}
        destination = f"webhook:{self.webhook_name}"
        parameters = [
            bigquery.ScalarQueryParameter("forecast_run_id", "STRING", event["forecast_run_id"]),
            bigquery.ScalarQueryParameter(
                "publication_version", "INT64", event["publication_version"]
            ),
            bigquery.ScalarQueryParameter("destination", "STRING", destination),
        ]
        latest = self._dataframe(
            f"""
            SELECT delivery_event_id, delivery_status, delivery_attempt
            FROM `{self.delivery_events_table}`
            WHERE forecast_run_id = @forecast_run_id
              AND publication_version = @publication_version
              AND destination = @destination
            ORDER BY occurred_at DESC, delivery_event_id DESC
            LIMIT 1
            """,
            parameters,
        )
        if not latest.empty and str(latest.iloc[0]["delivery_status"]) in {
            "delivered",
            "abandoned",
        }:
            return {
                "webhook_delivery_status": str(latest.iloc[0]["delivery_status"]),
                "webhook_delivery_event_id": str(latest.iloc[0]["delivery_event_id"]),
            }
        prior_status = None if latest.empty else str(latest.iloc[0]["delivery_status"])
        attempt = 1 if latest.empty else int(latest.iloc[0]["delivery_attempt"])
        if prior_status == "failed":
            attempt += 1
            pending = build_delivery_event(
                forecast_run_id=event["forecast_run_id"],
                publication_version=event["publication_version"],
                destination=destination,
                delivery_status="pending",
                delivery_attempt=attempt,
                actor=actor,
                idempotency_key=(
                    f"{event['publication_event_id']}:{destination}:{attempt}:pending"
                ),
                prior_status="failed",
                details={"publication_event_id": event["publication_event_id"]},
            )
            persist_delivery_event(
                pending, table_prefix=self.table_prefix, project_id=self.project_id
            )
        elif prior_status is None:
            pending = build_delivery_event(
                forecast_run_id=event["forecast_run_id"],
                publication_version=event["publication_version"],
                destination=destination,
                delivery_status="pending",
                delivery_attempt=attempt,
                actor=actor,
                idempotency_key=(
                    f"{event['publication_event_id']}:{destination}:{attempt}:pending"
                ),
                prior_status=None,
                details={"publication_event_id": event["publication_event_id"]},
            )
            persist_delivery_event(
                pending, table_prefix=self.table_prefix, project_id=self.project_id
            )
        try:
            response = deliver_publication_webhook(
                event,
                url=self.webhook_url,
                signing_secret=self.webhook_signing_secret,
                transport=self.webhook_transport,
            )
            terminal = build_delivery_event(
                forecast_run_id=event["forecast_run_id"],
                publication_version=event["publication_version"],
                destination=destination,
                delivery_status="delivered",
                delivery_attempt=attempt,
                actor=actor,
                idempotency_key=(
                    f"{event['publication_event_id']}:{destination}:{attempt}:delivered"
                ),
                prior_status="pending",
                delivery_reference=f"{self.webhook_name}:http:{response.status_code}",
                details={"publication_event_id": event["publication_event_id"]},
            )
        except (WebhookDeliveryError, ValueError) as exc:
            error_code = (
                exc.error_code if isinstance(exc, WebhookDeliveryError) else "configuration_error"
            )
            terminal = build_delivery_event(
                forecast_run_id=event["forecast_run_id"],
                publication_version=event["publication_version"],
                destination=destination,
                delivery_status="failed",
                delivery_attempt=attempt,
                actor=actor,
                idempotency_key=(f"{event['publication_event_id']}:{destination}:{attempt}:failed"),
                prior_status="pending",
                error_code=error_code,
                error_message=str(exc),
                details={"publication_event_id": event["publication_event_id"]},
            )
        persist_delivery_event(terminal, table_prefix=self.table_prefix, project_id=self.project_id)
        return {
            "webhook_delivery_status": terminal["delivery_status"],
            "webhook_delivery_event_id": terminal["delivery_event_id"],
        }

    def create_override(
        self,
        *,
        forecast_run_id: str,
        forecast_output_id: str,
        override_value: float,
        reason_code: str,
        comment: str,
        actor: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        rows = self._run_rows(forecast_run_id)
        selected = rows.loc[rows["forecast_output_id"] == forecast_output_id]
        if len(selected) != 1:
            raise MutationNotFoundError(
                "forecast_output_id must identify exactly one row in the run"
            )
        record = build_override_record(
            selected.iloc[0].to_dict(),
            override_value=override_value,
            reason_code=reason_code,
            comment=comment,
            actor=actor,
            idempotency_key=idempotency_key,
        )
        existing = self._dataframe(
            f"""
            SELECT * FROM `{self.overrides_table}`
            WHERE forecast_output_id = @forecast_output_id
              AND idempotency_key = @idempotency_key
            """,
            [
                bigquery.ScalarQueryParameter("forecast_output_id", "STRING", forecast_output_id),
                bigquery.ScalarQueryParameter("idempotency_key", "STRING", idempotency_key),
            ],
        )
        if not existing.empty:
            persisted = existing.iloc[0]
            matches = (
                len(existing) == 1
                and float(persisted["override_value"]) == float(record["override_value"])
                and persisted["reason_code"] == reason_code
                and persisted["comment"] == comment
                and persisted["overridden_by"] == actor
            )
            if not matches:
                raise MutationConflictError("idempotency key conflicts with a persisted override")
            return {"action": "override", "override_id": persisted["override_id"], "retry": True}
        persist_operation_records(
            table_prefix=self.table_prefix,
            project_id=self.project_id,
            overrides=[record],
        )
        return {"action": "override", "override_id": record["override_id"], "retry": False}

    def approve_run(
        self,
        *,
        forecast_run_id: str,
        reason_code: str,
        comment: str,
        actor: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        rows = self._run_rows(forecast_run_id)
        parameters = [bigquery.ScalarQueryParameter("forecast_run_id", "STRING", forecast_run_id)]
        overrides = self._dataframe(
            f"""
            SELECT * EXCEPT(row_number) FROM (
              SELECT *, ROW_NUMBER() OVER (
                PARTITION BY forecast_output_id ORDER BY overridden_at DESC, override_id DESC
              ) AS row_number
              FROM `{self.overrides_table}` WHERE forecast_run_id = @forecast_run_id
            ) WHERE row_number = 1
            """,
            parameters,
        )
        existing = self._dataframe(
            f"""
            SELECT * FROM `{self.approvals_table}`
            WHERE forecast_run_id = @forecast_run_id AND idempotency_key = @idempotency_key
            """,
            parameters
            + [bigquery.ScalarQueryParameter("idempotency_key", "STRING", idempotency_key)],
        )
        if not existing.empty:
            matches = (
                len(existing) == len(rows)
                and set(existing["forecast_output_id"]) == set(rows["forecast_output_id"])
                and set(existing["reason_code"]) == {reason_code}
                and set(existing["comment"]) == {comment}
                and set(existing["decided_by"]) == {actor}
            )
            if not matches:
                raise MutationConflictError(
                    "idempotency key conflicts with a persisted approval set"
                )
            return {"action": "approve", "approval_count": len(existing), "retry": True}
        approvals = build_approval_records(
            rows,
            overrides=overrides,
            actor=actor,
            idempotency_key=idempotency_key,
            reason_code=reason_code,
            comment=comment,
        )
        persist_operation_records(
            table_prefix=self.table_prefix,
            project_id=self.project_id,
            approvals=approvals,
        )
        return {
            "action": "approve",
            "approval_count": len(approvals),
            "override_count": len(overrides),
            "retry": False,
        }

    def publish_run(
        self,
        *,
        forecast_run_id: str,
        approval_idempotency_key: str,
        destination: str,
        publication_version: int,
        actor: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        rows = self._run_rows(forecast_run_id)
        common = [bigquery.ScalarQueryParameter("forecast_run_id", "STRING", forecast_run_id)]
        approvals = self._dataframe(
            f"""
            SELECT * FROM `{self.approvals_table}`
            WHERE forecast_run_id = @forecast_run_id
              AND idempotency_key = @approval_idempotency_key
            """,
            common
            + [
                bigquery.ScalarQueryParameter(
                    "approval_idempotency_key", "STRING", approval_idempotency_key
                )
            ],
        )
        if approvals.empty:
            raise MutationNotFoundError("approval decision set not found")
        try:
            publications = build_publication_records(
                rows,
                approvals=approvals,
                actor=actor,
                destination=destination,
                idempotency_key=idempotency_key,
                publication_version=publication_version,
            )
        except ValueError as exc:
            raise MutationConflictError(str(exc)) from exc
        contract_names = set(rows["forecast_contract_name"])
        contract_hashes = set(rows["forecast_contract_hash"])
        if len(contract_names) != 1 or len(contract_hashes) != 1:
            raise MutationConflictError("publication requires one forecast contract and hash")
        event = build_publication_event(
            event_type="forecast.published",
            forecast_run_id=forecast_run_id,
            forecast_contract_name=str(next(iter(contract_names))),
            forecast_contract_hash=str(next(iter(contract_hashes))),
            publication_version=publication_version,
            destination=destination,
            row_count=len(publications),
            actor=actor,
            idempotency_key=idempotency_key,
            occurred_at=publications[0]["published_at"],
        )
        existing = self._dataframe(
            f"""
            SELECT * FROM `{self.publications_table}`
            WHERE forecast_run_id = @forecast_run_id AND destination = @destination
            """,
            common + [bigquery.ScalarQueryParameter("destination", "STRING", destination)],
        )
        same_version = existing.loc[existing["publication_version"] == publication_version]
        if not same_version.empty:
            expected_by_id = {row["publication_id"]: row for row in publications}
            matches = (
                len(same_version) == len(rows)
                and set(same_version["idempotency_key"]) == {idempotency_key}
                and set(same_version["published_by"]) == {actor}
                and set(same_version["publication_id"]) == set(expected_by_id)
                and all(
                    row["approval_id"] == expected_by_id[str(row["publication_id"])]["approval_id"]
                    for row in same_version.to_dict(orient="records")
                )
            )
            if not matches:
                raise MutationConflictError(
                    "publication version conflicts with persisted immutable state"
                )
            event = build_publication_event(
                event_type="forecast.published",
                forecast_run_id=forecast_run_id,
                forecast_contract_name=str(next(iter(contract_names))),
                forecast_contract_hash=str(next(iter(contract_hashes))),
                publication_version=publication_version,
                destination=destination,
                row_count=len(same_version),
                actor=actor,
                idempotency_key=idempotency_key,
                occurred_at=same_version.iloc[0]["published_at"],
            )
            persist_publication_event(
                event, table_prefix=self.table_prefix, project_id=self.project_id
            )
            return {
                "action": "publish",
                "publication_count": len(same_version),
                "publication_version": publication_version,
                "publication_event_id": event["publication_event_id"],
                "retry": True,
                **self._deliver_webhook(event, actor=actor),
            }
        if not existing.empty and publication_version <= int(existing["publication_version"].max()):
            raise MutationConflictError("publication_version must increase monotonically")
        persist_operation_records(
            table_prefix=self.table_prefix,
            project_id=self.project_id,
            publications=publications,
        )
        persist_publication_event(event, table_prefix=self.table_prefix, project_id=self.project_id)
        return {
            "action": "publish",
            "publication_count": len(publications),
            "publication_version": publication_version,
            "publication_event_id": event["publication_event_id"],
            "retry": False,
            **self._deliver_webhook(event, actor=actor),
        }

    def resolve_current(self, *, contract_name: str, destination: str) -> PublicationScope | None:
        query = f"""
            SELECT * FROM `{self.delivery_table}`
            WHERE forecast_contract_name = @contract_name
              AND destination = @destination
              AND delivery_status = 'delivered'
            ORDER BY published_at DESC, publication_version DESC, forecast_run_id DESC
            LIMIT 1
        """
        return self._resolve(
            query,
            [
                bigquery.ScalarQueryParameter("contract_name", "STRING", contract_name),
                bigquery.ScalarQueryParameter("destination", "STRING", destination),
            ],
        )

    @staticmethod
    def _entity_option(entity_key_json: str, grain: str) -> dict[str, Any]:
        key = json.loads(entity_key_json)
        label = ", ".join(f"{name} {value}" for name, value in sorted(key.items()))
        return {
            "id": entity_key_json,
            "name": label,
            "hierarchyNode": entity_key_json,
            "hierarchyLevel": grain,
        }

    def forecast_explorer_options(
        self, *, forecast_run_id: str | None = None
    ) -> ForecastExplorerOptions:
        rows = self._dataframe(
            f"""
            SELECT
              forecasts.forecast_run_id,
              forecasts.forecast_origin,
              forecasts.publication_version,
              forecasts.entity_key_json,
              forecasts.grain,
              forecasts.model_id,
              forecasts.model_family,
              forecasts.config_name,
              forecasts.horizon
            FROM `{self.publication_table}` AS forecasts
            INNER JOIN `{self.delivery_table}` AS deliveries
              USING (forecast_run_id, publication_version, destination)
            WHERE deliveries.delivery_status = 'delivered'
            ORDER BY forecast_origin DESC, publication_version DESC,
                     entity_key_json, model_id, horizon
            """,
            [],
        )
        if rows.empty:
            return ForecastExplorerOptions(runs=[], entities=[], models=[], horizons=[])
        records = rows.to_dict(orient="records")
        run_keys: set[str] = set()
        entity_keys: set[str] = set()
        model_keys: set[str] = set()
        runs: list[dict[str, Any]] = []
        entities: list[dict[str, Any]] = []
        models: list[dict[str, Any]] = []
        for row in records:
            run_id = str(row["forecast_run_id"])
            if run_id not in run_keys:
                run_keys.add(run_id)
                origin = str(row["forecast_origin"])
                runs.append(
                    {
                        "id": run_id,
                        "label": f"{origin} · published v{int(row['publication_version'])}",
                        "origin": origin,
                    }
                )
            if forecast_run_id is not None and run_id != forecast_run_id:
                continue
            entity_id = canonical_entity_key(str(row["entity_key_json"]))
            if entity_id and entity_id not in entity_keys:
                entity_keys.add(entity_id)
                entities.append(self._entity_option(entity_id, str(row["grain"])))
            model_id = str(row["model_id"])
            if model_id not in model_keys:
                model_keys.add(model_id)
                name = row.get("config_name") or row.get("model_family") or model_id
                models.append({"id": model_id, "name": str(name)})
        return ForecastExplorerOptions(
            runs=runs,
            entities=entities,
            models=models,
            horizons=sorted({int(value) for value in rows["horizon"]}),
        )

    @staticmethod
    def _weighted_metric(rows: pd.DataFrame, column: str) -> float | None:
        valid = rows.loc[rows[column].notna() & rows["eligible_count"].gt(0)]
        if valid.empty:
            return None
        return float(
            (valid[column].astype(float) * valid["eligible_count"].astype(float)).sum()
            / valid["eligible_count"].astype(float).sum()
        )

    @classmethod
    def _experiment_metric(cls, rows: pd.DataFrame) -> dict[str, float | None] | None:
        wape = cls._weighted_metric(rows, "wape")
        bias = cls._weighted_metric(rows, "bias")
        coverage = cls._weighted_metric(rows, "interval_coverage")
        if wape is None or bias is None:
            return None
        return {"wape": wape * 100, "bias": bias, "coverage": coverage}

    @classmethod
    def _shape_experiment_run(cls, rows: pd.DataFrame) -> dict[str, Any]:
        first = rows.iloc[0]
        status = (
            "completed"
            if str(first["run_status"]).lower()
            in {
                "completed",
                "succeeded",
                "success",
            }
            else "failed"
        )
        summary = cls._experiment_metric(rows)
        run_id = str(first["experiment_run_id"])
        model_id = str(first["baseline_name"])
        created_at = pd.to_datetime(first["run_created_at"], utc=True)
        metric_created_at = pd.to_datetime(rows["metric_created_at"], utc=True).max()
        runtime_minutes = max(
            0.01,
            float((metric_created_at - created_at).total_seconds() / 60),
        )

        horizons: list[dict[str, Any]] = []
        for horizon, grouped in rows.groupby("horizon", sort=True):
            metric = cls._experiment_metric(grouped)
            if metric is not None:
                horizons.append({"horizon": int(horizon), **metric})

        segments: list[dict[str, Any]] = []
        for segment_id, grouped in rows.groupby("segment_key_json", sort=True):
            metric = cls._experiment_metric(grouped)
            if metric is not None:
                segments.append(
                    {
                        "segmentId": str(segment_id),
                        "segmentName": (
                            "All entities" if str(segment_id) == "{}" else str(segment_id)
                        ),
                        **metric,
                    }
                )

        rolling_origins: list[dict[str, Any]] = []
        for origin, grouped in rows.groupby("forecast_origin", sort=True):
            metric = cls._experiment_metric(grouped)
            if metric is not None:
                rolling_origins.append({"origin": str(origin), **metric})

        completed_at = metric_created_at.isoformat().replace("+00:00", "Z")
        return {
            "id": run_id,
            "label": f"{model_id} · {str(first['origin_end'])}",
            "modelId": model_id,
            "modelName": model_id,
            "modelFamily": str(first["display_model_family"]),
            "featureVersion": str(first["feature_version"]),
            "status": status,
            "createdAt": created_at.isoformat().replace("+00:00", "Z"),
            "completedAt": completed_at if status == "completed" else None,
            "runtimeMinutes": runtime_minutes,
            "comparable": status == "completed" and summary is not None,
            "summary": summary,
            "configuration": {
                "backtest_contract": str(first["backtest_contract_name"]),
                "contract_hash": str(first["backtest_contract_hash"]),
                "model_config": str(first["model_config_name"]),
                "model_type": str(first["display_model_type"]),
                "target": str(first["target"]),
                "grain": str(first["grain"]),
            },
            "horizons": horizons,
            "segments": segments,
            "rollingOrigins": rolling_origins,
            "statisticalEvidence": None,
            "forecastLink": None,
        }

    @staticmethod
    def _attach_experiment_confidence(
        runs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        comparable = [run for run in runs if run["comparable"] and run["rollingOrigins"]]
        if len(comparable) < 2:
            return runs
        reference = min(comparable, key=lambda run: str(run["createdAt"]))
        reference_values = {
            row["origin"]: float(row["wape"]) for row in reference["rollingOrigins"]
        }
        for run in comparable:
            if run["id"] == reference["id"]:
                continue
            values = {row["origin"]: float(row["wape"]) for row in run["rollingOrigins"]}
            origins = sorted(set(values) & set(reference_values))
            if len(origins) < 2:
                continue
            differences = [values[origin] - reference_values[origin] for origin in origins]
            seed = int.from_bytes(
                hashlib.sha256(f"{run['id']}:{reference['id']}".encode()).digest()[:8],
                "big",
            )
            generator = random.Random(seed)
            samples = sorted(
                sum(generator.choice(differences) for _ in differences) / len(differences)
                for _ in range(2000)
            )
            lower = samples[math.floor(0.025 * (len(samples) - 1))]
            upper = samples[math.ceil(0.975 * (len(samples) - 1))]
            delta = sum(differences) / len(differences)
            opposing = (
                sum(1 for value in samples if value >= 0)
                if delta < 0
                else sum(1 for value in samples if value <= 0)
            )
            run["statisticalEvidence"] = {
                "referenceRunId": reference["id"],
                "deltaWapePp": round(delta, 3),
                "confidenceLevel": 0.95,
                "ciLower": round(lower, 3),
                "ciUpper": round(upper, 3),
                "pValue": round(min(1.0, 2 * opposing / len(samples)), 4),
                "conclusion": (
                    "meaningful" if upper < 0 else "worse" if lower > 0 else "inconclusive"
                ),
            }
        return runs

    def experiment_runs(
        self,
        *,
        model_id: str | None = None,
        model_family: str | None = None,
        feature_version: str | None = None,
        status: str | None = None,
        horizon: int | None = None,
        run_ids: tuple[str, ...] = (),
    ) -> ExperimentResult:
        clauses = ["runs.target IS NOT NULL", "runs.metric_policy_json IS NOT NULL"]
        parameters: list[Any] = []
        if model_id:
            clauses.append("metrics.baseline_name = @model_id")
            parameters.append(bigquery.ScalarQueryParameter("model_id", "STRING", model_id))
        if model_family:
            clauses.append(
                "IF(metrics.baseline_name = runs.model_config_name, runs.model_family, "
                "'baseline') = @model_family"
            )
            parameters.append(bigquery.ScalarQueryParameter("model_family", "STRING", model_family))
        if feature_version:
            clauses.append(
                "COALESCE(features.feature_availability_hash, "
                "CONCAT('contract:', SUBSTR(runs.backtest_contract_hash, 1, 12))) "
                "= @feature_version"
            )
            parameters.append(
                bigquery.ScalarQueryParameter("feature_version", "STRING", feature_version)
            )
        if status:
            clauses.append(
                "IF(LOWER(runs.status) IN ('completed', 'succeeded', 'success'), "
                "'completed', 'failed') = @status"
            )
            parameters.append(bigquery.ScalarQueryParameter("status", "STRING", status))
        if horizon is not None:
            clauses.append("metrics.horizon = @horizon")
            parameters.append(bigquery.ScalarQueryParameter("horizon", "INT64", horizon))
        if run_ids:
            clauses.append(
                "CONCAT(runs.backtest_run_id, ':', metrics.baseline_name) IN UNNEST(@run_ids)"
            )
            parameters.append(bigquery.ArrayQueryParameter("run_ids", "STRING", list(run_ids)))
        rows = self._dataframe(
            f"""
            WITH features AS (
              SELECT
                backtest_run_id,
                baseline_name,
                ARRAY_AGG(
                  DISTINCT feature_availability_hash IGNORE NULLS
                  ORDER BY feature_availability_hash LIMIT 1
                )[SAFE_OFFSET(0)] AS feature_availability_hash
              FROM `{self.backtest_predictions_table}`
              GROUP BY backtest_run_id, baseline_name
            )
            SELECT
              CONCAT(runs.backtest_run_id, ':', metrics.baseline_name) AS experiment_run_id,
              runs.backtest_contract_name,
              runs.backtest_contract_hash,
              runs.model_config_name,
              runs.model_family,
              runs.model_type,
              runs.target,
              runs.grain,
              runs.status AS run_status,
              runs.origin_end,
              runs.created_at AS run_created_at,
              metrics.baseline_name,
              IF(metrics.baseline_name = runs.model_config_name, runs.model_family, 'baseline')
                AS display_model_family,
              IF(metrics.baseline_name = runs.model_config_name, runs.model_type, 'baseline')
                AS display_model_type,
              COALESCE(features.feature_availability_hash,
                CONCAT('contract:', SUBSTR(runs.backtest_contract_hash, 1, 12)))
                AS feature_version,
              metrics.forecast_origin,
              metrics.horizon,
              metrics.segment_key_json,
              metrics.eligible_count,
              metrics.wape,
              metrics.bias,
              metrics.interval_coverage,
              metrics.created_at AS metric_created_at
            FROM `{self.backtest_runs_table}` AS runs
            INNER JOIN `{self.backtest_metrics_table}` AS metrics
              USING (backtest_run_id, backtest_contract_name, backtest_contract_hash)
            LEFT JOIN features
              USING (backtest_run_id, baseline_name)
            WHERE {' AND '.join(clauses)}
            ORDER BY runs.created_at DESC, experiment_run_id,
                     metrics.forecast_origin, metrics.horizon, metrics.segment_key_json
            """,
            parameters,
        )
        if rows.empty:
            return ExperimentResult(runs=[], missing_run_ids=list(dict.fromkeys(run_ids)))
        shaped = self._attach_experiment_confidence(
            [
                self._shape_experiment_run(group)
                for _, group in rows.groupby("experiment_run_id", sort=False)
            ]
        )
        found = {str(run["id"]) for run in shaped}
        return ExperimentResult(
            runs=shaped,
            missing_run_ids=[run_id for run_id in dict.fromkeys(run_ids) if run_id not in found],
        )

    def experiment_options(self) -> ExperimentOptions:
        result = self.experiment_runs()
        runs = result.runs
        return ExperimentOptions(
            runs=[
                {"id": run["id"], "label": run["label"], "comparable": run["comparable"]}
                for run in runs
            ],
            models=list(
                {
                    str(run["modelId"]): {
                        "id": str(run["modelId"]),
                        "name": str(run["modelName"]),
                    }
                    for run in runs
                }.values()
            ),
            model_families=sorted({str(run["modelFamily"]) for run in runs}),
            feature_versions=sorted({str(run["featureVersion"]) for run in runs}),
            statuses=sorted({str(run["status"]) for run in runs}),
            horizons=sorted({int(metric["horizon"]) for run in runs for metric in run["horizons"]}),
        )

    def operations_snapshot(self) -> list[dict[str, Any]]:
        summaries = self._dataframe(
            f"""
            WITH output_counts AS (
              SELECT forecast_run_id, COUNT(*) AS output_count,
                     COUNTIF(confidence_flag IN ('medium', 'low')) AS exception_count,
                     ANY_VALUE(config_name) AS model_name
              FROM `{self.outputs_table}` GROUP BY forecast_run_id
            ), override_counts AS (
              SELECT forecast_run_id, COUNT(DISTINCT override_id) AS override_count
              FROM `{self.overrides_table}` GROUP BY forecast_run_id
            ), approval_counts AS (
              SELECT forecast_run_id, COUNT(DISTINCT approval_id) AS approval_count
              FROM `{self.approvals_table}` WHERE decision = 'approved'
              GROUP BY forecast_run_id
            ), latest_publications AS (
              SELECT forecast_run_id, MAX(publication_version) AS publication_version,
                     MAX(published_at) AS published_at
              FROM `{self.publications_table}` WHERE destination = 'canonical_bigquery'
              GROUP BY forecast_run_id
            ), latest_delivery AS (
              SELECT * EXCEPT(row_number) FROM (
                SELECT forecast_run_id, publication_version, delivery_status, delivery_status_at,
                       ROW_NUMBER() OVER (
                         PARTITION BY forecast_run_id ORDER BY publication_version DESC,
                         delivery_status_at DESC
                       ) AS row_number
                FROM `{self.delivery_table}` WHERE destination = 'canonical_bigquery'
              ) WHERE row_number = 1
            ), fva AS (
              SELECT forecast_run_id,
                     ARRAY_AGG(STRUCT(
                       comparison_status, planner_wape_fva_points, total_wape_fva_points
                     ) ORDER BY publication_version DESC, horizon DESC LIMIT 1)[OFFSET(0)] AS latest
              FROM `{self.operations_fva_table}` GROUP BY forecast_run_id
            )
            SELECT runs.forecast_run_id, DATE(runs.forecast_origin) AS origin,
              CASE WHEN runs.run_status IN
                ('draft', 'approved', 'published', 'superseded', 'failed')
                THEN runs.run_status WHEN runs.error_message IS NOT NULL THEN 'failed'
                ELSE 'draft' END AS status,
              COALESCE(outputs.model_name, runs.config_name, runs.model_id, 'unknown') AS model_name,
              COALESCE(outputs.output_count, runs.row_count, 0) AS output_count,
              COALESCE(runs.exception_count, outputs.exception_count, 0) AS exception_count,
              COALESCE(overrides.override_count, 0) AS override_count,
              COALESCE(approvals.approval_count, 0) AS approval_count,
              publications.publication_version,
              COALESCE(delivery.delivery_status, 'not_published') AS delivery_status,
              COALESCE(fva.latest.comparison_status, 'awaiting_actuals') AS fva_status,
              fva.latest.planner_wape_fva_points, fva.latest.total_wape_fva_points,
              COALESCE(delivery.delivery_status_at, publications.published_at,
                       runs.finished_at, runs.started_at) AS updated_at
            FROM `{self.forecast_runs_table}` AS runs
            LEFT JOIN output_counts AS outputs USING (forecast_run_id)
            LEFT JOIN override_counts AS overrides USING (forecast_run_id)
            LEFT JOIN approval_counts AS approvals USING (forecast_run_id)
            LEFT JOIN latest_publications AS publications USING (forecast_run_id)
            LEFT JOIN latest_delivery AS delivery USING (forecast_run_id, publication_version)
            LEFT JOIN fva USING (forecast_run_id)
            WHERE outputs.output_count IS NOT NULL
            ORDER BY runs.forecast_origin DESC, runs.forecast_run_id DESC LIMIT 100
            """,
            [],
        )
        if summaries.empty:
            return []
        run_ids = [str(value) for value in summaries["forecast_run_id"]]
        samples = self._dataframe(
            f"""
            SELECT * EXCEPT(row_number) FROM (
              SELECT forecast_run_id, forecast_output_id, entity_key_json, target_date,
                     COALESCE(planner_override, prediction_p50) AS current_value,
                     CASE confidence_flag WHEN 'low' THEN 'blocked'
                       WHEN 'medium' THEN 'watch' ELSE 'clear' END AS exception_state,
                     ROW_NUMBER() OVER (
                       PARTITION BY forecast_run_id ORDER BY
                         CASE confidence_flag WHEN 'low' THEN 1
                           WHEN 'medium' THEN 2 ELSE 3 END,
                         target_date, forecast_output_id
                     ) AS row_number
              FROM `{self.outputs_table}` WHERE forecast_run_id IN UNNEST(@run_ids)
            ) WHERE row_number <= 20 ORDER BY forecast_run_id, row_number
            """,
            [bigquery.ArrayQueryParameter("run_ids", "STRING", run_ids)],
        )
        outputs_by_run: dict[str, list[dict[str, Any]]] = {}
        for row in samples.to_dict(orient="records"):
            run_id = str(row["forecast_run_id"])
            entity_key = canonical_entity_key(str(row["entity_key_json"])) or "{}"
            outputs_by_run.setdefault(run_id, []).append(
                {
                    "id": str(row["forecast_output_id"]),
                    "entityLabel": self._entity_option(entity_key, "")["name"],
                    "targetDate": str(row["target_date"]),
                    "currentValue": float(row["current_value"]),
                    "exceptionState": str(row["exception_state"]),
                }
            )
        result: list[dict[str, Any]] = []
        for row in summaries.to_dict(orient="records"):
            run_id = str(row["forecast_run_id"])
            result.append(
                {
                    "runId": run_id,
                    "origin": str(row["origin"]),
                    "status": str(row["status"]),
                    "modelName": str(row["model_name"]),
                    "outputCount": int(row["output_count"]),
                    "exceptionCount": int(row["exception_count"]),
                    "overrideCount": int(row["override_count"]),
                    "approvalCount": int(row["approval_count"]),
                    "publicationVersion": (
                        None
                        if pd.isna(row["publication_version"])
                        else int(row["publication_version"])
                    ),
                    "deliveryStatus": str(row["delivery_status"]),
                    "fvaStatus": str(row["fva_status"]),
                    "plannerWapeFvaPoints": (
                        None
                        if pd.isna(row["planner_wape_fva_points"])
                        else float(row["planner_wape_fva_points"]) * 100
                    ),
                    "totalWapeFvaPoints": (
                        None
                        if pd.isna(row["total_wape_fva_points"])
                        else float(row["total_wape_fva_points"]) * 100
                    ),
                    "updatedAt": row["updated_at"].isoformat(),
                    "outputs": outputs_by_run.get(run_id, []),
                }
            )
        return result

    def pipeline_runs(self) -> list[dict[str, Any]]:
        summaries = self._dataframe(
            f"""
            SELECT * FROM `{self.pipeline_health_table}`
            ORDER BY started_at DESC, forecast_run_id DESC LIMIT 25
            """,
            [],
        )
        if summaries.empty:
            return []
        run_ids = [str(value) for value in summaries["forecast_run_id"]]
        stages = self._dataframe(
            f"""
            SELECT * FROM `{self.pipeline_stages_table}`
            WHERE forecast_run_id IN UNNEST(@run_ids)
            ORDER BY forecast_run_id, stage_position
            """,
            [bigquery.ArrayQueryParameter("run_ids", "STRING", run_ids)],
        )
        checks = self._dataframe(
            f"""
            SELECT * FROM `{self.validation_checks_table}`
            WHERE forecast_run_id IN UNNEST(@run_ids)
            ORDER BY forecast_run_id, checked_at, check_name
            """,
            [bigquery.ArrayQueryParameter("run_ids", "STRING", run_ids)],
        )
        stages_by_run: dict[str, list[dict[str, Any]]] = {}
        for row in stages.to_dict(orient="records"):
            started = row["started_at"]
            finished = row.get("finished_at")
            duration = None if pd.isna(finished) else (finished - started).total_seconds()
            stages_by_run.setdefault(str(row["forecast_run_id"]), []).append(
                {
                    "name": str(row["stage_name"]),
                    "position": int(row["stage_position"]),
                    "status": str(row["stage_status"]),
                    "inputRows": int(row["input_row_count"]),
                    "outputRows": int(row["output_row_count"]),
                    "durationSeconds": duration,
                    "retryState": "idempotent" if str(row["component_run_id"]) else "unknown",
                    "errorMessage": (
                        None if pd.isna(row.get("error_message")) else str(row["error_message"])
                    ),
                }
            )
        checks_by_run: dict[str, list[dict[str, Any]]] = {}
        for row in checks.to_dict(orient="records"):
            checks_by_run.setdefault(str(row["forecast_run_id"]), []).append(
                {
                    "name": str(row["check_name"]),
                    "severity": str(row["severity"]),
                    "passed": bool(row["passed"]),
                    "observedValue": (
                        None if pd.isna(row.get("observed_value")) else float(row["observed_value"])
                    ),
                    "thresholdValue": (
                        None
                        if pd.isna(row.get("threshold_value"))
                        else float(row["threshold_value"])
                    ),
                }
            )
        result: list[dict[str, Any]] = []
        for row in summaries.to_dict(orient="records"):
            run_id = str(row["forecast_run_id"])
            result.append(
                {
                    "runId": run_id,
                    "contractName": str(row["forecast_contract_name"]),
                    "origin": str(row["forecast_origin"]),
                    "status": str(row["run_status"]),
                    "healthStatus": str(row["health_status"]),
                    "startedAt": row["started_at"].isoformat(),
                    "finishedAt": (
                        None if pd.isna(row.get("finished_at")) else row["finished_at"].isoformat()
                    ),
                    "candidateCount": int(row["candidate_count"]),
                    "eligibleCount": int(row["eligible_count"]),
                    "outputCount": int(row["persisted_output_count"]),
                    "horizonCount": int(row["horizon_count"]),
                    "missingQuantileCount": int(row["missing_quantile_count"]),
                    "stages": stages_by_run.get(run_id, []),
                    "gates": checks_by_run.get(run_id, []),
                }
            )
        return result

    @staticmethod
    def _has_hierarchy_cycle(edges: list[dict[str, Any]]) -> bool:
        children: dict[str, list[str]] = {}
        for edge in edges:
            children.setdefault(str(edge["parent_node_id"]), []).append(str(edge["child_node_id"]))
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> bool:
            if node in visiting:
                return True
            if node in visited:
                return False
            visiting.add(node)
            if any(visit(child) for child in children.get(node, [])):
                return True
            visiting.remove(node)
            visited.add(node)
            return False

        return any(visit(node) for node in children)

    def hierarchy_snapshot(self, hierarchy_version: str) -> dict[str, Any] | None:
        version_filter = (
            "" if hierarchy_version == "current" else "WHERE hierarchy_version = @version"
        )
        parameters = (
            []
            if hierarchy_version == "current"
            else [bigquery.ScalarQueryParameter("version", "STRING", hierarchy_version)]
        )
        runs = self._dataframe(
            f"""
            SELECT * FROM `{self.reconciliation_runs_table}`
            {version_filter}
            ORDER BY started_at DESC, reconciliation_run_id DESC LIMIT 1
            """,
            parameters,
        )
        if runs.empty:
            return None
        run = runs.iloc[0]
        version = str(run["hierarchy_version"])
        common = [bigquery.ScalarQueryParameter("version", "STRING", version)]
        nodes = self._dataframe(
            f"""SELECT * FROM `{self.hierarchy_nodes_table}`
            WHERE hierarchy_version = @version ORDER BY level_position, node_id""",
            common,
        )
        edges_frame = self._dataframe(
            f"""SELECT * FROM `{self.hierarchy_edges_table}`
            WHERE hierarchy_version = @version ORDER BY parent_node_id, child_node_id""",
            common,
        )
        outputs = self._dataframe(
            f"""
            SELECT node_id, level_name,
              AVG(base_prediction_p50) AS base_p50,
              AVG(prediction_p50) AS reconciled_p50,
              COUNTIF(prediction_p10 IS NULL OR prediction_p50 IS NULL OR prediction_p90 IS NULL)
                AS missing_quantile_count,
              COUNTIF(NOT (prediction_p10 <= prediction_p50 AND prediction_p50 <= prediction_p90))
                AS unordered_quantile_count
            FROM `{self.reconciled_outputs_table}`
            WHERE reconciliation_run_id = @run_id
            GROUP BY node_id, level_name ORDER BY level_name, node_id
            """,
            [bigquery.ScalarQueryParameter("run_id", "STRING", str(run["reconciliation_run_id"]))],
        )
        edge_records = edges_frame.to_dict(orient="records")
        parent_counts: dict[str, int] = {}
        parent_by_child: dict[str, str] = {}
        for edge in edge_records:
            child = str(edge["child_node_id"])
            parent_counts[child] = parent_counts.get(child, 0) + 1
            parent_by_child[child] = str(edge["parent_node_id"])
        node_records = nodes.to_dict(orient="records")
        root_position = min((int(row["level_position"]) for row in node_records), default=0)
        non_roots = [row for row in node_records if int(row["level_position"]) > root_position]
        parent_violations = sum(parent_counts.get(str(row["node_id"]), 0) != 1 for row in non_roots)
        output_records = outputs.to_dict(orient="records")
        missing_quantiles = sum(int(row["missing_quantile_count"]) for row in output_records)
        unordered_quantiles = sum(int(row["unordered_quantile_count"]) for row in output_records)
        levels: dict[tuple[int, str], int] = {}
        for row in node_records:
            key = (int(row["level_position"]), str(row["level_name"]))
            levels[key] = levels.get(key, 0) + 1
        output_by_node = {str(row["node_id"]): row for row in output_records}
        shaped_nodes = []
        for row in node_records[:500]:
            node_id = str(row["node_id"])
            values = output_by_node.get(node_id, {})
            base = None if pd.isna(values.get("base_p50")) else float(values["base_p50"])
            reconciled = (
                None if pd.isna(values.get("reconciled_p50")) else float(values["reconciled_p50"])
            )
            shaped_nodes.append(
                {
                    "id": node_id,
                    "label": str(row["node_key_json"]),
                    "level": str(row["level_name"]),
                    "levelPosition": int(row["level_position"]),
                    "parentId": parent_by_child.get(node_id),
                    "baseP50": base,
                    "reconciledP50": reconciled,
                    "delta": None if base is None or reconciled is None else reconciled - base,
                }
            )
        violation_count = int(run["violation_count"] or 0)
        cycle = self._has_hierarchy_cycle(edge_records)
        return {
            "hierarchyName": str(run["hierarchy_name"]),
            "hierarchyVersion": version,
            "reconciliationRunId": str(run["reconciliation_run_id"]),
            "forecastRunId": str(run["forecast_run_id"]),
            "method": str(run["reconciliation_method"]),
            "status": str(run["run_status"]),
            "tolerance": float(run["tolerance_abs"]),
            "nodeCount": len(node_records),
            "edgeCount": len(edge_records),
            "levels": [
                {"name": name, "position": position, "nodeCount": count}
                for (position, name), count in sorted(levels.items())
            ],
            "nodes": shaped_nodes,
            "gates": [
                {
                    "name": "Exactly one parent",
                    "passed": parent_violations == 0,
                    "violationCount": parent_violations,
                },
                {"name": "Acyclic hierarchy", "passed": not cycle, "violationCount": int(cycle)},
                {
                    "name": "Coherent child totals",
                    "passed": violation_count == 0,
                    "violationCount": violation_count,
                },
                {
                    "name": "All quantiles reconciled",
                    "passed": missing_quantiles == 0,
                    "violationCount": missing_quantiles,
                },
                {
                    "name": "Ordered quantiles",
                    "passed": unordered_quantiles == 0,
                    "violationCount": unordered_quantiles,
                },
            ],
        }

    def _revision_operation(
        self,
        *,
        action: str,
        forecast_run_id: str,
        prior_version: int,
        publication_version: int,
        destination: str,
        reason_code: str,
        comment: str,
        actor: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        try:
            result = run_forecast_operation(
                Namespace(
                    action=action,
                    forecast_run_id=forecast_run_id,
                    idempotency_key=idempotency_key,
                    actor=actor,
                    reason_code=reason_code,
                    comment=comment,
                    project_id=self.project_id,
                    table_prefix=self.table_prefix,
                    forecast_output_id=None,
                    value=None,
                    destination=destination,
                    version=publication_version,
                    prior_version=prior_version,
                )
            )
        except ValueError as exc:
            message = str(exc)
            if "no canonical output" in message or "source version" in message:
                raise MutationNotFoundError(message) from exc
            raise MutationConflictError(message) from exc
        result.setdefault("retry", False)
        return result

    def supersede_run(self, **kwargs: Any) -> dict[str, Any]:
        return self._revision_operation(action="revise", **kwargs)

    def rollback_run(self, **kwargs: Any) -> dict[str, Any]:
        return self._revision_operation(action="rollback", **kwargs)

    def forecast_explorer_result(
        self,
        *,
        forecast_run_id: str,
        entity_key_json: str,
        model_id: str,
        horizon: int | None,
        exception_state: str | None,
        target_start: date | None = None,
        target_end: date | None = None,
        limit: int = 100,
        page_token: str | None = None,
    ) -> ForecastExplorerResult | None:
        scope_rows = self._dataframe(
            f"""
            SELECT * FROM `{self.delivery_table}`
            WHERE forecast_run_id = @forecast_run_id
              AND destination = 'canonical_bigquery'
              AND delivery_status = 'delivered'
            ORDER BY publication_version DESC
            LIMIT 1
            """,
            [bigquery.ScalarQueryParameter("forecast_run_id", "STRING", forecast_run_id)],
        )
        if scope_rows.empty:
            return None
        scope = self._scope(scope_rows.iloc[0])
        clauses = [
            "f.forecast_run_id = @forecast_run_id",
            "f.publication_version = @publication_version",
            "f.destination = @destination",
            "f.entity_key_json = @entity_key_json",
            "f.model_id = @model_id",
        ]
        parameters: list[Any] = [
            bigquery.ScalarQueryParameter("forecast_run_id", "STRING", forecast_run_id),
            bigquery.ScalarQueryParameter(
                "publication_version", "INT64", scope.publication_version
            ),
            bigquery.ScalarQueryParameter("destination", "STRING", scope.destination),
            bigquery.ScalarQueryParameter("entity_key_json", "STRING", entity_key_json),
            bigquery.ScalarQueryParameter("model_id", "STRING", model_id),
        ]
        if horizon is not None:
            clauses.append("f.horizon = @horizon")
            parameters.append(bigquery.ScalarQueryParameter("horizon", "INT64", horizon))
        if exception_state is not None:
            clauses.append(
                "CASE f.confidence_flag WHEN 'low' THEN 'blocked' "
                "WHEN 'medium' THEN 'watch' ELSE 'clear' END = @exception_state"
            )
            parameters.append(
                bigquery.ScalarQueryParameter("exception_state", "STRING", exception_state)
            )
        if target_start is not None:
            clauses.append("f.target_date >= @target_start")
            parameters.append(bigquery.ScalarQueryParameter("target_start", "DATE", target_start))
        if target_end is not None:
            clauses.append("f.target_date <= @target_end")
            parameters.append(bigquery.ScalarQueryParameter("target_end", "DATE", target_end))
        cursor = decode_page_token(page_token)
        if cursor is not None:
            if cursor["entity_key_json"] != entity_key_json:
                raise ValueError("page_token does not belong to the selected entity")
            clauses.append(
                "(f.target_date > @cursor_date "
                "OR (f.target_date = @cursor_date AND f.horizon > @cursor_horizon) "
                "OR (f.target_date = @cursor_date AND f.horizon = @cursor_horizon "
                "AND f.publication_id > @cursor_publication_id))"
            )
            parameters.extend(
                [
                    bigquery.ScalarQueryParameter("cursor_date", "DATE", cursor["target_date"]),
                    bigquery.ScalarQueryParameter("cursor_horizon", "INT64", cursor["horizon"]),
                    bigquery.ScalarQueryParameter(
                        "cursor_publication_id", "STRING", cursor["publication_id"]
                    ),
                ]
            )
        parameters.append(bigquery.ScalarQueryParameter("page_limit", "INT64", limit + 1))
        rows = self._dataframe(
            f"""
            SELECT
              f.*,
              demand.observed_sales_units AS actual,
              CASE f.confidence_flag WHEN 'low' THEN 'blocked'
                   WHEN 'medium' THEN 'watch' ELSE 'clear' END AS exception_state
            FROM `{self.publication_table}` AS f
            LEFT JOIN `{self.demand_table}` AS demand
              ON demand.date = f.target_date
             AND demand.store_nbr = SAFE_CAST(JSON_VALUE(f.entity_key_json, '$.store_nbr') AS INT64)
            WHERE {' AND '.join(clauses)}
            ORDER BY f.target_date, f.horizon, f.publication_id
            LIMIT @page_limit
            """,
            parameters,
        )
        if rows.empty:
            return None
        records = rows.to_dict(orient="records")
        has_more = len(records) > limit
        records = records[:limit]
        first = records[0]
        entity = self._entity_option(entity_key_json, str(first["grain"]))
        model_name = first.get("config_name") or first.get("model_family") or model_id
        output_rows = [
            {
                "runId": forecast_run_id,
                "entityId": entity_key_json,
                "modelId": model_id,
                "targetDate": str(row["target_date"]),
                "horizon": int(row["horizon"]),
                "actual": None if pd.isna(row.get("actual")) else float(row["actual"]),
                "p10": float(row["prediction_p10"]),
                "p50": float(row["prediction_p50"]),
                "p90": float(row["prediction_p90"]),
                "statisticalForecast": float(row["statistical_forecast"]),
                "publishedForecast": float(row["published_value"]),
                "strategy": str(row["forecast_strategy"]),
                "exceptionState": str(row["exception_state"]),
            }
            for row in records
        ]
        return ForecastExplorerResult(
            run={
                "id": forecast_run_id,
                "label": f"{first['forecast_origin']} · published v{scope.publication_version}",
                "origin": str(first["forecast_origin"]),
                "publicationStatus": "published",
            },
            entity=entity,
            model={"id": model_id, "name": str(model_name)},
            rows=output_rows,
            provenance={
                "contractName": str(first["forecast_contract_name"]),
                "contractHash": str(first["forecast_contract_hash"]),
                "modelRunId": str(first["model_run_id"]),
                "calibrationRunId": str(first["calibration_run_id"]),
                "reconciliationRunId": str(first["reconciliation_run_id"]),
                "hierarchyVersion": str(first["hierarchy_version"]),
                "featureVersion": str(first["feature_version"]),
                "featureAvailabilityHash": str(first["feature_availability_hash"]),
                "dataCutoff": first["data_cutoff"].isoformat(),
                "codeSha": str(first["code_sha"]),
                "publicationVersion": str(scope.publication_version),
            },
            next_page_token=(encode_page_token(records[-1]) if has_more else None),
        )

    def resolve_version(
        self,
        *,
        forecast_run_id: str,
        publication_version: int,
        destination: str,
    ) -> PublicationScope | None:
        query = f"""
            SELECT * FROM `{self.delivery_table}`
            WHERE forecast_run_id = @forecast_run_id
              AND publication_version = @publication_version
              AND destination = @destination
            LIMIT 1
        """
        return self._resolve(
            query,
            [
                bigquery.ScalarQueryParameter("forecast_run_id", "STRING", forecast_run_id),
                bigquery.ScalarQueryParameter("publication_version", "INT64", publication_version),
                bigquery.ScalarQueryParameter("destination", "STRING", destination),
            ],
        )

    def fetch_page(
        self,
        scope: PublicationScope,
        *,
        filters: ForecastFilters,
        limit: int,
        page_token: str | None,
    ) -> ForecastPageResult:
        count_query = f"""
            SELECT COUNT(*) AS row_count
            FROM `{self.publication_table}`
            WHERE forecast_run_id = @forecast_run_id
              AND publication_version = @publication_version
              AND destination = @destination
        """
        base_parameters: list[Any] = [
            bigquery.ScalarQueryParameter("forecast_run_id", "STRING", scope.forecast_run_id),
            bigquery.ScalarQueryParameter(
                "publication_version", "INT64", scope.publication_version
            ),
            bigquery.ScalarQueryParameter("destination", "STRING", scope.destination),
        ]
        count_config = bigquery.QueryJobConfig(query_parameters=base_parameters)
        persisted_count = int(
            next(iter(self.client.query(count_query, job_config=count_config).result()))[
                "row_count"
            ]
        )
        if persisted_count != scope.publication_row_count:
            raise RuntimeError(
                "publication version is incomplete: "
                f"expected {scope.publication_row_count}, found {persisted_count}"
            )

        clauses = [
            "forecast_run_id = @forecast_run_id",
            "publication_version = @publication_version",
            "destination = @destination",
        ]
        parameters = list(base_parameters)
        if filters.entity_key_json:
            clauses.append("entity_key_json = @entity_key_json")
            parameters.append(
                bigquery.ScalarQueryParameter("entity_key_json", "STRING", filters.entity_key_json)
            )
        if filters.target_start:
            clauses.append("target_date >= @target_start")
            parameters.append(
                bigquery.ScalarQueryParameter("target_start", "DATE", filters.target_start)
            )
        if filters.target_end:
            clauses.append("target_date <= @target_end")
            parameters.append(
                bigquery.ScalarQueryParameter("target_end", "DATE", filters.target_end)
            )
        if filters.horizons:
            clauses.append("horizon IN UNNEST(@horizons)")
            parameters.append(bigquery.ArrayQueryParameter("horizons", "INT64", filters.horizons))

        cursor = decode_page_token(page_token)
        if cursor:
            clauses.append(
                "(entity_key_json > @cursor_entity "
                "OR (entity_key_json = @cursor_entity AND target_date > @cursor_date) "
                "OR (entity_key_json = @cursor_entity AND target_date = @cursor_date "
                "AND horizon > @cursor_horizon) "
                "OR (entity_key_json = @cursor_entity AND target_date = @cursor_date "
                "AND horizon = @cursor_horizon AND publication_id > @cursor_publication_id))"
            )
            parameters.extend(
                [
                    bigquery.ScalarQueryParameter(
                        "cursor_entity", "STRING", cursor["entity_key_json"]
                    ),
                    bigquery.ScalarQueryParameter("cursor_date", "DATE", cursor["target_date"]),
                    bigquery.ScalarQueryParameter("cursor_horizon", "INT64", cursor["horizon"]),
                    bigquery.ScalarQueryParameter(
                        "cursor_publication_id", "STRING", cursor["publication_id"]
                    ),
                ]
            )
        parameters.append(bigquery.ScalarQueryParameter("page_limit", "INT64", limit + 1))
        query = f"""
            SELECT {', '.join(FORECAST_COLUMNS)}
            FROM `{self.publication_table}`
            WHERE {' AND '.join(clauses)}
            ORDER BY entity_key_json, target_date, horizon, publication_id
            LIMIT @page_limit
        """
        config = bigquery.QueryJobConfig(query_parameters=parameters)
        records = [
            dict(row.items()) for row in self.client.query(query, job_config=config).result()
        ]
        has_more = len(records) > limit
        records = records[:limit]
        next_token = encode_page_token(records[-1]) if has_more and records else None
        return ForecastPageResult(scope=scope, rows=records, next_page_token=next_token)
