import {
  leaderboardResultSchema,
  type LeaderboardFilters,
  type LeaderboardOptions,
} from "../types/leaderboard";
import {
  forecastApiOptionsSchema,
  forecastApiResultSchema,
  type ForecastFilters,
  type ForecastOptions,
} from "../types/forecasts";
import type { ForecastLabDataSource } from "./dataSource";

export class ApiDataSource implements ForecastLabDataSource {
  constructor(private readonly baseUrl: string) {}

  private requestError(label: string, response: Response) {
    const requestId = response.headers.get("x-request-id");
    return new Error(
      `${label} request failed (${response.status})${requestId ? ` · request ${requestId}` : ""}`,
    );
  }

  async getForecastOptions(runId?: string): Promise<ForecastOptions> {
    const query = new URLSearchParams();
    if (runId) query.set("run_id", runId);
    const suffix = query.size > 0 ? `?${query}` : "";
    const response = await fetch(
      `${this.baseUrl}/v1/forecasts/options${suffix}`,
    );
    if (!response.ok) {
      throw this.requestError("Forecast options", response);
    }
    return forecastApiOptionsSchema.parse(await response.json());
  }

  async getForecasts(filters: ForecastFilters) {
    const query = new URLSearchParams({
      run_id: filters.runId,
      entity_id: filters.entityId,
      model_id: filters.modelId,
      exception_state: filters.exceptionState,
    });
    if (filters.horizon !== null) query.set("horizon", String(filters.horizon));
    const response = await fetch(`${this.baseUrl}/v1/forecasts?${query}`);
    if (!response.ok) {
      throw this.requestError("Forecast", response);
    }
    const payload = await response.json();
    return forecastApiResultSchema.parse(payload);
  }

  async getLeaderboardOptions(): Promise<LeaderboardOptions> {
    const response = await fetch(
      `${this.baseUrl}/v1/models/leaderboard/options`,
    );
    if (!response.ok) {
      throw this.requestError("Leaderboard options", response);
    }
    return response.json() as Promise<LeaderboardOptions>;
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
      throw this.requestError("Leaderboard", response);
    }
    return leaderboardResultSchema.parse(await response.json());
  }

  async getModel(modelId: string, filters: LeaderboardFilters) {
    const result = await this.getLeaderboard(filters);
    return result.rows.find((row) => row.modelId === modelId) ?? null;
  }
}
