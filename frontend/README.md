# ForecastLab frontend

ForecastLab is the React, TypeScript, and Vite workbench for the forecasting platform. Its current
public-demo slice includes a platform overview, responsive model leaderboard, model-evidence
drilldown, experiment history and comparison, and canonical Forecast Explorer backed by
deterministic synthetic fixtures.

The production adapter validates the typed responses from `GET /v1/forecasts/options` and
`GET /v1/forecasts`. The root Dockerfile creates this build and embeds it in the FastAPI image:

```bash
VITE_DATA_MODE=api VITE_API_BASE_URL= npm run build
```

The public Pages build always remains fixture-backed and makes no production warehouse requests.
Cloud Run serves the browser application and API from the same IAP-protected origin; do not embed
bearer tokens or cloud credentials in Vite environment variables.

## Run locally

Node.js 22.12 or newer is required.

```bash
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173/overview`. The default data source is local and makes no network
requests. Available routes are:

- `/overview` for the champion, horizon-performance, and selection-evidence summary;
- `/forecasts` for actuals, P10/P50/P90 forecasts, published adjustments, and provenance;
- `/experiments` for sortable, filterable run history and comparison selection;
- `/experiments/compare?runs=…` for 2–5 run scientific comparisons;
- `/models/leaderboard` for horizon- and segment-filtered comparisons; and
- `/models/:modelId` for model evidence details.

The public build is published with the documentation site at
`https://the-datastrategist.github.io/tds-dbt-favorita/app/`.
Static-host routes use fragments, so the Forecast Explorer is directly addressable at
`https://the-datastrategist.github.io/tds-dbt-favorita/app/#/forecasts` without a Pages 404 on
refresh. Root-hosted and API deployments continue to use normal browser paths.

## Validate

```bash
npm run validate
npx playwright install chromium
npm run test:e2e
npm run build:pages
npm run test:pages
```

`validate` checks formatting, lint rules, TypeScript, unit/component tests, and the GitHub Pages
production build. `test:e2e` checks the primary filter-to-drilldown journeys and automated WCAG
violations in Chromium. After `build:pages`, `test:pages` verifies that direct experiment hash
routes load and survive refresh beneath the repository subpath.

## Builds and data modes

- `npm run build` creates a root-hosted production build.
- `npm run build:pages` creates a build with the `/tds-dbt-favorita/app/` base path.
- `VITE_DATA_MODE=fixture` is the default and reads the allowlisted model-performance and canonical
  forecast fixtures in `src/fixtures/`.
- `VITE_DATA_MODE=api VITE_API_BASE_URL=http://localhost:8000` opts into the typed FastAPI adapter.

Only public values may use the `VITE_` prefix because Vite embeds them in browser assets. The demo
fixture is synthetic and is covered by a regression test for URLs, email addresses, secrets, and
customer identifiers.

## Packaged assets

- `public/brand/` - approved secondary-attribution logo and usage terms;
- `src/assets/fonts/` - self-hosted Space Grotesk and Poppins WOFF2 files, CSS, checksums, and SIL
  Open Font License notices.

## Design and architecture references

- [ADR 0001](../docs/adr/0001-forecastlab-react-vite-fastapi.md)
- [Frontend specification](../docs/specs/open_source_frontend_ui.md)
- [UI/UX design](../docs/FORECASTING_WORKBENCH_UI_DESIGN.md)
- [Public demo data contract](../docs/frontend/public_demo_data.md)
