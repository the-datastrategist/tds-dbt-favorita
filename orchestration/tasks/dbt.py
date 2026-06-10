"""dbt tasks (run inside the ml-pipeline container; mirror make dbt-run)."""

from __future__ import annotations

from prefect import task

from orchestration.utils.repo import load_dotenv_into_environ, run_command


@task(name="dbt-run", retries=0, log_prints=True)
def run_dbt_run(extra_args: str = "") -> None:
    """
    Run the same command as ``make dbt-run``.

    Executes ``dbt run`` in the current container (Prefect worker), not nested Docker.
    """
    env = load_dotenv_into_environ()
    dbt_target = env.get("DBT_TARGET", "dev")
    cmd = [
        "dbt",
        "run",
        "--project-dir",
        "dbt",
        "--target",
        dbt_target,
        "--exclude",
        "tag:bqml",
    ]
    if extra_args.strip():
        cmd.extend(extra_args.split())
    run_command(cmd)
