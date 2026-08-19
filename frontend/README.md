# ForecastLab frontend

ForecastLab is the React, TypeScript, and Vite workbench for the forecasting platform. Its current
public-demo slice includes a platform overview, responsive model leaderboard, and model-evidence
drilldown backed by a deterministic, synthetic fixture.

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
- `/models/leaderboard` for horizon- and segment-filtered comparisons; and
- `/models/:modelId` for model evidence details.

The public build is published with the documentation site at
`https://the-datastrategist.github.io/tds-dbt-favorita/app/`.

## Validate

```bash
npm run validate
npx playwright install chromium
npm run test:e2e
```

`validate` checks formatting, lint rules, TypeScript, unit/component tests, and the GitHub Pages
production build. `test:e2e` checks the primary filter-to-drilldown journey and automated WCAG
violations in Chromium.

## Builds and data modes

- `npm run build` creates a root-hosted production build.
- `npm run build:pages` creates a build with the `/tds-dbt-favorita/app/` base path.
- `VITE_DATA_MODE=fixture` is the default and reads `src/fixtures/forecastlab_demo_v1.json`.
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
