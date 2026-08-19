import { Database, FileKey2, Sparkles } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { MetricCard } from "../../components/MetricCard";
import { PageSkeleton, PageState } from "../../components/PageState";
import type { ForecastFilters, ForecastOptions } from "../../types/forecasts";
import { ForecastSeriesChart } from "./ForecastSeriesChart";
import { ProvenanceDrawer } from "./ProvenanceDrawer";
import { useForecastOptions, useForecasts } from "./useForecasts";

const parseHorizon = (value: string | null) => {
  if (!value || value === "all") return null;
  const horizon = Number(value);
  return Number.isInteger(horizon) && horizon >= 1 && horizon <= 7
    ? horizon
    : null;
};

const makeFilters = (
  params: URLSearchParams,
  options: ForecastOptions,
): ForecastFilters => {
  const requestedRun = params.get("run");
  const requestedEntity = params.get("entity");
  const requestedModel = params.get("model");
  return {
    runId:
      options.runs.find(({ id }) => id === requestedRun)?.id ??
      options.runs[0]?.id ??
      "",
    entityId:
      options.entities.find(({ id }) => id === requestedEntity)?.id ??
      options.entities[0]?.id ??
      "",
    horizon: parseHorizon(params.get("horizon")),
    modelId:
      options.models.find(({ id }) => id === requestedModel)?.id ??
      options.models[0]?.id ??
      "",
    exceptionState:
      params.get("exception") === "watch" ||
      params.get("exception") === "blocked"
        ? (params.get("exception") as "watch" | "blocked")
        : params.get("exception") === "clear"
          ? "clear"
          : "all",
  };
};

export const ForecastExplorerPage = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [showProvenance, setShowProvenance] = useState(false);
  const optionsQuery = useForecastOptions(searchParams.get("run") ?? undefined);
  const filters = optionsQuery.data
    ? makeFilters(searchParams, optionsQuery.data)
    : null;
  const forecastsQuery = useForecasts(filters);

  const updateFilter = (key: string, value: string) => {
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.set(key, value);
        return next;
      },
      { replace: true },
    );
  };

  if (optionsQuery.isLoading || forecastsQuery.isLoading)
    return <PageSkeleton />;
  if (optionsQuery.isError || forecastsQuery.isError) {
    const error = optionsQuery.error ?? forecastsQuery.error;
    return (
      <div className="page">
        <PageState
          title="Forecast evidence is unavailable"
          message={
            error instanceof Error
              ? error.message
              : "Forecasts could not be loaded."
          }
        />
      </div>
    );
  }

  const options = optionsQuery.data;
  const result = forecastsQuery.data;
  if (!options || !filters || !result) return <PageSkeleton />;

  const adjustedRows = result.rows.filter(
    ({ statisticalForecast, publishedForecast }) =>
      statisticalForecast !== publishedForecast,
  );
  const exceptions = result.rows.filter(
    ({ exceptionState }) => exceptionState !== "clear",
  );

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Canonical forecast output</p>
          <h1>Forecast Explorer</h1>
          <p className="page-description">
            Inspect actuals, probabilistic forecasts, published adjustments, and
            the complete provenance chain behind each governed run.
          </p>
        </div>
        <span className="demo-pill">
          <Sparkles size={12} aria-hidden="true" />
          {result.datasetKind === "live"
            ? "Live warehouse"
            : "Synthetic fixture"}
        </span>
      </header>

      <section
        className="filters forecast-filters"
        aria-label="Forecast filters"
      >
        <div className="filter-field">
          <label htmlFor="run-filter">Forecast run</label>
          <select
            id="run-filter"
            value={filters.runId}
            onChange={(e) => updateFilter("run", e.target.value)}
          >
            {options.runs.map((run) => (
              <option key={run.id} value={run.id}>
                {run.label}
              </option>
            ))}
          </select>
        </div>
        <div className="filter-field">
          <label htmlFor="entity-filter">Hierarchy entity</label>
          <select
            id="entity-filter"
            value={filters.entityId}
            onChange={(e) => updateFilter("entity", e.target.value)}
          >
            {options.entities.map((entity) => (
              <option key={entity.id} value={entity.id}>
                {entity.name}
              </option>
            ))}
          </select>
        </div>
        <div className="filter-field">
          <label htmlFor="horizon-filter">Horizon</label>
          <select
            id="horizon-filter"
            value={filters.horizon ?? "all"}
            onChange={(e) => updateFilter("horizon", e.target.value)}
          >
            <option value="all">All horizons</option>
            {options.horizons.map((horizon) => (
              <option key={horizon} value={horizon}>
                Day {horizon}
              </option>
            ))}
          </select>
        </div>
        <div className="filter-field">
          <label htmlFor="model-filter">Strategy / model</label>
          <select
            id="model-filter"
            value={filters.modelId}
            onChange={(e) => updateFilter("model", e.target.value)}
          >
            {options.models.map((model) => (
              <option key={model.id} value={model.id}>
                {model.name}
              </option>
            ))}
          </select>
        </div>
        <div className="filter-field">
          <label htmlFor="exception-filter">Exception state</label>
          <select
            id="exception-filter"
            value={filters.exceptionState}
            onChange={(e) => updateFilter("exception", e.target.value)}
          >
            <option value="all">All states</option>
            {options.exceptionStates.map((state) => (
              <option key={state} value={state}>
                {state}
              </option>
            ))}
          </select>
        </div>
        <span className="environment-label">
          <Database size={13} aria-hidden="true" />
          {result.fixtureVersion ?? "production API"}
        </span>
      </section>

      <section className="metric-grid" aria-label="Forecast summary">
        <MetricCard
          label="Forecast origin"
          value={result.run.origin}
          context={result.run.publicationStatus}
        />
        <MetricCard
          label="Hierarchy node"
          value={result.entity.name}
          context={`${result.entity.hierarchyLevel}: ${result.entity.hierarchyNode}`}
        />
        <MetricCard
          label="Visible forecasts"
          value={String(result.rows.length)}
          context={
            filters.horizon ? `Day ${filters.horizon}` : "Seven-day contract"
          }
        />
        <MetricCard
          label="Exceptions / adjustments"
          value={`${exceptions.length} / ${adjustedRows.length}`}
          context="Visible governed evidence"
        />
      </section>

      {result.rows.length === 0 ? (
        <PageState
          title="No matching forecasts"
          message="No canonical rows match the selected run, entity, model, horizon, and exception state."
        />
      ) : (
        <section className="forecast-layout">
          <div className="panel">
            <div className="panel-header">
              <div>
                <h2>Actuals and forecast interval</h2>
                <p className="panel-subtitle">
                  P10–P90 interval with statistical and published values
                </p>
              </div>
              <button
                className="secondary-button"
                type="button"
                onClick={() => setShowProvenance(true)}
              >
                <FileKey2 size={15} aria-hidden="true" /> View provenance
              </button>
            </div>
            <ForecastSeriesChart rows={result.rows} />
            <div className="table-scroll">
              <table className="data-table forecast-table">
                <caption className="visually-hidden">
                  Canonical forecast values by target date
                </caption>
                <thead>
                  <tr>
                    <th>Target</th>
                    <th>Horizon</th>
                    <th>Actual</th>
                    <th>P10</th>
                    <th>P50</th>
                    <th>P90</th>
                    <th>Published</th>
                    <th>State</th>
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((row) => (
                    <tr key={`${row.runId}-${row.entityId}-${row.targetDate}`}>
                      <td>{row.targetDate}</td>
                      <td>D+{row.horizon}</td>
                      <td>{row.actual ?? "—"}</td>
                      <td>{row.p10}</td>
                      <td>{row.p50}</td>
                      <td>{row.p90}</td>
                      <td>{row.publishedForecast}</td>
                      <td>
                        <span
                          className={`exception-badge ${row.exceptionState}`}
                        >
                          {row.exceptionState}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          {showProvenance && (
            <ProvenanceDrawer
              provenance={result.provenance}
              onClose={() => setShowProvenance(false)}
            />
          )}
        </section>
      )}
    </div>
  );
};
