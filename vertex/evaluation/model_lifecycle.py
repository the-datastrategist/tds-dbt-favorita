"""Auditable model-candidate evaluation, promotion, and rollback records."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from vertex.config.backtest_contract import BacktestContract
from vertex.evaluation.backtesting import BaselineBacktestResult
from vertex.utils.data_utils import get_hash

MODEL_STATES = frozenset({"candidate", "champion", "rejected", "retired"})
LIFECYCLE_EVENTS = frozenset(
    {"registered", "evaluated", "promoted", "rejected", "rolled_back", "retired"}
)


@dataclass(frozen=True)
class PromotionEvaluation:
    candidate: dict[str, Any]
    checks: list[dict[str, Any]]
    event: dict[str, Any]

    @property
    def passed(self) -> bool:
        return all(bool(check["passed"]) for check in self.checks)


def model_scope(contract: BacktestContract) -> str:
    return json.dumps(
        {"target": contract.target, "grain": contract.grain, "horizons": contract.horizons},
        sort_keys=True,
        separators=(",", ":"),
    )


def _event(
    candidate_id: str,
    event_type: str,
    *,
    actor: str,
    occurred_at: datetime,
    from_state: str | None,
    to_state: str,
    reason: str | None = None,
    replaces_candidate_id: str | None = None,
) -> dict[str, Any]:
    if event_type not in LIFECYCLE_EVENTS or to_state not in MODEL_STATES:
        raise ValueError("invalid model lifecycle event")
    identity = {
        "candidate_id": candidate_id,
        "event_type": event_type,
        "from_state": from_state,
        "to_state": to_state,
        "replaces_candidate_id": replaces_candidate_id,
        "reason": reason,
    }
    return {
        "lifecycle_event_id": get_hash(identity),
        **identity,
        "actor": actor,
        "occurred_at": occurred_at,
    }


def evaluate_candidate(
    result: BaselineBacktestResult,
    contract: BacktestContract,
    *,
    artifact_uri: str | None,
    actor: str,
    evaluated_at: datetime | None = None,
) -> PromotionEvaluation:
    """Evaluate the configured model against its strongest scored baseline."""
    if not actor:
        raise ValueError("actor is required")
    evaluated_at = evaluated_at or datetime.now(timezone.utc)
    candidate_id = get_hash(
        {
            "backtest_run_id": result.backtest_run_id,
            "model_config_name": contract.model_config_name,
            "artifact_uri": artifact_uri,
            "scope": model_scope(contract),
        }
    )
    candidate = {
        "candidate_id": candidate_id,
        "model_scope_json": model_scope(contract),
        "model_config_name": contract.model_config_name,
        "model_family": contract.model_family,
        "model_type": contract.model_type,
        "backtest_run_id": result.backtest_run_id,
        "backtest_contract_hash": contract.hash,
        "artifact_uri": artifact_uri,
        "initial_state": "candidate",
        "registered_by": actor,
        "registered_at": evaluated_at,
    }

    metrics = result.metrics
    model = metrics[metrics["baseline_name"].eq(contract.model_config_name)]
    baselines = metrics[~metrics["baseline_name"].eq(contract.model_config_name)]
    if model.empty:
        raise ValueError("backtest result does not contain configured model metrics")

    def average(frame: pd.DataFrame, column: str) -> float | None:
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        return None if values.empty else float(values.mean())

    model_wape = average(model, "wape")
    baseline_wapes = pd.to_numeric(baselines["wape"], errors="coerce").dropna()
    best_baseline_wape = None if baseline_wapes.empty else float(baseline_wapes.min())
    improvement = (
        None
        if model_wape is None or best_baseline_wape in (None, 0)
        else (best_baseline_wape - model_wape) / best_baseline_wape
    )
    completeness = average(model, "prediction_completeness")
    model_predictions = result.predictions[
        result.predictions["baseline_name"].eq(contract.model_config_name)
    ]
    valid = model_predictions.dropna(subset=["actual", "prediction"])
    actual_mean = None if valid.empty else float(valid["actual"].abs().mean())
    bias = average(model, "bias")
    bias_pct = None if bias is None or actual_mean in (None, 0) else abs(bias) / actual_mean
    gates = contract.promotion_gates
    definitions = [
        (
            "baseline_improvement",
            improvement,
            float(gates.get("min_baseline_improvement_pct", 0)),
            improvement is not None
            and improvement >= float(gates.get("min_baseline_improvement_pct", 0)),
        ),
        (
            "absolute_bias",
            bias_pct,
            float(gates.get("max_bias_abs_pct", 1)),
            bias_pct is not None and bias_pct <= float(gates.get("max_bias_abs_pct", 1)),
        ),
        (
            "prediction_completeness",
            completeness,
            float(gates.get("min_prediction_completeness", 0)),
            completeness is not None
            and completeness >= float(gates.get("min_prediction_completeness", 0)),
        ),
        (
            "reproducible_artifact",
            1.0 if artifact_uri else 0.0,
            1.0 if gates.get("require_reproducible_artifact", False) else 0.0,
            bool(artifact_uri) or not gates.get("require_reproducible_artifact", False),
        ),
    ]
    checks = []
    for name, observed, threshold, passed in definitions:
        check = {
            "candidate_id": candidate_id,
            "check_name": name,
            "observed_value": observed,
            "threshold_value": threshold,
            "passed": bool(passed),
            "details_json": json.dumps({"gate": name}, sort_keys=True),
        }
        check["promotion_check_id"] = get_hash(check)
        checks.append(check)
    event = _event(
        candidate_id,
        "evaluated",
        actor=actor,
        occurred_at=evaluated_at,
        from_state="candidate",
        to_state="candidate" if all(c["passed"] for c in checks) else "rejected",
        reason=None if all(c["passed"] for c in checks) else "promotion gates failed",
    )
    return PromotionEvaluation(candidate, checks, event)


def build_promotion_event(
    evaluation: PromotionEvaluation,
    *,
    actor: str,
    current_champion_id: str | None = None,
    waiver_reason: str | None = None,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    if not evaluation.passed and not waiver_reason:
        raise ValueError("failed promotion gates require an audited waiver reason")
    return _event(
        evaluation.candidate["candidate_id"],
        "promoted",
        actor=actor,
        occurred_at=occurred_at or datetime.now(timezone.utc),
        from_state="candidate" if evaluation.passed else "rejected",
        to_state="champion",
        reason=waiver_reason,
        replaces_candidate_id=current_champion_id,
    )


def build_rollback_event(
    *,
    current_champion_id: str,
    restore_candidate_id: str,
    actor: str,
    reason: str,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    if not reason:
        raise ValueError("rollback reason is required")
    return _event(
        restore_candidate_id,
        "rolled_back",
        actor=actor,
        occurred_at=occurred_at or datetime.now(timezone.utc),
        from_state="retired",
        to_state="champion",
        reason=reason,
        replaces_candidate_id=current_champion_id,
    )
