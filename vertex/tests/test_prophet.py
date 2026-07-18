"""Unit tests for Prophet entity-level helpers."""

import numpy as np
import pandas as pd
import pytest

from vertex.models.prophet.prophet_common import (
    default_model_params,
    fit_entity_models,
    fit_prophet_entity,
    predict_forward_rows,
    predict_holdout_rows,
)
from vertex.models.timeseries.ts_common import prepare_panel


def _synthetic_panel(entities=("a", "b"), periods=90):
    rows = []
    for i, entity in enumerate(entities):
        dates = pd.date_range("2023-01-01", periods=periods, freq="D")
        seasonal = 2 * np.sin(np.arange(periods) * 2 * np.pi / 7)
        trend = np.linspace(10 + i, 20 + i, periods)
        values = trend + seasonal
        for d, v in zip(dates, values):
            rows.append({"entity_id": entity, "date": d, "sales": float(v), "store_id": 1})
    return prepare_panel(
        pd.DataFrame(rows),
        entity_column="entity_id",
        date_column="date",
        target_column="sales",
    )


@pytest.mark.unit
class TestDefaultModelParams:
    def test_default_model_params_keys(self):
        params = default_model_params()
        assert params == {
            "growth": "linear",
            "seasonality_mode": "additive",
            "yearly_seasonality": "auto",
            "weekly_seasonality": "auto",
            "changepoint_prior_scale": 0.05,
        }


@pytest.mark.unit
class TestFitProphetEntity:
    def test_fit_returns_fitted_model_with_uncertainty(self):
        dates = pd.date_range("2023-01-01", periods=60, freq="D")
        values = 10 + 2 * np.sin(np.arange(60) * 2 * np.pi / 7)
        series = pd.Series(values, index=dates)
        fitted = fit_prophet_entity(series, **default_model_params())
        forecast = fitted.predict(pd.DataFrame({"ds": dates[-7:]}))
        assert (forecast["yhat_lower"] <= forecast["yhat"]).all()
        assert (forecast["yhat"] <= forecast["yhat_upper"]).all()


@pytest.mark.unit
class TestFitEntityModels:
    def test_fit_entity_models_synthetic(self):
        panel = _synthetic_panel()
        bundle, train_perf, test_perf, entity_count, fitted = fit_entity_models(
            panel,
            entity_column="entity_id",
            date_column="date",
            target_column="sales",
            test_size=0.2,
            model_params=default_model_params(),
            min_train_obs=30,
        )
        assert entity_count == 2
        assert fitted == 2
        assert "mae" in train_perf
        assert "mae" in test_perf
        assert len(bundle["entity_models"]) == 2
        assert bundle["model_type"] == "prophet"

    def test_min_train_obs_skips_short_entities(self):
        panel = _synthetic_panel(entities=("a",), periods=10)
        with pytest.raises(ValueError, match="No entity models"):
            fit_entity_models(
                panel,
                entity_column="entity_id",
                date_column="date",
                target_column="sales",
                test_size=0.2,
                model_params=default_model_params(),
                min_train_obs=30,
            )


@pytest.mark.unit
class TestPredictRows:
    def _fitted_bundle(self):
        panel = _synthetic_panel()
        bundle, _train_perf, _test_perf, _entity_count, _fitted = fit_entity_models(
            panel,
            entity_column="entity_id",
            date_column="date",
            target_column="sales",
            test_size=0.2,
            model_params=default_model_params(),
            min_train_obs=30,
        )
        return panel, bundle

    def test_predict_holdout_rows_has_uncertainty_interval(self):
        panel, bundle = self._fitted_bundle()
        scored = predict_holdout_rows(
            panel,
            bundle,
            entity_column="entity_id",
            date_column="date",
            target_column="sales",
            test_size=0.2,
        )
        assert not scored.empty
        assert {"prediction", "prediction_lower", "prediction_upper", "actual"} <= set(
            scored.columns
        )
        assert (scored["prediction_lower"] <= scored["prediction"]).all()
        assert (scored["prediction"] <= scored["prediction_upper"]).all()

    def test_predict_forward_rows_has_uncertainty_interval(self):
        panel, bundle = self._fitted_bundle()
        scored = predict_forward_rows(
            panel,
            bundle,
            entity_column="entity_id",
            date_column="date",
            target_column="sales",
            forecast_horizon=7,
            id_columns=["entity_id"],
        )
        assert len(scored) == 7 * 2
        assert scored["actual"].isna().all()
        assert (scored["prediction_lower"] <= scored["prediction"]).all()
        assert (scored["prediction"] <= scored["prediction_upper"]).all()
        assert set(scored["forecast_horizon"]) == set(range(1, 8))
