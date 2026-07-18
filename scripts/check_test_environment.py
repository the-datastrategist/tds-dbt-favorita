"""Fail fast with an actionable message when test dependencies are incomplete."""

from __future__ import annotations

import importlib
import sys

REQUIRED_TEST_MODULES = ("pytest", "pytest_cov", "py7zr")


def main() -> int:
    missing = []
    for module in REQUIRED_TEST_MODULES:
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(module)
    if missing:
        print(
            "Missing test dependencies: "
            + ", ".join(missing)
            + ". Install requirements-dev.txt or rebuild the ml-pipeline image.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
