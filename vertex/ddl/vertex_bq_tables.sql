-- BigQuery DDL for Vertex ML orchestration and outputs (Favorita).
-- Run manually or via your infra pipeline against project tds-favorita.

-- Append-only evidence emitted by source loaders. data_mode controls whether
-- wall-clock freshness applies (continuous) or is intentionally disabled
-- while watermark and execution health remain observable (static_demo).
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.source_ingestion_runs` (
  ingestion_run_id STRING NOT NULL,
  source_name STRING NOT NULL,
  source_policy_hash STRING NOT NULL,
  data_mode STRING NOT NULL,
  status STRING NOT NULL,
  started_at TIMESTAMP NOT NULL,
  finished_at TIMESTAMP NOT NULL,
  source_watermark TIMESTAMP,
  ingested_row_count INT64 NOT NULL,
  table_count INT64 NOT NULL,
  source_uri STRING,
  source_table STRING NOT NULL,
  watermark_column STRING NOT NULL,
  expected_interval_hours INT64 NOT NULL,
  allowed_lateness_hours INT64 NOT NULL,
  evaluate_on_json JSON NOT NULL,
  code_sha STRING,
  error_message STRING,
  details_json JSON NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP() NOT NULL
)
PARTITION BY DATE(started_at)
CLUSTER BY source_name, data_mode, status;

-- Job orchestration audit trail
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.ml_vertex_job_runs` (
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
ALTER TABLE `tds-favorita.favorita.ml_vertex_job_runs`
  ADD COLUMN IF NOT EXISTS mlflow_run_id STRING;

ALTER TABLE `tds-favorita.favorita.ml_vertex_job_runs`
  ADD COLUMN IF NOT EXISTS vertex_experiment_run STRING;

-- Training metadata (one row per training run)
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.ml_model_metadata` (
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
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.ml_model_performance` (
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
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.ml_model_optimize` (
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
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.ml_model_predictions` (
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

-- One immutable record per logical rolling-origin execution. Re-running the
-- same contract and input fingerprint produces the same backtest_run_id.
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.backtest_runs` (
  backtest_run_id STRING NOT NULL,
  backtest_contract_name STRING NOT NULL,
  backtest_contract_hash STRING NOT NULL,
  model_config_name STRING NOT NULL,
  model_family STRING NOT NULL,
  model_type STRING NOT NULL,
  target STRING NOT NULL,
  grain STRING NOT NULL,
  metric_policy_json STRING NOT NULL,
  origin_start DATE NOT NULL,
  origin_end DATE NOT NULL,
  prediction_count INT64 NOT NULL,
  metric_count INT64 NOT NULL,
  status STRING NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP() NOT NULL
)
PARTITION BY origin_start
CLUSTER BY backtest_contract_name, model_config_name, backtest_run_id;

-- Forward-compatible migration for datasets created before comparison semantics
-- were persisted on the run record. BigQuery adds these as nullable on existing
-- tables; all new writers populate them.
ALTER TABLE `tds-favorita.favorita.backtest_runs`
ADD COLUMN IF NOT EXISTS target STRING;

ALTER TABLE `tds-favorita.favorita.backtest_runs`
ADD COLUMN IF NOT EXISTS grain STRING;

ALTER TABLE `tds-favorita.favorita.backtest_runs`
ADD COLUMN IF NOT EXISTS metric_policy_json STRING;

ALTER TABLE `tds-favorita.favorita.backtest_runs`
ADD COLUMN IF NOT EXISTS model_family STRING;

ALTER TABLE `tds-favorita.favorita.backtest_runs`
ADD COLUMN IF NOT EXISTS model_type STRING;

-- Append-only rolling-origin backtest predictions. prediction_id is a stable
-- logical key; writers must append new records and must not update prior runs.
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.backtest_predictions` (
  prediction_id STRING NOT NULL,
  backtest_run_id STRING NOT NULL,
  backtest_contract_name STRING NOT NULL,
  backtest_contract_hash STRING NOT NULL,
  forecast_origin DATE NOT NULL,
  target_date DATE NOT NULL,
  horizon INT64 NOT NULL,
  entity_key_json STRING NOT NULL,
  segment_key_json STRING NOT NULL,
  baseline_name STRING NOT NULL,
  actual FLOAT64,
  prediction FLOAT64,
  prediction_p10 FLOAT64,
  prediction_p50 FLOAT64,
  prediction_p90 FLOAT64,
  data_cutoff TIMESTAMP NOT NULL,
  source_cutoff_json JSON NOT NULL,
  feature_availability_hash STRING,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP() NOT NULL
)
PARTITION BY forecast_origin
CLUSTER BY backtest_contract_name, horizon, baseline_name, backtest_run_id;

ALTER TABLE `tds-favorita.favorita.backtest_predictions`
ADD COLUMN IF NOT EXISTS data_cutoff TIMESTAMP;

ALTER TABLE `tds-favorita.favorita.backtest_predictions`
ADD COLUMN IF NOT EXISTS source_cutoff_json JSON;

ALTER TABLE `tds-favorita.favorita.backtest_predictions`
ADD COLUMN IF NOT EXISTS feature_availability_hash STRING;

ALTER TABLE `tds-favorita.favorita.backtest_predictions`
ADD COLUMN IF NOT EXISTS prediction_p10 FLOAT64;

ALTER TABLE `tds-favorita.favorita.backtest_predictions`
ADD COLUMN IF NOT EXISTS prediction_p50 FLOAT64;

ALTER TABLE `tds-favorita.favorita.backtest_predictions`
ADD COLUMN IF NOT EXISTS prediction_p90 FLOAT64;

-- Append-only metrics derived from backtest_predictions. metric_id is stable
-- for a run/origin/horizon/baseline/segment metric record.
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.backtest_metrics` (
  metric_id STRING NOT NULL,
  backtest_run_id STRING NOT NULL,
  backtest_contract_name STRING NOT NULL,
  backtest_contract_hash STRING NOT NULL,
  forecast_origin DATE NOT NULL,
  horizon INT64 NOT NULL,
  baseline_name STRING NOT NULL,
  segment_key_json STRING NOT NULL,
  eligible_count INT64 NOT NULL,
  prediction_count INT64 NOT NULL,
  wape FLOAT64,
  mae FLOAT64,
  mase FLOAT64,
  rmsse FLOAT64,
  bias FLOAT64,
  prediction_completeness FLOAT64,
  pinball_loss FLOAT64,
  interval_coverage FLOAT64,
  interval_width FLOAT64,
  calibration_error FLOAT64,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP() NOT NULL
)
PARTITION BY forecast_origin
CLUSTER BY backtest_contract_name, horizon, baseline_name, backtest_run_id;

ALTER TABLE `tds-favorita.favorita.backtest_metrics`
ADD COLUMN IF NOT EXISTS mase FLOAT64;

ALTER TABLE `tds-favorita.favorita.backtest_metrics`
ADD COLUMN IF NOT EXISTS rmsse FLOAT64;

ALTER TABLE `tds-favorita.favorita.backtest_metrics`
ADD COLUMN IF NOT EXISTS pinball_loss FLOAT64;

ALTER TABLE `tds-favorita.favorita.backtest_metrics`
ADD COLUMN IF NOT EXISTS interval_coverage FLOAT64;

ALTER TABLE `tds-favorita.favorita.backtest_metrics`
ADD COLUMN IF NOT EXISTS interval_width FLOAT64;

ALTER TABLE `tds-favorita.favorita.backtest_metrics`
ADD COLUMN IF NOT EXISTS calibration_error FLOAT64;

-- Append-only series profiles used to prove and reproduce routing decisions.
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.forecast_series_classifications` (
  classification_id STRING NOT NULL,
  classification_run_id STRING NOT NULL,
  forecast_contract_name STRING NOT NULL,
  forecast_contract_hash STRING NOT NULL,
  forecast_origin TIMESTAMP NOT NULL,
  entity_key_json STRING NOT NULL,
  history_length INT64 NOT NULL,
  nonzero_observation_count INT64 NOT NULL,
  average_demand_interval FLOAT64,
  coefficient_of_variation_squared FLOAT64,
  is_intermittent BOOL NOT NULL,
  is_cold_start BOOL NOT NULL,
  recommended_strategy STRING NOT NULL,
  routing_policy_hash STRING NOT NULL,
  classified_at TIMESTAMP NOT NULL
)
PARTITION BY DATE(forecast_origin)
CLUSTER BY forecast_contract_name, recommended_strategy, routing_policy_hash;

-- Immutable registrations. Current state and champion history are derived from
-- model_lifecycle_events so retries never update or erase an earlier decision.
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.model_candidates` (
  candidate_id STRING NOT NULL,
  model_scope_json JSON NOT NULL,
  model_config_name STRING NOT NULL,
  model_family STRING NOT NULL,
  model_type STRING NOT NULL,
  backtest_run_id STRING NOT NULL,
  backtest_contract_hash STRING NOT NULL,
  artifact_uri STRING,
  initial_state STRING NOT NULL,
  registered_by STRING NOT NULL,
  registered_at TIMESTAMP NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP() NOT NULL
)
PARTITION BY DATE(registered_at)
CLUSTER BY model_config_name, model_family, candidate_id;

CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.model_promotion_checks` (
  promotion_check_id STRING NOT NULL,
  candidate_id STRING NOT NULL,
  check_name STRING NOT NULL,
  observed_value FLOAT64,
  threshold_value FLOAT64 NOT NULL,
  passed BOOL NOT NULL,
  details_json JSON,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP() NOT NULL
)
CLUSTER BY candidate_id, check_name, passed;

CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.model_lifecycle_events` (
  lifecycle_event_id STRING NOT NULL,
  candidate_id STRING NOT NULL,
  event_type STRING NOT NULL,
  from_state STRING,
  to_state STRING NOT NULL,
  replaces_candidate_id STRING,
  reason STRING,
  actor STRING NOT NULL,
  occurred_at TIMESTAMP NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP() NOT NULL
)
PARTITION BY DATE(occurred_at)
CLUSTER BY candidate_id, event_type, to_state;

-- SHAP feature attributions for tree-based Vertex predictions (xgboost, random_forest);
-- one row per prediction_id in ml_model_predictions when explain.enabled is set.
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
  contract_enforced BOOL NOT NULL,
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
  routing_policy_json JSON,
  calibration_policy_json JSON,
  contract_json JSON,
  is_active BOOL
)
PARTITION BY DATE(registered_at)
CLUSTER BY forecast_contract_name, forecast_contract_hash;

ALTER TABLE `tds-favorita.favorita.forecast_contracts`
ADD COLUMN IF NOT EXISTS routing_policy_json JSON;

ALTER TABLE `tds-favorita.favorita.forecast_contracts`
ADD COLUMN IF NOT EXISTS calibration_policy_json JSON;

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
  data_cutoff TIMESTAMP,
  source_cutoff_json JSON,
  feature_availability_hash STRING,
  feature_materialization_id STRING,
  feature_version STRING,
  code_sha STRING,
  model_run_id STRING,
  model_id STRING,
  config_name STRING,
  champion_candidate_id STRING,
  eligibility_snapshot_id STRING,
  row_count INT64,
  candidate_count INT64,
  eligible_count INT64,
  excluded_count INT64,
  exception_count INT64,
  error_message STRING
)
PARTITION BY DATE(started_at)
CLUSTER BY forecast_contract_name, run_type, run_status;

ALTER TABLE `tds-favorita.favorita.forecast_runs`
ADD COLUMN IF NOT EXISTS champion_candidate_id STRING;

ALTER TABLE `tds-favorita.favorita.forecast_runs`
ADD COLUMN IF NOT EXISTS eligibility_snapshot_id STRING;

ALTER TABLE `tds-favorita.favorita.forecast_runs` ADD COLUMN IF NOT EXISTS candidate_count INT64;
ALTER TABLE `tds-favorita.favorita.forecast_runs` ADD COLUMN IF NOT EXISTS eligible_count INT64;
ALTER TABLE `tds-favorita.favorita.forecast_runs` ADD COLUMN IF NOT EXISTS excluded_count INT64;
ALTER TABLE `tds-favorita.favorita.forecast_runs` ADD COLUMN IF NOT EXISTS exception_count INT64;

-- Frozen candidate population and immutable eligibility/exclusion evidence.
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.forecast_eligibility_decisions` (
  eligibility_decision_id STRING NOT NULL,
  forecast_run_id STRING NOT NULL,
  eligibility_snapshot_id STRING NOT NULL,
  forecast_contract_name STRING NOT NULL,
  forecast_contract_hash STRING NOT NULL,
  forecast_origin TIMESTAMP NOT NULL,
  entity_key_json STRING NOT NULL,
  target_date DATE NOT NULL,
  horizon INT64 NOT NULL,
  is_eligible BOOL NOT NULL,
  ineligibility_reason STRING,
  has_exception BOOL NOT NULL,
  decision_evidence_json JSON,
  decided_at TIMESTAMP NOT NULL
)
PARTITION BY DATE(decided_at)
CLUSTER BY forecast_run_id, is_eligible, forecast_contract_name;

-- Ordered component evidence. Stable stage_run_id values make identical retries no-ops.
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.forecast_pipeline_stage_runs` (
  stage_run_id STRING NOT NULL,
  forecast_run_id STRING NOT NULL,
  stage_name STRING NOT NULL,
  stage_position INT64 NOT NULL,
  component_run_id STRING NOT NULL,
  input_fingerprint STRING NOT NULL,
  output_fingerprint STRING NOT NULL,
  stage_status STRING NOT NULL,
  input_row_count INT64 NOT NULL,
  output_row_count INT64 NOT NULL,
  started_at TIMESTAMP NOT NULL,
  finished_at TIMESTAMP,
  error_message STRING
)
PARTITION BY DATE(started_at)
CLUSTER BY forecast_run_id, stage_position, stage_status;

-- Immutable quality gates evaluated before the draft visibility boundary.
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.forecast_validation_checks` (
  validation_check_id STRING NOT NULL,
  forecast_run_id STRING NOT NULL,
  check_name STRING NOT NULL,
  severity STRING NOT NULL,
  passed BOOL NOT NULL,
  observed_value FLOAT64,
  threshold_value FLOAT64,
  details_json JSON,
  checked_at TIMESTAMP NOT NULL
)
PARTITION BY DATE(checked_at)
CLUSTER BY forecast_run_id, severity, passed;

-- Mutable operational leases. Forecast evidence and outputs remain append-only.
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.forecast_pipeline_locks` (
  lock_key STRING NOT NULL,
  forecast_contract_hash STRING NOT NULL,
  forecast_origin TIMESTAMP NOT NULL,
  owner_id STRING NOT NULL,
  acquired_at TIMESTAMP NOT NULL,
  heartbeat_at TIMESTAMP NOT NULL,
  expires_at TIMESTAMP NOT NULL,
  released_at TIMESTAMP
)
CLUSTER BY forecast_contract_hash, forecast_origin;

-- Canonical forecast output rows. Initial predict jobs write draft statistical forecasts.
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.forecast_outputs` (
  forecast_output_id STRING NOT NULL,
  source_prediction_id STRING,
  forecast_run_id STRING NOT NULL,
  forecast_contract_name STRING NOT NULL,
  forecast_contract_hash STRING NOT NULL,
  forecast_origin TIMESTAMP NOT NULL,
  target_date DATE NOT NULL,
  horizon INT64 NOT NULL,
  grain STRING NOT NULL,
  entity_key_json STRING NOT NULL,
  target STRING NOT NULL,
  target_unit STRING,
  prediction_p10 FLOAT64,
  prediction_p50 FLOAT64,
  prediction_p90 FLOAT64,
  forecast_strategy STRING NOT NULL,
  fallback_reason STRING,
  confidence_flag STRING NOT NULL,
  calibration_method STRING,
  calibration_run_id STRING,
  hierarchy_version STRING,
  reconciliation_method STRING NOT NULL,
  reconciliation_run_id STRING,
  statistical_forecast FLOAT64 NOT NULL,
  planner_override FLOAT64,
  approved_forecast FLOAT64,
  published_forecast FLOAT64,
  forecast_status STRING NOT NULL,
  model_run_id STRING,
  model_id STRING NOT NULL,
  config_name STRING NOT NULL,
  model_family STRING,
  model_type STRING NOT NULL,
  feature_version STRING NOT NULL,
  code_sha STRING NOT NULL,
  data_cutoff TIMESTAMP NOT NULL,
  model_artifact_uri STRING NOT NULL,
  created_at TIMESTAMP NOT NULL
)
PARTITION BY DATE(forecast_origin)
CLUSTER BY forecast_contract_name, forecast_status, config_name;

ALTER TABLE `tds-favorita.favorita.forecast_outputs`
ADD COLUMN IF NOT EXISTS contract_enforced BOOL;

ALTER TABLE `tds-favorita.favorita.forecast_outputs`
ADD COLUMN IF NOT EXISTS forecast_strategy STRING;

ALTER TABLE `tds-favorita.favorita.forecast_outputs`
ADD COLUMN IF NOT EXISTS fallback_reason STRING;

ALTER TABLE `tds-favorita.favorita.forecast_outputs`
ADD COLUMN IF NOT EXISTS confidence_flag STRING;

ALTER TABLE `tds-favorita.favorita.forecast_outputs`
ADD COLUMN IF NOT EXISTS calibration_method STRING;

ALTER TABLE `tds-favorita.favorita.forecast_outputs`
ADD COLUMN IF NOT EXISTS calibration_run_id STRING;

ALTER TABLE `tds-favorita.favorita.forecast_outputs`
ADD COLUMN IF NOT EXISTS hierarchy_version STRING;

ALTER TABLE `tds-favorita.favorita.forecast_outputs`
ADD COLUMN IF NOT EXISTS reconciliation_method STRING;

ALTER TABLE `tds-favorita.favorita.forecast_outputs`
ADD COLUMN IF NOT EXISTS reconciliation_run_id STRING;

-- Versioned hierarchy nodes used by reconciliation runs.
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.forecast_hierarchy_nodes` (
  hierarchy_name STRING NOT NULL,
  hierarchy_version STRING NOT NULL,
  node_id STRING NOT NULL,
  level_name STRING NOT NULL,
  level_position INT64 NOT NULL,
  node_key_json JSON NOT NULL,
  effective_from DATE NOT NULL,
  effective_to DATE,
  created_at TIMESTAMP NOT NULL
)
CLUSTER BY hierarchy_name, hierarchy_version, level_name;

-- Single-parent hierarchy edges and optional top-down allocation weights.
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.forecast_hierarchy_edges` (
  hierarchy_name STRING NOT NULL,
  hierarchy_version STRING NOT NULL,
  parent_node_id STRING NOT NULL,
  child_node_id STRING NOT NULL,
  allocation_weight FLOAT64,
  weight_source STRING,
  effective_from DATE NOT NULL,
  effective_to DATE,
  created_at TIMESTAMP NOT NULL
)
CLUSTER BY hierarchy_name, hierarchy_version, parent_node_id;

-- One audit record per reconciliation execution.
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.forecast_reconciliation_runs` (
  reconciliation_run_id STRING NOT NULL,
  forecast_run_id STRING NOT NULL,
  hierarchy_name STRING NOT NULL,
  hierarchy_version STRING NOT NULL,
  reconciliation_method STRING NOT NULL,
  tolerance_abs FLOAT64 NOT NULL,
  run_status STRING NOT NULL,
  input_row_count INT64,
  output_row_count INT64,
  violation_count INT64,
  started_at TIMESTAMP NOT NULL,
  finished_at TIMESTAMP,
  error_message STRING
)
PARTITION BY DATE(started_at)
CLUSTER BY hierarchy_name, reconciliation_method, run_status;

-- Reconciled forecasts remain separately queryable from immutable base outputs.
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.forecast_reconciled_outputs` (
  reconciliation_output_id STRING NOT NULL,
  reconciliation_run_id STRING NOT NULL,
  forecast_output_id STRING,
  forecast_run_id STRING NOT NULL,
  hierarchy_name STRING NOT NULL,
  hierarchy_version STRING NOT NULL,
  node_id STRING NOT NULL,
  level_name STRING NOT NULL,
  forecast_origin TIMESTAMP NOT NULL,
  target_date DATE NOT NULL,
  horizon INT64 NOT NULL,
  base_prediction_p10 FLOAT64,
  base_prediction_p50 FLOAT64,
  base_prediction_p90 FLOAT64,
  prediction_p10 FLOAT64,
  prediction_p50 FLOAT64 NOT NULL,
  prediction_p90 FLOAT64,
  reconciliation_method STRING NOT NULL,
  created_at TIMESTAMP NOT NULL
)
PARTITION BY DATE(forecast_origin)
CLUSTER BY hierarchy_name, level_name, reconciliation_method;

-- Backtest comparison of base and reconciled accuracy by hierarchy level.
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.forecast_reconciliation_metrics` (
  reconciliation_metric_id STRING NOT NULL,
  evaluation_run_id STRING NOT NULL,
  hierarchy_name STRING NOT NULL,
  hierarchy_version STRING NOT NULL,
  model_config_name STRING NOT NULL,
  level_name STRING NOT NULL,
  horizon INT64 NOT NULL,
  metric_name STRING NOT NULL,
  base_metric_value FLOAT64,
  reconciled_metric_value FLOAT64,
  metric_delta FLOAT64,
  observation_count INT64 NOT NULL,
  computed_at TIMESTAMP NOT NULL
)
PARTITION BY DATE(computed_at)
CLUSTER BY hierarchy_name, hierarchy_version, level_name, metric_name;

-- Forecast status transition history.
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.forecast_status_history` (
  status_event_id STRING NOT NULL,
  forecast_output_id STRING,
  forecast_run_id STRING NOT NULL,
  previous_status STRING,
  new_status STRING NOT NULL,
  changed_at TIMESTAMP NOT NULL,
  changed_by STRING NOT NULL,
  reason_code STRING,
  comment STRING
)
PARTITION BY DATE(changed_at)
CLUSTER BY forecast_run_id, new_status;

-- Append-only exception queue records. exception_id and idempotency_key are
-- deterministic logical keys; writers must use insert-only MERGE semantics.
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.forecast_exceptions` (
  exception_id STRING NOT NULL,
  idempotency_key STRING NOT NULL,
  forecast_output_id STRING NOT NULL,
  forecast_run_id STRING NOT NULL,
  exception_type STRING NOT NULL,
  severity STRING NOT NULL,
  exception_status STRING NOT NULL,
  detected_at TIMESTAMP NOT NULL,
  detected_by STRING NOT NULL,
  details_json JSON,
  resolved_at TIMESTAMP,
  resolved_by STRING,
  resolution_comment STRING,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP() NOT NULL
)
PARTITION BY DATE(detected_at)
CLUSTER BY forecast_run_id, exception_status, severity;

-- Planner-entered adjustments. The canonical statistical_forecast remains
-- immutable; an override is a separate audited event selected at approval time.
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.forecast_overrides` (
  override_id STRING NOT NULL,
  idempotency_key STRING NOT NULL,
  forecast_output_id STRING NOT NULL,
  forecast_run_id STRING NOT NULL,
  override_value FLOAT64 NOT NULL,
  reason_code STRING NOT NULL,
  comment STRING NOT NULL,
  overridden_at TIMESTAMP NOT NULL,
  overridden_by STRING NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP() NOT NULL
)
PARTITION BY DATE(overridden_at)
CLUSTER BY forecast_run_id, reason_code, overridden_by;

-- Append-only approval decisions. override_id is populated when the approved
-- value came from a planner adjustment rather than the statistical forecast.
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.forecast_approvals` (
  approval_id STRING NOT NULL,
  idempotency_key STRING NOT NULL,
  forecast_output_id STRING NOT NULL,
  forecast_run_id STRING NOT NULL,
  override_id STRING,
  decision STRING NOT NULL,
  approved_value FLOAT64,
  reason_code STRING,
  comment STRING,
  decided_at TIMESTAMP NOT NULL,
  decided_by STRING NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP() NOT NULL
)
PARTITION BY DATE(decided_at)
CLUSTER BY forecast_run_id, decision, decided_by;

-- Immutable publication attempts and delivery outcomes. Deterministic
-- publication_id/idempotency_key pairs make retries safe without overwrites.
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.forecast_publications` (
  publication_id STRING NOT NULL,
  idempotency_key STRING NOT NULL,
  forecast_output_id STRING NOT NULL,
  forecast_run_id STRING NOT NULL,
  approval_id STRING NOT NULL,
  publication_version INT64 NOT NULL,
  published_value FLOAT64 NOT NULL,
  destination STRING NOT NULL,
  delivery_status STRING NOT NULL,
  delivery_reference STRING,
  published_at TIMESTAMP NOT NULL,
  published_by STRING NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP() NOT NULL
)
PARTITION BY DATE(published_at)
CLUSTER BY forecast_run_id, destination, delivery_status;

-- Supersession and rollback lineage. Records point from a prior publication to
-- its replacement; rollback republishes an earlier value as a new version.
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.forecast_revisions` (
  revision_id STRING NOT NULL,
  idempotency_key STRING NOT NULL,
  forecast_output_id STRING NOT NULL,
  forecast_run_id STRING NOT NULL,
  prior_publication_id STRING NOT NULL,
  replacement_publication_id STRING,
  revision_type STRING NOT NULL,
  reason_code STRING NOT NULL,
  comment STRING NOT NULL,
  revised_at TIMESTAMP NOT NULL,
  revised_by STRING NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP() NOT NULL
)
PARTITION BY DATE(revised_at)
CLUSTER BY forecast_run_id, revision_type, revised_by;

-- Version-level publication events for integrations and webhook adapters.
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.forecast_publication_events` (
  publication_event_id STRING NOT NULL,
  idempotency_key STRING NOT NULL,
  event_type STRING NOT NULL,
  forecast_run_id STRING NOT NULL,
  forecast_contract_name STRING NOT NULL,
  forecast_contract_hash STRING NOT NULL,
  publication_version INT64 NOT NULL,
  destination STRING NOT NULL,
  row_count INT64 NOT NULL,
  occurred_at TIMESTAMP NOT NULL,
  occurred_by STRING NOT NULL,
  payload_json JSON NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP() NOT NULL
)
PARTITION BY DATE(occurred_at)
CLUSTER BY forecast_run_id, publication_version, destination, event_type;

-- Append-only delivery transitions. Current delivery state is derived from the
-- latest event; immutable publication rows are never updated by delivery outcomes.
CREATE TABLE IF NOT EXISTS `tds-favorita.favorita.forecast_delivery_events` (
  delivery_event_id STRING NOT NULL,
  idempotency_key STRING NOT NULL,
  forecast_run_id STRING NOT NULL,
  publication_version INT64 NOT NULL,
  destination STRING NOT NULL,
  delivery_status STRING NOT NULL,
  delivery_attempt INT64 NOT NULL,
  delivery_reference STRING,
  error_code STRING,
  error_message STRING,
  occurred_at TIMESTAMP NOT NULL,
  occurred_by STRING NOT NULL,
  details_json JSON,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP() NOT NULL
)
PARTITION BY DATE(occurred_at)
CLUSTER BY forecast_run_id, publication_version, destination, delivery_status;
