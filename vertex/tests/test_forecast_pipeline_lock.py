"""Tests for deterministic forecast publication lease behavior."""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from vertex.evaluation.forecast_pipeline_lock import acquire_forecast_lock, forecast_lock_key


@pytest.mark.unit
def test_lock_key_is_stable_per_contract_and_origin() -> None:
    origin = datetime(2026, 7, 18, tzinfo=timezone.utc)
    assert forecast_lock_key("contract-1", origin) == forecast_lock_key("contract-1", origin)
    assert forecast_lock_key("contract-1", origin) != forecast_lock_key("contract-2", origin)


@pytest.mark.unit
@patch("vertex.evaluation.forecast_pipeline_lock.bigquery.Client")
def test_acquire_returns_false_when_another_owner_holds_lease(client_type: Mock) -> None:
    client = client_type.return_value
    client.query.return_value.result.return_value = [{"acquired": False}]

    acquired = acquire_forecast_lock(
        contract_hash="contract-1",
        forecast_origin=datetime(2026, 7, 18, tzinfo=timezone.utc),
        owner_id="run-2",
        lock_table="project.dataset.forecast_pipeline_locks",
    )

    assert acquired is False
    client.query.assert_called_once()
