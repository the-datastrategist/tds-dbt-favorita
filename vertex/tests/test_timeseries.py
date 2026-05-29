"""Unit tests for time-series helpers."""

import numpy as np
import pandas as pd
import pytest

from vertex.models.timeseries.ts_common import (
    fit_entity_models,
    normalize_order,
    prepare_panel,
    split_entity_frame,
)


@pytest.mark.unit
class TestTsCommon:
    def test_normalize_order(self):
        assert normalize_order([1, 1, 1], 3) == (1, 1, 1)

    def test_split_entity_frame(self):
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=10, freq="D"),
                "sales": range(10),
            }
        )
        train, test = split_entity_frame(df, test_size=0.2, date_column="date")
        assert len(train) == 8
        assert len(test) == 2

    def test_fit_entity_models_synthetic(self):
        rows = []
        for entity in ("a", "b"):
            dates = pd.date_range("2023-01-01", periods=80, freq="D")
            values = np.linspace(10, 20, len(dates)) + np.random.default_rng(0).normal(
                0, 0.1, len(dates)
            )
            for d, v in zip(dates, values):
                rows.append(
                    {"entity_id": entity, "date": d, "sales": float(v), "store_id": 1}
                )
        panel = prepare_panel(
            pd.DataFrame(rows),
            entity_column="entity_id",
            date_column="date",
            target_column="sales",
        )
        bundle, _train_perf, test_perf, entity_count, fitted = fit_entity_models(
            panel,
            entity_column="entity_id",
            date_column="date",
            target_column="sales",
            test_size=0.2,
            model_type="arima",
            model_params={
                "order": [1, 0, 0],
                "seasonal_order": [0, 0, 0, 0],
                "trend": "c",
                "maxiter": 25,
            },
            min_train_obs=30,
        )
        assert entity_count == 2
        assert fitted == 2
        assert "mae" in test_perf
        assert len(bundle["entity_models"]) == 2
