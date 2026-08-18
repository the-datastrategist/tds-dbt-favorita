# Forecasting Workbench — UI/UX Design Document

**Project:** GCP Demand Forecasting Platform
**Working product name:** ForecastLab
**Frontend:** React + TypeScript + Vite
**Document type:** Product / UI / UX design specification
**Primary audience:** Codex implementation, product/design review, portfolio presentation
**Status:** Proposed
**Design direction:** Ramp-inspired application UX + restrained theDataStrategist visual identity

---

## 1. Executive Summary

ForecastLab is a scientist-facing workbench for exploring, comparing, explaining, and monitoring demand forecasts produced by the GCP Demand Forecasting Platform.

The application is **not** intended to be a generic business-intelligence dashboard. It is a decision surface for questions such as:

- Which model currently performs best?
- Does the winner change by forecast horizon or segment?
- Is the improvement over the baseline meaningful and stable?
- Where does the current champion fail?
- Which feature groups materially improve forecast quality?
- Why did a specific forecast increase or decrease?
- Are prediction intervals calibrated?
- Is production accuracy degrading relative to backtest performance?
- Which model version, feature set, dataset, and code revision produced a forecast?

The experience should combine:

1. **Ramp's product design philosophy:** clean application shell, dense but readable information, excellent tables and filters, restrained surfaces, fast drill-down, low visual noise, and workflow-first interaction.
2. **theDataStrategist visual identity:** Space Grotesk, the lemon accent `#E2F86C`, dark graphite `#2E2E2E`, clean white/gray surfaces, and a pragmatic analytical tone.
3. **A forecasting-science emphasis:** rolling-origin evaluation, baselines, horizon-specific metrics, experiment comparisons, uncertainty, error analysis, explainability, and model lifecycle.

TheDataStrategist branding should be **subtle**. ForecastLab should look like a standalone software product built by theDataStrategist, not like an embedded page from the consulting website.

---

# 2. Product Goals

## 2.1 Primary goals

The UI must:

1. Make forecasting quality understandable within 30 seconds.
2. Let a technical user drill from aggregate performance into individual forecasts.
3. Make model comparisons scientifically defensible.
4. Expose the platform's experiment tracking and model lifecycle.
5. Surface production performance and degradation.
6. Demonstrate the full value of the forecasting platform to hiring managers, prospective clients, and technical collaborators.
7. Remain credible as an internal production tool rather than a portfolio-only demo.

## 2.2 Secondary goals

- Give the underlying BigQuery / Vertex / MLflow metadata a coherent visual layer.
- Make the project easy to demo without requiring users to inspect repository files.
- Provide stable deep links to experiments, models, and forecast slices.
- Allow screenshots to work well in portfolio case studies.

## 2.3 Non-goals for MVP

Do not spend significant engineering effort on:

- Billing
- User administration
- Complex RBAC
- Generic CRUD
- Collaboration/comments
- Mobile-first workflows
- Notification centers
- Marketing animations
- AI chat assistants
- Free-form dashboard builders
- Full notebook replacement
- Editing training configuration in the UI

These can be considered later, but they do not materially improve the initial scientific or portfolio value.

---

# 3. Target Users

## 3.1 Data Scientist

Needs to:
- compare models;
- inspect backtests;
- analyze errors;
- understand feature contribution;
- identify failure modes;
- validate uncertainty;
- select a champion.

## 3.2 ML Engineer

Needs to:
- inspect model versions;
- trace artifacts and code;
- see pipeline status;
- confirm production freshness;
- investigate degraded models.

## 3.3 Analytics / Operations Stakeholder

Needs to:
- understand whether forecasts are reliable;
- inspect forecast vs. actual;
- understand drivers;
- see where uncertainty is high.

## 3.4 Portfolio Reviewer / Hiring Manager

Needs to understand quickly that the system includes:

- strong forecasting methodology;
- governed feature pipelines;
- comparative experimentation;
- uncertainty and calibration;
- explainability;
- model lifecycle;
- production monitoring.

This user should be able to understand the project's sophistication without reading the repository first.

---

# 4. Design Principles

## 4.1 Decision-first

Every page should answer a concrete question.

Avoid vague page framing such as:

> Analytics Dashboard

Prefer:

> Model Leaderboard
> Which model wins by horizon and segment?

or:

> Error Analysis
> Where is forecast error concentrated?

---

## 4.2 Dense, calm, precise

The application should feel closer to Ramp than to a consumer SaaS landing page.

Use:

- compact navigation;
- tight but comfortable table rows;
- restrained cards;
- subtle borders;
- minimal shadow;
- small contextual controls;
- inline filtering;
- highly legible metric presentation;
- strong alignment;
- consistent spacing;
- progressive disclosure.

Avoid:

- giant KPI cards;
- excessive rounded containers;
- glassmorphism;
- decorative gradients;
- chart-heavy "dashboard walls";
- rainbow color palettes;
- giant page titles;
- excessive empty space.

---

## 4.3 Science before infrastructure

The default UI hierarchy should prioritize:

1. forecast quality;
2. model comparison;
3. uncertainty;
4. segment behavior;
5. experiment findings;
6. error analysis;
7. explainability.

Technical metadata should remain accessible but secondary.

---

## 4.4 Progressive disclosure

A model row should initially show:

- model name;
- primary metric;
- horizon;
- bias;
- status;
- last evaluated time.

Clicking it should reveal:

- all metrics;
- run history;
- training window;
- feature version;
- hyperparameters;
- artifact path;
- Git SHA;
- deployment metadata.

---

## 4.5 The UI should expose findings, not merely data

Whenever possible, pair metrics with a derived interpretation.

Example:

> **11.8% WAPE**
> 32.9% better than seasonal naive

or:

> **Coverage: 71%**
> Below the 80% interval target

This makes the product scientifically useful and easier to demo.

---

# 5. Visual Identity

## 5.1 Brand relationship

ForecastLab should have a standalone identity.

Recommended header treatment:

**ForecastLab**
*Demand Forecasting Workbench*

Optional attribution in the About / footer area:

> Built by theDataStrategist

Do **not** use the full theDataStrategist wordmark as the primary application logo.

The tDS mark may be used sparingly in:

- About dialog;
- app footer;
- favicon / secondary attribution;
- documentation link.

The approved source asset is checked in at
`frontend/public/brand/tds-logo-circle-white.jpg`. Follow its adjacent usage and licensing notes;
do not reconstruct the mark from text or derive transparent/favicon variants from the JPEG.

---

## 5.2 Brand guide elements to retain

Source of truth: *TheDataStrategist Brand Guideline (2026)*. This document derives product UI
rules from that guide; it does not replace the original logo artwork or grant additional asset
rights.

### Primary typeface
**Space Grotesk**

Use for:
- product name;
- page headings;
- major metric values;
- section titles.

### Secondary typeface
**Poppins**

Use selectively for:
- supporting text;
- marketing-style callouts;
- optional branded surfaces.

### Product UI recommendation

For the application itself, use:

```text
Primary UI font: Space Grotesk
Code / identifiers: Geist Mono or system monospace
```

Poppins should be optional rather than used throughout the application. A single UI type family creates a cleaner, more Ramp-like system.

For the open-source build, self-host approved Space Grotesk and Poppins files with their font
license notices. The public demo must not require a third-party font request.

---

## 5.3 Core brand colors

Brand guide source palette:

| Token | Brand color | HEX |
|---|---|---|
| Graphite | Light Black | `#2E2E2E` |
| Accent | Lemony | `#E2F86C` |
| Neutral | Sweet Grey | `#D8D8D8` |
| Base | White | `#FFFFFF` |

The guide also defines complete neutral and lemon ramps. ForecastLab should expose those values as
primitive tokens, then consume semantic aliases in components:

| Ramp | Values from light to dark |
|---|---|
| Neutral A | `#E5E5E5`, `#D5D5D5`, `#C5C5C5`, `#B5B5B5`, `#A5A5A5`, `#878787`, `#6A6A6A`, `#4C4C4C`, `#2E2E2E`, `#242424`, `#151515` |
| Lemon | `#F9FEE9`, `#F2FCC7`, `#EAFA9D`, `#E2F86C`, `#D5E865`, `#C5D85E`, `#B6C857`, `#A4B44F`, `#8F9D45`, `#7A863A`, `#656F30` |
| Neutral B | `#F8F8F8`, `#EDEDED`, `#E3E3E3`, `#D8D8D8`, `#CACACA`, `#BCBCBC`, `#AEAEAE`, `#9D9D9D`, `#898989`, `#757575`, `#616161` |

### Product interpretation

Do not make lemon the dominant interface color.

Use `#E2F86C` for:

- selected navigation accent;
- active filter indicator;
- focus state;
- champion highlight;
- small badges;
- chart emphasis;
- occasional primary CTA.

Avoid using it as:
- full-page background;
- every button;
- every chart series;
- large table backgrounds.

Do not use lemon alone to mean success, healthy, approved, or champion. Those meanings require a
text label or icon and a separate semantic token. Lemon text on white is not an approved body-text
pairing.

The application should remain approximately **85–90% neutral**.

---

# 6. Design Tokens

## 6.1 Light theme

```css
:root {
  --background-app: #F7F7F5;
  --background-surface: #FFFFFF;
  --background-subtle: #F1F1EE;
  --background-hover: #ECEDEA;

  --border-default: #E0E1DD;
  --border-strong: #C9CBC5;

  --text-primary: #20211F;
  --text-secondary: #5F625C;
  --text-muted: #8A8D86;

  --brand-graphite: #2E2E2E;
  --brand-lemon: #E2F86C;
  --brand-lemon-soft: #F2FCC7;
  --brand-sweet-grey: #D8D8D8;

  --success: #247A4A;
  --success-soft: #E8F5ED;
  --warning: #9A6700;
  --warning-soft: #FFF4CE;
  --danger: #B42318;
  --danger-soft: #FDECEA;
  --info: #3559A8;
  --info-soft: #EBF0FC;
}
```

## 6.2 Dark theme — optional after MVP

```css
[data-theme="dark"] {
  --background-app: #191A18;
  --background-surface: #232421;
  --background-subtle: #2B2C29;
  --background-hover: #343531;

  --border-default: #383A35;
  --border-strong: #4C4F48;

  --text-primary: #F6F7F3;
  --text-secondary: #B8BBB3;
  --text-muted: #898D84;
}
```

The initial MVP may ship light-theme only.

---

# 7. Typography

Recommended scale:

| Role | Size | Weight | Notes |
|---|---:|---:|---|
| Page title | 28 px | 600 | Space Grotesk |
| Page subtitle | 14 px | 400 | muted |
| Section heading | 18 px | 600 | |
| Card heading | 14 px | 600 | |
| Primary metric | 28–32 px | 600 | tabular numerals |
| Body | 14 px | 400 | |
| Table | 13 px | 400–500 | |
| Filter / control | 13 px | 500 | |
| Metadata | 12 px | 400 | |
| Micro label | 11 px | 500 | uppercase sparingly |

Metric-heavy elements should use:

```css
font-variant-numeric: tabular-nums;
```

---

# 8. Layout System

## 8.1 Desktop application shell

```text
┌───────────────────────────────────────────────────────────────┐
│ ForecastLab                  Favorita ▾      Demo   GitHub  ? │
├───────────────┬───────────────────────────────────────────────┤
│               │                                               │
│ Overview      │ Page title                                    │
│               │ Description                    Page actions   │
│ Models        │                                               │
│  Leaderboard  │ Filters                                       │
│  Registry     │                                               │
│               │ Main content                                  │
│ Experiments   │                                               │
│  Runs         │                                               │
│  Ablations    │                                               │
│               │                                               │
│ Forecasts     │                                               │
│  Explorer     │                                               │
│  Errors       │                                               │
│               │                                               │
│ Explain       │                                               │
│ Monitoring    │                                               │
│               │                                               │
│ ───────────   │                                               │
│ Docs          │                                               │
│ Repository    │                                               │
└───────────────┴───────────────────────────────────────────────┘
```

### Dimensions

- Sidebar: `224px`
- Collapsed sidebar: `64px`
- Top bar: `56px`
- Main content max width: `1600px`
- Standard page horizontal padding:
  - desktop: `28–32px`
  - tablet: `20px`
  - mobile: `16px`

---

## 8.2 Grid

Use a 12-column grid for dashboard-like pages.

Primary patterns:

### Metric summary
4 equal columns.

### Main + secondary
8 / 4.

### Analysis
Full-width chart followed by table.

### Detail
Main content 8 columns + metadata rail 4 columns.

---

# 9. Navigation / Information Architecture

```text
/
├── overview
│
├── models
│   ├── leaderboard
│   ├── registry
│   └── [modelId]
│
├── experiments
│   ├── runs
│   ├── compare
│   ├── ablations
│   └── [runId]
│
├── forecasts
│   ├── explorer
│   ├── errors
│   └── [forecastId]
│
├── explainability
│
├── monitoring
│
└── about
```

Optional future routes:

```text
├── hierarchies
├── calibration
├── scenario-analysis
└── data-quality
```

---

# 10. Global Filters

The application should use a consistent filter bar similar to Ramp's reporting-table behavior.

Core filters:

- Evaluation window
- Forecast origin
- Horizon
- Grain
- Target
- Store
- Product family
- Demand segment
- Promotion status
- Model family
- Model version

### Interaction pattern

Primary filters should remain visible.

Additional filters appear as removable filter chips:

```text
Evaluation: Last 12 origins ▾

+ Filter

[Horizon: 7d ×] [Promotion: Yes ×] [Store: 44 ×]
```

Requirements:

- Filters must be encoded in the URL.
- Browser back/forward must preserve analysis state.
- Views should be shareable as deep links.
- Tables and charts on the same page must use the same filter context unless clearly labeled otherwise.

---

# 11. Screen 1 — Overview

## Purpose

Answer:

> How is the forecasting system performing right now?

## Above-the-fold content

### Header

```text
Forecast Performance
Current production and rolling-origin model health

Evaluation: Last 12 origins ▾    Grain: Store / Day ▾
```

### Metric strip

Use four compact metrics:

```text
Production WAPE
11.8%
↓ 32.9% vs seasonal naive

Forecast coverage
98.7%
↑ 0.4 pp

P10–P90 calibration
81.3%
Target: 80%

Current champion
XGBoost v17
Promoted 3 days ago
```

Do not place each metric in a large floating card. Prefer a single bordered metric band with four columns.

## Main chart

### WAPE by horizon

Series:
- champion
- seasonal naive
- strongest challenger

Horizon:
- 1
- 7
- 14
- 28

The chart should emphasize the champion and visually mute the baseline.

## Secondary panel

### Champion rationale

```text
Current champion
favorita_store_global_xgb_v17

Passed
✓ Lowest rolling-origin WAPE
✓ Bias within ±3%
✓ Prediction completeness > 99%
✓ No accuracy drift alert

Watch
△ Coverage weak at D+28
```

## Bottom section

- Recent experiments
- Active monitoring alerts
- Worst-performing segments
- Latest model promotion

---

# 12. Screen 2 — Model Leaderboard

## Purpose

Answer:

> Which model is best under the current evaluation conditions?

## Table columns

| Column | Notes |
|---|---|
| Status | Champion / Challenger / Baseline / Archived |
| Model | Human-readable name |
| Family | XGBoost, Prophet, SARIMA, etc. |
| Grain | store-day, company-day |
| Horizon | 1d, 7d, etc. |
| WAPE | primary ranking metric |
| Δ vs baseline | relative improvement |
| MAE | |
| RMSE | |
| Bias | |
| Coverage | when relevant |
| Run date | |
| Actions | Compare / View |

### Status treatment

Champion:

```text
● Champion
```

Use a small lemon-accent badge.

Baseline:

```text
Baseline
```

Use neutral gray.

Do not use giant colored rows.

## Sorting

Default:

1. selected grain;
2. selected horizon;
3. primary metric ascending.

## Row interaction

Click row → model detail drawer or model detail page.

---

# 13. Screen 3 — Model Detail / Registry

## Purpose

Answer:

> What exactly is this model, how was it produced, and what is its lifecycle status?

## Header

```text
favorita_store_global_xgb_v17

XGBoost · Store/day · Multi-horizon

● Champion        Production
```

Actions:

```text
Compare
View experiments
View forecasts
```

Promotion actions should be disabled/read-only in the public portfolio deployment.

## Summary metrics

- WAPE
- MAE
- Bias
- coverage
- training duration
- last production score

## Tabs

```text
Performance
Metadata
Features
Runs
Artifacts
```

## Metadata

```text
Model version
v17

Training window
2025-01-01 → 2026-06-30

Feature version
features_v12

Data snapshot
favorita_20260701

Git commit
a83f7c1

Artifact
gs://.../model.joblib

MLflow run
...

Vertex experiment
...
```

---

# 14. Screen 4 — Experiment Runs

## Purpose

Answer:

> What experiments have we run, and what changed?

## Table

| Run | Model | Feature set | Horizon | WAPE | Δ | Status | Created |
|---|---|---|---:|---:|---:|---|---|

Filters:

- model family;
- feature version;
- status;
- run date;
- horizon.

### Run labels

Encourage meaningful names:

```text
xgb-promo-lag-ablation-v04
global-vs-local-store
conformal-calibration-v02
```

Avoid exposing UUIDs as primary labels.

---

# 15. Screen 5 — Experiment Comparison

## Purpose

Answer:

> How do selected experiments differ?

Allow 2–5 selected runs.

## Comparison header

```text
Compare experiments

A  XGBoost global v17
B  XGBoost global v16
C  Prophet v08
```

## Sections

### 1. Metrics table

```text
                  A         B         C
WAPE            11.8%     12.6%     14.1%
MAE              142       151       172
Bias            -0.7%     -2.1%     +0.8%
Coverage         81%        —         79%
```

### 2. Performance by horizon

Line chart.

### 3. Performance by segment

Horizontal bar or heatmap.

### 4. Configuration differences

Show only values that changed:

```text
max_depth          8       6
learning_rate     .05     .08
promotion_lag     yes      no
feature_version   v12     v11
```

### 5. Statistical comparison

Optional advanced section:

```text
Δ WAPE vs B
-0.8 pp

95% bootstrap CI
[-1.2, -0.3]

Conclusion
Likely meaningful improvement
```

---

# 16. Screen 6 — Feature Ablations

## Purpose

Answer:

> Which feature groups materially improve performance?

## Primary visualization

Waterfall-style conceptual presentation or ordered bar chart:

```text
Seasonal naive                     21.4%
+ demand lags                      17.5%
+ rolling statistics              15.9%
+ calendar                         15.1%
+ promotions                       12.8%
+ macro                            12.7%
```

## Table

| Experiment | Added feature group | WAPE | Absolute Δ | Relative Δ |
|---|---|---:|---:|---:|

## Insight callout

```text
Largest incremental gain

Promotion features reduced WAPE
by 2.3 percentage points versus
the calendar + lag feature set.
```

This page is particularly important for the portfolio because it demonstrates scientific reasoning rather than model engineering alone.

---

# 17. Screen 7 — Forecast Explorer

## Purpose

Answer:

> What did the model predict for this entity, and what actually happened?

## Control bar

```text
Store 44 ▾
Product family: Beverages ▾
Origin: Jul 1, 2026 ▾
Model: XGBoost v17 ▾
```

## Primary chart

Time series containing:

- actual;
- point forecast / P50;
- P10;
- P90;
- forecast origin;
- promotion overlays;
- holiday overlays.

### Interaction

Hover tooltip:

```text
Jul 8, 2026

Actual        1,482
Forecast      1,531
P10           1,310
P90           1,744

Abs error       49
APE            3.3%

Promotion       Yes
Holiday         No
```

## Summary metrics

- WAPE
- bias
- interval coverage
- max error
- forecast completeness

## Event row

Under the chart, render compact annotations:

```text
Jul 4   Holiday
Jul 6   Promotion starts
Jul 10  Promotion ends
```

---

# 18. Screen 8 — Error Analysis

## Purpose

Answer:

> Where does the model systematically fail?

## Top controls

Slice by:

- product family;
- store;
- demand decile;
- promotion status;
- intermittent class;
- horizon;
- weekday;
- cold-start status.

## Recommended modules

### Error by segment

Horizontal ranking:

```text
Cold start        31.4%
Low volume        24.8%
Promo             17.2%
Non-promo         10.9%
High volume        8.9%
```

### Bias by segment

Highlight systematic over/under forecasting.

### Actual vs predicted

Scatter plot with parity line.

### Error distribution

Histogram / quantiles.

### Worst entity table

| Entity | WAPE | Bias | Volume | Forecasts |
|---|---:|---:|---:|---:|

## Insight panel

Examples:

```text
Primary failure mode
Cold-start series

WAPE is 2.7× portfolio average.
```

or:

```text
Bias alert
Produce forecasts underpredict
promotion weeks by 8.3%.
```

---

# 19. Screen 9 — Explainability

## Purpose

Answer:

> Why did the model make this forecast?

## Global view

### Feature importance

Rank:

- lag_7
- rolling_mean_28
- promotion
- weekday
- holiday
- store_cluster
- macro variable

Allow:

```text
Global | Store | Product family | Horizon
```

## Local explanation

Select an individual prediction.

Example:

```text
Store 44 · Beverages · Jul 8

Base value                     1,103

Promotion                      +210
Lag 7                          +141
Recent trend                    +73
Saturday                        +46
Oil price                        -8
Other                           -34

Forecast                       1,531
```

Use a waterfall chart if practical.

## Important rule

Explainability must always show:

- model version;
- forecast origin;
- entity;
- forecast date.

Never show SHAP attribution without forecast context.

---

# 20. Screen 10 — Monitoring

## Purpose

Answer:

> Is the live forecasting system healthy?

## Sections

### Accuracy

Time-series:
- WAPE 7d;
- WAPE 28d;
- training/backtest WAPE reference.

### Bias

Time-series by production scoring date.

### Calibration

Actual interval coverage versus target.

### Completeness

```text
Expected forecasts      14,240
Produced forecasts      14,197
Completeness             99.7%
```

### Freshness

```text
Latest forecast
2h ago

Expected cadence
Daily

Status
Healthy
```

### Alerts

```text
WARN
D+28 coverage below target
71% vs 80%

WARN
Cold-start WAPE elevated
+31% vs trailing baseline
```

## Monitoring statuses

Use:

- Healthy
- Watch
- Warning
- Critical

Do not overload red. Red should mean a real failed gate.

---

# 21. Component System

Recommended reusable primitives:

## Layout

- `AppShell`
- `Sidebar`
- `TopBar`
- `PageHeader`
- `PageSection`
- `SplitPane`

## Data display

- `MetricStrip`
- `MetricCell`
- `DataTable`
- `StatusBadge`
- `DeltaBadge`
- `MetadataList`
- `EmptyState`
- `InsightCallout`

## Filters

- `FilterBar`
- `FilterChip`
- `DateRangePicker`
- `EntitySelector`
- `HorizonSelector`
- `ModelSelector`

## Charts

- `ForecastTimeSeries`
- `MetricByHorizonChart`
- `SegmentBarChart`
- `ActualVsPredictedScatter`
- `FeatureImportanceChart`
- `ShapWaterfall`
- `CalibrationChart`
- `MetricTrendChart`

## Overlays

- `DetailDrawer`
- `CompareDrawer`
- `Tooltip`
- `CommandMenu` — future

---

# 22. Table Design Rules

Tables are a central part of the application.

Use a Ramp-like approach:

- sticky header;
- sortable columns;
- filterable columns;
- optional column visibility;
- compact rows;
- clear hover state;
- row click for details;
- no heavy vertical borders;
- subtle horizontal separators;
- right-align numeric columns;
- tabular numerals;
- preserve units in headers;
- pin primary identity columns.

### Density

Default row height:
`44px`

Compact option:
`36px`

### Numbers

Good:

```text
11.8%
1,482
-0.7%
```

Avoid:

```text
0.11784293
1482.0000
-0.00693
```

Full precision can be shown in tooltips/details if needed.

---

# 23. Chart Design Rules

Charts should be analytical, not decorative.

## General

- no 3D;
- no gradients;
- minimal gridlines;
- no chart borders;
- short legends;
- direct labels where possible;
- clear units;
- sparse tooltips;
- consistent model color mapping.

## Color

Use theDataStrategist lemon only for a **focus series**.

Recommended semantic mapping:

```text
Champion       lemon / graphite emphasis
Challenger     neutral dark gray
Baseline       light gray
Actual         near-black
Prediction     lemon or dark graphite
Interval       muted neutral fill
Alert          semantic orange/red
```

Do not assign a new bright color to every model.

---

# 24. Interaction Design

## 24.1 Drill-down

Recommended hierarchy:

```text
Overview
  ↓
Leaderboard
  ↓
Model
  ↓
Experiment
  ↓
Forecast slice
  ↓
Individual prediction
  ↓
Explanation
```

Every level should preserve the parent filter context.

---

## 24.2 Compare

Comparison should be a first-class interaction.

Any experiment/model row can:

```text
[ ] Add to compare
```

When 2+ items selected:

```text
Compare 3 experiments
```

opens `/experiments/compare?runs=...`.

---

## 24.3 Deep linking

All meaningful analysis states should be represented in query parameters.

Example:

```text
/forecasts/explorer
?store=44
&family=beverages
&origin=2026-07-01
&model=xgb-v17
&horizon=7
```

This is essential for:

- portfolio sharing;
- debugging;
- reproducibility;
- collaboration.

---

# 25. Responsive Behavior

Primary target:

**1280px+ desktop**

Secondary:
- 1024px laptop
- tablet read-only

Mobile:
- basic view support only;
- not an MVP workflow target.

At narrow widths:

- sidebar becomes drawer;
- metric strip stacks 2 × 2;
- tables retain horizontal scroll;
- charts remain minimum 320px high;
- secondary metadata rail moves below primary content.

---

# 26. Accessibility

Minimum target:
**WCAG AA**

Requirements:

- keyboard-accessible filters;
- visible focus ring;
- no status communicated through color alone;
- accessible chart summaries;
- table headers properly marked;
- semantic buttons;
- 4.5:1 body text contrast;
- tooltips accessible through keyboard focus;
- reduced-motion support.

The lemon brand color should not be used as body text on white without verifying contrast.

---

# 27. React/Vite Technical Architecture

## Recommended stack

```text
React
TypeScript
Vite
React Router
Tailwind CSS
shadcn/ui primitives
TanStack Table
TanStack Query
Apache ECharts for standard analytical charts
D3 only for specialized visualizations
Zod for API contracts / validation
Vitest and React Testing Library
Playwright and axe-core
date-fns
Lucide icons
```

### Why

- Vite provides a small, fast, static-first toolchain for both the GitHub Pages demo and the
  production client.
- React Router keeps URL-addressable filter and drill-down state in the browser application.
- FastAPI remains the only server boundary, avoiding duplicated authorization and lifecycle logic.
- shadcn/ui allows ownership of the component code rather than dependence on a heavy visual framework.
- TanStack Table is appropriate for the dense, filter-heavy experience.
- Apache ECharts supports the dense forecast, interval, calibration, and hierarchy views in this
  workbench.
- Specialized SHAP or calibration visuals can use D3 when required.

---

# 28. React/Vite Project Structure

```text
src/
├── app/
│   ├── App.tsx
│   ├── routes.tsx
│   └── providers.tsx
│
├── pages/
│   ├── overview/
│   ├── models/
│   ├── experiments/
│   ├── forecasts/
│   ├── explainability/
│   └── monitoring/
│
├── components/
│   ├── app-shell/
│   ├── charts/
│   ├── data-table/
│   ├── filters/
│   ├── metrics/
│   └── ui/
│
├── features/
│   ├── models/
│   ├── experiments/
│   ├── forecasts/
│   ├── explainability/
│   └── monitoring/
│
├── lib/
│   ├── api/
│   ├── formatting/
│   ├── filters/
│   └── utils/
│
├── schemas/
├── types/
├── styles/
└── test/
```

---

# 29. Data / API Architecture

Recommended logical architecture:

```text
BigQuery
   │
   ├── model leaderboard marts
   ├── experiment metadata
   ├── forecast outputs
   ├── performance metrics
   ├── SHAP outputs
   └── monitoring marts
   │
   ▼
Forecast API
   │
   ▼
React/Vite
```

The React application should **not** directly construct analytical SQL from browser input.

Prefer:

```text
React/Vite → typed API → governed query/service layer → BigQuery
```

FastAPI is the authoritative service boundary. The browser never calls BigQuery directly, and the
frontend does not add a second backend-for-frontend layer.

---

# 30. Core API Contracts

Suggested endpoints:

```text
GET /api/overview
GET /api/models
GET /api/models/:id
GET /api/experiments
GET /api/experiments/:id
POST /api/experiments/compare
GET /api/ablations
GET /api/forecasts
GET /api/forecasts/:id
GET /api/errors
GET /api/explainability
GET /api/monitoring
```

All analytical endpoints should accept a shared filter object.

Example:

```ts
type ForecastFilters = {
  originStart?: string;
  originEnd?: string;
  horizons?: number[];
  grain?: string;
  target?: string;
  storeIds?: string[];
  productFamilies?: string[];
  modelIds?: string[];
  demandSegments?: string[];
  promotionStatus?: boolean;
};
```

---

# 31. Data Models Needed by the UI

## Model summary

```ts
type ModelSummary = {
  modelId: string;
  displayName: string;
  modelFamily: string;
  grain: string;
  horizons: number[];
  lifecycleStatus: "champion" | "challenger" | "baseline" | "archived";
  wape: number | null;
  mae: number | null;
  rmse: number | null;
  bias: number | null;
  coverage: number | null;
  relativeImprovementVsBaseline: number | null;
  evaluatedAt: string;
};
```

## Experiment

```ts
type ExperimentRun = {
  runId: string;
  runName: string;
  modelId: string;
  modelFamily: string;
  featureVersion: string;
  dataVersion: string;
  gitSha: string;
  trainStart: string;
  trainEnd: string;
  metrics: Record<string, number | null>;
  params: Record<string, unknown>;
  createdAt: string;
};
```

## Forecast row

```ts
type ForecastPoint = {
  entityId: string;
  forecastOrigin: string;
  forecastDate: string;
  horizon: number;
  actual: number | null;
  prediction: number;
  p10?: number | null;
  p50?: number | null;
  p90?: number | null;
  modelId: string;
  promotion?: boolean;
  holiday?: boolean;
};
```

---

# 32. Portfolio / Public Demo Mode

Public deployment should be safe and curated.

## Demo mode

Display badge:

```text
Demo
```

### Read-only

Disable:
- model promotion;
- deletion;
- retraining;
- pipeline runs;
- configuration edits.

### Curated defaults

Default to a dataset slice with:

- meaningful forecast variation;
- promotions;
- uncertainty;
- clear champion/baseline differences;
- at least one interesting failure mode.

### About panel

Include small attribution:

```text
ForecastLab

A production-style forecasting workbench
built on dbt, BigQuery, Vertex AI, MLflow,
Prefect, React, and Vite.

Built by theDataStrategist

View architecture
View GitHub
```

This should be the primary place theDataStrategist is referenced.

---

# 33. Content / Voice

Tone should be:

- direct;
- analytical;
- calm;
- specific;
- non-marketing;
- action-oriented.

Good:

> Coverage fell below the 80% target at D+28.

Bad:

> Unlock unparalleled insight into your model confidence!

Good:

> XGBoost reduced WAPE 18.4% versus seasonal naive.

Bad:

> AI-powered forecasting delivers superior predictive performance.

---

# 34. Loading / Empty / Error States

## Loading

Prefer:
- skeleton table rows;
- lightweight chart skeletons;
- inline loading.

Avoid full-screen spinners.

## Empty

Example:

```text
No experiments match these filters.

Clear filters
```

## Error

Example:

```text
Forecast metrics couldn't be loaded.

The most recent successfully loaded data
is from Jul 24, 2026 at 14:42 UTC.

Retry
```

For production-monitoring surfaces, stale data must be obvious.

---

# 35. MVP Scope

## Phase 1 — Core scientific workbench

Build:

1. App shell
2. Overview
3. Global filters
4. Model leaderboard
5. Model detail
6. Experiment runs
7. Experiment comparison
8. Forecast explorer
9. Error analysis

This is enough for a strong first public demo.

## Phase 2 — Deeper science

Add:

10. Feature ablations
11. Explainability
12. Calibration analysis
13. Global/local analysis
14. Intermittent-demand slices
15. Hierarchy reconciliation comparison

## Phase 3 — Operations

Add:

16. Monitoring
17. Model registry lifecycle
18. Pipeline metadata
19. Cost/runtime metadata
20. Operational alert history

---

# 36. Recommended Build Order

```text
01  Design tokens
02  App shell
03  Shared filter state
04  Data table primitives
05  Chart primitives
06  Overview
07  Leaderboard
08  Model detail
09  Experiment runs
10  Experiment compare
11  Forecast explorer
12  Error analysis
13  Ablations
14  Explainability
15  Monitoring
16  Public demo polish
```

The UI should be built against realistic fixture JSON before the full API is complete.
The public fixture must conform to the
[ForecastLab public demo data contract](frontend/public_demo_data.md).

---

# 37. Acceptance Criteria

The first release is successful when:

### Product

- A new visitor understands the project within 30 seconds.
- A user can identify the current champion in fewer than two clicks.
- A user can compare at least two experiments.
- A user can inspect performance by horizon.
- A user can inspect one forecast against actuals.
- A user can identify the worst-performing segment.
- A user can navigate from model → experiment → forecast.

### Design

- UI is primarily neutral with restrained lemon accents.
- No major screen resembles a generic card-grid dashboard.
- Tables are dense and readable.
- Charts use a consistent semantic visual system.
- theDataStrategist branding is visible but not dominant.
- Product remains visually coherent at 1280–1600px widths.

### Technical

- All filter state is shareable through URLs.
- API contracts are typed.
- No browser-side BigQuery credentials.
- Tables support sorting/filtering.
- Core pages have loading, empty, and error states.
- Public demo is read-only.

---

# 38. Explicit Design Decisions

## Decision: Use Ramp as a UX reference, not a clone

Borrow:

- dense reporting workflows;
- compact sidebar;
- high-quality tables;
- layered filters;
- drill-down behavior;
- restrained visual hierarchy;
- saved/shareable analytical state;
- contextual actions.

Do not copy:
- Ramp logos;
- exact proprietary layouts;
- exact color palette;
- exact components.

## Decision: Limit theDataStrategist branding

Use:
- Space Grotesk;
- graphite;
- lemon accent;
- minimalist tone;
- subtle tDS attribution.

Do not reproduce:
- marketing hero composition;
- large lemon page backgrounds;
- consulting-oriented navigation;
- extensive brand wordmark usage.

## Decision: Make the science the visual centerpiece

The highest-value screens are:

1. Model Leaderboard
2. Experiment Compare
3. Forecast Explorer
4. Error Analysis
5. Feature Ablations

These should receive the most design and engineering attention.

---

# 39. Reference Direction

## Ramp

Useful patterns to study:

- left-sidebar application architecture;
- reporting tables;
- layered filters and filter chips;
- compact metric summaries;
- drill-down from graphs into detail;
- saved/shared analytical views;
- minimal visual ornament.

Public reference:
`https://ramp.com/`

## theDataStrategist

Use the brand system for:
- typography;
- graphite/lemon visual identity;
- pragmatic analytical tone;
- restrained branded moments.

Public reference:
`https://www.thedatastrategist.com/`

Brand guide source:
*TheDataStrategist Brand Guideline (2026)*, supplied as the project brand reference.

---

# 40. Final Product Character

ForecastLab should feel like:

> **Ramp built a forecasting scientist workbench, with theDataStrategist's visual signature applied at 10–15% intensity.**

The strongest visual impression should be:

**clean → scientific → trustworthy → production-ready**

rather than:

**branded → flashy → dashboard-heavy → portfolio demo**

The product should make the underlying forecasting work easier to inspect and defend. The UI is successful when it causes a reviewer to ask about the modeling decisions—not about the frontend.
