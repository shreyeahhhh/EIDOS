/**
 * Types mirroring the real EIDOS backend contract (`eidos.service.spec`, `eidos.service.views`,
 * `eidos.state`, `eidos.contracts`), verified against a running instance of `eidos.api.app.create_app`
 * during the V1.5 inspection (2026-09-27) — not guessed from documentation alone.
 *
 * Keep this file synchronised with the backend by hand: there is no code generation step (the
 * backend's OpenAPI document is served at `/v1/openapi.json` if that is ever wanted later), and the
 * eight endpoints below are the whole surface (`docs/13_product_backend.md` section 7).
 */

// --- identifiers and enums ---------------------------------------------------------------------

/** A UUID string, as every EIDOS identifier is serialised. */
export type Uuid = string;

/** An ISO-8601 UTC timestamp, as `UtcDateTime` serialises (e.g. `2026-09-27T07:03:57.330675Z`). */
export type IsoDateTime = string;

export type RiskLevel = "low" | "medium" | "high";

/** `TaskGenome.autonomy_level` (0..4). The server ceiling defaults to 1 (`SAFE_READ_ONLY`). */
export type AutonomyLevel = 0 | 1 | 2 | 3 | 4;

/**
 * The capabilities this deployment's registered agents actually serve — fixed by which agents
 * `eidos.service.composition.Composition` wires up (Research + Analysis), not a platform-wide
 * vocabulary and not discoverable through any endpoint. If the backend's agents ever change, this
 * list must be updated by hand.
 */
export const KNOWN_CAPABILITIES = ["research", "architecture", "security", "cost"] as const;
export type CapabilityId = (typeof KNOWN_CAPABILITIES)[number] | (string & {});

/**
 * `allowed_actions`' real vocabulary is operator configuration (`EIDOS_ALLOWED_ACTIONS`), not
 * discoverable through any endpoint, and defaults to empty. The mission-creation form therefore
 * never offers a picker for it; it is sent as `[]` unless a caller supplies something explicitly.
 */
export type ActionId = string;

/** The API-level run lifecycle (`eidos.service.ports.RunStatus`). Never a `MissionStatus`. */
export type RunStatus = "created" | "queued" | "running" | "finished" | "rejected" | "interrupted" | "error";

/** `eidos.contracts.MissionStatus`. Absent (not this type) until at least one event exists. */
export type MissionStatus = "created" | "completed" | "failed" | "paused";

export type MissionFailureCause =
  | "plan_rejected"
  | "run_rejected"
  | "execution_failed"
  | "no_result"
  | "verification_failed"
  | "verification_inconclusive";

export type VerificationVerdict = "pass" | "fail" | "inconclusive";

export type NodeStatus =
  | "succeeded"
  | "failed"
  | "no_result"
  | "verification_failed"
  | "verification_inconclusive"
  | "skipped"
  | "not_reached"
  | "awaiting";

export type PlanStepKind = "agent" | "ROUTE" | "VERIFY" | "RETRY" | "REPLAN" | "HUMAN_APPROVAL" | "TERMINATE";

export type CitationKind = "resolved" | "unresolved" | "ambiguous" | "not_evidence";

/** Which validation gate refused a plan (the pipeline stops at the first that does). */
export type PlanRejectionStage = "validation" | "compilation" | "binding";

export interface RejectionReason {
  code: string;
  message: string;
}

export type MissionEventType =
  | "MISSION_CREATED"
  | "PLAN_GENERATED"
  | "PLAN_REJECTED"
  | "PLAN_COMPILED"
  | "A2A_TASK_STARTED"
  | "A2A_TASK_COMPLETED"
  | "MCP_TOOL_CALLED"
  | "RAG_SEARCH"
  | "EVIDENCE_REJECTED"
  | "VERIFICATION_FAILED"
  | "REPLAN_TRIGGERED"
  | "MISSION_COMPLETED"
  | "MISSION_FAILED"
  | "NODE_STARTED"
  | "NODE_SETTLED"
  | "MISSION_PAUSED";

// --- POST /v1/missions ---------------------------------------------------------------------------

export interface SuppliedDocument {
  ref: string;
  content_type: string;
  content: string;
}

export interface ReliabilitySpec {
  min_quality: number;
  max_risk_level: RiskLevel;
  min_independent_evidence: number;
  max_retries?: number | null;
  max_replans?: number | null;
  max_agent_calls?: number | null;
  max_tool_calls?: number | null;
  max_execution_time?: number | null;
  max_tokens?: number | null;
}

/** The whole request body of `POST /v1/missions`. No server-owned field (id, tenant, timestamp) belongs here. */
export interface MissionSpec {
  goal: string;
  required_capabilities: CapabilityId[];
  information_dependencies?: string[];
  risk_level: RiskLevel;
  autonomy_level: AutonomyLevel;
  allowed_actions: ActionId[];
  reliability: ReliabilitySpec;
  supplied_documents?: SuppliedDocument[];
}

export interface CreatedMission {
  mission_id: Uuid;
  run_status: RunStatus;
  created_at: IsoDateTime;
}

// --- POST /v1/missions/{id}/start -----------------------------------------------------------------

export interface StartedMission {
  mission_id: Uuid;
  run_status: RunStatus;
}

// --- GET /v1/missions/{id} -------------------------------------------------------------------------

export interface Counters {
  agent_calls_used: number;
  tool_calls_used: number;
  retries_used: number;
  replans_used: number;
  /** A lower bound: a call whose provider did not report tokens is not counted. */
  tokens_used: number;
  execution_time_used_ms: number;
}

export interface MissionSummary {
  mission_id: Uuid;
  tenant_id: Uuid;
  created_by: Uuid;
  created_at: IsoDateTime;
  goal: string;
  run_status: RunStatus;
  run_status_reason: string | null;
  mission_status: MissionStatus | null;
  status_reason: string | null;
  failure_cause: MissionFailureCause | null;
  verified: boolean | null;
  plan_version: number | null;
  counters: Counters | null;
  last_sequence: number;
}

// --- GET /v1/missions/{id}/execution ---------------------------------------------------------------

export interface ModelCallFacts {
  outcome: "response" | "timeout" | "unavailable" | "malformed_response" | "empty_response";
  prompt_tokens: number | null;
  output_tokens: number | null;
  elapsed_seconds: number | null;
}

export interface ToolCallFacts {
  tool_id: string;
  outcome: string;
  denial: string | null;
  args_digest: string | null;
  result_refs: string[];
  result_bytes: number | null;
  elapsed_ms: number | null;
}

export interface RetrievalHitFacts {
  rank: number;
  chunk_id: string;
  document_id: string;
  source_id: string;
  /** A digest of the retrieved text, never the text itself — the text comes from `GET /evidence` once resolved. */
  content_digest: string;
  /** Present only where the retrieval scheme provided one. */
  score: number | null;
}

export interface RetrievalFacts {
  kb_id: string;
  snapshot_id: string;
  scheme_id: string;
  query_id: string;
  top_k: number;
  outcome: string;
  score_kind: string | null;
  hits: RetrievalHitFacts[];
  result_bytes: number | null;
  elapsed_ms: number | null;
}

export interface NodeResult {
  step_id: string;
  kind: PlanStepKind;
  status: NodeStatus;
  artifact: string | null;
  reason: string | null;
}

export interface VerificationFacts {
  verdict: VerificationVerdict;
  reason: string;
}

export interface StepRecord {
  step_id: string;
  kind: PlanStepKind;
  capability: CapabilityId | null;
  depends_on: string[];
  agent_id: Uuid | null;
  started: boolean;
  result: NodeResult | null;
  dispatched: boolean | null;
  duration_ms: number | null;
  model_calls: ModelCallFacts[];
  tool_calls: ToolCallFacts[];
  retrievals: RetrievalFacts[];
  citations: string[];
  verification: VerificationFacts | null;
}

export interface HaltInfo {
  step_id: string;
  level: number;
  reason: string;
}

export interface AwaitingInfo {
  step_id: string;
  level: number;
  reason: string;
}

/**
 * The current (last) plan's execution, projected from the recorded events. A replanned mission's
 * earlier plans are not here — they must be read from `GET /events` (`PLAN_GENERATED`,
 * `REPLAN_TRIGGERED`). This is a documented V1.4 limitation, not an omission in this type.
 */
export interface ExecutionRecord {
  tenant_id: Uuid;
  mission_id: Uuid;
  execution_id: Uuid;
  plan_id: Uuid | null;
  plan_version: number | null;
  steps: StepRecord[];
  plan_rejected_at: PlanRejectionStage | null;
  plan_rejection_reasons: RejectionReason[];
  mission_status: MissionStatus;
  status_reason: string | null;
  run_outcome: "finished" | "failed" | "halted" | "awaiting" | null;
  verified: boolean | null;
  failure_cause: MissionFailureCause | null;
  failure_reason: string | null;
  halt: HaltInfo | null;
  awaiting: AwaitingInfo[];
  agent_calls_used: number;
  tool_calls_used: number;
  retries_used: number;
  replans_used: number;
  tokens_used: number;
  execution_time_used_ms: number;
  responses_missing_token_counts: number;
}

// --- GET /v1/missions/{id}/events ------------------------------------------------------------------

export interface MissionEvent {
  event_id: Uuid;
  tenant_id: Uuid;
  mission_id: Uuid;
  sequence: number;
  occurred_at: IsoDateTime;
  recorded_at: IsoDateTime;
  type: MissionEventType;
}

export interface TaskGenome {
  tenant_id: Uuid;
  goal: string;
  required_capabilities: CapabilityId[];
  information_dependencies: string[];
  risk_level: RiskLevel;
  autonomy_level: AutonomyLevel;
  allowed_actions: ActionId[];
  reliability_contract_id: Uuid;
}

export interface ReliabilityContract extends ReliabilitySpec {
  tenant_id: Uuid;
  contract_id: Uuid;
}

export interface PlanStep {
  step_id: string;
  depends_on: string[];
  kind: PlanStepKind;
  capability?: CapabilityId;
}

export interface Plan {
  tenant_id: Uuid;
  plan_id: Uuid;
  mission_id: Uuid;
  version: number;
  parent_plan_id: Uuid | null;
  replan_reason: string | null;
  steps: PlanStep[];
}

/**
 * The recorded event payload. Only the event types this backend build can actually emit are typed
 * precisely (no tool, no knowledge base and no A2A agent is wired in V1.4); the rest fall back to
 * `Record<string, unknown>` so an unexpected shape never breaks rendering — the UI should show them
 * generically rather than assume a shape it has not verified.
 */
export type EventPayload =
  | ({ event_type: "MISSION_CREATED" } & { task_genome: TaskGenome; reliability_contract: ReliabilityContract; execution_id: Uuid })
  | ({ event_type: "PLAN_GENERATED" } & { plan: Plan })
  | ({ event_type: "PLAN_REJECTED" } & { plan_id: Uuid; stage: PlanRejectionStage; reasons: RejectionReason[] })
  | ({ event_type: "NODE_STARTED" } & { plan_id: Uuid; step_id: string; kind: PlanStepKind; capability: CapabilityId | null; agent_id: Uuid | null })
  | ({ event_type: "NODE_SETTLED" } & { plan_id: Uuid; result: NodeResult; dispatched: boolean; duration_ms: number | null })
  | ({ event_type: "REPLAN_TRIGGERED" } & { failed_plan_id: Uuid; cause: MissionFailureCause; reason: string; next_plan_id: Uuid })
  | ({ event_type: "MISSION_COMPLETED" } & { plan_id: Uuid; verified: boolean })
  | ({ event_type: "MISSION_FAILED" } & { plan_id: Uuid | null; cause: MissionFailureCause; reason: string })
  | ({ event_type: "MISSION_PAUSED" } & { plan_id: Uuid; halt: HaltInfo | null; awaiting: AwaitingInfo[] })
  | ({ event_type: string } & Record<string, unknown>);

export interface EventRecord {
  event: MissionEvent;
  payload: EventPayload;
}

export interface EventsPage {
  events: EventRecord[];
  /** The mission's durable last sequence — compare against the last item's `event.sequence` to know if more exist. */
  last_sequence: number;
  /** Pass this back as `after` to continue paging. */
  next_after: number;
}

// --- GET /v1/missions/{id}/result -------------------------------------------------------------------

export interface ResultArtifact {
  ref: string;
  content_type: string;
  content: string;
  source_refs: string[];
}

export interface MissionFailure {
  cause: MissionFailureCause;
  reason: string | null;
}

export interface MissionResult {
  mission_status: MissionStatus;
  /** Only a completed mission says; a failed one has neither `verified` nor `verdict`. */
  verified: boolean | null;
  verdict: VerificationFacts | null;
  artifacts: ResultArtifact[];
  failure: MissionFailure | null;
}

// --- GET /v1/missions/{id}/evidence -----------------------------------------------------------------

export interface RetrievedBy {
  step_id: string;
  query_id: string;
  snapshot_id: string;
  scheme_id: string;
  rank: number;
}

export interface CitationTrace {
  step_id: string;
  ref: string;
  kind: CitationKind;
  kb_id: string | null;
  chunk_id: string | null;
  document_id: string | null;
  source_id: string | null;
  retrieved_by: RetrievedBy[];
}

export interface CitedDocument {
  source_id: string;
  document_id: string;
}

export interface EvidenceAudit {
  traces: CitationTrace[];
  cited: CitedDocument[];
}

export interface EvidenceItem {
  ref: string;
  content_type: string;
  content: string;
}

export interface EvidenceView {
  audit: EvidenceAudit;
  evidence: EvidenceItem[];
}

// --- errors ------------------------------------------------------------------------------------------

/** Every one of the eighteen codes `eidos.api.errors.STATUS_OF` maps to an HTTP status. */
export type ApiErrorCode =
  | "unauthenticated"
  | "no_tenant_membership"
  | "not_found"
  | "method_not_allowed"
  | "tenant_required"
  | "invalid_spec"
  | "invalid_request"
  | "payload_too_large"
  | "not_startable"
  | "no_events"
  | "not_finished"
  | "tenant_run_limit"
  | "idempotency_conflict"
  | "busy"
  | "storage_unavailable"
  | "auth_unavailable"
  | "integrity_error"
  | "internal_error";

export interface ApiErrorDetail {
  field: string;
  message: string;
}

export interface ApiErrorBody {
  code: ApiErrorCode;
  message: string;
  details?: ApiErrorDetail[];
}

export interface ApiErrorEnvelope {
  error: ApiErrorBody;
}
