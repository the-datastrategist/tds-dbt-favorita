"""Pipeline definitions and config name resolution from model_config.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from vertex.config.load_config import (
    get_job_spec,
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


def find_config_by_family_and_step(
    model_family: str,
    model_type: str,
    step: str,
    config_path: str | Path | None = None,
) -> Optional[str]:
    """Return config name matching model_family, model_type, and job step."""
    for config in load_all_configs(config_path):
        if config.get("model_family") != model_family:
            continue
        spec = get_job_spec(config)
        if spec["model_type"] == model_type and spec["step"] == step:
            return spec["config_name"]
    return None


def resolve_pipeline_step_configs(
    pipeline_name: str,
    config_path: str | Path | None = None,
) -> dict[str, str]:
    """
    Resolve optimize/train/predict config names for a named pipeline.

    Uses explicit `configs` in the pipeline definition, or discovers configs
  by model_family + model_type + step.
    """
    pipelines = load_pipeline_definitions(config_path)
    if pipeline_name not in pipelines:
        raise ValueError(
            f"Pipeline {pipeline_name!r} not found. "
            f"Available: {sorted(pipelines.keys())}"
        )
    definition = pipelines[pipeline_name]
    model_family = definition["model_family"]
    model_type = definition["model_type"]
    steps = list(definition.get("steps") or ["optimize", "train", "predict"])
    explicit = definition.get("configs") or {}

    resolved: dict[str, str] = {}
    for step in steps:
        if step in explicit:
            resolved[step] = explicit[step]
            continue
        name = find_config_by_family_and_step(
            model_family,
            model_type,
            step,
            config_path=config_path,
        )
        if not name:
            raise ValueError(
                f"No config for pipeline={pipeline_name!r} step={step!r} "
                f"(family={model_family!r}, type={model_type!r})"
            )
        resolved[step] = name
    return resolved


def load_pipeline_vertex_config(
    pipeline_name: str,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Merge vertex: settings from first step config with pipeline-level overrides."""
    pipelines = load_pipeline_definitions(config_path)
    definition = pipelines[pipeline_name]
    step_configs = resolve_pipeline_step_configs(pipeline_name, config_path)
    # Prefer train config as template for project/region/buckets
    base_name = step_configs.get("train") or next(iter(step_configs.values()))
    base = load_model_config(base_name, config_path)
    vertex_cfg = dict(base.get("vertex") or {})
    vertex_cfg.update(definition.get("vertex") or {})
    return vertex_cfg
