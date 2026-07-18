{% docs specs_index %}

# Engineering specs — roadmap items

Working specs for the **longer-horizon roadmap items** already flagged (but not designed) elsewhere in this repo: [`docs/client_rollout.md`](../client_rollout.md#post-rollout-weeks-58-optional) "Post-rollout" table, [`docs/iac.md`](../iac.md#terraform-roadmap) "Terraform roadmap", [`vertex/README.md`](../../vertex/README.md#adding-a-model-family) "Planned: prophet", and [`docs/demand_forecasting_platform_recommendations.md`](../demand_forecasting_platform_recommendations.md) for the broader open-source demand forecasting platform roadmap.

These are **internal implementation specs**, not client-facing collateral — contrast with the [consulting package](../consulting_package.md) (case study, benchmarks, rollout playbook), which documents what's *already shipped*. A spec here should graduate into an accelerator entry in [accelerators.md](../accelerators.md) once implemented.

---

## Status legend

| Status | Meaning |
|--------|---------|
| **Proposed** | Design written, not started |
| **In progress** | Implementation underway |
| **Shipped** | Merged; spec kept for history, accelerator updated |

---

## Specs

Status reviewed **2026-07-18**. The completion figures are implementation estimates, while
the status column continues to use the acceptance-based definitions above. Across the full
platform roadmap, the current implementation is approximately **75% complete**.

| Spec | Status | Completion | Roadmap reference | Summary |
|------|--------|-----------:|--------------------|---------|
| [Model leaderboard mart](model_leaderboard_mart.md) | Shipped | 100% | `client_rollout.md` → "Model leaderboard mart" | Unify BQML + Vertex holdout metrics into one ranked, champion-flagged mart |
| [Prediction accuracy monitoring](prediction_accuracy_monitoring.md) | Shipped | 100% | `client_rollout.md` → "Drift / accuracy monitoring" | dbt tests + mart that catch production accuracy degradation vs. training-time metrics |
| [Terraform modules](terraform_modules.md) | Shipped | 100% | `iac.md` → "Terraform roadmap" | Codify the manual GCP setup scripts as reviewable, per-environment IaC |
| [Workload Identity Federation](workload_identity_federation.md) | In progress | 80% | `iac.md` → security checklist "prefer WIF" | Terraform resources and GitHub Actions authentication are implemented; live-environment configuration and CI validation remain |
| [Prophet model family](prophet_model_family.md) | Shipped | 100% | `vertex/README.md` → model families | Add `prophet` as a third time-series family via the existing registry pattern |
| [Forecast contract and canonical output](forecast_contract_and_output.md) | In progress | 90% | `demand_forecasting_platform_recommendations.md` → P0 forecast contract | Contract validation, canonical output DDL, staging, provenance, and the default writer path are implemented; a real GCP smoke test and accelerator graduation remain |
| [Rolling-origin backtesting and model lifecycle](backtesting_and_model_lifecycle.md) | Shipped | 100% | `demand_forecasting_platform_recommendations.md` → P0 backtesting/champion semantics | Live-accepted rolling-origin evaluation, governed promotion gates, scheduled lifecycle orchestration, and current-state warehouse views |
| [Point-in-time feature availability](point_in_time_feature_availability.md) | In progress | 90% | `demand_forecasting_platform_recommendations.md` → P0 feature correctness | Origin-specific cutoff enforcement, registry validation, persisted cutoff evidence, and model-path integration are implemented; live acceptance and accelerator graduation remain |
| [Forecasting methods, horizons, cold start, and intermittent demand](forecasting_methods.md) | In progress | 85% | `demand_forecasting_platform_recommendations.md` → P0/P1 methods | Horizon-aware models, intermittent-demand baselines, probabilistic calibration, cold-start fallbacks, and strategy routing are implemented; complete scheduled publication-path validation remains |
| [Hierarchical reconciliation](hierarchical_reconciliation.md) | In progress | 75% | `demand_forecasting_platform_recommendations.md` → P1 reconciliation | Configurable hierarchies, bottom-up/top-down/middle-out/MinT methods, persistence, and tests are implemented; scheduled publication integration remains |
| [Demand data model](demand_data_model.md) | Proposed | 20% | `demand_forecasting_platform_recommendations.md` → P1 demand data | Distinguish observed sales from demand and model inventory, eligibility, lifecycle, prices, and promotions |
| [Forecast operations](forecast_operations.md) | In progress | 50% | `demand_forecasting_platform_recommendations.md` → P1/P2 operations | Append-only override, approval, publication, revision, and exception tables plus staging contracts are implemented; workflow services and transition commands remain |
| [Monitoring, alerts, and SLOs](monitoring_and_slos.md) | Proposed | 35% | `demand_forecasting_platform_recommendations.md` → P1 monitoring | Define forecast freshness, completeness, accuracy, drift, calibration, pipeline, and cost monitoring |
| [Integration contracts and forecast delivery](integration_contracts.md) | Proposed | 25% | `demand_forecasting_platform_recommendations.md` → P2 integrations | Provide stable warehouse, API, export, webhook, and publication contracts |
| [Open-source product readiness](open_source_product_readiness.md) | Proposed | 40% | `demand_forecasting_platform_recommendations.md` → P3 open source | Add governance, first-run quickstart, roadmap, compatibility, extension, and modularization plans |

---

## Related documents

- [Client rollout](../client_rollout.md) — where these items surface as "Backlog" / "Post-rollout"
- [Demand forecasting platform recommendations](../demand_forecasting_platform_recommendations.md) — roadmap behind the new platform-level specs
- [IaC and GCP operations](../iac.md) — current manual state each spec replaces
- [Accelerators](../accelerators.md) — where shipped specs get catalogued

{% enddocs %}
