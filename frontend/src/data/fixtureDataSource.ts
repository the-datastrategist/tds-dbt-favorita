import fixtureJson from "../fixtures/forecastlab_demo_v1.json";
import {
  leaderboardFixtureSchema,
  type LeaderboardFilters,
  type LeaderboardResult,
  type LeaderboardRow,
} from "../types/leaderboard";
import type { ForecastLabDataSource } from "./dataSource";

const fixture = leaderboardFixtureSchema.parse(fixtureJson);

const round = (value: number, digits = 1) => Number(value.toFixed(digits));
const clamp = (value: number, minimum: number, maximum: number) =>
  Math.min(maximum, Math.max(minimum, value));

export class FixtureDataSource implements ForecastLabDataSource {
  async getLeaderboardOptions() {
    return {
      horizons: fixture.horizons,
      segments: fixture.segments.map(({ id, name }) => ({ id, name })),
    };
  }

  async getLeaderboard(
    filters: LeaderboardFilters,
  ): Promise<LeaderboardResult> {
    const horizonIndex = fixture.horizons.indexOf(filters.horizon);
    if (horizonIndex < 0) {
      throw new Error(`Unsupported demo horizon: ${filters.horizon}`);
    }

    const segment = fixture.segments.find(({ id }) => id === filters.segmentId);
    if (!segment) {
      throw new Error(`Unknown demo segment: ${filters.segmentId}`);
    }

    const rowsWithoutRank = fixture.models.map((model) => {
      const wape = model.metrics.wape[horizonIndex];
      const bias = model.metrics.bias[horizonIndex];
      const coverage = model.metrics.coverage[horizonIndex];
      const baselineImprovement =
        model.metrics.baselineImprovement[horizonIndex];

      if (
        wape === undefined ||
        bias === undefined ||
        coverage === undefined ||
        baselineImprovement === undefined
      ) {
        throw new Error(`Incomplete metric evidence for ${model.id}`);
      }

      return {
        rank: null,
        modelId: model.id,
        modelName: model.name,
        family: model.family,
        lifecycleStatus: model.lifecycleStatus,
        evidenceStatus: model.evidenceStatus,
        description: model.description,
        horizon: filters.horizon,
        segmentId: segment.id,
        segmentName: segment.name,
        wape: round(wape * segment.wapeMultiplier),
        bias: round(bias * segment.biasMultiplier),
        coverage: round(clamp(coverage + segment.coverageDelta, 0, 1), 2),
        baselineImprovement: round(
          baselineImprovement + segment.improvementDelta,
        ),
        lastEvaluatedAt: model.lastEvaluatedAt,
      } satisfies LeaderboardRow;
    });

    const rows = rowsWithoutRank
      .sort((left, right) => {
        if (left.evidenceStatus !== right.evidenceStatus) {
          return left.evidenceStatus === "sufficient" ? -1 : 1;
        }
        return left.wape - right.wape;
      })
      .map((row, index) => ({
        ...row,
        rank: row.evidenceStatus === "sufficient" ? index + 1 : null,
      }));

    return {
      datasetKind: fixture.metadata.datasetKind,
      fixtureVersion: fixture.metadata.fixtureVersion,
      horizon: filters.horizon,
      segmentId: segment.id,
      segmentName: segment.name,
      rows,
    };
  }

  async getModel(modelId: string, filters: LeaderboardFilters) {
    const result = await this.getLeaderboard(filters);
    return result.rows.find((row) => row.modelId === modelId) ?? null;
  }
}
