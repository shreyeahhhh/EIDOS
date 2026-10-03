import type { MissionFailureCause, MissionStatus, NodeStatus, PlanStepKind, RunStatus, VerificationVerdict } from "./api/types";

export type Tone = "neutral" | "info" | "success" | "warning" | "error";

/**
 * Human labels for the two lifecycles the backend keeps deliberately separate (`docs/13` section 6):
 * `run_status` is this API's own job lifecycle; `mission_status` is what the recorded log says the
 * mission came to. A "finished" run is not itself success — the mission's own status says that.
 */
export const RUN_STATUS_LABEL: Record<RunStatus, string> = {
  created: "Created",
  queued: "Queued",
  running: "Running",
  finished: "Finished",
  rejected: "Rejected",
  interrupted: "Interrupted",
  error: "Error",
};

export const RUN_STATUS_TONE: Record<RunStatus, Tone> = {
  created: "neutral",
  queued: "info",
  running: "info",
  finished: "neutral",
  rejected: "error",
  interrupted: "warning",
  error: "error",
};

export const MISSION_STATUS_LABEL: Record<MissionStatus, string> = {
  created: "Created",
  completed: "Completed",
  failed: "Failed",
  paused: "Paused",
};

export const MISSION_STATUS_TONE: Record<MissionStatus, Tone> = {
  created: "neutral",
  completed: "success",
  failed: "error",
  paused: "warning",
};

export const VERDICT_LABEL: Record<VerificationVerdict, string> = {
  pass: "Passed verification",
  fail: "Failed verification",
  inconclusive: "Verification inconclusive",
};

export const VERDICT_TONE: Record<VerificationVerdict, Tone> = {
  pass: "success",
  fail: "error",
  inconclusive: "warning",
};

/** A plan node's own settled state (`NodeResult.status`), distinct from the mission-level `MissionStatus` above — several nodes each carry one of these while the mission carries one of the other. */
export const NODE_STATUS_LABEL: Record<NodeStatus, string> = {
  succeeded: "Succeeded",
  failed: "Failed",
  no_result: "No result",
  verification_failed: "Failed verification",
  verification_inconclusive: "Inconclusive",
  skipped: "Skipped",
  not_reached: "Not reached",
  awaiting: "Awaiting",
};

const PLAN_STEP_KIND_LABEL: Record<Exclude<PlanStepKind, "agent">, string> = {
  ROUTE: "Route",
  VERIFY: "Verify",
  RETRY: "Retry",
  REPLAN: "Replan",
  HUMAN_APPROVAL: "Human approval",
  TERMINATE: "Terminate",
};

/** What a plan node is, in one short phrase: its capability if it is work, or its control-flow role otherwise. */
export function stepKindLabel(kind: PlanStepKind, capability: string | null): string {
  if (kind === "agent") return capability ? capability[0].toUpperCase() + capability.slice(1) : "Agent";
  return PLAN_STEP_KIND_LABEL[kind];
}

const FAILURE_CAUSE_LABEL: Record<MissionFailureCause, string> = {
  plan_rejected: "The plan was rejected before it could run",
  run_rejected: "No runnable strategy could be selected",
  execution_failed: "Execution failed",
  no_result: "The mission produced no result",
  verification_failed: "Verification failed",
  verification_inconclusive: "Verification was inconclusive",
};

export function failureCauseLabel(cause: MissionFailureCause): string {
  return FAILURE_CAUSE_LABEL[cause];
}

export function formatDateTime(iso: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(iso));
}
