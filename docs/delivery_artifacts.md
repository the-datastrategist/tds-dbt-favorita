{% docs delivery_artifacts %}

# Delivery artifacts

Delivery artifacts support **sales conversations, kickoff, delivery, and handoff**. They sit on top of the [accelerators](accelerators.md) and [reference architecture](reference_architecture.md).

---

## Artifact inventory

| Artifact | Document / location | Status | Audience |
|----------|---------------------|--------|----------|
| **Case study** | [case_study.md](case_study.md) | Available | Executive, product, data leaders |
| **Benchmarks** | [benchmarks.md](benchmarks.md) | Template + SQL recipes | ML engineers, platform |
| **Dashboard blueprint** | This page § Dashboard | Blueprint | Analytics, merchandising |
| **Rollout playbook** | [client_rollout.md](client_rollout.md) | Available | Delivery PM, client team |
| **IaC / GCP ops** | [iac.md](iac.md), `vertex/ops/README.md` | Runbook available | Platform / DevOps |
| **Architecture diagrams** | [reference_architecture.md](reference_architecture.md) | Available | All technical stakeholders |
| **Lineage & catalog** | dbt Docs + `exposures.yml` | Available (hosted on GitHub Pages) | Analytics engineering |
| **Demo walkthrough** | Root `README.md`, `make help` | Available | Hands-on evaluators |

---

## Case study

Narrative covering business context, constraints, technical approach, dual ML strategy, and client adaptation notes.

→ [case_study.md](case_study.md)

---

## Benchmarks

Structured comparison of BQML vs Vertex model families on holdout metrics (MAE, WAPE, RMSE, train duration). Includes BigQuery and MLflow queries to populate results after runs.

→ [benchmarks.md](benchmarks.md)

**Populate after a benchmark run:**

```bash
make dbt-run
make dbt-train && make dbt-predict          # BQML baseline
make vertex-train && make vertex-predict    # Vertex XGBoost (default)
make mlflow-ui                              # Visual comparison
```

---

## Dashboard blueprint

**Status:** Blueprint — consumption layer is documented and staged; a hosted BI dashboard is a recommended next artifact for client demos.

### Purpose

Give merchandising / planning teams a **forecast vs actual** view without opening MLflow or BigQuery consoles.

### Recommended data sources (already in repo)

| Source | Table / model | Use in dashboard |
|--------|---------------|------------------|
| Vertex predictions | `stg_vertex_model_predictions` | Forecast vs actual by store, date |
| Vertex metadata | `stg_vertex_model_metadata` | Champion model, run timestamp |
| Vertex job runs | `stg_vertex_job_runs` | Pipeline health, failures |
| BQML predictions | `bqml_model_predict` | Warehouse-native baseline |
| BQML evaluation | `bqml_model_evaluate` | Holdout metrics |
| Features | `int_sales_store_daily` | Context: promotions, holidays |

### Suggested pages

1. **Executive summary** — company-day forecast, WAPE trend, last successful pipeline run
2. **Store drill-down** — store-day actual vs predicted, top errors
3. **Model leaderboard** — rank by `test_mae` / `test_wape` from performance tables (see [benchmarks.md](benchmarks.md))
4. **Operations** — job run status from `stg_vertex_job_runs`

### Implementation options (client-specific)

| Tool | Effort | Best for |
|------|--------|----------|
| **Looker Studio** | Low | Fast GCP-native demo |
| **Looker / LookML** | Medium | Enterprise semantic layer |
| **Streamlit in Docker** | Medium | Custom demo app in same repo |
| **Hex / Evidence** | Medium | Analytics team self-serve |

### dbt exposure (add when dashboard exists)

When a dashboard is built, register it in `dbt/models/exposures.yml`:

```yaml
- name: favorita_forecast_dashboard
  type: dashboard
  maturity: high
  depends_on:
    - ref('stg_vertex_model_predictions')
    - ref('int_sales_store_daily')
```

---

## Rollout playbook

Four-week engagement template from discovery through first production refresh.

→ [client_rollout.md](client_rollout.md)

---

## Infrastructure as code

GCP provisioning guidance, IAM matrix, GCS layout, and Scheduler patterns. Full Terraform modules are **roadmapped**; operational runbook is **available today**.

→ [iac.md](iac.md)

---

## Supporting collateral checklist

Use during proposals and close:

- [ ] Link to hosted dbt Docs (GitHub Pages)
- [ ] 5-minute architecture diagram (from [reference_architecture.md](reference_architecture.md))
- [ ] Screenshot: dbt lineage on `favorita_vertex_predictions` exposure
- [ ] Screenshot: MLflow runs with `gcs_model_catalog.json`
- [ ] Screenshot: Prefect deployment runs (optional)
- [ ] Completed [benchmarks.md](benchmarks.md) table for at least XGBoost + BQML
- [ ] Client-specific IAM worksheet from [iac.md](iac.md)

---

## Related documents

- [Consulting package overview](consulting_package.md)
- Product views: [dbt](dbt/consulting_package.md) · [Vertex](vertex/consulting_package.md) · [MLflow](mlflow/consulting_package.md) · [Prefect](prefect/consulting_package.md)

{% enddocs %}
