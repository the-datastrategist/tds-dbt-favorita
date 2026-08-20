import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, CircleX, GitBranch } from "lucide-react";
import { useState } from "react";
import { PageSkeleton, PageState } from "../../components/PageState";
import { platformDataSource } from "../../data/platformDataSource";

export const HierarchyPage = () => {
  const query = useQuery({
    queryKey: ["hierarchy", "current"],
    queryFn: () => platformDataSource.hierarchy(),
  });
  const [level, setLevel] = useState("all");

  if (query.isLoading) return <PageSkeleton />;
  if (query.isError)
    return (
      <div className="page">
        <PageState
          title="Hierarchy evidence is unavailable"
          message={
            query.error instanceof Error
              ? query.error.message
              : "Reconciliation evidence could not be loaded."
          }
        />
      </div>
    );
  if (!query.data)
    return (
      <div className="page">
        <PageState
          title="No hierarchy evidence"
          message="Run a hierarchy-enabled forecast before opening this view."
        />
      </div>
    );

  const snapshot = query.data;
  const nodes =
    level === "all"
      ? snapshot.nodes
      : snapshot.nodes.filter((node) => node.level === level);
  const failedGates = snapshot.gates.filter((gate) => !gate.passed).length;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Coherent forecasts</p>
          <h1>Hierarchy &amp; Reconciliation</h1>
          <p className="page-description">
            Navigate hierarchy levels, compare base and reconciled P50 values,
            and inspect fail-closed coherence and quantile gates.
          </p>
        </div>
        <span className="demo-pill">
          <GitBranch size={12} aria-hidden="true" />{" "}
          {snapshot.datasetKind === "live"
            ? "Live hierarchy"
            : "Synthetic fixture"}
        </span>
      </header>

      <section className="filter-bar" aria-label="Hierarchy filters">
        <div className="filter-field wide-filter">
          <label htmlFor="hierarchy-level">Hierarchy level</label>
          <select
            id="hierarchy-level"
            value={level}
            onChange={(event) => setLevel(event.target.value)}
          >
            <option value="all">All levels</option>
            {snapshot.levels.map((item) => (
              <option key={item.name} value={item.name}>
                {item.position + 1}. {item.name} ({item.nodeCount})
              </option>
            ))}
          </select>
        </div>
      </section>

      <section className="metric-grid" aria-label="Hierarchy summary">
        <article className="metric-card">
          <span>Hierarchy</span>
          <strong>{snapshot.hierarchyVersion}</strong>
          <small>{snapshot.hierarchyName}</small>
        </article>
        <article className="metric-card">
          <span>Method</span>
          <strong>{snapshot.method}</strong>
          <small>{snapshot.status}</small>
        </article>
        <article className="metric-card">
          <span>Structure</span>
          <strong>{snapshot.nodeCount}</strong>
          <small>
            {snapshot.edgeCount} edges · {snapshot.levels.length} levels
          </small>
        </article>
        <article className="metric-card">
          <span>Failed gates</span>
          <strong>{failedGates}</strong>
          <small>tolerance {snapshot.tolerance}</small>
        </article>
      </section>

      {failedGates > 0 && (
        <div className="inline-alert danger-alert" role="alert">
          <CircleX size={15} /> Reconciliation failed. Publication must remain
          blocked until every gate passes.
        </div>
      )}

      <section className="analysis-grid">
        <article className="panel">
          <div className="panel-header">
            <div>
              <h2>Hierarchy nodes</h2>
              <p className="panel-subtitle">
                Base versus reconciled average P50 by node
              </p>
            </div>
          </div>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Node</th>
                  <th>Level</th>
                  <th>Parent</th>
                  <th>Base P50</th>
                  <th>Reconciled P50</th>
                  <th>Delta</th>
                </tr>
              </thead>
              <tbody>
                {nodes.map((node) => (
                  <tr key={node.id}>
                    <th scope="row">{node.label}</th>
                    <td>{node.level}</td>
                    <td>{node.parentId ?? "Root"}</td>
                    <td>{node.baseP50?.toFixed(1) ?? "—"}</td>
                    <td>{node.reconciledP50?.toFixed(1) ?? "—"}</td>
                    <td
                      className={
                        node.delta && node.delta < 0
                          ? "negative"
                          : node.delta && node.delta > 0
                            ? "positive"
                            : ""
                      }
                    >
                      {node.delta?.toFixed(1) ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
        <aside className="panel">
          <div className="panel-header">
            <div>
              <h2>Reconciliation gates</h2>
              <p className="panel-subtitle">
                Violations are displayed, never silently corrected
              </p>
            </div>
          </div>
          <ul className="gate-list">
            {snapshot.gates.map((gate) => (
              <li key={gate.name} className={gate.passed ? "passed" : "failed"}>
                {gate.passed ? (
                  <CheckCircle2 size={16} />
                ) : (
                  <CircleX size={16} />
                )}
                <span>
                  <strong>{gate.name}</strong>
                  <small>{gate.violationCount} violations</small>
                </span>
              </li>
            ))}
          </ul>
          <dl className="provenance-list compact-provenance">
            <div>
              <dt>Reconciliation run</dt>
              <dd>{snapshot.reconciliationRunId}</dd>
            </div>
            <div>
              <dt>Forecast run</dt>
              <dd>{snapshot.forecastRunId}</dd>
            </div>
          </dl>
        </aside>
      </section>
    </div>
  );
};
