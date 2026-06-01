"""
Container entrypoint: load config, track job run, dispatch to model registry.

  python -m vertex.jobs.run --config-name favorita_xgboost_train
"""

from __future__ import annotations

import argparse
import copy
import logging
import sys
from pathlib import Path
from typing import Any

from vertex.config.load_config import (
    DEFAULT_CONFIG_PATH,
    apply_job_step,
    get_job_spec,
    load_model_config,
    validate_config_for_step,
)
from vertex.models.registry import ensure_registered, run_registered
from vertex.utils.experiment_tracking import ExperimentRunContext
from vertex.utils.tracking import finish_job_run, start_job_run

logger = logging.getLogger(__name__)


def run_job_config(config: dict[str, Any]) -> dict[str, Any]:
    """
    Execute a fully prepared config dict (used by backfill and future Prefect flows).

    Caller must set job.step (via apply_job_step) before calling.
    """
    config = copy.deepcopy(config)
    if not (config.get("job") or {}).get("step"):
        config = apply_job_step(config, "train")
    validate_config_for_step(config)
    ensure_registered()

    spec = get_job_spec(config)
    logger.info(
        "Running config=%s step=%s model_type=%s family=%s",
        spec["config_name"],
        spec["step"],
        spec["model_type"],
        spec.get("model_family"),
    )

    job_run_id, started_at = start_job_run(config)
    with ExperimentRunContext(config, job_run_id=job_run_id) as experiment:
        try:
            result = run_registered(config)
            if not isinstance(result, dict):
                raise TypeError(f"Expected dict result from runner, got {type(result).__name__}")
            experiment.log_success(result)
            finish_job_run(
                config,
                job_run_id,
                started_at=started_at,
                status="SUCCEEDED",
                result=result,
                extra_fields=experiment.job_run_fields(),
            )
            return result
        except Exception as exc:
            experiment.log_failure(str(exc))
            finish_job_run(
                config,
                job_run_id,
                started_at=started_at,
                status="FAILED",
                error_message=str(exc),
                extra_fields=experiment.job_run_fields(),
            )
            raise


def run_job(
    config_name: str,
    config_path: str | Path | None = None,
    *,
    step_override: str | None = None,
) -> dict[str, Any]:
    config = load_model_config(config_name, config_path)
    if step_override:
        config = apply_job_step(config, step_override)
    return run_job_config(config)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Run a Vertex model job from YAML config")
    parser.add_argument(
        "--config-path",
        "-f",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to model_config.yaml",
    )
    parser.add_argument(
        "--config-name",
        "-c",
        required=True,
        help="Named config block in the YAML file",
    )
    parser.add_argument(
        "--step",
        default=None,
        help="Optional override for job.step (train|predict|optimize)",
    )
    args = parser.parse_args()

    try:
        run_job(
            config_name=args.config_name,
            config_path=args.config_path,
            step_override=args.step,
        )
    except Exception:
        logger.exception("Job failed for config %s", args.config_name)
        sys.exit(1)


if __name__ == "__main__":
    main()
