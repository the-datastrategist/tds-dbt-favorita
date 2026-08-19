import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  LockKeyhole,
  PackageCheck,
  RotateCcw,
  ShieldCheck,
  SlidersHorizontal,
} from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { PageSkeleton, PageState } from "../../components/PageState";
import { operationsDataSource } from "../../data/operationsDataSource";
import type {
  LifecycleAction,
  LifecycleIntent,
  OperationRun,
} from "../../types/operations";

const requiredRole: Record<
  LifecycleAction,
  "planner" | "approver" | "publisher"
> = {
  override: "planner",
  approve: "approver",
  publish: "publisher",
  supersede: "publisher",
  rollback: "publisher",
};

const actionLabel: Record<LifecycleAction, string> = {
  override: "Create override",
  approve: "Approve run",
  publish: "Publish run",
  supersede: "Supersede publication",
  rollback: "Roll back publication",
};

const OperationActions = ({ run }: { run: OperationRun }) => {
  const capabilities = useQuery({
    queryKey: ["capabilities"],
    queryFn: () => operationsDataSource.capabilities(),
  });
  const queryClient = useQueryClient();
  const [action, setAction] = useState<LifecycleAction>("override");
  const [confirmed, setConfirmed] = useState(false);
  const mutation = useMutation({
    mutationFn: (intent: LifecycleIntent) =>
      operationsDataSource.mutate(intent),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["operations"] }),
  });
  const allowed = Boolean(
    capabilities.data?.mutationsEnabled &&
    capabilities.data.roles.includes(requiredRole[action]),
  );

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const now = Date.now();
    mutation.mutate({
      action,
      runId: run.runId,
      outputId: String(values.get("outputId") ?? ""),
      value: Number(values.get("value")),
      reasonCode: String(values.get("reasonCode") ?? ""),
      comment: String(values.get("comment") ?? ""),
      approvalIdempotencyKey: String(values.get("approvalKey") ?? ""),
      publicationVersion: Number(values.get("publicationVersion")),
      priorVersion: Number(values.get("priorVersion")),
      idempotencyKey: `${action}:${run.runId}:${now}`,
    });
  };

  return (
    <section className="panel operation-actions">
      <div className="panel-header">
        <div>
          <h2>Governed actions</h2>
          <p className="panel-subtitle">
            The API revalidates role, state transition, completeness, and
            idempotency.
          </p>
        </div>
        <ShieldCheck size={18} aria-hidden="true" />
      </div>
      {!capabilities.data?.mutationsEnabled && (
        <div className="inline-alert" role="status">
          <LockKeyhole size={15} aria-hidden="true" /> Actions are disabled in
          this deployment. Read-only evidence remains available.
        </div>
      )}
      <form onSubmit={submit}>
        <div className="action-tabs" role="group" aria-label="Lifecycle action">
          {(Object.keys(actionLabel) as LifecycleAction[]).map((value) => (
            <button
              key={value}
              type="button"
              className={action === value ? "active" : ""}
              onClick={() => {
                setAction(value);
                setConfirmed(false);
              }}
            >
              {actionLabel[value]}
            </button>
          ))}
        </div>
        <div className="action-form-grid">
          {action === "override" && (
            <>
              <label>
                Forecast output
                <select name="outputId" required>
                  {run.outputs.map((output) => (
                    <option key={output.id} value={output.id}>
                      {output.entityLabel} · {output.targetDate} ·{" "}
                      {output.currentValue}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Override value
                <input
                  name="value"
                  type="number"
                  min="0"
                  step="0.01"
                  required
                />
              </label>
            </>
          )}
          {action === "publish" && (
            <label>
              Approval idempotency key
              <input name="approvalKey" required />
            </label>
          )}
          {(action === "publish" ||
            action === "supersede" ||
            action === "rollback") && (
            <label>
              New publication version
              <input
                name="publicationVersion"
                type="number"
                min="1"
                defaultValue={(run.publicationVersion ?? 0) + 1}
                required
              />
            </label>
          )}
          {(action === "supersede" || action === "rollback") && (
            <label>
              Prior publication version
              <input
                name="priorVersion"
                type="number"
                min="1"
                defaultValue={run.publicationVersion ?? 1}
                required
              />
            </label>
          )}
          <label>
            Reason code
            <input name="reasonCode" placeholder="review_complete" required />
          </label>
          <label className="full-field">
            Audit comment
            <textarea name="comment" rows={3} minLength={3} required />
          </label>
        </div>
        <label className="confirmation-check">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(event) => setConfirmed(event.target.checked)}
          />{" "}
          I reviewed the selected run, action, and immutable version
          identifiers.
        </label>
        {mutation.isError && (
          <p className="form-error" role="alert">
            {mutation.error instanceof Error
              ? mutation.error.message
              : "The lifecycle action failed."}
          </p>
        )}
        {mutation.isSuccess && (
          <p className="form-success" role="status">
            <CheckCircle2 size={14} aria-hidden="true" /> {mutation.data.action}{" "}
            accepted{mutation.data.retry ? " as an idempotent retry" : ""}.
          </p>
        )}
        <button
          className="primary-button"
          type="submit"
          disabled={!allowed || !confirmed || mutation.isPending}
        >
          {mutation.isPending ? "Submitting…" : actionLabel[action]}
        </button>
        {capabilities.data?.mutationsEnabled && !allowed && (
          <small className="permission-note">
            Requires the {requiredRole[action]} role.
          </small>
        )}
      </form>
    </section>
  );
};

export const OperationsPage = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const snapshot = useQuery({
    queryKey: ["operations"],
    queryFn: () => operationsDataSource.snapshot(),
  });
  const requestedRun = searchParams.get("run") ?? "";
  const run =
    snapshot.data?.runs.find(({ runId }) => runId === requestedRun) ??
    snapshot.data?.runs[0];

  useEffect(() => {
    if (!run || requestedRun === run.runId) return;
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.set("run", run.runId);
        return next;
      },
      { replace: true },
    );
  }, [requestedRun, run, setSearchParams]);

  if (snapshot.isLoading) return <PageSkeleton />;
  if (snapshot.isError)
    return (
      <div className="page">
        <PageState
          title="Operations evidence is unavailable"
          message={
            snapshot.error instanceof Error
              ? snapshot.error.message
              : "The operational read model could not be loaded."
          }
        />
      </div>
    );
  if (!run)
    return (
      <div className="page">
        <PageState
          title="No forecast runs"
          message="Create a governed forecast draft before using the operations workbench."
        />
      </div>
    );

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Forecast operations</p>
          <h1>Publication Control</h1>
          <p className="page-description">
            Review exceptions, planner adjustments, approval completeness,
            delivery state, FVA, and immutable publication history.
          </p>
        </div>
        <span className="demo-pill">
          <PackageCheck size={12} aria-hidden="true" />{" "}
          {snapshot.data?.datasetKind === "live"
            ? "Live operations"
            : "Synthetic fixture"}
        </span>
      </header>
      <section className="filter-bar" aria-label="Operations filters">
        <div className="filter-field wide-filter">
          <label htmlFor="operations-run">Forecast run</label>
          <select
            id="operations-run"
            value={run.runId}
            onChange={(event) =>
              setSearchParams({ run: event.target.value }, { replace: true })
            }
          >
            {snapshot.data?.runs.map((item) => (
              <option key={item.runId} value={item.runId}>
                {item.origin} · {item.status} · {item.modelName}
              </option>
            ))}
          </select>
        </div>
      </section>
      <section className="metric-grid" aria-label="Operational summary">
        <article className="metric-card">
          <span>Lifecycle state</span>
          <strong>{run.status}</strong>
          <small>
            {run.approvalCount}/{run.outputCount} approvals
          </small>
        </article>
        <article className="metric-card">
          <span>Exceptions</span>
          <strong>{run.exceptionCount}</strong>
          <small>{run.overrideCount} planner overrides</small>
        </article>
        <article className="metric-card">
          <span>Delivery</span>
          <strong>{run.deliveryStatus}</strong>
          <small>
            {run.publicationVersion
              ? `publication v${run.publicationVersion}`
              : "not published"}
          </small>
        </article>
        <article className="metric-card">
          <span>Total FVA</span>
          <strong>
            {run.totalWapeFvaPoints === null
              ? "Pending"
              : `${run.totalWapeFvaPoints.toFixed(1)} pp`}
          </strong>
          <small>{run.fvaStatus}</small>
        </article>
      </section>
      <section className="analysis-grid">
        <article className="panel comparison-section">
          <div className="panel-header">
            <div>
              <h2>Exception queue</h2>
              <p className="panel-subtitle">
                Sample outputs requiring planner attention
              </p>
            </div>
            <SlidersHorizontal size={18} aria-hidden="true" />
          </div>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">Entity</th>
                  <th scope="col">Target date</th>
                  <th scope="col">Value</th>
                  <th scope="col">State</th>
                </tr>
              </thead>
              <tbody>
                {run.outputs.map((output) => (
                  <tr key={output.id}>
                    <th scope="row">{output.entityLabel}</th>
                    <td>{output.targetDate}</td>
                    <td>{output.currentValue}</td>
                    <td>{output.exceptionState}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
        <article className="panel comparison-section">
          <div className="panel-header">
            <div>
              <h2>Lifecycle evidence</h2>
              <p className="panel-subtitle">
                Current immutable counters and delivery state
              </p>
            </div>
            <RotateCcw size={18} aria-hidden="true" />
          </div>
          <dl className="evidence-list">
            <div>
              <dt>Run ID</dt>
              <dd>{run.runId}</dd>
            </div>
            <div>
              <dt>Outputs</dt>
              <dd>{run.outputCount}</dd>
            </div>
            <div>
              <dt>Approvals</dt>
              <dd>{run.approvalCount}</dd>
            </div>
            <div>
              <dt>Planner FVA</dt>
              <dd>
                {run.plannerWapeFvaPoints === null
                  ? "Pending actuals"
                  : `${run.plannerWapeFvaPoints.toFixed(1)} pp`}
              </dd>
            </div>
            <div>
              <dt>Updated</dt>
              <dd>{new Date(run.updatedAt).toLocaleString()}</dd>
            </div>
          </dl>
        </article>
      </section>
      <OperationActions run={run} />
    </div>
  );
};
