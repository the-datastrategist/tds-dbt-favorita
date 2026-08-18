# ADR 0001: ForecastLab uses React, Vite, and FastAPI

- **Status:** Accepted
- **Date:** 2026-08-18
- **Owners:** ForecastLab maintainers

## Context

ForecastLab needs one open-source frontend that can run as a public, read-only GitHub Pages demo
and as an authenticated production application. The repository already has a versioned FastAPI
service boundary. Browser code must not query BigQuery directly or duplicate forecast lifecycle,
authorization, or audit rules.

The application is a filter-heavy analytical workbench. It does not require search-engine
rendering, server components, or a second backend-for-frontend runtime.

## Decision

Build ForecastLab as a React and TypeScript single-page application using Vite and React Router.
FastAPI remains the sole HTTP and authorization boundary.

- The public build is static and reads only the approved synthetic fixture dataset.
- The production build calls versioned FastAPI endpoints over HTTPS and uses OIDC public-client
  authentication.
- Fixture and live API adapters implement the same generated or schema-checked TypeScript types.
- Vite's repository base path supports the GitHub Pages `/tds-dbt-favorita/app/` deployment.
- Frontend code never constructs analytical SQL or holds cloud credentials.

## Consequences

This keeps local onboarding small, avoids a production Node.js server, and preserves one governed
Python service boundary. The same component tree can support fixture and authenticated modes.

The tradeoffs are that ForecastLab does not receive server-side rendering or Next.js server
features, deep links require static-host routing configuration, and public runtime configuration
must be non-secret browser configuration.

## Alternatives considered

- **Next.js:** Rejected for the initial workbench because its server features duplicate FastAPI and
  are unavailable in the GitHub Pages static mode.
- **Direct BigQuery access from the browser:** Rejected because it would expose credentials and
  bypass the platform's API, authorization, and audit contracts.

## Related decisions and specifications

- [Open-source frontend specification](../specs/open_source_frontend_ui.md)
- [ForecastLab UI/UX design](../FORECASTING_WORKBENCH_UI_DESIGN.md)
- [Public demo data contract](../frontend/public_demo_data.md)
