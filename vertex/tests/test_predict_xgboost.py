"""Unit tests for XGBoost prediction helpers."""

import pandas as pd
import pytest
from xgboost import XGBRegressor

from vertex.models.xgboost.predict_xgboost import prepare_prediction_features


@pytest.mark.unit
class TestPreparePredictionFeatures:
    def test_aligns_to_manifest_when_columns_missing_from_data(self):
        """Predict rows may lack some training features (all-null lags on test split)."""
        df = pd.DataFrame(
            {
                "feature_a": [1.0, 2.0],
                "sales_store": [10.0, 20.0],
            }
        )
        manifest = {
            "features": ["feature_a", "feature_b", "pct_sales_store_on_promotion"],
        }
        X = prepare_prediction_features(
            df,
            manifest,
            target_column="sales_store",
            excluded_columns=[],
        )
        assert list(X.columns) == manifest["features"]
        assert X["feature_b"].tolist() == [0.0, 0.0]
        assert X["pct_sales_store_on_promotion"].tolist() == [0.0, 0.0]

    def test_xgboost_accepts_aligned_matrix(self):
        """Model trained on more features than appear in a later scoring frame."""
        train_df = pd.DataFrame(
            {
                "x": [1.0, 2.0, 3.0],
                "z": [0.1, 0.2, 0.3],
                "sales_store": [1.0, 2.0, 3.0],
            }
        )
        manifest_features = ["x", "z"]
        model = XGBRegressor(n_estimators=3, max_depth=2, random_state=0)
        model.fit(train_df[manifest_features], train_df["sales_store"])

        predict_df = pd.DataFrame({"x": [4.0, 5.0], "sales_store": [4.0, 5.0]})
        X_pred = prepare_prediction_features(
            predict_df,
            {"features": manifest_features},
            target_column="sales_store",
            excluded_columns=[],
        )
        preds = model.predict(X_pred)
        assert len(preds) == len(predict_df)
