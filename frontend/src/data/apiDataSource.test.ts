import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiDataSource } from "./apiDataSource";

const options = {
  runs: [{ id: "run-1", label: "Published run", origin: "2026-08-18" }],
  entities: [
    {
      id: '{"store_nbr":1}',
      name: "store_nbr 1",
      hierarchyNode: '{"store_nbr":1}',
      hierarchyLevel: "store_day",
    },
  ],
  models: [{ id: "model-1", name: "XGBoost" }],
  horizons: [1, 7],
  exceptionStates: ["clear", "watch", "blocked"],
};

const result = {
  datasetKind: "live",
  run: {
    id: "run-1",
    label: "Published run",
    origin: "2026-08-18",
    publicationStatus: "published",
  },
  entity: options.entities[0],
  model: options.models[0],
  rows: [
    {
      runId: "run-1",
      entityId: '{"store_nbr":1}',
      modelId: "model-1",
      targetDate: "2026-08-19",
      horizon: 1,
      actual: null,
      p10: 10,
      p50: 12,
      p90: 15,
      statisticalForecast: 12,
      publishedForecast: 13,
      strategy: "entity_model",
      exceptionState: "clear",
    },
  ],
  provenance: {
    contractName: "contract-1",
    contractHash: "hash-1",
    modelRunId: "model-run-1",
    calibrationRunId: "calibration-1",
    reconciliationRunId: "reconciliation-1",
    hierarchyVersion: "hierarchy-1",
    featureVersion: "features-1",
    featureAvailabilityHash: "availability-1",
    dataCutoff: "2026-08-18T00:00:00Z",
    codeSha: "abc123",
    publicationVersion: "1",
  },
};

describe("ApiDataSource forecast contract", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("validates options and sends canonical server-side filters", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(options)))
      .mockResolvedValueOnce(new Response(JSON.stringify(result)));
    vi.stubGlobal("fetch", fetchMock);
    const source = new ApiDataSource("https://forecast.example");

    await expect(source.getForecastOptions("run-1")).resolves.toEqual(options);
    await expect(
      source.getForecasts({
        runId: "run-1",
        entityId: '{"store_nbr":1}',
        modelId: "model-1",
        horizon: 7,
        exceptionState: "watch",
      }),
    ).resolves.toEqual(result);

    const optionsUrl = new URL(String(fetchMock.mock.calls[0]?.[0]));
    expect(optionsUrl.searchParams.get("run_id")).toBe("run-1");

    const url = new URL(String(fetchMock.mock.calls[1]?.[0]));
    expect(url.pathname).toBe("/v1/forecasts");
    expect(Object.fromEntries(url.searchParams)).toEqual({
      run_id: "run-1",
      entity_id: '{"store_nbr":1}',
      model_id: "model-1",
      horizon: "7",
      exception_state: "watch",
    });
  });

  it("rejects malformed or unordered live forecast evidence", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            ...result,
            rows: [{ ...result.rows[0], p10: 20, p50: 12 }],
          }),
        ),
      ),
    );

    await expect(
      new ApiDataSource("").getForecasts({
        runId: "run-1",
        entityId: '{"store_nbr":1}',
        modelId: "model-1",
        horizon: null,
        exceptionState: "all",
      }),
    ).rejects.toThrow("Forecast quantiles must be ordered");
  });

  it("includes the server request ID in actionable errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("failed", {
          status: 500,
          headers: { "x-request-id": "request-123" },
        }),
      ),
    );

    await expect(new ApiDataSource("").getForecastOptions()).rejects.toThrow(
      "Forecast options request failed (500) · request request-123",
    );
  });

  it("loads typed live leaderboard options and nullable interval evidence", async () => {
    const leaderboardOptions = {
      horizons: [7],
      segments: [{ id: "all", name: "All entities" }],
    };
    const leaderboard = {
      datasetKind: "live",
      horizon: 7,
      segmentId: "all",
      segmentName: "All entities",
      rows: [
        {
          rank: 1,
          modelId: "model-1",
          modelName: "Model 1",
          family: "xgboost",
          lifecycleStatus: "champion",
          evidenceStatus: "sufficient",
          description: "Latest rolling-origin evidence.",
          horizon: 7,
          segmentId: "all",
          segmentName: "All entities",
          wape: 12,
          bias: -1,
          coverage: null,
          baselineImprovement: 5,
          lastEvaluatedAt: "2026-08-18T00:05:00Z",
        },
      ],
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(leaderboardOptions)))
      .mockResolvedValueOnce(new Response(JSON.stringify(leaderboard)));
    vi.stubGlobal("fetch", fetchMock);
    const source = new ApiDataSource("");

    await expect(source.getLeaderboardOptions()).resolves.toEqual(
      leaderboardOptions,
    );
    await expect(
      source.getLeaderboard({ horizon: 7, segmentId: "all" }),
    ).resolves.toEqual(leaderboard);
  });
});
