"""Scheduled champion scoring through validated atomic draft persistence."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pandas as pd
from prefect import flow

from vertex.config.backtest_contract import DEFAULT_BACKTEST_CONTRACT_PATH, load_backtest_contract
from vertex.config.feature_availability import (
    load_feature_availability_registry,
    registry_path_from_config,
)
from vertex.config.forecast_contract import load_forecast_contract
from vertex.config.hierarchy import load_hierarchy_config
from vertex.config.load_config import apply_job_step, load_model_config
from vertex.evaluation.forecast_pipeline import (
    ForecastRunPins,
    build_forecast_run_id,
    eligibility_snapshot_id,
    execute_forecast_pipeline,
)
from vertex.evaluation.forecast_pipeline_lock import acquire_forecast_lock, release_forecast_lock
from vertex.evaluation.forecast_pipeline_persistence import (
    persist_forecast_pipeline_exception,
    persist_forecast_pipeline_result,
)
from vertex.evaluation.model_lifecycle_persistence import (
    resolve_champion_candidate_id,
    resolve_champion_config_name,
)
from vertex.jobs.run import run_job_config
from vertex.utils.forecast_outputs import _feature_version
from vertex.utils.forecast_publication import (
    load_calibration_history,
    load_hierarchy_version,
    load_prediction_run,
)
from vertex.utils.run_context import get_git_sha

DEFAULT_TABLE_PREFIX = "tds-favorita.favorita"
DEFAULT_PUBLICATION_CONTRACT = (
    Path(__file__).resolve().parents[2] / "vertex/config/forecast_contract_publication.yaml"
)


def run_scheduled_forecast_pipeline_cycle(
    *,
    contract_path: str | Path = DEFAULT_PUBLICATION_CONTRACT,
    backtest_contract_path: str | Path = DEFAULT_BACKTEST_CONTRACT_PATH,
    actor: str = "prefect-scheduled-forecast-pipeline",
    table_prefix: str = DEFAULT_TABLE_PREFIX,
    project_id: str | None = None,
    source_predict_run_id: str | None = None,
    minimum_calibration_residuals: int = 20,
    hierarchy_config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Score the scoped champion, transform it, and expose one validated draft."""
    if not actor:
        raise ValueError("actor is required")
    contract = load_forecast_contract(contract_path)
    backtest_contract = load_backtest_contract(backtest_contract_path)
    candidate_table = f"{table_prefix}.model_candidates"
    event_table = f"{table_prefix}.model_lifecycle_events"
    champion_candidate_id = resolve_champion_candidate_id(
        backtest_contract,
        candidate_table=candidate_table,
        event_table=event_table,
        project_id=project_id,
    )
    config_name = resolve_champion_config_name(
        backtest_contract,
        candidate_table=candidate_table,
        event_table=event_table,
        project_id=project_id,
    )
    config = apply_job_step(load_model_config(config_name), "predict")
    if source_predict_run_id is None:
        scoring_config = copy.deepcopy(config)
        # Canonical drafts become visible only after all pipeline gates pass.
        scoring_config.setdefault("outputs", {}).pop("forecast_output_table", None)
        score_result = run_job_config(scoring_config)
        source_predict_run_id = str(score_result["predict_run_id"])
    predictions = load_prediction_run(
        source_predict_run_id,
        prediction_table=f"{table_prefix}.ml_model_predictions",
        project_id=project_id,
    )
    if predictions.empty:
        raise ValueError(f"prediction run {source_predict_run_id!r} produced no rows")
    model_run_ids = predictions["model_run_id"].dropna().astype(str).unique().tolist()
    if len(model_run_ids) != 1:
        raise ValueError("scheduled publication requires one pinned model_run_id")
    calibration = load_calibration_history(
        config_name,
        backtest_prediction_table=f"{table_prefix}.backtest_predictions",
        project_id=project_id,
    )
    cutoff = predictions["date"].max()
    code_sha = get_git_sha()
    if not code_sha:
        raise ValueError("code SHA is required for scheduled publication")
    feature_registry = load_feature_availability_registry(registry_path_from_config(config))
    pins = ForecastRunPins(
        champion_candidate_id=champion_candidate_id,
        model_run_id=model_run_ids[0],
        feature_version=_feature_version(config),
        feature_availability_hash=feature_registry.hash,
        data_cutoff=cutoff,
        source_cutoff_json={"model_input_data_cutoff": str(cutoff)},
        eligibility_snapshot_id=eligibility_snapshot_id(predictions, contract),
        code_sha=code_sha,
    )
    hierarchy_config = None
    hierarchy_nodes = None
    hierarchy_edges = None
    if contract.reconciliation_policy != "none":
        if hierarchy_config_path is None:
            raise ValueError("hierarchy_config_path is required for reconciled publication")
        hierarchy_config = load_hierarchy_config(hierarchy_config_path)
        hierarchy_nodes, hierarchy_edges = load_hierarchy_version(
            hierarchy_config.name,
            hierarchy_config.version,
            node_table=f"{table_prefix}.forecast_hierarchy_nodes",
            edge_table=f"{table_prefix}.forecast_hierarchy_edges",
            project_id=project_id,
        )
    planned_run_id = build_forecast_run_id(
        contract,
        forecast_origin=predictions["date"].iloc[0],
        pins=pins,
    )
    try:
        result = execute_forecast_pipeline(
            predictions,
            calibration,
            contract=contract,
            pins=pins,
            hierarchy_config=hierarchy_config,
            hierarchy_nodes=hierarchy_nodes,
            hierarchy_edges=hierarchy_edges,
            minimum_calibration_residuals=minimum_calibration_residuals,
        )
    except Exception as exc:
        persist_forecast_pipeline_exception(
            forecast_run_id=planned_run_id,
            error=exc,
            table_prefix=table_prefix,
            actor=actor,
            project_id=project_id,
        )
        raise
    forecast_origin = pd.Timestamp(predictions["date"].iloc[0]).to_pydatetime()
    lock_table = f"{table_prefix}.forecast_pipeline_locks"
    if not acquire_forecast_lock(
        contract_hash=contract.hash,
        forecast_origin=forecast_origin,
        owner_id=result.forecast_run_id,
        lock_table=lock_table,
        project_id=project_id,
    ):
        raise RuntimeError("another forecast publication run holds the contract/origin lock")
    try:
        persist_forecast_pipeline_result(
            result,
            contract=contract,
            pins=pins,
            table_prefix=table_prefix,
            actor=actor,
            project_id=project_id,
        )
    finally:
        release_forecast_lock(
            contract_hash=contract.hash,
            forecast_origin=forecast_origin,
            owner_id=result.forecast_run_id,
            lock_table=lock_table,
            project_id=project_id,
        )
    return {
        "forecast_run_id": result.forecast_run_id,
        "source_predict_run_id": source_predict_run_id,
        "champion_candidate_id": champion_candidate_id,
        "config_name": config_name,
        "draft_row_count": len(result.rows),
        "stage_count": len(result.stage_records),
        "validation_check_count": len(result.validation_checks),
        "run_status": "draft",
    }


@flow(
    name="prefect-scheduled-forecast-pipeline",
    description="Score the champion and create a calibrated, coherent, validated atomic draft.",
    log_prints=True,
    retries=2,
    retry_delay_seconds=60,
)
def prefect_scheduled_forecast_pipeline_flow(
    contract_path: str = str(DEFAULT_PUBLICATION_CONTRACT),
    backtest_contract_path: str = str(DEFAULT_BACKTEST_CONTRACT_PATH),
    actor: str = "prefect-scheduled-forecast-pipeline",
    table_prefix: str = DEFAULT_TABLE_PREFIX,
    project_id: str | None = None,
    source_predict_run_id: str | None = None,
    minimum_calibration_residuals: int = 20,
    hierarchy_config_path: str | None = None,
) -> dict[str, Any]:
    return run_scheduled_forecast_pipeline_cycle(
        contract_path=contract_path,
        backtest_contract_path=backtest_contract_path,
        actor=actor,
        table_prefix=table_prefix,
        project_id=project_id,
        source_predict_run_id=source_predict_run_id,
        minimum_calibration_residuals=minimum_calibration_residuals,
        hierarchy_config_path=hierarchy_config_path,
    )
