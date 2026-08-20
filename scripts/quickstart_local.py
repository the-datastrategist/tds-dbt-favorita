#!/usr/bin/env python3
"""Generate a deterministic, credential-free demand forecast example."""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import date, timedelta
from pathlib import Path

STORES = {"store_01": 92.0, "store_02": 58.0, "store_03": 34.0}


def demand(store: str, day_index: int) -> float:
    base = STORES[store]
    weekday = (day_index % 7) - 3
    promotion = 18 if day_index in {10, 11, 24, 25, 38, 39} else 0
    trend = day_index * 0.35
    return round(max(0, base + weekday * 2.2 + promotion + trend), 2)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    start = date(2026, 1, 1)
    history: list[dict[str, object]] = []
    values: dict[str, list[float]] = {}
    for store in STORES:
        values[store] = [demand(store, index) for index in range(42)]
        for index, value in enumerate(values[store]):
            history.append(
                {
                    "date": start + timedelta(days=index),
                    "store_id": store,
                    "demand_units": value,
                    "lag_1": "" if index < 1 else values[store][index - 1],
                    "lag_7": "" if index < 7 else values[store][index - 7],
                    "rolling_mean_7": (
                        "" if index < 7 else round(sum(values[store][index - 7 : index]) / 7, 2)
                    ),
                }
            )
    forecasts: list[dict[str, object]] = []
    errors: list[float] = []
    actual_total = 0.0
    for store, series in values.items():
        for horizon in range(1, 8):
            actual = series[-8 + horizon]
            prediction = series[-15 + horizon]
            errors.append(abs(actual - prediction))
            actual_total += abs(actual)
            forecasts.append(
                {
                    "forecast_origin": start + timedelta(days=34),
                    "target_date": start + timedelta(days=34 + horizon),
                    "horizon": horizon,
                    "store_id": store,
                    "model": "seasonal_naive_7d",
                    "actual": actual,
                    "prediction_p50": prediction,
                    "prediction_p10": round(max(0, prediction * 0.85), 2),
                    "prediction_p90": round(prediction * 1.15, 2),
                }
            )
    wape = sum(errors) / actual_total
    benchmark = [
        {
            "model": "seasonal_naive_7d",
            "evaluation_protocol": "rolling_origin_holdout",
            "entities": len(STORES),
            "forecast_rows": len(forecasts),
            "wape": round(wape, 6),
        }
    ]
    write_csv(output_dir / "features.csv", history)
    write_csv(output_dir / "forecast_outputs.csv", forecasts)
    write_csv(output_dir / "benchmark.csv", benchmark)
    manifest = {
        "dataset": "deterministic_synthetic_demand_v1",
        "feature_rows": len(history),
        "forecast_rows": len(forecasts),
        "benchmark_wape": benchmark[0]["wape"],
        "files": ["features.csv", "forecast_outputs.csv", "benchmark.csv"],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if manifest["feature_rows"] != 126 or manifest["forecast_rows"] != 21:
        raise RuntimeError("quickstart row-count contract failed")
    if not math.isclose(float(manifest["benchmark_wape"]), 0.095177, abs_tol=1e-6):
        raise RuntimeError("quickstart benchmark contract failed")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/quickstart"))
    args = parser.parse_args()
    print(json.dumps(run(args.output_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
