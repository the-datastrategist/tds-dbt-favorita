"""Tests for deterministic rolling-origin baseline scoring."""

import copy
from datetime import date
from typing import Any

import pandas as pd
import pytest

from vertex.config.backtest_contract import BacktestContract, load_backtest_contract
from vertex.evaluation.backtesting import (
    PREDICTION_COLUMNS,
    score_baselines,
    score_model_and_baselines,
)


def _contract(*, baselines=None, segment_columns=None) -> BacktestContract:
    default = load_backtest_contract()
    raw = copy.deepcopy(default.raw)
    raw["backtest"]["baselines"] = baselines or [
        "zero_demand",
        "last_observation",
        "seasonal_naive_7d",
        "moving_average",
    ]
    raw["backtest"]["segment_columns"] = segment_columns or []
    raw["backtest"]["moving_average_window"] = 7
    return BacktestContract(
        raw=raw,
        forecast_contract=default.forecast_contract,
        origins=(date(2016, 8, 1),),
    )


def _history() -> pd.DataFrame:
    dates = pd.date_range("2016-07-25", "2016-08-08", freq="D")
    rows: list[dict[str, Any]] = []
    for store_nbr, segment, values in (
        (1, "large", range(1, 16)),
        (2, "small", [0] * 15),
    ):
        rows.extend(
            {
                "store_nbr": store_nbr,
                "store_segment": segment,
                "date": day,
                "sales_store": value,
            }
            for day, value in zip(dates, values)
        )
    return pd.DataFrame(rows)


@pytest.mark.unit
class TestBaselineScoring:
    def test_scores_four_baselines_with_standard_records(self):
        result = score_baselines(_history(), _contract(), backtest_run_id="run-1")

        assert list(result.predictions.columns) == PREDICTION_COLUMNS
        assert len(result.predictions) == 8
        store_one = result.predictions[result.predictions["entity_key_json"] == '{"store_nbr":1}']
        predictions = dict(zip(store_one["baseline_name"], store_one["prediction"]))
        assert predictions == {
            "zero_demand": 0.0,
            "last_observation": 8.0,
            "seasonal_naive_7d": 8.0,
            "moving_average": 5.0,
        }
        assert store_one["actual"].unique().tolist() == [15.0]
        assert store_one["target_date"].unique().tolist() == ["2016-08-08"]

    def test_metrics_handle_zero_actual_demand(self):
        result = score_baselines(
            _history(), _contract(baselines=["zero_demand"]), backtest_run_id="run-1"
        )
        metric = result.metrics.iloc[0]

        assert metric["eligible_count"] == 2
        assert metric["prediction_count"] == 2
        assert metric["prediction_completeness"] == 1.0
        assert metric["wape"] == 1.0
        assert metric["mae"] == 7.5
        assert metric["mase"] == 15.0
        assert metric["rmsse"] == 15.0
        assert metric["bias"] == -7.5

    def test_missing_predictions_reduce_completeness(self):
        history = pd.concat(
            [
                _history(),
                pd.DataFrame(
                    [
                        {
                            "store_nbr": 3,
                            "store_segment": "small",
                            "date": "2016-08-08",
                            "sales_store": 5,
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
        result = score_baselines(
            history, _contract(baselines=["last_observation"]), backtest_run_id="run-1"
        )
        metric = result.metrics.iloc[0]

        assert metric["eligible_count"] == 3
        assert metric["prediction_count"] == 2
        assert metric["prediction_completeness"] == pytest.approx(2 / 3)

    def test_emits_aggregate_and_segment_metrics(self):
        result = score_baselines(
            _history(),
            _contract(baselines=["zero_demand"], segment_columns=["store_segment"]),
            backtest_run_id="run-1",
        )

        assert set(result.metrics["segment_key_json"]) == {
            "{}",
            '{"store_segment":"large"}',
            '{"store_segment":"small"}',
        }

    def test_missing_actual_is_not_eligible(self):
        history = _history()
        history.loc[
            (history["store_nbr"] == 2) & (history["date"] == pd.Timestamp("2016-08-08")),
            "sales_store",
        ] = None
        result = score_baselines(
            history, _contract(baselines=["zero_demand"]), backtest_run_id="run-1"
        )

        assert result.metrics.iloc[0]["eligible_count"] == 1

    def test_rejects_duplicate_entity_dates(self):
        history = pd.concat([_history(), _history().iloc[[0]]], ignore_index=True)

        with pytest.raises(ValueError, match="one row per entity and date"):
            score_baselines(history, _contract())

    def test_rejects_baseline_without_scorer(self):
        with pytest.raises(ValueError, match="do not have scorers"):
            score_baselines(_history(), _contract(baselines=["not_implemented"]))

    def test_same_period_last_year_uses_same_calendar_date(self):
        history = pd.concat(
            [
                _history(),
                pd.DataFrame(
                    [
                        {
                            "store_nbr": 1,
                            "store_segment": "large",
                            "date": "2015-08-08",
                            "sales_store": 42,
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )

        result = score_baselines(
            history,
            _contract(baselines=["same_period_last_year"]),
            backtest_run_id="run-1",
        )

        store_one = result.predictions[result.predictions["entity_key_json"] == '{"store_nbr":1}']
        assert store_one.iloc[0]["prediction"] == 42

    def test_intermittent_demand_baselines_are_deterministic(self):
        contract = _contract(baselines=["croston_sba", "tsb", "croston_sba_tsb"])
        first = score_baselines(_history(), contract, backtest_run_id="run-1")
        second = score_baselines(_history(), contract, backtest_run_id="run-1")

        pd.testing.assert_series_equal(
            first.predictions["prediction"], second.predictions["prediction"]
        )
        store_two = first.predictions[first.predictions["entity_key_json"] == '{"store_nbr":2}']
        assert store_two["prediction"].tolist() == [0.0, 0.0, 0.0]

    def test_scores_configured_model_on_same_origin_and_run(self):
        history = _history()
        history["sales_store_n7d"] = history["sales_store"].shift(-7)
        history["sales_store_l1d"] = range(len(history))
        seen: dict[str, pd.DataFrame] = {}

        def fit_predict(train_rows, predict_rows, _model_config):
            seen["train"] = train_rows
            seen["predict"] = predict_rows
            return pd.Series(14.0, index=predict_rows.index)

        result = score_model_and_baselines(
            history,
            _contract(baselines=["zero_demand"]),
            backtest_run_id="run-1",
            fit_predict=fit_predict,
        )

        model_rows = result.predictions[
            result.predictions["baseline_name"] == "favorita_store_h7_xgboost"
        ]
        assert len(model_rows) == 2
        assert model_rows["prediction"].tolist() == [14.0, 14.0]
        assert seen["train"]["date"].max() == date(2016, 7, 25)
        assert seen["predict"]["date"].unique().tolist() == [date(2016, 8, 1)]
        assert set(result.predictions["backtest_run_id"]) == {"run-1"}
        assert result.predictions["data_cutoff"].notna().all()
        assert result.predictions["source_cutoff_json"].notna().all()
        assert result.predictions["feature_availability_hash"].notna().all()

    def test_rejects_model_feature_snapshot_created_after_origin(self):
        history = _history()
        history["sales_store_n7d"] = history["sales_store"].shift(-7)
        history["promotion"] = 1
        history["promotion_plan_updated_at"] = pd.Timestamp("2016-08-02")

        with pytest.raises(ValueError, match="violates forecast cutoff"):
            score_model_and_baselines(
                history,
                _contract(baselines=["zero_demand"]),
                backtest_run_id="run-1",
                fit_predict=lambda train, predict, config: pd.Series(1.0, index=predict.index),
            )

    def test_generated_ids_are_stable_for_same_contract_and_input(self):
        first = score_baselines(_history(), _contract(baselines=["zero_demand"]))
        second = score_baselines(_history(), _contract(baselines=["zero_demand"]))

        assert first.backtest_run_id == second.backtest_run_id
        assert (
            first.predictions["prediction_id"].tolist()
            == second.predictions["prediction_id"].tolist()
        )

    def test_changed_actuals_generate_a_new_run_id(self):
        changed = _history()
        changed.loc[0, "sales_store"] = 999

        original = score_baselines(_history(), _contract(baselines=["zero_demand"]))
        updated = score_baselines(changed, _contract(baselines=["zero_demand"]))

        assert original.backtest_run_id != updated.backtest_run_id

    def test_all_zero_actuals_have_null_wape(self):
        history = _history()
        history["sales_store"] = 0
        result = score_baselines(
            history, _contract(baselines=["zero_demand"]), backtest_run_id="run-1"
        )

        assert pd.isna(result.metrics.iloc[0]["wape"])
        assert result.metrics.iloc[0]["mae"] == 0
        assert pd.isna(result.metrics.iloc[0]["mase"])
        assert pd.isna(result.metrics.iloc[0]["rmsse"])
