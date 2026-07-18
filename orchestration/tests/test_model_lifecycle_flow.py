"""Unit tests for governed model lifecycle orchestration."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from orchestration.flows.model_lifecycle import run_model_lifecycle_cycle


@pytest.mark.unit
@patch("orchestration.flows.model_lifecycle.persist_lifecycle_event")
@patch("orchestration.flows.model_lifecycle.resolve_champion_candidate_id")
@patch("orchestration.flows.model_lifecycle.persist_evaluation")
@patch("orchestration.flows.model_lifecycle.evaluate_candidate")
@patch("orchestration.flows.model_lifecycle.persist_backtest_result")
@patch("orchestration.flows.model_lifecycle.run_backtest")
@patch("orchestration.flows.model_lifecycle.load_backtest_contract")
def test_cycle_persists_evidence_and_replaces_champion(
    load_contract: Mock,
    run_backtest: Mock,
    persist_backtest: Mock,
    evaluate: Mock,
    persist_evaluation: Mock,
    resolve_champion: Mock,
    persist_event: Mock,
) -> None:
    contract = SimpleNamespace(model_config_name="model-h7")
    result = SimpleNamespace(backtest_run_id="run-1")
    evaluation = SimpleNamespace(
        candidate={"candidate_id": "candidate-2"},
        passed=True,
    )
    load_contract.return_value = contract
    run_backtest.return_value = result
    evaluate.return_value = evaluation
    resolve_champion.return_value = "candidate-1"

    with patch(
        "orchestration.flows.model_lifecycle.build_promotion_event",
        return_value={
            "lifecycle_event_id": "event-1",
            "replaces_candidate_id": "candidate-1",
        },
    ):
        output = run_model_lifecycle_cycle(artifact_uri="gs://models/model.json")

    assert output == {
        "backtest_run_id": "run-1",
        "candidate_id": "candidate-2",
        "checks_passed": True,
        "promoted": True,
        "lifecycle_event_id": "event-1",
        "replaces_candidate_id": "candidate-1",
    }
    persist_backtest.assert_called_once()
    persist_evaluation.assert_called_once()
    persist_event.assert_called_once()


@pytest.mark.unit
@patch("orchestration.flows.model_lifecycle.persist_lifecycle_event")
@patch("orchestration.flows.model_lifecycle.resolve_champion_candidate_id")
@patch("orchestration.flows.model_lifecycle.persist_evaluation")
@patch("orchestration.flows.model_lifecycle.evaluate_candidate")
@patch("orchestration.flows.model_lifecycle.persist_backtest_result")
@patch("orchestration.flows.model_lifecycle.run_backtest")
@patch("orchestration.flows.model_lifecycle.load_backtest_contract")
def test_cycle_does_not_promote_failed_candidate(
    load_contract: Mock,
    run_backtest: Mock,
    persist_backtest: Mock,
    evaluate: Mock,
    persist_evaluation: Mock,
    resolve_champion: Mock,
    persist_event: Mock,
) -> None:
    load_contract.return_value = SimpleNamespace(model_config_name="model-h7")
    run_backtest.return_value = SimpleNamespace(backtest_run_id="run-1")
    evaluate.return_value = SimpleNamespace(
        candidate={"candidate_id": "candidate-2"},
        passed=False,
    )

    output = run_model_lifecycle_cycle(artifact_uri="gs://models/model.json")

    assert output["checks_passed"] is False
    assert output["promoted"] is False
    persist_backtest.assert_called_once()
    persist_evaluation.assert_called_once()
    resolve_champion.assert_not_called()
    persist_event.assert_not_called()
