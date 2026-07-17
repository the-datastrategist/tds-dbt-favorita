# Feature Availability

Point-in-time feature availability defines whether a model input was knowable at the forecast origin. The platform keeps this as an explicit registry in `vertex/config/feature_availability.yaml` and validates concrete model features before training or prediction.

## Availability Classes

| Class | Meaning |
|-------|---------|
| `known_future` | Planned or calendar information known for future target dates at forecast origin. |
| `observed_lagged` | Historical observations available at or before the feature row cutoff. |
| `observed_after_period` | Outcomes only known after the target period; these are valid targets or evaluation fields, but not model inputs. |
| `forecasted_external` | External covariates forecasted separately and versioned by origin. |
| `planned_revisable` | Plans that may change, such as price or promotion plans, requiring plan/version metadata. |
| `static_master_data` | Slowly changing or static attributes such as date parts or product/store attributes. |

## Adding Features Safely

1. Add the feature or a narrow naming pattern to `vertex/config/feature_availability.yaml`.
2. Choose the strictest availability class that matches what is knowable at forecast origin.
3. For `known_future`, `forecasted_external`, or `planned_revisable`, include cutoff or version metadata such as `timestamp_column`, `source_cutoff_column`, or `plan_version_column`.
4. Keep target/outcome columns classified as `observed_after_period`; the runtime validator rejects them as model inputs.
5. Run unit tests and `dbt parse` after changing the registry or feature SQL.

The registry is intentionally project-adaptable. A new project should replace the default feature names and patterns with the dbt models and covariates for that domain while preserving the same availability semantics.
