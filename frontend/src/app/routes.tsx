import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./AppShell";
import { ModelDetailPage } from "../features/models/ModelDetailPage";
import { ModelLeaderboardPage } from "../features/models/ModelLeaderboardPage";
import { OverviewPage } from "../features/overview/OverviewPage";
import { ForecastExplorerPage } from "../features/forecasts/ForecastExplorerPage";
import { ExperimentComparisonPage } from "../features/experiments/ExperimentComparisonPage";
import { ExperimentRunsPage } from "../features/experiments/ExperimentRunsPage";
import { AccuracyPage } from "../features/accuracy/AccuracyPage";
import { OperationsPage } from "../features/operations/OperationsPage";

export const AppRoutes = () => (
  <Routes>
    <Route element={<AppShell />}>
      <Route index element={<Navigate replace to="/overview" />} />
      <Route path="overview" element={<OverviewPage />} />
      <Route path="forecasts" element={<ForecastExplorerPage />} />
      <Route path="experiments" element={<ExperimentRunsPage />} />
      <Route path="accuracy" element={<AccuracyPage />} />
      <Route path="operations" element={<OperationsPage />} />
      <Route
        path="experiments/compare"
        element={<ExperimentComparisonPage />}
      />
      <Route path="models/leaderboard" element={<ModelLeaderboardPage />} />
      <Route path="models/:modelId" element={<ModelDetailPage />} />
      <Route path="*" element={<Navigate replace to="/overview" />} />
    </Route>
  </Routes>
);
