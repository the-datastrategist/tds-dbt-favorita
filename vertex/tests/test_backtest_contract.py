"""Tests for backtest run contract validation."""

from datetime import date

import pytest

from vertex.config.backtest_contract import (
    load_backtest_contract,
    validate_backtest_contract,
)
from vertex.jobs.backtest import build_backtest_plan


def _valid_contract():
    return {
        "backtest": {
            "name": "test_backtest",
            "forecast_contract_path": "vertex/config/forecast_contract.yaml",
            "model_config_name": "favorita_store_h7_xgboost",
            "origin_policy": {
                "start_date": "2016-08-01",
                "end_date": "2016-08-15",
                "interval_days": 7,
            },
            "horizons": [7],
            "train_window_days": 180,
            "entity_columns": ["store_nbr"],
            "date_column": "date",
            "actual_column": "sales_store",
            "segment_columns": ["store_id"],
            "moving_average_window": 7,
            "max_entities": 10,
            "baselines": ["seasonal_naive_7d", "zero_demand"],
            "metric_policy": {
                "primary_metric": "wape",
                "lower_is_better": True,
                "selection_scope": ["target", "grain", "horizon", "segment_key_json"],
            },
            "promotion_gates": {
                "min_baseline_improvement_pct": 0.05,
                "max_bias_abs_pct": 0.10,
                "min_prediction_completeness": 0.98,
            },
        }
    }


@pytest.mark.unit
class TestBacktestContract:
    def test_default_contract_loads_and_builds_plan(self):
        contract = load_backtest_contract()

        assert contract.name == "store_daily_rolling_origin"
        assert contract.model_config_name == "favorita_store_h7_xgboost"
        assert contract.horizons == [7]
        assert contract.forecast_contract.name == "store_daily_demand"
        assert len(contract.origin_plan_rows()) == len(contract.origins)

    def test_origin_policy_generates_sorted_dates(self):
        contract = validate_backtest_contract(_valid_contract())

        assert contract.origins == (
            date(2016, 8, 1),
            date(2016, 8, 8),
            date(2016, 8, 15),
        )
        assert contract.baselines == ["seasonal_naive_7d", "zero_demand"]

    def test_rejects_horizons_not_in_forecast_contract(self):
        raw = _valid_contract()
        raw["backtest"]["horizons"] = [99]

        with pytest.raises(ValueError, match="subset"):
            validate_backtest_contract(raw)

    def test_rejects_horizons_not_supported_by_model(self):
        raw = _valid_contract()
        raw["backtest"]["horizons"] = [1]

        with pytest.raises(ValueError, match="exactly match the model config"):
            validate_backtest_contract(raw)

    def test_rejects_unknown_baseline(self):
        raw = _valid_contract()
        raw["backtest"]["baselines"] = ["magic_baseline"]

        with pytest.raises(ValueError, match="Unsupported backtest baselines"):
            validate_backtest_contract(raw)

    def test_rejects_origins_and_origin_policy_together(self):
        raw = _valid_contract()
        raw["backtest"]["origins"] = ["2016-08-01"]

        with pytest.raises(ValueError, match="either origins or origin_policy"):
            validate_backtest_contract(raw)

    def test_build_backtest_plan_from_default_contract(self):
        plan = build_backtest_plan()

        assert plan
        assert plan[0]["backtest_contract_name"] == "store_daily_rolling_origin"
        assert plan[0]["forecast_contract_name"] == "store_daily_demand"
        assert plan[0]["horizon"] == 7
