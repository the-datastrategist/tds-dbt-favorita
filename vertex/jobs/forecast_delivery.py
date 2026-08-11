"""Record immutable delivery outcomes for one published forecast version."""

from __future__ import annotations

import argparse
import json

from google.cloud import bigquery

from vertex.utils.bigquery_utils import validate_bq_table_id
from vertex.utils.forecast_delivery import build_delivery_event, persist_delivery_event


def _query(project_id: str, sql: str, parameters: list[bigquery.ScalarQueryParameter]):
    client = bigquery.Client(project=project_id)
    return client.query(
        sql, job_config=bigquery.QueryJobConfig(query_parameters=parameters)
    ).to_dataframe()


def _table(prefix: str, name: str) -> str:
    return validate_bq_table_id(f"{prefix}.{name}")


def run(args: argparse.Namespace) -> dict[str, object]:
    publications = _table(args.table_prefix, "forecast_publications")
    outputs = _table(args.table_prefix, "forecast_outputs")
    delivery_events = _table(args.table_prefix, "forecast_delivery_events")
    parameters = [
        bigquery.ScalarQueryParameter("forecast_run_id", "STRING", args.forecast_run_id),
        bigquery.ScalarQueryParameter("publication_version", "INT64", args.version),
        bigquery.ScalarQueryParameter("destination", "STRING", args.destination),
    ]
    scope = _query(
        args.project_id,
        f"""
        SELECT
          COUNT(*) AS publication_count,
          COUNT(DISTINCT publication_id) AS distinct_publication_count,
          (SELECT COUNT(*) FROM `{outputs}`
           WHERE forecast_run_id = @forecast_run_id) AS expected_output_count
        FROM `{publications}`
        WHERE forecast_run_id = @forecast_run_id
          AND publication_version = @publication_version
          AND destination = @destination
        """,
        parameters,
    ).iloc[0]
    if (
        int(scope["publication_count"]) < 1
        or int(scope["publication_count"]) != int(scope["distinct_publication_count"])
        or int(scope["publication_count"]) != int(scope["expected_output_count"])
    ):
        raise ValueError("delivery requires one complete, duplicate-free publication version")

    latest = _query(
        args.project_id,
        f"""
        SELECT delivery_status, delivery_attempt
        FROM `{delivery_events}`
        WHERE forecast_run_id = @forecast_run_id
          AND publication_version = @publication_version
          AND destination = @destination
        ORDER BY occurred_at DESC, delivery_event_id DESC
        LIMIT 1
        """,
        parameters,
    )
    prior_status = None if latest.empty else str(latest.iloc[0]["delivery_status"])
    prior_attempt = 0 if latest.empty else int(latest.iloc[0]["delivery_attempt"])
    status_by_action = {
        "start": "pending",
        "confirm": "delivered",
        "fail": "failed",
        "abandon": "abandoned",
        "retry": "pending",
    }
    delivery_status = status_by_action[args.action]
    existing_key = _query(
        args.project_id,
        f"""
        SELECT delivery_event_id, delivery_status, delivery_attempt
        FROM `{delivery_events}`
        WHERE forecast_run_id = @forecast_run_id
          AND publication_version = @publication_version
          AND destination = @destination
          AND idempotency_key = @idempotency_key
        """,
        parameters
        + [bigquery.ScalarQueryParameter("idempotency_key", "STRING", args.idempotency_key)],
    )
    if not existing_key.empty:
        if (
            len(existing_key) != 1
            or str(existing_key.iloc[0]["delivery_status"]) != delivery_status
        ):
            raise ValueError("delivery idempotency key conflicts with persisted event")
        return {
            "action": args.action,
            "delivery_event_id": str(existing_key.iloc[0]["delivery_event_id"]),
            "delivery_status": delivery_status,
            "delivery_attempt": int(existing_key.iloc[0]["delivery_attempt"]),
            "retry": True,
        }
    delivery_attempt = prior_attempt + 1 if args.action in {"start", "retry"} else prior_attempt
    event = build_delivery_event(
        forecast_run_id=args.forecast_run_id,
        publication_version=args.version,
        destination=args.destination,
        delivery_status=delivery_status,
        delivery_attempt=delivery_attempt,
        actor=args.actor,
        idempotency_key=args.idempotency_key,
        prior_status=prior_status,
        delivery_reference=args.delivery_reference,
        error_code=args.error_code,
        error_message=args.error_message,
        details=json.loads(args.details_json) if args.details_json else None,
    )
    persist_delivery_event(event, table_prefix=args.table_prefix, project_id=args.project_id)
    return {
        "action": args.action,
        "delivery_event_id": event["delivery_event_id"],
        "delivery_status": delivery_status,
        "delivery_attempt": delivery_attempt,
        "publication_count": int(scope["publication_count"]),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "confirm", "fail", "abandon", "retry"))
    parser.add_argument("--forecast-run-id", required=True)
    parser.add_argument("--version", required=True, type=int)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--idempotency-key", required=True)
    parser.add_argument("--delivery-reference")
    parser.add_argument("--error-code")
    parser.add_argument("--error-message")
    parser.add_argument("--details-json")
    parser.add_argument("--project-id", default="tds-favorita")
    parser.add_argument("--table-prefix", default="tds-favorita.favorita")
    return parser


def main() -> None:
    args = _parser().parse_args()
    print(json.dumps(run(args), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
