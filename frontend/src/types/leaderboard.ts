import { z } from "zod";

const sevenMetrics = z.array(z.number()).length(7);

export const leaderboardFixtureSchema = z.object({
  metadata: z.object({
    datasetKind: z.literal("synthetic"),
    fixtureVersion: z.string().startsWith("forecastlab_demo_"),
    generatedAt: z.iso.datetime(),
    description: z.string(),
  }),
  horizons: z.array(z.number().int().min(1)).length(7),
  segments: z.array(
    z.object({
      id: z.string().startsWith("demo_"),
      name: z.string(),
      wapeMultiplier: z.number().positive(),
      biasMultiplier: z.number().positive(),
      coverageDelta: z.number(),
      improvementDelta: z.number(),
    }),
  ),
  models: z.array(
    z.object({
      id: z.string().startsWith("demo_"),
      name: z.string(),
      family: z.string(),
      lifecycleStatus: z.enum(["champion", "candidate", "baseline"]),
      evidenceStatus: z.enum(["sufficient", "insufficient"]),
      description: z.string(),
      lastEvaluatedAt: z.iso.datetime(),
      metrics: z.object({
        wape: sevenMetrics,
        bias: sevenMetrics,
        coverage: sevenMetrics,
        baselineImprovement: sevenMetrics,
      }),
    }),
  ),
});

export const leaderboardRowSchema = z.object({
  rank: z.number().int().positive().nullable(),
  modelId: z.string(),
  modelName: z.string(),
  family: z.string(),
  lifecycleStatus: z.enum(["champion", "candidate", "baseline"]),
  evidenceStatus: z.enum(["sufficient", "insufficient"]),
  description: z.string(),
  horizon: z.number().int().positive(),
  segmentId: z.string(),
  segmentName: z.string(),
  wape: z.number().nonnegative(),
  bias: z.number(),
  coverage: z.number().min(0).max(1).nullable(),
  baselineImprovement: z.number(),
  lastEvaluatedAt: z.iso.datetime(),
});

export const leaderboardResultSchema = z.object({
  datasetKind: z.enum(["synthetic", "live"]),
  fixtureVersion: z.string().optional(),
  horizon: z.number().int().positive(),
  segmentId: z.string(),
  segmentName: z.string(),
  rows: z.array(leaderboardRowSchema),
});

export type LeaderboardFixture = z.infer<typeof leaderboardFixtureSchema>;
export type LeaderboardRow = z.infer<typeof leaderboardRowSchema>;
export type LeaderboardResult = z.infer<typeof leaderboardResultSchema>;

export interface LeaderboardFilters {
  horizon: number;
  segmentId: string;
}

export interface LeaderboardOptions {
  horizons: number[];
  segments: Array<{ id: string; name: string }>;
}
