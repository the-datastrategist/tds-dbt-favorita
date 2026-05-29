"""Prefect flow for end-to-end Vertex ML pipelines (optimize → train → predict)."""

from __future__ import annotations

import os

from prefect import flow

from orchestration.tasks.vertex import (
    run_vertex_job_config,
    run_vertex_pipeline_submit,
)
from orchestration.utils.pipelines import resolve_pipeline_config_names


def _default_vertex_mode() -> str:
    return os.environ.get("PREFECT_DEFAULT_VERTEX_MODE", "docker")


@flow(
    name="prefect-vertex-ml-pipeline",
    description=(
        "Run a Vertex ML pipeline from model_config.yaml "
        "(optimize → train → predict), equivalent to make vertex-pipeline-submit "
        "or sequential vertex-run steps."
    ),
    log_prints=True,
)
def prefect_vertex_ml_pipeline_flow(
    pipeline_name: str = "favorita_xgboost",
    vertex_mode: str | None = None,
    sync: bool = False,
    skip_optimize: bool = False,
    skip_predict: bool = False,
) -> list[str]:
    """
    Execute a named ML pipeline (see ``pipelines:`` in model_config.yaml).

    Parameters
    ----------
    pipeline_name:
        e.g. favorita_xgboost, favorita_random_forest, favorita_arima
    vertex_mode:
        docker — run each step in the worker container; vertex — KFP PipelineJob on GCP.
    sync:
        When vertex_mode=vertex, wait for the PipelineJob to finish.
    skip_optimize:
        Omit the optimize step (even if defined on the pipeline).
    skip_predict:
        Omit the predict step.
    """
    mode = (vertex_mode or _default_vertex_mode()).lower()
    config_names = resolve_pipeline_config_names(
        pipeline_name,
        skip_optimize=skip_optimize,
        skip_predict=skip_predict,
    )
    if not config_names:
        raise ValueError(
            f"No steps to run for pipeline {pipeline_name!r} "
            f"(skip_optimize={skip_optimize}, skip_predict={skip_predict})"
        )

    if mode == "vertex":
        run_vertex_pipeline_submit(
            pipeline_name,
            sync=sync,
            skip_optimize=skip_optimize,
            skip_predict=skip_predict,
        )
        return config_names

    for config_name in config_names:
        run_vertex_job_config(config_name, vertex_mode=mode, sync=sync)

    return config_names
