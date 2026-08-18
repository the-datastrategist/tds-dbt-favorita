import type {
  LeaderboardFilters,
  LeaderboardOptions,
  LeaderboardResult,
  LeaderboardRow,
} from "../types/leaderboard";

export interface ForecastLabDataSource {
  getLeaderboardOptions(): Promise<LeaderboardOptions>;
  getLeaderboard(filters: LeaderboardFilters): Promise<LeaderboardResult>;
  getModel(
    modelId: string,
    filters: LeaderboardFilters,
  ): Promise<LeaderboardRow | null>;
}
