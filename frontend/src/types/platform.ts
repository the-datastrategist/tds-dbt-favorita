import { z } from "zod";

const pipelineStageSchema = z.object({
  name: z.string().min(1),
  position: z.number().int().positive(),
  status: z.string().min(1),
  inputRows: z.number().int().nonnegative(),
  outputRows: z.number().int().nonnegative(),
  durationSeconds: z.number().nonnegative().nullable(),
  retryState: z.string().min(1),
  errorMessage: z.string().nullable(),
});

const pipelineGateSchema = z.object({
  name: z.string().min(1),
  severity: z.string().min(1),
  passed: z.boolean(),
  observedValue: z.number().nullable(),
  thresholdValue: z.number().nullable(),
});

const pipelineRunSchema = z.object({
  runId: z.string().min(1),
  contractName: z.string().min(1),
  origin: z.iso.date(),
  status: z.string().min(1),
  healthStatus: z.string().min(1),
  startedAt: z.iso.datetime({ offset: true }),
  finishedAt: z.iso.datetime({ offset: true }).nullable(),
  candidateCount: z.number().int().nonnegative().nullable(),
  eligibleCount: z.number().int().nonnegative().nullable(),
  outputCount: z.number().int().nonnegative(),
  horizonCount: z.number().int().nonnegative(),
  missingQuantileCount: z.number().int().nonnegative(),
  stages: z.array(pipelineStageSchema),
  gates: z.array(pipelineGateSchema),
});

export const pipelineRunsSchema = z.object({
  datasetKind: z.enum(["synthetic", "live"]),
  fixtureVersion: z.string().optional(),
  runs: z.array(pipelineRunSchema),
});

const hierarchyLevelSchema = z.object({
  name: z.string().min(1),
  position: z.number().int().nonnegative(),
  nodeCount: z.number().int().nonnegative(),
});

const hierarchyNodeSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  level: z.string().min(1),
  levelPosition: z.number().int().nonnegative(),
  parentId: z.string().nullable(),
  baseP50: z.number().nonnegative().nullable(),
  reconciledP50: z.number().nonnegative().nullable(),
  delta: z.number().nullable(),
});

const reconciliationGateSchema = z.object({
  name: z.string().min(1),
  passed: z.boolean(),
  violationCount: z.number().int().nonnegative(),
});

export const hierarchySchema = z.object({
  datasetKind: z.enum(["synthetic", "live"]),
  fixtureVersion: z.string().optional(),
  hierarchyName: z.string().min(1),
  hierarchyVersion: z.string().min(1),
  reconciliationRunId: z.string().min(1),
  forecastRunId: z.string().min(1),
  method: z.string().min(1),
  status: z.string().min(1),
  tolerance: z.number().nonnegative(),
  nodeCount: z.number().int().nonnegative(),
  edgeCount: z.number().int().nonnegative(),
  levels: z.array(hierarchyLevelSchema),
  nodes: z.array(hierarchyNodeSchema),
  gates: z.array(reconciliationGateSchema),
});

export type PipelineRuns = z.infer<typeof pipelineRunsSchema>;
export type PipelineRun = z.infer<typeof pipelineRunSchema>;
export type HierarchySnapshot = z.infer<typeof hierarchySchema>;
