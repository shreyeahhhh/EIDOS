import type { EventRecord, EvidenceView, ExecutionRecord, MissionResult, MissionSummary, Plan, StepRecord } from "./api/types";

/**
 * One example mission, shaped exactly like what the backend returns, with static illustrative values — it is shown on the landing page
 * (and used by the tests) and is never presented as a live run. It tells a small, real-shaped story: a research step fails once, EIDOS
 * replans, reads one web page, writes an answer that cites it, and the checks pass.
 */

export const EXAMPLE_URL = "https://example.com/";
export const EXAMPLE_PAGE_REF = "tool:web/fetch:449a47084cc8:example.com-f83a719872";

const MISSION_ID = "example-mission";

function step(id: string, kind: Plan["steps"][number]["kind"], capability: string | undefined, dependsOn: string[]): Plan["steps"][number] {
  return { step_id: id, kind, capability, depends_on: dependsOn };
}

const PLAN_1: Plan = {
  tenant_id: "example", plan_id: "plan-1", mission_id: MISSION_ID, version: 1, parent_plan_id: null, replan_reason: null,
  steps: [step("p1_research", "agent", "research", []), step("p1_analysis", "agent", "architecture", ["p1_research"]), step("p1_verify", "VERIFY", undefined, ["p1_analysis"])],
};

const PLAN_2: Plan = {
  tenant_id: "example", plan_id: "plan-2", mission_id: MISSION_ID, version: 2, parent_plan_id: "plan-1", replan_reason: "the research step's model call failed",
  steps: [step("p2_research", "agent", "research", []), step("p2_analysis", "agent", "architecture", ["p2_research"]), step("p2_verify", "VERIFY", undefined, ["p2_analysis"])],
};

function event(sequence: number, type: EventRecord["event"]["type"], secondsIn: number): EventRecord["event"] {
  const at = new Date(Date.UTC(2026, 0, 1, 9, 0, 0) + secondsIn * 1000).toISOString();
  return { event_id: `example-${sequence}`, tenant_id: "example", mission_id: MISSION_ID, sequence, occurred_at: at, recorded_at: at, type };
}

function started(plan: string, stepId: string, capability: string | null, kind: "agent" | "VERIFY" = "agent") {
  return { event_type: "NODE_STARTED" as const, plan_id: plan, step_id: stepId, kind, capability, agent_id: null };
}

function settled(plan: string, stepId: string, status: "succeeded" | "failed" | "skipped", durationMs: number | null, reason: string | null = null, kind: "agent" | "VERIFY" = "agent", artifact: string | null = null) {
  return { event_type: "NODE_SETTLED" as const, plan_id: plan, result: { step_id: stepId, kind, status, artifact, reason }, dispatched: status !== "skipped", duration_ms: durationMs };
}

export const EXAMPLE_EVENTS: EventRecord[] = [
  { event: event(1, "MISSION_CREATED", 0), payload: { event_type: "MISSION_CREATED", task_genome: { tenant_id: "example", goal: `Review the page at ${EXAMPLE_URL} and tell me what it says.`, required_capabilities: ["research", "architecture"], information_dependencies: [], risk_level: "low", autonomy_level: 1, allowed_actions: ["web_fetch"], reliability_contract_id: "contract-1" }, reliability_contract: { tenant_id: "example", contract_id: "contract-1", min_quality: 0, max_risk_level: "medium", min_independent_evidence: 1, max_tool_calls: 3 }, execution_id: "execution-1" } },
  { event: event(2, "PLAN_GENERATED", 1), payload: { event_type: "PLAN_GENERATED", plan: PLAN_1 } },
  { event: event(3, "PLAN_COMPILED", 2), payload: { event_type: "PLAN_COMPILED" } },
  { event: event(4, "NODE_STARTED", 3), payload: started("plan-1", "p1_research", "research") },
  { event: event(5, "NODE_SETTLED", 5), payload: settled("plan-1", "p1_research", "failed", 1900, "the model call failed (unavailable): the provider answered HTTP status 429: Rate limit reached for model on tokens per minute (TPM): Limit 8000, Used 5997, Requested 4073.") },
  { event: event(6, "NODE_SETTLED", 5), payload: settled("plan-1", "p1_analysis", "skipped", null) },
  { event: event(7, "NODE_SETTLED", 5), payload: settled("plan-1", "p1_verify", "skipped", null, null, "VERIFY") },
  { event: event(8, "REPLAN_TRIGGERED", 6), payload: { event_type: "REPLAN_TRIGGERED", failed_plan_id: "plan-1", cause: "execution_failed", reason: "the research step's model call failed", next_plan_id: "plan-2" } },
  { event: event(9, "PLAN_GENERATED", 7), payload: { event_type: "PLAN_GENERATED", plan: PLAN_2 } },
  { event: event(10, "PLAN_COMPILED", 8), payload: { event_type: "PLAN_COMPILED" } },
  { event: event(11, "NODE_STARTED", 9), payload: started("plan-2", "p2_research", "research") },
  { event: event(12, "NODE_SETTLED", 14), payload: settled("plan-2", "p2_research", "succeeded", 4800, null, "agent", "artifact:p2_research") },
  { event: event(13, "NODE_STARTED", 14), payload: started("plan-2", "p2_analysis", "architecture") },
  { event: event(14, "NODE_SETTLED", 19), payload: settled("plan-2", "p2_analysis", "succeeded", 5200, null, "agent", "artifact:p2_analysis") },
  { event: event(15, "NODE_STARTED", 19), payload: started("plan-2", "p2_verify", null, "VERIFY") },
  { event: event(16, "NODE_SETTLED", 20), payload: settled("plan-2", "p2_verify", "succeeded", 40, null, "VERIFY") },
  { event: event(17, "MISSION_COMPLETED", 20), payload: { event_type: "MISSION_COMPLETED", plan_id: "plan-2", verified: true } },
];

function stepRecord(id: string, kind: StepRecord["kind"], capability: string | null, dependsOn: string[], status: "succeeded", duration: number, extra: Partial<StepRecord> = {}): StepRecord {
  return {
    step_id: id, kind, capability, depends_on: dependsOn, agent_id: null, started: true, result: { step_id: id, kind, status, artifact: null, reason: null },
    dispatched: true, duration_ms: duration, model_calls: [], tool_calls: [], retrievals: [], citations: [], verification: null, ...extra,
  };
}

export const EXAMPLE_EXECUTION: ExecutionRecord = {
  tenant_id: "example", mission_id: MISSION_ID, execution_id: "execution-1", plan_id: "plan-2", plan_version: 2,
  steps: [
    stepRecord("p2_research", "agent", "research", [], "succeeded", 4800, {
      model_calls: [{ outcome: "response", prompt_tokens: 812, output_tokens: 436, elapsed_seconds: 4.7 }],
      tool_calls: [{ tool_id: "web/fetch", outcome: "result", denial: null, args_digest: "449a47084cc8c2d112bcfd94d4d610cbc7bce34251434b41b0fd694489040362a", result_refs: [EXAMPLE_PAGE_REF], result_bytes: 1523, elapsed_ms: 640 }],
      citations: [EXAMPLE_PAGE_REF],
    }),
    stepRecord("p2_analysis", "agent", "architecture", ["p2_research"], "succeeded", 5200, {
      model_calls: [{ outcome: "response", prompt_tokens: 1204, output_tokens: 388, elapsed_seconds: 5.1 }], citations: [EXAMPLE_PAGE_REF],
    }),
    stepRecord("p2_verify", "VERIFY", null, ["p2_analysis"], "succeeded", 40, {
      verification: { verdict: "pass", reason: "schema_validity satisfied (1 artifact(s) well-formed); citation_coverage satisfied (every artifact cites sources that exist); minimum_distinct_sources satisfied (1 distinct supplied source(s) reached, 1 required)." },
    }),
  ],
  plan_rejected_at: null, plan_rejection_reasons: [], mission_status: "completed", status_reason: null, run_outcome: "finished", verified: true, failure_cause: null, failure_reason: null,
  halt: null, awaiting: [], agent_calls_used: 3, tool_calls_used: 1, retries_used: 0, replans_used: 1, tokens_used: 2840, execution_time_used_ms: 20000, responses_missing_token_counts: 0,
};

export const EXAMPLE_MISSION: MissionSummary = {
  mission_id: MISSION_ID, tenant_id: "example", created_by: "example-user", created_at: "2026-01-01T09:00:00.000Z",
  goal: `Review the page at ${EXAMPLE_URL} and tell me what it says.`, run_status: "finished", run_status_reason: null, mission_status: "completed", status_reason: null, failure_cause: null,
  verified: true, plan_version: 2, last_sequence: 17,
  counters: { agent_calls_used: 3, tool_calls_used: 1, retries_used: 0, replans_used: 1, tokens_used: 2840, execution_time_used_ms: 20000 },
};

export const EXAMPLE_RESULT: MissionResult = {
  mission_status: "completed", verified: true,
  verdict: { verdict: "pass", reason: EXAMPLE_EXECUTION.steps[2].verification!.reason },
  artifacts: [
    {
      ref: "artifact:p2_analysis", content_type: "text/markdown", source_refs: [EXAMPLE_PAGE_REF],
      content: [
        "**What the page says**",
        "",
        "| Area | What it says | Evidence |",
        "|------|--------------|----------|",
        `| **Title** | The page is titled “Example Domain”. | “Example Domain” [[${EXAMPLE_PAGE_REF}]] |`,
        `| **Purpose** | It says the domain is for use in illustrative examples in documents. | “This domain is for use in illustrative examples in documents.” [[${EXAMPLE_PAGE_REF}]] |`,
        `| **Reuse** | It adds that the domain may be used in examples without prior coordination or asking permission. | “You may use this domain in literature without prior coordination or asking for permission.” [[${EXAMPLE_PAGE_REF}]] |`,
        "",
        "### In short",
        "",
        "1. **It is a reference page** – deliberately plain, not a product or a service.",
        "2. **There is nothing to act on** – it links to one further page for more information, and nothing else.",
      ].join("\n"),
    },
  ],
  failure: null,
};

export const EXAMPLE_EVIDENCE: EvidenceView = {
  audit: { traces: [{ step_id: "p2_research", ref: EXAMPLE_PAGE_REF, kind: "not_evidence", kb_id: null, chunk_id: null, document_id: null, source_id: null, retrieved_by: [] }, { step_id: "p2_analysis", ref: EXAMPLE_PAGE_REF, kind: "not_evidence", kb_id: null, chunk_id: null, document_id: null, source_id: null, retrieved_by: [] }], cited: [] },
  evidence: [
    {
      ref: EXAMPLE_PAGE_REF, content_type: "text/plain",
      content: `URL: ${EXAMPLE_URL}\n\nTitle: Example Domain\n\nExample Domain\n\nThis domain is for use in illustrative examples in documents. You may use this domain in literature without prior coordination or asking for permission.\n\nMore information...`,
    },
  ],
};
