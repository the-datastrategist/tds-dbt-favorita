"""Compile KFP pipeline definitions to JSON for Vertex PipelineJob submission."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from kfp import compiler

from vertex.config.load_config import DEFAULT_CONFIG_PATH, load_model_config
from vertex.config.pipelines import (
    load_pipeline_definitions,
    resolve_pipeline_step_configs,
)
from vertex.jobs.gcp import resolve_gcp_settings
from vertex.pipelines.favorita_ml_pipeline import create_favorita_ml_pipeline

logger = logging.getLogger(__name__)

COMPILED_DIR = Path(__file__).resolve().parent / "compiled"
DEFAULT_TRAINING_IMAGE = (
    "us-central1-docker.pkg.dev/example-project/vertex/tds-favorita:latest"
)


def _resolve_training_image(
    pipeline_name: str,
    config_path: Path,
    step_configs: dict[str, str],
) -> str:
    pipelines = load_pipeline_definitions(config_path)
    train_config = load_model_config(step_configs["train"], config_path)
    merged = dict(train_config)
    merged["vertex"] = {
        **(train_config.get("vertex") or {}),
        **(pipelines[pipeline_name].get("vertex") or {}),
    }
    settings = resolve_gcp_settings(merged)
    return (
        settings.training_image
        or os.getenv("VERTEX_TRAINING_IMAGE")
        or DEFAULT_TRAINING_IMAGE
    )


def compile_favorita_pipeline(
    pipeline_name: str,
    *,
    config_path: Path | None = None,
    output_path: Path | None = None,
    training_image: str | None = None,
    run_optimize: bool = True,
    run_predict: bool = True,
) -> Path:
    """Compile favorita_ml_pipeline to JSON; returns output file path."""
    config_path = config_path or DEFAULT_CONFIG_PATH
    step_configs = resolve_pipeline_step_configs(pipeline_name, config_path)
    pipelines = load_pipeline_definitions(config_path)
    declared_steps = list(pipelines[pipeline_name].get("steps") or ["train"])

    steps: list[str] = []
    for step in ("optimize", "train", "predict"):
        if step not in declared_steps:
            continue
        if step == "optimize" and not run_optimize:
            continue
        if step == "predict" and not run_predict:
            continue
        steps.append(step)

    image = training_image or _resolve_training_image(
        pipeline_name, config_path, step_configs
    )
    pipeline_func = create_favorita_ml_pipeline(image, steps=steps)

    output_path = output_path or (COMPILED_DIR / f"{pipeline_name}.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    compiler.Compiler().compile(
        pipeline_func=pipeline_func,
        package_path=str(output_path),
    )
    logger.info(
        "Compiled pipeline %s -> %s (image=%s, steps=%s)",
        pipeline_name,
        output_path,
        image,
        steps,
    )
    return output_path


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Compile Vertex KFP pipeline JSON")
    parser.add_argument(
        "--pipeline",
        "-p",
        required=True,
        help="Pipeline name from model_config.yaml pipelines: block",
    )
    parser.add_argument(
        "--config-path",
        "-f",
        default=str(DEFAULT_CONFIG_PATH),
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Output JSON path (default: vertex/pipelines/compiled/<pipeline>.json)",
    )
    parser.add_argument(
        "--training-image",
        default=None,
        help="Override VERTEX_TRAINING_IMAGE for this compile",
    )
    parser.add_argument("--skip-optimize", action="store_true")
    parser.add_argument("--skip-predict", action="store_true")
    args = parser.parse_args()

    out = compile_favorita_pipeline(
        args.pipeline,
        config_path=Path(args.config_path),
        output_path=Path(args.output) if args.output else None,
        training_image=args.training_image,
        run_optimize=not args.skip_optimize,
        run_predict=not args.skip_predict,
    )
    print(out)


if __name__ == "__main__":
    main()
