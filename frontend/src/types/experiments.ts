import { z } from "zod";

const metricSchema = z.object({
  wape: z.number().nonnegative(),
  bias: z.number(),
  coverage: z.number().min(0).max(1),
});

const configurationValueSchema = z.union([z.string(), z.number(), z.boolean()]);

export const experimentRunSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  modelId: z.string().min(1),
  modelName: z.string().min(1),
  modelFamily: z.string().min(1),
  featureVersion: z.string().min(1),
  status: z.enum(["completed", "failed"]),
  createdAt: z.iso.datetime(),
  completedAt: z.iso.datetime().nullable(),
  runtimeMinutes: z.number().nonnegative(),
  comparable: z.boolean(),
  summary: metricSchema.nullable(),
  configuration: z.record(z.string(), configurationValueSchema),
  horizons: z.array(
    metricSchema.extend({ horizon: z.number().int().min(1).max(7) }),
  ),
  segments: z.array(
    metricSchema.extend({
      segmentId: z.string().min(1),
      segmentName: z.string().min(1),
    }),
  ),
  rollingOrigins: z.array(metricSchema.extend({ origin: z.iso.date() })),
  statisticalEvidence: z
    .object({
      referenceRunId: z.string().min(1),
      deltaWapePp: z.number(),
      confidenceLevel: z.number().min(0).max(1),
      ciLower: z.number(),
      ciUpper: z.number(),
      pValue: z.number().min(0).max(1),
      conclusion: z.enum(["meaningful", "inconclusive", "worse"]),
    })
    .nullable(),
  forecastLink: z
    .object({
      runId: z.string().min(1),
      entityId: z.string().min(1),
      modelId: z.string().min(1),
      exceptionState: z.enum(["all", "clear", "watch", "blocked"]),
    })
    .nullable(),
});

export const experimentFixtureSchema = z.object({
  metadata: z.object({
    datasetKind: z.literal("synthetic"),
    fixtureVersion: z.string().startsWith("forecastlab_experiments_demo_"),
    generatedAt: z.iso.datetime(),
    description: z.string(),
  }),
  runs: z.array(experimentRunSchema).min(2),
});

export const experimentOptionsSchema = z.object({
  runs: z.array(
    z.object({
      id: z.string().min(1),
      label: z.string().min(1),
      comparable: z.boolean(),
    }),
  ),
  models: z.array(z.object({ id: z.string().min(1), name: z.string().min(1) })),
  modelFamilies: z.array(z.string()),
  featureVersions: z.array(z.string()),
  statuses: z.array(z.enum(["completed", "failed"])),
  horizons: z.array(z.number().int().positive()),
});

export const experimentListResultSchema = z.object({
  datasetKind: z.enum(["synthetic", "live"]),
  fixtureVersion: z.string().optional(),
  runs: z.array(experimentRunSchema),
});

export const experimentComparisonResultSchema =
  experimentListResultSchema.extend({ missingRunIds: z.array(z.string()) });

export type ExperimentRun = z.infer<typeof experimentRunSchema>;
export type ExperimentMetric = "wape" | "bias" | "coverage";

export interface ExperimentFilters {
  modelId: string;
  modelFamily: string;
  featureVersion: string;
  status: "all" | ExperimentRun["status"];
  horizon: number | null;
}

export interface ExperimentOptions {
  runs: Array<{ id: string; label: string; comparable: boolean }>;
  models: Array<{ id: string; name: string }>;
  modelFamilies: string[];
  featureVersions: string[];
  statuses: Array<ExperimentRun["status"]>;
  horizons: number[];
}

export interface ExperimentListResult {
  datasetKind: "synthetic" | "live";
  fixtureVersion?: string;
  runs: ExperimentRun[];
}

export interface ExperimentComparisonResult {
  datasetKind: "synthetic" | "live";
  fixtureVersion?: string;
  runs: ExperimentRun[];
  missingRunIds: string[];
}
