"""Tests for model promotion gates and append-only lifecycle decisions."""

from datetime import datetime, timezone
from unittest.mock import call, patch

import pandas as pd
import pytest

from vertex.config.backtest_contract import load_backtest_contract
from vertex.evaluation.backtesting import BaselineBacktestResult
from vertex.evaluation.model_lifecycle import (
    build_promotion_event,
    build_rollback_event,
    evaluate_candidate,
)
from vertex.evaluation.model_lifecycle_persistence import (
    persist_evaluation,
    resolve_champion_config_name,
)
from vertex.jobs.model_lifecycle import build_lifecycle_plan

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _result(*, model_wape: float = 0.10, completeness: float = 1.0):
    contract = load_backtest_contract()
    common = {
        "backtest_run_id": "run-1",
        "forecast_origin": pd.Timestamp("2016-08-01").date(),
        "horizon": 7,
        "segment_key_json": "{}",
        "eligible_count": 2,
        "prediction_count": 2,
        "mae": 1.0,
        "bias": 0.1,
    }
    metrics = pd.DataFrame(
        [
            {
                **common,
                "baseline_name": contract.model_config_name,
                "wape": model_wape,
                "prediction_completeness": completeness,
            },
            {
                **common,
                "baseline_name": "seasonal_naive_7d",
                "wape": 0.20,
                "prediction_completeness": 1.0,
            },
        ]
    )
    predictions = pd.DataFrame(
        [
            {"baseline_name": contract.model_config_name, "actual": 10.0, "prediction": 10.1},
            {"baseline_name": contract.model_config_name, "actual": 12.0, "prediction": 12.1},
        ]
    )
    return contract, BaselineBacktestResult("run-1", predictions, metrics)


@pytest.mark.unit
def test_passing_candidate_can_be_promoted_and_replaces_champion():
    contract, result = _result()
    evaluation = evaluate_candidate(
        result, contract, artifact_uri="gs://models/run-1/model.json", actor="ci", evaluated_at=NOW
    )
    event = build_promotion_event(
        evaluation, actor="ci", current_champion_id="old", occurred_at=NOW
    )

    assert evaluation.passed
    assert event["to_state"] == "champion"
    assert event["replaces_candidate_id"] == "old"


@pytest.mark.unit
def test_failed_gates_require_audited_waiver():
    contract, result = _result(model_wape=0.30, completeness=0.5)
    evaluation = evaluate_candidate(
        result, contract, artifact_uri=None, actor="ci", evaluated_at=NOW
    )

    assert not evaluation.passed
    with pytest.raises(ValueError, match="waiver"):
        build_promotion_event(evaluation, actor="ci", occurred_at=NOW)
    event = build_promotion_event(
        evaluation, actor="reviewer", waiver_reason="incident recovery", occurred_at=NOW
    )
    assert event["reason"] == "incident recovery"
    assert event["from_state"] == "rejected"


@pytest.mark.unit
def test_baseline_gate_compares_average_wape_per_strategy():
    contract, result = _result()
    common = result.metrics.iloc[0].to_dict()
    result = BaselineBacktestResult(
        result.backtest_run_id,
        result.predictions,
        pd.DataFrame(
            [
                {**common, "baseline_name": contract.model_config_name, "wape": 0.08},
                {**common, "baseline_name": contract.model_config_name, "wape": 0.10},
                {**common, "baseline_name": "seasonal_naive_7d", "wape": 0.05},
                {**common, "baseline_name": "seasonal_naive_7d", "wape": 0.20},
                {**common, "baseline_name": "moving_average", "wape": 0.11},
                {**common, "baseline_name": "moving_average", "wape": 0.13},
            ]
        ),
    )

    evaluation = evaluate_candidate(
        result, contract, artifact_uri="gs://models/run-1/model.json", actor="ci", evaluated_at=NOW
    )
    improvement = next(
        check for check in evaluation.checks if check["check_name"] == "baseline_improvement"
    )

    # Model average is 0.09 and the best baseline average is 0.12. Comparing
    # against the single-origin 0.05 value would incorrectly reject this model.
    assert improvement["observed_value"] == pytest.approx(0.25)
    assert improvement["passed"] is True


@pytest.mark.unit
def test_evaluation_and_rollback_ids_are_retry_stable():
    contract, result = _result()
    first = evaluate_candidate(
        result, contract, artifact_uri="gs://model", actor="ci", evaluated_at=NOW
    )
    second = evaluate_candidate(
        result, contract, artifact_uri="gs://model", actor="ci", evaluated_at=NOW
    )
    assert first.candidate["candidate_id"] == second.candidate["candidate_id"]
    assert [c["promotion_check_id"] for c in first.checks] == [
        c["promotion_check_id"] for c in second.checks
    ]
    one = build_rollback_event(
        current_champion_id="new",
        restore_candidate_id="old",
        actor="ops",
        reason="drift",
        occurred_at=NOW,
    )
    two = build_rollback_event(
        current_champion_id="new",
        restore_candidate_id="old",
        actor="ops",
        reason="drift",
        occurred_at=NOW,
    )
    assert one["lifecycle_event_id"] == two["lifecycle_event_id"]


@pytest.mark.unit
def test_plan_is_write_free_and_exposes_configured_gates():
    plan = build_lifecycle_plan()
    assert plan["writes"] == []
    assert plan["promotion_gates"]["min_prediction_completeness"] == 0.98


@pytest.mark.unit
@patch("vertex.evaluation.model_lifecycle_persistence.insert_rows_idempotent")
def test_evaluation_persistence_uses_all_stable_ids(insert_rows):
    contract, result = _result()
    evaluation = evaluate_candidate(
        result, contract, artifact_uri="gs://model", actor="ci", evaluated_at=NOW
    )
    persist_evaluation(
        evaluation,
        candidate_table="p.d.candidates",
        check_table="p.d.checks",
        event_table="p.d.events",
        project_id="p",
    )
    assert insert_rows.call_args_list == [
        call([evaluation.candidate], "p.d.candidates", id_column="candidate_id", project_id="p"),
        call(evaluation.checks, "p.d.checks", id_column="promotion_check_id", project_id="p"),
        call([evaluation.event], "p.d.events", id_column="lifecycle_event_id", project_id="p"),
    ]


@pytest.mark.unit
def test_lifecycle_ddl_has_append_only_contract_tables():
    ddl = (
        contract_path := __import__("pathlib").Path(__file__).resolve().parents[1]
        / "ddl"
        / "vertex_bq_tables.sql"
    ).read_text(encoding="utf-8")
    assert contract_path.is_file()
    for table in ("model_candidates", "model_promotion_checks", "model_lifecycle_events"):
        assert f"CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.{table}`" in ddl


@pytest.mark.unit
@patch("vertex.evaluation.model_lifecycle_persistence.run_query")
def test_scheduled_workloads_resolve_latest_champion(run_query):
    contract = load_backtest_contract()
    run_query.return_value = pd.DataFrame([{"model_config_name": "favorita_store_h7_xgboost"}])
    resolved = resolve_champion_config_name(
        contract,
        candidate_table="p.d.candidates",
        event_table="p.d.events",
        project_id="p",
    )
    assert resolved == "favorita_store_h7_xgboost"
    query = run_query.call_args.args[0]
    assert "ORDER BY events.occurred_at DESC" in query
    assert "LIMIT 1" in query
