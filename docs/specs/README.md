{% docs specs_index %}

# Engineering specs — roadmap items

Working specs for the **longer-horizon roadmap items** already flagged (but not designed) elsewhere in this repo: [`docs/client_rollout.md`](../client_rollout.md#post-rollout-weeks-58-optional) "Post-rollout" table, [`docs/iac.md`](../iac.md#terraform-roadmap) "Terraform roadmap", and [`vertex/README.md`](../../vertex/README.md#adding-a-model-family) "Planned: prophet".

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

| Spec | Status | Roadmap reference | Summary |
|------|--------|--------------------|---------|
| [Model leaderboard mart](model_leaderboard_mart.md) | Shipped | `client_rollout.md` → "Model leaderboard mart" | Unify BQML + Vertex holdout metrics into one ranked, champion-flagged mart |
| [Prediction accuracy monitoring](prediction_accuracy_monitoring.md) | Proposed | `client_rollout.md` → "Drift / accuracy monitoring" | dbt tests + mart that catch production accuracy degradation vs. training-time metrics |
| [Terraform modules](terraform_modules.md) | Proposed | `iac.md` → "Terraform roadmap" | Codify the manual GCP setup scripts as reviewable, per-environment IaC |
| [Workload Identity Federation](workload_identity_federation.md) | Proposed | `iac.md` → security checklist "prefer WIF" | Remove long-lived SA key files from CI, local dev, and Vertex Custom Jobs |
| [Prophet model family](prophet_model_family.md) | Proposed | `vertex/README.md` → "Planned: prophet" | Add `prophet` as a third time-series family via the existing registry pattern |

---

## Related documents

- [Client rollout](../client_rollout.md) — where these items surface as "Backlog" / "Post-rollout"
- [IaC and GCP operations](../iac.md) — current manual state each spec replaces
- [Accelerators](../accelerators.md) — where shipped specs get catalogued

{% enddocs %}
