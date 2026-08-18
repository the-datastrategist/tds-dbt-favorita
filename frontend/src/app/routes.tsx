import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./AppShell";
import { ModelDetailPage } from "../features/models/ModelDetailPage";
import { ModelLeaderboardPage } from "../features/models/ModelLeaderboardPage";

export const AppRoutes = () => (
  <Routes>
    <Route element={<AppShell />}>
      <Route index element={<Navigate replace to="/models/leaderboard" />} />
      <Route path="models/leaderboard" element={<ModelLeaderboardPage />} />
      <Route path="models/:modelId" element={<ModelDetailPage />} />
      <Route path="*" element={<Navigate replace to="/models/leaderboard" />} />
    </Route>
  </Routes>
);
