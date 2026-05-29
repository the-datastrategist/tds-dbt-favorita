"""
Submit a compiled Vertex AI PipelineJob (optimize → train → predict).

  python -m vertex.jobs.submit_pipeline --pipeline favorita_xgboost
  python -m vertex.jobs.submit_pipeline --pipeline favorita_xgboost --sync
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Optional

from google.cloud import aiplatform

from vertex.config.load_config import DEFAULT_CONFIG_PATH, load_model_config
from vertex.config.pipelines import (
    load_pipeline_definitions,
    resolve_pipeline_step_configs,
)
from vertex.jobs.gcp import resolve_gcp_settings, standard_labels
from vertex.pipelines.compile import compile_favorita_pipeline

logger = logging.getLogger(__name__)


def submit_pipeline(
    pipeline_name: str,
    config_path: str | Path | None = None,
    *,
    template_path: Optional[str | Path] = None,
    sync: bool = False,
    enable_caching: bool = True,
    run_optimize: bool = True,
    run_predict: bool = True,
    compile_first: bool = True,
) -> aiplatform.PipelineJob:
    """
    Submit a Vertex AI PipelineJob using a compiled KFP template.

    GCP best practices:
    - pipeline_root under customer-owned GCS bucket
    - optional dedicated pipeline service account (VERTEX_PIPELINE_SERVICE_ACCOUNT)
    - resource labels for chargeback
    - enable_caching for idempotent steps (disable during active tuning)
    """
    config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    pipelines = load_pipeline_definitions(config_path)
    if pipeline_name not in pipelines:
        raise ValueError(f"Unknown pipeline {pipeline_name!r}")

    step_configs = resolve_pipeline_step_configs(pipeline_name, config_path)
    train_config = load_model_config(step_configs["train"], config_path)
    merged = dict(train_config)
    merged["vertex"] = {
        **(train_config.get("vertex") or {}),
        **(pipelines[pipeline_name].get("vertex") or {}),
    }
    settings = resolve_gcp_settings(merged)

    if compile_first or template_path is None:
        template_path = compile_favorita_pipeline(
            pipeline_name,
            config_path=config_path,
            run_optimize=run_optimize and "optimize" in step_configs,
            run_predict=run_predict and "predict" in step_configs,
        )
    template_path = Path(template_path)

    aiplatform.init(
        project=settings.project_id,
        location=settings.region,
        staging_bucket=settings.staging_bucket,
    )

    parameter_values = {
        "optimize_config": step_configs.get("optimize", ""),
        "train_config": step_configs["train"],
        "predict_config": step_configs.get("predict", ""),
        "config_path": str(config_path),
    }

    labels = standard_labels(config=merged, managed_by="vertex-pipeline")
    labels["pipeline"] = pipeline_name.replace("_", "-")[:63]

    display_name = f"pipeline-{pipeline_name}"
    job = aiplatform.PipelineJob(
        display_name=display_name,
        template_path=str(template_path),
        pipeline_root=settings.pipeline_root,
        parameter_values=parameter_values,
        project=settings.project_id,
        location=settings.region,
        enable_caching=enable_caching,
        labels=labels,
    )

    submit_kwargs: dict = {}
    if settings.service_account:
        submit_kwargs["service_account"] = settings.service_account
    if settings.network:
        submit_kwargs["network"] = settings.network

    logger.info(
        "Submitting PipelineJob %s (root=%s, template=%s)",
        display_name,
        settings.pipeline_root,
        template_path,
    )
    job.submit(**submit_kwargs)
    if sync:
        job.wait()
    return job


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Submit Vertex AI PipelineJob")
    parser.add_argument("--pipeline", "-p", required=True)
    parser.add_argument("--config-path", "-f", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--template", default=None, help="Pre-compiled pipeline JSON")
    parser.add_argument("--sync", action="store_true")
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable Vertex pipeline step caching",
    )
    parser.add_argument("--skip-optimize", action="store_true")
    parser.add_argument("--skip-predict", action="store_true")
    parser.add_argument(
        "--no-compile",
        action="store_true",
        help="Use existing compiled JSON only",
    )
    args = parser.parse_args()

    job = submit_pipeline(
        pipeline_name=args.pipeline,
        config_path=args.config_path,
        template_path=args.template,
        sync=args.sync,
        enable_caching=not args.no_cache,
        run_optimize=not args.skip_optimize,
        run_predict=not args.skip_predict,
        compile_first=not args.no_compile,
    )
    print(f"Submitted: {job.resource_name}")


if __name__ == "__main__":
    main()
