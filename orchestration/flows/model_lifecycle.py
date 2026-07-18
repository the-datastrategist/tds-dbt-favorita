"""Scheduled rolling-origin evaluation and governed model promotion."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from prefect import flow

from vertex.config.backtest_contract import DEFAULT_BACKTEST_CONTRACT_PATH, load_backtest_contract
from vertex.evaluation.model_lifecycle import build_promotion_event, evaluate_candidate
from vertex.evaluation.model_lifecycle_persistence import (
    persist_evaluation,
    persist_lifecycle_event,
    resolve_champion_candidate_id,
)
from vertex.evaluation.persistence import persist_backtest_result
from vertex.jobs.backtest import run_backtest
from vertex.utils.artifacts import resolve_latest_artifact

DEFAULT_TABLE_PREFIX = "tds-favorita.favorita"


def run_model_lifecycle_cycle(
    *,
    contract_path: str | Path = DEFAULT_BACKTEST_CONTRACT_PATH,
    actor: str = "prefect-model-lifecycle",
    project_id: str | None = None,
    artifact_uri: str | None = None,
    auto_promote: bool = True,
    table_prefix: str = DEFAULT_TABLE_PREFIX,
) -> dict[str, Any]:
    """Backtest, persist evidence, evaluate gates, and optionally promote."""
    if not actor:
        raise ValueError("actor is required")
    contract = load_backtest_contract(contract_path)
    if artifact_uri is None:
        gcs_model_path = str(contract.model_config["inputs"]["gcs_model_path"])
        artifact_uri, _ = resolve_latest_artifact(gcs_model_path, contract.model_config_name)

    result = run_backtest(contract_path=contract_path, use_bigquery=True, project_id=project_id)
    persist_backtest_result(
        result,
        contract,
        run_table=f"{table_prefix}.backtest_runs",
        prediction_table=f"{table_prefix}.backtest_predictions",
        metric_table=f"{table_prefix}.backtest_metrics",
        project_id=project_id,
    )
    evaluation = evaluate_candidate(
        result,
        contract,
        artifact_uri=artifact_uri,
        actor=actor,
    )
    candidate_table = f"{table_prefix}.model_candidates"
    check_table = f"{table_prefix}.model_promotion_checks"
    event_table = f"{table_prefix}.model_lifecycle_events"
    persist_evaluation(
        evaluation,
        candidate_table=candidate_table,
        check_table=check_table,
        event_table=event_table,
        project_id=project_id,
    )

    output: dict[str, Any] = {
        "backtest_run_id": result.backtest_run_id,
        "candidate_id": evaluation.candidate["candidate_id"],
        "checks_passed": evaluation.passed,
        "promoted": False,
    }
    if not evaluation.passed or not auto_promote:
        return output

    try:
        current_champion_id = resolve_champion_candidate_id(
            contract,
            candidate_table=candidate_table,
            event_table=event_table,
            project_id=project_id,
        )
    except LookupError:
        current_champion_id = None
    if current_champion_id == evaluation.candidate["candidate_id"]:
        output["promoted"] = True
        output["already_champion"] = True
        return output

    promotion = build_promotion_event(
        evaluation,
        actor=actor,
        current_champion_id=current_champion_id,
    )
    persist_lifecycle_event(promotion, event_table=event_table, project_id=project_id)
    output["promoted"] = True
    output["lifecycle_event_id"] = promotion["lifecycle_event_id"]
    output["replaces_candidate_id"] = current_champion_id
    return output


@flow(
    name="prefect-model-lifecycle",
    description="Run rolling-origin evidence, promotion gates, and champion replacement.",
    log_prints=True,
    retries=2,
    retry_delay_seconds=60,
)
def prefect_model_lifecycle_flow(
    contract_path: str = str(DEFAULT_BACKTEST_CONTRACT_PATH),
    actor: str = "prefect-model-lifecycle",
    project_id: str | None = None,
    artifact_uri: str | None = None,
    auto_promote: bool = True,
    table_prefix: str = DEFAULT_TABLE_PREFIX,
) -> dict[str, Any]:
    return run_model_lifecycle_cycle(
        contract_path=contract_path,
        actor=actor,
        project_id=project_id,
        artifact_uri=artifact_uri,
        auto_promote=auto_promote,
        table_prefix=table_prefix,
    )
