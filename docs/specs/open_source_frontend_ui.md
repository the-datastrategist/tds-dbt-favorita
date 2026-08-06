{% docs spec_open_source_frontend_ui %}

# SPEC: Open-source forecasting platform UI

**Status:** Proposed
**Roadmap reference:** [Specs overview](README.md) — P2 forecast operations and integration contracts; P3 open-source product readiness

---

## Summary

The platform exposes forecasting, backtesting, model lifecycle, reconciliation, and publication
capabilities through warehouse tables, Python services, Prefect flows, and documentation. It does
not yet provide a cohesive browser interface for analysts, planners, approvers, or platform
operators.

This spec defines an open-source frontend built with React, TypeScript, and Vite, backed by a
versioned FastAPI boundary. The same frontend supports two deployment modes:

- a public, read-only demonstration on GitHub Pages using sanitized or bundled data; and
- an authenticated production application deployed with its API on Cloud Run or another
  container-compatible runtime.

The UI is a consumer of platform contracts. It must not query BigQuery directly, embed cloud
credentials, or reproduce forecast lifecycle rules in browser-only code.

## Goals

- Provide one navigable interface for forecast exploration, model performance, lifecycle state,
  hierarchy reconciliation, pipeline health, and publication history.
- Support planner and approver workflows once the forecast-operations API is available.
- Keep the application source, dependencies, build, and local development workflow open source.
- Reuse canonical run IDs, contract hashes, provenance fields, and status transitions already
  defined by the forecasting platform.
- Make a read-only demonstration deployable as static assets on GitHub Pages.
- Make the production build deployable without source changes behind authenticated APIs.
- Meet WCAG 2.1 AA accessibility expectations for core workflows.

## Non-goals

- Connecting a browser directly to BigQuery, Vertex AI, Prefect, or Terraform.
- Storing service-account keys, client secrets, or privileged configuration in frontend assets.
- Replacing dbt Docs, MLflow, or the Prefect UI for their specialist administrative functions.
- Implementing forecast algorithms, reconciliation, calibration, or lifecycle state machines in
  TypeScript.
- Providing multi-tenant billing, marketplace packaging, or a hosted SaaS control plane in the
  first release.
- Treating the public GitHub Pages build as a secure operational deployment.

## Users and permissions

| Role | Primary needs | Minimum access |
|------|---------------|----------------|
| Viewer | Inspect published forecasts, accuracy, and provenance | Read published data |
| Analyst | Compare models, baselines, segments, and horizons | Read runs and evaluation data |
| Planner | Review exceptions and propose forecast overrides | Viewer plus draft/override actions |
| Approver | Approve or reject forecast drafts | Planner plus approval actions |
| Publisher | Publish, supersede, or roll back approved versions | Approver plus publication actions |
| Operator | Diagnose pipeline runs and failed quality gates | Read operational metadata and retry links |

Authorization is enforced by the API. Hiding a button in the browser is a usability measure, not
an authorization control.

## Architecture

```text
GitHub Pages demo                   Production deployment
-----------------                   ---------------------
React/Vite static assets            React/Vite static assets
        |                                    |
bundled sanitized fixtures          OIDC access token over HTTPS
                                             |
                                             v
                                      versioned FastAPI
                                             |
                           +-----------------+-----------------+
                           |                 |                 |
                        BigQuery          Prefect       platform services
```

### Open-source technology choices

| Layer | Default | Purpose |
|-------|---------|---------|
| Frontend | React + TypeScript + Vite | Static application and build tooling |
| Routing | React Router | URL-addressable application views |
| Server state | TanStack Query | Fetching, caching, retries, and invalidation |
| Tables | TanStack Table | Accessible sorting, filtering, and pagination |
| Charts | Apache ECharts | Forecast intervals, accuracy, and hierarchy visualizations |
| Components | shadcn/ui or Material UI | Accessible, reusable interface primitives |
| API | FastAPI + Pydantic | Versioned HTTP boundary over platform services |
| Authentication | OpenID Connect | Portable identity integration |
| Self-hosted identity option | Keycloak | Open-source OIDC provider for deployments that require it |
| Packaging | Docker + Docker Compose | Reproducible local and production builds |

Dependencies must be pinned, license-reviewed, and replaceable at their architectural boundary.
The project license remains authoritative for original application code.

## Repository layout

The implementation should use an explicit boundary between browser and server code:

```text
frontend/
  src/
    api/
    components/
    features/
      forecasts/
      accuracy/
      hierarchy/
      lifecycle/
      operations/
      pipeline-health/
    pages/
    test/
  public/
  package.json
  vite.config.ts

api/
  routes/
  schemas/
  services/
  auth/
  tests/
```

Generic forecast rules stay in the existing Python platform modules. API services call those
modules rather than duplicating validation or transition logic.

## Information architecture

### 1. Platform overview

Show the latest forecast origin, active champion, publication status, coverage, exception count,
recent accuracy, and pipeline health. Every summary card links to its underlying filtered view.

### 2. Forecast explorer

Required filters:

- forecast run or published version
- forecast origin and target-date range
- entity and hierarchy node
- horizon
- forecast strategy and model
- confidence or exception state

Required visualization:

- actuals where available
- P50 forecast
- P10–P90 interval
- statistical and adjusted/published values when they differ
- provenance drawer containing contract, model, calibration, reconciliation, feature, cutoff,
  code, and publication identifiers

### 3. Accuracy and backtesting

Compare configured ML models and baselines by horizon, segment, rolling origin, and metric. Clearly
distinguish backtest, holdout, and realized production accuracy. Metric definitions must link to
the platform documentation.

### 4. Model lifecycle

Display candidates, promotion checks, current champion, lifecycle events, waivers, and rollback
history. The initial release is read-only. Promotion actions require a separate authenticated API
contract and confirmation flow.

### 5. Hierarchy and reconciliation

Allow users to navigate hierarchy levels, compare base and reconciled forecasts, and inspect
coherence checks. Quantile ordering or coherence failures must appear as failed gates, not as
silently corrected UI values.

### 6. Forecast operations

Once the operations API is implemented, provide:

- exception queue
- override editor with reason code and comment
- draft review
- approval or rejection
- publication confirmation
- revision, supersession, and rollback history

The UI submits intentions to the API; the API validates state transitions, permissions,
idempotency, and append-only audit records.

### 7. Pipeline health

Show scheduled run stages, durations, retry state, validation gates, row-count envelopes, and links
to specialist Prefect or cloud logs. Do not expose secrets, raw tokens, or unrestricted log
payloads.

## API boundary

The UI consumes a versioned `/v1` JSON API. Initial read-only endpoints should include:

```text
GET /v1/platform/summary
GET /v1/forecasts
GET /v1/forecast-runs/{forecast_run_id}
GET /v1/backtests
GET /v1/models/leaderboard
GET /v1/models/lifecycle
GET /v1/hierarchies/{hierarchy_version}
GET /v1/publications
GET /v1/pipeline-runs
```

Operational endpoints are owned by the integration and forecast-operations contracts:

```text
POST /v1/overrides
POST /v1/forecast-runs/{forecast_run_id}/approve
POST /v1/forecast-runs/{forecast_run_id}/publish
POST /v1/publications/{publication_version}/supersede
```

API requirements:

- cursor pagination for large result sets
- server-side filtering and ordering
- explicit UTC timestamps and documented display-time-zone behavior
- stable error envelopes and machine-readable error codes
- request IDs and audit actor identity
- optimistic-concurrency or version checks for mutations
- idempotency keys for publication and other retryable writes
- canonical forecast identifiers and provenance in response schemas
- generated OpenAPI documentation and a generated or schema-checked TypeScript client

## Authentication and security

### Public demo

The GitHub Pages build is public and read-only. It uses bundled, generated, or explicitly
sanitized fixtures. It must make no authenticated cloud requests and contain no confidential
forecast, customer, employee, or infrastructure data.

### Production

The production application uses Authorization Code Flow with PKCE through an OpenID Connect
provider. The browser is a public client and stores no client secret. The API validates issuer,
audience, signature, expiry, and role claims before serving protected data or accepting actions.

Additional requirements:

- least-privilege role mapping
- narrow redirect URIs and CORS origins
- HTTPS only outside local development
- no long-lived tokens in local storage where a safer session pattern is available
- content security policy and dependency vulnerability scanning
- server-side audit records for every operational mutation
- confirmation and reason capture for high-impact actions

## Deployment modes

### GitHub Pages demo

- Build static assets through GitHub Actions.
- Publish beneath the existing repository site, preferably `/app/`.
- Configure Vite's base path for `/tds-dbt-favorita/app/`.
- Preserve the existing documentation portal and dbt Docs routes.
- Use hash routing or an equivalent static-host-compatible fallback.
- Publish only sanitized fixtures committed or generated during the build.

### Authenticated production

- Build the frontend and FastAPI service as reproducible containers.
- Deploy the API with a dedicated runtime identity and least-privilege data access.
- Serve the frontend from Cloud Run, an object/CDN host, or the same application gateway.
- Keep environment-specific API origins and OIDC public configuration outside source code.
- Run database queries and platform mutations only through the API identity.

## Accessibility and responsive behavior

- Meet WCAG 2.1 AA for the core read, override, approval, and publication paths.
- Support keyboard navigation and visible focus states.
- Provide accessible names and text alternatives for charts and status indicators.
- Never encode model quality, exceptions, or lifecycle state by color alone.
- Provide tabular alternatives for forecast and accuracy charts.
- Support desktop and tablet operational use; small-screen views may be read-only where complex
  editing cannot be made safe.

## Observability

- Frontend errors include a request ID but no forecast payload or token.
- API logs include route, status, latency, actor ID, and request ID with sensitive fields redacted.
- Track endpoint latency, failure rate, authorization denials, stale-data age, and mutation
  outcomes.
- Product analytics are opt-in for the public OSS distribution and documented when enabled by a
  deployment.

## Implementation plan

### Phase 1 — read-only foundation

1. Scaffold React, TypeScript, and Vite with linting, tests, and accessible primitives.
2. Define API schemas and generate or validate the TypeScript client.
3. Add application shell, navigation, error boundaries, and loading/empty/error states.
4. Implement platform overview, forecast explorer, accuracy, and model lifecycle views.
5. Add sanitized demo fixtures and GitHub Pages deployment beneath `/app/`.

### Phase 2 — operational visibility

1. Add hierarchy reconciliation, publication history, and pipeline-health views.
2. Add authenticated production deployment and role-aware navigation.
3. Add deep links to dbt Docs, Prefect, MLflow, and runbook documentation where configured.

### Phase 3 — governed actions

1. Implement exception review and override submission.
2. Add approval and rejection flows.
3. Add publication, supersession, and rollback flows with explicit confirmation.
4. Add end-to-end audit, idempotency, authorization, and concurrency tests.

## Testing and validation

- Unit tests for formatting, filtering, permission presentation, and error states.
- Component accessibility checks and keyboard-navigation tests.
- Contract tests between OpenAPI schemas and the TypeScript client.
- Browser tests for forecast exploration and lifecycle drill-down.
- Mutation tests for override, approval, publication, supersession, idempotency, and stale-version
  conflicts.
- Static-build smoke test using the repository subpath.
- Test proving the GitHub Pages artifact contains no credentials or non-demo data.
- Production integration test against an isolated environment with least-privilege identities.
- Performance budgets for initial JavaScript, largest-contentful paint, and large-table interaction.

## Acceptance criteria

- A new contributor can run the frontend and fixture API locally using documented commands.
- The public demo loads from `/tds-dbt-favorita/app/` without breaking the documentation portal or
  dbt Docs.
- A viewer can find a published forecast, inspect uncertainty, and trace it to its model, contract,
  feature cutoff, calibration, reconciliation, and publication metadata.
- An analyst can compare ML models and baselines across rolling origins and horizons.
- The public artifact contains only sanitized data and no credentials.
- Production users authenticate through OIDC and the API enforces every role-protected operation.
- Once Phase 3 is delivered, authorized users can override, approve, publish, supersede, and roll
  back forecasts without overwriting append-only source records.
- Core workflows pass automated accessibility checks and manual keyboard validation.
- Frontend and API can be built and deployed using only documented open-source tooling.

## Open questions

- Should the first production identity integration use an existing client OIDC provider or a
  reference Keycloak deployment?
- Should production serve frontend assets from the API container or from a separate static host?
- Which hierarchy sizes require server-side aggregation rather than browser rendering?
- Which operational actions belong in the first UI release versus remaining CLI/API-only?
- What sanitized dataset best demonstrates intermittent demand, cold start, probabilistic
  intervals, and reconciliation without exposing client data?

## Related documents

- [Forecast contract and canonical output](forecast_contract_and_output.md)
- [Forecast operations](forecast_operations.md)
- [Integration contracts and forecast delivery](integration_contracts.md)
- [Scheduled forecast publication pipeline](scheduled_forecast_publication_pipeline.md)
- [Hierarchical reconciliation](hierarchical_reconciliation.md)
- [Monitoring, alerts, and SLOs](monitoring_and_slos.md)
- [Open-source product readiness](open_source_product_readiness.md)

{% enddocs %}
