interface MetricCardProps {
  label: string;
  value: string;
  context: string;
}

export const MetricCard = ({ label, value, context }: MetricCardProps) => (
  <article className="metric-card">
    <div className="metric-label">{label}</div>
    <div className="metric-value">{value}</div>
    <p className="metric-context">{context}</p>
  </article>
);
