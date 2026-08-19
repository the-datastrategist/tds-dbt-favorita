import {
  Activity,
  ArrowDownRight,
  FlaskConical,
  TriangleAlert,
} from "lucide-react";
import { useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { PageSkeleton, PageState } from "../../components/PageState";
import {
  useExperimentOptions,
  useExperiments,
} from "../experiments/useExperiments";

const asHorizon = (value: string | null) => {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
};

export const AccuracyPage = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const optionsQuery = useExperimentOptions();
  const runsQuery = useExperiments({
    modelId: "",
    modelFamily: "",
    featureVersion: "",
    status: "completed",
    horizon: null,
  });
  const requestedRun = searchParams.get("run") ?? "";
  const requestedHorizon = asHorizon(searchParams.get("horizon"));
  const runs = runsQuery.data?.runs ?? [];
  const run = runs.find(({ id }) => id === requestedRun) ?? runs[0];
  const horizons = run?.horizons ?? [];
  const horizon =
    horizons.find((row) => row.horizon === requestedHorizon) ?? horizons[0];

  useEffect(() => {
    if (!run || !horizon) return;
    if (requestedRun === run.id && requestedHorizon === horizon.horizon) return;
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.set("run", run.id);
        next.set("horizon", String(horizon.horizon));
        return next;
      },
      { replace: true },
    );
  }, [horizon, requestedHorizon, requestedRun, run, setSearchParams]);

  if (optionsQuery.isLoading || runsQuery.isLoading) return <PageSkeleton />;
  if (optionsQuery.isError || runsQuery.isError) {
    const error = optionsQuery.error ?? runsQuery.error;
    return (
      <div className="page">
        <PageState
          title="Accuracy evidence is unavailable"
          message={
            error instanceof Error
              ? error.message
              : "Backtest evidence could not be loaded."
          }
        />
      </div>
    );
  }
  if (!run || !horizon) {
    return (
      <div className="page">
        <PageState
          title="No completed backtests"
          message="Run a rolling-origin evaluation before opening error analysis."
        />
      </div>
    );
  }

  const firstHorizon = horizons[0];
  const degradation = firstHorizon ? horizon.wape - firstHorizon.wape : 0;
  const worstSegments = [...run.segments].sort((a, b) => b.wape - a.wape);
  const originWapes = run.rollingOrigins.map(({ wape }) => wape);
  const originRange = originWapes.length
    ? Math.max(...originWapes) - Math.min(...originWapes)
    : 0;
  const setParam = (name: string, value: string) =>
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.set(name, value);
        return next;
      },
      { replace: true },
    );

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Accuracy and backtesting</p>
          <h1>Error Analysis</h1>
          <p className="page-description">
            Diagnose horizon degradation, unstable origins, weak segments, bias,
            and interval calibration from immutable rolling-origin evidence.
          </p>
        </div>
        <span className="demo-pill">
          <FlaskConical size={12} aria-hidden="true" />{" "}
          {runsQuery.data?.datasetKind === "live"
            ? "Live evidence"
            : "Synthetic fixture"}
        </span>
      </header>

      <section className="filter-bar" aria-label="Error analysis filters">
        <div className="filter-field wide-filter">
          <label htmlFor="accuracy-run">Experiment run</label>
          <select
            id="accuracy-run"
            value={run.id}
            onChange={(event) => setParam("run", event.target.value)}
          >
            {runs.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </div>
        <div className="filter-field">
          <label htmlFor="accuracy-horizon">Horizon</label>
          <select
            id="accuracy-horizon"
            value={horizon.horizon}
            onChange={(event) => setParam("horizon", event.target.value)}
          >
            {horizons.map((item) => (
              <option key={item.horizon} value={item.horizon}>
                Day {item.horizon}
              </option>
            ))}
          </select>
        </div>
        <Link
          className="secondary-button"
          to={`/experiments/compare?runs=${encodeURIComponent(run.id)}`}
        >
          Compare run
        </Link>
      </section>

      <section className="metric-grid" aria-label="Selected accuracy summary">
        <article className="metric-card">
          <span>WAPE</span>
          <strong>{horizon.wape.toFixed(1)}%</strong>
          <small>day {horizon.horizon}</small>
        </article>
        <article className="metric-card">
          <span>Bias</span>
          <strong>{horizon.bias.toFixed(1)}%</strong>
          <small>
            {Math.abs(horizon.bias) < 1
              ? "near neutral"
              : "investigate direction"}
          </small>
        </article>
        <article className="metric-card">
          <span>Interval coverage</span>
          <strong>{(horizon.coverage * 100).toFixed(0)}%</strong>
          <small>P10–P90 realized coverage</small>
        </article>
        <article className="metric-card">
          <span>Horizon degradation</span>
          <strong>
            {degradation >= 0 ? "+" : ""}
            {degradation.toFixed(1)} pp
          </strong>
          <small>versus day {firstHorizon?.horizon}</small>
        </article>
      </section>

      <section className="analysis-grid">
        <article className="panel comparison-section">
          <div className="panel-header">
            <div>
              <h2>Horizon degradation</h2>
              <p className="panel-subtitle">
                WAPE and calibration across the forecast window
              </p>
            </div>
            <ArrowDownRight size={18} aria-hidden="true" />
          </div>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">Horizon</th>
                  <th scope="col">WAPE</th>
                  <th scope="col">Bias</th>
                  <th scope="col">Coverage</th>
                </tr>
              </thead>
              <tbody>
                {horizons.map((item) => (
                  <tr
                    key={item.horizon}
                    className={
                      item.horizon === horizon.horizon ? "selected-row" : ""
                    }
                  >
                    <th scope="row">
                      <button
                        className="table-link-button"
                        type="button"
                        onClick={() =>
                          setParam("horizon", String(item.horizon))
                        }
                      >
                        Day {item.horizon}
                      </button>
                    </th>
                    <td>{item.wape.toFixed(1)}%</td>
                    <td>{item.bias.toFixed(1)}%</td>
                    <td>{(item.coverage * 100).toFixed(0)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <article className="panel comparison-section">
          <div className="panel-header">
            <div>
              <h2>Origin stability</h2>
              <p className="panel-subtitle">
                Distribution of rolling-origin aggregate error
              </p>
            </div>
            <Activity size={18} aria-hidden="true" />
          </div>
          <p className="evidence-callout">
            <strong>{originRange.toFixed(1)} pp range</strong> between the best
            and worst observed origins. Large ranges indicate temporal
            instability even when aggregate WAPE looks healthy.
          </p>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">Origin</th>
                  <th scope="col">WAPE</th>
                  <th scope="col">Bias</th>
                  <th scope="col">Coverage</th>
                </tr>
              </thead>
              <tbody>
                {run.rollingOrigins.map((item) => (
                  <tr key={item.origin}>
                    <th scope="row">{item.origin}</th>
                    <td>{item.wape.toFixed(1)}%</td>
                    <td>{item.bias.toFixed(1)}%</td>
                    <td>{(item.coverage * 100).toFixed(0)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      </section>

      <section className="panel comparison-section">
        <div className="panel-header">
          <div>
            <h2>Worst-performing segments</h2>
            <p className="panel-subtitle">
              Prioritized by WAPE; inspect bias and under-coverage together
            </p>
          </div>
          <TriangleAlert size={18} aria-hidden="true" />
        </div>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Priority</th>
                <th scope="col">Segment</th>
                <th scope="col">WAPE</th>
                <th scope="col">Bias</th>
                <th scope="col">Coverage</th>
                <th scope="col">Signal</th>
              </tr>
            </thead>
            <tbody>
              {worstSegments.map((item, index) => (
                <tr key={item.segmentId}>
                  <td>{index + 1}</td>
                  <th scope="row">{item.segmentName}</th>
                  <td>{item.wape.toFixed(1)}%</td>
                  <td>{item.bias.toFixed(1)}%</td>
                  <td>{(item.coverage * 100).toFixed(0)}%</td>
                  <td>
                    {item.coverage < 0.75
                      ? "Under-covered"
                      : Math.abs(item.bias) > 2
                        ? "Directional bias"
                        : "Stable"}
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
