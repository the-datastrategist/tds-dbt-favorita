"""Load and validate Vertex model job configs from model_config.yaml."""

from __future__ import annotations

import copy
import os
import re
from pathlib import Path
from typing import Any, Optional

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "model_config.yaml"

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _resolve_env_strings(value: Any) -> Any:
    """Replace ${ENV_VAR} placeholders when the variable is set."""
    if isinstance(value, str):

        def repl(match: re.Match[str]) -> str:
            key = match.group(1)
            return os.environ.get(key, match.group(0))

        return _ENV_PATTERN.sub(repl, value)
    if isinstance(value, list):
        return [_resolve_env_strings(item) for item in value]
    if isinstance(value, dict):
        return {key: _resolve_env_strings(item) for key, item in value.items()}
    return value


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _load_yaml_file(config_path: Path) -> dict[str, Any]:
    if not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with config_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping at root of {config_path}")
    return data


def load_raw_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load full YAML document (defaults, configs, pipelines) with env substitution."""
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    return _resolve_env_strings(_load_yaml_file(path))


def load_all_configs(config_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Return all config blocks with defaults merged."""
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    raw = _resolve_env_strings(_load_yaml_file(path))
    defaults = raw.get("defaults") or {}
    configs = raw.get("configs") or []
    if not configs:
        raise ValueError(f"No configs found in {path}")
    return [_merge_config_defaults(defaults, cfg) for cfg in configs]


def _merge_config_defaults(
    defaults: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    merged = _deep_merge(defaults, config)
    # Promote top-level defaults into inputs/outputs when not set on the block.
    for key in ("project_id", "region"):
        if key in defaults and key not in merged.get("inputs", {}):
            merged.setdefault("inputs", {})[key] = defaults[key]
    if "outputs" in defaults:
        merged.setdefault("outputs", {})
        merged["outputs"] = _deep_merge(defaults["outputs"], merged.get("outputs", {}))
    return merged


def load_model_config(
    config_name: str,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Load a named config block with defaults merged."""
    for config in load_all_configs(config_path):
        if config.get("name") == config_name:
            return config
    raise ValueError(f"Config with name {config_name!r} not found")


def get_job_spec(config: dict[str, Any]) -> dict[str, Any]:
    """
    Return normalized job routing fields: step, model_type, model_family.

    Supports legacy configs that only set inputs.model_type.
    """
    job = config.get("job") or {}
    inputs = config.get("inputs") or {}
    step = job.get("step")
    if not step:
        name = config.get("name", "")
        if "_train" in name or name.startswith("train_"):
            step = "train"
        elif "_predict" in name or name.startswith("predict_"):
            step = "predict"
        elif "_optimize" in name or name.startswith("optimize_"):
            step = "optimize"
    model_type = job.get("model_type") or inputs.get("model_type")
    if not step or not model_type:
        raise ValueError(
            "Config must define job.step and job.model_type "
            "(or legacy inputs.model_type with a recognizable config name)."
        )
    return {
        "step": step,
        "model_type": model_type,
        "model_family": config.get("model_family"),
        "config_name": config.get("name"),
    }


def validate_config_for_step(config: dict[str, Any]) -> None:
    """Raise ValueError when required keys for the job step are missing."""
    spec = get_job_spec(config)
    step = spec["step"]
    inputs = config.get("inputs") or {}
    outputs = config.get("outputs") or {}

    if step in ("train", "optimize"):
        if not (
            inputs.get("sql_query")
            or inputs.get("sql_file")
            or inputs.get("source_table")
        ):
            raise ValueError(f"{spec['config_name']}: inputs.sql_query (or file/table) required")
        if not inputs.get("target_column"):
            raise ValueError(f"{spec['config_name']}: inputs.target_column required")

    if step == "train":
        if not inputs.get("gcs_model_path"):
            raise ValueError(f"{spec['config_name']}: inputs.gcs_model_path required")
        if not outputs.get("metadata_table"):
            raise ValueError(f"{spec['config_name']}: outputs.metadata_table required")

    if step == "predict":
        if not (
            inputs.get("sql_query")
            or inputs.get("sql_file")
            or inputs.get("source_table")
        ):
            raise ValueError(f"{spec['config_name']}: predict inputs need sql_query/file/table")
        if not outputs.get("prediction_table"):
            raise ValueError(f"{spec['config_name']}: outputs.prediction_table required")
        if not inputs.get("artifact_config_name") and not inputs.get("model_run_id"):
            raise ValueError(
                f"{spec['config_name']}: set inputs.artifact_config_name or "
                "inputs.model_run_id to resolve training artifacts"
            )

    if step == "optimize":
        if not outputs.get("optimize_table"):
            raise ValueError(f"{spec['config_name']}: outputs.optimize_table required")
        trial_count = inputs.get("trial_count")
        if trial_count is None or int(trial_count) < 1:
            raise ValueError(f"{spec['config_name']}: inputs.trial_count must be >= 1")
