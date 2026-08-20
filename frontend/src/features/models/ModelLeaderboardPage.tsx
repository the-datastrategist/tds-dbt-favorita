import { Database, Sparkles } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { MetricCard } from "../../components/MetricCard";
import { PageSkeleton, PageState } from "../../components/PageState";
import { LeaderboardChart } from "./LeaderboardChart";
import { LeaderboardTable } from "./LeaderboardTable";
import { useLeaderboard, useLeaderboardOptions } from "./useLeaderboard";

const toHorizon = (value: string | null) => {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 1 && parsed <= 7 ? parsed : 1;
};

export const ModelLeaderboardPage = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const horizon = toHorizon(searchParams.get("horizon"));
  const segmentId =
    searchParams.get("segment") ??
    (import.meta.env.VITE_DATA_MODE === "api" ? "all" : "demo_all");
  const filters = { horizon, segmentId };
  const optionsQuery = useLeaderboardOptions();
  const leaderboardQuery = useLeaderboard(filters);

  const updateFilter = (key: "horizon" | "segment", value: string) => {
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.set(key, value);
        return next;
      },
      { replace: true },
    );
  };

  if (optionsQuery.isLoading || leaderboardQuery.isLoading) {
    return <PageSkeleton />;
  }

  if (optionsQuery.isError || leaderboardQuery.isError) {
    const error = optionsQuery.error ?? leaderboardQuery.error;
    return (
      <div className="page">
        <PageState
          title="Model evidence is unavailable"
          message={
            error instanceof Error
              ? error.message
              : "The leaderboard could not be loaded."
          }
        />
      </div>
    );
  }

  const result = leaderboardQuery.data;
  const options = optionsQuery.data;
  if (!result || !options || result.rows.length === 0) {
    return (
      <div className="page">
        <PageState
          title="No comparable models"
          message="No model evidence matches the selected horizon and segment."
        />
      </div>
    );
  }

  const champion = result.rows.find(
    ({ lifecycleStatus }) => lifecycleStatus === "champion",
  );
  const baseline = result.rows.find(
    ({ modelId, lifecycleStatus }) =>
      modelId === "seasonal_naive_7d" || lifecycleStatus === "baseline",
  );

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Model science</p>
          <h1>Model Leaderboard</h1>
          <p className="page-description">
            Which model wins by horizon and segment, and is the improvement over
            a comparable baseline meaningful?
          </p>
        </div>
        <span className="demo-pill">
          <Sparkles size={12} aria-hidden="true" />{" "}
          {result.datasetKind === "live"
            ? "Live warehouse evidence"
            : "Synthetic fixture"}
        </span>
      </header>

      <section className="filters" aria-label="Leaderboard filters">
        <div className="filter-field">
          <label htmlFor="horizon-filter">Forecast horizon</label>
          <select
            id="horizon-filter"
            value={horizon}
            onChange={(event) => updateFilter("horizon", event.target.value)}
          >
            {options.horizons.map((value) => (
              <option key={value} value={value}>
                Day {value}
              </option>
            ))}
          </select>
        </div>
        <div className="filter-field">
          <label htmlFor="segment-filter">Demand segment</label>
          <select
            id="segment-filter"
            value={segmentId}
            onChange={(event) => updateFilter("segment", event.target.value)}
          >
            {options.segments.map((segment) => (
              <option key={segment.id} value={segment.id}>
                {segment.name}
              </option>
            ))}
          </select>
        </div>
        <span className="environment-label">
          <Database size={13} aria-hidden="true" />{" "}
          {result.datasetKind === "live"
            ? "Live warehouse evidence"
            : result.fixtureVersion}
        </span>
      </section>

      <section className="metric-grid" aria-label="Champion summary">
        <MetricCard
          label="Current champion"
          value={champion?.modelName ?? "Unavailable"}
          context={`${result.segmentName}, day ${horizon}`}
        />
        <MetricCard
          label="Champion WAPE"
          value={champion ? `${champion.wape.toFixed(1)}%` : "—"}
          context="Lower is better"
        />
        <MetricCard
          label="Baseline improvement"
          value={
            champion ? `+${champion.baselineImprovement.toFixed(1)}%` : "—"
          }
          context={`Compared with ${baseline?.modelName ?? "configured baseline"}`}
        />
        <MetricCard
          label="Interval coverage"
          value={
            champion?.coverage === null || !champion
              ? "—"
              : `${(champion.coverage * 100).toFixed(0)}%`
          }
          context={
            champion?.coverage === null
              ? "No interval evidence for this run"
              : "P10–P90 realized coverage"
          }
        />
      </section>

      <section className="content-grid">
        <div className="panel">
          <div className="panel-header">
            <div>
              <h2>Comparable performance</h2>
              <p className="panel-subtitle">
                Rolling-origin WAPE on an identical population
              </p>
            </div>
          </div>
          <LeaderboardTable
            rows={result.rows}
            horizon={horizon}
            segmentId={segmentId}
          />
        </div>

        <div className="panel">
          <div className="panel-header">
            <div>
              <h2>WAPE comparison</h2>
              <p className="panel-subtitle">
                Models with sufficient evaluation evidence
              </p>
            </div>
          </div>
          <LeaderboardChart rows={result.rows} />
        </div>
      </section>
    </div>
  );
};
