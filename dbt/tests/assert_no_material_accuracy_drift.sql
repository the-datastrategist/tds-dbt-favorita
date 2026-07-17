-- Flags configs whose live rolling WAPE has degraded beyond accuracy_drift_tolerance_pct
-- vs. the WAPE recorded at training time for that model_run_id. Starts as severity=warn
-- since tolerance hasn't been validated against real client data yet; promote to error
-- once it has (see docs/specs/prediction_accuracy_monitoring.md).
{{ config(tags=['data_quality', 'vertex'], severity='warn') }}

select *
from {{ ref('ml_prediction_accuracy_rolling') }}
where train_test_wape is not null
  and wape_7d > train_test_wape * (1 + {{ var('accuracy_drift_tolerance_pct', 0.25) }})
