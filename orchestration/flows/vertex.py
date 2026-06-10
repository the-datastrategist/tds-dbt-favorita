"""Prefect flows for Vertex model training."""

from __future__ import annotations

import os

from prefect import flow

from orchestration.tasks.vertex import run_vertex_train_batch
from orchestration.utils.configs import resolve_train_config_names


def _default_vertex_mode() -> str:
    return os.environ.get("PREFECT_DEFAULT_VERTEX_MODE", "docker")


@flow(
    name="prefect-vertex-train-model",
    description=(
        "Train one or all Vertex configs from vertex/config/model_config.yaml "
        "(equivalent to make vertex-train)."
    ),
    log_prints=True,
)
def prefect_vertex_train_model_flow(
    config_name: str | None = None,
    train_all: bool = False,
    vertex_mode: str | None = None,
    sync: bool = False,
) -> list[str]:
    """
    Train model(s) from model_config.yaml.

    Parameters
    ----------
    config_name:
        Named train config (e.g. favorita_store_n1d_xgboost). Required unless train_all.
    train_all:
        When true, run every config with include_in_run: true and job.step == train.
    vertex_mode:
        docker | vertex (default from PREFECT_DEFAULT_VERTEX_MODE or docker).
    sync:
        When vertex_mode=vertex, block until all Custom Jobs finish (make SYNC=1).
    """
    mode = (vertex_mode or _default_vertex_mode()).lower()
    names = resolve_train_config_names(config_name, train_all=train_all)

    run_vertex_train_batch(names, vertex_mode=mode, sync=sync)

    return names
