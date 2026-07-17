"""Tests for point-in-time feature availability validation."""

from datetime import datetime

import pandas as pd
import pytest

from vertex.config.feature_availability import (
    feature_cutoff_metadata_from_frame,
    load_feature_availability_registry,
    validate_feature_availability_registry,
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
