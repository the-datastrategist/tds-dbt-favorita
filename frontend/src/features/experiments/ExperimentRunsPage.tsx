import { FlaskConical, GitCompareArrows, Sparkles } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { PageSkeleton, PageState } from "../../components/PageState";
import type { ExperimentFilters } from "../../types/experiments";
import { ExperimentRunsTable } from "./ExperimentRunsTable";
import { useExperimentOptions, useExperiments } from "./useExperiments";

const parseHorizon = (value: string | null) => {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 1 && parsed <= 7 ? parsed : null;
};

const parseSelectedRuns = (value: string | null) =>
  value ? [...new Set(value.split(",").filter(Boolean))].slice(0, 5) : [];

export const ExperimentRunsPage = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const optionsQuery = useExperimentOptions();
  const filters: ExperimentFilters = {
    modelId: searchParams.get("model") ?? "",
    modelFamily: searchParams.get("family") ?? "",
    featureVersion: searchParams.get("feature") ?? "",
    status:
      searchParams.get("status") === "completed" ||
      searchParams.get("status") === "failed"
        ? (searchParams.get("status") as "completed" | "failed")
        : "all",
    horizon: parseHorizon(searchParams.get("horizon")),
  };
  const selectedRunIds = parseSelectedRuns(searchParams.get("runs"));
  const experimentsQuery = useExperiments(filters);

  const setParameter = (key: string, value: string) => {
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (value) next.set(key, value);
        else next.delete(key);
        return next;
      },
      { replace: true },
    );
  };

  const toggleRun = (runId: string) => {
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current);
        const currentRunIds = parseSelectedRuns(current.get("runs"));
        const updatedRunIds = currentRunIds.includes(runId)
          ? currentRunIds.filter((id) => id !== runId)
          : [...currentRunIds, runId].slice(0, 5);
        if (updatedRunIds.length > 0) next.set("runs", updatedRunIds.join(","));
        else next.delete("runs");
        return next;
      },
      { replace: true },
    );
  };

  if (optionsQuery.isLoading || experimentsQuery.isLoading) {
    return <PageSkeleton />;
  }
  if (optionsQuery.isError || experimentsQuery.isError) {
    const error = optionsQuery.error ?? experimentsQuery.error;
    return (
      <div className="page">
        <PageState
          title="Experiment evidence is unavailable"
          message={
            error instanceof Error
              ? error.message
              : "Run history could not be loaded."
          }
        />
      </div>
    );
  }

  const options = optionsQuery.data;
  const result = experimentsQuery.data;
  if (!options || !result) return <PageSkeleton />;
  const compareQuery = new URLSearchParams({ runs: selectedRunIds.join(",") });

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Scientific evaluation</p>
          <h1>Experiment Runs</h1>
          <p className="page-description">
            Review what changed, select comparable runs, and trace successful
            experiments into published forecast evidence.
          </p>
        </div>
        <span className="demo-pill">
          <Sparkles size={12} aria-hidden="true" />{" "}
          {result.datasetKind === "live"
            ? "Live warehouse evidence"
            : "Synthetic fixture"}
        </span>
      </header>

      <section
        className="filters experiment-filters"
        aria-label="Experiment filters"
      >
        <div className="filter-field">
          <label htmlFor="experiment-model-filter">Model</label>
          <select
            id="experiment-model-filter"
            value={filters.modelId}
            onChange={(event) => setParameter("model", event.target.value)}
          >
            <option value="">All models</option>
            {options.models.map((model) => (
              <option key={model.id} value={model.id}>
                {model.name}
              </option>
            ))}
          </select>
        </div>
        <div className="filter-field">
          <label htmlFor="experiment-family-filter">Model family</label>
          <select
            id="experiment-family-filter"
            value={filters.modelFamily}
            onChange={(event) => setParameter("family", event.target.value)}
          >
            <option value="">All families</option>
            {options.modelFamilies.map((family) => (
              <option key={family} value={family}>
                {family}
              </option>
            ))}
          </select>
        </div>
        <div className="filter-field">
          <label htmlFor="experiment-feature-filter">Feature version</label>
          <select
            id="experiment-feature-filter"
            value={filters.featureVersion}
            onChange={(event) => setParameter("feature", event.target.value)}
          >
            <option value="">All feature sets</option>
            {options.featureVersions.map((version) => (
              <option key={version} value={version}>
                {version}
              </option>
            ))}
          </select>
        </div>
        <div className="filter-field">
          <label htmlFor="experiment-status-filter">Status</label>
          <select
            id="experiment-status-filter"
            value={filters.status}
            onChange={(event) => setParameter("status", event.target.value)}
          >
            <option value="all">All statuses</option>
            {options.statuses.map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </select>
        </div>
        <div className="filter-field">
          <label htmlFor="experiment-horizon-filter">Horizon evidence</label>
          <select
            id="experiment-horizon-filter"
            value={filters.horizon ?? ""}
            onChange={(event) => setParameter("horizon", event.target.value)}
          >
            <option value="">All horizons</option>
            {options.horizons.map((horizon) => (
              <option key={horizon} value={horizon}>
                Day {horizon}
              </option>
            ))}
          </select>
        </div>
        <span className="environment-label">
          <FlaskConical size={13} aria-hidden="true" />{" "}
          {result.datasetKind === "live"
            ? "Live warehouse evidence"
            : result.fixtureVersion}
        </span>
      </section>

      <section className="selection-bar" aria-live="polite">
        <div>
          <strong>{selectedRunIds.length} selected</strong>
          <span>Select 2–5 completed runs for a defensible comparison.</span>
        </div>
        {selectedRunIds.length >= 2 ? (
          <Link
            className="primary-button"
            to={`/experiments/compare?${compareQuery}`}
          >
            <GitCompareArrows size={15} aria-hidden="true" /> Compare
            experiments
          </Link>
        ) : (
          <span className="primary-button disabled" aria-disabled="true">
            <GitCompareArrows size={15} aria-hidden="true" /> Compare
            experiments
          </span>
        )}
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>Run history</h2>
            <p className="panel-subtitle">
              {result.runs.length} matching run
              {result.runs.length === 1 ? "" : "s"}
            </p>
          </div>
        </div>
        {result.runs.length > 0 ? (
          <ExperimentRunsTable
            runs={result.runs}
            selectedRunIds={selectedRunIds}
            onToggleRun={toggleRun}
          />
        ) : (
          <PageState
            title="No experiments match these filters"
            message="Adjust the model, feature, status, or horizon filters to restore run history."
          />
        )}
      </section>
    </div>
  );
};
