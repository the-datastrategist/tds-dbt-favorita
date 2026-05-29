"""
Run multiple model configs concurrently.

  python -m vertex.jobs.run_batch --step train
  python -m vertex.jobs.run_batch --config-name favorita_xgboost_train
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from vertex.config.load_config import DEFAULT_CONFIG_PATH, list_run_config_names
from vertex.jobs.submit import submit_job

logger = logging.getLogger(__name__)

VALID_VERTEX_MODES = frozenset({"docker", "vertex"})


def resolve_batch_config_names(
    config_name: str | None,
    *,
    step: str | None = "train",
    config_path: str | Path | None = None,
) -> list[str]:
    """Resolve one explicit config or all include_in_run configs for the step."""
    if config_name:
        return [config_name]
    names = list_run_config_names(config_path, step=step)
    if not names:
        raise ValueError(
            f"No configs with include_in_run: true found for step={step!r}. "
            "Set include_in_run: true on configs in model_config.yaml or pass --config-name."
        )
    return names


def run_configs(
    config_names: list[str],
    config_path: str | Path | None = None,
    *,
    vertex_mode: str = "docker",
    sync: bool = False,
    max_workers: int | None = None,
) -> None:
    """Run or submit each config concurrently."""
    if not config_names:
        raise ValueError("config_names must not be empty")

    mode = vertex_mode.lower()
    if mode not in VALID_VERTEX_MODES:
        raise ValueError(
            f"vertex_mode must be one of {sorted(VALID_VERTEX_MODES)}, got {mode!r}"
        )

    path = str(config_path or DEFAULT_CONFIG_PATH)
    workers = max_workers or len(config_names)
    logger.info(
        "Running %d config(s) asynchronously (mode=%s, sync=%s): %s",
        len(config_names),
        mode,
        sync,
        ", ".join(config_names),
    )

    if mode == "vertex":
        _run_vertex_batch(config_names, path, sync=sync, max_workers=workers)
        return

    _run_docker_batch(config_names, path, max_workers=workers)


def _run_docker_batch(
    config_names: list[str],
    config_path: str,
    *,
    max_workers: int,
) -> None:
    failed: list[str] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                subprocess.run,
                [
                    sys.executable,
                    "-m",
                    "vertex.jobs.run",
                    "--config-path",
                    config_path,
                    "--config-name",
                    name,
                ],
                check=False,
            ): name
            for name in config_names
        }
        for future in as_completed(futures):
            name = futures[future]
            result = future.result()
            if result.returncode == 0:
                logger.info("Completed config %s", name)
            else:
                logger.error(
                    "Config %s failed with exit code %s",
                    name,
                    result.returncode,
                )
                failed.append(name)

    if failed:
        raise RuntimeError(
            f"Batch run failed for {len(failed)} config(s): {', '.join(sorted(failed))}"
        )


def _run_vertex_batch(
    config_names: list[str],
    config_path: str,
    *,
    sync: bool,
    max_workers: int,
) -> None:
    submitted: list[tuple[str, object]] = []
    failed: list[str] = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                submit_job,
                name,
                config_path,
                sync=False,
            ): name
            for name in config_names
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                job = future.result()
                submitted.append((name, job))
                logger.info("Submitted config %s: %s", name, job.resource_name)
            except Exception:
                logger.exception("Failed to submit config %s", name)
                failed.append(name)

    if failed:
        raise RuntimeError(
            f"Batch submit failed for {len(failed)} config(s): {', '.join(sorted(failed))}"
        )

    if sync:
        for name, job in submitted:
            logger.info("Waiting for config %s", name)
            job.wait()
            logger.info("Completed config %s", name)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Run multiple Vertex model jobs from YAML (async batch)"
    )
    parser.add_argument(
        "--config-path",
        "-f",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to model_config.yaml",
    )
    parser.add_argument(
        "--config-name",
        "-c",
        default=None,
        help="Run a single named config (default: all with include_in_run: true)",
    )
    parser.add_argument(
        "--step",
        default="train",
        help="Job step when selecting include_in_run configs (train|predict|optimize)",
    )
    parser.add_argument(
        "--vertex-mode",
        choices=sorted(VALID_VERTEX_MODES),
        default="docker",
        help="docker: run locally in parallel; vertex: submit Custom Jobs in parallel",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="When vertex-mode=vertex, wait for all submitted jobs to finish",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=None,
        help="Max concurrent jobs (default: number of configs)",
    )
    args = parser.parse_args()

    try:
        names = resolve_batch_config_names(
            args.config_name,
            step=args.step,
            config_path=args.config_path,
        )
        run_configs(
            names,
            args.config_path,
            vertex_mode=args.vertex_mode,
            sync=args.sync,
            max_workers=args.max_workers,
        )
    except Exception:
        logger.exception("Batch run failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
