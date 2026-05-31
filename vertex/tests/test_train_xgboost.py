"""Unit tests for sklearn XGBoost training helpers."""

import json
from datetime import datetime

import numpy as np
import pandas as pd
import pytest
from xgboost import XGBRegressor

from vertex.models.xgboost.train_xgboost import (
    chronological_train_test_split,
    get_performance_metrics,
    get_train_metadata,
    metadata_to_bq_row,
    prepare_feature_matrix,
    train_sklearn_xgboost,
)


@pytest.mark.unit
class TestPrepareFeatureMatrix:
    def test_excluded_date_kept_for_split(self):
        rows = 20
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=rows, freq="D"),
                "sales": np.arange(rows, dtype=float),
                "store_id": 1,
                "feature_a": np.random.rand(rows),
            }
        )
        matrix, features, _dates = prepare_feature_matrix(
            df,
            target_column="sales",
            excluded_columns=["store_id", "date"],
            date_column="date",
        )
        assert "date" in matrix.columns
        assert "store_id" not in features
        assert "feature_a" in features

    def test_target_in_excluded_columns_still_available(self):
        rows = 10
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=rows, freq="D"),
                "sales": np.arange(rows, dtype=float),
                "feature_a": np.random.rand(rows),
            }
        )
        matrix, features, _dates = prepare_feature_matrix(
            df,
            target_column="sales",
            excluded_columns=["sales", "date"],
            date_column="date",
        )
        assert "sales" not in features
        assert "sales" in matrix.columns
        assert matrix["sales"].notna().all()


@pytest.mark.unit
class TestTrainSklearnXgboost:
    def test_fit_predict(self):
        X = pd.DataFrame({"x1": [1.0, 2.0, 3.0, 4.0], "x2": [0.5, 1.5, 2.5, 3.5]})
        y = pd.Series([1.0, 2.0, 3.0, 4.0])
        model = train_sklearn_xgboost(
            X,
            y,
            model_parameters={"n_estimators": 5, "max_depth": 2, "random_state": 0},
        )
        preds = model.predict(X)
        assert len(preds) == len(y)
        assert hasattr(model, "feature_importances_")


@pytest.mark.unit
class TestMetadata:
    def test_metadata_round_trip(self):
        X_train = pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]})
        X_test = pd.DataFrame({"x": [7.0, 8.0]})
        y_train = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        y_test = pd.Series([7.0, 8.0])
        model = XGBRegressor(
            n_estimators=5, max_depth=2, random_state=0, objective="reg:squarederror"
        )
        model.fit(X_train, y_train)

        metadata = get_train_metadata(
            model,
            X_train,
            X_test,
            y_train,
            y_test,
            config_name="test",
            target_column="y",
            run_at=datetime(2024, 1, 1),
        )
        row = metadata_to_bq_row(metadata)
        assert row["config_name"] == "test"
        assert row["model_type"] == "xgboost_sklearn"
        json.loads(row["train_performance"])
        json.loads(row["feature_importance"])


@pytest.mark.unit
class TestChronologicalSplit:
    def test_split_order(self):
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=10, freq="D"),
                "x": range(10),
                "sales": range(10),
            }
        )
        X_train, X_test, y_train, y_test = chronological_train_test_split(
            df,
            ["x"],
            "sales",
            test_size=0.2,
            date_column="date",
        )
        assert len(X_train) == 8
        assert len(X_test) == 2
        assert y_train.max() < y_test.min()


@pytest.mark.unit
class TestPerformanceMetrics:
    def test_perfect_predictions(self):
        y = np.array([1.0, 2.0, 3.0])
        metrics = get_performance_metrics(y, y)
        assert metrics["mae"] == pytest.approx(0.0)
        assert metrics["r2"] == pytest.approx(1.0)
