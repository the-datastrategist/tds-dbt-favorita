"""Model lifecycle planning, evaluation, promotion, and rollback CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from vertex.config.backtest_contract import DEFAULT_BACKTEST_CONTRACT_PATH, load_backtest_contract
from vertex.evaluation.model_lifecycle import (
    build_promotion_event,
    build_rollback_event,
    evaluate_candidate,
    model_scope,
)
from vertex.evaluation.model_lifecycle_persistence import (
    persist_evaluation,
    persist_lifecycle_event,
)
from vertex.jobs.backtest import run_backtest

DEFAULT_TABLE_PREFIX = "tds-favorita.favorita"


def build_lifecycle_plan(contract_path: str | Path | None = None) -> dict[str, Any]:
    contract = load_backtest_contract(contract_path)
    return {
        "action": "evaluate_candidate",
        "backtest_contract_name": contract.name,
        "model_config_name": contract.model_config_name,
        "model_scope_json": model_scope(contract),
        "promotion_gates": contract.promotion_gates,
        "writes": [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the model promotion lifecycle")
    parser.add_argument("action", choices=("plan", "evaluate", "promote", "rollback"))
    parser.add_argument("--contract-path", default=str(DEFAULT_BACKTEST_CONTRACT_PATH))
    parser.add_argument("--input-csv")
    parser.add_argument("--artifact-uri")
    parser.add_argument("--actor")
    parser.add_argument("--current-champion-id")
    parser.add_argument("--restore-candidate-id")
    parser.add_argument("--reason")
    parser.add_argument("--waiver-reason")
    parser.add_argument("--persist", action="store_true")
    parser.add_argument("--project-id")
    parser.add_argument("--candidate-table", default=f"{DEFAULT_TABLE_PREFIX}.model_candidates")
    parser.add_argument("--check-table", default=f"{DEFAULT_TABLE_PREFIX}.model_promotion_checks")
    parser.add_argument("--event-table", default=f"{DEFAULT_TABLE_PREFIX}.model_lifecycle_events")
    args = parser.parse_args()

    if args.action == "plan":
        print(json.dumps(build_lifecycle_plan(args.contract_path), indent=2, sort_keys=True))
        return
    if not args.actor:
        parser.error("--actor is required")
    if args.action == "rollback":
        if not args.current_champion_id or not args.restore_candidate_id or not args.reason:
            parser.error(
                "rollback requires --current-champion-id, --restore-candidate-id, and --reason"
            )
        event = build_rollback_event(
            current_champion_id=args.current_champion_id,
            restore_candidate_id=args.restore_candidate_id,
            actor=args.actor,
            reason=args.reason,
        )
        if args.persist:
            persist_lifecycle_event(event, event_table=args.event_table, project_id=args.project_id)
        print(json.dumps(event, default=str, indent=2, sort_keys=True))
        return
    if not args.input_csv:
        parser.error("evaluate and promote require --input-csv")
    contract = load_backtest_contract(args.contract_path)
    result = run_backtest(args.input_csv, args.contract_path)
    evaluation = evaluate_candidate(
        result, contract, artifact_uri=args.artifact_uri, actor=args.actor
    )
    if args.persist:
        persist_evaluation(
            evaluation,
            candidate_table=args.candidate_table,
            check_table=args.check_table,
            event_table=args.event_table,
            project_id=args.project_id,
        )
    output: dict[str, Any] = {
        "candidate": evaluation.candidate,
        "checks": evaluation.checks,
        "passed": evaluation.passed,
    }
    if args.action == "promote":
        promotion = build_promotion_event(
            evaluation,
            actor=args.actor,
            current_champion_id=args.current_champion_id,
            waiver_reason=args.waiver_reason,
        )
        if args.persist:
            persist_lifecycle_event(
                promotion, event_table=args.event_table, project_id=args.project_id
            )
        output["promotion_event"] = promotion
    print(json.dumps(output, default=str, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
