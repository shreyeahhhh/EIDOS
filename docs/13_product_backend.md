# 13. Product Backend (V1.4)

**Status:** DERIVED. **V1.4-A (architecture and contracts, `decisions.md` D-229 to D-234, 2026-09-26) was accepted by the owner on 2026-09-27, and V1.4-B, the backend MVP, implemented it in one phase (2026-09-27).** Sections 1 to 11 are the accepted contracts as V1.4-A wrote them; where the code says more, or differs, a **Built** note says so, and section 12 records what was built, the choices made under the accepted architecture, and what was and was not verified. The code is `eidos.api`, `eidos.service` and `eidos.persistence`, plus one optional parameter of `run_with_replanning`. No frontend, deployment, Qdrant or knowledge-base management exists.
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

- The core layers (`contracts`, `validation`, `compiler`, `runtime`, `state`) and every other existing package import none of the three new packages (CLAUDE.md section 8). The one composition module, in `eidos.api`, wires the service to the adapters. **Built:** the import guards are `tests/unit/service/test_service_guards.py` (the direction of dependency, the one importer of each library, no `MissionState` construction, plain-`def` handlers, no ORM, the migrations' deny-all RLS, and that nothing deferred was built).
- **The whole stack is synchronous.** The runtime is synchronous (the ports, the executors, the recorder's lock). Route handlers are plain `def`, run by FastAPI in its thread pool, and the database driver is synchronous. There is no async database layer and no second event loop.
- **New dependencies are optional extras**, in the pattern of `langgraph` and `a2a`: `api` (FastAPI, an ASGI server, a JWT library) and `postgres` (psycopg 3 and its pool); `dev` includes both. **Built:** `api` is `fastapi>=0.141.1,<1`, `uvicorn>=0.54,<1` and `pyjwt[crypto]>=2.15,<3`; `postgres` is `psycopg[binary,pool]>=3.3.6,<4`; `dev` includes both (`pyproject.toml`). The lower bounds are the versions installed and tested against on 2026-09-26. FastAPI's `TestClient` needs `httpx`, which `dev` already has through the `a2a` extra.
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
  contract_id uuid not null,             -- the ReliabilityContractId assigned at creation: the run rebuilds the same contract from it
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

alter table eidos.tenants enable row level security;   -- and the same for tenant_members, missions, mission_events, artifacts and schema_migrations:
                                                       -- no policy, so the API roles are denied
-- then every privilege on schema eidos and its tables is revoked from anon, authenticated and service_role, wherever those roles exist (Supabase's; section 5)
```

- **Built.** The authoritative text is `src/eidos/persistence/migrations/0001_init.sql`. It differs from the block above in three ways only: the `contract_id` column; names for the constraints (`missions_scope`, `missions_execution_scope`, `missions_idempotency`, `mission_events_event_id`, `tenant_is_not_the_reserved_sentinel`); and the row level security and revoke statements written out. The composite foreign keys mean the schema itself refuses an event or an artifact that names another tenant's mission.

- **`ArtifactStore` contract, unchanged.** `put_supplied`, `put_step_artifact`, `get`, `get_step_artifact`, `supplied`. A duplicate ref or a second primary artifact for a step raises `ArtifactConflict`. `supplied` orders by ref in code-point order (`order by ref collate "C"`), because the in-memory store sorts in Python and the database collation must not change the order a model is shown.
- **Identifiers.** `tenant_id`, `mission_id`, `execution_id`, `plan_id`, `event_id`, `agent_id` are the existing EIDOS UUIDs, server-assigned. `user_id` is the Supabase user id, held only in the database (and in `MissionSummary`); it is not a core contract and no core model gains a field.
- **Migrations.** Plain versioned SQL files and a small applier that records `schema_migrations`. No ORM. Nothing in a migration or a query uses session state (session-level advisory locks, `LISTEN`, session `SET`, server-side prepared statements: the pool sets `prepare_threshold=None`), so any Supabase connection mode can be used. The applier serialises concurrent appliers with a transaction-level advisory lock, which is released at commit and so holds under the transaction pooler. Checked against Supabase's documentation (section 12.4).

### 2.3 The write-through model

1. **`DurableEventLog(EventLog)`** (in `eidos.service`) overrides `accept` only: it calls `super().accept`, and if the proposal was applied it hands the applied `EventRecord` to the run's outbox and flushes. `EventLog`, `Recorder`, `record_attempt` and the reducer are untouched. Nothing is ever persisted that the reducer refused.
2. **`WriteThroughArtifactStore`** wraps the run's `InMemoryArtifactStore`: reads come from memory, which is the runtime authority for the run; each put goes to memory first, then to the outbox. After the run, reads come from the database.
3. **The outbox** is one ordered list per run of artifact puts and event records. A flush is **one transaction**: `update missions set last_sequence = :new ... where mission_id = :m and tenant_id = :t and last_sequence = :expected` (zero rows means another writer: stop and mark the run `error`), then the inserts in outbox order, artifacts before the events that follow them, each `on conflict do nothing` followed by a check that an existing row is the identical record.
4. **Fail-soft.** A flush failure never raises into the runtime: the recorder holds its lock and nodes run on worker threads. The outbox keeps the items and the run is marked degraded; every later accept and the final flush retry the whole outbox in order (bounded retries and timeouts, provisional, section 9).
5. **End of run.** A final flush. If it fails after the bounded retries, `run_status` is `error` with reason `persistence`; the events that never reached the database exist only in memory and are lost when the process exits, and the API says so.
6. **Consequence.** The durable log is behind the in-memory log by at most the unflushed outbox, and the durable prefix is always a valid log (contiguous from sequence 1, applied events only, D-155), so a crash leaves a replayable prefix. The recorder's lock is held while a flush runs, so database latency serialises node settlements; this is accepted for the MVP.
7. **Built: lost answers and other writers.** A commit whose answer was lost (the write landed and the caller heard an error) is recognised on the retry: the guard refuses it as a conflict, the durable log is read, and if it already holds exactly the pending events (the same event ids at the same sequences) the outbox is cleared and nothing is written twice. Any other sequence conflict, and any artifact conflict, means another writer touched the mission: it is a permanent failure of the run (`error`) and nothing more is written. `DurableEventLog` overrides `accept_resumed` as it does `accept`.

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
- **Replanned duplicate queries.** As D-228 reading 5 says, the `KnowledgeGate` serves a repeated query from its stored answer, so a replan attempt's Research node records no retrieval fact of its own. Its citations resolve to the first attempt's recorded hits in an `audit_evidence` over the whole execution; over the default `execution_record`, which holds the last plan's steps only, they are `unresolved` (found by a V1.4-B test; section 12.2).
- **Frozen contract lifted, once.** D-208 item 5 listed `run_with_replanning`, `record_attempt` and tracker propagation as frozen for V1.3. V1.4 lifts that for this one parameter by the owner's direction.
- **Tests required with the change:** every existing test passes unmodified; a run with no tracker records the log the existing replanning scenarios pin; with a tracker and a forced replan, model, tool, retrieval and citation facts are on the settled nodes of every attempt and are not attributed across attempts; the change touches only `replanning.py`.
- **Built (V1.4-B).** The change is exactly the one above (`src/eidos/replanning.py`). "Every existing test passes unmodified" held, with one deliberate update: `tests/unit/recording/test_recording_tool_facts.py` pins the exact parameter list of `run_with_replanning`, and the pin now ends `log, tracker` (keyword-only, both default `None`). The new tests are `tests/integration/planning/test_v1_replanning_tracker.py`.

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
| (server) the `MissionState` carrier | `status=CREATED`, `plans=()`, counters 0, `state_version=1`, built by the reducer (section 12.2) | carries the genome, the contract and the ids into `run_with_replanning`; `MISSION_CREATED` builds the real state (D-201: before a run the mission does not exist for the log) |

Validation order: body size (413), structure with unknown fields forbidden (422), server ceilings (422), the existing contract validators (422), then persist. The mapping answers D-066 for the API: the contract is user-supplied and validated, never synthesised.

**The API safety ceilings (PROVISIONAL, section 9) are not runtime budget enforcement.** They bound what the service accepts. EIDOS still records the six budgets and enforces none of them beyond what D-205 and `max_replans` already do (D-127, D-156).

## 5. Authentication and tenancy (D-233)

- **Authentication.** `Authorization: Bearer <Supabase-issued JWT>`. FastAPI verifies the **signature** (configured key material and an algorithm allowlist, never `none`), **expiry** (`exp` required) and **audience** (`aud` equals the configured audience). `sub`, which must parse as a UUID, is the user. Any failure is one `401 unauthenticated`. The token and key details were checked against Supabase's documentation when the code was written (section 12.4).
- **Membership.** `tenant_members(tenant_id, user_id, role)`, roles `owner` and `member`. Both roles have every V1 endpoint on their tenant's missions; the role is reserved for the membership management deferred to a later milestone.
- **Tenant resolution.** No membership: `403 no_tenant_membership` — unless the deployer set `EIDOS_AUTO_PROVISION_WORKSPACES` (D-237), in which case a user with **no** tenant is first given one of their own (an `owner` membership in a new "Personal workspace" tenant whose id is derived from the user id, so concurrent first requests make one) and resolves normally; a user who already has any tenant is never given another. `X-Tenant-Id` present: it must be one of the user's tenants, otherwise `404 not_found` (it never says whether that tenant exists). Absent: the single membership; several memberships and no header: `422 tenant_required`. The result is a `RequestContext(user_id, tenant_id, role)` handed to the service.
- **Every repository operation is tenant-scoped.** Each method takes `tenant_id` as a required parameter and each query filters on it. **A resource of another tenant is indistinguishable from one that does not exist: 404.** Isolation is tested with the same contract tests over the in-memory and the PostgreSQL repositories.
- **The nil tenant.** `DEFAULT_TENANT_ID` (the nil UUID) is reserved for tests, in-memory and single-tenant contexts. The `tenants` table rejects it, and the API neither accepts it nor produces it. This settles D-032.
- **Row level security.** Tenant isolation is **application-enforced**. RLS is enabled on every table **with no policies**, the `eidos` schema is not exposed through Supabase's Data API, and the API roles hold no privilege on it, so a leaked public key reaches nothing. The backend connects with a server-side credential. Tenant-scoped RLS policies are deferred. This is the smallest production-safe design; how Supabase exposes schemas and roles was checked against its documentation (section 12.4).
- **Provisioning (accepted).** Tenants and memberships are created out of band (SQL); there is no signup, tenant or membership endpoint in V1.4.
- **Secrets** come from the environment only. None is in the repository, in a test or in a log.
- **Not built:** SSO, an RBAC engine, rate limiting, per-endpoint policy, audit trails.

## 6. The runtime and API boundary, and `run_status` (D-234)

**FastAPI never mutates `MissionState`.** A route calls `MissionService`; the service reads by replay and writes only by starting a run; `MissionState` changes only by the reducer inside the recorded run.

**The runner.** `RunManager` owns a bounded `ThreadPoolExecutor` (`worker_pool_size`). `start` does a compare-and-set `created -> queued` and submits; a worker does `queued -> running`, builds the per-run composition, calls `run_with_replanning(... log=DurableEventLog, tracker=tracker)`, translates the result, and does the final transition. One execution per mission is guaranteed by the compare-and-set and by a per-process set of active mission ids. There is no cancel and no retry (deferred).

**The per-run composition** (nothing is shared between runs, so per-execution memory is freed): the `MissionState` carrier; `SystemLimits` from configuration (D-103); a `CapabilityRegistry` with stable configured agent ids; the Research agent (model, and knowledge access when a `KnowledgeProvision` is supplied), the Analysis agent and `VerificationAgent`, wrapped with the tracker's recording adapters; a trivial always-admit `AdmissionGuard`, labelled as enforcing no budget; the sequential executor (the LangGraph backend is not wired); `SystemClock` and the UUID id sources; `RuleBasedCandidateGenerator` and `DeterministicSelector`; a per-mission in-memory `ExperienceStore`; `DurableEventLog` and `WriteThroughArtifactStore`. The model comes from a factory in `eidos.providers` chosen by configuration, so no vendor name enters `eidos.service` or `eidos.api` (D-135).

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
| `GET /v1/missions/{id}/evidence` | `{audit: EvidenceAudit, evidence: [{ref, content_type, content}]}` where `audit` is `audit_evidence` of the whole-execution record (every plan's steps; section 12.2) and `evidence` holds the text of the artifacts the audit resolved. 409 `no_events` before the first event. |
| `GET /v1/healthz` | Unauthenticated liveness, `{"status": "ok"}`. No database check (readiness is a deployment concern). |

## 8. Failure semantics

An API failure is a failure of the request or the service. A mission failure is a recorded outcome of a run. **The two never share a channel:** a failed or paused mission is a successful `200` describing what happened; an API error is never an event.

| Situation | Where it shows | HTTP |
|---|---|---|
| bad, expired, wrong-audience or unsigned token | API error `unauthenticated` | 401 |
| the token's key source cannot be reached | `auth_unavailable` | 503 |
| no membership | `no_tenant_membership` | 403 |
| another tenant's, or an unknown, mission or tenant | `not_found` | 404 |
| several tenants and no `X-Tenant-Id` | `tenant_required` | 422 |
| invalid `MissionSpec`, or over a ceiling | `invalid_spec` with per-field details | 422 |
| a well-formed request that is wrong as a call (a bad `after` or `limit`, a malformed `Idempotency-Key`) | `invalid_request` | 422 |
| body too large | `payload_too_large` | 413 |
| wrong state to start; no events yet; not finished; run limit | `not_startable`, `no_events`, `not_finished`, `tenant_run_limit`, `idempotency_conflict` | 409 |
| queue full; database unavailable | `busy`, `storage_unavailable` | 503 |
| a stored log that does not replay | `integrity_error` (never a mission outcome) | 500 |
| a path or a method this API does not have | `not_found` or `method_not_allowed` (the framework's own 404 and 405, in the same shape) | 404 / 405 |
| a mission that failed, or paused | the mission's own `mission_status`, `failure_cause` and reason | 200 |
| a run that was `rejected`, `interrupted` or ended in `error` | `run_status` and `run_status_reason` on `GET /v1/missions/{id}` | 200 |
| an unexpected exception in the service | run `error` (never a `MISSION_FAILED` event); `internal_error` if it was in a request | 500 |

The message of a service fault (`storage_unavailable`, `integrity_error`, `auth_unavailable`, `internal_error`) is a fixed sentence and never the message the fault was raised with, and the `run_status_reason` of an unexpected or a persistence fault is the exception's type alone: the detail goes to the server log (`eidos.service.runner`). A 401 carries `WWW-Authenticate: Bearer`.

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
| flush retries; database timeouts | 3 attempts with a growing pause (0.5 s, then 1 s); a 10-second statement timeout and a 10-second connect timeout |

`SystemLimits` are supplied by configuration (D-103: EIDOS has no defaults); their values are provisional (D-046 stays Open) and are chosen when the configuration is written. **The admission guard is a trivial always-admit guard; it enforces no budget** (D-127, D-156). A run cannot be preempted, so there is no wall-clock cap; each model call and each tool call keeps its own timeout, and the plan's shape limits and `max_replans` bound the rest. Cancel, and a run timeout that means something, are deferred together.

**Knowledge and tools for V1.4.** **Knowledge is optional and no production knowledge-base choice is made (the owner's ruling of 2026-09-27; D-227 is not reopened; no Qdrant).** The V1.4-A proposal of one static knowledge base per deployment is not built and no loader ships. A deployer may hand `Composition` a `KnowledgeProvision` (a `KnowledgeBaseDescriptor` and a `KnowledgePort`); Research then reaches it through the existing `KnowledgeGate`, and `eidos.api.main` configures none. Without one, missions work from their supplied documents. No tool and no MCP server is wired.

## 10. Deferred, not built in V1.4

List, cancel, replay and strategy-view endpoints; membership, tenant and signup endpoints, and any role behaviour beyond owner and member; tenant-scoped RLS policies; a separate worker service, leases, heartbeats and multi-instance operation; resume or retry of an interrupted run; preemptive cancel and a run timeout; projection columns, listing, search and pagination beyond events; server-sent events or websockets; tenant-private or managed knowledge bases, ingestion and index persistence; semantic-retrieval wiring (D-227); MCP tool wiring; Qdrant; strategy memory persistence and cross-mission learning (a tenant-scoped store is a later decision); runtime budget enforcement (D-043, D-127, D-156) and any real admission guard; D-204 item 2; observability and logging configuration; the frontend, Docker, cloud deployment and Kubernetes (Deployment and Frontend are unassigned, D-229).

## 11. Implementation order (replaced by the owner's scope change)

V1.4-A proposed four steps (the tracker; the service and persistence; the API and authentication; the close-out). On 2026-09-27 the owner replaced them with ONE substantial phase, V1.4-B, built and committed as one: the tracker; `MissionSpec` and the ceilings; the composition, `RunManager`, `DurableEventLog` and the write-through artifact store; the repository Protocols, the in-memory implementations, the PostgreSQL adapters and the migrations, with one contract suite over both; authentication and tenant resolution; the endpoints and the error mapping; and the tests. The new optional dependencies (FastAPI, uvicorn, PyJWT, psycopg 3 and its pool) were approved for that phase. Not built in V1.4-B, in addition to section 10: a knowledge-base loader or any production knowledge-base choice, the LangGraph executor in the service, a second model adapter and a readiness check.

## 12. Built in V1.4-B (implementation notes, 2026-09-27)

### 12.1 The code

| Package or module | What it is |
|---|---|
| `eidos.replanning` | the one core change: the optional keyword-only `tracker` parameter (D-231) |
| `eidos.service.spec` | `MissionSpec`, `ReliabilitySpec`, `SuppliedDocument`; `validate_spec` (ceilings, allowlists, documents); `contract_and_genome` (the one-to-one mapping); `initial_state` (the reducer-built carrier); `spec_digest` |
| `eidos.service.config` | `ApiCeilings`, `RunnerConfig`, `ServiceConfig`, `provisional_system_limits`: every number PROVISIONAL and labelled so |
| `eidos.service.ports` | the repository Protocols (`TenancyRepository`, `MissionRepository`, `EventStore`), `MissionRecord`, `RunStatus`, `Role`, `ArtifactWrite` and the storage errors |
| `eidos.service.memory` | `InMemoryStorage`: the default suite's implementation of every port |
| `eidos.service.durable` | `RunPersistence` (the outbox), `DurableEventLog(EventLog)`, `WriteThroughArtifactStore` |
| `eidos.service.composition` | `Composition` (one `prepare` per run), `AlwaysAdmit`, `InMemoryExperienceStore`, `KnowledgeProvision` |
| `eidos.service.runner` | `RunManager`: the bounded in-process runner and `run_status` |
| `eidos.service.views` | the response models and the replay projections (`summary_of`, `result_of`, `evidence_of`, `whole_execution_record`) |
| `eidos.service.service` | `MissionService` and `RequestContext`: the only thing the HTTP layer calls |
| `eidos.persistence` | `PostgresStorage`, `PostgresArtifacts`, `apply_migrations`, `migrations/0001_init.sql` |
| `eidos.api` | `create_app`, `JwtVerifier`, `JwksKeys`, `StaticKey`, the error mapping, and `main.create_app_from_environment` (the composition root) |
| `eidos.providers.factory` | `model_port(provider, *, base_url)`; the only provider is `ollama` |

### 12.2 Choices made under the accepted architecture (not separately confirmed)

1. **The carrier `MissionState` is built by the reducer.** Only the reducer may construct a `MissionState` (a repository guard), so `initial_state` folds one `MISSION_CREATED` event through a throwaway `EventLog` and discards the log; the run's own log records its own `MISSION_CREATED`. The carrier's `state_version` is 1 (V1.4-A said 0).
2. **`missions.contract_id`** is stored (section 2.2), so the run rebuilds the same reliability contract the creation validated.
3. **Evidence is audited over the whole execution.** The default `execution_record` is the last plan's steps only, and a retrieval fact lives on the node of the attempt that made it, so a replan attempt's citations are `unresolved` in an audit over the default record. `whole_execution_record` lays every plan's steps, in plan order, into one `ExecutionRecord` through the record's own strict JSON form (validated, never constructed around its validators); `GET .../evidence` audits that. `GET .../execution` returns the existing default record, unchanged. A core question, left to the owner: whether the default should ever be the whole execution.
4. **Knowledge is optional** and no loader ships (the owner's ruling); see section 9.
5. **The sequential reference executor only.** The LangGraph executor was proposed "by configuration" and is not wired: the backend does not need it and it would add an import path.
6. **`AlwaysAdmit`** is the admission guard `run_with_replanning` requires and none ships; it enforces no budget and says so (D-127, D-156).
7. **A per-mission in-memory experience store**: nothing is learned across missions and nothing leaks across tenants.
8. **The checks of `start` run in this order:** `not_startable` (a mission that is not `created` never becomes startable, so that answer is not hidden behind a capacity answer that could change), then `tenant_run_limit`, then `busy`. The compare-and-set stays the authority.
9. **Fixed sentences for service faults; type-only reasons.** Found by a test: a storage message would have reached the caller and, through `run_status_reason`, every reader of the mission. The API now answers a service fault with a fixed sentence, a `run_status_reason` for an unexpected or a persistence fault is the exception's type alone (a sequence or artifact conflict keeps its own wording), and the full detail goes to the `eidos.service.runner` logger. The PostgreSQL adapter already raised `StorageError` with the exception's type name only.
10. **The request body is counted as it arrives** and refused with 413 over the limit whether or not it declares a length; it is parsed with `MissionSpec.model_validate_json`, because the EIDOS contracts are strict and only the JSON form of a strict model accepts JSON's own types (a JSON integer is a valid `min_quality`; a string is not).
11. **`/v1/openapi.json` is served; `/docs` and `/redoc` are off.**
12. **PostgreSQL connection:** a pool of 1 to 8 connections, `prepare_threshold=None`, a 10-second statement timeout and connect timeout, no `timezone` connection option (timestamps are converted to UTC by the client; the embedded test server has no time-zone data), and every statement one round trip or one transaction.
13. **`X-Tenant-Id`** is the header that names the tenant of a user of several.
14. **The service does not import `eidos.knowledge`.** The knowledge package is imported by three boundary modules only (its guard, unchanged). `KnowledgeProvision.port` is typed by a one-method structural `RetrievalPort` in `eidos.service.composition`, which is a `KnowledgePort` in shape and is handed straight to the recording adapter. The first full run found this: the composition had imported `KnowledgePort` for an annotation and the guard refused it.
15. **`start` is idempotent by state, not by key:** a second `start` of a mission that is queued, running or over is a 409 `not_startable`. `Idempotency-Key` applies to creation only, and a key lives as long as its mission row.

### 12.3 Running it

```bash
pip install -e ".[api,postgres]"
python -m eidos.persistence.migrate                          # reads EIDOS_DATABASE_URL and applies pending migrations
uvicorn eidos.api.main:create_app_from_environment --factory
```

Configuration is the environment. A missing or malformed variable stops startup before anything is served and names the variable, never its value; no connection string, secret or token is logged or echoed. Required: `EIDOS_DATABASE_URL`; `EIDOS_MODEL_PROVIDER` (`ollama`), `EIDOS_MODEL_BASE_URL`, `EIDOS_MODEL_NAME`, `EIDOS_MODEL_TEMPERATURE`, `EIDOS_MODEL_SEED`, `EIDOS_MODEL_MAX_OUTPUT_TOKENS`, `EIDOS_MODEL_TIMEOUT_SECONDS` (no defaults, D-135); and exactly one of `EIDOS_JWKS_URL` (an `https` URL, the asymmetric mode) and `EIDOS_JWT_SECRET` (the legacy HS256 mode). Optional: `EIDOS_JWT_AUDIENCE` (default `authenticated`), `EIDOS_JWT_ISSUER`, `EIDOS_ALLOWED_ACTIONS` (comma separated), `EIDOS_WORKER_POOL_SIZE`, `EIDOS_MAX_QUEUED_RUNS`, `EIDOS_MAX_ACTIVE_RUNS_PER_TENANT`, `EIDOS_AUTO_PROVISION_WORKSPACES` (`true`/`1`/`yes` turns on D-237; absent is off). Unless that is on, tenants and memberships are inserted with SQL.

### 12.4 What was verified, and what was not

**Read from Supabase's documentation on 2026-09-26 (nothing was run against a Supabase project):** a signed-in user's token has audience `authenticated` and the user's UUID as `sub`; asymmetric signing keys are published at `https://<project>.supabase.co/auth/v1/.well-known/jwks.json` and may be cached for at most about ten minutes so a rotation is picked up; the legacy shared HS256 secret is discouraged; the direct connection is on port 5432, the session pooler on 5432 (IPv4) and the transaction pooler on 6543, which supports no prepared statements and no session features; a table with row level security enabled and no policy is denied to the `anon` and `authenticated` roles, while `service_role` and `postgres` bypass row level security (so the application connects with its own server-side credential and the schema also revokes the API roles' privileges).

**Run:** the default suite (no database, no credential); the same repository-contract tests and 15 PostgreSQL-only tests on a real PostgreSQL 16.2 (an embedded local server, not Supabase) with `-m postgres`. **Not run:** anything against a live Supabase project, a real model through the API, mutation testing (no explicit acceptance criterion required it and the brief said not to start it), and a load or soak test.

### 12.5 The tests

| Suite | Tests | Holds |
|---|---|---|
| `tests/unit/service/test_service_spec.py` | 36 | the mapping, ceilings that reject, documents, the digest |
| `tests/unit/service/test_service_durable.py` | 12 | the write-through model: order, fail-soft, bounded flush, lost answers, another writer, artifacts |
| `tests/unit/service/test_service_runner.py` | 21 | `run_status`, the bounded runner, recovery, failure versus API failure, no leak of a fault's message, a transient store fault around a transition (V1.4-C) |
| `tests/unit/service/test_service_service.py` | 40 | identity, creation, idempotency, tenant isolation, every read as a replay, integrity failure |
| `tests/unit/service/test_service_guards.py` | 96 | the boundaries, no `MissionState` construction, the migrations, nothing deferred built, no credential in the repository (V1.4-C) |
| `tests/unit/service/test_service_storable.py` | 8 | text the durable store cannot keep (V1.4-C) |
| `tests/unit/api/test_api_auth.py` | 32 | JWT verification, algorithm confusion, JWKS availability |
| `tests/unit/api/test_api_main.py` | 18 | configuration errors name the variable and never a value, a shared secret below the least an HS256 key may be (V1.4-C) |
| `tests/integration/api/test_api_endpoints.py` | 112 | the eight endpoints and no others, authentication, tenancy, failure semantics, invariants |
| `tests/integration/api/test_api_real_process.py` | 6 (5 `-m postgres`) | the documented start command as a real `uvicorn` process: a whole mission, a process killed mid-run, concurrency, misconfiguration (V1.4-C) |
| `tests/integration/service/test_service_flow.py` | 12 | the durable log is the runtime's log, restart, a store that fails part-way, concurrency |
| `tests/integration/persistence/test_storage_contract.py` | 34 | the repository contract, on the in-memory storage and, with `-m postgres`, on PostgreSQL (the count includes both) |
| `tests/integration/persistence/test_postgres_service.py` | 18 | (all `-m postgres`) migrations, deny-all RLS, the schema's own constraints, a whole mission, recovery, a race between two processes, a model's answer holding a NUL (V1.4-C) |
| `tests/integration/persistence/test_postgres_boundary.py` | 3 | an unreachable database and the migration runner, without a server |
| `tests/integration/planning/test_v1_replanning_tracker.py` | 6 | the tracker parameter under replanning |

**The full default suite (after V1.4-C):** 7,255 passed and 74 deselected, reproduced under two hash seeds (`PYTHONHASHSEED=20270927` and `20270928`); 7,233 and 65 at V1.4-B; 6,819 and 34 at V1.3's close-out. The deselected tests are the 34 real-model tests and the 40 PostgreSQL tests (`-m postgres`, all 40 passed against a disposable local PostgreSQL 16.2). Section 12.6 is the V1.4-C acceptance audit.

### 12.6 The V1.4-C acceptance audit (2026-09-27)

A bounded acceptance audit of the implemented backend against this document and D-229 to D-234, before anything is pushed: no new capability, no redesign, no reopening of a provisional value or a deferred item
unless the audit found a concrete correctness or security failure in it.

**Method.** The existing suites first; new tests only for a genuine gap the audit found. An independent AST import audit at `e6bcb1a` (V1.3's close) and at this commit, over every file, confirms exactly the three
new package edges reported in section 1 and none from a core layer; a documentation-conformance script checked the eight endpoints, every error code and status, and every configured environment variable
against the code, all matching; a real `uvicorn` process (the documented start command) was driven over real HTTP and a real disposable PostgreSQL, including killing it mid-run; and the repository was scanned
for credential-shaped text (private key blocks, JWTs, cloud and platform tokens, connection strings with a password) with no other change made on that account beyond hardening `.gitignore`.

**Found and fixed, each with a new test (no core file changed; every fix is in `eidos.service` or `eidos.api`):**

1. **A NUL character reaching PostgreSQL was an unhandled 500, and a model that answered with one ended its run in error with a short prefix.** PostgreSQL's `text` and `jsonb` refuse a NUL outright. A
   request holding one (the goal, an information dependency, a document) is now refused at the door with a 422 naming the field (`eidos.service.spec`, `UNSTORABLE`); a model's answer is passed through a
   `StorableModel` port that replaces a NUL with U+FFFD before anything is recorded, so the runtime sees, records and cites the same text the store holds and the durable log is still exactly the runtime's
   log (`eidos.service.composition`).
2. **The framework's own 404 (no such path) and 405 (wrong method) were FastAPI's default `{"detail": ...}` body**, not this API's one error shape. They now go through the same `error_response` (a new
   `method_not_allowed` code; `not_found` is reused for a missing path) and section 8 documents both.
3. **A transient storage fault exactly when a run started or ended was a single try.** `RunManager`'s own transition to `running` or to a terminal status now retries with the same bound and backoff as the
   event flush (`RunnerConfig.flush_attempts`/`flush_backoff_seconds`) before it gives up and lets startup recovery mark the row `interrupted`; the fault is logged, never raised past that bound.
4. **A shared HS256 secret shorter than 32 bytes** (the least RFC 7518 section 3.2 allows for that algorithm) is now refused at startup, naming the variable and never the value.
5. **A concurrent-create race relies on the database's own unique constraint** (`missions_idempotency`), confirmed under real concurrency: many simultaneous creates with one `Idempotency-Key`, over the
   in-memory service, the `TestClient` and a real `uvicorn` process over real PostgreSQL, all make exactly one mission.
6. **Awkward but storable text (emoji, right-to-left marks, combining marks, control characters other than NUL, quotes, SQL and JSON metacharacters) round-trips unchanged** through a document, a step
   artifact, a goal and an event, confirmed on the in-memory storage and on real PostgreSQL byte for byte.

**Reconfirmed, not changed (the audit found no defect):** D-231's tracker propagation under a forced replan (the existing suite, rerun); the import boundaries (no edge from a core layer, no edge into
`eidos.api`/`eidos.service`/`eidos.persistence` from outside them); tenant isolation and cross-tenant 404 on every method, in-memory and on real PostgreSQL; idempotency, including the race above; the
write-through model and replay from a persisted log; restart and interrupted-run recovery, including a process killed mid-run over real PostgreSQL; the bounded runner's one-execution-per-mission guarantee
under real concurrency; the API-error-versus-mission-failure separation; and that no confidence or score appears in any answer. No credential, key, token or connection string with a password was found in
the repository.

**Left exactly as documented, because the audit found no concrete failure in them (the owner's brief named these as non-blocking MVP limitations):** no configured knowledge base means an empty evidence
view; `execution_record` stays last-plan-only; the API, `SystemLimits`, runner, flush and database values stay provisional; one API process per database; only the `ollama` model adapter exists.

**Tests:** 22 new default tests and 9 new opt-in PostgreSQL tests (31 total; section 12.5's counts already include them). The full default suite passed under two hash seeds; the full opt-in PostgreSQL suite
(40 tests) passed once against a disposable local PostgreSQL 16.2, never against a Supabase project. Mutation testing was not run: no acceptance criterion required it.
