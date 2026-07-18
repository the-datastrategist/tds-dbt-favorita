# Clean Rebuild Runbook

Use this runbook to deliberately reconstruct the platform's derived BigQuery dataset from preserved source data and version-controlled definitions.

This is a reset and recovery procedure. It is **not** routine maintenance. Once an environment is operating normally, use incremental dbt runs, schema migrations, idempotent DDL, scheduled scoring, and gated model retraining instead of deleting its derived dataset.

## Rebuild boundary

The platform separates source data from reconstructible outputs:

| Zone | Configuration | Treatment during a clean rebuild |
|---|---|---|
| Source/raw dataset | `BQ_RAW_DATASET` | Preserve. This is an input to the rebuild. |
| Derived/analytics dataset | `DBT_DATASET` | May be deleted only for an intentional reset or recovery. |
| Model artifact storage | `inputs.gcs_model_path` in the Vertex model configuration | Preserve unless retraining every model and losing prior artifacts is intentional. |
| Terraform state | Environment backend configuration | Preserve. It is required to reconcile deleted infrastructure. |

For the included reference implementation, the boundary is:

```text
Preserve: tds-favorita.raw_favorita
Rebuild:  tds-favorita.favorita
```

Treat these names as examples. Resolve the actual project and datasets from the target environment before doing anything destructive.

## When to use this runbook

Appropriate uses include:

- a controlled development or non-production reset;
- validating that the platform is reproducible from its declared inputs;
- recovery from an irreparably inconsistent derived dataset;
- an explicitly approved disaster-recovery exercise.

Do not use it to deploy ordinary model, SQL, configuration, or schema changes. Do not use it in production without an approved change window, owners for data and ML validation, and a recovery decision.

## Prerequisites

Before starting, confirm that you have:

- read access to the preserved raw dataset;
- permission to delete and recreate the derived dataset;
- permission to run BigQuery jobs and create BigQuery models;
- access to the Terraform backend and the correct environment configuration;
- access to the configured GCS model-artifact bucket;
- valid Docker and GCP credentials configured through `.env`;
- a clean, reviewed code revision to rebuild from;
- enough time and BigQuery/Vertex budget to rerun transformations and training.

Record the code commit, operator, target environment, start time, and reason for the rebuild in the relevant change or incident record.

## 1. Resolve and verify the target

Read the values from `.env` and the matching Terraform environment configuration:

```text
GOOGLE_PROJECT_ID=<project>
BQ_RAW_DATASET=<source dataset to preserve>
DBT_DATASET=<derived dataset to rebuild>
DBT_TARGET=<dbt target>
```

Stop immediately if:

- any value is empty or still contains a placeholder;
- `BQ_RAW_DATASET` equals `DBT_DATASET`;
- the project or environment is not the intended target;
- the proposed deletion target includes the raw dataset;
- the Terraform state or environment configuration cannot be identified.

Print and independently review the fully qualified boundary before deletion:

```text
PRESERVE: <GOOGLE_PROJECT_ID>.<BQ_RAW_DATASET>
DELETE:   <GOOGLE_PROJECT_ID>.<DBT_DATASET>
```

Have a second reviewer confirm the boundary for shared or production environments.

## 2. Capture a pre-rebuild inventory

Inventory both datasets and preserve the output with the change record:

```bash
bq ls --format=prettyjson <GOOGLE_PROJECT_ID>:<BQ_RAW_DATASET>
bq ls --format=prettyjson <GOOGLE_PROJECT_ID>:<DBT_DATASET>
```

Also record:

- source-table row counts and maximum source timestamps;
- the current dbt object inventory;
- active model/configuration names and recent model run IDs;
- current forecast or prediction row counts and date ranges;
- relevant dataset location, labels, expiration settings, and access grants.

This inventory is the baseline for post-rebuild validation. If any object in the derived dataset is not reproducible from code, raw data, configuration, or preserved artifacts, stop and back it up or move it outside the rebuild boundary.

## 3. Validate the rebuild definitions

Run the non-destructive checks before deleting anything:

```bash
make docker-build
make dbt-deps
make dbt-debug
make vertex-validate-configs
make vertex-backtest-plan
make test-unit
```

Review the target table IDs in:

- `dbt/dbt_project.yml` and the active dbt profile;
- `vertex/config/model_config.yaml`;
- `vertex/ddl/vertex_bq_tables.sql`;
- the selected Terraform environment.

The checked-in Vertex DDL currently uses fully qualified reference-implementation table IDs. Those IDs are correct for the included Favorita environment, but a generalized deployment must parameterize or update them before running `make vertex-bq-ddl`. Do not apply the DDL until every target points to the intended derived dataset.

## 4. Delete the derived dataset

Deletion is intentionally not automated by this repository. Use the organization's approved BigQuery administration process to delete only the fully qualified `DBT_DATASET` confirmed above.

Do not delete:

- `BQ_RAW_DATASET` or its tables;
- Terraform state;
- GCS source objects;
- model artifacts unless full retraining and loss of model history are explicitly in scope.

After deletion, confirm that the derived dataset is absent and the raw dataset and its expected tables remain present. Record this checkpoint before proceeding.

## 5. Recreate dataset-level infrastructure

Reconcile the deleted derived dataset through the Terraform environment that owns it:

```bash
cd terraform/environments/<environment>
terraform init -backend-config="bucket=<state-bucket>"
terraform plan
terraform apply
```

The plan should recreate the missing analytics dataset without replacing the raw dataset or unrelated resources. Review the plan before applying it.

Afterward, verify the derived dataset's location, labels, access grants, and expiration settings against the pre-rebuild inventory and Terraform configuration. See [Terraform provisioning](../terraform/README.md) and [Infrastructure as code](iac.md) for environment setup and ownership details.

## 6. Recreate platform-owned output tables

Apply the idempotent Vertex and forecast-output DDL after the derived dataset exists:

```bash
make vertex-bq-ddl
```

Confirm that the expected job-run, model metadata, performance, optimization, prediction, forecast-contract, forecast-run, forecast-output, and status-history tables exist. The authoritative definitions are in `vertex/ddl/vertex_bq_tables.sql`.

## 7. Rebuild dbt transformations

Build staging, intermediate, and non-BQML marts from the preserved raw dataset:

```bash
make dbt-run-full-refresh
make dbt-test
make dbt-source-freshness
```

If the implementation uses seeds or snapshots, also run the applicable commands:

```bash
make dbt-seed
make dbt-snapshot
```

Do not continue to model execution until dbt tests pass or every exception is reviewed and documented.

## 8. Rebuild the BigQuery ML path

Create the configured BQML models, predictions, evaluations, and explanations:

```bash
make dbt-train
make dbt-predict
```

Validate that every configured model expected for the environment exists and that prediction outputs cover the expected entities and dates.

## 9. Rebuild the Vertex path

Train before predicting when the derived metadata tables were deleted. Repeat for each model configuration required by the environment:

```bash
make vertex-train VERTEX_CONFIG=<config-name>
make vertex-predict VERTEX_CONFIG=<config-name>
```

Optimization is optional and should follow the environment's normal cadence rather than being run automatically during every rebuild:

```bash
make vertex-optimize VERTEX_CONFIG=<config-name>
```

If a preserved artifact is intentionally reused, pin and verify its model run ID according to [the Vertex guide](../vertex/README.md). Never assume that the latest artifact and newly rebuilt metadata refer to the same run.

## 10. Rebuild downstream marts and monitoring

Stage the new Vertex outputs and rebuild downstream evaluation models:

```bash
make dbt-vertex
make selector-accuracy-monitoring
make dbt-test
```

Start or re-enable orchestration only after the rebuilt environment passes validation. See [the orchestration guide](../orchestration/README.md) for deployment and worker commands.

## 11. Validate the rebuilt environment

Compare the rebuilt environment with the pre-rebuild inventory. At minimum, verify:

- the raw dataset is unchanged and source freshness is acceptable;
- the derived dataset has the intended location, labels, IAM, and lifecycle settings;
- expected dbt relations and BQML models exist;
- dbt tests pass;
- Vertex job, metadata, performance, and prediction tables contain the new runs;
- prediction and forecast coverage matches the configured grain and horizons;
- row counts and date ranges are plausible relative to the preserved sources;
- model metrics are compared with appropriate baselines and previous accepted results;
- scheduled workflows are enabled only after their dependencies are healthy.

Generate dbt documentation if desired:

```bash
make dbt-docs-generate
```

Record the final commit, run IDs, validation results, completion time, and any accepted differences in the change or incident record.

## Failure and recovery

If the rebuild fails:

1. Stop scheduled workflows to prevent partial downstream publication.
2. Preserve logs, dbt artifacts, job run IDs, and the failing command.
3. Correct configuration or code through the normal review process.
4. Resume from the earliest failed idempotent step when safe.
5. Repeat the full post-rebuild validation before enabling consumers.

Deleting the derived dataset again should be a last resort, not the default retry mechanism. If the raw dataset was altered or deleted, stop: that is outside this runbook and requires source restoration or incident recovery.

## Routine operation after recovery

After the system is healthy, return to the normal operating workflow:

- incremental feature refreshes rather than full rebuilds;
- idempotent DDL and reviewed migrations rather than dataset deletion;
- daily champion scoring and monitoring;
- scheduled or trigger-based challenger retraining;
- gated promotion and rollback procedures.

The derived dataset is reconstructible by design, but its deletion remains an exceptional, explicitly approved operation.
