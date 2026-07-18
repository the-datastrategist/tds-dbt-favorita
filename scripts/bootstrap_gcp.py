#!/usr/bin/env python3
"""Preflight, adopt, and bootstrap a GCP environment safely.

The command is intentionally idempotent: existing resources are imported,
destructive plans are rejected, and apply requires an explicit flag.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
TF_DIR = ROOT / "terraform" / "environments" / "dev"


@dataclass(frozen=True)
class Resource:
    address: str
    resource_id: str
    exists_command: tuple[str, ...]


def run(command: Sequence[str], *, check: bool = True, capture: bool = False) -> str:
    result = subprocess.run(
        command,
        cwd=TF_DIR,
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if check and result.returncode:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"command failed ({' '.join(command)}): {detail}")
    return (result.stdout or "").strip()


def terraform_vars() -> dict[str, object]:
    command = ["terraform", "console"]
    values: dict[str, object] = {}
    for name in (
        "project_id",
        "region",
        "client_label",
        "caller_member",
        "dbt_dataset",
        "raw_dataset",
        "github_repository",
        "terraform_state_bucket",
    ):
        result = subprocess.run(
            command,
            cwd=TF_DIR,
            input=f"jsonencode(var.{name})\n",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip())
        values[name] = json.loads(json.loads(result.stdout.strip()))
    return values


def preflight() -> dict[str, object]:
    failures: list[str] = []
    for binary in ("terraform", "gcloud", "gh"):
        if not shutil.which(binary):
            failures.append(f"{binary} is not installed")

    credential_override = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if credential_override:
        failures.append(
            "GOOGLE_APPLICATION_CREDENTIALS overrides ADC "
            f"({credential_override}); unset it for human bootstrap"
        )

    if failures:
        raise RuntimeError("\n".join(failures))

    values = terraform_vars()
    project = str(values["project_id"])
    checks = (
        (
            ["gcloud", "projects", "describe", project, "--format=value(projectNumber)"],
            "project access",
        ),
        (
            [
                "gcloud",
                "services",
                "list",
                "--enabled",
                f"--project={project}",
                "--limit=1",
            ],
            "Service Usage access",
        ),
        (
            ["gcloud", "auth", "application-default", "print-access-token"],
            "Application Default Credentials",
        ),
        (["gh", "auth", "status"], "GitHub CLI authentication"),
    )
    for command, label in checks:
        try:
            run(command, capture=True)
            print(f"PASS: {label}")
        except RuntimeError as exc:
            failures.append(f"FAIL: {label}: {exc}")

    bucket = str(values["terraform_state_bucket"])
    if bucket:
        result = subprocess.run(
            ["gcloud", "storage", "buckets", "describe", f"gs://{bucket}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode:
            failures.append(f"FAIL: state bucket gs://{bucket} is missing or inaccessible")
        else:
            print(f"PASS: state bucket gs://{bucket}")

    if failures:
        raise RuntimeError("\n".join(failures))
    return values


def resources(values: dict[str, object]) -> list[Resource]:
    project = str(values["project_id"])
    client = str(values["client_label"])
    region = str(values["region"])
    dbt_dataset = str(values["dbt_dataset"])
    raw_dataset = str(values["raw_dataset"])
    project_number = run(
        ["gcloud", "projects", "describe", project, "--format=value(projectNumber)"],
        capture=True,
    )
    pool = f"projects/{project_number}/locations/global/workloadIdentityPools/github-pool"
    return [
        Resource(
            "module.iam_vertex_sa.google_service_account.vertex_ml",
            f"projects/{project}/serviceAccounts/sa-vertex-ml@{project}.iam.gserviceaccount.com",
            (
                "gcloud",
                "iam",
                "service-accounts",
                "describe",
                f"sa-vertex-ml@{project}.iam.gserviceaccount.com",
                f"--project={project}",
            ),
        ),
        Resource(
            "module.iam_vertex_sa.google_service_account.vertex_prediction",
            (
                f"projects/{project}/serviceAccounts/"
                f"sa-vertex-ml-predict@{project}.iam.gserviceaccount.com"
            ),
            (
                "gcloud",
                "iam",
                "service-accounts",
                "describe",
                f"sa-vertex-ml-predict@{project}.iam.gserviceaccount.com",
                f"--project={project}",
            ),
        ),
        Resource(
            "module.artifact_registry.google_artifact_registry_repository.vertex",
            f"projects/{project}/locations/{region}/repositories/vertex",
            (
                "gcloud",
                "artifacts",
                "repositories",
                "describe",
                "vertex",
                f"--project={project}",
                f"--location={region}",
            ),
        ),
        Resource(
            "module.bigquery_datasets.google_bigquery_dataset.analytics",
            f"projects/{project}/datasets/{dbt_dataset}",
            ("bq", "show", f"--project_id={project}", dbt_dataset),
        ),
        Resource(
            "module.bigquery_datasets.google_bigquery_dataset.raw",
            f"projects/{project}/datasets/{raw_dataset}",
            ("bq", "show", f"--project_id={project}", raw_dataset),
        ),
        *[
            Resource(
                address,
                bucket,
                ("gcloud", "storage", "buckets", "describe", f"gs://{bucket}"),
            )
            for address, bucket in (
                (
                    'module.gcs_buckets.google_storage_bucket.buckets["models"]',
                    f"{client}-vertex-models",
                ),
                ('module.gcs_buckets.google_storage_bucket.buckets["raw"]', f"{client}-raw"),
                (
                    'module.gcs_buckets.google_storage_bucket.buckets["staging"]',
                    f"{client}-vertex-staging",
                ),
                ("module.gcs_buckets.google_storage_bucket.mlflow[0]", f"{client}-mlflow"),
            )
        ],
        Resource(
            "module.github_wif[0].google_iam_workload_identity_pool.github",
            pool,
            (
                "gcloud",
                "iam",
                "workload-identity-pools",
                "describe",
                "github-pool",
                f"--project={project}",
                "--location=global",
            ),
        ),
        Resource(
            "module.github_wif[0].google_iam_workload_identity_pool_provider.github",
            f"{pool}/providers/github-provider",
            (
                "gcloud",
                "iam",
                "workload-identity-pools",
                "providers",
                "describe",
                "github-provider",
                "--workload-identity-pool=github-pool",
                f"--project={project}",
                "--location=global",
            ),
        ),
        Resource(
            "module.github_wif[0].google_service_account.github_terraform",
            (
                f"projects/{project}/serviceAccounts/"
                f"sa-github-terraform@{project}.iam.gserviceaccount.com"
            ),
            (
                "gcloud",
                "iam",
                "service-accounts",
                "describe",
                f"sa-github-terraform@{project}.iam.gserviceaccount.com",
                f"--project={project}",
            ),
        ),
    ]


def adopt(values: dict[str, object]) -> None:
    state = set(run(["terraform", "state", "list"], capture=True).splitlines())
    for resource in resources(values):
        if resource.address in state:
            print(f"MANAGED: {resource.address}")
            continue
        exists = (
            subprocess.run(
                resource.exists_command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            ).returncode
            == 0
        )
        if not exists:
            print(f"CREATE: {resource.address}")
            continue
        print(f"IMPORT: {resource.address}")
        run(["terraform", "import", resource.address, resource.resource_id])


def destructive_changes(document: dict[str, Any]) -> list[str]:
    unsafe: list[str] = []
    for change in document.get("resource_changes", []):
        actions = change.get("change", {}).get("actions", [])
        if "delete" in actions:
            unsafe.append(f"{change['address']}: {actions}")
    return unsafe


def safe_plan() -> Path:
    handle, name = tempfile.mkstemp(prefix="favorita-bootstrap-", suffix=".tfplan")
    os.close(handle)
    plan = Path(name)
    run(["terraform", "plan", "-input=false", f"-out={plan}"])
    document = json.loads(run(["terraform", "show", "-json", str(plan)], capture=True))
    unsafe = destructive_changes(document)
    if unsafe:
        plan.unlink(missing_ok=True)
        raise RuntimeError("refusing destructive plan:\n" + "\n".join(unsafe))
    return plan


def configure_github(values: dict[str, object]) -> None:
    outputs = json.loads(run(["terraform", "output", "-json"], capture=True))
    variables = {
        "GCP_DEV_PROJECT_ID": values["project_id"],
        "GCP_DEV_CLIENT_LABEL": values["client_label"],
        "GCP_DEV_CALLER_MEMBER": values["caller_member"],
        "GCP_DEV_TF_STATE_BUCKET": values["terraform_state_bucket"],
        "GCP_DEV_WIF_PROVIDER": outputs["github_wif_provider"]["value"],
        "GCP_DEV_WIF_SERVICE_ACCOUNT": outputs["github_terraform_service_account"]["value"],
    }
    repository = str(values["github_repository"])
    run(["gh", "api", "--method", "PUT", f"repos/{repository}/environments/dev", "--silent"])
    for name, value in variables.items():
        run(
            [
                "gh",
                "variable",
                "set",
                name,
                "--env",
                "dev",
                "--repo",
                repository,
                "--body",
                str(value),
            ]
        )
        print(f"SET: GitHub dev variable {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "bootstrap"))
    parser.add_argument("--apply", action="store_true", help="apply the reviewed zero-delete plan")
    parser.add_argument(
        "--configure-github",
        action="store_true",
        help="write Terraform outputs to the GitHub dev environment",
    )
    args = parser.parse_args()
    try:
        values = preflight()
        if args.command == "check":
            print("Preflight complete; no changes made.")
            return 0
        adopt(values)
        plan = safe_plan()
        if not args.apply:
            print(f"Safe plan saved at {plan}; rerun with --apply to apply it.")
            return 0
        run(["terraform", "apply", "-input=false", str(plan)])
        if args.configure_github:
            configure_github(values)
        run(["terraform", "plan", "-input=false", "-detailed-exitcode"])
        print("Bootstrap complete: resources adopted, WIF applied, and plan is clean.")
        return 0
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
