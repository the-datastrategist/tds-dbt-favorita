"""Vertex job tasks (run inside the ml-pipeline container; mirror Makefile targets)."""

from __future__ import annotations

from prefect import task

from orchestration.utils.repo import run_command
from vertex.config.load_config import DEFAULT_CONFIG_PATH

VALID_VERTEX_MODES = frozenset({"docker", "vertex"})
_VERTEX_CONFIG = str(DEFAULT_CONFIG_PATH)


def _validate_vertex_mode(vertex_mode: str) -> str:
    mode = vertex_mode.lower()
    if mode not in VALID_VERTEX_MODES:
        raise ValueError(
            f"vertex_mode must be one of {sorted(VALID_VERTEX_MODES)}, got {mode!r}"
        )
    return mode


@task(name="vertex-run-config", retries=0, log_prints=True)
def run_vertex_job_config(
    config_name: str,
    *,
    vertex_mode: str = "docker",
    sync: bool = False,
) -> None:
    """
    Run one Vertex config (train, predict, or optimize).

    Equivalent to ``make vertex-run-docker`` or ``make vertex-submit`` on the host.
    Executes in the current container (Prefect worker), not nested Docker.
    """
    mode = _validate_vertex_mode(vertex_mode)

    if mode == "vertex":
        cmd = [
            "python",
            "-m",
            "vertex.jobs.submit",
            "--config-path",
            _VERTEX_CONFIG,
            "--config-name",
            config_name,
        ]
        if sync:
            cmd.append("--sync")
        run_command(cmd)
        return

    run_command(
        [
            "python",
            "-m",
            "vertex.jobs.run",
            "--config-path",
            _VERTEX_CONFIG,
            "--config-name",
            config_name,
        ]
    )


@task(name="vertex-train-config", retries=0, log_prints=True)
def run_vertex_train_config(
    config_name: str,
    *,
    vertex_mode: str = "docker",
    sync: bool = False,
) -> None:
    """Train one model config (alias for run_vertex_job_config)."""
    run_vertex_job_config(config_name, vertex_mode=vertex_mode, sync=sync)


@task(name="vertex-train-batch", retries=0, log_prints=True)
def run_vertex_train_batch(
    config_names: list[str],
    *,
    vertex_mode: str = "docker",
    sync: bool = False,
) -> None:
    """Train multiple model configs concurrently (equivalent to vertex.jobs.run_batch)."""
    from vertex.jobs.run_batch import run_configs

    mode = _validate_vertex_mode(vertex_mode)
    run_configs(config_names, vertex_mode=mode, sync=sync)


@task(name="vertex-pipeline-submit", retries=0, log_prints=True)
def run_vertex_pipeline_submit(
    pipeline_name: str,
    *,
    sync: bool = False,
    skip_optimize: bool = False,
    skip_predict: bool = False,
) -> None:
    """
    Submit a Vertex AI PipelineJob (optimize → train → predict).

    Equivalent to ``make vertex-pipeline-submit`` on the host.
    """
    cmd = [
        "python",
        "-m",
        "vertex.jobs.submit_pipeline",
        "--pipeline",
        pipeline_name,
        "--config-path",
        _VERTEX_CONFIG,
    ]
    if sync:
        cmd.append("--sync")
    if skip_optimize:
        cmd.append("--skip-optimize")
    if skip_predict:
        cmd.append("--skip-predict")
    run_command(cmd)
