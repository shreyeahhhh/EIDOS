import type { MissionFailureCause, MissionStatus, RunStatus, VerificationVerdict } from "./api/types";

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
