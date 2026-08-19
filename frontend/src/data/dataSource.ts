import type {
  LeaderboardFilters,
  LeaderboardOptions,
  LeaderboardResult,
  LeaderboardRow,
} from "../types/leaderboard";
import type {
  ForecastFilters,
  ForecastOptions,
  ForecastResult,
} from "../types/forecasts";

export interface ForecastLabDataSource {
  getLeaderboardOptions(): Promise<LeaderboardOptions>;
  getLeaderboard(filters: LeaderboardFilters): Promise<LeaderboardResult>;
  getModel(
    modelId: string,
    filters: LeaderboardFilters,
  ): Promise<LeaderboardRow | null>;
  getForecastOptions(runId?: string): Promise<ForecastOptions>;
  getForecasts(filters: ForecastFilters): Promise<ForecastResult>;
}
