import fixture from "../fixtures/forecastlab_demo_v1.json";
import { FixtureDataSource } from "./fixtureDataSource";

describe("FixtureDataSource", () => {
  const source = new FixtureDataSource();

  it("returns the supported horizons and synthetic segments", async () => {
    const options = await source.getLeaderboardOptions();

    expect(options.horizons).toEqual([1, 2, 3, 4, 5, 6, 7]);
    expect(options.segments).toHaveLength(4);
    expect(options.segments.every(({ id }) => id.startsWith("demo_"))).toBe(
      true,
    );
  });

  it("ranks sufficient evidence and leaves insufficient evidence unranked", async () => {
    const result = await source.getLeaderboard({
      horizon: 1,
      segmentId: "demo_all",
    });

    expect(result.datasetKind).toBe("synthetic");
    expect(result.rows[0]).toMatchObject({
      rank: 1,
      modelId: "demo_model_global_xgboost",
      lifecycleStatus: "champion",
    });
    expect(result.rows.at(-1)).toMatchObject({
      rank: null,
      evidenceStatus: "insufficient",
    });
  });

  it("applies deterministic segment adjustments", async () => {
    const all = await source.getLeaderboard({
      horizon: 3,
      segmentId: "demo_all",
    });
    const coastal = await source.getLeaderboard({
      horizon: 3,
      segmentId: "demo_coastal",
    });

    expect(coastal.rows[0]?.wape).not.toBe(all.rows[0]?.wape);
    expect(coastal.rows[0]?.segmentName).toBe("Coastal region");
  });

  it("rejects unsupported filters", async () => {
    await expect(
      source.getLeaderboard({ horizon: 9, segmentId: "demo_all" }),
    ).rejects.toThrow("Unsupported demo horizon");
    await expect(
      source.getLeaderboard({ horizon: 1, segmentId: "unknown" }),
    ).rejects.toThrow("Unknown demo segment");
  });

  it("contains no public-demo secret or customer identifiers", () => {
    const serialized = JSON.stringify(fixture);

    expect(serialized).not.toMatch(/gs:\/\//i);
    expect(serialized).not.toMatch(/https?:\/\//i);
    expect(serialized).not.toMatch(/[\w.+-]+@[\w.-]+\.[a-z]{2,}/i);
    expect(serialized).not.toMatch(
      /(?:api[_-]?key|password|secret|token|customer[_-]?id)/i,
    );
  });
});
