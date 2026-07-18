"""Pipeline definitions and config name resolution from model_config.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vertex.config.load_config import (
    load_model_config,
    load_raw_config,
)


def load_pipeline_definitions(
    config_path: str | Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Return pipeline name -> definition from model_config.yaml."""
    raw = load_raw_config(config_path)
    pipelines = raw.get("pipelines") or {}
    if not isinstance(pipelines, dict):
        raise ValueError(f"pipelines must be a mapping in {config_path}")
    return pipelines


def resolve_pipeline_name(
    name_or_config: str,
    config_path: str | Path | None = None,
) -> str:
    """
    Return the pipeline key from a pipeline name or linked model config name.

    Accepts either the key under ``pipelines:`` (e.g. ``favorita_random_forest``)
    or the unified model config it references (e.g. ``favorita_store_n1d_rf``).
    """
    pipelines = load_pipeline_definitions(config_path)
    if name_or_config in pipelines:
        return name_or_config
    for pipeline_name, definition in pipelines.items():
        if definition.get("config") == name_or_config:
            return pipeline_name
    config_names = sorted(c for definition in pipelines.values() if (c := definition.get("config")))
    raise ValueError(
        f"Pipeline {name_or_config!r} not found. "
        f"Pipeline keys: {sorted(pipelines.keys())}. "
        f"Model config names: {config_names}"
    )


def resolve_pipeline_model_config(
    pipeline_name: str,
    config_path: str | Path | None = None,
) -> str:
    """Return the single model config name for a pipeline."""
    pipeline_name = resolve_pipeline_name(pipeline_name, config_path)
    pipelines = load_pipeline_definitions(config_path)
    definition = pipelines[pipeline_name]

    model_config = definition.get("config")
    if not model_config:
        raise ValueError(f"Pipeline {pipeline_name!r} must define config")
    return str(model_config)


def resolve_pipeline_step_configs(
    pipeline_name: str,
    config_path: str | Path | None = None,
) -> dict[str, str]:
    """
    Resolve optimize/train/predict config names for a named pipeline.

    Unified setups use one model config for every step; the job step is set at
    runtime via ``--step``.
    """
    pipeline_name = resolve_pipeline_name(pipeline_name, config_path)
    pipelines = load_pipeline_definitions(config_path)
    definition = pipelines[pipeline_name]
    steps = list(definition.get("steps") or ["optimize", "train", "predict"])
    model_config = resolve_pipeline_model_config(pipeline_name, config_path)

    return {step: model_config for step in steps}


def load_pipeline_vertex_config(
    pipeline_name: str,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Merge vertex: settings from the model config with pipeline-level overrides."""
    pipeline_name = resolve_pipeline_name(pipeline_name, config_path)
    pipelines = load_pipeline_definitions(config_path)
    definition = pipelines[pipeline_name]
    model_config_name = resolve_pipeline_model_config(pipeline_name, config_path)
    base = load_model_config(model_config_name, config_path)
    vertex_cfg = dict(base.get("vertex") or {})
    vertex_cfg.update(definition.get("vertex") or {})
    return vertex_cfg
