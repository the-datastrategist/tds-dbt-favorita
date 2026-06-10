"""
Submit a Vertex AI Custom Job that runs vertex.jobs.run in a training container.

  python -m vertex.jobs.submit --config-name favorita_store_n1d_xgboost
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Optional

from google.cloud import aiplatform

from vertex.config.load_config import (
    DEFAULT_CONFIG_PATH,
    apply_job_step,
    get_job_spec,
    load_model_config,
    validate_config_for_step,
)
from vertex.jobs.gcp import resolve_gcp_settings, standard_labels, worker_pool_spec
from vertex.utils.tracking import start_job_run

logger = logging.getLogger(__name__)


def submit_job(
    config_name: str,
    config_path: str | Path | None = None,
    *,
    step: str | None = None,
    sync: bool = False,
    image_uri: Optional[str] = None,
    update_config: Optional[bool] = None,
) -> aiplatform.CustomJob:
    """
    Submit a Custom Job for the given config and return the job object.

    Requires GOOGLE_PROJECT_ID (or config inputs.project_id), region, and
    VERTEX_AI_STAGING_BUCKET (or vertex.staging_bucket in config).
    """
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    config = load_model_config(config_name, path)
    if step:
        config = apply_job_step(config, step)
    elif not (config.get("job") or {}).get("step"):
        config = apply_job_step(config, "train")
    validate_config_for_step(config)

    settings = resolve_gcp_settings(config, image_uri=image_uri)
    spec = get_job_spec(config)
    labels = standard_labels(config=config, step=spec["step"])

    aiplatform.init(
        project=settings.project_id,
        location=settings.region,
        staging_bucket=settings.staging_bucket,
    )

    job_run_id, _started_at = start_job_run(config)
    display_name = f"{config_name}-{job_run_id[:8]}"

    job = aiplatform.CustomJob(
        display_name=display_name,
        worker_pool_specs=worker_pool_spec(
            settings,
            config_name=config_name,
            config_path=str(path),
            job_run_id=job_run_id,
            step=spec["step"],
            update_config=update_config,
        ),
        staging_bucket=settings.staging_bucket,
        labels=labels,
    )
    logger.info("Submitting Custom Job %s", display_name)
    submit_kwargs: dict = {}
    if settings.service_account:
        submit_kwargs["service_account"] = settings.service_account
    job.submit(**submit_kwargs)
    if sync:
        job.wait()
    return job


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Submit a Vertex AI Custom Job from YAML")
    parser.add_argument("--config-name", "-c", required=True)
    parser.add_argument("--config-path", "-f", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument(
        "--step",
        default=None,
        help="Job step (train|predict|optimize); default train",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Block until the Custom Job completes",
    )
    parser.add_argument("--image-uri", default=None, help="Override training container image")
    update_group = parser.add_mutually_exclusive_group()
    update_group.add_argument(
        "--update-config",
        action="store_true",
        default=None,
        help="After optimize, merge best_params into model_config.yaml (default)",
    )
    update_group.add_argument(
        "--no-update-config",
        action="store_true",
        default=None,
        help="After optimize, do not write best_params to model_config.yaml",
    )
    args = parser.parse_args()

    update_config: Optional[bool] = None
    if args.no_update_config:
        update_config = False
    elif args.update_config:
        update_config = True

    job = submit_job(
        config_name=args.config_name,
        config_path=args.config_path,
        step=args.step,
        sync=args.sync,
        image_uri=args.image_uri,
        update_config=update_config,
    )
    print(f"Submitted: {job.resource_name}")


if __name__ == "__main__":
    main()
