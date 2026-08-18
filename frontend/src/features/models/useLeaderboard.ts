import { useQuery } from "@tanstack/react-query";
import { createDataSource } from "../../data";
import type { LeaderboardFilters } from "../../types/leaderboard";

const dataSource = createDataSource();

export const useLeaderboardOptions = () =>
  useQuery({
    queryKey: ["leaderboard-options"],
    queryFn: () => dataSource.getLeaderboardOptions(),
  });

export const useLeaderboard = (filters: LeaderboardFilters) =>
  useQuery({
    queryKey: ["leaderboard", filters.horizon, filters.segmentId],
    queryFn: () => dataSource.getLeaderboard(filters),
  });

export const useModel = (modelId: string, filters: LeaderboardFilters) =>
  useQuery({
    queryKey: ["model", modelId, filters.horizon, filters.segmentId],
    queryFn: () => dataSource.getModel(modelId, filters),
  });
