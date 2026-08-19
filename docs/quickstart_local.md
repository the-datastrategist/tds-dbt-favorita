# Local quickstart

Run a complete, deterministic forecasting example without GCP credentials, Docker, or external
data:

```bash
make quickstart-local
```

The command creates `artifacts/quickstart/` containing:

| Artifact | Contract |
|---|---:|
| `features.csv` | 126 store-day rows with lag and rolling features |
| `forecast_outputs.csv` | 21 seven-horizon forecasts across three stores |
| `benchmark.csv` | Seasonal-naive rolling holdout, WAPE `0.095177` |
| `manifest.json` | Dataset version, row counts, benchmark, and file allowlist |

The input is generated from a deterministic formula and contains no downloaded or client data.
The command fails if row counts or the reference benchmark drift. Inspect the CSV files directly,
or launch the synthetic ForecastLab workbench separately from `frontend/` with `npm run dev`.

Clean up with:

```bash
make quickstart-clean
```

This quickstart proves the contributor workflow and artifact shape; it is not a production
benchmark or a substitute for live BigQuery acceptance.
