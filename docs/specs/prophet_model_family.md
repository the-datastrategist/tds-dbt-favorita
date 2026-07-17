{% docs spec_prophet_model_family %}

# SPEC: Prophet model family

**Status:** Shipped
**Roadmap reference:** [`vertex/README.md`](../../vertex/README.md#adding-a-model-family) — "Planned: `prophet`"; [`client_rollout.md`](../client_rollout.md#post-rollout-weeks-58-optional) — "Prophet / deep learning family | `vertex/models/registry.py` pattern"; README.md feature list — "Vertex AI: ... (Prophet planned)"

---

## Summary

This repo already supports two per-entity time-series model types (`arima`, `sarima`) via `vertex/models/timeseries/`, registered in [`vertex/models/registry.py`](../../vertex/models/registry.py). Prophet is the next family explicitly called out as "planned" in three places in the repo. This spec adds it **without SHAP explainability** (Prophet isn't a tree model — see [`vertex/utils/explain.py`](../../vertex/utils/explain.py) docstring, "Not intended for ARIMA/SARIMA, which are not tree models"; Prophet is in the same boat) and follows the extension steps already documented in `vertex/README.md` § "Adding a model family."

## Goals

- `prophet` as a new `model_type`, fittable per-entity (store) exactly like `arima`/`sarima` — same `train_days`, `forecast_horizon`, holdout-then-forward-forecast pattern.
- Zero special-casing in `vertex/jobs/run.py`, `submit.py`, or the KFP pipeline compiler — the registry dispatch pattern means adding a model family should only touch `vertex/models/`, `vertex/config/load_config.py` (if any Prophet-only validation is needed), `model_config.yaml`, and `vertex/tests/`.
- Prophet's native uncertainty intervals (`yhat_lower`/`yhat_upper`) populate the existing `prediction_lower`/`prediction_upper` columns on `ml_model_predictions` (already in the DDL, currently unused by ARIMA/SARIMA, which don't emit intervals today).

## Non-goals

- SHAP explainability for Prophet. `explain.enabled` validation in `load_config.py` (`SHAP_SUPPORTED_MODEL_TYPES = frozenset({"xgboost", "xgboost_sklearn", "random_forest"})`) already rejects non-tree types — Prophet configs should simply never set `explain.enabled: true`. If per-component attribution is wanted later, Prophet's own `plot_components`/regressor coefficients are a separate, non-SHAP mechanism and a separate spec.
- Multiplicative seasonality, holidays regressor wiring, or custom regressors in the first cut — ship additive-seasonality Prophet with the same `order`/`seasonal_order`-style simplicity ARIMA/SARIMA have today; richer configuration is a fast-follow once the family exists end-to-end.
- Deep learning families (also mentioned alongside Prophet in `client_rollout.md`'s "Prophet / deep learning family" row) — scope this spec to Prophet only; a deep-learning family (e.g. N-BEATS, TFT) would need GPU machine types and a materially different training loop, warranting its own spec.

## Implementation notes (as shipped)

Shipped as option (a) from § "Shared per-entity loop" — a standalone `vertex/models/prophet/`
package, `ts_common.py` untouched. Deviations from the letter of the design, and answers to the
two Open Questions:

- **Open question resolved — no CmdStan preinstall needed.** Spiked `pip install
  "prophet>=1.1,<2.0"` on both a bare `python:3.11-slim` venv and the actual project Docker image
  (`docker build --target runtime` + a fit/predict smoke test inside the built container, arm64).
  Both worked with zero `Dockerfile` changes — PyPI's `prophet`/`cmdstanpy` wheels ship a
  prebuilt CmdStan backend, and the `Dockerfile`'s existing `build-essential` (added for other
  reasons) was never actually exercised. Net image dependency footprint: ~38MB (`prophet` +
  `cmdstanpy` + `holidays`); `pandas`/`numpy` are already shared with the rest of the stack.
- **`include_in_run: true` dropped from the example config.** The spec's own YAML example sets
  it, but `vertex/tests/test_run_batch.py::test_includes_only_explicit_include_in_run` asserts
  the *exact* config list eligible for `make vertex-train` batch runs (currently
  `["favorita_store_n1d_xgboost"]` only) — same reason ARIMA/SARIMA don't set it either.
  `favorita_store_n1d_prophet` is runnable directly by name
  (`make vertex-train VERTEX_CONFIG=favorita_store_n1d_prophet`), just not part of the
  batch-all default, consistent with the other time-series configs.
- **Optimize's search space is `changepoint_prior_scale` only**, not a fuller grid — Non-goals
  already rules out multiplicative seasonality for v1, and `growth`/`yearly_seasonality`/
  `weekly_seasonality` don't have a small discrete search space that's obviously worth Optuna
  trials yet (they stay at their config defaults). Revisit once real client data shows
  `changepoint_prior_scale` alone isn't the binding constraint.
- **Holdout/forward scoring calls `Prophet.predict()` with the actual target dates** (from the
  entity's chronological test split, or `pd.date_range` off the last observed date for forward),
  rather than a step-count-based `forecast(steps=...)` like SARIMAX. This is more natural for
  Prophet's API (`predict(future_df)` takes explicit `ds` values) and sidesteps any
  frequency-inference mismatch for the holdout case specifically — forward-scope forecasting
  still uses `pd.infer_freq` exactly as `ts_common.predict_forward_rows` does.
- **Config omits `excluded_columns`** (present, unused, on the ARIMA/SARIMA config blocks —
  vestigial from the tabular-model template) since per-entity univariate time series never
  reference it.

## Design

### 1. Shared per-entity loop: generalize `ts_common.py` or duplicate it?

`fit_entity_models` / `predict_holdout_rows` / `predict_forward_rows` in [`ts_common.py`](../../vertex/models/timeseries/ts_common.py) are SARIMAX-coupled (`fitted.forecast(steps=...)`, `fitted.fittedvalues`) — Prophet's API is different (`Prophet().fit(df[['ds','y']])`, `.predict(future_df)` returning a dataframe with `yhat`/`yhat_lower`/`yhat_upper`). Two options:

- **(a) Duplicate**: new `vertex/models/prophet/prophet_common.py` with its own entity loop, reusing only the model-agnostic helpers already in `ts_common.py` (`prepare_panel`, `split_entity_frame`, `bundle_model_id`). Fast, but the train/test-split-per-entity loop (`for entity in entities: ... split_entity_frame(...) ... `) gets duplicated almost verbatim.
- **(b) Generalize** (preferred): extract the entity-loop *shape* out of `fit_entity_models` into a model-agnostic `fit_entity_models_generic(panel, ..., fit_fn, forecast_fn)` that takes a `fit_fn(train_series, **model_params) -> fitted` and `forecast_fn(fitted, steps) -> np.ndarray` pair, then make `fit_sarimax`/SARIMAX-specific forecast the ARIMA/SARIMA implementation of that interface, and add a parallel Prophet implementation. This is a larger refactor of shipped, tested code (`ts_common.py`, exercised by `predict_timeseries.py` / `optimize_timeseries.py` today) — worth doing only if there's confidence it won't destabilize ARIMA/SARIMA; otherwise ship (a) first and refactor once Prophet proves the interface is right (avoid speculative generalization from a single example).

**Recommendation:** ship (a) for the first cut — a working, tested `vertex/models/prophet/` package — and revisit (b) as a follow-on cleanup once Prophet is live and the shared shape is proven, not assumed.

### 2. New package: `vertex/models/prophet/`

```text
vertex/models/prophet/
  __init__.py
  prophet_common.py     # prepare_panel (reuse from ts_common), fit_prophet_entity, forecast helpers
  train_prophet.py       # run_train_prophet(config) — mirrors train_timeseries.py
  predict_prophet.py     # run_predict_prophet(config) — mirrors predict_timeseries.py
  optimize_prophet.py    # run_optimize_prophet(config) — mirrors optimize_timeseries.py
```

`fit_prophet_entity`:

```python
from prophet import Prophet

def fit_prophet_entity(train_series: pd.Series, **model_params) -> Prophet:
    df = train_series.rename("y").reset_index().rename(columns={train_series.index.name or "index": "ds"})
    model = Prophet(
        growth=model_params.get("growth", "linear"),
        seasonality_mode=model_params.get("seasonality_mode", "additive"),
        yearly_seasonality=model_params.get("yearly_seasonality", "auto"),
        weekly_seasonality=model_params.get("weekly_seasonality", "auto"),
        changepoint_prior_scale=model_params.get("changepoint_prior_scale", 0.05),
    )
    return model.fit(df)
```

`default_model_params("prophet")` (new branch in a Prophet-local `default_model_params`, or extend `ts_common.default_model_params` with a `prophet` case if kept shared): `growth`, `seasonality_mode`, `yearly_seasonality`, `weekly_seasonality`, `changepoint_prior_scale` — Prophet's own tunables, analogous to how `order`/`seasonal_order` are ARIMA/SARIMA's.

### 3. Registry

```python
# vertex/models/registry.py, in _register_all()
_REGISTRY[("prophet", "train")] = _lazy_runner(
    ("vertex.models.prophet.train_prophet", "run_train_prophet")
)
_REGISTRY[("prophet", "predict")] = _lazy_runner(
    ("vertex.models.prophet.predict_prophet", "run_predict_prophet")
)
_REGISTRY[("prophet", "optimize")] = _lazy_runner(
    ("vertex.models.prophet.optimize_prophet", "run_optimize_prophet")
)
```

Zero changes needed to `run_registered`, `vertex/jobs/run.py`, `submit.py`, or `submit_pipeline.py` — this is the entire point of the registry pattern already in place.

### 4. `model_config.yaml`

New config + pipeline entry, following the existing `favorita_store_n1d_arima` shape:

```yaml
configs:
  - name: favorita_store_n1d_prophet
    description: Prophet on store daily sales (per-entity, additive seasonality)
    model_family: favorita_store_daily
    model_type: prophet
    include_in_run: true
    job:
      step: train
    inputs:
      train_sql_query: |
        select * from `tds-favorita.favorita.int_sales_store_daily`
        qualify ntile(5) over (order by date desc) > 1
      predict_sql_query: |
        select * from `tds-favorita.favorita.int_sales_store_daily`
        qualify ntile(5) over (order by date desc) = 1
      target_column: sales_store_n1d
      date_column: date
      entity_column: store_nbr
      gcs_model_path: gs://favorita-vertex-models/
      forecast_horizon: 7
      train_days: 180
      test_size: 0.2
      model_params:
        growth: linear
        seasonality_mode: additive
        yearly_seasonality: auto
        weekly_seasonality: auto
        changepoint_prior_scale: 0.05
    outputs: {}

pipelines:
  favorita_prophet:
    config: favorita_store_n1d_prophet
    steps: [train, predict]
```

No `explain:` block — omission is the correct/default state (`explain_enabled()` returns `False` when absent).

### 5. Dependencies

Add `prophet>=1.1,<2.0` to `requirements.in` (pulls in `cmdstanpy`, which needs a compiled CmdStan backend — check the `Dockerfile`'s `build-essential` apt install already covers what CmdStan needs, or add `cmdstan` install step). This is the main integration risk — Prophet's native compiled-backend dependency is heavier than `statsmodels` (`arima`/`sarima`) or `shap` (pure Python + `numba`/`llvmlite`, already added for the explainability feature). Validate the Docker image build size/time impact before committing.

### 6. Tests

`vertex/tests/test_prophet.py` (or `test_prophet_common.py`), mirroring the existing `vertex/tests/` pattern for `arima`/`sarima` — fit on a small synthetic seasonal series, assert forecast shape and that `yhat_lower <= yhat <= yhat_upper`.

## Testing & validation

- Unit tests per above, marked `@pytest.mark.unit` (fast — small synthetic series, no GCP).
- `make vertex-validate-config MODEL=favorita_store_n1d_prophet` once the config exists.
- `make vertex-pipeline-compile VERTEX_PIPELINE=favorita_prophet` — confirms the KFP compile step (already exercised in CI via `favorita_arima`) works for Prophet's `train, predict` step list with no code changes needed in `vertex/pipelines/compile.py`.
- Docker-local `make vertex-train VERTEX_CONFIG=favorita_store_n1d_prophet` end-to-end before adding to `benchmarks.md`.

## Open questions

- ~~Ship the `ts_common.py` generalization (option b above) as part of this spec, or strictly as a follow-on?~~ **Resolved: follow-on.** Shipped option (a) — `ts_common.py` is untouched; revisit generalizing once a third per-entity family (or richer Prophet config) makes the shared shape worth extracting.
- ~~Does the Vertex Custom Job base image need a CmdStan preinstall step?~~ **Resolved: no.** See Implementation notes — `pip install prophet` on the existing `python:3.11-slim` base works as-is, confirmed both in a bare venv and inside the actual built `Dockerfile` image.

## Related documents

- [Specs index](README.md)
- `vertex/README.md` § "Adding a model family"
- [Accelerators — Vertex AI](../accelerators.md#vertex-ai-accelerators) — update "Model types" row once shipped
- [Benchmarks](../benchmarks.md) — add a Prophet row to the store-day results template once trained

{% enddocs %}
