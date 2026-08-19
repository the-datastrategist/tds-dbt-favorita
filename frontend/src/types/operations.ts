import { z } from "zod";

export const operationOutputSchema = z.object({
  id: z.string().min(1),
  entityLabel: z.string().min(1),
  targetDate: z.iso.date(),
  currentValue: z.number().nonnegative(),
  exceptionState: z.enum(["clear", "watch", "blocked"]),
});

export const operationRunSchema = z.object({
  runId: z.string().min(1),
  origin: z.iso.date(),
  status: z.enum(["draft", "approved", "published", "superseded", "failed"]),
  modelName: z.string().min(1),
  outputCount: z.number().int().nonnegative(),
  exceptionCount: z.number().int().nonnegative(),
  overrideCount: z.number().int().nonnegative(),
  approvalCount: z.number().int().nonnegative(),
  publicationVersion: z.number().int().positive().nullable(),
  deliveryStatus: z.string().min(1),
  fvaStatus: z.string().min(1),
  plannerWapeFvaPoints: z.number().nullable(),
  totalWapeFvaPoints: z.number().nullable(),
  updatedAt: z.iso.datetime(),
  outputs: z.array(operationOutputSchema),
});

export const operationSnapshotSchema = z.object({
  datasetKind: z.enum(["synthetic", "live"]),
  fixtureVersion: z.string().optional(),
  runs: z.array(operationRunSchema),
});

export const capabilitySchema = z.object({
  mutationsEnabled: z.boolean(),
  actor: z.string().nullable(),
  roles: z.array(
    z.enum(["viewer", "planner", "approver", "publisher", "operator"]),
  ),
});

export const mutationResultSchema = z.object({
  action: z.string(),
  retry: z.boolean(),
  override_id: z.string().nullable().optional(),
  approval_count: z.number().nullable().optional(),
  publication_count: z.number().nullable().optional(),
  publication_version: z.number().nullable().optional(),
  publication_event_id: z.string().nullable().optional(),
});

export type OperationSnapshot = z.infer<typeof operationSnapshotSchema>;
export type OperationRun = z.infer<typeof operationRunSchema>;
export type Capabilities = z.infer<typeof capabilitySchema>;
export type MutationResult = z.infer<typeof mutationResultSchema>;
export type LifecycleAction =
  "override" | "approve" | "publish" | "supersede" | "rollback";

export interface LifecycleIntent {
  action: LifecycleAction;
  runId: string;
  outputId?: string;
  value?: number;
  reasonCode: string;
  comment: string;
  idempotencyKey: string;
  approvalIdempotencyKey?: string;
  publicationVersion?: number;
  priorVersion?: number;
}
