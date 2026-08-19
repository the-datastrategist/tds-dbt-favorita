import experimentFixture from "../fixtures/forecastlab_experiments_demo_v1.json";
import {
  ExperimentApiDataSource,
  ExperimentFixtureDataSource,
} from "./experimentDataSource";

describe("ExperimentFixtureDataSource", () => {
  const source = new ExperimentFixtureDataSource();

  it("filters run history by model, status, feature version, and horizon", async () => {
    const result = await source.list({
      modelId: "demo_model_global_xgboost",
      modelFamily: "Gradient boosted trees",
      featureVersion: "features_v12",
      status: "completed",
      horizon: 7,
    });

    expect(result.runs.map(({ id }) => id)).toEqual([
      "demo_experiment_xgb_global_v17",
    ]);
  });

  it("preserves requested comparison order and rejects failed evidence", async () => {
    const result = await source.compare([
      "demo_experiment_prophet_v08",
      "demo_experiment_xgb_global_v17",
      "demo_experiment_xgb_ablation_v04",
      "missing",
    ]);

    expect(result.runs.map(({ id }) => id)).toEqual([
      "demo_experiment_prophet_v08",
      "demo_experiment_xgb_global_v17",
    ]);
    expect(result.missingRunIds).toEqual([
      "demo_experiment_xgb_ablation_v04",
      "missing",
    ]);
  });

  it("ships rolling-origin and confidence evidence for scientific comparison", async () => {
    const result = await source.compare([
      "demo_experiment_xgb_global_v17",
      "demo_experiment_xgb_global_v16",
    ]);

    expect(result.runs[0]?.rollingOrigins).toHaveLength(5);
    expect(result.runs[0]?.statisticalEvidence).toMatchObject({
      confidenceLevel: 0.95,
      conclusion: "meaningful",
    });
  });

  it("contains no public-demo secrets or infrastructure identifiers", () => {
    const serialized = JSON.stringify(experimentFixture);
    expect(serialized).not.toMatch(/gs:\/\//i);
    expect(serialized).not.toMatch(/https?:\/\//i);
    expect(serialized).not.toMatch(/[\w.+-]+@[\w.-]+\.[a-z]{2,}/i);
    expect(serialized).not.toMatch(/(?:api[_-]?key|password|secret|token)/i);
  });
});

describe("ExperimentApiDataSource", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sends canonical filters and repeated comparison run IDs", async () => {
    const fixtureSource = new ExperimentFixtureDataSource();
    const options = await fixtureSource.getOptions();
    const list = await fixtureSource.list({
      modelId: "demo_model_global_xgboost",
      modelFamily: "Gradient boosted trees",
      featureVersion: "features_v12",
      status: "completed",
      horizon: 7,
    });
    const comparison = await fixtureSource.compare([
      "demo_experiment_xgb_global_v17",
      "demo_experiment_xgb_global_v16",
    ]);
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(options)))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ...list, datasetKind: "live" })),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ...comparison, datasetKind: "live" })),
      );
    vi.stubGlobal("fetch", fetchMock);
    const source = new ExperimentApiDataSource("https://forecast.example");

    await source.getOptions();
    await source.list({
      modelId: "demo_model_global_xgboost",
      modelFamily: "Gradient boosted trees",
      featureVersion: "features_v12",
      status: "completed",
      horizon: 7,
    });
    await source.compare([
      "demo_experiment_xgb_global_v17",
      "demo_experiment_xgb_global_v16",
    ]);

    const listUrl = new URL(String(fetchMock.mock.calls[1]?.[0]));
    expect(Object.fromEntries(listUrl.searchParams)).toEqual({
      model_id: "demo_model_global_xgboost",
      model_family: "Gradient boosted trees",
      feature_version: "features_v12",
      status: "completed",
      horizon: "7",
    });
    const compareUrl = new URL(String(fetchMock.mock.calls[2]?.[0]));
    expect(compareUrl.searchParams.getAll("runs")).toEqual([
      "demo_experiment_xgb_global_v17",
      "demo_experiment_xgb_global_v16",
    ]);
  });

  it("includes the request ID in experiment API errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("failed", {
          status: 500,
          headers: { "x-request-id": "experiment-request-1" },
        }),
      ),
    );

    await expect(new ExperimentApiDataSource("").getOptions()).rejects.toThrow(
      "Experiment request failed (500) · request experiment-request-1",
    );
  });
});
