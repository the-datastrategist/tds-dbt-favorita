interface PageStateProps {
  title: string;
  message: string;
}

export const PageState = ({ title, message }: PageStateProps) => (
  <section className="panel state-panel" role="status">
    <div>
      <h2>{title}</h2>
      <p>{message}</p>
    </div>
  </section>
);

export const PageSkeleton = () => (
  <div className="page" aria-label="Loading model evidence" aria-busy="true">
    <div className="skeleton skeleton-heading" />
    <div className="skeleton skeleton-panel" />
  </div>
);
