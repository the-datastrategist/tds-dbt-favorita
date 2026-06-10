"""
Prefect flow for Vertex walk-forward backfill.

Register in prefect.yaml when you are ready to deploy; until then use:
  make vertex-backfill START_DATE=... END_DATE=...
"""

from __future__ import annotations

from datetime import date

from prefect import flow

from vertex.jobs.backfill import BackfillIterationResult, run_backfill


@flow(
    name="prefect-vertex-backfill",
    description=(
        "Walk-forward train + predict per anchor date "
        "(same logic as python -m vertex.jobs.backfill)."
    ),
    log_prints=True,
)
def prefect_vertex_backfill_flow(
    config_name: str,
    start_date: str | date,
    end_date: str | date,
    *,
    interval_days: int = 1,
    train_days: int | None = None,
    feature_table: str | None = None,
    dry_run: bool = False,
    max_iterations: int | None = None,
    stop_on_error: bool = True,
) -> list[BackfillIterationResult]:
    return run_backfill(
        config_name,
        start_date,
        end_date,
        interval_days=interval_days,
        train_days=train_days,
        feature_table=feature_table,
        dry_run=dry_run,
        max_iterations=max_iterations,
        stop_on_error=stop_on_error,
    )
