#!/usr/bin/env python3
"""Validate and capture sanitized evidence for a read-only ForecastLab IAP release."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

IMAGE_DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")
PUBLIC_MEMBERS = {"allUsers", "allAuthenticatedUsers"}
PLAN_RESOURCE_PREFIX = "module.forecast_api"


def _run(command: Sequence[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"command failed ({' '.join(command)}): {detail}")
    return result.stdout


def _environment(container: dict[str, Any]) -> dict[str, str]:
    return {
        item["name"]: str(item.get("value", ""))
        for item in container.get("env", [])
        if item.get("name")
    }


def validate_readonly_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Fail closed unless a Terraform plan is an IAP-only, read-only deployment."""
    changes = [
        item
        for item in plan.get("resource_changes", [])
        if item.get("address", "").startswith(PLAN_RESOURCE_PREFIX)
    ]
    if not changes:
        raise ValueError("plan contains no ForecastLab API resources")

    destructive = [
        item["address"] for item in changes if "delete" in item.get("change", {}).get("actions", [])
    ]
    if destructive:
        raise ValueError(f"plan contains destructive ForecastLab changes: {destructive}")

    public_bindings: list[str] = []
    for item in changes:
        after = item.get("change", {}).get("after") or {}
        member = after.get("member")
        members = after.get("members") or []
        if member in PUBLIC_MEMBERS or PUBLIC_MEMBERS.intersection(members):
            public_bindings.append(item["address"])
    if public_bindings:
        raise ValueError(f"plan grants public access: {public_bindings}")

    def resources(resource_type: str) -> list[dict[str, Any]]:
        return [item for item in changes if item.get("type") == resource_type]

    services = resources("google_cloud_run_v2_service")
    if len(services) != 1:
        raise ValueError("plan must contain exactly one ForecastLab Cloud Run service")
    service = services[0].get("change", {}).get("after") or {}
    if service.get("iap_enabled") is not True:
        raise ValueError("Cloud Run IAP must be enabled")
    containers = (service.get("template") or [{}])[0].get("containers") or []
    if len(containers) != 1:
        raise ValueError("ForecastLab must have exactly one application container")
    image = str(containers[0].get("image", ""))
    if not IMAGE_DIGEST.search(image):
        raise ValueError("container image must be pinned by sha256 digest")
    env = _environment(containers[0])
    if env.get("FORECAST_API_MUTATIONS_ENABLED") != "false":
        raise ValueError("lifecycle mutations must be disabled for read-only acceptance")
    if env.get("FORECAST_API_AUTHORIZATION_ENABLED") != "true":
        raise ValueError("API authorization must be enabled with IAP")
    if env.get("FORECAST_API_ROLE_MEMBERS_JSON", "{}") not in ("", "{}"):
        raise ValueError("lifecycle role assignments belong to the mutation activation phase")

    dataset_bindings = resources("google_bigquery_dataset_iam_member")
    roles = {(item.get("change", {}).get("after") or {}).get("role") for item in dataset_bindings}
    if roles != {"roles/bigquery.dataViewer"}:
        raise ValueError("read-only service account must have only BigQuery dataViewer access")

    iap_bindings = resources("google_iap_web_cloud_run_service_iam_member")
    if not iap_bindings:
        raise ValueError("at least one named IAP access member is required")
    iap_members = {
        str((item.get("change", {}).get("after") or {}).get("member", "")) for item in iap_bindings
    }
    if "" in iap_members:
        raise ValueError("IAP access member cannot be empty")

    run_bindings = resources("google_cloud_run_v2_service_iam_member")
    run_members = {
        str((item.get("change", {}).get("after") or {}).get("member", "")) for item in run_bindings
    }
    if not any("gcp-sa-iap.iam.gserviceaccount.com" in value for value in run_members):
        raise ValueError("Google-managed IAP service agent must be a Cloud Run invoker")

    canonical = json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
    return {
        "gate": "forecastlab_readonly_plan",
        "status": "passed",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "plan_sha256": hashlib.sha256(canonical).hexdigest(),
        "image_digest": image.rsplit("@", 1)[1],
        "iap_access_member_count": len(iap_members),
        "mutations_enabled": False,
        "authorization_enabled": True,
        "bigquery_role": "roles/bigquery.dataViewer",
        "public_access_bindings": 0,
    }


def _load_plan(plan_path: Path, terraform_dir: Path | None = None) -> dict[str, Any]:
    if plan_path.suffix == ".json":
        return json.loads(plan_path.read_text())
    return json.loads(
        _run(("terraform", "show", "-json", str(plan_path.resolve())), cwd=terraform_dir)
    )


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


def _request(
    url: str, token: str | None, *, follow_redirects: bool = True
) -> tuple[int, dict[str, str], bytes]:
    headers = {"Accept": "application/json, text/html"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    opener = build_opener() if follow_redirects else build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=30) as response:
            return response.status, dict(response.headers), response.read()
    except HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def _json_probe(base_url: str, path: str, token: str) -> tuple[dict[str, Any], dict[str, Any]]:
    status, headers, body = _request(f"{base_url}{path}", token)
    if status != 200:
        raise RuntimeError(f"{path} returned HTTP {status}")
    payload = json.loads(body)
    return payload, {
        "path": path,
        "status": status,
        "request_id_present": bool(headers.get("X-Request-ID")),
    }


def capture_live_evidence(
    *,
    project: str,
    region: str,
    service_name: str,
    base_url: str,
    iap_client_id: str | None,
    manual_browser: bool = False,
) -> dict[str, Any]:
    """Capture only deployment metadata, response shapes, counts, and request-ID presence."""
    service = json.loads(
        _run(
            (
                "gcloud",
                "run",
                "services",
                "describe",
                service_name,
                f"--project={project}",
                f"--region={region}",
                "--format=json",
            )
        )
    )
    containers = service.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
    if not containers:
        containers = service.get("template", {}).get("containers", [])
    if len(containers) != 1:
        raise RuntimeError("deployed service must have exactly one container")
    image = str(containers[0].get("image", ""))
    env = _environment(containers[0])
    if not IMAGE_DIGEST.search(image):
        raise RuntimeError("deployed image is not pinned by digest")
    if env.get("FORECAST_API_MUTATIONS_ENABLED") != "false":
        raise RuntimeError("deployed service is not read-only")
    if env.get("FORECAST_API_AUTHORIZATION_ENABLED") != "true":
        raise RuntimeError("deployed service does not enforce IAP-backed authorization")

    policy = json.loads(
        _run(
            (
                "gcloud",
                "run",
                "services",
                "get-iam-policy",
                service_name,
                f"--project={project}",
                f"--region={region}",
                "--format=json",
            )
        )
    )
    members = {
        member for binding in policy.get("bindings", []) for member in binding.get("members", [])
    }
    if PUBLIC_MEMBERS.intersection(members):
        raise RuntimeError("deployed Cloud Run service has a public IAM binding")
    if not any("gcp-sa-iap.iam.gserviceaccount.com" in value for value in members):
        raise RuntimeError("deployed Cloud Run policy is missing the IAP service agent")

    iap_policy = json.loads(
        _run(
            (
                "gcloud",
                "iap",
                "web",
                "get-iam-policy",
                "--resource-type=cloud-run",
                f"--service={service_name}",
                f"--region={region}",
                f"--project={project}",
                "--format=json",
            )
        )
    )
    iap_members = {
        member
        for binding in iap_policy.get("bindings", [])
        if binding.get("role") == "roles/iap.httpsResourceAccessor"
        for member in binding.get("members", [])
    }
    if not iap_members:
        raise RuntimeError("deployed IAP policy has no named access member")
    if PUBLIC_MEMBERS.intersection(iap_members):
        raise RuntimeError("deployed IAP policy has a public access binding")

    unauthorized_status, _, _ = _request(base_url, None, follow_redirects=False)
    if unauthorized_status not in (302, 303, 307, 401, 403):
        raise RuntimeError(f"unauthenticated root returned unexpected HTTP {unauthorized_status}")

    probes: list[dict[str, Any]] = []
    if not manual_browser:
        if not iap_client_id:
            raise RuntimeError("--iap-client-id is required for programmatic authenticated probes")
        try:
            token = _run(
                ("gcloud", "auth", "print-identity-token", f"--audiences={iap_client_id}")
            ).strip()
        except RuntimeError as exc:
            raise RuntimeError(
                "programmatic IAP probing requires a service-account identity or a separately "
                "allowlisted desktop OAuth client; use --manual-browser for a human-only IAP client"
            ) from exc
        if not token:
            raise RuntimeError("gcloud returned an empty IAP identity token")

        capabilities, probe = _json_probe(base_url, "/v1/capabilities", token)
        probes.append(probe)
        if capabilities.get("mutationsEnabled") is not False:
            raise RuntimeError("capabilities endpoint reports mutations enabled")
        experiments, probe = _json_probe(base_url, "/v1/experiments", token)
        probe["run_count"] = len(experiments.get("runs", []))
        probes.append(probe)
        operations, probe = _json_probe(base_url, "/v1/operations", token)
        probe["run_count"] = len(operations.get("runs", []))
        probes.append(probe)
        options, probe = _json_probe(base_url, "/v1/forecasts/options", token)
        probe["run_count"] = len(options.get("runs", []))
        probes.append(probe)

        for path in ("/overview", "/experiments", "/accuracy", "/operations", "/forecasts"):
            status, headers, _ = _request(f"{base_url}{path}", token)
            if status != 200 or "text/html" not in headers.get("Content-Type", ""):
                raise RuntimeError(f"browser route {path} did not return the application shell")
            probes.append({"path": path, "status": status, "content_type": "text/html"})

    revision = (
        service.get("status", {}).get("latestReadyRevisionName")
        or service.get("latestReadyRevision")
        or "unknown"
    )
    return {
        "gate": "forecastlab_readonly_live",
        "status": "passed",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "project": project,
        "region": region,
        "service": service_name,
        "revision": revision,
        "image_digest": image.rsplit("@", 1)[1],
        "mutations_enabled": False,
        "authorization_enabled": True,
        "iap_access_member_count": len(iap_members),
        "public_access_bindings": 0,
        "unauthenticated_root_status": unauthorized_status,
        "probes": probes,
        "authenticated_probe_mode": "manual_browser" if manual_browser else "programmatic",
        "manual_browser_session_required": manual_browser,
    }


def _write_evidence(output: Path, evidence: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(f"PASS: {evidence['gate']}")
    print(f"Sanitized evidence: {output}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan", help="validate a Terraform plan before apply")
    plan.add_argument("--plan", type=Path, required=True)
    plan.add_argument(
        "--terraform-dir",
        type=Path,
        help="Terraform working directory containing the initialized provider plugins",
    )
    plan.add_argument("--output", type=Path, required=True)
    live = subparsers.add_parser("live", help="capture sanitized evidence after deployment")
    live.add_argument("--project", required=True)
    live.add_argument("--region", required=True)
    live.add_argument("--service", required=True)
    live.add_argument("--base-url", required=True)
    live.add_argument("--iap-client-id")
    live.add_argument(
        "--manual-browser",
        action="store_true",
        help="verify infrastructure and anonymous denial; record authenticated routes manually",
    )
    live.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "plan":
            evidence = validate_readonly_plan(_load_plan(args.plan, args.terraform_dir))
        else:
            evidence = capture_live_evidence(
                project=args.project,
                region=args.region,
                service_name=args.service,
                base_url=args.base_url.rstrip("/"),
                iap_client_id=args.iap_client_id,
                manual_browser=args.manual_browser,
            )
        _write_evidence(args.output, evidence)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
