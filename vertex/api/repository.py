"""BigQuery-backed retrieval for complete, immutable forecast publication versions."""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol

from google.cloud import bigquery

from vertex.utils.bigquery_utils import validate_bq_table_id

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
    "hierarchy_version",
    "reconciliation_method",
    "reconciliation_run_id",
    "model_run_id",
    "model_id",
    "config_name",
    "model_family",
    "model_type",
    "feature_version",
    "code_sha",
    "data_cutoff",
    "published_at",
    "published_by",
)


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


class ForecastRepository(Protocol):
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
    def __init__(self, *, project_id: str, table_prefix: str) -> None:
        self.client = bigquery.Client(project=project_id)
        self.delivery_table = validate_bq_table_id(f"{table_prefix}.forecast_delivery_current")
        self.publication_table = validate_bq_table_id(f"{table_prefix}.published_forecasts_by_run")

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
