"""Append-only persistence and champion resolution for model lifecycle records."""

from vertex.config.backtest_contract import BacktestContract
from vertex.evaluation.model_lifecycle import PromotionEvaluation, model_scope
from vertex.utils.bigquery_utils import insert_rows_idempotent, run_query, validate_bq_table_id


def persist_evaluation(
    evaluation: PromotionEvaluation,
    *,
    candidate_table: str,
    check_table: str,
    event_table: str,
    project_id: str | None = None,
) -> None:
    insert_rows_idempotent(
        [evaluation.candidate], candidate_table, id_column="candidate_id", project_id=project_id
    )
    insert_rows_idempotent(
        evaluation.checks, check_table, id_column="promotion_check_id", project_id=project_id
    )
    insert_rows_idempotent(
        [evaluation.event], event_table, id_column="lifecycle_event_id", project_id=project_id
    )


def persist_lifecycle_event(
    event: dict[str, object], *, event_table: str, project_id: str | None = None
) -> None:
    insert_rows_idempotent(
        [event], event_table, id_column="lifecycle_event_id", project_id=project_id
    )


def resolve_champion_config_name(
    contract: BacktestContract,
    *,
    candidate_table: str,
    event_table: str,
    project_id: str | None = None,
) -> str:
    """Resolve the latest atomic promotion/rollback event for a model scope."""
    candidate_table = validate_bq_table_id(candidate_table)
    event_table = validate_bq_table_id(event_table)
    scope = model_scope(contract).replace("\\", "\\\\").replace("'", "\\'")
    query = f"""
        SELECT candidates.model_config_name
        FROM `{event_table}` AS events
        INNER JOIN `{candidate_table}` AS candidates USING (candidate_id)
        WHERE TO_JSON_STRING(candidates.model_scope_json) = '{scope}'
          AND events.event_type IN ('promoted', 'rolled_back')
          AND events.to_state = 'champion'
        ORDER BY events.occurred_at DESC, events.lifecycle_event_id DESC
        LIMIT 1
    """
    rows = run_query(query, project_id=project_id)
    if rows.empty:
        raise LookupError(f"no champion is registered for model scope {model_scope(contract)}")
    return str(rows.iloc[0]["model_config_name"])


def resolve_champion_candidate_id(
    contract: BacktestContract,
    *,
    candidate_table: str,
    event_table: str,
    project_id: str | None = None,
) -> str:
    """Resolve the candidate ID from the latest champion-setting event."""
    candidate_table = validate_bq_table_id(candidate_table)
    event_table = validate_bq_table_id(event_table)
    scope = model_scope(contract).replace("\\", "\\\\").replace("'", "\\'")
    query = f"""
        SELECT events.candidate_id
        FROM `{event_table}` AS events
        INNER JOIN `{candidate_table}` AS candidates USING (candidate_id)
        WHERE TO_JSON_STRING(candidates.model_scope_json) = '{scope}'
          AND events.event_type IN ('promoted', 'rolled_back')
          AND events.to_state = 'champion'
        ORDER BY events.occurred_at DESC, events.lifecycle_event_id DESC
        LIMIT 1
    """
    rows = run_query(query, project_id=project_id)
    if rows.empty:
        raise LookupError(f"no champion is registered for model scope {model_scope(contract)}")
    return str(rows.iloc[0]["candidate_id"])
