"""Prefect flows for dbt runs."""

from __future__ import annotations

from prefect import flow

from orchestration.tasks.dbt import run_dbt_run


@flow(
    name="prefect-dbt-run",
    description="Run dbt models (equivalent to make dbt-run, excludes tag:bqml).",
    log_prints=True,
)
def prefect_dbt_run_flow(extra_args: str = "") -> None:
    """Execute the standard dbt run pipeline."""
    run_dbt_run(extra_args)
