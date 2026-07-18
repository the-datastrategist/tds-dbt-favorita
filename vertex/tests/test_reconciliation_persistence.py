"""Tests for reconciliation persistence records."""

from datetime import datetime, timezone

import pandas as pd
import pytest

from vertex.config.hierarchy import validate_hierarchy_config
from vertex.evaluation.reconciliation_persistence import build_reconciliation_records


@pytest.mark.unit
def test_builds_deterministic_append_only_records():
    config = validate_hierarchy_config(
        {
            "hierarchy": {
                "name": "retail",
                "version": "v1",
                "levels": [
                    {"name": "company", "keys": []},
                    {"name": "store", "keys": ["store_id"]},
                ],
                "reconciliation": {"method": "bottom_up", "tolerance_abs": 0.01},
            }
        }
    )
    rows = pd.DataFrame(
        {
            "node_id": ["company"],
            "level_name": ["company"],
            "forecast_origin": ["2026-01-01"],
            "target_date": ["2026-01-02"],
            "horizon": [1],
            "base_prediction_p10": [8.0],
            "base_prediction_p50": [10.0],
            "base_prediction_p90": [12.0],
            "prediction_p10": [9.0],
            "prediction_p50": [11.0],
            "prediction_p90": [13.0],
            "reconciliation_method": ["bottom_up"],
        }
    )
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)

    first_run, first_outputs = build_reconciliation_records(
        rows, config=config, forecast_run_id="forecast-1", started_at=started
    )
    second_run, second_outputs = build_reconciliation_records(
        rows, config=config, forecast_run_id="forecast-1", started_at=started
    )

    assert first_run["reconciliation_run_id"] == second_run["reconciliation_run_id"]
    assert (
        first_outputs.loc[0, "reconciliation_output_id"]
        == second_outputs.loc[0, "reconciliation_output_id"]
    )
    assert first_outputs.loc[0, "base_prediction_p50"] == 10.0
    assert first_outputs.loc[0, "prediction_p50"] == 11.0
