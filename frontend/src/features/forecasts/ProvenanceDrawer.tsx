import { X } from "lucide-react";
import type { ForecastProvenance } from "../../types/forecasts";

const labels: Record<keyof ForecastProvenance, string> = {
  contractName: "Contract",
  contractHash: "Contract hash",
  modelRunId: "Model run",
  calibrationRunId: "Calibration run",
  reconciliationRunId: "Reconciliation run",
  hierarchyVersion: "Hierarchy version",
  featureVersion: "Feature version",
  featureAvailabilityHash: "Feature availability hash",
  dataCutoff: "Data cutoff",
  codeSha: "Code SHA",
  publicationVersion: "Publication version",
};

export const ProvenanceDrawer = ({
  provenance,
  onClose,
}: {
  provenance: ForecastProvenance;
  onClose: () => void;
}) => (
  <aside className="provenance-drawer" aria-labelledby="provenance-title">
    <div className="drawer-header">
      <div>
        <p className="eyebrow">Canonical output</p>
        <h2 id="provenance-title">Forecast provenance</h2>
      </div>
      <button
        className="icon-button"
        type="button"
        onClick={onClose}
        aria-label="Close provenance"
      >
        <X size={18} aria-hidden="true" />
      </button>
    </div>
    <dl className="provenance-list">
      {(Object.keys(labels) as Array<keyof ForecastProvenance>).map((key) => (
        <div key={key}>
          <dt>{labels[key]}</dt>
          <dd>{provenance[key]}</dd>
        </div>
      ))}
    </dl>
  </aside>
);
