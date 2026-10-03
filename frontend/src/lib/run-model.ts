import type { EventRecord, MissionFailureCause, MissionSummary, NodeStatus, PlanStepKind } from "./api/types";
import { failureCauseLabel, stepKindLabel, type Tone } from "./status";

/**
 * Everything the mission cockpit shows about a run is derived here from the recorded events alone — the same
 * log the backend replays — so a replay, a plan version and a step's state are never anything but what was
 * recorded. Nothing in this file invents a fact: a step with no recorded start is "pending", a plan the log
 * never generated does not exist, and a sentence only says what the event says.
 */

export type StepState = "pending" | "running" | "done" | "failed" | "unsure" | "skipped" | "waiting";

export interface PlanStepView {
  id: string;
  label: string;
  kind: PlanStepKind;
  capability: string | null;
  dependsOn: string[];
}

export interface PlanVersion {
  planId: string;
  version: number;
  /** Why this plan replaced the one before it, when the log recorded one. */
  replanReason: string | null;
  steps: PlanStepView[];
}

export type MomentKind = "created" | "plan" | "validated" | "rejected" | "started" | "settled" | "replan" | "completed" | "failed" | "paused" | "other";

/** One recorded event, as a point on the replay: what happened, in a plain sentence, and just enough structure to replay it. */
export interface Moment {
  index: number;
  sequence: number;
  at: string;
  /** Milliseconds since the first recorded event. */
  offsetMs: number;
  kind: MomentKind;
  tone: Tone;
  text: string;
  planId: string | null;
  stepId: string | null;
  status: NodeStatus | null;
  reason: string | null;
  durationMs: number | null;
  artifact: string | null;
  /** The recorded event's own type, for the technical view. */
  eventType: string;
}

export interface RunModel {
  plans: PlanVersion[];
  moments: Moment[];
}

export interface StepSnapshot {
  state: StepState;
  reason: string | null;
  durationMs: number | null;
  startedAt: string | null;
  settledAt: string | null;
  artifact: string | null;
}

export interface Snapshot {
  plan: PlanVersion | null;
  steps: Record<string, StepSnapshot>;
  moment: Moment | null;
  /** A terminal event (completed, failed, paused) has happened at or before this point. */
  ended: boolean;
}

const STATE_OF_STATUS: Record<NodeStatus, StepState> = {
  succeeded: "done",
  failed: "failed",
  no_result: "failed",
  verification_failed: "failed",
  verification_inconclusive: "unsure",
  skipped: "skipped",
  not_reached: "skipped",
  awaiting: "waiting",
};

export const STEP_STATE_LABEL: Record<StepState, string> = {
  pending: "Waiting its turn",
  running: "Working",
  done: "Done",
  failed: "Didn't work",
  unsure: "Unsure",
  skipped: "Skipped",
  waiting: "Waiting for a person",
};

export const STEP_STATE_TONE: Record<StepState, Tone> = {
  pending: "neutral",
  running: "info",
  done: "success",
  failed: "error",
  unsure: "warning",
  skipped: "neutral",
  waiting: "info",
};

/** The backend prefixes a recorded reason with its machine code ("execution_failed: the model call failed…"); a person reads only the sentence after it. */
export function plainReason(reason: string | null): string | null {
  if (reason === null) return null;
  return reason.replace(/^(plan_rejected|run_rejected|execution_failed|no_result|verification_failed|verification_inconclusive):\s*/, "").trim() || null;
}

function titleCase(screamingSnake: string): string {
  return screamingSnake
    .toLowerCase()
    .split("_")
    .map((word) => (word ? word[0].toUpperCase() + word.slice(1) : word))
    .join(" ");
}

function lower(text: string): string {
  return text ? text[0].toLowerCase() + text.slice(1) : text;
}

/** A sentence about a step that has just finished, in the user's words — never a score, only what the recorded status says. */
function settledSentence(label: string, kind: PlanStepKind, status: NodeStatus): { text: string; tone: Tone } {
  if (kind === "VERIFY") {
    if (status === "succeeded") return { text: "The answer passed its checks.", tone: "success" };
    if (status === "verification_inconclusive") return { text: "The checks couldn't confirm the answer either way.", tone: "warning" };
    if (status === "skipped" || status === "not_reached") return { text: "The checks were skipped, because an earlier step didn't work.", tone: "neutral" };
    return { text: "The answer failed its checks.", tone: "error" };
  }
  switch (status) {
    case "succeeded":
      return { text: `${label} finished.`, tone: "success" };
    case "failed":
      return { text: `${label} didn't work.`, tone: "error" };
    case "no_result":
      return { text: `${label} finished without producing anything.`, tone: "error" };
    case "verification_failed":
      return { text: `${label} failed its checks.`, tone: "error" };
    case "verification_inconclusive":
      return { text: `${label} couldn't be confirmed.`, tone: "warning" };
    case "skipped":
      return { text: `${label} was skipped.`, tone: "neutral" };
    case "not_reached":
      return { text: `${label} was never reached.`, tone: "neutral" };
    case "awaiting":
      return { text: `${label} is waiting for a person.`, tone: "info" };
  }
}

/** Builds the replayable model from a mission's recorded events (already in sequence order, as the backend returns them). */
export function buildRunModel(events: EventRecord[]): RunModel {
  const plans: PlanVersion[] = [];
  const moments: Moment[] = [];
  const labelByPlanStep = new Map<string, string>(); // `${planId}:${stepId}` -> label
  const kindByPlanStep = new Map<string, PlanStepKind>();
  const first = events.length > 0 ? new Date(events[0].event.occurred_at).getTime() : 0;

  const labelOf = (planId: string | null, stepId: string): string => (planId ? labelByPlanStep.get(`${planId}:${stepId}`) : undefined) ?? stepId;

  for (const record of events) {
    const { event, payload } = record;
    const base = {
      index: moments.length,
      sequence: event.sequence,
      at: event.occurred_at,
      offsetMs: Math.max(0, new Date(event.occurred_at).getTime() - first),
      planId: null as string | null,
      stepId: null as string | null,
      status: null as NodeStatus | null,
      reason: null as string | null,
      durationMs: null as number | null,
      artifact: null as string | null,
      eventType: event.type,
    };

    // `in` narrows on structural presence; the fallback member's `event_type: string` defeats equality narrowing (see execution-timeline.tsx).
    if ("plan" in payload) {
      const plan = payload.plan;
      const steps: PlanStepView[] = plan.steps.map((step) => {
        const label = stepKindLabel(step.kind, step.capability ?? null);
        labelByPlanStep.set(`${plan.plan_id}:${step.step_id}`, label);
        kindByPlanStep.set(`${plan.plan_id}:${step.step_id}`, step.kind);
        return { id: step.step_id, label, kind: step.kind, capability: step.capability ?? null, dependsOn: step.depends_on };
      });
      plans.push({ planId: plan.plan_id, version: plan.version, replanReason: plainReason(plan.replan_reason), steps });
      const text =
        plan.version <= 1
          ? `EIDOS drew up a plan with ${steps.length} ${steps.length === 1 ? "step" : "steps"}.`
          : `EIDOS drew up a new plan (version ${plan.version}) with ${steps.length} ${steps.length === 1 ? "step" : "steps"}.`;
      moments.push({ ...base, kind: "plan", tone: "info", text, planId: plan.plan_id });
    } else if ("step_id" in payload) {
      const label = labelOf(payload.plan_id, payload.step_id);
      moments.push({ ...base, kind: "started", tone: "info", text: `${label} started.`, planId: payload.plan_id, stepId: payload.step_id });
    } else if ("result" in payload) {
      const stepId = payload.result.step_id;
      const label = labelOf(payload.plan_id, stepId);
      const kind = kindByPlanStep.get(`${payload.plan_id}:${stepId}`) ?? payload.result.kind;
      const sentence = settledSentence(label, kind, payload.result.status);
      moments.push({
        ...base, kind: "settled", tone: sentence.tone, text: sentence.text, planId: payload.plan_id, stepId, status: payload.result.status,
        reason: payload.result.reason, durationMs: payload.duration_ms, artifact: payload.result.artifact,
      });
    } else if ("failed_plan_id" in payload) {
      moments.push({
        ...base, kind: "replan", tone: "warning", planId: payload.failed_plan_id, reason: plainReason(payload.reason),
        text: `That plan didn't work (${lower(failureCauseLabel(payload.cause))}). EIDOS is trying a different approach.`,
      });
    } else if ("verified" in payload) {
      moments.push({
        ...base, kind: "completed", tone: payload.verified ? "success" : "warning", planId: payload.plan_id,
        text: payload.verified ? "Finished — the checks passed." : "Finished, but the answer wasn't verified.",
      });
    } else if ("halt" in payload) {
      moments.push({ ...base, kind: "paused", tone: "warning", planId: payload.plan_id, text: "Paused: a person needs to review before it can go on." });
    } else if ("task_genome" in payload) {
      moments.push({ ...base, kind: "created", tone: "neutral", text: "Mission created." });
    } else if ("cause" in payload && "reason" in payload) {
      moments.push({
        ...base, kind: "failed", tone: "error", planId: payload.plan_id, reason: payload.reason,
        text: `It couldn't be completed: ${lower(failureCauseLabel(payload.cause as MissionFailureCause))}.`,
      });
    } else if ("stage" in payload) {
      moments.push({ ...base, kind: "rejected", tone: "error", planId: payload.plan_id, text: "The plan was rejected before it could run." });
    } else if (payload.event_type === "PLAN_COMPILED") {
      moments.push({ ...base, kind: "validated", tone: "neutral", text: "The plan passed EIDOS's checks and is ready to run." });
    } else {
      moments.push({ ...base, kind: "other", tone: "neutral", text: titleCase(payload.event_type) });
    }
  }
  return { plans, moments };
}

/** The plan versions generated at or before a point on the replay, oldest first. */
export function plansAt(model: RunModel, cursor: number): PlanVersion[] {
  const known = new Set<string>();
  for (const moment of model.moments) {
    if (moment.index > cursor) break;
    if (moment.kind === "plan" && moment.planId) known.add(moment.planId);
  }
  return model.plans.filter((plan) => known.has(plan.planId)).sort((a, b) => a.version - b.version);
}

/**
 * The state of the run at a point on the replay: which plan is in view, what each of its steps is doing, and the moment itself.
 * `cursor` is a moment index (-1: before anything happened). `planId` picks an earlier version to look at; by default the newest one generated by then.
 */
export function snapshotAt(model: RunModel, cursor: number, planId?: string | null): Snapshot {
  const available = plansAt(model, cursor);
  const plan = (planId ? available.find((candidate) => candidate.planId === planId) : undefined) ?? available[available.length - 1] ?? null;
  const steps: Record<string, StepSnapshot> = {};
  if (plan) {
    for (const step of plan.steps) {
      steps[step.id] = { state: "pending", reason: null, durationMs: null, startedAt: null, settledAt: null, artifact: null };
    }
  }
  let ended = false;
  for (const moment of model.moments) {
    if (moment.index > cursor) break;
    if (moment.kind === "completed" || moment.kind === "failed" || moment.kind === "paused") ended = true;
    if (!plan || moment.planId !== plan.planId || !moment.stepId || !steps[moment.stepId]) continue;
    if (moment.kind === "started") {
      steps[moment.stepId] = { ...steps[moment.stepId], state: "running", startedAt: moment.at };
    } else if (moment.kind === "settled" && moment.status) {
      steps[moment.stepId] = {
        ...steps[moment.stepId], state: STATE_OF_STATUS[moment.status], reason: moment.reason, durationMs: moment.durationMs, settledAt: moment.at, artifact: moment.artifact,
      };
    }
  }
  return { plan, steps, moment: cursor >= 0 ? (model.moments[cursor] ?? null) : null, ended };
}

/** "+1.2 s" — how far into the run a moment is. */
export function formatOffset(ms: number): string {
  if (ms < 1000) return `+${ms} ms`;
  if (ms < 60_000) return `+${(ms / 1000).toFixed(1)} s`;
  const minutes = Math.floor(ms / 60_000);
  const seconds = Math.round((ms % 60_000) / 1000);
  return `+${minutes} min ${seconds} s`;
}

export function formatDuration(ms: number | null): string | null {
  if (ms === null || ms <= 0) return null;
  if (ms < 1000) return `${ms} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
  return `${Math.floor(ms / 60_000)} min ${Math.round((ms % 60_000) / 1000)} s`;
}

export interface Story {
  headline: string;
  detail: string | null;
  tone: Tone;
}

/** The one-sentence account of where a mission stands, from its summary and what the log shows is going on. */
export function storyOf(mission: MissionSummary, model: RunModel): Story {
  const current = (() => {
    const open = new Map<string, Moment>();
    for (const moment of model.moments) {
      if (moment.kind === "started" && moment.stepId && moment.planId) open.set(`${moment.planId}:${moment.stepId}`, moment);
      if (moment.kind === "settled" && moment.stepId && moment.planId) open.delete(`${moment.planId}:${moment.stepId}`);
    }
    const last = [...open.values()].pop();
    return last ? last.text.replace(/ started\.$/, "") : null;
  })();

  switch (mission.run_status) {
    case "created":
      return { headline: "Ready when you are.", detail: "Start the mission and EIDOS will plan the work, do it, and check the result.", tone: "neutral" };
    case "queued":
      return { headline: "Waiting for its turn.", detail: "EIDOS will begin as soon as there is room to run it.", tone: "info" };
    case "running":
      return { headline: "EIDOS is working on it.", detail: current ? `Right now: ${current}.` : "It is planning the work.", tone: "info" };
    case "rejected":
      return { headline: "This mission couldn't start.", detail: mission.run_status_reason, tone: "error" };
    case "interrupted":
      return { headline: "The run was interrupted.", detail: mission.run_status_reason ?? "The server stopped before it finished. Nothing was made up to fill the gap.", tone: "warning" };
    case "error":
      return { headline: "Something went wrong on our side.", detail: mission.run_status_reason, tone: "error" };
    case "finished":
      break;
  }
  switch (mission.mission_status) {
    case "completed":
      return mission.verified
        ? { headline: "Done — and the checks passed.", detail: "EIDOS finished the work. The checks confirm the answer is well-formed and that every source it cites exists.", tone: "success" }
        : { headline: "Finished, but not verified.", detail: "EIDOS completed the steps, but its checks didn't confirm the result, so treat it with care.", tone: "warning" };
    case "failed":
      // The recorded reason is shown once, where it matters (the step that failed, and the answer card); the story only says what kind of failure it was.
      return { headline: "It didn't work out.", detail: mission.failure_cause ? failureCauseLabel(mission.failure_cause) : null, tone: "error" };
    case "paused":
      return { headline: "Paused for review.", detail: mission.status_reason ?? "A person needs to look at this before it can go on.", tone: "warning" };
    default:
      return { headline: "Finished.", detail: null, tone: "neutral" };
  }
}
