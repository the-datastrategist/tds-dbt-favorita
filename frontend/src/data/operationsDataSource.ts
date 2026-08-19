import {
  capabilitySchema,
  mutationResultSchema,
  operationSnapshotSchema,
  type Capabilities,
  type LifecycleIntent,
  type MutationResult,
  type OperationSnapshot,
} from "../types/operations";

export interface OperationsDataSource {
  capabilities(): Promise<Capabilities>;
  snapshot(): Promise<OperationSnapshot>;
  mutate(intent: LifecycleIntent): Promise<MutationResult>;
}

const fixture: OperationSnapshot = operationSnapshotSchema.parse({
  datasetKind: "synthetic",
  fixtureVersion: "forecastlab_operations_demo_v1",
  runs: [
    {
      runId: "demo_run_2026_08_18",
      origin: "2026-08-18",
      status: "published",
      modelName: "Global XGBoost v17",
      outputCount: 147,
      exceptionCount: 4,
      overrideCount: 2,
      approvalCount: 147,
      publicationVersion: 3,
      deliveryStatus: "delivered",
      fvaStatus: "comparable",
      plannerWapeFvaPoints: 0.3,
      totalWapeFvaPoints: 0.5,
      updatedAt: "2026-08-18T14:28:00Z",
      outputs: [
        {
          id: "demo_output_1",
          entityLabel: "Quito 01",
          targetDate: "2026-08-19",
          currentValue: 412,
          exceptionState: "clear",
        },
        {
          id: "demo_output_2",
          entityLabel: "Guayaquil 03",
          targetDate: "2026-08-20",
          currentValue: 188,
          exceptionState: "watch",
        },
      ],
    },
    {
      runId: "demo_run_2026_08_11",
      origin: "2026-08-11",
      status: "superseded",
      modelName: "Global XGBoost v16",
      outputCount: 147,
      exceptionCount: 7,
      overrideCount: 3,
      approvalCount: 147,
      publicationVersion: 2,
      deliveryStatus: "delivered",
      fvaStatus: "comparable",
      plannerWapeFvaPoints: -0.2,
      totalWapeFvaPoints: 0.1,
      updatedAt: "2026-08-12T09:10:00Z",
      outputs: [],
    },
  ],
});

class FixtureOperationsDataSource implements OperationsDataSource {
  async capabilities() {
    return { mutationsEnabled: false, actor: null, roles: ["viewer" as const] };
  }

  async snapshot() {
    return fixture;
  }

  async mutate(): Promise<MutationResult> {
    throw new Error(
      "Lifecycle actions are disabled in the synthetic public demo.",
    );
  }
}

class ApiOperationsDataSource implements OperationsDataSource {
  constructor(private readonly baseUrl: string) {}

  private async request(path: string, init?: RequestInit) {
    const response = await fetch(`${this.baseUrl}${path}`, init);
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      const requestId = response.headers.get("x-request-id");
      throw new Error(
        `${payload?.message ?? "Operations request failed"} (${response.status})${requestId ? ` · request ${requestId}` : ""}`,
      );
    }
    return response.json();
  }

  async capabilities() {
    return capabilitySchema.parse(await this.request("/v1/capabilities"));
  }

  async snapshot() {
    return operationSnapshotSchema.parse(await this.request("/v1/operations"));
  }

  async mutate(intent: LifecycleIntent) {
    const common = {
      reason_code: intent.reasonCode,
      comment: intent.comment,
      idempotency_key: intent.idempotencyKey,
    };
    let path: string;
    let body: Record<string, unknown>;
    if (intent.action === "override") {
      path = "/v1/overrides";
      body = {
        ...common,
        forecast_run_id: intent.runId,
        forecast_output_id: intent.outputId,
        override_value: intent.value,
      };
    } else if (intent.action === "approve") {
      path = `/v1/forecast-runs/${encodeURIComponent(intent.runId)}/approve`;
      body = common;
    } else if (intent.action === "publish") {
      path = `/v1/forecast-runs/${encodeURIComponent(intent.runId)}/publish`;
      body = {
        ...common,
        approval_idempotency_key: intent.approvalIdempotencyKey,
        publication_version: intent.publicationVersion,
        destination: "canonical_bigquery",
      };
    } else {
      path = `/v1/forecast-runs/${encodeURIComponent(intent.runId)}/${intent.action}`;
      body = {
        ...common,
        publication_version: intent.publicationVersion,
        prior_version: intent.priorVersion,
        destination: "canonical_bigquery",
      };
    }
    return mutationResultSchema.parse(
      await this.request(path, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      }),
    );
  }
}

export const operationsDataSource: OperationsDataSource =
  import.meta.env.VITE_DATA_MODE === "api"
    ? new ApiOperationsDataSource(import.meta.env.VITE_API_BASE_URL ?? "")
    : new FixtureOperationsDataSource();
