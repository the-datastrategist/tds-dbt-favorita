"""Backtest contract planning CLI.

This module intentionally stops at contract resolution and dry-run planning. The
scoring/evaluation runner will consume the same BacktestContract in the next slice.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from vertex.config.backtest_contract import DEFAULT_BACKTEST_CONTRACT_PATH, load_backtest_contract

logger = logging.getLogger(__name__)


def build_backtest_plan(contract_path: str | Path | None = None) -> list[dict[str, object]]:
    """Return one origin/horizon plan row per required backtest score."""
    contract = load_backtest_contract(contract_path)
    return contract.origin_plan_rows()


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
        "--dry-run",
        action="store_true",
        help="Print planned origin/horizon rows and exit",
    )
    args = parser.parse_args()

    plan = build_backtest_plan(args.contract_path)
    if args.dry_run:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return
    logger.info("Resolved %s backtest origin/horizon rows", len(plan))


if __name__ == "__main__":
    main()
