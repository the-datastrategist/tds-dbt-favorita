import fixtureJson from "../fixtures/forecastlab_experiments_demo_v1.json";
import {
  experimentComparisonResultSchema,
  experimentFixtureSchema,
  experimentListResultSchema,
  experimentOptionsSchema,
  type ExperimentComparisonResult,
  type ExperimentFilters,
  type ExperimentListResult,
  type ExperimentOptions,
  type ExperimentRun,
} from "../types/experiments";

export interface ExperimentDataSource {
  getOptions(): Promise<ExperimentOptions>;
  list(filters: ExperimentFilters): Promise<ExperimentListResult>;
  compare(runIds: string[]): Promise<ExperimentComparisonResult>;
}

const fixture = experimentFixtureSchema.parse(fixtureJson);

export class ExperimentFixtureDataSource implements ExperimentDataSource {
  async getOptions(): Promise<ExperimentOptions> {
    const unique = <T>(values: T[]) => [...new Set(values)];
    return {
      runs: fixture.runs.map(({ id, label, comparable }) => ({
        id,
        label,
        comparable,
      })),
      models: unique(fixture.runs.map(({ modelId }) => modelId)).map((id) => {
        const run = fixture.runs.find(({ modelId }) => modelId === id);
        return { id, name: run?.modelName.replace(/ v\d+.*$/, "") ?? id };
      }),
      modelFamilies: unique(fixture.runs.map(({ modelFamily }) => modelFamily)),
      featureVersions: unique(
        fixture.runs.map(({ featureVersion }) => featureVersion),
      ),
      statuses: ["completed", "failed"],
      horizons: [1, 2, 3, 4, 5, 6, 7],
    };
  }

  async list(filters: ExperimentFilters): Promise<ExperimentListResult> {
    const runs = fixture.runs.filter(
      (run) =>
        (!filters.modelId || run.modelId === filters.modelId) &&
        (!filters.modelFamily || run.modelFamily === filters.modelFamily) &&
        (!filters.featureVersion ||
          run.featureVersion === filters.featureVersion) &&
        (filters.status === "all" || run.status === filters.status) &&
        (filters.horizon === null ||
          run.horizons.some(({ horizon }) => horizon === filters.horizon)),
    );

    return {
      datasetKind: fixture.metadata.datasetKind,
      fixtureVersion: fixture.metadata.fixtureVersion,
      runs,
    };
  }

  async compare(runIds: string[]): Promise<ExperimentComparisonResult> {
    const uniqueRunIds = [...new Set(runIds)];
    const runs: ExperimentRun[] = [];
    uniqueRunIds.forEach((runId) => {
      const run = fixture.runs.find(({ id }) => id === runId);
      if (run?.comparable) runs.push(run);
    });
    const foundIds = new Set(runs.map(({ id }) => id));

    return {
      datasetKind: fixture.metadata.datasetKind,
      fixtureVersion: fixture.metadata.fixtureVersion,
      runs,
      missingRunIds: uniqueRunIds.filter((runId) => !foundIds.has(runId)),
    };
  }
}

export class ExperimentApiDataSource implements ExperimentDataSource {
  constructor(private readonly baseUrl: string) {}

  private async request(path: string) {
    const response = await fetch(`${this.baseUrl}${path}`);
    if (!response.ok) {
      const requestId = response.headers.get("x-request-id");
      throw new Error(
        `Experiment request failed (${response.status})${requestId ? ` · request ${requestId}` : ""}`,
      );
    }
    return response.json();
  }

  async getOptions(): Promise<ExperimentOptions> {
    return experimentOptionsSchema.parse(
      await this.request("/v1/experiments/options"),
    );
  }

  async list(filters: ExperimentFilters): Promise<ExperimentListResult> {
    const query = new URLSearchParams();
    if (filters.modelId) query.set("model_id", filters.modelId);
    if (filters.modelFamily) query.set("model_family", filters.modelFamily);
    if (filters.featureVersion)
      query.set("feature_version", filters.featureVersion);
    if (filters.status !== "all") query.set("status", filters.status);
    if (filters.horizon !== null) query.set("horizon", String(filters.horizon));
    return experimentListResultSchema.parse(
      await this.request(`/v1/experiments?${query}`),
    );
  }

  async compare(runIds: string[]): Promise<ExperimentComparisonResult> {
    const query = new URLSearchParams();
    runIds.forEach((runId) => query.append("runs", runId));
    return experimentComparisonResultSchema.parse(
      await this.request(`/v1/experiments/compare?${query}`),
    );
  }
}

export const createExperimentDataSource = (): ExperimentDataSource =>
  import.meta.env.VITE_DATA_MODE === "api"
    ? new ExperimentApiDataSource(import.meta.env.VITE_API_BASE_URL ?? "")
    : new ExperimentFixtureDataSource();
