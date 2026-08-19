import fixtureJson from "../fixtures/forecastlab_demo_v1.json";
import forecastFixtureJson from "../fixtures/forecastlab_forecasts_demo_v1.json";
import {
  forecastFixtureSchema,
  type ForecastFilters,
  type ForecastOptions,
  type ForecastResult,
} from "../types/forecasts";
import {
  leaderboardFixtureSchema,
  type LeaderboardFilters,
  type LeaderboardResult,
  type LeaderboardRow,
} from "../types/leaderboard";
import type { ForecastLabDataSource } from "./dataSource";

const fixture = leaderboardFixtureSchema.parse(fixtureJson);
const forecastFixture = forecastFixtureSchema.parse(forecastFixtureJson);

const round = (value: number, digits = 1) => Number(value.toFixed(digits));
const clamp = (value: number, minimum: number, maximum: number) =>
  Math.min(maximum, Math.max(minimum, value));

export class FixtureDataSource implements ForecastLabDataSource {
  async getForecastOptions(): Promise<ForecastOptions> {
    return {
      runs: forecastFixture.runs.map(({ id, label, origin }) => ({
        id,
        label,
        origin,
      })),
      entities: forecastFixture.entities,
      models: forecastFixture.models,
      horizons: [1, 2, 3, 4, 5, 6, 7],
      exceptionStates: ["clear", "watch", "blocked"],
    };
  }

  async getForecasts(filters: ForecastFilters): Promise<ForecastResult> {
    const run = forecastFixture.runs.find(({ id }) => id === filters.runId);
    const entity = forecastFixture.entities.find(
      ({ id }) => id === filters.entityId,
    );
    const model = forecastFixture.models.find(
      ({ id }) => id === filters.modelId,
    );
    if (!run) throw new Error(`Unknown demo forecast run: ${filters.runId}`);
    if (!entity) throw new Error(`Unknown demo entity: ${filters.entityId}`);
    if (!model)
      throw new Error(`Unknown demo forecast model: ${filters.modelId}`);

    const rows = forecastFixture.rows.filter(
      (row) =>
        row.runId === filters.runId &&
        row.entityId === filters.entityId &&
        row.modelId === filters.modelId &&
        (filters.horizon === null || row.horizon === filters.horizon) &&
        (filters.exceptionState === "all" ||
          row.exceptionState === filters.exceptionState),
    );

    return {
      datasetKind: forecastFixture.metadata.datasetKind,
      fixtureVersion: forecastFixture.metadata.fixtureVersion,
      run: {
        id: run.id,
        label: run.label,
        origin: run.origin,
        publicationStatus: run.publicationStatus,
      },
      entity,
      model,
      rows,
      provenance: run.provenance,
    };
  }

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
