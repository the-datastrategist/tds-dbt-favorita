"""Tests for forecast publication orchestration."""

from unittest.mock import Mock, patch

import pandas as pd
import pytest

from orchestration.flows.forecast_publication import run_forecast_publication_cycle


@pytest.mark.unit
@patch("orchestration.flows.forecast_publication.persist_publication_records")
@patch("orchestration.flows.forecast_publication.build_publication_records")
@patch("orchestration.flows.forecast_publication.validate_publication_batch")
@patch("orchestration.flows.forecast_publication.load_forecast_run")
@patch("orchestration.flows.forecast_publication.load_forecast_contract")
def test_auto_publish_validates_then_persists(
    load_contract: Mock,
    load_run: Mock,
    validate: Mock,
    build: Mock,
    persist: Mock,
) -> None:
    rows = pd.DataFrame([{"forecast_output_id": "output-1"}])
    load_run.return_value = rows
    build.return_value = ([{"approval_id": "approval-1"}], [{"publication_id": "pub-1"}])

    result = run_forecast_publication_cycle(
        forecast_run_id="run-1",
        publication_mode="auto_publish",
        idempotency_key="daily-1",
    )

    validate.assert_called_once_with(rows, load_contract.return_value)
    persist.assert_called_once()
    assert result["published"] is True
    assert result["publication_count"] == 1


@pytest.mark.unit
@patch("orchestration.flows.forecast_publication.persist_publication_records")
@patch("orchestration.flows.forecast_publication.validate_publication_batch")
@patch("orchestration.flows.forecast_publication.load_forecast_run")
@patch("orchestration.flows.forecast_publication.load_forecast_contract")
def test_draft_only_validates_without_publishing(
    load_contract: Mock, load_run: Mock, validate: Mock, persist: Mock
) -> None:
    load_run.return_value = pd.DataFrame([{"forecast_output_id": "output-1"}])

    result = run_forecast_publication_cycle(
        forecast_run_id="run-1",
        publication_mode="draft_only",
        idempotency_key="daily-1",
    )

    assert result["published"] is False
    validate.assert_called_once()
    persist.assert_not_called()
