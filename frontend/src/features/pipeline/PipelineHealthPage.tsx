import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, CircleX, Clock3, Workflow } from "lucide-react";
import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { PageSkeleton, PageState } from "../../components/PageState";
import { platformDataSource } from "../../data/platformDataSource";

const seconds = (value: number | null) =>
  value === null
    ? "Running"
    : value < 60
      ? `${value.toFixed(0)}s`
      : `${(value / 60).toFixed(1)}m`;

export const PipelineHealthPage = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const query = useQuery({
    queryKey: ["pipeline-runs"],
    queryFn: () => platformDataSource.pipelineRuns(),
  });
  const requestedRun = searchParams.get("run") ?? "";
  const run =
    query.data?.runs.find(({ runId }) => runId === requestedRun) ??
    query.data?.runs[0];

  useEffect(() => {
    if (!run || requestedRun === run.runId) return;
    setSearchParams({ run: run.runId }, { replace: true });
  }, [requestedRun, run, setSearchParams]);

  if (query.isLoading) return <PageSkeleton />;
  if (query.isError)
    return (
      <div className="page">
        <PageState
          title="Pipeline evidence is unavailable"
          message={
            query.error instanceof Error
              ? query.error.message
              : "Scheduled-run evidence could not be loaded."
          }
        />
      </div>
    );
  if (!run)
    return (
      <div className="page">
        <PageState
          title="No scheduled runs"
          message="Execute the publication pipeline to populate stage and gate evidence."
        />
      </div>
    );

  const blockingFailures = run.gates.filter(
    (gate) => gate.severity === "blocking" && !gate.passed,
  ).length;
  const duration = run.finishedAt
    ? (new Date(run.finishedAt).getTime() - new Date(run.startedAt).getTime()) /
      1000
    : null;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Scheduled publication</p>
          <h1>Pipeline Health</h1>
          <p className="page-description">
            Inspect ordered stages, retry-safe execution, blocking gates,
            cardinality, horizons, and quantile completeness.
          </p>
        </div>
        <span className="demo-pill">
          <Workflow size={12} aria-hidden="true" />{" "}
          {query.data?.datasetKind === "live"
            ? "Live pipeline"
            : "Synthetic fixture"}
        </span>
      </header>

      <section className="filter-bar" aria-label="Pipeline filters">
        <div className="filter-field wide-filter">
          <label htmlFor="pipeline-run">Pipeline run</label>
          <select
            id="pipeline-run"
            value={run.runId}
            onChange={(event) =>
              setSearchParams({ run: event.target.value }, { replace: true })
            }
          >
            {query.data?.runs.map((item) => (
              <option key={item.runId} value={item.runId}>
                {item.origin} · {item.contractName} · {item.healthStatus}
              </option>
            ))}
          </select>
        </div>
      </section>

      <section className="metric-grid" aria-label="Pipeline summary">
        <article className="metric-card">
          <span>Health</span>
          <strong>{run.healthStatus}</strong>
          <small>{run.status} lifecycle state</small>
        </article>
        <article className="metric-card">
          <span>Duration</span>
          <strong>{seconds(duration)}</strong>
          <small>{run.stages.length} ordered stages</small>
        </article>
        <article className="metric-card">
          <span>Cardinality</span>
          <strong>
            {run.outputCount}/{run.eligibleCount ?? "—"}
          </strong>
          <small>
            {run.candidateCount === null
              ? "Candidate count unavailable"
              : `${run.candidateCount} candidates`}
          </small>
        </article>
        <article className="metric-card">
          <span>Blocking gates</span>
          <strong>{blockingFailures}</strong>
          <small>
            {run.horizonCount} horizons · {run.missingQuantileCount} missing
            quantiles
          </small>
        </article>
      </section>

      <section className="panel comparison-section">
        <div className="panel-header">
          <div>
            <h2>Stage execution</h2>
            <p className="panel-subtitle">
              Persisted component order and row-count envelopes
            </p>
          </div>
          <Clock3 size={18} aria-hidden="true" />
        </div>
        <div className="stage-timeline">
          {run.stages.map((stage) => (
            <article
              className={`stage-card ${stage.status}`}
              key={`${stage.position}-${stage.name}`}
            >
              <span className="stage-position">{stage.position}</span>
              <div>
                <strong>{stage.name}</strong>
                <small>
                  {stage.inputRows} → {stage.outputRows} rows ·{" "}
                  {stage.retryState}
                </small>
                {stage.errorMessage && <p role="alert">{stage.errorMessage}</p>}
              </div>
              <span>{seconds(stage.durationSeconds)}</span>
            </article>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>Validation gates</h2>
            <p className="panel-subtitle">
              Failed blocking checks prevent draft visibility and publication
            </p>
          </div>
        </div>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Gate</th>
                <th>Severity</th>
                <th>Observed</th>
                <th>Threshold</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              {run.gates.map((gate) => (
                <tr key={gate.name}>
                  <th scope="row">{gate.name}</th>
                  <td>{gate.severity}</td>
                  <td>{gate.observedValue ?? "—"}</td>
                  <td>{gate.thresholdValue ?? "—"}</td>
                  <td>
                    <span
                      className={`gate-result ${gate.passed ? "passed" : "failed"}`}
                    >
                      {gate.passed ? (
                        <CheckCircle2 size={14} />
                      ) : (
                        <CircleX size={14} />
                      )}
                      {gate.passed ? "Passed" : "Failed"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
};
