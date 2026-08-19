import { z } from "zod";

const metricSchema = z.object({
  wape: z.number().nonnegative(),
  bias: z.number(),
  coverage: z.number().min(0).max(1),
});

const configurationValueSchema = z.union([z.string(), z.number(), z.boolean()]);

export const experimentRunSchema = z.object({
  id: z.string().startsWith("demo_experiment_"),
  label: z.string().min(1),
  modelId: z.string().startsWith("demo_model_"),
  modelName: z.string().min(1),
  modelFamily: z.string().min(1),
  featureVersion: z.string().min(1),
  status: z.enum(["completed", "failed"]),
  createdAt: z.iso.datetime(),
  completedAt: z.iso.datetime().nullable(),
  runtimeMinutes: z.number().positive(),
  comparable: z.boolean(),
  summary: metricSchema.nullable(),
  configuration: z.record(z.string(), configurationValueSchema),
  horizons: z.array(
    metricSchema.extend({ horizon: z.number().int().min(1).max(7) }),
  ),
  segments: z.array(
    metricSchema.extend({
      segmentId: z.string().startsWith("demo_"),
      segmentName: z.string().min(1),
    }),
  ),
  rollingOrigins: z.array(metricSchema.extend({ origin: z.iso.date() })),
  statisticalEvidence: z
    .object({
      referenceRunId: z.string().startsWith("demo_experiment_"),
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
      runId: z.string().startsWith("demo_run_"),
      entityId: z.string().startsWith("demo_"),
      modelId: z.string().startsWith("demo_model_"),
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
  datasetKind: "synthetic";
  fixtureVersion: string;
  runs: ExperimentRun[];
}

export interface ExperimentComparisonResult {
  datasetKind: "synthetic";
  fixtureVersion: string;
  runs: ExperimentRun[];
  missingRunIds: string[];
}
