# Product roadmap

## Implemented

- Governed forecast contracts, rolling-origin backtesting, point-in-time features, model lifecycle,
  reconciliation, calibration, scheduled publication, monitoring/SLOs, delivery, webhooks, and FVA.
- ForecastLab overview, leaderboard, model detail, Forecast Explorer, experiments, error analysis,
  and read-only operational evidence.
- Typed FastAPI read models and append-only override, approval, publication, supersession, and
  rollback endpoints with optional IAP role authorization.
- Terraform modules, CI, documentation portal, synthetic Pages demo, and credential-free quickstart.

## In progress

- Phase 1 live read-only IAP deployment acceptance for the same-origin ForecastLab container; the
  fail-closed plan gate and sanitized live evidence command are implemented.
- Live warehouse acceptance for experiment, operations, and lifecycle UI workflows.
- Optional demand-source adapters and controlled production activation for external integrations.

## Experimental

- Phase 2 controlled planner mutation acceptance. The contracts and UI are implemented, but it
  remains separate from read-only activation and requires explicit mutation enablement and IAP
  roles; the public demo remains read-only.
- Bootstrap confidence evidence across matched rolling origins.

## Planned

- Pipeline-health and hierarchy/reconciliation workbench views.
- A second project implementation proving generality beyond Favorita.
- Gradual extraction of generic contracts into a stable platform-core package.

## Out of scope

- Multi-tenant SaaS billing, a hosted marketplace, direct browser access to BigQuery, and non-GCP
  production guarantees.

The current repository is a production-style GCP demand-forecasting platform foundation. Live
acceptance records—not screen availability alone—determine production readiness.
