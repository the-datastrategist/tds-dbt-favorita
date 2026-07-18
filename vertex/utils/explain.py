"""SHAP feature attributions for tree-based Vertex predict jobs.

Supported for XGBoost and Random Forest (shap.TreeExplainer is exact and fast for
tree ensembles). Not intended for ARIMA/SARIMA, which are not tree models.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from vertex.utils.data_utils import get_hash

DEFAULT_TOP_K_FEATURES = 20

STANDARD_EXPLAIN_COLUMNS = [
    "explanation_id",
    "prediction_id",
    "predict_run_id",
    "model_run_id",
    "model_id",
    "config_name",
    "model_family",
    "model_type",
    "run_at",
    "run_date",
    "entity_id",
    "store_id",
    "product_id",
    "date",
    "predicted_value",
    "base_value",
    "top_feature_attributions",
    "model_artifact_uri",
]


def compute_tree_shap_top_features(
    model: Any,
    model_input: pd.DataFrame,
    *,
    top_k_features: int = DEFAULT_TOP_K_FEATURES,
) -> tuple[list[list[dict[str, float]]], float]:
    """
    Return (per-row top-k [{feature, attribution}] sorted by |attribution| desc, base_value).

    ``model_input`` rows must be in the same order as the caller's predictions/prediction
    rows, since the result list is aligned positionally (no index is carried through shap).
    """
    if model.__class__.__module__.startswith("xgboost"):
        # XGBoost's native contribution API is the source of truth for Tree SHAP
        # and avoids compatibility failures when SHAP lags XGBoost's model JSON
        # format (for example XGBoost 3.2 serializes base_score as "[5E-1]").
        import xgboost as xgb

        booster = model.get_booster()
        contributions = booster.predict(
            xgb.DMatrix(model_input, feature_names=list(model_input.columns)),
            pred_contribs=True,
        )
        if contributions.ndim != 2 or contributions.shape[1] != len(model_input.columns) + 1:
            raise ValueError(
                "Expected XGBoost SHAP contributions to contain one value per feature "
                "plus a bias column"
            )
        shap_values = contributions[:, :-1]
        base_value = contributions[0, -1]
    else:
        import shap  # heavy optional dependency; only imported when explain is enabled

        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(model_input)
        if isinstance(shap_values, list):
            shap_values = shap_values[0]
        base_value = explainer.expected_value
        if isinstance(base_value, (list, tuple, np.ndarray)):
            base_value = np.ravel(base_value)[0]

    feature_names = list(model_input.columns)
    top_features: list[list[dict[str, float]]] = []
    for row in shap_values:
        pairs = sorted(zip(feature_names, row), key=lambda item: abs(item[1]), reverse=True)
        top_features.append(
            [
                {"feature": name, "attribution": float(value)}
                for name, value in pairs[:top_k_features]
            ]
        )
    return top_features, float(base_value)


def build_explain_rows(
    prediction_rows: pd.DataFrame,
    *,
    top_feature_attributions: list[list[dict[str, float]]],
    base_value: float,
) -> pd.DataFrame:
    """
    Build favorita_model_explain rows aligned 1:1 (by position) with prediction_rows,
    reusing its ids/dimensions so explanations join back to predictions via prediction_id.
    """
    if len(top_feature_attributions) != len(prediction_rows):
        raise ValueError(
            "top_feature_attributions length must match prediction_rows "
            f"({len(top_feature_attributions)} != {len(prediction_rows)})"
        )
    frame = prediction_rows.reset_index(drop=True).copy()
    frame["explanation_id"] = [
        get_hash({"prediction_id": pid, "purpose": "explain"}) for pid in frame["prediction_id"]
    ]
    frame["predicted_value"] = frame["prediction"]
    frame["base_value"] = base_value
    frame["top_feature_attributions"] = top_feature_attributions
    return frame[STANDARD_EXPLAIN_COLUMNS]
