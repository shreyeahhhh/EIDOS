import { MissionStatusPair } from "@/components/mission/mission-status-pair";
import { ExecutionTimeline } from "@/components/execution/execution-timeline";
import { PlanGraph } from "@/components/plan/plan-graph";
import { ReplanLineage } from "@/components/plan/replan-lineage";
import type { EventRecord, Plan, StepRecord } from "@/lib/api/types";

/**
 * The real workspace components (`PlanGraph`, `ReplanLineage`, `ExecutionTimeline`, `MissionStatusPair`)
 * rendering a static, illustrative example mission — not a live fetch, and said so plainly in the
 * caption. This is deliberately the actual product code, not a mockup drawn to look like it: what a
 * visitor sees here is pixel-for-pixel what a signed-in mission's workspace renders.
 */

const PLAN_V1: Plan = {
  tenant_id: "demo",
  plan_id: "demo-plan-1",
  mission_id: "demo-mission",
  version: 1,
  parent_plan_id: null,
  replan_reason: null,
  steps: [{ step_id: "research-1", depends_on: [], kind: "agent", capability: "research" }],
};

const PLAN_V2: Plan = {
  tenant_id: "demo",
  plan_id: "demo-plan-2",
  mission_id: "demo-mission",
  version: 2,
  parent_plan_id: "demo-plan-1",
  replan_reason: "the research step's model call failed",
  steps: [
    { step_id: "research-1", depends_on: [], kind: "agent", capability: "research" },
    { step_id: "analyze-1", depends_on: ["research-1"], kind: "agent", capability: "architecture" },
    { step_id: "verify-1", depends_on: ["analyze-1"], kind: "VERIFY" },
  ],
};

const DEMO_STEPS: StepRecord[] = [
  {
    step_id: "research-1",
    kind: "agent",
    capability: "research",
    depends_on: [],
    agent_id: null,
    started: true,
    result: { step_id: "research-1", kind: "agent", status: "succeeded", artifact: null, reason: null },
    dispatched: true,
    duration_ms: 2100,
    model_calls: [],
    tool_calls: [],
    retrievals: [],
    citations: [],
    verification: null,
  },
  {
    step_id: "analyze-1",
    kind: "agent",
    capability: "architecture",
    depends_on: ["research-1"],
    agent_id: null,
    started: true,
    result: { step_id: "analyze-1", kind: "agent", status: "succeeded", artifact: null, reason: null },
    dispatched: true,
    duration_ms: 1800,
    model_calls: [],
    tool_calls: [],
    retrievals: [],
    citations: [],
    verification: null,
  },
  {
    step_id: "verify-1",
    kind: "VERIFY",
    capability: null,
    depends_on: ["analyze-1"],
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
  },
];

function demoEvent(sequence: number, type: EventRecord["event"]["type"]): EventRecord["event"] {
  return {
    event_id: `demo-${sequence}`,
    tenant_id: "demo",
    mission_id: "demo-mission",
    sequence,
    occurred_at: `2026-01-01T00:00:${String(sequence).padStart(2, "0")}.000000Z`,
    recorded_at: `2026-01-01T00:00:${String(sequence).padStart(2, "0")}.000000Z`,
    type,
  };
}

const DEMO_EVENTS: EventRecord[] = [
  { event: demoEvent(1, "PLAN_GENERATED"), payload: { event_type: "PLAN_GENERATED", plan: PLAN_V1 } },
  {
    event: demoEvent(2, "REPLAN_TRIGGERED"),
    payload: {
      event_type: "REPLAN_TRIGGERED",
      failed_plan_id: "demo-plan-1",
      cause: "execution_failed",
      reason: "the research step's model call failed",
      next_plan_id: "demo-plan-2",
    },
  },
  { event: demoEvent(3, "PLAN_GENERATED"), payload: { event_type: "PLAN_GENERATED", plan: PLAN_V2 } },
  {
    event: demoEvent(4, "NODE_STARTED"),
    payload: { event_type: "NODE_STARTED", plan_id: "demo-plan-2", step_id: "research-1", kind: "agent", capability: "research", agent_id: null },
  },
  {
    event: demoEvent(5, "NODE_SETTLED"),
    payload: {
      event_type: "NODE_SETTLED",
      plan_id: "demo-plan-2",
      result: { step_id: "research-1", kind: "agent", status: "succeeded", artifact: null, reason: null },
      dispatched: true,
      duration_ms: 2100,
    },
  },
  {
    event: demoEvent(6, "NODE_STARTED"),
    payload: { event_type: "NODE_STARTED", plan_id: "demo-plan-2", step_id: "analyze-1", kind: "agent", capability: "architecture", agent_id: null },
  },
  {
    event: demoEvent(7, "NODE_SETTLED"),
    payload: {
      event_type: "NODE_SETTLED",
      plan_id: "demo-plan-2",
      result: { step_id: "analyze-1", kind: "agent", status: "succeeded", artifact: null, reason: null },
      dispatched: true,
      duration_ms: 1800,
    },
  },
  {
    event: demoEvent(8, "NODE_STARTED"),
    payload: { event_type: "NODE_STARTED", plan_id: "demo-plan-2", step_id: "verify-1", kind: "VERIFY", capability: null, agent_id: null },
  },
];

export function ProductPreview() {
  return (
    <div className="rounded-xl border border-border bg-surface-raised p-6 shadow-[var(--shadow-raised)] sm:p-8">
      <div className="flex flex-col gap-3 border-b border-border pb-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="font-mono text-xs text-ink-faint">Mission</p>
          <p className="mt-1 font-display text-xl text-ink">Research the current AI agent landscape</p>
        </div>
        <MissionStatusPair runStatus="running" missionStatus="created" />
      </div>

      <div className="pt-6">
        <p className="mb-3 text-xs font-medium tracking-wide text-ink-faint uppercase">Plan lineage</p>
        <ReplanLineage events={DEMO_EVENTS} />
      </div>

      <div className="pt-6">
        <p className="mb-3 text-xs font-medium tracking-wide text-ink-faint uppercase">Plan v2 — running</p>
        <PlanGraph steps={DEMO_STEPS} />
      </div>

      <details className="mt-6 border-t border-border pt-4">
        <summary className="cursor-pointer text-sm font-medium text-ink-muted select-none hover:text-ink">
          See the recorded events
        </summary>
        <div className="mt-3">
          <ExecutionTimeline events={DEMO_EVENTS} steps={DEMO_STEPS} />
        </div>
      </details>

      <p className="mt-6 border-t border-border pt-4 text-xs text-ink-faint">
        Example mission, shown with static data for illustration — not a live run.
      </p>
    </div>
  );
}
