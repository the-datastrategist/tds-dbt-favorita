"""Tests for append-only forecast lifecycle events."""

from datetime import datetime

import pandas as pd
import pytest

from vertex.utils.forecast_lifecycle import build_status_events, validate_status_transition


@pytest.mark.unit
@pytest.mark.parametrize(
    ("previous", "new"),
    [(None, "draft"), ("draft", "approved"), ("approved", "published"), ("published", "superseded")],
)
def test_valid_status_transitions(previous, new):
    validate_status_transition(previous, new)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("previous", "new"),
    [(None, "published"), ("draft", "published"), ("published", "draft"), ("failed", "draft")],
)
def test_invalid_status_transitions(previous, new):
    with pytest.raises(ValueError, match="invalid forecast status transition"):
        validate_status_transition(previous, new)


@pytest.mark.unit
def test_status_event_ids_are_idempotent():
    rows = pd.DataFrame(
        [{"forecast_output_id": "output-1", "forecast_run_id": "run-1", "forecast_status": "draft"}]
    )
    first = build_status_events(rows, changed_at=datetime(2024, 1, 1), changed_by="test")
    retry = build_status_events(rows, changed_at=datetime(2024, 1, 2), changed_by="test")
    assert first[0]["status_event_id"] == retry[0]["status_event_id"]
