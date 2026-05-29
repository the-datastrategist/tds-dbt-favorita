-- BigQuery DDL for Vertex ML orchestration and outputs (Favorita).
-- Run manually or via your infra pipeline against project the-data-strategist.

-- Job orchestration audit trail
CREATE TABLE IF NOT EXISTS `the-data-strategist.favorita.favorita_vertex_job_runs` (
  job_run_id STRING NOT NULL,
  config_name STRING NOT NULL,
  model_family STRING,
  model_type STRING,
  job_step STRING NOT NULL,
  status STRING NOT NULL,
  vertex_job_resource STRING,
  vertex_experiment STRING,
  error_message STRING,
  started_at TIMESTAMP NOT NULL,
  finished_at TIMESTAMP,
  project_id STRING,
  region STRING
)
PARTITION BY DATE(started_at)
CLUSTER BY config_name, job_step, status;

-- Training metadata (one row per training run)
CREATE TABLE IF NOT EXISTS `the-data-strategist.favorita.favorita_model_metadata` (
  model_run_id STRING NOT NULL,
  model_id STRING NOT NULL,
  parameter_id STRING,
  config_name STRING,
  model_family STRING,
  model_type STRING,
  run_at TIMESTAMP NOT NULL,
  target_column STRING,
  source_query STRING,
  gcs_uri STRING,
  joblib_gcs_uri STRING,
  trees_gcs_uri STRING,
  manifest_gcs_uri STRING,
  boosting_rounds INT64,
  feature_count INT64,
  entity_count INT64,
  entities_fitted INT64,
  train_row_count INT64,
  test_row_count INT64,
  project_id STRING,
  region STRING,
  parameters JSON,
  feature_importance JSON,
  features ARRAY<STRING>,
  train_performance JSON,
  test_performance JSON
)
PARTITION BY DATE(run_at)
CLUSTER BY model_family, model_type, config_name;

-- Holdout / evaluation metrics
CREATE TABLE IF NOT EXISTS `the-data-strategist.favorita.favorita_model_performance` (
  model_run_id STRING NOT NULL,
  model_id STRING NOT NULL,
  config_name STRING,
  model_family STRING,
  model_type STRING,
  run_at TIMESTAMP NOT NULL,
  metric_set STRING,
  mean_pred FLOAT64,
  mean_actual FLOAT64,
  mae FLOAT64,
  rmse FLOAT64,
  mse FLOAT64,
  r2 FLOAT64,
  mape FLOAT64,
  wape FLOAT64,
  smape FLOAT64,
  bias FLOAT64,
  median_ae FLOAT64
)
PARTITION BY DATE(run_at)
CLUSTER BY model_family, model_type;

-- Hyperparameter optimization trials
CREATE TABLE IF NOT EXISTS `the-data-strategist.favorita.favorita_model_optimize` (
  optimize_run_id STRING NOT NULL,
  trial_number INT64 NOT NULL,
  config_name STRING NOT NULL,
  model_family STRING,
  model_type STRING,
  model_id STRING,
  model_run_id STRING,
  run_at TIMESTAMP NOT NULL,
  run_date DATE,
  target_column STRING,
  objective_metric STRING,
  objective_value FLOAT64,
  feature_count INT64,
  test_size FLOAT64,
  parameters JSON,
  test_performance JSON
)
PARTITION BY run_date
CLUSTER BY config_name, model_family;

-- Unified predictions across model types
CREATE TABLE IF NOT EXISTS `the-data-strategist.favorita.favorita_model_predictions` (
  prediction_id STRING NOT NULL,
  predict_run_id STRING NOT NULL,
  model_run_id STRING,
  model_id STRING NOT NULL,
  config_name STRING NOT NULL,
  model_family STRING,
  model_type STRING NOT NULL,
  run_at TIMESTAMP NOT NULL,
  run_date DATE NOT NULL,
  target_column STRING,
  entity_id STRING,
  store_id INT64,
  product_id INT64,
  date DATE,
  forecast_date DATE,
  forecast_horizon INT64,
  actual FLOAT64,
  prediction FLOAT64,
  prediction_lower FLOAT64,
  prediction_upper FLOAT64,
  model_artifact_uri STRING
)
PARTITION BY run_date
CLUSTER BY model_family, model_type, config_name;
