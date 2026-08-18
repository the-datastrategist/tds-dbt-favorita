{% docs specs_index %}

# Engineering specs — roadmap items

Working specs for the **longer-horizon roadmap items** that turn this repo into a production-style GCP demand forecasting platform. The roadmap is now tracked here, alongside [`docs/client_rollout.md`](../client_rollout.md#post-rollout-weeks-58-optional) "Post-rollout" items, [`docs/iac.md`](../iac.md#terraform-roadmap) "Terraform roadmap", and [`vertex/README.md`](../../vertex/README.md#adding-a-model-family) "Planned: prophet".

These are implementation specs for planned or evolving platform capabilities. The
[open-source forecasting platform guide](../platform_guide.md) documents the shipped architecture
and reusable components.
A completed spec should graduate into an accelerator entry in [accelerators.md](../accelerators.md).

---

## Status legend

| Status | Meaning |
|--------|---------|
| **Proposed** | Design written, not started |
| **In progress** | Implementation underway |
| **Shipped** | Merged; spec kept for history, accelerator updated |

---

## Specs

Status reviewed **2026-08-17**. The completion figures are implementation estimates, while
the status column continues to use the acceptance-based definitions above. Across the full
platform roadmap, including the proposed frontend and separate generalization workstream, the
current implementation is approximately **84% complete**. Excluding open-source productization,
the proposed frontend, and generalization, the accepted core platform roadmap is approximately
**98% complete**.

| Spec | Status | Completion | Roadmap reference | Summary |
|------|--------|-----------:|--------------------|---------|
| [Model leaderboard mart](model_leaderboard_mart.md) | Shipped | 100% | `client_rollout.md` → "Model leaderboard mart" | Unify BQML + Vertex holdout metrics into one ranked, champion-flagged mart |
| [Prediction accuracy monitoring](prediction_accuracy_monitoring.md) | Shipped | 100% | `client_rollout.md` → "Drift / accuracy monitoring" | dbt tests + mart that catch production accuracy degradation vs. training-time metrics |
| [Terraform modules](terraform_modules.md) | Shipped | 100% | `iac.md` → "Terraform roadmap" | Codify the manual GCP setup scripts as reviewable, per-environment IaC |
| [Workload Identity Federation](workload_identity_federation.md) | Shipped | 100% | `iac.md` → security checklist "prefer WIF" | Live-accepted repository-scoped GitHub OIDC authentication, keyless Terraform planning, and ADC-based dbt access |
| [Prophet model family](prophet_model_family.md) | Shipped | 100% | `vertex/README.md` → model families | Add `prophet` as a third time-series family via the existing registry pattern |
| [Forecast contract and canonical output](forecast_contract_and_output.md) | Shipped | 100% | Platform roadmap → P0 forecast contract | Live-accepted contract validation, canonical output DDL, staging, complete provenance, lifecycle status, and governed writer paths |
| [Rolling-origin backtesting and model lifecycle](backtesting_and_model_lifecycle.md) | Shipped | 100% | Platform roadmap → P0 backtesting/champion semantics | Live-accepted rolling-origin evaluation, governed promotion gates, scheduled lifecycle orchestration, and current-state warehouse views |
| [Point-in-time feature availability](point_in_time_feature_availability.md) | Shipped | 100% | Platform roadmap → P0 feature correctness | Live-accepted origin-specific cutoff enforcement, registry validation, persisted registry/source-cutoff evidence, and model-path integration |
| [Forecasting methods, horizons, cold start, and intermittent demand](forecasting_methods.md) | Shipped | 100% | Platform roadmap → P0/P1 methods | Seven-horizon direct scoring, intermittent-demand baselines, calibrated quantiles, cold-start routing, and live-accepted scheduled-stage integration |
| [Hierarchical reconciliation](hierarchical_reconciliation.md) | Shipped | 100% | Platform roadmap → P1 reconciliation | Configurable methods, scheduled integration, append-only base/reconciled evidence, level-wise backtest metrics, and live coherence/fail-closed acceptance are complete |
| [Demand data model](demand_data_model.md) | In progress | 80% | Platform roadmap → P1 demand data | Explicit observed-sales proxy, canonical store-day demand semantics, immutable run-level eligibility evidence, population gates, monitoring, and controlled exclusion acceptance are implemented; live optional-source adapters remain |
| [Forecast operations](forecast_operations.md) | In progress | 98% | Platform roadmap → P1/P2 operations | Append-only lifecycle, overrides, publication, rollback, delivery confirmation, and FVA marts are implemented; the planner UI remains |
| [Scheduled forecast publication pipeline](scheduled_forecast_publication_pipeline.md) | Shipped | 100% | Cross-spec operational integration | Live-accepted deterministic champion scoring, routing, calibration, reconciliation gates, leases, failure evidence, Prefect deployment, idempotent retry, and atomic draft visibility |
| [Monitoring, alerts, and SLOs](monitoring_and_slos.md) | In progress | 99% | Platform roadmap → P1 monitoring | All repository signals, including realized calibration, target/feature drift, and pipeline cost, are live accepted; applying real notification channels and witnessing delivery remain |
| [Integration contracts and forecast delivery](integration_contracts.md) | In progress | 95% | Platform roadmap → P2 integrations | Stable views, GCS export, events, delivery confirmation, and a private live-accepted read-only retrieval API are implemented; mutations and outbound webhooks remain |
| [Open-source forecasting platform UI](open_source_frontend_ui.md) | In progress | 5% | Platform roadmap → P2/P3 frontend | React/Vite/FastAPI architecture, approved demo-data boundary, logo, and self-hosted brand fonts are established; application scaffolding and views remain |
| [Open-source product readiness](open_source_product_readiness.md) | Proposed | 40% | Platform roadmap → P3 open source | Add governance, first-run quickstart, roadmap, compatibility, extension, and modularization plans |
| [General-purpose demand forecasting platform](platform_generalization.md) | Proposed | 0% | Separate platform-generalization workstream | Add canonical datasets, configurable periods, resource parameterization, and typed extension interfaces; multi-implementation validation is deferred |

---

## Related documents

- [Client rollout](../client_rollout.md) — where these items surface as "Backlog" / "Post-rollout"
- [Open-source forecasting platform guide](../platform_guide.md) — shipped architecture and reusable platform components
- [IaC and GCP operations](../iac.md) — current manual state each spec replaces
- [Accelerators](../accelerators.md) — where shipped specs get catalogued

{% enddocs %}
