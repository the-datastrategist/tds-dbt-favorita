from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.forecastlab_readonly_acceptance import _load_plan, validate_readonly_plan


def _change(
    address: str, resource_type: str, after: dict, actions: list[str] | None = None
) -> dict:
    return {
        "address": f"module.forecast_api.{address}",
        "type": resource_type,
        "change": {"actions": actions or ["create"], "after": after},
    }


def valid_plan() -> dict:
    return {
        "resource_changes": [
            _change(
                "google_cloud_run_v2_service.api[0]",
                "google_cloud_run_v2_service",
                {
                    "iap_enabled": True,
                    "template": [
                        {
                            "containers": [
                                {
                                    "image": "us-central1-docker.pkg.dev/demo/vertex/app@sha256:"
                                    + "a" * 64,
                                    "env": [
                                        {
                                            "name": "FORECAST_API_MUTATIONS_ENABLED",
                                            "value": "false",
                                        },
                                        {
                                            "name": "FORECAST_API_AUTHORIZATION_ENABLED",
                                            "value": "true",
                                        },
                                        {"name": "FORECAST_API_ROLE_MEMBERS_JSON", "value": "{}"},
                                    ],
                                }
                            ]
                        }
                    ],
                },
            ),
            _change(
                "google_bigquery_dataset_iam_member.forecast_dataset_access[0]",
                "google_bigquery_dataset_iam_member",
                {"role": "roles/bigquery.dataViewer", "member": "serviceAccount:api@example.com"},
            ),
            _change(
                'google_iap_web_cloud_run_service_iam_member.forecastlab_user["user:a@example.com"]',
                "google_iap_web_cloud_run_service_iam_member",
                {"role": "roles/iap.httpsResourceAccessor", "member": "user:a@example.com"},
            ),
            _change(
                "google_cloud_run_v2_service_iam_member.iap_invoker[0]",
                "google_cloud_run_v2_service_iam_member",
                {
                    "role": "roles/run.invoker",
                    "member": "serviceAccount:service-123@gcp-sa-iap.iam.gserviceaccount.com",
                },
            ),
        ]
    }


def test_accepts_readonly_iap_plan() -> None:
    evidence = validate_readonly_plan(valid_plan())

    assert evidence["status"] == "passed"
    assert evidence["iap_access_member_count"] == 1
    assert evidence["mutations_enabled"] is False
    assert len(evidence["plan_sha256"]) == 64


def test_loads_binary_plan_from_initialized_terraform_directory(tmp_path, monkeypatch) -> None:
    plan_path = tmp_path / "release.tfplan"
    terraform_dir = tmp_path / "terraform"
    plan_path.write_bytes(b"binary plan")
    terraform_dir.mkdir()
    observed: dict[str, object] = {}

    def fake_run(command, *, cwd=None):
        observed["command"] = command
        observed["cwd"] = cwd
        return '{"resource_changes": []}'

    monkeypatch.setattr("scripts.forecastlab_readonly_acceptance._run", fake_run)

    assert _load_plan(plan_path, terraform_dir) == {"resource_changes": []}
    assert observed == {
        "command": ("terraform", "show", "-json", str(plan_path.resolve())),
        "cwd": terraform_dir,
    }


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda plan: plan["resource_changes"][0]["change"]["after"].update(iap_enabled=False),
            "IAP",
        ),
        (
            lambda plan: plan["resource_changes"][0]["change"]["after"]["template"][0][
                "containers"
            ][0]["env"][0].update(value="true"),
            "mutations",
        ),
        (
            lambda plan: plan["resource_changes"][1]["change"]["after"].update(
                role="roles/bigquery.dataEditor"
            ),
            "dataViewer",
        ),
        (
            lambda plan: plan["resource_changes"][2]["change"]["after"].update(member="allUsers"),
            "public access",
        ),
        (
            lambda plan: plan["resource_changes"][0]["change"].update(actions=["delete", "create"]),
            "destructive",
        ),
    ],
)
def test_rejects_unsafe_plan(mutation, message: str) -> None:
    plan = deepcopy(valid_plan())
    mutation(plan)

    with pytest.raises(ValueError, match=message):
        validate_readonly_plan(plan)
