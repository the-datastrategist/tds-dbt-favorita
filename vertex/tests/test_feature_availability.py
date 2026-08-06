"""Tests for point-in-time feature availability validation."""

import re
from datetime import datetime

import pandas as pd
import pytest

from vertex.config.feature_availability import (
    feature_cutoff_metadata_from_frame,
    load_feature_availability_registry,
    registry_path_from_config,
    validate_feature_availability_registry,
    validate_feature_cutoffs_from_config,
    validate_model_features_from_config,
)


@pytest.mark.unit
class TestFeatureAvailabilityRegistry:
    def test_default_registry_validates_contract_features(self):
        registry = load_feature_availability_registry()
        registry.validate_forecast_contract(
            {
                "known_future_features": ["promotion", "holiday"],
                "observed_features": ["sales", "transactions"],
            }
        )
        assert registry.match("sales_store_l7d").availability == "observed_lagged"
        assert registry.match("sales_store_n7d").availability == "observed_after_period"
        assert registry.match("sales_store_n7d_cum").availability == "observed_after_period"

    def test_rejects_unregistered_model_feature(self):
        registry = load_feature_availability_registry()
        with pytest.raises(ValueError, match="Unregistered"):
            registry.validate_features(["not_in_registry"], context="test features")

    def test_rejects_observed_after_period_model_feature(self):
        registry = load_feature_availability_registry()
        with pytest.raises(ValueError, match="Observed-after-period"):
            registry.validate_features(["sales_store_n7d"], context="test features")

    def test_rejects_known_future_feature_without_cutoff_metadata(self):
        registry = validate_feature_availability_registry(
            {
                "features": {
                    "planned_price": {
                        "availability": "known_future",
                        "source_model": "stg_price_plan",
                    }
                }
            }
        )
        with pytest.raises(ValueError, match="missing source cutoff"):
            registry.validate_forecast_contract(
                {"known_future_features": ["planned_price"], "observed_features": []}
            )

    @pytest.mark.parametrize(
        ("raw", "message"),
        [
            ({"features": ["sales"]}, "features must be a mapping"),
            ({"features": {"sales": "observed_lagged"}}, "metadata must be a mapping"),
            (
                {"features": {"sales": {"availability": "sometimes"}}},
                "availability must be one of",
            ),
            (
                {
                    "features": {
                        "sales": {"availability": "observed_lagged", "max_target_lag_days": -1}
                    }
                },
                "max_target_lag_days must be >= 0",
            ),
            ({"patterns": {"pattern": "sales"}}, "patterns must be a list"),
            ({"patterns": ["sales_.*"]}, r"patterns\[0\] must be a mapping"),
            (
                {"patterns": [{"availability": "observed_lagged"}]},
                r"patterns\[0\]\.pattern is required",
            ),
            ({}, "must contain features or patterns"),
        ],
    )
    def test_rejects_invalid_registry_construction(self, raw, message):
        with pytest.raises(ValueError, match=message):
            validate_feature_availability_registry(raw)

    def test_rejects_invalid_regex_pattern(self):
        with pytest.raises(re.error):
            validate_feature_availability_registry(
                {"patterns": [{"pattern": "[", "availability": "observed_lagged"}]}
            )

    def test_exact_feature_takes_precedence_over_pattern(self):
        registry = validate_feature_availability_registry(
            {
                "features": {"sales_l7d": {"availability": "static_master_data"}},
                "patterns": [{"pattern": r"^sales_l\d+d$", "availability": "observed_lagged"}],
            }
        )

        assert registry.match("sales_l7d").availability == "static_master_data"
        assert registry.match("sales_l14d").availability == "observed_lagged"
        assert registry.match("unknown") is None

    @pytest.mark.parametrize(
        ("contract", "message"),
        [
            ({"known_future_features": ["unknown"]}, "unknown: not registered"),
            ({"known_future_features": ["sales"]}, "is not known-future safe"),
            ({"observed_features": ["unknown"]}, "unknown: not registered"),
            ({"observed_features": ["holiday"]}, "is not observed"),
        ],
    )
    def test_rejects_invalid_contract_feature_classification(self, contract, message):
        registry = load_feature_availability_registry()

        with pytest.raises(ValueError, match=message):
            registry.validate_forecast_contract(contract)

    def test_feature_cutoff_metadata_from_frame(self):
        registry = load_feature_availability_registry()
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-01", "2024-01-03"]),
                "sales_store_l7d": [1.0, 2.0],
            }
        )
        metadata = feature_cutoff_metadata_from_frame(
            frame,
            date_column="date",
            registry=registry,
            materialization_id="features-20240103",
        )
        assert metadata["data_cutoff"] == datetime(2024, 1, 3).isoformat()
        assert metadata["source_cutoff_json"]["date"] == datetime(2024, 1, 3).isoformat()
        assert metadata["feature_availability_hash"] == registry.hash
        assert metadata["feature_materialization_id"] == "features-20240103"

    def test_rejects_known_future_snapshot_loaded_after_forecast_origin(self):
        registry = load_feature_availability_registry()
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-03"]),
                "promotion": [1],
                "promotion_plan_updated_at": pd.to_datetime(["2024-01-04"]),
            }
        )

        with pytest.raises(ValueError, match="violates forecast cutoff"):
            registry.validate_frame_cutoffs(
                frame,
                ["promotion"],
                cutoff=datetime(2024, 1, 3),
                date_column="date",
                context="test snapshot",
            )

    def test_records_each_source_cutoff_for_safe_snapshot(self):
        registry = load_feature_availability_registry()
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-03"]),
                "promotion": [1],
                "promotion_plan_updated_at": pd.to_datetime(["2024-01-02 12:00:00"]),
            }
        )

        metadata = registry.validate_frame_cutoffs(
            frame,
            ["promotion"],
            cutoff=datetime(2024, 1, 3),
            date_column="date",
            context="test snapshot",
        )

        assert metadata["source_cutoff_json"] == {
            "date": datetime(2024, 1, 3).isoformat(),
            "promotion_plan_updated_at": datetime(2024, 1, 2, 12).isoformat(),
        }

    def test_rejects_empty_cutoff_frame(self):
        registry = load_feature_availability_registry()

        with pytest.raises(ValueError, match="empty feature frame"):
            registry.validate_frame_cutoffs(pd.DataFrame(), ["sales"], cutoff=datetime(2024, 1, 3))

    @pytest.mark.parametrize(
        ("frame", "message"),
        [
            (
                pd.DataFrame({"promotion": [1]}),
                "missing point-in-time metadata column",
            ),
            (
                pd.DataFrame({"promotion": [1], "promotion_plan_updated_at": [None]}),
                "null or invalid values",
            ),
        ],
    )
    def test_rejects_missing_or_invalid_source_metadata(self, frame, message):
        registry = load_feature_availability_registry()

        with pytest.raises(ValueError, match=message):
            registry.validate_frame_cutoffs(frame, ["promotion"], cutoff=datetime(2024, 1, 3))

    @pytest.mark.parametrize(
        ("frame", "cutoff", "message"),
        [
            (pd.DataFrame({"date": ["2024-01-01"]}), None, "invalid forecast cutoffs"),
            (
                pd.DataFrame({"other_date": ["2024-01-01"]}),
                "2024-01-03",
                "missing cutoff date column",
            ),
            (
                pd.DataFrame({"date": ["2024-01-04"]}),
                "2024-01-03",
                "contains rows later",
            ),
        ],
    )
    def test_rejects_invalid_frame_cutoffs(self, frame, cutoff, message):
        registry = load_feature_availability_registry()

        with pytest.raises(ValueError, match=message):
            registry.validate_frame_cutoffs(
                frame, ["sales_store_l7d"], cutoff=cutoff, date_column="date"
            )

    def test_supports_row_specific_cutoffs(self):
        registry = load_feature_availability_registry()
        frame = pd.DataFrame({"date": pd.to_datetime(["2024-01-01", "2024-01-02"])})
        cutoffs = pd.Series(pd.to_datetime(["2024-01-01", "2024-01-03"]), index=frame.index)

        metadata = registry.validate_frame_cutoffs(
            frame, ["sales_store_l7d"], cutoff=cutoffs, date_column="date"
        )

        assert metadata["data_cutoff"] == datetime(2024, 1, 3).isoformat()

    @pytest.mark.parametrize(
        ("config", "expected"),
        [
            (
                {
                    "inputs": {"feature_availability_path": "inputs.yaml"},
                    "outputs": {"feature_availability_path": "outputs.yaml"},
                    "feature_availability_path": "root.yaml",
                },
                "inputs.yaml",
            ),
            (
                {
                    "outputs": {"feature_availability_path": "outputs.yaml"},
                    "feature_availability_path": "root.yaml",
                },
                "outputs.yaml",
            ),
            ({"feature_availability_path": "root.yaml"}, "root.yaml"),
            ({}, None),
        ],
    )
    def test_registry_path_precedence(self, config, expected):
        assert registry_path_from_config(config) == expected

    def test_config_validation_wrappers(self):
        registry = validate_model_features_from_config(
            {}, ["sales_store_l7d"], context="wrapper test"
        )
        frame = pd.DataFrame({"date": pd.to_datetime(["2024-01-01"])})

        metadata = validate_feature_cutoffs_from_config(
            {},
            frame,
            ["sales_store_l7d"],
            cutoff="2024-01-01",
            date_column="date",
            context="wrapper test",
        )

        assert metadata["feature_availability_hash"] == registry.hash

    def test_cutoff_metadata_omits_unavailable_optional_values(self):
        metadata = feature_cutoff_metadata_from_frame(
            pd.DataFrame({"date": [None]}), date_column="date"
        )

        assert metadata == {}
