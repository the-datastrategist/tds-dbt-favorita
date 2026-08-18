"""Signed outbound delivery for immutable forecast publication events."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlparse

import requests


@dataclass(frozen=True)
class WebhookResponse:
    status_code: int
    delivery_reference: str


class WebhookDeliveryError(RuntimeError):
    def __init__(self, *, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


WebhookTransport = Callable[[str, bytes, dict[str, str], float], WebhookResponse]


def canonical_webhook_body(event: dict[str, Any]) -> bytes:
    """Serialize a stable public envelope without warehouse-only audit fields."""
    payload = {
        "publication_event_id": event["publication_event_id"],
        **event["payload_json"],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def webhook_signature(body: bytes, *, timestamp: str, signing_secret: str) -> str:
    if not signing_secret:
        raise ValueError("webhook signing secret is required")
    message = timestamp.encode("utf-8") + b"." + body
    return "sha256=" + hmac.new(signing_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _requests_transport(
    url: str, body: bytes, headers: dict[str, str], timeout_seconds: float
) -> WebhookResponse:
    try:
        response = requests.post(url, data=body, headers=headers, timeout=timeout_seconds)
    except requests.RequestException as exc:
        raise WebhookDeliveryError(
            error_code="request_error", message="webhook request failed"
        ) from exc
    if not 200 <= response.status_code < 300:
        raise WebhookDeliveryError(
            error_code=f"http_{response.status_code}",
            message=f"webhook returned HTTP {response.status_code}",
        )
    reference = response.headers.get("Location") or f"http:{response.status_code}"
    return WebhookResponse(status_code=response.status_code, delivery_reference=reference)


def deliver_publication_webhook(
    event: dict[str, Any],
    *,
    url: str,
    signing_secret: str,
    timeout_seconds: float = 10.0,
    transport: WebhookTransport | None = None,
) -> WebhookResponse:
    """POST one signed publication event and reject unsafe endpoint configuration."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("webhook URL must be an HTTPS URL without embedded credentials")
    if timeout_seconds <= 0:
        raise ValueError("webhook timeout must be positive")
    body = canonical_webhook_body(event)
    timestamp = event["occurred_at"].isoformat()
    headers = {
        "Content-Type": "application/json",
        "Idempotency-Key": str(event["publication_event_id"]),
        "X-Forecast-Event-Id": str(event["publication_event_id"]),
        "X-Forecast-Timestamp": timestamp,
        "X-Forecast-Signature": webhook_signature(
            body, timestamp=timestamp, signing_secret=signing_secret
        ),
    }
    return (transport or _requests_transport)(url, body, headers, timeout_seconds)
