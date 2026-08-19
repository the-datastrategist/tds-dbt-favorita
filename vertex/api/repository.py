"""BigQuery-backed retrieval for complete, immutable forecast publication versions."""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol

import pandas as pd
from google.cloud import bigquery

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
    def forecast_explorer_options(self) -> ForecastExplorerOptions:
        """Return filter values drawn only from completely delivered publications."""

    def forecast_explorer_result(
        self,
        *,
        forecast_run_id: str,
        entity_key_json: str,
        model_id: str,
        horizon: int | None,
        exception_state: str | None,
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

    def _resolve(
        self, query: str, parameters: list[bigquery.ScalarQueryParameter]
    ) -> PublicationScope | None:
        config = bigquery.QueryJobConfig(query_parameters=parameters)
        rows = list(self.client.query(query, job_config=config).result())
        return self._scope(rows[0]) if rows else None

    def _dataframe(
        self, query: str, parameters: list[bigquery.ScalarQueryParameter]
    ) -> pd.DataFrame:
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

    def forecast_explorer_options(self) -> ForecastExplorerOptions:
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

    def forecast_explorer_result(
        self,
        *,
        forecast_run_id: str,
        entity_key_json: str,
        model_id: str,
        horizon: int | None,
        exception_state: str | None,
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
            """,
            parameters,
        )
        if rows.empty:
            return None
        records = rows.to_dict(orient="records")
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
