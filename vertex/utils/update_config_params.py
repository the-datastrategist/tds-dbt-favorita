"""Write optimized hyperparameters back to model_config.yaml."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

from ruamel.yaml import YAML

from vertex.config.load_config import DEFAULT_CONFIG_PATH

logger = logging.getLogger(__name__)


def should_update_config_params(config: dict[str, Any]) -> bool:
    """
    Return whether optimize should persist best_params into model_config.yaml.

    Precedence: VERTEX_UPDATE_CONFIG env < inputs.update_config_params (default true).
    """
    env = os.getenv("VERTEX_UPDATE_CONFIG", "").strip().lower()
    if env in ("0", "false", "no"):
        return False
    if env in ("1", "true", "yes"):
        return True
    inputs = config.get("inputs") or {}
    return inputs.get("update_config_params", True) is not False


def resolve_config_path(config_path: str | Path | None = None) -> Path:
    if config_path is not None:
        return Path(config_path)
    env_path = os.getenv("VERTEX_CONFIG_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_CONFIG_PATH


def update_model_config_params(
    config_path: str | Path,
    config_name: str,
    best_params: dict[str, Any],
) -> Path:
    """
    Merge best_params into inputs.model_params for the named config block.

    Uses ruamel.yaml to preserve formatting and comments where possible.
    """
    if not best_params:
        raise ValueError("best_params must be non-empty to update model_config.yaml")

    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)

    with path.open(encoding="utf-8") as handle:
        document = yaml.load(handle)

    if not isinstance(document, dict):
        raise ValueError(f"Expected mapping at root of {path}")

    configs = document.get("configs") or []
    for block in configs:
        if not isinstance(block, dict) or block.get("name") != config_name:
            continue
        inputs = block.setdefault("inputs", {})
        model_params = inputs.setdefault("model_params", {})
        for key, value in best_params.items():
            model_params[key] = value
        with path.open("w", encoding="utf-8") as handle:
            yaml.dump(document, handle)
        logger.info(
            "Updated inputs.model_params for %s in %s (%s keys)",
            config_name,
            path,
            len(best_params),
        )
        return path

    raise ValueError(f"Config with name {config_name!r} not found in {path}")


def maybe_update_model_config_params(
    config: dict[str, Any],
    best_params: dict[str, Any],
    *,
    config_path: str | Path | None = None,
) -> Optional[Path]:
    """Update model_config.yaml when enabled; return path written or None if skipped."""
    if not should_update_config_params(config):
        logger.info(
            "Skipping model_config.yaml update for %s (update_config_params disabled)",
            config.get("name"),
        )
        return None
    if not best_params:
        logger.warning(
            "Skipping model_config.yaml update for %s: no best_params",
            config.get("name"),
        )
        return None

    config_name = config.get("name")
    if not config_name:
        raise ValueError("config.name required to update model_config.yaml")

    path = resolve_config_path(config_path)
    return update_model_config_params(path, config_name, best_params)
