"""Validate every named block in model_config.yaml."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from vertex.config.load_config import (
    DEFAULT_CONFIG_PATH,
    load_all_configs,
    load_raw_config,
    validate_config_for_step,
)
from vertex.config.pipelines import (
    load_pipeline_definitions,
    resolve_pipeline_step_configs,
)


def validate_all_configs(config_path: Path | None = None) -> list[str]:
    """Return list of config names validated successfully."""
    path = config_path or DEFAULT_CONFIG_PATH
    validated: list[str] = []

    for config in load_all_configs(path):
        validate_config_for_step(config)
        validated.append(config["name"])

    raw = load_raw_config(path)
    pipelines = raw.get("pipelines") or {}
    if pipelines:
        load_pipeline_definitions(path)
        for pipeline_name in pipelines:
            resolve_pipeline_step_configs(pipeline_name, path)

    return validated


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate model_config.yaml")
    parser.add_argument(
        "--config-path",
        "-f",
        default=str(DEFAULT_CONFIG_PATH),
    )
    args = parser.parse_args()
    try:
        names = validate_all_configs(Path(args.config_path))
    except Exception as exc:
        print(f"Config validation failed: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"Validated {len(names)} configs and pipelines OK.")
    for name in names:
        print(f"  - {name}")


if __name__ == "__main__":
    main()
