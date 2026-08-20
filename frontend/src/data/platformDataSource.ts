import {
  hierarchySchema,
  pipelineRunsSchema,
  type HierarchySnapshot,
  type PipelineRuns,
} from "../types/platform";

export interface PlatformDataSource {
  pipelineRuns(): Promise<PipelineRuns>;
  hierarchy(version?: string): Promise<HierarchySnapshot>;
}

const pipelineFixture = pipelineRunsSchema.parse({
  datasetKind: "synthetic",
  fixtureVersion: "forecastlab_platform_demo_v1",
  runs: [
    {
      runId: "demo_pipeline_2026_08_18",
      contractName: "store_daily_demand_h7",
      origin: "2026-08-18",
      status: "draft",
      healthStatus: "healthy",
      startedAt: "2026-08-18T13:00:00Z",
      finishedAt: "2026-08-18T13:04:42Z",
      candidateCount: 55,
      eligibleCount: 55,
      outputCount: 55,
      horizonCount: 1,
      missingQuantileCount: 0,
      stages: [
        {
          name: "eligibility",
          position: 1,
          status: "completed",
          inputRows: 55,
          outputRows: 55,
          durationSeconds: 22,
          retryState: "idempotent",
          errorMessage: null,
        },
        {
          name: "champion scoring",
          position: 2,
          status: "completed",
          inputRows: 55,
          outputRows: 55,
          durationSeconds: 91,
          retryState: "idempotent",
          errorMessage: null,
        },
        {
          name: "calibration",
          position: 3,
          status: "completed",
          inputRows: 55,
          outputRows: 55,
          durationSeconds: 34,
          retryState: "idempotent",
          errorMessage: null,
        },
        {
          name: "reconciliation",
          position: 4,
          status: "completed",
          inputRows: 55,
          outputRows: 55,
          durationSeconds: 68,
          retryState: "idempotent",
          errorMessage: null,
        },
        {
          name: "draft persistence",
          position: 5,
          status: "completed",
          inputRows: 55,
          outputRows: 55,
          durationSeconds: 67,
          retryState: "idempotent",
          errorMessage: null,
        },
      ],
      gates: [
        {
          name: "output_cardinality",
          severity: "blocking",
          passed: true,
          observedValue: 55,
          thresholdValue: 55,
        },
        {
          name: "horizon_coverage",
          severity: "blocking",
          passed: true,
          observedValue: 1,
          thresholdValue: 1,
        },
        {
          name: "quantile_completeness",
          severity: "blocking",
          passed: true,
          observedValue: 0,
          thresholdValue: 0,
        },
        {
          name: "reconciliation_coherence",
          severity: "blocking",
          passed: true,
          observedValue: 0,
          thresholdValue: 0,
        },
      ],
    },
  ],
});

const hierarchyFixture = hierarchySchema.parse({
  datasetKind: "synthetic",
  fixtureVersion: "forecastlab_hierarchy_demo_v1",
  hierarchyName: "favorita_store",
  hierarchyVersion: "demo_company_city_store_v1",
  reconciliationRunId: "demo_reconciliation_2026_08_18",
  forecastRunId: "demo_pipeline_2026_08_18",
  method: "bottom_up",
  status: "completed",
  tolerance: 0.001,
  nodeCount: 5,
  edgeCount: 4,
  levels: [
    { name: "company", position: 0, nodeCount: 1 },
    { name: "city", position: 1, nodeCount: 2 },
    { name: "store", position: 2, nodeCount: 2 },
  ],
  nodes: [
    {
      id: "company",
      label: "Favorita",
      level: "company",
      levelPosition: 0,
      parentId: null,
      baseP50: 615,
      reconciledP50: 600,
      delta: -15,
    },
    {
      id: "quito",
      label: "Quito",
      level: "city",
      levelPosition: 1,
      parentId: "company",
      baseP50: 420,
      reconciledP50: 412,
      delta: -8,
    },
    {
      id: "guayaquil",
      label: "Guayaquil",
      level: "city",
      levelPosition: 1,
      parentId: "company",
      baseP50: 195,
      reconciledP50: 188,
      delta: -7,
    },
    {
      id: "store-01",
      label: "Store 01",
      level: "store",
      levelPosition: 2,
      parentId: "quito",
      baseP50: 420,
      reconciledP50: 412,
      delta: -8,
    },
    {
      id: "store-03",
      label: "Store 03",
      level: "store",
      levelPosition: 2,
      parentId: "guayaquil",
      baseP50: 195,
      reconciledP50: 188,
      delta: -7,
    },
  ],
  gates: [
    { name: "Exactly one parent", passed: true, violationCount: 0 },
    { name: "Acyclic hierarchy", passed: true, violationCount: 0 },
    { name: "Coherent child totals", passed: true, violationCount: 0 },
    { name: "All quantiles reconciled", passed: true, violationCount: 0 },
    { name: "Ordered quantiles", passed: true, violationCount: 0 },
  ],
});

class FixturePlatformDataSource implements PlatformDataSource {
  async pipelineRuns() {
    return pipelineFixture;
  }

  async hierarchy() {
    return hierarchyFixture;
  }
}

class ApiPlatformDataSource implements PlatformDataSource {
  constructor(private readonly baseUrl: string) {}

  private async request(path: string) {
    const response = await fetch(`${this.baseUrl}${path}`);
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      const requestId = response.headers.get("x-request-id");
      throw new Error(
        `${payload?.message ?? "Platform evidence request failed"} (${response.status})${requestId ? ` · request ${requestId}` : ""}`,
      );
    }
    return response.json();
  }

  async pipelineRuns() {
    return pipelineRunsSchema.parse(await this.request("/v1/pipeline-runs"));
  }

  async hierarchy(version = "current") {
    return hierarchySchema.parse(
      await this.request(`/v1/hierarchies/${encodeURIComponent(version)}`),
    );
  }
}

export const platformDataSource: PlatformDataSource =
  import.meta.env.VITE_DATA_MODE === "api"
    ? new ApiPlatformDataSource(import.meta.env.VITE_API_BASE_URL ?? "")
    : new FixturePlatformDataSource();
