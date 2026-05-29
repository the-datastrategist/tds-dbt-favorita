"""Runtime context for Vertex jobs (git, image, pipeline ids)."""

from __future__ import annotations

import os
import subprocess
from typing import Optional


def get_git_sha() -> Optional[str]:
    for key in ("GIT_SHA", "GITHUB_SHA", "COMMIT_SHA"):
        value = os.getenv(key)
        if value:
            return value[:40]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()[:40]
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def get_container_image() -> Optional[str]:
    return os.getenv("VERTEX_TRAINING_IMAGE") or os.getenv("TRAINING_IMAGE_URI")


def get_pipeline_run_id() -> Optional[str]:
    return (
        os.getenv("VERTEX_PIPELINE_JOB_ID")
        or os.getenv("CLOUD_ML_JOB_ID")
        or os.getenv("AIP_PIPELINE_JOB_ID")
    )


def job_run_id_from_env() -> Optional[str]:
    return os.getenv("VERTEX_JOB_RUN_ID")
