"""Repository root, environment loading, and subprocess execution."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def get_repo_root() -> Path:
    """Return the repository root (parent of orchestration/)."""
    return _REPO_ROOT


def load_dotenv_into_environ(env: dict[str, str] | None = None) -> dict[str, str]:
    """
    Merge variables from .env into a copy of os.environ (same keys as the Makefile).

    Does not override variables already set in the environment.
    """
    merged = dict(os.environ if env is None else env)
    dotenv_path = get_repo_root() / ".env"
    if not dotenv_path.is_file():
        return merged

    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if not key or key in merged:
            continue
        merged[key] = value.strip().strip('"').strip("'")
    return merged


def run_command(
    command: list[str],
    *,
    extra_env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a command from the repository root with .env applied."""
    env = load_dotenv_into_environ()
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        command,
        cwd=get_repo_root(),
        env=env,
        check=check,
        text=True,
        capture_output=False,
    )
