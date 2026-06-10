"""Pipeline definitions and config name resolution from model_config.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from vertex.config.load_config import (
    get_model_type,
    load_all_configs,
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
        legacy = definition.get("configs") or {}
        if name_or_config in legacy.values():
            return pipeline_name
    config_names = sorted(c for definition in pipelines.values() if (c := definition.get("config")))
    raise ValueError(
        f"Pipeline {name_or_config!r} not found. "
        f"Pipeline keys: {sorted(pipelines.keys())}. "
        f"Model config names: {config_names}"
    )


def find_config_by_family_and_type(
    model_family: str,
    model_type: str,
    config_path: str | Path | None = None,
) -> Optional[str]:
    """Return config name matching model_family and model_type."""
    for config in load_all_configs(config_path):
        if config.get("model_family") != model_family:
            continue
        if get_model_type(config) == model_type:
            return config.get("name")
    return None


def resolve_pipeline_model_config(
    pipeline_name: str,
    config_path: str | Path | None = None,
) -> str:
    """Return the single model config name for a pipeline."""
    pipeline_name = resolve_pipeline_name(pipeline_name, config_path)
    pipelines = load_pipeline_definitions(config_path)
    definition = pipelines[pipeline_name]

    explicit = definition.get("config")
    if explicit:
        return explicit

    # Legacy: configs.train or per-step map
    legacy = definition.get("configs") or {}
    if legacy.get("train"):
        return legacy["train"]

    model_family = definition["model_family"]
    model_type = definition["model_type"]
    name = find_config_by_family_and_type(
        model_family,
        model_type,
        config_path=config_path,
    )
    if not name:
        raise ValueError(
            f"No model config for pipeline={pipeline_name!r} "
            f"(family={model_family!r}, type={model_type!r})"
        )
    return name


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

    # Legacy explicit per-step config names (deprecated)
    explicit = definition.get("configs") or {}
    resolved: dict[str, str] = {}
    for step in steps:
        resolved[step] = explicit.get(step) or model_config
    return resolved


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
