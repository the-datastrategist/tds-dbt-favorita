import { CheckCircle2, Sparkles, TriangleAlert } from "lucide-react";
import { MetricCard } from "../../components/MetricCard";
import { PageSkeleton, PageState } from "../../components/PageState";
import { HorizonPerformanceChart } from "./HorizonPerformanceChart";
import { useOverview } from "./useOverview";

export const OverviewPage = () => {
  const overviewQuery = useOverview();

  if (overviewQuery.isLoading) {
    return <PageSkeleton />;
  }

  if (overviewQuery.isError) {
    return (
      <div className="page">
        <PageState
          title="Platform evidence is unavailable"
          message={
            overviewQuery.error instanceof Error
              ? overviewQuery.error.message
              : "The forecasting overview could not be loaded."
          }
        />
      </div>
    );
  }

  const results = overviewQuery.data?.results ?? [];
  const daySeven = results.find(({ horizon }) => horizon === 7);
  const champion = daySeven?.rows.find(
    ({ lifecycleStatus }) => lifecycleStatus === "champion",
  );
  const baseline = daySeven?.rows.find(
    ({ modelId, lifecycleStatus }) =>
      modelId === "seasonal_naive_7d" || lifecycleStatus === "baseline",
  );

  if (!champion || !baseline || results.length === 0) {
    return (
      <div className="page">
        <PageState
          title="No overview evidence"
          message="The configured model and baseline evidence is incomplete."
        />
      </div>
    );
  }

  const coverageTargetMet =
    champion.coverage !== null && champion.coverage >= 0.78;
  const datasetLabel =
    daySeven?.datasetKind === "live"
      ? "Live warehouse evidence"
      : "Synthetic fixture";

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Decision intelligence</p>
          <h1>Platform Overview</h1>
          <p className="page-description">
            A concise view of forecast quality, model leadership, and the
            evidence supporting the current champion.
          </p>
        </div>
        <span className="demo-pill">
          <Sparkles size={12} aria-hidden="true" /> {datasetLabel}
        </span>
      </header>

      <section className="metric-grid" aria-label="Platform summary">
        <MetricCard
          label="Current champion"
          value={champion.modelName}
          context="All regions, governed model selection"
        />
        <MetricCard
          label="Day 7 champion WAPE"
          value={`${champion.wape.toFixed(1)}%`}
          context="Lower is better"
        />
        <MetricCard
          label="Day 7 baseline WAPE"
          value={`${baseline.wape.toFixed(1)}%`}
          context={`Compared with ${baseline.modelName}`}
        />
        <MetricCard
          label="Day 7 interval coverage"
          value={
            champion.coverage === null
              ? "Unavailable"
              : `${(champion.coverage * 100).toFixed(0)}%`
          }
          context={
            champion.coverage === null
              ? "No interval evidence for this run"
              : "P10–P90 realized coverage"
          }
        />
      </section>

      <section className="overview-grid">
        <div className="panel">
          <div className="panel-header">
            <div>
              <h2>Performance by horizon</h2>
              <p className="panel-subtitle">
                Rolling-origin WAPE across the seven-day contract
              </p>
            </div>
          </div>
          <HorizonPerformanceChart results={results} />
        </div>

        <aside
          className="panel rationale-panel"
          aria-labelledby="rationale-title"
        >
          <div className="panel-header">
            <div>
              <h2 id="rationale-title">Champion rationale</h2>
              <p className="panel-subtitle">
                Evidence used by the governed selection policy
              </p>
            </div>
          </div>
          <div className="rationale-body">
            <p className="champion-name">{champion.modelName}</p>
            <p>
              Leads the configured baseline by{" "}
              {champion.baselineImprovement.toFixed(1)}% at day 7 while
              retaining ordered probabilistic coverage.
            </p>
            <ul className="evidence-list">
              <li className="evidence-pass">
                <CheckCircle2 aria-hidden="true" />
                Sufficient rolling-origin evidence
              </li>
              <li className="evidence-pass">
                <CheckCircle2 aria-hidden="true" />
                Positive Forecast Value Added
              </li>
              <li
                className={
                  coverageTargetMet ? "evidence-pass" : "evidence-watch"
                }
              >
                {coverageTargetMet ? (
                  <CheckCircle2 aria-hidden="true" />
                ) : (
                  <TriangleAlert aria-hidden="true" />
                )}
                {champion.coverage === null
                  ? "Interval coverage evidence is unavailable"
                  : `Day 7 coverage ${coverageTargetMet ? "meets" : "needs review against"} the target`}
              </li>
            </ul>
          </div>
        </aside>
      </section>
    </div>
  );
};
