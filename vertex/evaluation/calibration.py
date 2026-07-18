"""Model-agnostic conformal calibration for demand forecasts."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Iterable, Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ConformalCalibration:
    """Calibrated forecasts and the residual sample used to create them."""

    forecasts: pd.DataFrame
    residual_count: int
    calibration_method: str = "symmetric_split_conformal"


def _validate_quantiles(quantiles: Sequence[float]) -> tuple[float, ...]:
    values = tuple(float(value) for value in quantiles)
    if not values or any(value <= 0 or value >= 1 for value in values):
        raise ValueError("quantiles must contain values strictly between zero and one")
    if tuple(sorted(set(values))) != values:
        raise ValueError("quantiles must be unique and sorted")
    if 0.5 not in values:
        raise ValueError("quantiles must include 0.5 for the point forecast")
    return values


def _finite_sample_quantile(values: np.ndarray, probability: float) -> float:
    """Return the conservative split-conformal empirical quantile."""
    if probability <= 0:
        return 0.0
    corrected_probability = min(1.0, ceil((len(values) + 1) * probability) / len(values))
    return float(np.quantile(values, corrected_probability, method="higher"))


def calibrate_quantiles(
    point_predictions: Iterable[float],
    residuals: Iterable[float],
    *,
    quantiles: Sequence[float] = (0.1, 0.5, 0.9),
    minimum_residuals: int = 20,
    lower_bound: float | None = 0.0,
) -> ConformalCalibration:
    """Calibrate symmetric quantiles from out-of-sample historical residuals.

    Residuals must come from predictions generated without training on their
    corresponding observations. Paired quantiles use the finite-sample corrected
    absolute-residual distribution; P50 remains the supplied point forecast.
    """
    requested = _validate_quantiles(quantiles)
    points = np.asarray(list(point_predictions), dtype=float)
    errors = np.asarray(list(residuals), dtype=float)
    errors = errors[np.isfinite(errors)]
    if not np.isfinite(points).all():
        raise ValueError("point_predictions must contain only finite values")
    if minimum_residuals < 1:
        raise ValueError("minimum_residuals must be positive")
    if len(errors) < minimum_residuals:
        raise ValueError(
            f"conformal calibration requires at least {minimum_residuals} residuals; "
            f"received {len(errors)}"
        )

    absolute_errors = np.abs(errors)
    output: dict[str, np.ndarray] = {}
    for quantile in requested:
        percentile = int(round(quantile * 100))
        if quantile == 0.5:
            values = points.copy()
        else:
            # For P10/P90, 2 * |q - .5| = .8, producing an 80% central interval.
            radius = _finite_sample_quantile(absolute_errors, 2.0 * abs(quantile - 0.5))
            values = points - radius if quantile < 0.5 else points + radius
        if lower_bound is not None:
            values = np.maximum(values, lower_bound)
        output[f"prediction_p{percentile}"] = values

    forecasts = pd.DataFrame(output)
    forecasts = forecasts.cummax(axis=1)
    return ConformalCalibration(forecasts=forecasts, residual_count=len(errors))


def attach_calibrated_intervals(
    prediction_rows: pd.DataFrame,
    residuals: Iterable[float],
    *,
    minimum_residuals: int = 20,
) -> pd.DataFrame:
    """Attach canonical P10/P50/P90 values to standard prediction rows."""
    if "prediction" not in prediction_rows.columns:
        raise ValueError("prediction_rows must include prediction")
    calibrated = calibrate_quantiles(
        prediction_rows["prediction"],
        residuals,
        minimum_residuals=minimum_residuals,
    ).forecasts
    result = prediction_rows.copy()
    result["prediction_lower"] = calibrated["prediction_p10"].to_numpy()
    result["prediction"] = calibrated["prediction_p50"].to_numpy()
    result["prediction_upper"] = calibrated["prediction_p90"].to_numpy()
    return result
