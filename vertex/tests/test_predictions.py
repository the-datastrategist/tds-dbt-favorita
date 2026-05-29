"""Tests for unified prediction row builder."""

from datetime import datetime

import pandas as pd
import pytest

from vertex.utils.predictions import build_standard_prediction_rows, new_predict_run_id


@pytest.mark.unit
class TestPredictionRows:
    def test_standard_columns(self):
        df = pd.DataFrame(
            {
                "entity_id": ["e1", "e2"],
                "store_id": [1, 2],
                "date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
                "sales": [10.0, 20.0],
            }
        )
        predictions = pd.Series([9.5, 19.0], index=df.index)
        run_at = datetime(2024, 6, 1, 12, 0, 0)
        predict_run_id = new_predict_run_id(
            model_id="mid",
            model_run_id="mrid",
            run_at=run_at,
        )
        rows = build_standard_prediction_rows(
            df,
            predictions,
            predict_run_id=predict_run_id,
            model_id="mid",
            model_run_id="mrid",
            config_name="favorita_xgboost_predict",
            model_family="favorita_store_daily",
            model_type="xgboost_sklearn",
            target_column="sales",
            run_at=run_at,
        )
        assert len(rows) == 2
        assert rows["model_id"].tolist() == ["mid", "mid"]
        assert rows["model_run_id"].tolist() == ["mrid", "mrid"]
        assert rows["prediction"].tolist() == [9.5, 19.0]
        assert rows["entity_id"].tolist() == ["e1", "e2"]

    def test_store_nbr_maps_to_bq_entity_columns(self):
        df = pd.DataFrame(
            {
                "store_nbr": [10, 20],
                "date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
                "sales_store": [100.0, 200.0],
            }
        )
        predictions = pd.Series([95.0, 195.0], index=df.index)
        run_at = datetime(2024, 6, 1, 12, 0, 0)
        rows = build_standard_prediction_rows(
            df,
            predictions,
            predict_run_id="pred-run",
            model_id="mid",
            model_run_id="mrid",
            config_name="favorita_xgboost_predict",
            model_family="favorita_store_daily",
            model_type="xgboost_sklearn",
            target_column="sales_store",
            run_at=run_at,
            id_columns=["store_nbr"],
        )
        assert rows["store_id"].tolist() == [10, 20]
        assert rows["entity_id"].tolist() == ["10", "20"]
