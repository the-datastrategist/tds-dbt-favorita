#!/usr/bin/env python3
"""Evaluate normalized monitoring signal JSON and route configured alerts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from google.cloud import bigquery

from vertex.config.monitoring import DEFAULT_MONITORING_PATH, load_monitoring_config
from vertex.monitoring.alerts import evaluate_alerts, route_alerts
from vertex.utils.bigquery_utils import validate_bq_table_id

SIGNAL_TABLES = {
    "pipeline_cost": "forecast_pipeline_cost",
    "data_drift": "forecast_data_drift",
    "delivery_health": "forecast_delivery_health",
    "feature_completeness": "forecast_feature_completeness",
    "publication_freshness": "forecast_publication_freshness",
    "prediction_coverage": "forecast_prediction_coverage",
    "pipeline_health": "forecast_pipeline_health",
    "realized_calibration": "forecast_realized_calibration",
}


def _load_rows(path: str | None) -> list[dict[str, Any]]:
    if not path:
        return []
    with Path(path).open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
        raise ValueError(f"{path} must contain a JSON array of objects")
    return payload


def load_bigquery_rows(*, project_id: str, table_prefix: str) -> dict[str, list[dict[str, Any]]]:
    """Read normalized monitoring views through validated table identifiers."""
    client = bigquery.Client(project=project_id)
    rows: dict[str, list[dict[str, Any]]] = {}
    for signal, table_name in SIGNAL_TABLES.items():
        table = validate_bq_table_id(f"{table_prefix}.{table_name}")
        frame = client.query(f"SELECT * FROM `{table}`").to_dataframe()
        rows[signal] = frame.to_dict(orient="records")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_MONITORING_PATH))
    parser.add_argument("--source", choices=("bigquery", "json"), default="bigquery")
    parser.add_argument("--project-id", default="tds-favorita")
    parser.add_argument("--table-prefix", default="tds-favorita.favorita")
    parser.add_argument("--publication-freshness-json")
    parser.add_argument("--pipeline-cost-json")
    parser.add_argument("--data-drift-json")
    parser.add_argument("--delivery-health-json")
    parser.add_argument("--feature-completeness-json")
    parser.add_argument("--prediction-coverage-json")
    parser.add_argument("--pipeline-health-json")
    parser.add_argument("--realized-calibration-json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config = load_monitoring_config(args.config)
    if args.source == "json":
        signal_rows = {
            "pipeline_cost": _load_rows(args.pipeline_cost_json),
            "data_drift": _load_rows(args.data_drift_json),
            "delivery_health": _load_rows(args.delivery_health_json),
            "feature_completeness": _load_rows(args.feature_completeness_json),
            "publication_freshness": _load_rows(args.publication_freshness_json),
            "prediction_coverage": _load_rows(args.prediction_coverage_json),
            "pipeline_health": _load_rows(args.pipeline_health_json),
            "realized_calibration": _load_rows(args.realized_calibration_json),
        }
    else:
        if any(
            (
                args.pipeline_cost_json,
                args.data_drift_json,
                args.delivery_health_json,
                args.publication_freshness_json,
                args.feature_completeness_json,
                args.prediction_coverage_json,
                args.pipeline_health_json,
                args.realized_calibration_json,
            )
        ):
            parser.error("JSON paths require --source json")
        signal_rows = load_bigquery_rows(project_id=args.project_id, table_prefix=args.table_prefix)
    events = evaluate_alerts(config, signal_rows)
    if args.dry_run:
        print(json.dumps([event.__dict__ for event in events], indent=2, default=str))
        return
    print(json.dumps({"emitted_alert_count": route_alerts(config, events)}))


if __name__ == "__main__":
    main()
