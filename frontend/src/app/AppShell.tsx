import {
  Activity,
  BarChart3,
  ExternalLink,
  FlaskConical,
  GitBranch,
  LayoutDashboard,
  Settings2,
  Trophy,
  Workflow,
} from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

const navigation = [
  { label: "Overview", to: "/overview", icon: LayoutDashboard },
  { label: "Model leaderboard", to: "/models/leaderboard", icon: Trophy },
  { label: "Experiments", to: "/experiments", icon: FlaskConical },
  { label: "Error analysis", to: "/accuracy", icon: Activity },
  { label: "Pipeline health", to: "/pipeline", icon: Workflow },
  { label: "Hierarchy", to: "/hierarchy", icon: GitBranch },
  { label: "Operations", to: "/operations", icon: Settings2 },
  {
    label: "Forecast explorer",
    to: "/forecasts",
    icon: BarChart3,
  },
];

const environmentLabel =
  import.meta.env.VITE_DATA_MODE === "api"
    ? "Authenticated production data"
    : "Synthetic public demo";

const specialistLinks = [
  {
    label: "dbt lineage",
    href:
      import.meta.env.VITE_DBT_DOCS_URL ||
      "https://the-datastrategist.github.io/tds-dbt-favorita/dbt-docs/",
  },
  {
    label: "Prefect",
    href:
      import.meta.env.VITE_PREFECT_URL ||
      "https://github.com/the-datastrategist/tds-dbt-favorita/blob/main/docs/prefect/component_guide.md",
  },
  {
    label: "MLflow",
    href:
      import.meta.env.VITE_MLFLOW_URL ||
      "https://github.com/the-datastrategist/tds-dbt-favorita/blob/main/docs/mlflow/component_guide.md",
  },
  {
    label: "Runbook",
    href:
      import.meta.env.VITE_RUNBOOK_URL ||
      "https://github.com/the-datastrategist/tds-dbt-favorita/blob/main/docs/forecast_operations.md",
  },
];

export const AppShell = () => (
  <div className="app-shell">
    <aside className="sidebar">
      <div className="product-lockup">
        <div className="product-mark" aria-hidden="true">
          FL
        </div>
        <div>
          <p className="product-name">ForecastLab</p>
          <p className="product-subtitle">Forecasting workbench</p>
        </div>
      </div>

      <nav aria-label="Primary navigation">
        <div className="nav-section-label">Science</div>
        <ul className="nav-list">
          {navigation.map(({ label, to, icon: Icon }) => (
            <li key={to}>
              <NavLink
                className={({ isActive }) =>
                  `nav-link${isActive ? " active" : ""}`
                }
                to={to}
              >
                <Icon size={15} aria-hidden="true" />
                {label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <nav aria-label="Specialist tools">
        <div className="nav-section-label">Specialist tools</div>
        <ul className="nav-list">
          {specialistLinks.map(({ label, href }) => (
            <li key={label}>
              <a className="nav-link" href={href} rel="noreferrer" target="_blank">
                <ExternalLink size={15} aria-hidden="true" />
                {label}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      <div className="sidebar-footer">
        <div className="brand-attribution">
          <img
            src={`${import.meta.env.BASE_URL}brand/tds-logo-circle-white.jpg`}
            alt=""
          />
          <span>
            Built by
            <br />
            theDataStrategist
          </span>
        </div>
      </div>
    </aside>

    <div className="main-area">
      <header className="topbar">
        <span className="environment-label">
          <span className="environment-dot" aria-hidden="true" />
          {environmentLabel}
        </span>
        <a
          className="topbar-link"
          href="https://github.com/the-datastrategist/tds-dbt-favorita"
          rel="noreferrer"
          target="_blank"
        >
          <ExternalLink size={14} aria-hidden="true" /> <span>GitHub</span>
        </a>
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  </div>
);
