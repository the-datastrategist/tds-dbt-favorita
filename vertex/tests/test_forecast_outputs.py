"""Tests for canonical forecast output row builder."""

from datetime import datetime

import pandas as pd
import pytest

from vertex.config.forecast_contract import validate_forecast_contract
from vertex.utils.forecast_outputs import build_forecast_output_rows
from vertex.utils.predictions import build_standard_prediction_rows


@pytest.mark.unit
def test_build_forecast_output_rows_from_standard_predictions():
    contract = validate_forecast_contract(
        {
            "forecast": {
                "name": "store_daily_demand",
                "target": "demand_units",
                "target_unit": "units",
                "dimensions": ["store_id"],
                "frequency": "day",
                "timezone": "America/New_York",
                "issue_schedule": "0 6 * * *",
                "horizons": [7],
                "quantiles": [0.1, 0.5, 0.9],
                "training_window_days": 180,
                "known_future_features": ["promotion"],
                "observed_features": ["sales"],
                "hierarchy": ["company", "store"],
                "reconciliation_policy": "none",
                "demand_policy": "observed_sales_only",
            }
        }
    )
    source = pd.DataFrame(
        {
            "store_nbr": [1, 2],
            "date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "sales": [10.0, 20.0],
        }
    )
    predictions = build_standard_prediction_rows(
        source,
        pd.Series([11.0, 21.0], index=source.index),
        predict_run_id="predict-run",
        model_id="model",
        model_run_id="model-run",
        config_name="config",
        model_family="family",
        model_type="xgboost",
        target_column="sales",
        run_at=datetime(2024, 2, 1, 6, 0, 0),
        id_columns=["store_nbr"],
        forecast_horizon=7,
    )

    rows = build_forecast_output_rows(
        predictions,
        contract=contract,
        feature_version="features-v1",
        code_sha="abc123",
        data_cutoff=datetime(2024, 1, 31, 23, 59, 59),
    )

    assert rows["forecast_contract_name"].tolist() == ["store_daily_demand"] * 2
    assert rows["forecast_run_id"].tolist() == ["predict-run"] * 2
    assert rows["horizon"].tolist() == [7, 7]
    assert rows["prediction_p50"].tolist() == [11.0, 21.0]
    assert rows["statistical_forecast"].tolist() == [11.0, 21.0]
    assert rows["forecast_status"].tolist() == ["draft", "draft"]
    assert rows["feature_version"].tolist() == ["features-v1", "features-v1"]
    assert rows["code_sha"].tolist() == ["abc123", "abc123"]
