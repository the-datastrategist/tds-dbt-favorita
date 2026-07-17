"""Unit tests for SHAP feature attribution helpers."""

from datetime import datetime

import pandas as pd
import pytest
from sklearn.ensemble import RandomForestRegressor

from vertex.utils.explain import (
    STANDARD_EXPLAIN_COLUMNS,
    build_explain_rows,
    compute_tree_shap_top_features,
)
from vertex.utils.predictions import build_standard_prediction_rows


def _fit_random_forest():
    X_train = pd.DataFrame(
        {
            "feature_a": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            "feature_b": [6.0, 5.0, 4.0, 3.0, 2.0, 1.0],
        }
    )
    y_train = X_train["feature_a"] * 2 - X_train["feature_b"]
    model = RandomForestRegressor(n_estimators=5, max_depth=2, random_state=0)
    model.fit(X_train, y_train)
    return model


@pytest.mark.unit
class TestComputeTreeShapTopFeatures:
    def test_returns_per_row_top_k_sorted_by_abs_attribution(self):
        model = _fit_random_forest()
        model_input = pd.DataFrame({"feature_a": [1.0, 5.0], "feature_b": [6.0, 2.0]})

        top_features, base_value = compute_tree_shap_top_features(
            model, model_input, top_k_features=1
        )

        assert len(top_features) == 2
        assert isinstance(base_value, float)
        for row in top_features:
            assert len(row) == 1
            assert set(row[0].keys()) == {"feature", "attribution"}
            assert row[0]["feature"] in {"feature_a", "feature_b"}

    def test_top_k_features_limits_row_length(self):
        model = _fit_random_forest()
        model_input = pd.DataFrame({"feature_a": [3.0], "feature_b": [4.0]})

        top_features, _ = compute_tree_shap_top_features(model, model_input, top_k_features=1)
        full_features, _ = compute_tree_shap_top_features(model, model_input, top_k_features=10)

        assert len(top_features[0]) == 1
        assert len(full_features[0]) == 2
        # Sorted descending by |attribution|.
        attributions = [abs(item["attribution"]) for item in full_features[0]]
        assert attributions == sorted(attributions, reverse=True)


@pytest.mark.unit
class TestBuildExplainRows:
    def _prediction_rows(self):
        df = pd.DataFrame(
            {
                "store_nbr": [10, 20],
                "date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
                "sales_store": [100.0, 200.0],
            }
        )
        predictions = pd.Series([95.0, 195.0], index=df.index)
        run_at = datetime(2024, 6, 1, 12, 0, 0)
        return build_standard_prediction_rows(
            df,
            predictions,
            predict_run_id="pred-run",
            model_id="mid",
            model_run_id="mrid",
            config_name="favorita_store_n1d_rf",
            model_family="favorita_store_daily",
            model_type="random_forest",
            target_column="sales_store",
            run_at=run_at,
            id_columns=["store_nbr"],
        )

    def test_builds_aligned_rows_with_standard_columns(self):
        prediction_rows = self._prediction_rows()
        top_feature_attributions = [
            [{"feature": "feature_a", "attribution": 0.5}],
            [{"feature": "feature_b", "attribution": -0.3}],
        ]

        explain_rows = build_explain_rows(
            prediction_rows,
            top_feature_attributions=top_feature_attributions,
            base_value=1.23,
        )

        assert list(explain_rows.columns) == STANDARD_EXPLAIN_COLUMNS
        assert len(explain_rows) == 2
        assert explain_rows["prediction_id"].tolist() == prediction_rows["prediction_id"].tolist()
        assert explain_rows["predicted_value"].tolist() == [95.0, 195.0]
        assert (explain_rows["base_value"] == 1.23).all()
        assert explain_rows["top_feature_attributions"].tolist() == top_feature_attributions

    def test_length_mismatch_raises(self):
        prediction_rows = self._prediction_rows()
        with pytest.raises(ValueError, match="length must match"):
            build_explain_rows(
                prediction_rows,
                top_feature_attributions=[[{"feature": "feature_a", "attribution": 0.5}]],
                base_value=0.0,
            )
