"""Resolve Vertex ML pipelines (optimize → train → predict) for Prefect flows."""

from __future__ import annotations

from pathlib import Path

from vertex.config.load_config import DEFAULT_CONFIG_PATH
from vertex.config.pipelines import (
    load_pipeline_definitions,
    resolve_pipeline_step_configs,
)

STEP_ORDER = ("optimize", "train", "predict")


def list_pipeline_names(config_path: str | Path | None = None) -> list[str]:
    """Return sorted pipeline names from model_config.yaml."""
    return sorted(load_pipeline_definitions(config_path).keys())


def resolve_pipeline_steps(
    pipeline_name: str,
    *,
    config_path: str | Path | None = None,
    skip_optimize: bool = False,
    skip_predict: bool = False,
) -> list[tuple[str, str]]:
    """
    Return ordered (step, config_name) pairs to run for a named pipeline.

    Honors pipeline ``steps`` in YAML and optional skip flags (train-only, etc.).
    """
    pipelines = load_pipeline_definitions(config_path)
    if pipeline_name not in pipelines:
        available = sorted(pipelines.keys())
        raise ValueError(
            f"Pipeline {pipeline_name!r} not found. Available: {available}"
        )

    definition = pipelines[pipeline_name]
    allowed_steps = set(definition.get("steps") or list(STEP_ORDER))
    step_configs = resolve_pipeline_step_configs(pipeline_name, config_path)

    resolved: list[tuple[str, str]] = []
    for step in STEP_ORDER:
        if step not in allowed_steps:
            continue
        if step == "optimize" and skip_optimize:
            continue
        if step == "predict" and skip_predict:
            continue
        if step not in step_configs:
            continue
        resolved.append((step, step_configs[step]))
    return resolved


def resolve_pipeline_config_names(
    pipeline_name: str,
    *,
    config_path: str | Path | None = None,
    skip_optimize: bool = False,
    skip_predict: bool = False,
) -> list[str]:
    """Config names in run order (optimize, train, predict)."""
    return [
        name
        for _, name in resolve_pipeline_steps(
            pipeline_name,
            config_path=config_path,
            skip_optimize=skip_optimize,
            skip_predict=skip_predict,
        )
    ]


def default_config_path() -> Path:
    return DEFAULT_CONFIG_PATH
