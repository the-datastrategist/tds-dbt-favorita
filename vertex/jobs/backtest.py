"""Backtest contract planning and local deterministic-baseline scoring CLI."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from vertex.config.backtest_contract import DEFAULT_BACKTEST_CONTRACT_PATH, load_backtest_contract
from vertex.evaluation.backtesting import BaselineBacktestResult, score_baselines

logger = logging.getLogger(__name__)


def build_backtest_plan(contract_path: str | Path | None = None) -> list[dict[str, object]]:
    """Return one origin/horizon plan row per required backtest score."""
    contract = load_backtest_contract(contract_path)
    return contract.origin_plan_rows()


def run_baseline_backtest(
    input_csv: str | Path,
    contract_path: str | Path | None = None,
) -> BaselineBacktestResult:
    """Load local history and score all baselines declared by the contract."""
    contract = load_backtest_contract(contract_path)
    return score_baselines(pd.read_csv(input_csv), contract)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Resolve a backtest contract plan")
    parser.add_argument(
        "--contract-path",
        "-f",
        default=str(DEFAULT_BACKTEST_CONTRACT_PATH),
        help="Path to backtest contract YAML",
    )
    parser.add_argument(
        "--input-csv",
        help="Local historical actuals used to execute deterministic baseline scoring",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned origin/horizon rows and exit",
    )
    args = parser.parse_args()

    plan = build_backtest_plan(args.contract_path)
    if args.dry_run:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return
    if not args.input_csv:
        parser.error("--input-csv is required unless --dry-run is used")
    result = run_baseline_backtest(args.input_csv, args.contract_path)
    metric_records = json.loads(result.metrics.to_json(orient="records"))
    print(
        json.dumps(
            {
                "backtest_run_id": result.backtest_run_id,
                "prediction_count": len(result.predictions),
                "metrics": metric_records,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
