"""Tests for model-agnostic forecast calibration."""

import pandas as pd
import pytest

from vertex.evaluation.calibration import (
    attach_calibrated_intervals,
    calibrate_quantiles,
    fit_horizon_calibrator,
    probabilistic_metrics,
)


@pytest.mark.unit
def test_conformal_quantiles_are_deterministic_monotonic_and_nonnegative():
    result = calibrate_quantiles(
        [2.0, 10.0],
        [-1.0, 1.0, -2.0, 2.0, -3.0, 3.0, -4.0, 4.0, -5.0, 5.0],
        minimum_residuals=10,
    )

    assert result.residual_count == 10
    assert result.forecasts.to_dict("list") == {
        "prediction_p10": [0.0, 5.0],
        "prediction_p50": [2.0, 10.0],
        "prediction_p90": [7.0, 15.0],
    }
    assert (result.forecasts.diff(axis=1).iloc[:, 1:] >= 0).all(axis=None)


@pytest.mark.unit
def test_calibration_rejects_too_few_out_of_sample_residuals():
    with pytest.raises(ValueError, match="at least 5 residuals"):
        calibrate_quantiles([10.0], [1.0, 2.0], minimum_residuals=5)


@pytest.mark.unit
def test_attach_calibrated_intervals_uses_standard_prediction_columns():
    rows = pd.DataFrame({"prediction": [4.0]})
    result = attach_calibrated_intervals(rows, [-1.0, 1.0, -2.0, 2.0], minimum_residuals=4)
    assert result.loc[0, "prediction_lower"] == 2.0
    assert result.loc[0, "prediction"] == 4.0
    assert result.loc[0, "prediction_upper"] == 6.0


@pytest.mark.unit
def test_horizon_calibration_uses_horizon_sample_and_pooled_fallback():
    calibration = pd.DataFrame(
        {
            "horizon": [1] * 4 + [2] * 4,
            "actual": [9, 11, 8, 12, 15, 25, 10, 30],
            "prediction": [10] * 8,
        }
    )
    calibrator = fit_horizon_calibrator(calibration, minimum_residuals=4)
    future = pd.DataFrame({"forecast_horizon": [1, 2, 3], "prediction": [10.0, 10.0, 10.0]})

    result = calibrator.transform(future)

    assert result["prediction_lower"].tolist() == [8.0, 0.0, 0.0]
    assert result["prediction_upper"].tolist() == [12.0, 30.0, 30.0]
    assert result["prediction"].tolist() == [10.0, 10.0, 10.0]


@pytest.mark.unit
def test_probabilistic_metrics_report_pinball_coverage_width_and_error():
    rows = pd.DataFrame(
        {
            "actual": [5.0, 15.0, 25.0],
            "prediction_p10": [0.0, 10.0, 10.0],
            "prediction_p50": [5.0, 15.0, 20.0],
            "prediction_p90": [10.0, 20.0, 20.0],
        }
    )

    metrics = probabilistic_metrics(rows)

    assert metrics["observation_count"] == 3
    assert metrics["pinball_loss"] == pytest.approx(7 / 6)
    assert metrics["interval_coverage"] == pytest.approx(2 / 3)
    assert metrics["interval_width"] == pytest.approx(10.0)
    assert metrics["calibration_error"] == pytest.approx(abs(2 / 3 - 0.8))


@pytest.mark.unit
def test_conformal_quantiles_require_symmetric_pairs():
    with pytest.raises(ValueError, match="paired"):
        calibrate_quantiles([10.0], [-1.0, 1.0], quantiles=[0.1, 0.5], minimum_residuals=2)
