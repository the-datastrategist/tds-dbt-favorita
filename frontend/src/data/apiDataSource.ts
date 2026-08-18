import {
  leaderboardResultSchema,
  type LeaderboardFilters,
  type LeaderboardOptions,
} from "../types/leaderboard";
import type { ForecastLabDataSource } from "./dataSource";

export class ApiDataSource implements ForecastLabDataSource {
  constructor(private readonly baseUrl: string) {}

  async getLeaderboardOptions(): Promise<LeaderboardOptions> {
    return {
      horizons: [1, 2, 3, 4, 5, 6, 7],
      segments: [{ id: "all", name: "All segments" }],
    };
  }

  async getLeaderboard(filters: LeaderboardFilters) {
    const query = new URLSearchParams({
      horizon: String(filters.horizon),
      segment_id: filters.segmentId,
    });
    const response = await fetch(
      `${this.baseUrl}/v1/models/leaderboard?${query}`,
    );
    if (!response.ok) {
      throw new Error(`Leaderboard request failed (${response.status})`);
    }
    return leaderboardResultSchema.parse(await response.json());
  }

  async getModel(modelId: string, filters: LeaderboardFilters) {
    const result = await this.getLeaderboard(filters);
    return result.rows.find((row) => row.modelId === modelId) ?? null;
  }
}
