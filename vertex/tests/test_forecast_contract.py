"""Tests for forecast contract validation."""

import pytest

from vertex.config.forecast_contract import validate_forecast_contract


def _valid_contract():
    return {
        "forecast": {
            "name": "store_daily_demand",
            "target": "demand_units",
            "target_unit": "units",
            "dimensions": ["store_id"],
            "frequency": "day",
            "timezone": "America/New_York",
            "issue_schedule": "0 6 * * *",
            "horizons": [7, 1],
            "quantiles": [0.9, 0.1, 0.5],
            "training_window_days": 180,
            "known_future_features": ["promotion"],
            "observed_features": ["sales"],
            "hierarchy": ["company", "store"],
            "reconciliation_policy": "none",
            "demand_policy": "observed_sales_only",
        }
    }


@pytest.mark.unit
class TestForecastContract:
    def test_valid_contract_normalizes_lists(self):
        contract = validate_forecast_contract(_valid_contract())

        assert contract.name == "store_daily_demand"
        assert contract.horizons == [1, 7]
        assert contract.quantiles == [0.1, 0.5, 0.9]
        assert contract.routing["fallback_order"]["cold_start"][0] == "global_model"
        assert contract.calibration["method"] == "symmetric_split_conformal"
        assert contract.hash

    def test_rejects_feature_availability_overlap(self):
        raw = _valid_contract()
        raw["forecast"]["observed_features"] = ["sales", "promotion"]

        with pytest.raises(ValueError, match="known-future and observed"):
            validate_forecast_contract(raw)

    def test_rejects_invalid_quantiles(self):
        raw = _valid_contract()
        raw["forecast"]["quantiles"] = [0.1, 1.2]

        with pytest.raises(ValueError, match="quantiles"):
            validate_forecast_contract(raw)

    @pytest.mark.parametrize("frequency", ["day", "week", "month"])
    def test_accepts_supported_period_frequencies(self, frequency):
        raw = _valid_contract()
        raw["forecast"]["frequency"] = frequency

        assert validate_forecast_contract(raw).frequency == frequency
