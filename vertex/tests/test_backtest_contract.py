"""Tests for backtest run contract validation."""

from datetime import date
from unittest.mock import patch

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
            "history_table": "tds-favorita.favorita.int_sales_store_daily",
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
        assert contract.model_type == "xgboost"
        assert contract.model_family == "favorita_store_daily"
        assert contract.horizons == [7]
        assert contract.train_window_days > 0
        assert contract.segment_columns == []
        assert contract.entity_columns == ["series_key"]
        assert contract.entity_key_json_column == "entity_key_json"
        assert contract.date_column == "period_start"
        assert contract.actual_column == "target_value"
        assert contract.history_table.endswith("forecast_features_store")
        assert contract.moving_average_window == 7
        assert contract.max_entities is None
        assert contract.forecast_contract.name == "store_daily_demand"
        assert contract.target == "demand_units"
        assert contract.grain == "store-day"
        assert contract.primary_metric == "wape"
        assert contract.metric_policy["evaluation_protocol"] == "rolling_origin"
        assert contract.promotion_gates["min_prediction_completeness"] == 0.98
        assert contract.hash
        assert len(contract.origin_plan_rows()) == len(contract.origins)

    def test_rejects_missing_contract_file(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Backtest contract not found"):
            load_backtest_contract(tmp_path / "missing.yaml")

    def test_rejects_non_mapping_yaml_root(self, tmp_path):
        contract_path = tmp_path / "backtest.yaml"
        contract_path.write_text("- not\n- a\n- mapping\n", encoding="utf-8")

        with pytest.raises(ValueError, match="Expected mapping at root"):
            load_backtest_contract(contract_path)

    def test_rejects_missing_backtest_mapping(self):
        with pytest.raises(ValueError, match="must contain a backtest mapping"):
            validate_backtest_contract({})

    def test_origin_policy_generates_sorted_dates(self):
        contract = validate_backtest_contract(_valid_contract())

        assert contract.origins == (
            date(2016, 8, 1),
            date(2016, 8, 8),
            date(2016, 8, 15),
        )
        assert contract.baselines == ["seasonal_naive_7d", "zero_demand"]

    def test_explicit_origins_are_supported(self):
        raw = _valid_contract()
        raw["backtest"].pop("origin_policy")
        raw["backtest"]["origins"] = ["2016-08-08", "2016-08-15"]

        contract = validate_backtest_contract(raw)

        assert contract.origins == (date(2016, 8, 8), date(2016, 8, 15))

    @pytest.mark.parametrize(
        ("field", "value", "message"),
        [
            ("train_window_days", 0, "train_window_days must be positive"),
            ("segment_columns", "store_id", "segment_columns must be a list"),
            ("segment_columns", [""], "segment_columns must contain non-empty strings"),
            ("entity_columns", [], "entity_columns must be a non-empty list"),
            ("entity_columns", [""], "entity_columns must contain non-empty strings"),
            ("date_column", "", "date_column must be a non-empty string"),
            ("moving_average_window", 0, "moving_average_window must be positive"),
            ("max_entities", 0, "max_entities must be positive"),
            ("baselines", [], "baselines must be a non-empty list"),
        ],
    )
    def test_rejects_invalid_backtest_fields(self, field, value, message):
        raw = _valid_contract()
        raw["backtest"][field] = value

        with pytest.raises(ValueError, match=message):
            validate_backtest_contract(raw)

    @pytest.mark.parametrize("field", ["name", "forecast_contract_path", "model_config_name"])
    def test_rejects_missing_required_scalars(self, field):
        raw = _valid_contract()
        raw["backtest"][field] = ""

        with pytest.raises(ValueError, match=rf"backtest\.{field} is required"):
            validate_backtest_contract(raw)

    def test_rejects_missing_origin_policy(self):
        raw = _valid_contract()
        raw["backtest"].pop("origin_policy")

        with pytest.raises(ValueError, match="origin_policy is required"):
            validate_backtest_contract(raw)

    def test_rejects_model_without_prediction_horizons(self):
        raw = _valid_contract()
        with patch(
            "vertex.config.backtest_contract.load_model_config",
            return_value={"model_type": "tree", "model_family": "xgboost", "inputs": {}},
        ):
            with pytest.raises(ValueError, match="must declare inputs.prediction_horizons"):
                validate_backtest_contract(raw)

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

    def test_rejects_invalid_promotion_completeness(self):
        raw = _valid_contract()
        raw["backtest"]["promotion_gates"]["min_prediction_completeness"] = 1.01

        with pytest.raises(ValueError, match="must be <= 1"):
            validate_backtest_contract(raw)

    @pytest.mark.parametrize(
        ("mutate", "message"),
        [
            (
                lambda spec: spec.update({"metric_policy": None}),
                "metric_policy is required",
            ),
            (
                lambda spec: spec["metric_policy"].update({"primary_metric": "accuracy"}),
                "primary_metric must be one of",
            ),
            (
                lambda spec: spec["metric_policy"].update({"selection_scope": []}),
                "selection_scope must be a non-empty list",
            ),
            (
                lambda spec: spec["promotion_gates"].update(
                    {"min_baseline_improvement_pct": -0.01}
                ),
                "min_baseline_improvement_pct must be >= 0",
            ),
            (
                lambda spec: spec["promotion_gates"].update(
                    {"require_reproducible_artifact": "yes"}
                ),
                "require_reproducible_artifact must be boolean",
            ),
        ],
    )
    def test_rejects_invalid_metric_and_promotion_policy(self, mutate, message):
        raw = _valid_contract()
        mutate(raw["backtest"])

        with pytest.raises(ValueError, match=message):
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
