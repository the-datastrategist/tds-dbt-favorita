import { z } from "zod";

const forecastRowSchema = z
  .object({
    runId: z.string().startsWith("demo_"),
    entityId: z.string().startsWith("demo_"),
    modelId: z.string().startsWith("demo_"),
    targetDate: z.iso.date(),
    horizon: z.number().int().min(1).max(7),
    actual: z.number().nonnegative().nullable(),
    p10: z.number().nonnegative(),
    p50: z.number().nonnegative(),
    p90: z.number().nonnegative(),
    statisticalForecast: z.number().nonnegative(),
    publishedForecast: z.number().nonnegative(),
    strategy: z.string().min(1),
    exceptionState: z.enum(["clear", "watch", "blocked"]),
  })
  .refine(({ p10, p50, p90 }) => p10 <= p50 && p50 <= p90, {
    message: "Forecast quantiles must be ordered",
  });

const provenanceSchema = z.object({
  contractName: z.string(),
  contractHash: z.string(),
  modelRunId: z.string(),
  calibrationRunId: z.string(),
  reconciliationRunId: z.string(),
  hierarchyVersion: z.string(),
  featureVersion: z.string(),
  featureAvailabilityHash: z.string(),
  dataCutoff: z.iso.datetime(),
  codeSha: z.string(),
  publicationVersion: z.string(),
});

export const forecastFixtureSchema = z.object({
  metadata: z.object({
    datasetKind: z.literal("synthetic"),
    fixtureVersion: z.string().startsWith("forecastlab_forecasts_demo_"),
    generatedAt: z.iso.datetime(),
    description: z.string(),
  }),
  runs: z.array(
    z.object({
      id: z.string().startsWith("demo_"),
      label: z.string(),
      origin: z.iso.date(),
      publicationStatus: z.enum(["draft", "published", "superseded"]),
      provenance: provenanceSchema,
    }),
  ),
  entities: z.array(
    z.object({
      id: z.string().startsWith("demo_"),
      name: z.string(),
      hierarchyNode: z.string(),
      hierarchyLevel: z.string(),
    }),
  ),
  models: z.array(
    z.object({ id: z.string().startsWith("demo_"), name: z.string() }),
  ),
  rows: z.array(forecastRowSchema),
});

const forecastOptionSchema = z.object({
  runs: z.array(
    z.object({
      id: z.string().min(1),
      label: z.string(),
      origin: z.iso.date(),
    }),
  ),
  entities: z.array(
    z.object({
      id: z.string().min(1),
      name: z.string(),
      hierarchyNode: z.string(),
      hierarchyLevel: z.string(),
    }),
  ),
  models: z.array(z.object({ id: z.string().min(1), name: z.string() })),
  horizons: z.array(z.number().int().positive()),
  exceptionStates: z.array(z.enum(["clear", "watch", "blocked"])),
});

export const forecastApiResultSchema = z.object({
  datasetKind: z.literal("live"),
  run: z.object({
    id: z.string().min(1),
    label: z.string(),
    origin: z.iso.date(),
    publicationStatus: z.enum(["draft", "published", "superseded"]),
  }),
  entity: forecastOptionSchema.shape.entities.element,
  model: forecastOptionSchema.shape.models.element,
  rows: z.array(
    forecastRowSchema.safeExtend({
      runId: z.string().min(1),
      entityId: z.string().min(1),
      modelId: z.string().min(1),
      horizon: z.number().int().positive(),
    }),
  ),
  provenance: provenanceSchema,
  nextPageToken: z.string().nullable().optional(),
});

export const forecastApiOptionsSchema = forecastOptionSchema;

export type ForecastRow = z.infer<typeof forecastRowSchema>;
export type ForecastProvenance = z.infer<typeof provenanceSchema>;

export interface ForecastFilters {
  runId: string;
  entityId: string;
  horizon: number | null;
  modelId: string;
  exceptionState: "all" | ForecastRow["exceptionState"];
}

export interface ForecastOptions {
  runs: Array<{ id: string; label: string; origin: string }>;
  entities: Array<{
    id: string;
    name: string;
    hierarchyNode: string;
    hierarchyLevel: string;
  }>;
  models: Array<{ id: string; name: string }>;
  horizons: number[];
  exceptionStates: Array<ForecastRow["exceptionState"]>;
}

export interface ForecastResult {
  datasetKind: "synthetic" | "live";
  fixtureVersion?: string;
  run: {
    id: string;
    label: string;
    origin: string;
    publicationStatus: "draft" | "published" | "superseded";
  };
  entity: ForecastOptions["entities"][number];
  model: ForecastOptions["models"][number];
  rows: ForecastRow[];
  provenance: ForecastProvenance;
  nextPageToken?: string | null;
}
