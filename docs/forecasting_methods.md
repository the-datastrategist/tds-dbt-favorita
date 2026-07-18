# Forecasting methods and routing

Forecast contracts define the required horizons and quantiles. Model configs define how
those forecasts are produced. A model must emit every horizon it claims to support.

## Horizon strategies

- **Direct** trains or selects a separate estimator for each horizon. It avoids recursive
  error accumulation and is the default for the configured tree models.
- **Recursive** repeatedly feeds one-step predictions back into later steps. It is useful
  when only a one-step estimator exists, but uncertainty and bias can accumulate.
- **Multi-output** predicts all horizons jointly. It can learn relationships between
  horizons but requires model-family support.
- **Global** pools multiple entities in one model and includes entity attributes. This is
  the preferred learned fallback for short-history entities.

Model configs express this under `inputs.horizon_strategy`, `inputs.horizons`, and
`inputs.quantiles`. The forecast contract remains authoritative.

## Probabilistic forecasts

Model-native intervals may be used when available. Other models use split-conformal
calibration from out-of-sample historical residuals. The implementation creates a
finite-sample-corrected symmetric central interval and writes P10, P50, and P90 to the
canonical output. Calibration residuals must be rolling-origin or holdout residuals; using
in-sample residuals understates uncertainty. Demand intervals are floored at zero.

Calibration is performed separately by horizon when residual behavior differs materially
across horizons. Production calibration should require enough recent residuals for a stable
estimate and should be monitored using empirical interval coverage and width.

## Intermittent demand and cold start

The series classifier records history length, nonzero observations, average demand
interval (ADI), and squared coefficient of variation. A series is cold-start when it has
fewer than the configured history or nonzero-observation minimums. A series is intermittent
when ADI is at least 1.32. Intermittent backtests include Croston/SBA and TSB methods.

Routing follows this order:

1. entity-specific model for sufficient regular history;
2. global model using entity attributes;
3. aggregate family/store forecast allocated to the entity;
4. seasonal or intermittent-rate baseline;
5. configured business default.

Every persisted forecast records `forecast_strategy`, `fallback_reason`, and
`confidence_flag`. A business default is always low confidence; entity models on sufficient
history are high confidence; learned or allocated fallbacks are medium confidence.

Example configuration:

```yaml
inputs:
  horizon_strategy: direct
  horizons: [1, 2, 3, 4, 5, 6, 7]
  quantiles: [0.1, 0.5, 0.9]
routing:
  minimum_history: 28
  minimum_nonzero_observations: 3
  intermittent_adi_threshold: 1.32
calibration:
  method: symmetric_split_conformal
  minimum_residuals: 20
```
