import { BarChart3, ExternalLink, Trophy } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

const navigation = [
  { label: "Model leaderboard", to: "/models/leaderboard", icon: Trophy },
  {
    label: "Forecast explorer",
    to: "/forecasts",
    icon: BarChart3,
    disabled: true,
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
          {navigation.map(({ label, to, icon: Icon, disabled }) => (
            <li key={to}>
              {disabled ? (
                <span
                  className="nav-link"
                  aria-disabled="true"
                  title="Planned for the next slice"
                >
                  <Icon size={15} aria-hidden="true" />
                  {label}
                </span>
              ) : (
                <NavLink
                  className={({ isActive }) =>
                    `nav-link${isActive ? " active" : ""}`
                  }
                  to={to}
                >
                  <Icon size={15} aria-hidden="true" />
                  {label}
                </NavLink>
              )}
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
          Synthetic public demo
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
