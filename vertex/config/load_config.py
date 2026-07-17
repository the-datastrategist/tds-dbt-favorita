"""Load and validate Vertex model job configs from model_config.yaml."""

from __future__ import annotations

import copy
import os
import re
from pathlib import Path
from typing import Any, cast

import yaml

from vertex.config.feature_availability import load_feature_availability_registry
from vertex.config.forecast_contract import load_forecast_contract
from vertex.utils.data_loading import has_step_data_source

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "model_config.yaml"

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

VALID_STEPS = frozenset({"train", "predict", "optimize"})

# Tree ensembles supported by shap.TreeExplainer; ARIMA/SARIMA are not tree models
# and do not have a supported explain path.
SHAP_SUPPORTED_MODEL_TYPES = frozenset({"xgboost", "xgboost_sklearn", "random_forest"})
DEFAULT_EXPLAIN_TOP_K_FEATURES = 20


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
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
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
    return cast(dict[str, Any], _resolve_env_strings(_load_yaml_file(path)))


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


def config_include_in_run(config: dict[str, Any]) -> bool:
    """True when a config block explicitly sets include_in_run: true."""
    return config.get("include_in_run") is True


def get_model_type(config: dict[str, Any]) -> str | None:
    """Return model_type from config top level, job block, or inputs."""
    job = config.get("job") or {}
    inputs = config.get("inputs") or {}
    return config.get("model_type") or job.get("model_type") or inputs.get("model_type")


def get_explain_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return the `explain` block for a model config, or {} when absent."""
    return config.get("explain") or {}


def explain_enabled(config: dict[str, Any]) -> bool:
    """True when config.explain.enabled is set (SHAP feature attributions on predict)."""
    return bool(get_explain_config(config).get("enabled"))


def explain_top_k_features(config: dict[str, Any]) -> int:
    """Number of top SHAP feature attributions to keep per prediction row."""
    return int(get_explain_config(config).get("top_k_features", DEFAULT_EXPLAIN_TOP_K_FEATURES))


def apply_job_step(config: dict[str, Any], step: str) -> dict[str, Any]:
    """
    Return a copy of config with job.step (and job.model_type) set for dispatch.

    Unified model configs define model_type once; the step is chosen at runtime
    (CLI --step, Makefile VERTEX_STEP, or KFP pipeline container args).
    """
    if step not in VALID_STEPS:
        raise ValueError(f"step must be one of {sorted(VALID_STEPS)}, got {step!r}")
    out = copy.deepcopy(config)
    model_type = get_model_type(out)
    if not model_type:
        raise ValueError(f"{out.get('name')}: model_type required on config, job, or inputs")
    out["job"] = {
        **(out.get("job") or {}),
        "step": step,
        "model_type": model_type,
    }
    return out


def list_run_config_names(
    config_path: str | Path | None = None,
) -> list[str]:
    """Return sorted model config names with include_in_run: true."""
    names: list[str] = []
    for config in load_all_configs(config_path):
        if not config_include_in_run(config):
            continue
        names.append(config.get("name", ""))
    return sorted(names)


def load_model_config(
    config_name: str,
    config_path: str | Path | None = None,
    *,
    step: str | None = None,
) -> dict[str, Any]:
    """Load a named config block with defaults merged; optionally set job.step."""
    for config in load_all_configs(config_path):
        if config.get("name") == config_name:
            if step:
                return apply_job_step(config, step)
            return config
    raise ValueError(f"Config with name {config_name!r} not found")


def get_job_spec(config: dict[str, Any]) -> dict[str, Any]:
    """
    Return normalized job routing fields: step, model_type, model_family.

    Step must be set on config.job.step via apply_job_step.
    """
    job = config.get("job") or {}
    step = job.get("step")
    model_type = get_model_type(config)
    if not step or not model_type:
        raise ValueError(
            f"{config.get('name')}: job.step is required "
            "(pass --step train|predict|optimize or use apply_job_step)"
        )
    return {
        "step": step,
        "model_type": model_type,
        "model_family": config.get("model_family"),
        "config_name": config.get("name"),
    }


def validate_config_for_step(
    config: dict[str, Any],
    *,
    step: str | None = None,
) -> None:
    """Raise ValueError when required keys for the job step are missing."""
    if step:
        config = apply_job_step(config, step)
    spec = get_job_spec(config)
    step = spec["step"]
    inputs = config.get("inputs") or {}
    outputs = config.get("outputs") or {}
    config_name = spec["config_name"]
    _validate_forecast_feature_contract(config)

    if step in ("train", "optimize"):
        if not has_step_data_source(inputs, step):
            raise ValueError(
                f"{config_name}: train/optimize inputs need train_sql_query, "
                "sql_file, or source_table"
            )
        if not inputs.get("target_column"):
            raise ValueError(f"{config_name}: inputs.target_column required")

    if step == "train":
        if not inputs.get("gcs_model_path"):
            raise ValueError(f"{config_name}: inputs.gcs_model_path required")
        if not outputs.get("metadata_table"):
            raise ValueError(f"{config_name}: outputs.metadata_table required")

    if step == "predict":
        if not has_step_data_source(inputs, "predict"):
            raise ValueError(
                f"{config_name}: predict inputs need predict_sql_query, "
                "sql_file, or source_table"
            )
        if not outputs.get("prediction_table"):
            raise ValueError(f"{config_name}: outputs.prediction_table required")
        if not inputs.get("artifact_config_name") and not inputs.get("model_run_id"):
            # Unified configs default artifact lookup to the same config name.
            pass
        if explain_enabled(config):
            explain_model_type = get_model_type(config)
            if explain_model_type not in SHAP_SUPPORTED_MODEL_TYPES:
                raise ValueError(
                    f"{config_name}: explain.enabled requires model_type in "
                    f"{sorted(SHAP_SUPPORTED_MODEL_TYPES)}, got {explain_model_type!r}"
                )
            if not outputs.get("explain_table"):
                raise ValueError(
                    f"{config_name}: outputs.explain_table required when explain.enabled"
                )

    if step == "optimize":
        if not outputs.get("optimize_table"):
            raise ValueError(f"{config_name}: outputs.optimize_table required")
        trial_count = inputs.get("trial_count")
        if trial_count is None or int(trial_count) < 1:
            raise ValueError(f"{config_name}: inputs.trial_count must be >= 1")


def _validate_forecast_feature_contract(config: dict[str, Any]) -> None:
    """Validate forecast contract feature declarations when forecast outputs are configured."""
    outputs = config.get("outputs") or {}
    inputs = config.get("inputs") or {}
    contract_path = (
        outputs.get("forecast_contract_path")
        or config.get("forecast_contract_path")
        or inputs.get("forecast_contract_path")
    )
    if not contract_path and not outputs.get("forecast_output_table"):
        return
    contract = load_forecast_contract(contract_path)
    registry_path = (
        inputs.get("feature_availability_path")
        or outputs.get("feature_availability_path")
        or config.get("feature_availability_path")
    )
    registry = load_feature_availability_registry(registry_path)
    registry.validate_forecast_contract(contract.spec)


def validate_config_all_steps(config: dict[str, Any]) -> None:
    """Validate train, predict, and optimize requirements for a unified model config."""
    validate_config_for_step(config, step="train")
    validate_config_for_step(config, step="predict")
    inputs = config.get("inputs") or {}
    if inputs.get("trial_count") is not None:
        validate_config_for_step(config, step="optimize")
