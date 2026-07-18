"""Tests for model-agnostic forecast calibration."""

import pandas as pd
import pytest

from vertex.evaluation.calibration import (
    attach_calibrated_intervals,
    calibrate_quantiles,
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
