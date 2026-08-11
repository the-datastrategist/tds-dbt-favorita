#!/usr/bin/env python3
"""Record one normalized cloud or forecast-pipeline cost event."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime

from vertex.monitoring.costs import build_cost_event, persist_cost_event


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-name", required=True)
    parser.add_argument("--cost-type", required=True)
    parser.add_argument("--usage-start-at", required=True, type=_timestamp)
    parser.add_argument("--usage-end-at", required=True, type=_timestamp)
    parser.add_argument("--amount-usd", required=True)
    parser.add_argument("--source-system", required=True)
    parser.add_argument("--source-event-id", required=True)
    parser.add_argument("--forecast-contract-name")
    parser.add_argument("--forecast-run-id")
    parser.add_argument("--model-run-id")
    parser.add_argument("--stage-name")
    parser.add_argument("--environment")
    parser.add_argument("--usage-amount")
    parser.add_argument("--usage-unit")
    parser.add_argument("--bytes-processed", type=int)
    parser.add_argument("--slot-ms", type=int)
    parser.add_argument("--labels-json", default="{}")
    parser.add_argument("--table-id")
    args = parser.parse_args()

    project = os.getenv("GOOGLE_PROJECT_ID")
    if not project and not args.table_id:
        raise ValueError("GOOGLE_PROJECT_ID is required when --table-id is not provided")
    dataset = os.getenv("DBT_DATASET", "favorita")
    table_id = args.table_id or f"{project}.{dataset}.forecast_cost_events"
    labels = json.loads(args.labels_json)
    if not isinstance(labels, dict):
        raise ValueError("labels-json must contain an object")
    row = build_cost_event(
        service_name=args.service_name,
        cost_type=args.cost_type,
        usage_start_at=args.usage_start_at,
        usage_end_at=args.usage_end_at,
        amount_usd=args.amount_usd,
        source_system=args.source_system,
        source_event_id=args.source_event_id,
        forecast_contract_name=args.forecast_contract_name,
        forecast_run_id=args.forecast_run_id,
        model_run_id=args.model_run_id,
        stage_name=args.stage_name,
        environment=args.environment,
        usage_amount=args.usage_amount,
        usage_unit=args.usage_unit,
        bytes_processed=args.bytes_processed,
        slot_ms=args.slot_ms,
        labels=labels,
    )
    inserted = persist_cost_event(row, table_id=table_id, project_id=project)
    print({"cost_event_id": row["cost_event_id"], "inserted": inserted})


if __name__ == "__main__":
    main()
