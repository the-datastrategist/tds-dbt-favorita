{% docs benchmarks %}

# Model benchmarks

Compare **BigQuery ML** and **Vertex AI** models on shared holdout metrics. Use this page in client conversations to justify algorithm and platform choices with data.

---

## Benchmark dimensions

| Dimension | Values in this repo |
|-----------|---------------------|
| **Platform** | `bqml`, `vertex` |
| **Model type** | `BOOSTED_TREE_REGRESSOR`, `xgboost`, `random_forest`, `arima`, `sarima` |
| **Grain** | company-day (`int_sales_daily`), store-day (`int_sales_store_daily`) |
| **Metrics** | MAE, RMSE, WAPE, R² (where applicable) |
| **Split** | Chronological holdout (`test_size: 0.2`, `train_days: 180` in Vertex configs) |

---

## Results template

Populate after running pipelines in your GCP project. Replace `{values}` with measured results.

### Store-day grain (Vertex default — `favorita_store_n1d_xgboost`)

| Platform | Model | Config | test_mae | test_wape | test_rmse | Train time | Notes |
|----------|-------|--------|----------|-----------|-----------|------------|-------|
| vertex | xgboost | `favorita_store_n1d_xgboost` | `{fill}` | `{fill}` | `{fill}` | `{fill}` | Default XGBoost config |
| vertex | random_forest | `favorita_store_n1d_rf` | `{fill}` | `{fill}` | `{fill}` | `{fill}` | Same features as XGBoost |
| vertex | arima | `favorita_store_n1d_arima` | `{fill}` | `{fill}` | `{fill}` | `{fill}` | Per-entity time series |
| vertex | sarima | `favorita_store_n1d_sarima` | `{fill}` | `{fill}` | `{fill}` | `{fill}` | Seasonal order in YAML |

### Company-day grain (BQML default — `bqml_sales_forecast`)

| Platform | Model | Config | metric | `{fill}` | Notes |
|----------|-------|--------|--------|----------|-------|
| bqml | BOOSTED_TREE_REGRESSOR | `bqml_sales_forecast` | mean_absolute_error | `{fill}` | From `bqml_model_evaluate` |
| bqml | BOOSTED_TREE_REGRESSOR | `bqml_sales_forecast` | mean_squared_error | `{fill}` | |
| bqml | BOOSTED_TREE_REGRESSOR | `bqml_sales_forecast` | r2_score | `{fill}` | |

### Champion selection (recommended)

| Grain | Champion platform | Champion model | Primary metric | Selected date |
|-------|-------------------|----------------|----------------|---------------|
| store-day | `{fill}` | `{fill}` | test_wape | `{fill}` |
| company-day | `{fill}` | `{fill}` | test_mae | `{fill}` |

---

## How to run benchmarks

```bash
# 1. Features
make dbt-run

# 2. BQML baseline
make dbt-train
make dbt-predict

# 3. Vertex models (Docker — repeat per config)
make vertex-train VERTEX_TRAIN_CONFIG=favorita_store_n1d_xgboost
make vertex-predict VERTEX_PREDICT_CONFIG=favorita_store_n1d_xgboost

make vertex-train VERTEX_TRAIN_CONFIG=favorita_store_n1d_rf
make vertex-predict VERTEX_PREDICT_CONFIG=favorita_store_n1d_rf

make vertex-train VERTEX_TRAIN_CONFIG=favorita_store_n1d_arima
make vertex-predict VERTEX_PREDICT_CONFIG=favorita_store_n1d_arima

# 4. Optional: full tuned pipeline
make vertex-pipeline-submit VERTEX_PIPELINE=favorita_xgboost SYNC=1

# 5. Stage Vertex outputs for SQL analysis
make dbt-vertex

# 6. Browse MLflow
make mlflow-ui
```

For Vertex on GCP: append `VERTEX_MODE=vertex` to train/predict commands.

---

## Query recipes

### Vertex performance (latest run per config)

```sql
SELECT
  config_name,
  model_type,
  model_family,
  JSON_VALUE(test_performance, '$.mae') AS test_mae,
  JSON_VALUE(test_performance, '$.wape') AS test_wape,
  JSON_VALUE(test_performance, '$.rmse') AS test_rmse,
  run_at
FROM `{project}.{dataset}.favorita_model_performance`
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY config_name
  ORDER BY run_at DESC
) = 1
ORDER BY CAST(JSON_VALUE(test_performance, '$.mae') AS FLOAT64);
```

Replace `{project}` and `{dataset}` with your `GOOGLE_PROJECT_ID` and `DBT_DATASET`.

### BQML evaluation

```sql
SELECT *
FROM `{project}.{dataset}.bqml_model_evaluate`
ORDER BY created_at DESC
LIMIT 10;
```

(Exact column names depend on your BQML evaluate macro output — inspect after `make dbt-train`.)

### Prediction vs actual (Vertex)

```sql
SELECT
  model_type,
  config_name,
  store_id,
  date,
  actual,
  prediction,
  ABS(actual - prediction) AS abs_error
FROM `{project}.{dataset}.stg_vertex_model_predictions`
WHERE actual IS NOT NULL
ORDER BY abs_error DESC
LIMIT 100;
```

### MLflow (local)

After `make mlflow-ui`, filter runs by tag `job_step=train` and compare `test_mae`, `test_wape` across configs. Each train run logs `config_name`, `model_type`, and `model_family` tags.

---

## Cost context (order-of-magnitude)

Use for proposals — **measure in client project** before committing.

| Workload | Cost drivers | Typical dev-demo range |
|----------|--------------|------------------------|
| dbt feature build | BQ bytes scanned | Low ($) if partitioned / incremental |
| BQML train | BQ ML slot time | Low–medium |
| Vertex Custom Job | `machine_type`, duration | ~$0.05–0.50 per short train on `n1-standard-4` |
| Vertex PipelineJob | Steps × machine hours | Higher than single train; use `SKIP_OPTIMIZE=1` for cheap refresh |
| GCS artifacts | Storage + egress | Low for joblib-sized models |

See [iac.md](iac.md) for production cost controls (reservations, labels, schedule tiering).

---

## Recommended benchmark narrative for consulting

1. **Start with BQML** on company-day — establishes a SQL-native baseline in hours.
2. **Move to Vertex XGBoost** on store-day — tests whether finer grain + tuning beats baseline.
3. **Add ARIMA/SARIMA** where series are short or highly seasonal per store.
4. **Document champion** in the table above and wire to dashboard / alerting (see [delivery_artifacts.md](delivery_artifacts.md)).

---

## Related documents

- [Case study](case_study.md)
- [Delivery artifacts — dashboard blueprint](delivery_artifacts.md#dashboard-blueprint)
- [Vertex experiment tracking](../../vertex/README.md) (repo)

{% enddocs %}
