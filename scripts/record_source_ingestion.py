#!/usr/bin/env python3
"""Record an ingestion outcome for static-demo or continuously updating sources."""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone

from vertex.config.source_monitoring import load_source_monitoring_config
from vertex.monitoring.source_ingestion import (
    build_source_ingestion_row,
    persist_source_ingestion_row,
)
from vertex.utils.run_context import get_git_sha


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--status", choices=["succeeded", "failed", "partial"], required=True)
    parser.add_argument("--source-watermark")
    parser.add_argument("--ingested-row-count", type=int, default=0)
    parser.add_argument("--table-count", type=int, default=1)
    parser.add_argument("--source-uri")
    parser.add_argument("--error-message")
    parser.add_argument(
        "--table-id",
        default=None,
        help="Defaults to GOOGLE_PROJECT_ID.DBT_DATASET.source_ingestion_runs",
    )
    parser.add_argument("--policy-path", default="vertex/config/source_monitoring.yaml")
    args = parser.parse_args()

    policies = load_source_monitoring_config(args.policy_path)
    if args.source not in policies:
        raise ValueError(f"unknown monitored source {args.source!r}")
    project = os.getenv("GOOGLE_PROJECT_ID")
    if not project and not args.table_id:
        raise ValueError("GOOGLE_PROJECT_ID is required when --table-id is not provided")
    dataset = os.getenv("DBT_DATASET", "favorita")
    table_id = args.table_id or f"{project}.{dataset}.source_ingestion_runs"
    now = datetime.now(timezone.utc)
    row = build_source_ingestion_row(
        policy=policies[args.source],
        status=args.status,
        started_at=now,
        finished_at=now,
        source_watermark=args.source_watermark,
        ingested_row_count=args.ingested_row_count,
        table_count=args.table_count,
        source_uri=args.source_uri,
        code_sha=get_git_sha(),
        error_message=args.error_message,
    )
    inserted = persist_source_ingestion_row(row, table_id=table_id, project_id=project)
    print({"ingestion_run_id": row["ingestion_run_id"], "inserted": inserted})


if __name__ == "__main__":
    main()
