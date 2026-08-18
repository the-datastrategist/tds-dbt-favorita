"""Tests for signed outbound forecast publication webhooks."""

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import patch

import pandas as pd
import pytest

from vertex.api.repository import BigQueryForecastRepository
from vertex.utils.forecast_delivery import build_publication_event
from vertex.utils.forecast_webhook import (
    WebhookDeliveryError,
    WebhookResponse,
    deliver_publication_webhook,
)


def _event() -> dict:
    return build_publication_event(
        event_type="forecast.published",
        forecast_run_id="run-1",
        forecast_contract_name="contract-1",
        forecast_contract_hash="hash-1",
        publication_version=2,
        destination="canonical_bigquery",
        row_count=55,
        actor="publisher@example.com",
        idempotency_key="publish-2",
        occurred_at=datetime(2026, 8, 18, 12, tzinfo=timezone.utc),
    )


@pytest.mark.unit
def test_webhook_posts_stable_signed_event_envelope():
    captured = {}

    def transport(url, body, headers, timeout):
        captured.update(url=url, body=body, headers=headers, timeout=timeout)
        return WebhookResponse(status_code=202, delivery_reference="receipt-1")

    response = deliver_publication_webhook(
        _event(),
        url="https://consumer.example.com/forecast-events",
        signing_secret="test-secret",
        transport=transport,
    )

    payload = json.loads(captured["body"])
    assert response.delivery_reference == "receipt-1"
    assert payload["event_type"] == "forecast.published"
    assert payload["publication_event_id"] == _event()["publication_event_id"]
    assert captured["headers"]["Idempotency-Key"] == _event()["publication_event_id"]
    message = captured["headers"]["X-Forecast-Timestamp"].encode() + b"." + captured["body"]
    expected = "sha256=" + hmac.new(b"test-secret", message, hashlib.sha256).hexdigest()
    assert hmac.compare_digest(captured["headers"]["X-Forecast-Signature"], expected)


@pytest.mark.unit
@pytest.mark.parametrize(
    "url",
    ["http://consumer.example.com/hook", "https://user:pass@example.com/hook", "not-a-url"],
)
def test_webhook_rejects_unsafe_urls(url):
    with pytest.raises(ValueError, match="HTTPS URL"):
        deliver_publication_webhook(_event(), url=url, signing_secret="secret")


@pytest.mark.unit
def test_webhook_transport_failure_is_structured_without_response_body():
    def transport(*_):
        raise WebhookDeliveryError(error_code="http_503", message="webhook returned HTTP 503")

    with pytest.raises(WebhookDeliveryError) as error:
        deliver_publication_webhook(
            _event(),
            url="https://consumer.example.com/hook",
            signing_secret="secret",
            transport=transport,
        )

    assert error.value.error_code == "http_503"
    assert "consumer response" not in str(error.value)


def _repository(latest: pd.DataFrame, transport) -> BigQueryForecastRepository:
    repository = object.__new__(BigQueryForecastRepository)
    repository.webhook_url = "https://consumer.example.com/hook"
    repository.webhook_signing_secret = "secret"
    repository.webhook_name = "planning"
    repository.webhook_transport = transport
    repository.delivery_events_table = "project.dataset.forecast_delivery_events"
    repository.table_prefix = "project.dataset"
    repository.project_id = "project"
    cast(Any, repository)._dataframe = lambda *_: latest
    return repository


@pytest.mark.unit
@patch("vertex.api.repository.persist_delivery_event")
def test_repository_persists_pending_then_delivered(persist):
    repository = _repository(
        pd.DataFrame(),
        lambda *_: WebhookResponse(status_code=202, delivery_reference="ignored"),
    )

    result = repository._deliver_webhook(_event(), actor="publisher@example.com")

    assert result["webhook_delivery_status"] == "delivered"
    events = [call.args[0] for call in persist.call_args_list]
    assert [event["delivery_status"] for event in events] == ["pending", "delivered"]
    assert events[1]["delivery_reference"] == "planning:http:202"


@pytest.mark.unit
@patch("vertex.api.repository.persist_delivery_event")
def test_repository_retries_failed_webhook_and_records_failure(persist):
    latest = pd.DataFrame(
        [{"delivery_event_id": "failed-1", "delivery_status": "failed", "delivery_attempt": 1}]
    )

    def transport(*_):
        raise WebhookDeliveryError(error_code="http_503", message="webhook returned HTTP 503")

    repository = _repository(latest, transport)

    result = repository._deliver_webhook(_event(), actor="publisher@example.com")

    assert result["webhook_delivery_status"] == "failed"
    events = [call.args[0] for call in persist.call_args_list]
    assert [event["delivery_status"] for event in events] == ["pending", "failed"]
    assert {event["delivery_attempt"] for event in events} == {2}
    assert events[1]["error_code"] == "http_503"


@pytest.mark.unit
@patch("vertex.api.repository.persist_delivery_event")
def test_repository_records_invalid_webhook_configuration_as_delivery_failure(persist):
    repository = _repository(pd.DataFrame(), lambda *_: pytest.fail("transport must not be called"))
    repository.webhook_url = "http://consumer.example.com/hook"

    result = repository._deliver_webhook(_event(), actor="publisher@example.com")

    assert result["webhook_delivery_status"] == "failed"
    events = [call.args[0] for call in persist.call_args_list]
    assert [event["delivery_status"] for event in events] == ["pending", "failed"]
    assert events[1]["error_code"] == "configuration_error"


@pytest.mark.unit
def test_repository_does_not_redeliver_completed_webhook():
    latest = pd.DataFrame(
        [
            {
                "delivery_event_id": "delivered-1",
                "delivery_status": "delivered",
                "delivery_attempt": 1,
            }
        ]
    )
    repository = _repository(latest, lambda *_: pytest.fail("transport must not be called"))

    result = repository._deliver_webhook(_event(), actor="publisher@example.com")

    assert result == {
        "webhook_delivery_status": "delivered",
        "webhook_delivery_event_id": "delivered-1",
    }
