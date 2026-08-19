import {
  ArrowLeft,
  CheckCircle2,
  FlaskConical,
  Plus,
  Sparkles,
  TriangleAlert,
  X,
} from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { PageSkeleton, PageState } from "../../components/PageState";
import type { ExperimentMetric, ExperimentRun } from "../../types/experiments";
import {
  ExperimentHorizonChart,
  RollingOriginChart,
} from "./ExperimentComparisonCharts";
import {
  useExperimentComparison,
  useExperimentOptions,
} from "./useExperiments";

const parseRuns = (value: string | null) =>
  value ? [...new Set(value.split(",").filter(Boolean))].slice(0, 5) : [];

const parseMetric = (value: string | null): ExperimentMetric =>
  value === "bias" || value === "coverage" ? value : "wape";

const displayConfigurationValue = (
  value: string | number | boolean | undefined,
) => {
  if (value === undefined) return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
};

const getChangedConfiguration = (runs: ExperimentRun[]) => {
  const keys = [
    ...new Set(runs.flatMap((run) => Object.keys(run.configuration))),
  ].sort();
  return keys.filter(
    (key) =>
      new Set(runs.map((run) => JSON.stringify(run.configuration[key]))).size >
      1,
  );
};

export const ExperimentComparisonPage = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const runIds = parseRuns(searchParams.get("runs"));
  const metric = parseMetric(searchParams.get("metric"));
  const comparisonQuery = useExperimentComparison(runIds);
  const optionsQuery = useExperimentOptions();

  const setComparisonState = (nextRunIds: string[], nextMetric = metric) => {
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (nextRunIds.length > 0) next.set("runs", nextRunIds.join(","));
        else next.delete("runs");
        next.set("metric", nextMetric);
        return next;
      },
      { replace: true },
    );
  };

  if (comparisonQuery.isLoading || optionsQuery.isLoading)
    return <PageSkeleton />;
  if (comparisonQuery.isError || optionsQuery.isError) {
    const error = comparisonQuery.error ?? optionsQuery.error;
    return (
      <div className="page">
        <PageState
          title="Comparison evidence is unavailable"
          message={
            error instanceof Error
              ? error.message
              : "The selected runs could not be loaded."
          }
        />
      </div>
    );
  }

  const result = comparisonQuery.data;
  const options = optionsQuery.data;
  const runs = result?.runs ?? [];
  const addableRuns = (options?.runs ?? []).filter(
    ({ id, comparable }) => comparable && !runIds.includes(id),
  );
  const changedConfiguration = getChangedConfiguration(runs);
  const segmentNames = [
    ...new Set(
      runs.flatMap((run) => run.segments.map(({ segmentName }) => segmentName)),
    ),
  ];

  return (
    <div className="page">
      <Link
        className="back-link"
        to={`/experiments?runs=${encodeURIComponent(runIds.join(","))}`}
      >
        <ArrowLeft size={14} aria-hidden="true" /> Back to experiment runs
      </Link>

      <header className="page-header">
        <div>
          <p className="eyebrow">Scientific evaluation</p>
          <h1>Compare Experiments</h1>
          <p className="page-description">
            Compare identical rolling-origin evidence across metrics, horizons,
            segments, runtime, configuration, and uncertainty.
          </p>
        </div>
        <span className="demo-pill">
          <Sparkles size={12} aria-hidden="true" /> Synthetic fixture
        </span>
      </header>

      {result && result.missingRunIds.length > 0 && (
        <div className="inline-alert" role="status">
          <TriangleAlert size={16} aria-hidden="true" />
          {result.missingRunIds.length} selected run
          {result.missingRunIds.length === 1 ? " is" : "s are"} unavailable or
          lack comparable evidence.
        </div>
      )}

      <section
        className="comparison-selection"
        aria-label="Selected experiments"
      >
        <div className="run-chip-list">
          {runs.map((run, index) => (
            <div className="run-chip" key={run.id}>
              <span className="comparison-key" aria-hidden="true">
                {String.fromCharCode(65 + index)}
              </span>
              <span>
                <strong>{run.label}</strong>
                <small>{run.modelName}</small>
              </span>
              <button
                className="chip-remove"
                type="button"
                aria-label={`Remove ${run.label} from comparison`}
                onClick={() =>
                  setComparisonState(runIds.filter((id) => id !== run.id))
                }
              >
                <X size={13} aria-hidden="true" />
              </button>
            </div>
          ))}
        </div>
        {runs.length < 5 && addableRuns.length > 0 && (
          <label className="add-run-control">
            <span className="visually-hidden">Add experiment</span>
            <Plus size={14} aria-hidden="true" />
            <select
              aria-label="Add experiment"
              value=""
              onChange={(event) => {
                if (event.target.value)
                  setComparisonState([...runIds, event.target.value]);
              }}
            >
              <option value="">Add run…</option>
              {addableRuns.map((run) => (
                <option key={run.id} value={run.id}>
                  {run.label}
                </option>
              ))}
            </select>
          </label>
        )}
      </section>

      {runs.length < 2 ? (
        <PageState
          title="Select at least two completed experiments"
          message="Return to run history or use Add run to create a scientific comparison."
        />
      ) : (
        <>
          <section className="panel comparison-section">
            <div className="panel-header">
              <div>
                <h2>Summary metrics</h2>
                <p className="panel-subtitle">
                  Comparable aggregate evidence and execution cost
                </p>
              </div>
              <span className="environment-label">
                <FlaskConical size={13} aria-hidden="true" />{" "}
                {result?.datasetKind === "live"
                  ? "Live warehouse evidence"
                  : result?.fixtureVersion}
              </span>
            </div>
            <div className="table-scroll">
              <table className="data-table comparison-table">
                <caption className="visually-hidden">
                  Experiment summary metric comparison
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Metric</th>
                    {runs.map((run) => (
                      <th scope="col" key={run.id}>
                        {run.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <th scope="row">WAPE</th>
                    {runs.map((run) => (
                      <td key={run.id}>{run.summary?.wape.toFixed(1)}%</td>
                    ))}
                  </tr>
                  <tr>
                    <th scope="row">Bias</th>
                    {runs.map((run) => (
                      <td key={run.id}>{run.summary?.bias.toFixed(1)}%</td>
                    ))}
                  </tr>
                  <tr>
                    <th scope="row">Coverage</th>
                    {runs.map((run) => (
                      <td key={run.id}>
                        {((run.summary?.coverage ?? 0) * 100).toFixed(0)}%
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <th scope="row">Runtime</th>
                    {runs.map((run) => (
                      <td key={run.id}>{run.runtimeMinutes.toFixed(1)} min</td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel comparison-section">
            <div className="panel-header">
              <div>
                <h2>Performance by horizon</h2>
                <p className="panel-subtitle">
                  Identical population and forecast origins
                </p>
              </div>
              <div className="filter-field compact-filter">
                <label htmlFor="comparison-metric">Metric</label>
                <select
                  id="comparison-metric"
                  value={metric}
                  onChange={(event) =>
                    setComparisonState(runIds, parseMetric(event.target.value))
                  }
                >
                  <option value="wape">WAPE</option>
                  <option value="bias">Bias</option>
                  <option value="coverage">Coverage</option>
                </select>
              </div>
            </div>
            <ExperimentHorizonChart runs={runs} metric={metric} />
          </section>

          <section className="panel comparison-section">
            <div className="panel-header">
              <div>
                <h2>Performance by segment</h2>
                <p className="panel-subtitle">
                  WAPE, bias, and interval coverage by demand slice
                </p>
              </div>
            </div>
            <div className="table-scroll">
              <table className="data-table comparison-table segment-comparison-table">
                <caption className="visually-hidden">
                  Experiment performance by segment
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Segment</th>
                    {runs.map((run) => (
                      <th scope="col" key={run.id}>
                        {run.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {segmentNames.map((segmentName) => (
                    <tr key={segmentName}>
                      <th scope="row">{segmentName}</th>
                      {runs.map((run) => {
                        const segment = run.segments.find(
                          (row) => row.segmentName === segmentName,
                        );
                        return (
                          <td key={run.id}>
                            {segment ? (
                              <span className="segment-metrics">
                                <strong>{segment.wape.toFixed(1)}% WAPE</strong>
                                <span>{segment.bias.toFixed(1)}% bias</span>
                                <span>
                                  {(segment.coverage * 100).toFixed(0)}%
                                  coverage
                                </span>
                              </span>
                            ) : (
                              "—"
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel comparison-section">
            <div className="panel-header">
              <div>
                <h2>Configuration differences</h2>
                <p className="panel-subtitle">
                  Only parameters that changed are shown
                </p>
              </div>
            </div>
            <div className="table-scroll">
              <table className="data-table comparison-table configuration-table">
                <caption className="visually-hidden">
                  Changed experiment configuration
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Parameter</th>
                    {runs.map((run) => (
                      <th scope="col" key={run.id}>
                        {run.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {changedConfiguration.map((key) => (
                    <tr key={key}>
                      <th scope="row">{key.replaceAll("_", " ")}</th>
                      {runs.map((run) => (
                        <td key={run.id}>
                          {displayConfigurationValue(run.configuration[key])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="comparison-evidence-grid">
            <div className="panel comparison-section">
              <div className="panel-header">
                <div>
                  <h2>Rolling-origin evidence</h2>
                  <p className="panel-subtitle">
                    Five weekly origins using the same population
                  </p>
                </div>
              </div>
              <RollingOriginChart runs={runs} />
            </div>
            <div className="panel comparison-section">
              <div className="panel-header">
                <div>
                  <h2>Confidence and significance</h2>
                  <p className="panel-subtitle">Bootstrap difference in WAPE</p>
                </div>
              </div>
              <div className="confidence-list">
                {runs.map((run) => (
                  <article key={run.id} className="confidence-card">
                    <div>
                      <strong>{run.label}</strong>
                      <span>
                        {run.statisticalEvidence
                          ? `vs ${
                              runs.find(
                                ({ id }) =>
                                  id ===
                                  run.statisticalEvidence?.referenceRunId,
                              )?.label ??
                              run.statisticalEvidence.referenceRunId.replace(
                                "demo_experiment_",
                                "",
                              )
                            }`
                          : "configured reference"}
                      </span>
                    </div>
                    {run.statisticalEvidence ? (
                      <>
                        <span
                          className={`significance-badge ${run.statisticalEvidence.conclusion}`}
                        >
                          {run.statisticalEvidence.conclusion ===
                          "meaningful" ? (
                            <CheckCircle2 size={13} aria-hidden="true" />
                          ) : (
                            <TriangleAlert size={13} aria-hidden="true" />
                          )}
                          {run.statisticalEvidence.conclusion}
                        </span>
                        <dl>
                          <dt>Δ WAPE</dt>
                          <dd>
                            {run.statisticalEvidence.deltaWapePp.toFixed(1)} pp
                          </dd>
                          <dt>
                            {(
                              run.statisticalEvidence.confidenceLevel * 100
                            ).toFixed(0)}
                            % bootstrap CI
                          </dt>
                          <dd>
                            [{run.statisticalEvidence.ciLower.toFixed(1)},{" "}
                            {run.statisticalEvidence.ciUpper.toFixed(1)}]
                          </dd>
                          <dt>p-value</dt>
                          <dd>{run.statisticalEvidence.pValue.toFixed(3)}</dd>
                        </dl>
                      </>
                    ) : (
                      <p className="confidence-reference">
                        Reference run; no self-comparison.
                      </p>
                    )}
                  </article>
                ))}
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
};
