#!/usr/bin/env python3
"""Run dbt with project, dataset, and location from a deployment manifest."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

from vertex.config.deployment import load_deployment


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deployment-config", type=Path, required=True)
    parser.add_argument("dbt_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not args.dbt_args or args.dbt_args[0] != "--":
        parser.error("pass a dbt command after --, for example: -- compile --project-dir dbt")
    command = ["dbt", *args.dbt_args[1:]]
    if len(command) == 1:
        parser.error("a dbt subcommand is required after --")
    environment = os.environ.copy()
    environment.update(load_deployment(args.deployment_config).dbt_environment())
    raise SystemExit(subprocess.run(command, env=environment, check=False).returncode)


if __name__ == "__main__":
    main()
