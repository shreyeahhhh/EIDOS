/** Minimal, realistically-shaped builders for component tests — never used outside `*.test.tsx`. */
import type { Counters, EventRecord, MissionEvent, NodeResult, PlanStepKind, StepRecord } from "./types";

let sequence = 0;

export function makeEvent(overrides: Partial<MissionEvent> = {}): MissionEvent {
  sequence += 1;
  return {
    event_id: `00000000-0000-0000-0000-${String(sequence).padStart(12, "0")}`,
    tenant_id: "00000000-0000-0000-0000-000000000001",
    mission_id: "00000000-0000-0000-0000-000000000002",
    sequence,
    occurred_at: "2026-09-27T07:00:00.000000Z",
    recorded_at: "2026-09-27T07:00:00.000000Z",
    type: "MISSION_CREATED",
    ...overrides,
  };
}

export function makeEventRecord(overrides: Partial<EventRecord> = {}): EventRecord {
  return {
    event: makeEvent(),
    payload: { event_type: "MISSION_CREATED" },
    ...overrides,
  };
}

export function makeStep(overrides: Partial<StepRecord> = {}): StepRecord {
  return {
    step_id: "step",
    kind: "agent" as PlanStepKind,
    capability: "research",
    depends_on: [],
    agent_id: null,
    started: false,
    result: null,
    dispatched: null,
    duration_ms: null,
    model_calls: [],
    tool_calls: [],
    retrievals: [],
    citations: [],
    verification: null,
    ...overrides,
  };
}

export function makeNodeResult(overrides: Partial<NodeResult> = {}): NodeResult {
  return { step_id: "step", kind: "agent" as PlanStepKind, status: "succeeded", artifact: null, reason: null, ...overrides };
}

export function makeCounters(overrides: Partial<Counters> = {}): Counters {
  return {
    agent_calls_used: 1,
    tool_calls_used: 0,
    retries_used: 0,
    replans_used: 0,
    tokens_used: 0,
    execution_time_used_ms: 0,
    ...overrides,
  };
}
