"""Read-only forecast retrieval API contract tests."""

from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from vertex.api.app import create_app
from vertex.api.repository import (
    BigQueryForecastRepository,
    ForecastExplorerOptions,
    ForecastExplorerResult,
    ForecastFilters,
    ForecastPageResult,
    MutationConflictError,
    MutationNotFoundError,
    PublicationScope,
    canonical_entity_key,
    decode_page_token,
    encode_page_token,
)


def _scope() -> PublicationScope:
    return PublicationScope(
        forecast_run_id="run-1",
        forecast_contract_name="contract-1",
        forecast_contract_hash="hash-1",
        publication_version=3,
        destination="canonical_bigquery",
        publication_row_count=2,
        published_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
        delivery_status="delivered",
    )


def _row(publication_id: str = "publication-1") -> dict:
    return {
        "publication_id": publication_id,
        "forecast_run_id": "run-1",
        "forecast_contract_name": "contract-1",
        "forecast_contract_hash": "hash-1",
        "publication_version": 3,
        "destination": "canonical_bigquery",
        "entity_key_json": '{"store_nbr":1}',
        "target_date": "2026-08-18",
        "horizon": 7,
        "published_value": 42.0,
    }


@pytest.mark.unit
def test_forecastlab_spa_is_served_without_shadowing_api_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    (tmp_path / "index.html").write_text("<html>ForecastLab</html>", encoding="utf-8")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("console.log('ForecastLab')", encoding="utf-8")
    monkeypatch.setenv("FORECASTLAB_DIST_DIR", str(tmp_path))
    client = TestClient(create_app(FakeRepository()))

    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/forecasts").text == "<html>ForecastLab</html>"
    assert "console.log" in client.get("/assets/app.js").text
    assert client.get("/../requirements.txt").text == "<html>ForecastLab</html>"


_DEFAULT_SCOPE = object()


class FakeRepository:
    def __init__(
        self,
        *,
        scope: PublicationScope | None | object = _DEFAULT_SCOPE,
        failure: Exception | None = None,
    ):
        if scope is _DEFAULT_SCOPE:
            self.scope: PublicationScope | None = _scope()
        else:
            assert isinstance(scope, PublicationScope) or scope is None
            self.scope = scope
        self.failure = failure
        self.calls: list[tuple[object, ...]] = []

    def forecast_explorer_options(self, *, forecast_run_id=None):
        self.calls.append(("explorer_options", forecast_run_id))
        return ForecastExplorerOptions(
            runs=[{"id": "run-1", "label": "2026-08-11 · published v3", "origin": "2026-08-11"}],
            entities=[
                {
                    "id": '{"store_nbr":1}',
                    "name": "store_nbr 1",
                    "hierarchyNode": '{"store_nbr":1}',
                    "hierarchyLevel": "store_day",
                }
            ],
            models=[{"id": "model-1", "name": "favorita_xgboost"}],
            horizons=[1, 7],
        )

    def forecast_explorer_result(self, **kwargs):
        self.calls.append(("explorer_result", kwargs))
        if self.failure:
            raise self.failure
        if self.scope is None:
            return None
        return ForecastExplorerResult(
            run={
                "id": "run-1",
                "label": "2026-08-11 · published v3",
                "origin": "2026-08-11",
                "publicationStatus": "published",
            },
            entity={
                "id": '{"store_nbr":1}',
                "name": "store_nbr 1",
                "hierarchyNode": '{"store_nbr":1}',
                "hierarchyLevel": "store_day",
            },
            model={"id": "model-1", "name": "favorita_xgboost"},
            rows=[
                {
                    "runId": "run-1",
                    "entityId": '{"store_nbr":1}',
                    "modelId": "model-1",
                    "targetDate": "2026-08-18",
                    "horizon": 7,
                    "actual": 40.0,
                    "p10": 35.0,
                    "p50": 42.0,
                    "p90": 49.0,
                    "statisticalForecast": 42.0,
                    "publishedForecast": 43.0,
                    "strategy": "entity_model",
                    "exceptionState": "clear",
                }
            ],
            provenance={
                "contractName": "contract-1",
                "contractHash": "hash-1",
                "modelRunId": "model-run-1",
                "calibrationRunId": "calibration-1",
                "reconciliationRunId": "reconciliation-1",
                "hierarchyVersion": "hierarchy-1",
                "featureVersion": "features-1",
                "featureAvailabilityHash": "availability-1",
                "dataCutoff": "2026-08-11T00:00:00+00:00",
                "codeSha": "abc123",
                "publicationVersion": "3",
            },
        )

    def resolve_current(self, *, contract_name: str, destination: str):
        self.calls.append(("current", contract_name, destination))
        return self.scope

    def resolve_version(self, *, forecast_run_id: str, publication_version: int, destination: str):
        self.calls.append(("version", forecast_run_id, publication_version, destination))
        return self.scope

    def fetch_page(self, scope, *, filters, limit, page_token):
        self.calls.append(("fetch", scope, filters, limit, page_token))
        if self.failure:
            raise self.failure
        return ForecastPageResult(scope=scope, rows=[_row()], next_page_token="next")

    def create_override(self, **kwargs):
        self.calls.append(("override", kwargs))
        if self.failure:
            raise self.failure
        return {"action": "override", "override_id": "override-1", "retry": False}

    def approve_run(self, **kwargs):
        self.calls.append(("approve", kwargs))
        if self.failure:
            raise self.failure
        return {
            "action": "approve",
            "approval_count": 2,
            "override_count": 1,
            "retry": False,
        }

    def publish_run(self, **kwargs):
        self.calls.append(("publish", kwargs))
        if self.failure:
            raise self.failure
        return {
            "action": "publish",
            "publication_count": 2,
            "publication_version": 4,
            "publication_event_id": "event-1",
            "retry": False,
        }


@pytest.mark.unit
def test_current_endpoint_resolves_one_delivered_version_and_normalizes_filters():
    repository = FakeRepository()
    client = TestClient(create_app(repository))

    response = client.get(
        "/v1/forecasts/current",
        params=[
            ("contract_name", "contract-1"),
            ("entity_key", '{"store_nbr": 1}'),
            ("horizon", "7"),
            ("horizon", "14"),
            ("limit", "25"),
        ],
    )

    assert response.status_code == 200
    assert response.json()["forecast_run_id"] == "run-1"
    assert response.json()["publication_version"] == 3
    assert response.json()["next_page_token"] == "next"
    fetch = repository.calls[-1]
    assert fetch[2] == ForecastFilters(entity_key_json='{"store_nbr":1}', horizons=(7, 14))
    assert fetch[3] == 25


@pytest.mark.unit
def test_forecastlab_options_and_forecasts_expose_live_typed_contract():
    repository = FakeRepository()
    client = TestClient(create_app(repository))

    options = client.get("/v1/forecasts/options")
    forecasts = client.get(
        "/v1/forecasts",
        params={
            "run_id": "run-1",
            "entity_id": '{"store_nbr": 1}',
            "model_id": "model-1",
            "horizon": 7,
            "exception_state": "clear",
        },
    )

    assert options.status_code == 200
    assert options.headers["x-request-id"]
    assert options.json()["horizons"] == [1, 7]
    assert options.json()["exceptionStates"] == ["clear", "watch", "blocked"]
    assert forecasts.status_code == 200
    assert forecasts.json()["datasetKind"] == "live"
    assert forecasts.json()["rows"][0]["publishedForecast"] == 43.0
    assert forecasts.json()["provenance"]["featureAvailabilityHash"] == "availability-1"
    assert repository.calls[-1] == (
        "explorer_result",
        {
            "forecast_run_id": "run-1",
            "entity_key_json": '{"store_nbr":1}',
            "model_id": "model-1",
            "horizon": 7,
            "exception_state": "clear",
            "target_start": None,
            "target_end": None,
            "limit": 100,
            "page_token": None,
        },
    )
    openapi = client.get("/openapi.json").json()
    assert openapi["info"]["version"] == "1.2.0"
    assert "/v1/forecasts/options" in openapi["paths"]
    assert "/v1/forecast-runs/{forecast_run_id}" in openapi["paths"]
    assert "ExplorerProvenance" in openapi["components"]["schemas"]


@pytest.mark.unit
def test_forecastlab_scopes_options_and_preserves_valid_request_ids():
    repository = FakeRepository()
    client = TestClient(create_app(repository))

    response = client.get(
        "/v1/forecasts/options",
        params={"run_id": "run-1"},
        headers={"X-Request-ID": "forecastlab-test-123"},
    )

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "forecastlab-test-123"
    assert repository.calls[-1] == ("explorer_options", "run-1")


@pytest.mark.unit
def test_forecastlab_validates_date_bounds_and_page_tokens():
    repository = FakeRepository(failure=ValueError("invalid page_token"))
    client = TestClient(create_app(repository))
    params = {
        "run_id": "run-1",
        "entity_id": '{"store_nbr":1}',
        "model_id": "model-1",
    }

    invalid_range = client.get(
        "/v1/forecasts",
        params={**params, "target_start": "2026-08-20", "target_end": "2026-08-18"},
    )
    invalid_token = client.get("/v1/forecasts", params={**params, "page_token": "tampered"})

    assert invalid_range.status_code == 422
    assert invalid_range.json()["code"] == "invalid_date_range"
    assert invalid_token.status_code == 400
    assert invalid_token.json()["code"] == "invalid_page_token"


@pytest.mark.unit
def test_forecastlab_run_alias_and_validation_use_structured_errors():
    repository = FakeRepository()
    client = TestClient(create_app(repository))

    alias = client.get(
        "/v1/forecast-runs/run-1",
        params={"entity_id": '{"store_nbr":1}', "model_id": "model-1"},
    )
    invalid_entity = client.get(
        "/v1/forecasts",
        params={"run_id": "run-1", "entity_id": "bad", "model_id": "model-1"},
    )
    invalid_state = client.get(
        "/v1/forecasts",
        params={
            "run_id": "run-1",
            "entity_id": '{"store_nbr":1}',
            "model_id": "model-1",
            "exception_state": "unknown",
        },
    )

    assert alias.status_code == 200
    assert invalid_entity.status_code == 422
    assert invalid_entity.json()["code"] == "invalid_entity_id"
    assert invalid_state.status_code == 422
    assert invalid_state.json()["code"] == "validation_error"


@pytest.mark.unit
def test_forecastlab_returns_not_found_for_undelivered_or_empty_selection():
    client = TestClient(create_app(FakeRepository(scope=None)))

    response = client.get(
        "/v1/forecasts",
        params={
            "run_id": "missing",
            "entity_id": '{"store_nbr":1}',
            "model_id": "model-1",
        },
    )

    assert response.status_code == 404
    assert response.json()["code"] == "forecast_selection_not_found"


@pytest.mark.unit
def test_versioned_endpoint_requires_explicit_positive_version():
    repository = FakeRepository()
    client = TestClient(create_app(repository))

    missing = client.get("/v1/forecasts/runs/run-1")
    invalid = client.get("/v1/forecasts/runs/run-1", params={"publication_version": 0})
    valid = client.get("/v1/forecasts/runs/run-1", params={"publication_version": 3})

    assert missing.status_code == 422
    assert missing.json()["code"] == "validation_error"
    assert invalid.status_code == 422
    assert valid.status_code == 200
    assert repository.calls[-2] == ("version", "run-1", 3, "canonical_bigquery")


@pytest.mark.unit
def test_not_found_incomplete_and_invalid_requests_are_structured():
    missing_client = TestClient(create_app(FakeRepository(scope=None)))
    incomplete_client = TestClient(
        create_app(FakeRepository(failure=RuntimeError("expected 55, found 54")))
    )
    normal_client = TestClient(create_app(FakeRepository()))

    missing = missing_client.get("/v1/forecasts/runs/run-1", params={"publication_version": 3})
    incomplete = incomplete_client.get(
        "/v1/forecasts/runs/run-1", params={"publication_version": 3}
    )
    invalid_entity = normal_client.get(
        "/v1/forecasts/current",
        params={"contract_name": "contract-1", "entity_key": "not-json"},
    )
    invalid_range = normal_client.get(
        "/v1/forecasts/current",
        params={
            "contract_name": "contract-1",
            "target_start": "2026-08-20",
            "target_end": "2026-08-18",
        },
    )

    assert missing.status_code == 404
    assert missing.json()["code"] == "publication_not_found"
    assert incomplete.status_code == 409
    assert incomplete.json()["code"] == "incomplete_publication"
    assert invalid_entity.status_code == 422
    assert invalid_entity.json()["code"] == "invalid_entity_key"
    assert invalid_range.status_code == 422
    assert invalid_range.json()["code"] == "invalid_date_range"


@pytest.mark.unit
def test_unexpected_repository_failures_do_not_leak_details():
    client = TestClient(
        create_app(FakeRepository(failure=Exception("sensitive warehouse detail"))),
        raise_server_exceptions=False,
    )

    response = client.get("/v1/forecasts/runs/run-1", params={"publication_version": 3})

    assert response.status_code == 500
    assert response.json() == {
        "code": "internal_error",
        "message": "forecast API request failed",
    }
    assert "sensitive" not in response.text


@pytest.mark.unit
def test_lifecycle_mutations_forward_explicit_idempotent_contracts():
    repository = FakeRepository()
    client = TestClient(create_app(repository, mutations_enabled=True))

    override = client.post(
        "/v1/overrides",
        json={
            "forecast_run_id": "run-1",
            "forecast_output_id": "output-1",
            "override_value": 45.0,
            "reason_code": "planner_judgment",
            "comment": "Local event expected",
            "actor": "planner@example.com",
            "idempotency_key": "override-request-1",
        },
    )
    approval = client.post(
        "/v1/forecast-runs/run-1/approve",
        json={
            "reason_code": "review_complete",
            "comment": "Reviewed all exceptions",
            "actor": "approver@example.com",
            "idempotency_key": "approval-request-1",
        },
    )
    publication = client.post(
        "/v1/forecast-runs/run-1/publish",
        json={
            "approval_idempotency_key": "approval-request-1",
            "publication_version": 4,
            "destination": "canonical_bigquery",
            "actor": "publisher@example.com",
            "idempotency_key": "publication-request-1",
        },
    )

    assert override.status_code == 200
    assert override.json()["override_id"] == "override-1"
    assert approval.status_code == 200
    assert approval.json()["approval_count"] == 2
    assert publication.status_code == 200
    assert publication.json()["publication_event_id"] == "event-1"
    assert repository.calls[-1] == (
        "publish",
        {
            "forecast_run_id": "run-1",
            "approval_idempotency_key": "approval-request-1",
            "destination": "canonical_bigquery",
            "publication_version": 4,
            "actor": "publisher@example.com",
            "idempotency_key": "publication-request-1",
        },
    )


@pytest.mark.unit
def test_lifecycle_mutations_return_structured_validation_not_found_and_conflict_errors():
    normal = TestClient(create_app(FakeRepository(), mutations_enabled=True))
    missing = TestClient(
        create_app(
            FakeRepository(failure=MutationNotFoundError("run missing")),
            mutations_enabled=True,
        )
    )
    conflict = TestClient(
        create_app(
            FakeRepository(failure=MutationConflictError("version already exists")),
            mutations_enabled=True,
        )
    )

    invalid = normal.post(
        "/v1/overrides",
        json={
            "forecast_run_id": "run-1",
            "forecast_output_id": "output-1",
            "override_value": -1,
            "reason_code": "reason",
            "comment": "comment",
            "actor": "planner@example.com",
            "idempotency_key": "key-1",
        },
    )
    not_found = missing.post(
        "/v1/forecast-runs/run-1/approve",
        json={
            "reason_code": "reason",
            "comment": "comment",
            "actor": "approver@example.com",
            "idempotency_key": "key-2",
        },
    )
    collided = conflict.post(
        "/v1/forecast-runs/run-1/publish",
        json={
            "approval_idempotency_key": "approval-1",
            "publication_version": 2,
            "actor": "publisher@example.com",
            "idempotency_key": "key-3",
        },
    )

    assert invalid.status_code == 422
    assert invalid.json()["code"] == "validation_error"
    assert not_found.status_code == 404
    assert not_found.json()["code"] == "mutation_target_not_found"
    assert collided.status_code == 409
    assert collided.json()["code"] == "mutation_conflict"


@pytest.mark.unit
def test_lifecycle_mutations_are_disabled_by_default():
    client = TestClient(create_app(FakeRepository(), mutations_enabled=False))

    response = client.post(
        "/v1/forecast-runs/run-1/approve",
        json={
            "reason_code": "review_complete",
            "comment": "Reviewed",
            "actor": "approver@example.com",
            "idempotency_key": "approval-1",
        },
    )

    assert response.status_code == 403
    assert response.json()["code"] == "mutations_disabled"


@pytest.mark.unit
def test_page_token_is_stable_and_rejects_tampering():
    token = encode_page_token(_row())

    decoded = decode_page_token(token)

    assert decoded["entity_key_json"] == '{"store_nbr":1}'
    assert decoded["horizon"] == 7
    with pytest.raises(ValueError, match="invalid page_token"):
        decode_page_token("not-a-token")


@pytest.mark.unit
def test_entity_key_requires_a_non_empty_json_object():
    assert canonical_entity_key('{"b": 2, "a": 1}') == '{"a":1,"b":2}'
    with pytest.raises(ValueError, match="non-empty"):
        canonical_entity_key("[]")


class FakeQueryJob:
    def __init__(self, rows):
        self.rows = rows

    def result(self):
        return iter(self.rows)


@pytest.mark.unit
@patch("vertex.api.repository.bigquery.Client")
def test_bigquery_repository_blocks_incomplete_versions(client_class):
    client = MagicMock()
    client_class.return_value = client
    client.query.return_value = FakeQueryJob([{"row_count": 1}])
    repository = BigQueryForecastRepository(project_id="project", table_prefix="project.dataset")

    with pytest.raises(RuntimeError, match="expected 2, found 1"):
        repository.fetch_page(_scope(), filters=ForecastFilters(), limit=100, page_token=None)

    query = client.query.call_args.args[0]
    assert "forecast_run_id = @forecast_run_id" in query
    assert "publication_version = @publication_version" in query
    assert "destination = @destination" in query


@pytest.mark.unit
@patch("vertex.api.repository.bigquery.Client")
def test_bigquery_repository_uses_keyset_pagination_with_bound_parameters(client_class):
    client = MagicMock()
    client_class.return_value = client
    first = _row("publication-1")
    second = _row("publication-2")
    client.query.side_effect = [
        FakeQueryJob([{"row_count": 2}]),
        FakeQueryJob([first, second]),
    ]
    repository = BigQueryForecastRepository(project_id="project", table_prefix="project.dataset")

    result = repository.fetch_page(
        _scope(),
        filters=ForecastFilters(horizons=(7,)),
        limit=1,
        page_token=encode_page_token(_row("prior-publication")),
    )

    assert [row["publication_id"] for row in result.rows] == ["publication-1"]
    assert result.next_page_token
    page_query = client.query.call_args.args[0]
    assert "ORDER BY entity_key_json, target_date, horizon, publication_id" in page_query
    assert "horizon IN UNNEST(@horizons)" in page_query
    assert "publication_id > @cursor_publication_id" in page_query
    parameters = client.query.call_args.kwargs["job_config"].query_parameters
    assert {parameter.name for parameter in parameters} >= {
        "forecast_run_id",
        "publication_version",
        "destination",
        "horizons",
        "cursor_publication_id",
        "page_limit",
    }


@pytest.mark.unit
@patch("vertex.api.repository.bigquery.Client")
def test_bigquery_repository_shapes_only_delivered_forecastlab_evidence(client_class):
    client_class.return_value = MagicMock()
    repository = BigQueryForecastRepository(project_id="project", table_prefix="project.dataset")
    delivered = pd.DataFrame(
        [
            {
                "forecast_run_id": "run-1",
                "forecast_contract_name": "contract-1",
                "forecast_contract_hash": "hash-1",
                "publication_version": 3,
                "destination": "canonical_bigquery",
                "publication_row_count": 1,
                "published_at": datetime(2026, 8, 18, tzinfo=timezone.utc),
                "delivery_status": "delivered",
            }
        ]
    )
    forecast = pd.DataFrame(
        [
            {
                "publication_id": "publication-1",
                "forecast_run_id": "run-1",
                "forecast_contract_name": "contract-1",
                "forecast_contract_hash": "hash-1",
                "forecast_origin": date(2026, 8, 18),
                "target_date": date(2026, 8, 19),
                "horizon": 1,
                "grain": "store_day",
                "prediction_p10": 10,
                "prediction_p50": 12,
                "prediction_p90": 15,
                "statistical_forecast": 12,
                "published_value": 13,
                "forecast_strategy": "entity_model",
                "exception_state": "clear",
                "actual": 11,
                "config_name": "favorita_xgboost",
                "model_family": "xgboost",
                "model_run_id": "model-run-1",
                "calibration_run_id": "calibration-1",
                "reconciliation_run_id": "reconciliation-1",
                "hierarchy_version": "hierarchy-1",
                "feature_version": "features-1",
                "feature_availability_hash": "availability-1",
                "data_cutoff": datetime(2026, 8, 18, tzinfo=timezone.utc),
                "code_sha": "abc123",
            }
        ]
    )
    repository._dataframe = MagicMock(side_effect=[delivered, forecast])

    result = repository.forecast_explorer_result(
        forecast_run_id="run-1",
        entity_key_json='{"store_nbr":1}',
        model_id="model-1",
        horizon=1,
        exception_state="clear",
    )

    assert result is not None
    assert result.rows[0]["actual"] == 11.0
    assert result.rows[0]["publishedForecast"] == 13.0
    assert result.provenance["featureAvailabilityHash"] == "availability-1"
    forecast_query = repository._dataframe.call_args_list[1].args[0]
    assert "delivery_status = 'delivered'" in repository._dataframe.call_args_list[0].args[0]
    assert "LEFT JOIN `project.dataset.int_demand_store_daily`" in forecast_query
    assert "f.horizon = @horizon" in forecast_query
    assert "@exception_state" in forecast_query
