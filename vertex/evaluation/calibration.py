"""Model-agnostic conformal calibration and probabilistic forecast metrics."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

DEFAULT_QUANTILES = (0.1, 0.5, 0.9)


@dataclass(frozen=True)
class ConformalCalibration:
    """Calibrated forecasts and metadata describing their residual sample."""

    forecasts: pd.DataFrame
    residual_count: int
    calibration_method: str = "symmetric_split_conformal"


@dataclass(frozen=True)
class HorizonConformalCalibrator:
    """Split-conformal error distributions fitted independently by horizon."""

    residuals_by_horizon: Mapping[int, tuple[float, ...]]
    pooled_residuals: tuple[float, ...]
    minimum_residuals: int = 20
    lower_bound: float | None = 0.0

    def transform(
        self,
        prediction_rows: pd.DataFrame,
        *,
        quantiles: Sequence[float] = DEFAULT_QUANTILES,
        horizon_column: str = "forecast_horizon",
        prediction_column: str = "prediction",
    ) -> pd.DataFrame:
        """Attach intervals, using the matching horizon or the pooled fallback."""
        required = {horizon_column, prediction_column}
        missing = sorted(required.difference(prediction_rows.columns))
        if missing:
            raise ValueError(f"prediction_rows are missing required columns: {missing}")

        result = prediction_rows.copy()
        output_columns = [_quantile_column(value) for value in _validate_quantiles(quantiles)]
        for column in output_columns:
            result[column] = np.nan

        for horizon, index in result.groupby(horizon_column, dropna=False).groups.items():
            if pd.isna(horizon):
                raise ValueError("every prediction row must include a forecast horizon")
            residuals = self.residuals_by_horizon.get(int(horizon), self.pooled_residuals)
            calibrated = calibrate_quantiles(
                result.loc[index, prediction_column],
                residuals,
                quantiles=quantiles,
                minimum_residuals=self.minimum_residuals,
                lower_bound=self.lower_bound,
            ).forecasts
            calibrated.index = index
            result.loc[index, output_columns] = calibrated[output_columns]

        if tuple(float(value) for value in quantiles) == DEFAULT_QUANTILES:
            result["prediction_lower"] = result["prediction_p10"]
            result[prediction_column] = result["prediction_p50"]
            result["prediction_upper"] = result["prediction_p90"]
        return result


def _validate_quantiles(quantiles: Sequence[float]) -> tuple[float, ...]:
    values = tuple(float(value) for value in quantiles)
    if not values or any(value <= 0 or value >= 1 for value in values):
        raise ValueError("quantiles must contain values strictly between zero and one")
    if tuple(sorted(set(values))) != values:
        raise ValueError("quantiles must be unique and sorted")
    if 0.5 not in values:
        raise ValueError("quantiles must include 0.5 for the point forecast")
    for value in values:
        if value != 0.5 and not any(np.isclose(candidate, 1.0 - value) for candidate in values):
            raise ValueError("symmetric conformal quantiles must be paired around 0.5")
    return values


def _quantile_column(quantile: float) -> str:
    percentile = quantile * 100
    suffix = str(int(percentile)) if percentile.is_integer() else str(percentile).replace(".", "_")
    return f"prediction_p{suffix}"


def _finite_sample_quantile(values: np.ndarray, probability: float) -> float:
    """Return the conservative split-conformal empirical quantile."""
    corrected_probability = min(1.0, ceil((len(values) + 1) * probability) / len(values))
    return float(np.quantile(values, corrected_probability, method="higher"))


def calibrate_quantiles(
    point_predictions: Iterable[float],
    residuals: Iterable[float],
    *,
    quantiles: Sequence[float] = DEFAULT_QUANTILES,
    minimum_residuals: int = 20,
    lower_bound: float | None = 0.0,
) -> ConformalCalibration:
    """Create symmetric split-conformal quantiles from out-of-sample residuals."""
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
        if quantile == 0.5:
            values = points.copy()
        else:
            coverage = 2.0 * abs(quantile - 0.5)
            radius = _finite_sample_quantile(absolute_errors, coverage)
            values = points - radius if quantile < 0.5 else points + radius
        if lower_bound is not None:
            values = np.maximum(values, lower_bound)
        output[_quantile_column(quantile)] = values

    forecasts = pd.DataFrame(output).cummax(axis=1)
    return ConformalCalibration(forecasts=forecasts, residual_count=len(errors))


def fit_horizon_calibrator(
    calibration_rows: pd.DataFrame,
    *,
    actual_column: str = "actual",
    prediction_column: str = "prediction",
    horizon_column: str = "horizon",
    minimum_residuals: int = 20,
    lower_bound: float | None = 0.0,
) -> HorizonConformalCalibrator:
    """Fit horizon residual samples from strictly out-of-sample predictions."""
    required = {actual_column, prediction_column, horizon_column}
    missing = sorted(required.difference(calibration_rows.columns))
    if missing:
        raise ValueError(f"calibration_rows are missing required columns: {missing}")
    valid = calibration_rows.dropna(subset=list(required)).copy()
    valid["_residual"] = valid[actual_column].astype(float) - valid[prediction_column].astype(float)
    valid = valid[np.isfinite(valid["_residual"])]
    pooled = tuple(valid["_residual"].tolist())
    if len(pooled) < minimum_residuals:
        raise ValueError(
            f"conformal calibration requires at least {minimum_residuals} residuals; "
            f"received {len(pooled)}"
        )
    by_horizon = {
        int(horizon): tuple(group["_residual"].tolist())
        for horizon, group in valid.groupby(horizon_column)
        if len(group) >= minimum_residuals
    }
    return HorizonConformalCalibrator(by_horizon, pooled, minimum_residuals, lower_bound)


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
        prediction_rows["prediction"], residuals, minimum_residuals=minimum_residuals
    ).forecasts
    result = prediction_rows.copy()
    result["prediction_lower"] = calibrated["prediction_p10"].to_numpy()
    result["prediction"] = calibrated["prediction_p50"].to_numpy()
    result["prediction_upper"] = calibrated["prediction_p90"].to_numpy()
    return result


def probabilistic_metrics(
    forecast_rows: pd.DataFrame,
    *,
    actual_column: str = "actual",
    lower_column: str = "prediction_p10",
    median_column: str = "prediction_p50",
    upper_column: str = "prediction_p90",
) -> dict[str, float | int | None]:
    """Compute P10/P50/P90 pinball loss and central-interval calibration metrics."""
    required = {actual_column, lower_column, median_column, upper_column}
    missing = sorted(required.difference(forecast_rows.columns))
    if missing:
        raise ValueError(f"forecast_rows are missing required columns: {missing}")
    valid = forecast_rows.dropna(subset=list(required))
    if valid.empty:
        return {
            "observation_count": 0,
            "pinball_loss": None,
            "interval_coverage": None,
            "interval_width": None,
            "calibration_error": None,
        }
    actual = valid[actual_column].astype(float).to_numpy()
    lower = valid[lower_column].astype(float).to_numpy()
    median = valid[median_column].astype(float).to_numpy()
    upper = valid[upper_column].astype(float).to_numpy()
    if np.any(lower > median) or np.any(median > upper):
        raise ValueError("forecast quantiles must be monotonic")

    losses = []
    for quantile, prediction in ((0.1, lower), (0.5, median), (0.9, upper)):
        error = actual - prediction
        losses.append(np.maximum(quantile * error, (quantile - 1.0) * error))
    coverage = float(np.mean((actual >= lower) & (actual <= upper)))
    return {
        "observation_count": int(len(valid)),
        "pinball_loss": float(np.mean(np.column_stack(losses))),
        "interval_coverage": coverage,
        "interval_width": float(np.mean(upper - lower)),
        "calibration_error": abs(coverage - 0.8),
    }
