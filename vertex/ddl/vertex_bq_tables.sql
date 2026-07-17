-- BigQuery DDL for Vertex ML orchestration and outputs (Favorita).
-- Run manually or via your infra pipeline against project tds-favorita.

-- Job orchestration audit trail
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.favorita_vertex_job_runs` (
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
  duration_sec FLOAT64,
  row_count INT64,
  artifact_uri STRING,
  git_sha STRING,
  image_uri STRING,
  pipeline_run_id STRING,
  optimize_run_id STRING,
  project_id STRING,
  region STRING,
  mlflow_run_id STRING,
  vertex_experiment_run STRING
)
PARTITION BY DATE(started_at)
CLUSTER BY config_name, job_step, status;

-- Idempotent migrations for tables created before mlflow / experiment columns existed
ALTER TABLE `tds-favorita.favorita.favorita_vertex_job_runs`
  ADD COLUMN IF NOT EXISTS mlflow_run_id STRING;

ALTER TABLE `tds-favorita.favorita.favorita_vertex_job_runs`
  ADD COLUMN IF NOT EXISTS vertex_experiment_run STRING;

-- Training metadata (one row per training run)
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.favorita_model_metadata` (
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
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.favorita_model_performance` (
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
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.favorita_model_optimize` (
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
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.favorita_model_predictions` (
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

-- SHAP feature attributions for tree-based Vertex predictions (xgboost, random_forest);
-- one row per prediction_id in favorita_model_predictions when explain.enabled is set.
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.favorita_model_explain` (
  explanation_id STRING NOT NULL,
  prediction_id STRING NOT NULL,
  predict_run_id STRING NOT NULL,
  model_run_id STRING,
  model_id STRING NOT NULL,
  config_name STRING NOT NULL,
  model_family STRING,
  model_type STRING NOT NULL,
  run_at TIMESTAMP NOT NULL,
  run_date DATE NOT NULL,
  entity_id STRING,
  store_id INT64,
  product_id INT64,
  date DATE,
  predicted_value FLOAT64,
  base_value FLOAT64,
  top_feature_attributions JSON,
  model_artifact_uri STRING
)
PARTITION BY run_date
CLUSTER BY model_family, model_type, config_name;

-- Forecast contracts registered by platform implementations.
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.forecast_contracts` (
  forecast_contract_name STRING NOT NULL,
  forecast_contract_hash STRING NOT NULL,
  registered_at TIMESTAMP NOT NULL,
  target STRING NOT NULL,
  target_unit STRING,
  frequency STRING NOT NULL,
  timezone STRING NOT NULL,
  issue_schedule STRING,
  dimensions ARRAY<STRING>,
  horizons ARRAY<INT64>,
  quantiles ARRAY<FLOAT64>,
  training_window_days INT64,
  known_future_features ARRAY<STRING>,
  observed_features ARRAY<STRING>,
  hierarchy ARRAY<STRING>,
  reconciliation_policy STRING,
  demand_policy STRING,
  contract_json JSON,
  is_active BOOL
)
PARTITION BY DATE(registered_at)
CLUSTER BY forecast_contract_name, forecast_contract_hash;

-- Forecast scoring / publication run audit.
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.forecast_runs` (
  forecast_run_id STRING NOT NULL,
  forecast_contract_name STRING NOT NULL,
  forecast_contract_hash STRING NOT NULL,
  run_type STRING NOT NULL,
  run_status STRING NOT NULL,
  forecast_origin TIMESTAMP NOT NULL,
  started_at TIMESTAMP NOT NULL,
  finished_at TIMESTAMP,
  source_cutoff_json JSON,
  feature_version STRING,
  code_sha STRING,
  model_run_id STRING,
  model_id STRING,
  config_name STRING,
  row_count INT64,
  error_message STRING
)
PARTITION BY DATE(started_at)
CLUSTER BY forecast_contract_name, run_type, run_status;

-- Canonical forecast output rows. Initial predict jobs write draft statistical forecasts.
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.forecast_outputs` (
  forecast_output_id STRING NOT NULL,
  source_prediction_id STRING,
  forecast_run_id STRING NOT NULL,
  forecast_contract_name STRING NOT NULL,
  forecast_contract_hash STRING NOT NULL,
  forecast_origin TIMESTAMP NOT NULL,
  target_date DATE,
  horizon INT64,
  grain STRING,
  entity_key_json STRING,
  target STRING,
  target_unit STRING,
  prediction_p10 FLOAT64,
  prediction_p50 FLOAT64,
  prediction_p90 FLOAT64,
  statistical_forecast FLOAT64,
  planner_override FLOAT64,
  approved_forecast FLOAT64,
  published_forecast FLOAT64,
  forecast_status STRING NOT NULL,
  model_run_id STRING,
  model_id STRING,
  config_name STRING,
  model_family STRING,
  model_type STRING,
  feature_version STRING,
  code_sha STRING,
  data_cutoff TIMESTAMP,
  model_artifact_uri STRING,
  created_at TIMESTAMP NOT NULL
)
PARTITION BY DATE(forecast_origin)
CLUSTER BY forecast_contract_name, forecast_status, config_name;

-- Forecast status transition history.
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.forecast_status_history` (
  status_event_id STRING NOT NULL,
  forecast_output_id STRING,
  forecast_run_id STRING NOT NULL,
  previous_status STRING,
  new_status STRING NOT NULL,
  changed_at TIMESTAMP NOT NULL,
  changed_by STRING,
  reason_code STRING,
  comment STRING
)
PARTITION BY DATE(changed_at)
CLUSTER BY forecast_run_id, new_status;
