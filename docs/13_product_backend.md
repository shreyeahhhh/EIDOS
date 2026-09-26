# 13. Product Backend (V1.4)

**Status:** DERIVED. **V1.4-A (architecture and contracts, `decisions.md` D-229 to D-234, 2026-09-26) is frozen for the owner's confirmation. Nothing here is implemented:** no FastAPI, database, JWT or migration code exists and no dependency has been added.
**Derived from:** handoff sections 51 to 54, 73, 76 and 78 (the handoff is not modified; where this document departs from it, D-229 and D-230 say so); `decisions.md` D-005, D-017, D-038, D-052, D-076, D-085, D-157, D-201, D-204, D-227.
**Authority:** This document is derived from `EIDOS_CLAUDE_CODE_HANDOFF.md` and subordinate to it. If this document and the handoff conflict, stop and report the conflict to the human owner.

> **The rule that governs everything below.** The API and the database adapt to EIDOS; EIDOS is not redesigned to fit them. The event log stays the authoritative mission history (D-157), `MissionState` stays its fold, and `ExecutionRecord` and `audit_evidence` stay projections. Persistence is durable storage and never a second authority. FastAPI never mutates `MissionState`.

## 1. The boundary (D-234)

```text
HTTP + Supabase JWT
      |
eidos.api           FastAPI: routers, auth dependency, error mapping, settings.
      |             The only importer of FastAPI and the JWT library. Reads response types only; never an EventLog or a reducer.
eidos.service       Application service: MissionService, RunManager, Composition, repository Protocols, in-memory implementations.
      |             Imports the EIDOS core. Imports no FastAPI, no JWT library and no database driver.
EIDOS core          run_with_replanning -> EventLog (authority) -> MissionState (its fold);
      |             execution_record and audit_evidence (projections).  Unchanged, except the one additive parameter of D-231.
eidos.persistence   PostgreSQL adapters for the service Protocols and for the existing ArtifactStore.
      |             The only importer of psycopg. Imports the service Protocols; the service never imports it.
Supabase PostgreSQL
```

- The core layers (`contracts`, `validation`, `compiler`, `runtime`, `state`) and every other existing package import none of the three new packages (CLAUDE.md section 8). The one composition module, in `eidos.api`, wires the service to the adapters. Import guards, in the pattern of the existing ones ("only X may import Y"), are written with the code.
- **The whole stack is synchronous.** The runtime is synchronous (the ports, the executors, the recorder's lock). Route handlers are plain `def`, run by FastAPI in its thread pool, and the database driver is synchronous. There is no async database layer and no second event loop.
- **New dependencies are optional extras**, in the pattern of `langgraph` and `a2a`: `api` (FastAPI, an ASGI server, a JWT library) and `postgres` (psycopg 3 and its pool); `dev` includes both. Versions are verified and pinned when the code is written; none is added by this phase.
- **One process per database in V1.4.** The runner is an in-process thread pool (section 6). A separate worker service, leases and multi-instance operation are deferred.

## 2. Persistence (D-230)

### 2.1 What is authoritative, what is durable, what is derived

| Fact | Authority | Durable form | Derived views |
|---|---|---|---|
| Mission history | the recorded events (`EventLog`) | `mission_events` | `MissionState` (replay), `ExecutionRecord`, `EvidenceAudit` |
| Artifact content | the write-once `ArtifactStore` | `artifacts` | result and evidence text |
| Mission input | the accepted `MissionSpec` until `MISSION_CREATED` exists, then that event's payload | `missions.spec` (without documents) and supplied `artifacts` | |
| Run lifecycle | the service (API level, section 6) | `missions.run_status` | never in `MissionState` |
| Identity | Supabase user ids and `tenant_members` | `tenants`, `tenant_members` | |

No table holds a copy of `MissionState`, of `ExecutionRecord` or of any status the reducer folds. `missions.last_sequence` is the only value derived from the log; it is an append guard, and the log wins on any mismatch. There is no plans table: a plan is immutable, versioned and in its `PLAN_GENERATED` payload (invariant 6). Projection columns for listing (a status, counters) arrive with a list API and not before.

### 2.2 Schema (PostgreSQL, schema `eidos`)

```sql
create schema if not exists eidos;

create table eidos.schema_migrations (
  version text primary key,
  applied_at timestamptz not null default now()
);

create table eidos.tenants (
  tenant_id uuid primary key,
  name text not null check (length(name) between 1 and 200),
  created_at timestamptz not null default now(),
  constraint tenant_is_not_the_reserved_sentinel check (tenant_id <> '00000000-0000-0000-0000-000000000000')
);

create table eidos.tenant_members (
  tenant_id uuid not null references eidos.tenants (tenant_id),
  user_id uuid not null,                 -- the Supabase Auth user id (the JWT subject); no foreign key into Supabase's own schema
  role text not null check (role in ('owner', 'member')),
  created_at timestamptz not null default now(),
  primary key (tenant_id, user_id)
);
create index tenant_members_by_user on eidos.tenant_members (user_id);

create table eidos.missions (
  mission_id uuid primary key,
  tenant_id uuid not null references eidos.tenants (tenant_id),
  execution_id uuid not null unique,     -- one execution per mission (D-085)
  created_by uuid not null,
  created_at timestamptz not null,
  spec jsonb not null,                   -- the validated MissionSpec as accepted, without supplied_documents (those are artifacts)
  spec_sha256 text not null,             -- digest of the whole request body, documents included (idempotency)
  idempotency_key text,
  run_status text not null default 'created'
    check (run_status in ('created', 'queued', 'running', 'finished', 'rejected', 'interrupted', 'error')),
  run_status_reason text,
  run_updated_at timestamptz not null,
  last_sequence integer not null default 0 check (last_sequence >= 0),
  unique (mission_id, tenant_id),
  unique (execution_id, tenant_id),
  unique (tenant_id, idempotency_key)    -- a null key never conflicts
);

create table eidos.mission_events (
  mission_id uuid not null,
  tenant_id uuid not null,
  sequence integer not null check (sequence >= 1),
  event_id uuid not null,
  event_type text not null,
  occurred_at timestamptz not null,
  record jsonb not null,                 -- the whole EventRecord in its strict JSON form: the durable authority
  primary key (mission_id, sequence),
  unique (mission_id, event_id),
  foreign key (mission_id, tenant_id) references eidos.missions (mission_id, tenant_id)
);

create table eidos.artifacts (
  execution_id uuid not null,
  tenant_id uuid not null,
  ref text not null check (length(ref) >= 1),
  kind text not null check (kind in ('supplied', 'step')),
  step_id text,
  content_type text not null,
  content text not null,
  source_refs jsonb not null default '[]',
  created_at timestamptz not null default now(),
  primary key (execution_id, ref),       -- a second write of a ref is refused: write-once
  foreign key (execution_id, tenant_id) references eidos.missions (execution_id, tenant_id),
  check ((kind = 'step') = (step_id is not null))
);
create unique index artifacts_one_primary_per_step on eidos.artifacts (execution_id, step_id) where kind = 'step';

-- Every table: row level security enabled with no policies, and no privilege for Supabase's API roles (section 5).
```

- **`ArtifactStore` contract, unchanged.** `put_supplied`, `put_step_artifact`, `get`, `get_step_artifact`, `supplied`. A duplicate ref or a second primary artifact for a step raises `ArtifactConflict`. `supplied` orders by ref in code-point order (`order by ref collate "C"`), because the in-memory store sorts in Python and the database collation must not change the order a model is shown.
- **Identifiers.** `tenant_id`, `mission_id`, `execution_id`, `plan_id`, `event_id`, `agent_id` are the existing EIDOS UUIDs, server-assigned. `user_id` is the Supabase user id, held only in the database (and in `MissionSummary`); it is not a core contract and no core model gains a field.
- **Migrations.** Plain versioned SQL files and a small applier that records `schema_migrations`. No ORM. Nothing in a migration or a query uses session state (advisory locks, `LISTEN`, session `SET`, server-side prepared statements), so any Supabase connection mode can be used. This is to be verified against Supabase's current documentation when the code is written.

### 2.3 The write-through model

1. **`DurableEventLog(EventLog)`** (in `eidos.service`) overrides `accept` only: it calls `super().accept`, and if the proposal was applied it hands the applied `EventRecord` to the run's outbox and flushes. `EventLog`, `Recorder`, `record_attempt` and the reducer are untouched. Nothing is ever persisted that the reducer refused.
2. **`WriteThroughArtifactStore`** wraps the run's `InMemoryArtifactStore`: reads come from memory, which is the runtime authority for the run; each put goes to memory first, then to the outbox. After the run, reads come from the database.
3. **The outbox** is one ordered list per run of artifact puts and event records. A flush is **one transaction**: `update missions set last_sequence = :new ... where mission_id = :m and tenant_id = :t and last_sequence = :expected` (zero rows means another writer: stop and mark the run `error`), then the inserts in outbox order, artifacts before the events that follow them, each `on conflict do nothing` followed by a check that an existing row is the identical record.
4. **Fail-soft.** A flush failure never raises into the runtime: the recorder holds its lock and nodes run on worker threads. The outbox keeps the items and the run is marked degraded; every later accept and the final flush retry the whole outbox in order (bounded retries and timeouts, provisional, section 9).
5. **End of run.** A final flush. If it fails after the bounded retries, `run_status` is `error` with reason `persistence`; the events that never reached the database exist only in memory and are lost when the process exits, and the API says so.
6. **Consequence.** The durable log is behind the in-memory log by at most the unflushed outbox, and the durable prefix is always a valid log (contiguous from sequence 1, applied events only, D-155), so a crash leaves a replayable prefix. The recorder's lock is held while a flush runs, so database latency serialises node settlements; this is accepted for the MVP.

### 2.4 The read path

Load the records ordered by sequence, then `replay(records)` gives `MissionState`, or a typed `ReplayRejection`, which is an integrity error and never a mission outcome. `execution_record(records)` and `audit_evidence(...)` are derived on demand. Nothing is written on a read. While a run is in progress a reader sees the flushed prefix; its `mission_status` is `created` until a terminal event exists. The applied-event-id set (D-038) is derived from the log; it is not stored separately.

### 2.5 Crash recovery

At startup, before the service accepts a request, every mission whose `run_status` is `queued` or `running` becomes `interrupted` (with a reason). **No event is written** and no `MISSION_FAILED` is fabricated: the failure-cause vocabulary is the runtime's, and a service restart is not one of its causes. This presumes one API process per database. An interrupted mission's prefix stays readable; it cannot be resumed or retried in V1.4 (the client creates a new mission).

### 2.6 Runtime only, never durable

Worker threads; the model, tool and knowledge ports; the `KnowledgeGate` answers, the `ToolGate` ledger and the `EvidenceLedger` (each derivable, and rebuilt per run); the experience store (per mission, in memory); the in-flight executor.

## 3. The execution path (D-231)

The API's execution path is `run_with_replanning`, the full driver (candidates, selection, expansion, attempts, replan, terminal event). D-204 item 1 is resolved by **one additive, optional, keyword-only parameter** and nothing else:

```python
# src/eidos/replanning.py  (the only core change in V1.4)
def run_with_replanning(*, state, limits, registry, agents, verifier, admission_guard_factory, executor_factory, clock, ids,
                        strategy_ids, plan_ids, candidate_generator, max_candidates, selector, store,
                        log: EventLog | None = None,
                        tracker: ModelCallTracker | None = None,      # NEW; default None
                        ) -> ReplanRun | ReplanRejection:
    ...
    recorder, report = record_attempt(..., clock=clock, ids=ids, log=log, tracker=tracker)   # forwarded; the only other edit
```

- `ModelCallTracker` is already exported by `eidos.recording`, which `eidos.replanning` already imports.
- **Default `None` changes nothing.** `record_attempt` then builds its own fresh `ModelCallTracker()` exactly as today, so an existing caller's recorded events, telemetry and experiences are identical.
- **With a tracker**, the caller wraps its model, tool access, knowledge port and agents with that same tracker (`RecordingModel`, `RecordingToolAccess`, `RecordingKnowledgePort`, `RecordingCitations`), as for `record_baseline`. Every attempt's nodes then settle with their model, tool, retrieval and citation facts. One tracker across attempts is correct: its collectors are thread-local and opened and closed per node, and `record_attempt` still creates a fresh `Recorder` per attempt (its own docstring's reason stands).
- **The only observable difference, and only when a tracker is supplied:** model-call and token counts stop being zero, so `TelemetryRecord` and `ExecutionExperience` (`model_call_count`, `tokens_used`, `responses_missing_token_counts`) become real.
- **Not changed:** `record_attempt`, `record_baseline`, the recorder, the tracker, the reducer, the events, the flow of `run_with_replanning`, and D-204 item 2 (`tool_calls_used` stays a whole-mission total; it stays Open and deferred).
- **Replanned duplicate queries.** As D-228 reading 5 says, the `KnowledgeGate` serves a repeated query from its stored answer, so a replan attempt's Research node records no retrieval fact of its own; its citations still resolve to the first attempt's recorded hits in `audit_evidence`.
- **Frozen contract lifted, once.** D-208 item 5 listed `run_with_replanning`, `record_attempt` and tracker propagation as frozen for V1.3. V1.4 lifts that for this one parameter by the owner's direction.
- **Tests required with the change:** every existing test passes unmodified; a run with no tracker records the log the existing replanning scenarios pin; with a tracker and a forced replan, model, tool, retrieval and citation facts are on the settled nodes of every attempt and are not attributed across attempts; the change touches only `replanning.py`.

## 4. MissionSpec and its mapping (D-232)

`POST /v1/missions` takes an explicit structured `MissionSpec`. **No component derives a `TaskGenome` or a `ReliabilityContract`, and no model has any part in creating one** (invariant 3). The field names are the contract's own, so the mapping is one-to-one and the product schema stays as small as the contracts are.

```json
{
  "goal": "string",
  "required_capabilities": ["research", "cost"],
  "information_dependencies": [],
  "risk_level": "low",
  "autonomy_level": 1,
  "allowed_actions": [],
  "reliability": {
    "min_quality": 0.0,
    "max_risk_level": "medium",
    "min_independent_evidence": 2,
    "max_retries": null, "max_replans": null, "max_agent_calls": null,
    "max_tool_calls": null, "max_execution_time": null, "max_tokens": null
  },
  "supplied_documents": [{"ref": "doc:1", "content_type": "text/plain", "content": "..."}]
}
```

| MissionSpec | Target | Rule |
|---|---|---|
| `goal` | `TaskGenome.goal` | non-empty after stripping; stored verbatim; at most `max_goal_chars` |
| `required_capabilities` | `TaskGenome.required_capabilities` | at least one, no duplicates, each a capability the server's registry serves (unknown: 422 naming it) |
| `information_dependencies` | `TaskGenome.information_dependencies` | optional opaque strings, at most `max_information_dependencies` |
| `risk_level` | `TaskGenome.risk_level` | as stated by the caller; the server does not assess it (D-057 for the API) |
| `autonomy_level` | `TaskGenome.autonomy_level` | 0 to 4, and at most `max_autonomy_level` |
| `allowed_actions` | `TaskGenome.allowed_actions` | each in the server's allowlist, at most `max_allowed_actions` |
| `reliability.min_quality`, `.max_risk_level`, `.min_independent_evidence` | `ReliabilityContract` (required, D-073) | as stated. They are recorded and **not evaluated** by verification (D-015, D-146); a verdict names them `NOT_EVALUATED`, and the API never reports a confidence |
| `reliability.max_*` (six, optional, D-065) | `ReliabilityContract` | absent stays absent (the existing semantics apply, including D-205 for tools); a present value above `SystemLimits`'s same field is **rejected, never clamped** (D-009) |
| `supplied_documents` | supplied `artifacts` (D-145) | optional; bounded in count and size; each ref unique |
| (not accepted) `tenant_id` | from the authenticated context | a client-supplied tenant is a 422 |
| (server) `mission_id`, `execution_id`, `contract_id`, `created_at` | fresh UUIDs and the clock | |
| (server) the `MissionState` carrier | `status=CREATED`, `plans=()`, counters 0, `state_version=0` | carries the genome, the contract and the ids into `run_with_replanning`; `MISSION_CREATED` builds the real state (D-201: before a run the mission does not exist for the log) |

Validation order: body size (413), structure with unknown fields forbidden (422), server ceilings (422), the existing contract validators (422), then persist. The mapping answers D-066 for the API: the contract is user-supplied and validated, never synthesised.

**The API safety ceilings (PROVISIONAL, section 9) are not runtime budget enforcement.** They bound what the service accepts. EIDOS still records the six budgets and enforces none of them beyond what D-205 and `max_replans` already do (D-127, D-156).

## 5. Authentication and tenancy (D-233)

- **Authentication.** `Authorization: Bearer <Supabase-issued JWT>`. FastAPI verifies the **signature** (configured key material and an algorithm allowlist, never `none`), **expiry** (`exp` required) and **audience** (`aud` equals the configured audience). `sub`, which must parse as a UUID, is the user. Any failure is one `401 unauthenticated`. Supabase's current token and key details are to be verified when the code is written.
- **Membership.** `tenant_members(tenant_id, user_id, role)`, roles `owner` and `member`. Both roles have every V1 endpoint on their tenant's missions; the role is reserved for the membership management deferred to a later milestone.
- **Tenant resolution.** No membership: `403 no_tenant_membership`. `X-Tenant-Id` present: it must be one of the user's tenants, otherwise `404 not_found` (it never says whether that tenant exists). Absent: the single membership; several memberships and no header: `422 tenant_required`. The result is a `RequestContext(user_id, tenant_id, role)` handed to the service.
- **Every repository operation is tenant-scoped.** Each method takes `tenant_id` as a required parameter and each query filters on it. **A resource of another tenant is indistinguishable from one that does not exist: 404.** Isolation is tested with the same contract tests over the in-memory and the PostgreSQL repositories.
- **The nil tenant.** `DEFAULT_TENANT_ID` (the nil UUID) is reserved for tests, in-memory and single-tenant contexts. The `tenants` table rejects it, and the API neither accepts it nor produces it. This settles D-032.
- **Row level security.** Tenant isolation is **application-enforced**. RLS is enabled on every table **with no policies**, the `eidos` schema is not exposed through Supabase's Data API, and the API roles hold no privilege on it, so a leaked public key reaches nothing. The backend connects with a server-side credential. Tenant-scoped RLS policies are deferred. This is the smallest production-safe design; how Supabase exposes schemas and roles is to be verified when the code is written.
- **Provisioning (proposed).** Tenants and memberships are created out of band (a SQL script); there is no signup, tenant or membership endpoint in V1.4-A.
- **Secrets** come from the environment only. None is in the repository, in a test or in a log.
- **Not built:** SSO, an RBAC engine, rate limiting, per-endpoint policy, audit trails.

## 6. The runtime and API boundary, and `run_status` (D-234)

**FastAPI never mutates `MissionState`.** A route calls `MissionService`; the service reads by replay and writes only by starting a run; `MissionState` changes only by the reducer inside the recorded run.

**The runner.** `RunManager` owns a bounded `ThreadPoolExecutor` (`worker_pool_size`). `start` does a compare-and-set `created -> queued` and submits; a worker does `queued -> running`, builds the per-run composition, calls `run_with_replanning(... log=DurableEventLog, tracker=tracker)`, translates the result, and does the final transition. One execution per mission is guaranteed by the compare-and-set and by a per-process set of active mission ids. There is no cancel and no retry (deferred).

**The per-run composition** (nothing is shared between runs, so per-execution memory is freed): the `MissionState` carrier; `SystemLimits` from configuration (D-103); a `CapabilityRegistry` with stable configured agent ids; the Research agent (model, and knowledge access when a static knowledge base is configured), the Analysis agent and `VerificationAgent`, wrapped with the tracker's recording adapters; a trivial always-admit `AdmissionGuard`, labelled as enforcing no budget; the sequential executor by default (the LangGraph backend by configuration); `SystemClock` and the UUID id sources; `RuleBasedCandidateGenerator` and `DeterministicSelector`; a per-mission in-memory `ExperienceStore`; `DurableEventLog` and `WriteThroughArtifactStore`. The model comes from a factory in `eidos.providers` chosen by configuration, so no vendor name enters `eidos.service` or `eidos.api` (D-135).

**`run_status` is API-level. It is never a `MissionStatus`, never an event and never in `MissionState`.**

| `run_status` | Meaning | Events | Terminal |
|---|---|---|---|
| `created` | the spec was accepted; nothing has started | none | no |
| `queued` | `start` was accepted; waiting for a worker | none | no |
| `running` | a worker is executing `run_with_replanning` | a growing prefix | no |
| `finished` | `run_with_replanning` returned a `ReplanRun`, the final flush succeeded, and `refused` and `discrepancies` are empty | complete, ending in a terminal mission event | yes |
| `rejected` | `ReplanRejection`: no first strategy was selectable; nothing was recorded (D-201); the code, outcome and reason are the `run_status_reason` | none | yes |
| `interrupted` | the process stopped or restarted while `queued` or `running` (section 2.5) | possibly a prefix | yes |
| `error` | a service fault: an unexpected exception, persistence that failed after its retries, or a log that is not the whole story (`refused` or `discrepancies` not empty, D-160) | possibly a prefix | yes |

Transitions, all compare-and-set and all by `RunManager` only: `created -> queued`, `queued -> running`, `running -> finished | rejected | error`, `queued | running -> interrupted` (startup only), `queued -> error` (submission failure). `finished` says the run ended; **what the mission came to** is `mission_status` (`completed`, `failed` or `paused`) with its typed cause and `verified`, read from the folded log.

## 7. The minimal API (`/v1`)

Common. JSON. `Authorization: Bearer` on everything except `healthz`; `X-Tenant-Id` as section 5. Errors have one shape, `{"error": {"code": "...", "message": "...", "details": [...]}}` (`details` only for `invalid_spec`). Responses reuse the EIDOS models (`ExecutionRecord`, `EventRecord`, `EvidenceAudit`) and add no parallel schema.

| Endpoint | Behaviour |
|---|---|
| `POST /v1/missions` | Body `MissionSpec`; optional `Idempotency-Key` (at most 128 characters). Validates, stores the spec and any supplied documents, returns **201** `{mission_id, run_status: "created", created_at}`. The same key with the same body digest returns the existing mission (200); with a different body, 409 `idempotency_conflict`. No event is written. |
| `POST /v1/missions/{id}/start` | **202** `{mission_id, run_status: "queued"}`. 409 `not_startable` unless `run_status` is `created`; 409 `tenant_run_limit`; 503 `busy` when the queue is full. |
| `GET /v1/missions/{id}` | `MissionSummary`: `mission_id`, `tenant_id`, `created_by`, `created_at`, `goal`, `run_status`, `run_status_reason`, then, once events exist and derived by replay: `mission_status`, `status_reason`, `failure_cause`, `verified`, `plan_version`, the counters (`agent_calls_used`, `tool_calls_used`, `retries_used`, `replans_used`, `tokens_used` as a lower bound, `execution_time_used_ms`), `last_sequence`. |
| `GET /v1/missions/{id}/execution` | The existing `ExecutionRecord`. 409 `no_events` before the first event. |
| `GET /v1/missions/{id}/events?after=&limit=` | `{events: [EventRecord...], last_sequence, next_after}` in sequence order; `after` defaults to 0; `limit` defaults to 100 and is capped (section 9). An empty list is a normal answer. This is the live view: poll with `after`. |
| `GET /v1/missions/{id}/result` | 409 `not_finished` until a terminal mission event exists. Then `{mission_status, verified, verdict: {verdict, reason} or null, artifacts: [...], failure: {cause, reason} or null}`. `verdict` is the verifier's verdict and reason, word for word. `artifacts` are the primary artifacts of the succeeded work steps that no other work step depends on in the last plan (the plan's sinks; the `VERIFY` step reads them). No confidence, no score. |
| `GET /v1/missions/{id}/evidence` | `{audit: EvidenceAudit, evidence: [{ref, content_type, content}]}` where `audit` is `audit_evidence` of the execution record and `evidence` holds the text of the cited `evidence:` artifacts. 409 `no_events` before the first event. |
| `GET /v1/healthz` | Unauthenticated liveness, `{"status": "ok"}`. No database check (readiness is a deployment concern). |

## 8. Failure semantics

An API failure is a failure of the request or the service. A mission failure is a recorded outcome of a run. **The two never share a channel:** a failed or paused mission is a successful `200` describing what happened; an API error is never an event.

| Situation | Where it shows | HTTP |
|---|---|---|
| bad, expired, wrong-audience or unsigned token | API error `unauthenticated` | 401 |
| no membership | `no_tenant_membership` | 403 |
| another tenant's, or an unknown, mission or tenant | `not_found` | 404 |
| several tenants and no `X-Tenant-Id` | `tenant_required` | 422 |
| invalid `MissionSpec`, or over a ceiling | `invalid_spec` with per-field details | 422 |
| body too large | `payload_too_large` | 413 |
| wrong state to start; no events yet; not finished; run limit | `not_startable`, `no_events`, `not_finished`, `tenant_run_limit`, `idempotency_conflict` | 409 |
| queue full; database unavailable | `busy`, `storage_unavailable` | 503 |
| a stored log that does not replay | `integrity_error` (never a mission outcome) | 500 |
| a mission that failed, or paused | the mission's own `mission_status`, `failure_cause` and reason | 200 |
| a run that was `rejected`, `interrupted` or ended in `error` | `run_status` and `run_status_reason` on `GET /v1/missions/{id}` | 200 |
| an unexpected exception in the service | run `error` (never a `MISSION_FAILED` event); `internal_error` if it was in a request | 500 |

## 9. The configuration profile (PROVISIONAL)

**Every value in this section is provisional: a round starting number, not tuned, not measured, not derived from any run.** Changing one is configuration and not an architecture change. The record follows D-046: a provisional bound is never presented as a tuned one. **These are API safety ceilings. They are not EIDOS budget enforcement, and nothing here claims to enforce a `ReliabilityContract`.** A request over a ceiling is rejected, never clamped.

| Setting | Provisional value |
|---|---|
| `max_request_body_bytes` | 262144 |
| `max_goal_chars` | 2000 |
| `max_information_dependencies`, `max_allowed_actions` | 16 each (`allowed_actions` also within the server allowlist) |
| `max_autonomy_level` | 1 (`SAFE_READ_ONLY`) |
| `max_supplied_documents`, `max_document_bytes`, `max_total_document_bytes` | 8, 32768, 131072 |
| contract budgets | each at most `SystemLimits`'s same field |
| `worker_pool_size`, `max_queued_runs`, `max_active_runs_per_tenant` | 2, 8, 1 (`queued` plus `running`) |
| `events_page_default`, `events_page_max` | 100, 500 |
| flush retries and per-flush timeout | 3 attempts, 10 seconds |

`SystemLimits` are supplied by configuration (D-103: EIDOS has no defaults); their values are provisional (D-046 stays Open) and are chosen when the configuration is written. **The admission guard is a trivial always-admit guard; it enforces no budget** (D-127, D-156). A run cannot be preempted, so there is no wall-clock cap; each model call and each tool call keeps its own timeout, and the plan's shape limits and `max_replans` bound the rest. Cancel, and a run timeout that means something, are deferred together.

**Knowledge and tools for V1.4.** At most one **static knowledge base per deployment**: a configured directory of UTF-8 text files, each file one declared source, built once at startup by `build_snapshot` into a pinned snapshot and served by the in-process `LexicalKnowledgePort` behind the existing `KnowledgePort` and `KnowledgeGate`. The service refuses to start if a configured knowledge base is invalid. It is one read-only reference corpus shared by every tenant, so it must contain only what every tenant may read. Without one, missions work from their supplied documents. Semantic retrieval stays available behind `KnowledgePort` and is not reopened: its production wiring (interpreter and model paths, worker lifetime, worker-environment logging, index persistence) remains deferred (D-227). No tool and no MCP server is wired. No Qdrant.

## 10. Deferred, not built in V1.4-A

List, cancel, replay and strategy-view endpoints; membership, tenant and signup endpoints, and any role behaviour beyond owner and member; tenant-scoped RLS policies; a separate worker service, leases, heartbeats and multi-instance operation; resume or retry of an interrupted run; preemptive cancel and a run timeout; projection columns, listing, search and pagination beyond events; server-sent events or websockets; tenant-private or managed knowledge bases, ingestion and index persistence; semantic-retrieval wiring (D-227); MCP tool wiring; Qdrant; strategy memory persistence and cross-mission learning (a tenant-scoped store is a later decision); runtime budget enforcement (D-043, D-127, D-156) and any real admission guard; D-204 item 2; observability and logging configuration; the frontend, Docker, cloud deployment and Kubernetes (Deployment and Frontend are unassigned, D-229).

## 11. Proposed implementation order (for the owner's approval)

Each step is one commit with its own tests, in this order, and none starts before the owner confirms D-229 to D-234:

1. **V1.4-B, the additive tracker (D-231):** the one core change and its tests.
2. **V1.4-C, the service and the persistence:** `MissionSpec`, ceilings, the composition, `RunManager`, `DurableEventLog`, the write-through artifact store, the repository Protocols with in-memory implementations, the PostgreSQL adapters and migrations, and shared contract tests over both. The PostgreSQL tests are opt-in (a marker and `EIDOS_TEST_DATABASE_URL` for a disposable database, never a real project's credentials); the default suite uses the in-memory implementations.
3. **V1.4-D, the API and authentication:** FastAPI, JWT verification, tenant resolution, the endpoints and the error mapping, with end-to-end tests over in-memory repositories and a scripted model.
4. **V1.4-E, the close-out audit.**
