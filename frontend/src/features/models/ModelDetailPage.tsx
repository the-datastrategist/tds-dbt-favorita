import { ArrowLeft, FlaskConical } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { MetricCard } from "../../components/MetricCard";
import { PageSkeleton, PageState } from "../../components/PageState";
import { useModel } from "./useLeaderboard";

const toHorizon = (value: string | null) => {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 1 && parsed <= 7 ? parsed : 1;
};

export const ModelDetailPage = () => {
  const { modelId = "" } = useParams();
  const [searchParams] = useSearchParams();
  const horizon = toHorizon(searchParams.get("horizon"));
  const segmentId = searchParams.get("segment") ?? "demo_all";
  const modelQuery = useModel(modelId, { horizon, segmentId });
  const query = `?horizon=${horizon}&segment=${encodeURIComponent(segmentId)}`;

  if (modelQuery.isLoading) {
    return <PageSkeleton />;
  }

  if (modelQuery.isError) {
    return (
      <div className="page">
        <PageState
          title="Model evidence is unavailable"
          message={
            modelQuery.error instanceof Error
              ? modelQuery.error.message
              : "Try again later."
          }
        />
      </div>
    );
  }

  const model = modelQuery.data;
  if (!model) {
    return (
      <div className="page">
        <PageState
          title="Model not found"
          message="This model is not present in the demo fixture."
        />
      </div>
    );
  }

  return (
    <div className="page">
      <Link className="back-link" to={`/models/leaderboard${query}`}>
        <ArrowLeft size={14} aria-hidden="true" /> Back to leaderboard
      </Link>

      <header className="page-header">
        <div>
          <p className="eyebrow">{model.family}</p>
          <h1>{model.modelName}</h1>
          <p className="page-description">{model.description}</p>
        </div>
        <span className={`status-badge ${model.lifecycleStatus}`}>
          {model.lifecycleStatus}
        </span>
      </header>

      <div className="page-actions">
        <Link
          className="primary-button"
          to={`/experiments?model=${encodeURIComponent(model.modelId)}`}
        >
          <FlaskConical size={15} aria-hidden="true" /> View experiments
        </Link>
      </div>

      <section className="metric-grid" aria-label="Selected model metrics">
        <MetricCard
          label="WAPE"
          value={`${model.wape.toFixed(1)}%`}
          context="Lower is better"
        />
        <MetricCard
          label="Bias"
          value={`${model.bias.toFixed(1)}%`}
          context="Zero is unbiased"
        />
        <MetricCard
          label="Coverage"
          value={`${(model.coverage * 100).toFixed(0)}%`}
          context="P10–P90 interval"
        />
        <MetricCard
          label="vs baseline"
          value={`${model.baselineImprovement > 0 ? "+" : ""}${model.baselineImprovement.toFixed(1)}%`}
          context={
            model.evidenceStatus === "sufficient"
              ? "Comparable evidence"
              : "Ranking withheld"
          }
        />
      </section>

      <section className="detail-grid">
        <article className="panel detail-card">
          <h2>Evaluation context</h2>
          <dl className="detail-list">
            <dt>Horizon</dt>
            <dd>Day {model.horizon}</dd>
            <dt>Segment</dt>
            <dd>{model.segmentName}</dd>
            <dt>Evidence</dt>
            <dd>{model.evidenceStatus}</dd>
            <dt>Last evaluated</dt>
            <dd>{new Date(model.lastEvaluatedAt).toLocaleString()}</dd>
          </dl>
        </article>
        <article className="panel detail-card">
          <h2>Provenance</h2>
          <dl className="detail-list">
            <dt>Model ID</dt>
            <dd>{model.modelId}</dd>
            <dt>Data mode</dt>
            <dd>Synthetic fixture</dd>
            <dt>Population</dt>
            <dd>Identical rolling-origin evaluation rows</dd>
            <dt>Publication</dt>
            <dd>Read-only public demonstration</dd>
          </dl>
        </article>
      </section>
    </div>
  );
};
