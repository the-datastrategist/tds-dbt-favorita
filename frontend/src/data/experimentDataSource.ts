import fixtureJson from "../fixtures/forecastlab_experiments_demo_v1.json";
import {
  experimentFixtureSchema,
  type ExperimentComparisonResult,
  type ExperimentFilters,
  type ExperimentListResult,
  type ExperimentOptions,
  type ExperimentRun,
} from "../types/experiments";

const fixture = experimentFixtureSchema.parse(fixtureJson);

export class ExperimentFixtureDataSource {
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

export const experimentDataSource = new ExperimentFixtureDataSource();
