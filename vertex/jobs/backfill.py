"""
Walk-forward backfill: train and predict per anchor date with point-in-time SQL.

  python -m vertex.jobs.backfill \\
    --config-name favorita_store_n1d_xgboost \\
    --start-date 2016-08-01 --end-date 2016-08-07

Makefile: make vertex-backfill START_DATE=... END_DATE=...

Prefect: import run_backfill from this module (see orchestration/flows/backfill.py).
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from vertex.config.backfill import (
    apply_backfill_overrides,
    iter_backfill_dates,
    parse_backfill_date,
    resolve_feature_table,
)
from vertex.config.load_config import (
    DEFAULT_CONFIG_PATH,
    apply_job_step,
    load_model_config,
    validate_config_for_step,
)
from vertex.jobs.run import run_job_config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BackfillIterationResult:
    as_of_date: str
    model_run_id: str
    predict_run_id: str
    prediction_count: int
    config_name: str


def run_backfill_iteration(
    config_name: str,
    as_of_date: date,
    *,
    config_path: str | Path | None = None,
    train_days: int | None = None,
    feature_table: str | None = None,
) -> BackfillIterationResult:
    """Train on history through as_of_date - 1 day, then predict at as_of_date."""
    base = load_model_config(config_name, config_path)
    resolved_train_days = int(
        train_days if train_days is not None else base.get("inputs", {}).get("train_days", 180)
    )
    table = feature_table or resolve_feature_table(base)

    train_config = apply_backfill_overrides(
        base,
        as_of_date=as_of_date,
        train_days=resolved_train_days,
        feature_table=table,
    )
    train_config = apply_job_step(train_config, "train")
    validate_config_for_step(train_config)

    train_result = run_job_config(train_config)
    model_run_id = train_result.get("model_run_id")
    if not model_run_id:
        raise ValueError(f"Train step did not return model_run_id for as_of_date={as_of_date}")

    predict_config = apply_backfill_overrides(
        base,
        as_of_date=as_of_date,
        train_days=resolved_train_days,
        feature_table=table,
    )
    predict_config = apply_job_step(predict_config, "predict")
    predict_config.setdefault("inputs", {})["model_run_id"] = model_run_id
    validate_config_for_step(predict_config)

    predict_result = run_job_config(predict_config)
    predict_run_id = predict_result.get("predict_run_id")
    if not predict_run_id:
        raise ValueError(f"Predict step did not return predict_run_id for as_of_date={as_of_date}")

    return BackfillIterationResult(
        as_of_date=as_of_date.isoformat(),
        model_run_id=str(model_run_id),
        predict_run_id=str(predict_run_id),
        prediction_count=int(predict_result.get("prediction_count", 0)),
        config_name=config_name,
    )


def run_backfill(
    config_name: str,
    start_date: str | date,
    end_date: str | date,
    *,
    config_path: str | Path | None = None,
    interval_days: int = 1,
    train_days: int | None = None,
    feature_table: str | None = None,
    dry_run: bool = False,
    max_iterations: int | None = None,
    stop_on_error: bool = True,
) -> list[BackfillIterationResult]:
    """
    Run train → predict for each anchor date in [start_date, end_date].

    This is the single entry point intended for CLI, Makefile, and Prefect flows.
    """
    start = parse_backfill_date(start_date)
    end = parse_backfill_date(end_date)
    dates = list(iter_backfill_dates(start, end, interval_days=interval_days))
    if max_iterations is not None:
        dates = dates[:max_iterations]

    if dry_run:
        base = load_model_config(config_name, config_path)
        table = feature_table or resolve_feature_table(base)
        resolved_train_days = int(
            train_days if train_days is not None else base.get("inputs", {}).get("train_days", 180)
        )
        for as_of in dates:
            cfg = apply_backfill_overrides(
                base,
                as_of_date=as_of,
                train_days=resolved_train_days,
                feature_table=table,
            )
            logger.info(
                "DRY RUN as_of=%s train_sql=%s predict_sql=%s",
                as_of.isoformat(),
                cfg["inputs"]["train_sql_query"].strip().replace("\n", " "),
                cfg["inputs"]["predict_sql_query"].strip().replace("\n", " "),
            )
        return []

    results: list[BackfillIterationResult] = []
    for index, as_of in enumerate(dates, start=1):
        logger.info(
            "Backfill iteration %s/%s config=%s as_of_date=%s",
            index,
            len(dates),
            config_name,
            as_of.isoformat(),
        )
        try:
            result = run_backfill_iteration(
                config_name,
                as_of,
                config_path=config_path,
                train_days=train_days,
                feature_table=feature_table,
            )
            results.append(result)
            logger.info(
                "Completed as_of=%s model_run_id=%s predict_run_id=%s predictions=%s",
                result.as_of_date,
                result.model_run_id,
                result.predict_run_id,
                result.prediction_count,
            )
        except Exception:
            logger.exception("Backfill failed for as_of_date=%s", as_of.isoformat())
            if stop_on_error:
                raise
    return results


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Walk-forward Vertex backfill (train + predict per anchor date)",
    )
    parser.add_argument("--config-path", "-f", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--config-name", "-c", required=True)
    parser.add_argument("--start-date", required=True, help="First anchor date (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="Last anchor date (YYYY-MM-DD)")
    parser.add_argument("--interval-days", type=int, default=1, help="Days between anchors")
    parser.add_argument(
        "--train-days",
        type=int,
        default=None,
        help="Training lookback window (default: inputs.train_days from config)",
    )
    parser.add_argument(
        "--feature-table",
        default=None,
        help="Override BigQuery feature table (project.dataset.table)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Log SQL only, do not run jobs")
    parser.add_argument("--max-iterations", type=int, default=None, help="Cap iterations (dev)")
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Log failures and proceed to the next date",
    )
    args = parser.parse_args()

    try:
        results = run_backfill(
            args.config_name,
            args.start_date,
            args.end_date,
            config_path=args.config_path,
            interval_days=args.interval_days,
            train_days=args.train_days,
            feature_table=args.feature_table,
            dry_run=args.dry_run,
            max_iterations=args.max_iterations,
            stop_on_error=not args.continue_on_error,
        )
    except Exception:
        logger.exception("Backfill failed")
        sys.exit(1)

    if args.dry_run:
        logger.info(
            "Dry run complete (%s dates)",
            len(
                list(
                    iter_backfill_dates(
                        parse_backfill_date(args.start_date),
                        parse_backfill_date(args.end_date),
                        interval_days=args.interval_days,
                    )
                )
            ),
        )
        return

    logger.info("Backfill finished successfully (%s iterations)", len(results))


if __name__ == "__main__":
    main()
