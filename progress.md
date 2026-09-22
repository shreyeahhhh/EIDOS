# progress.md — EIDOS Implementation Tracking

Status only. Rules live in [CLAUDE.md](CLAUDE.md). Decisions and open questions live in
[decisions.md](decisions.md). The canonical specification is `EIDOS_CLAUDE_CODE_HANDOFF.md`.

---

## Current state

**Milestone: V0.5 Mission State + Event Reducer — complete as scoped (D-152 to D-164), on top of V0.4 Real Local Agents (complete as scoped, D-131 to D-151), V0.1 Core Contracts, V0.2 Plan Validation and V0.3 LangGraph Runtime (complete as scoped, D-112 to D-130).**

All seven V0.1 contracts (`ReliabilityContract`, `TaskGenome`, `Plan`, `PlanStep`, `MissionEvent`,
`MissionState`, `AgentTask`) are implemented in `src/eidos/contracts/`, immutable, in-memory only
(D-005), with no I/O, no network, no LLM calls and no vendor/model/SDK reference. 165 unit tests in
`tests/unit/contracts/` pass (155 at implementation, +10 for D-107/D-108), covering construction, rejection of invalid input, immutability, every
required/optional field, opaque identifier typing, Plan step uniqueness, `depends_on` referential
integrity, plan lineage/reference consistency, TaskGenome/ReliabilityContract reference consistency,
and the MissionState cross-object consistency checks (A7). No architecture decision was reopened
during implementation.

V0.2 (`src/eidos/validation/`) adds a deterministic, seven-stage plan-validation pipeline with two entry
points — `validate_plan_json(text, state, limits)` and `validate_plan(plan, state, limits)` — that returns a
typed report and never raises for an invalid plan. See "V0.2 Plan Validation" below. (574 tests at V0.2
completion: 165 in `tests/unit/contracts/`, 409 in `tests/unit/validation/`.)

**V0.3 (LangGraph Runtime): complete as scoped; Steps 2 to 5 implemented.** The architecture rulings are recorded as
D-112 to D-130 (2026-09-19 to 2026-09-20; D-130 accepted 2026-09-20). Step 2 added `src/eidos/compiler/` — the immutable compiled form and `compile_plan`.
Step 3 added `src/eidos/runtime/` — result types, `ExecutionContext`, the synchronous ports, the admission
hook, and the **sequential reference executor**. Step 4 added `src/eidos/backends/langgraph/` — the LangGraph adapter, the **only** importer of LangGraph — and the
optional `langgraph` extra. Step 5 added `tests/scenarios/` — whole missions driven through validation, compilation and both
executors — and closed the milestone. There was **no real agent** at that point (V0.4 added them). See "V0.3 LangGraph Runtime" below. **1,683 tests pass**
(165 in `tests/unit/contracts/`, 409 in `tests/unit/validation/`, 276 in `tests/unit/compiler/`, 431 in
`tests/unit/runtime/`, 48 in `tests/unit/backends/`, 305 in `tests/integration/langgraph/`, 49 in `tests/scenarios/`).

**V0.4 (Real Local Agents): complete as scoped (2026-09-21; D-131 to D-151).** The owner ruled on the V0.4 exploration (Q1–Q15) and then on the questions the rulings raised; the rulings are
**D-131 to D-140 and D-144 to D-150 (Accepted)**, which also resolve **D-006, D-018, D-141, D-142 and D-143**. Steps 2 to 9 are done. The baseline works end to end with a scripted model on both
backends, and **with a real local model the committed opt-in test (`qwen3:4b`, 4,096 output tokens, 240 s), run once, finished — Research → Analysis → VERIFY → PASS, outcome `finished`,
`verified` true.** The route there is recorded as it happened: at 512 tokens the first step failed because the reasoning model spent its whole budget before answering (D-149), and at 2,048
the second step failed the same way (D-150). The PASS covers three deterministic rules and measures no quality, and the committed test asserts structure only, so its printed outcome, not
pytest's green, is what shows the result. **D-151 (Open)** records the one thing deliberately left: a non-empty answer that stopped at the output limit. See "The first real baseline run"
and the sections after it, and "V0.4 close-out review".

**V0.5 (Mission State + Event Reducer): complete as scoped (2026-09-21; D-152 to D-164); pushed to origin/master.** The owner approved the exploration's proposal with nine rulings and then eight more on the
implementation details (D-152 to D-161). Built: the sixteen-type event vocabulary; the typed payloads and `EventRecord` beside the unchanged V0.1 envelope; a pure, outcome-returning reducer (the only writer of
`MissionState`); an in-memory event log with an intake that assigns the sequence, checkpoint, replay and a strict JSONL round trip (`eidos.state`); recording adapters around the baseline, with an
observational hook on `run_baseline` (`eidos.recording`); and a derived, read-only `ExecutionRecord`. The full chain is proved on both executors for the verified baseline and for every failure path, and a
fresh interpreter replays a serialized log without loading an agent, provider or backend. **The gap found while building was closed on the owner's ruling (D-162 item 1):** the intake, and a fold from scratch,
refuse a repeated `NODE_STARTED` or `NODE_SETTLED` for the same step of a plan, and `MissionState` gained no per-node state. **One question stays Open, not affecting an acceptance criterion:** D-164 (a start
recorded after the same step's settlement). D-163 (the admission guard is not wrapped) was resolved by amending D-158 item 1; the recorder is unchanged. A real-model recording was not run (not required). See "V0.5 Mission State + Event
Reducer" and "V0.5 close-out review" below.

**V0.6 (One A2A Boundary): the protocol and contract design is accepted (2026-09-22; D-165 to D-176); no code exists yet.** The owner directed research against the published A2A Protocol Specification and the actual `a2a-sdk` dependency graph before any transport choice, then ruled on all twelve items. This resolves **D-023, D-035, D-036, D-037** and amends **D-160** ruling 4 narrowly (**D-176**): an admission-guard `paused` mission is unchanged from V0.5; a `paused` mission caused by an A2A-awaiting pause is the one exception, resumable on the same log. No fifth `MissionStatus`. No code changed. See "V0.6 One A2A Boundary" below.

There is still no planner, no MCP, no RAG, no persistence, no telemetry, no API and no frontend, and no A2A code — only its contract.

Real-model runs have been recorded (V0.4; see "The first real baseline run" and the sections after it). They record what happened in those runs and are not a benchmark: no quality
metric exists anywhere in this repository, and the only latencies recorded are the first run's one trivial completion and the runtime-reported durations of the later runs' calls.

### Bootstrap deliverables

- [x] `CLAUDE.md` — permanent rules, 18 architecture invariants
- [x] `progress.md` — this file
- [x] `decisions.md` — 132 Accepted, 40 Open, 5 Deferred (counts current as of the latest decision below)
- [x] `README.md`, `pyproject.toml`, `.gitignore`
- [x] `docs/01`–`docs/12` — the twelve documents required by handoff §81
- [x] `src/eidos/` and `src/eidos/contracts/` — docstring only, no code
- [x] `tests/{unit,integration,protocol,scenarios}/` — layer definitions per §62
- [x] Git repository initialized with one checkpoint commit

---

## Milestone ladder

Source: handoff §50. Every milestone's gate is that milestone's §50 content plus the §61 definition
of done: implementation exists, tests exist, tests pass, integration works, architecture invariants
hold, failure cases are covered, documentation matches reality, a git checkpoint exists.

| Milestone | Scope (§50) | Status |
|---|---|---|
| **V0.1** Core Contracts | `TaskGenome`, `ReliabilityContract`, `MissionState`, `MissionEvent`, `Plan`, `PlanStep`, `AgentTask`. No real agents, no A2A, no MCP, no frontend. In-memory only (D-005). | **Implemented — 165 unit tests passing** (155 at implementation, +10 for D-107/D-108) |
| **V0.2** Plan DSL | Schema validation, cycle detection, dependency validation, depth limits, node limits, parallel-branch limits, capability validation, policy validation. | **Implemented — 409 unit tests passing** (2026-09-19). Every stage is implemented **except policy validation, which reports `NOT_APPLICABLE`** (D-110): no policy rule exists to check, and none was invented. D-046 (the actual limit values) stays Open — no limits object ships (D-103). D-111 (eight implementation details, Open) awaits the owner. |
| **V0.3** LangGraph Runtime | Map `SEQUENTIAL`, `PARALLEL`, `ROUTE`, `VERIFY`, `RETRY`, `REPLAN` into runtime nodes. Mock agents. | **Complete as scoped — 2026-09-20 (D-112 to D-130). Step 2 (compiled form and `compile_plan`, 276 tests), Step 3 (runtime types, ports, admission, prior outcomes and the sequential reference executor, 431 tests), Step 4 (the LangGraph extra, the S1–S10 spike, the adapter and conformance with the reference executor, 353 tests) and Step 5 (scenario tests, 49 tests) are done.** Narrowed from §50's list: only `agent` and `VERIFY` compile; `ROUTE`, `RETRY`, `REPLAN`, `TERMINATE`, `HUMAN_APPROVAL` are rejected at compile time and D-012 stays Open. **Not delivered, by scope:** mapping `ROUTE`, `RETRY` and `REPLAN` (D-012 and D-125 stay Open), and any importable mock agent — work is exercised by scripted test doubles only, and no product mock agents exist (see "V0.3 close-out" below). |
| **V0.4** Real Local Agents | Research, Analysis, Verification. Baseline workflow end-to-end. | **Complete as scoped — 2026-09-21 (D-131 to D-151).** `eidos.agents` (the model seam, the artifact store, Research, Analysis and a deterministic Verification rule set), `eidos.capabilities`, `eidos.baseline` and `eidos.providers`; 2,053 tests pass, 2 real-model tests deselected. The baseline works end to end **with a scripted model** on both backends, and **with a real local model the committed opt-in test (4,096 output tokens, 240 s), run once, finished with a verifier PASS** (three deterministic rules; no quality measured). Smaller budgets had failed, as recorded (D-149, D-150). **Not delivered, by scope:** a planner, replan, events and replay, tools, A2A, MCP, RAG and persistence; D-151 (Open) is deliberately left. See "V0.4 close-out review". |
| **V0.5** MissionState + Event Reducer | `MissionEvent`, `MissionState`, `StateReducer`, checkpoints, replay. §50: state handling must be reliable **before** A2A. | **Complete as scoped — 2026-09-21 (D-152 to D-164).** The event log, a pure outcome-returning reducer, checkpoint and replay, recording adapters outside the runtime, and a thin derived `ExecutionRecord`; in memory with a JSONL round trip, no durable store. Resolves D-010b, D-039 and D-126; D-151, D-129, D-059, D-015 and D-017 stay Open. The intake and replay refuse a repeated node event (D-162); **D-164 stays Open** (D-163 was resolved by amending D-158 item 1). 2,524 tests pass in the default suite. |
| **V0.6** One A2A Boundary | Move exactly one agent into an independent process. Test: normal completion, timeout, duplicate event, late event, agent restart, partial artifact, failure. | **Protocol/contract design accepted 2026-09-22 (D-165 to D-176), resolving D-023, D-035, D-036, D-037; D-160 amended by D-176. No code — not started.** |
| **V0.7** MCP | 2–3 real tools only (`search_documents`, `retrieve_evidence`). Test: successful call, invalid arguments, timeout, unavailable tool, unauthorized call, duplicate call. | Not started — deferred (D-027) |
| **V0.8** Agentic RAG | Qdrant, local embeddings, retrieval, reranking, evidence judge. | Not started — deferred (D-028) |
| **V0.9** Telemetry | Structured event logging. Measure latency, tokens, agent calls, tool calls, A2A interactions, RAG rounds, retries, quality. | Not started |
| **V1.0** Strategy Optimization | Historical strategy memory, strategy ranking, constraint-based selection, pilot execution. | Not started |
| **V1.1** Adaptive Learning | Strategy memory, historical ranking, exploration, empirical estimation, prediction-error tracking. | Not started |
| **V1.2** Reliability / Governance | Policy engine, autonomy levels, human approval, failure recovery, replan limits, execution budgets. | Not started |
| **V1.3** Frontend | Mission Center, Strategy View, Live Execution, Evidence Explorer, Replay, Strategy Lab, Failure Lab. | Not started — blocked (D-022) |
| **V1.4** Deployment | Docker Compose → single cloud environment → API + workers + DB → optional separate A2A agents. Not Kubernetes. | Not started |

---

## V0.1 Core Contracts — implemented (2026-09-18)

Scope from §50 and §82. In-memory typed contracts, deterministic validation-oriented structures,
and tests. **No persistence (D-005). No behaviour beyond construction and validation.**

Modules in `src/eidos/contracts/`:

- `_base.py` — shared frozen, extra-forbid, strict-validation base model
- `_validators.py` — the UTC-timestamp-required validator (D-083)
- `identifiers.py` — every opaque identifier type (D-053) and `DEFAULT_TENANT_ID` (D-079)
- `enums.py` — `RiskLevel`, `AutonomyLevel`, `MissionStatus`, `PlanStepKind`, `MissionEventType`
- `reliability_contract.py` — `ReliabilityContract` — §30
- `task_genome.py` — `TaskGenome` — §6
- `plan.py` — `Plan`, `PlanStep` (as `AgentStep`/`ControlStep` discriminated union) — §13, D-004
- `mission_event.py` — `MissionEvent` — §10, §33
- `agent_task.py` — `AgentTask` — §8
- `mission_state.py` — `MissionState` — §9, §10, with the six A7 cross-object validators

`tests/unit/contracts/` — 165 tests (155 at implementation, +10 for D-107/D-108): valid-object factories in `tests/support/eidos_factories.py` (shared; D-109), and one test module per
contract module above, covering construction, field validation, rejection of invalid input, the
failure paths (§61, CLAUDE.md §6), immutability, and every cross-object consistency check named in
A7. `test_mission_state.py` is last, since `MissionState` composes every other contract.

**Next:** V0.2 followed — see "V0.2 Plan Validation" below. The pre-implementation blocker analysis
(which of the eight stages needed which decision) is recorded in `decisions.md` D-102, D-103 and D-104..D-110
and in the session log; it found no blocker for the mechanism, and none arose.

**The five named blocking decisions are resolved** — D-013, D-019, D-011, D-010a, D-009. The
structural questions about V0.1 are settled.

**D-016 resolved** (2026-09-16, human owner): `ReliabilityContract.min_quality` is a **plain scalar
threshold** — a user-stated requirement, not an estimate, so it carries no uncertainty. The
quality-**estimate** type §19 and invariant 17 require is **not** introduced in V0.1, because nothing
in V0.1 produces an estimate; it is deferred to its proper owner as **D-063**. **D-064** logged:
whether §31/§47 `confidence` and §30 `quality` are the same quantity. **D-015 untouched.**

**D-014 resolved** (2026-09-16, human owner): `TaskGenome.autonomy_level` uses §29's 0–4 scale.
Unlike the risk case, the handoff supplies a scale at the right abstraction with a consistent
example, so declining it would discard evidence rather than avoid invention. **D-060**, **D-061**
and **D-062** left Open.

**D-065 resolved** (2026-09-17, human owner): all six budget fields are **optional**; an omitted
budget falls back to the applicable system ceiling, and a supplied one may tighten but never exceed
it. §30's own example contract omits four of the six, so omission is legal by demonstration. No
numerical defaults in V0.1. **D-072** and **D-073** logged.

**D-069 resolved** (2026-09-17, human owner): the high-risk approval clause is **not** a
`ReliabilityContract` field. Approval is a governance concern routed through §29's `autonomy_level`,
with per-step `HUMAN_APPROVAL` and per-tool policy as separate mechanisms. §29 already carries
mission-wide approval, so this removes a duplicate; and an approval-threshold field could not be
built honestly, since "high-risk actions" needs an action-risk notion D-051 left untyped. **This is a
second departure from §30's example, after D-045.** **D-074** logged.

**D-067 resolved** (2026-09-17, human owner): V0.1's `MissionEvent` carries **only the envelope** —
`event_id`, `tenant_id`, `mission_id`, `sequence`, `occurred_at`, `recorded_at`, `type` — with **no
payload field**. §33 names thirteen types and describes no payload; §10 lists an event's fields and
omits payload entirely; and V0.1 emits no events at all. Intended future direction recorded: a typed
discriminated payload keyed by event type, never an untyped mapping. **D-075** and **D-076** logged.

**D-073 resolved** (2026-09-17, human owner): `min_quality`, `max_risk_level` and
`min_independent_evidence` are **required**; the six budgets remain optional per D-065. §30's example
carries all three with no demonstration of omission — the same standard that made budgets optional,
applied to opposite evidence. **`ReliabilityContract` is now fully specified.**

**A broader gap was identified and logged as D-077:** field optionality has never been decided for
`TaskGenome`, `Plan`, `PlanStep`, `MissionEvent` or `MissionState`. It blocks all five.

**Six representation gaps logged as D-078–D-083** (2026-09-17): units for time/token budgets,
`tenant_id` required-vs-defaulted, `capability` representation, `AgentTask.status` representation,
`MissionState` collection shapes and `Plan.version`, and timestamp representation.

**D-077 resolved** (2026-09-18, human owner): the required/optional split for `TaskGenome`, `Plan`,
`PlanStep`, `MissionEvent` and `MissionState`, applying D-065's demonstration-of-omission standard.
Absence and emptiness are separate; `depends_on` is required and may be empty for a DAG root. Four
items split out: **D-084**–**D-087**.

**Representation round resolved** (2026-09-18, human owner) — ten decisions, **D-088**–**D-097**:
`Plan.mission_id` kept required as a deliberate asymmetry with D-068; the genome references its
contract by `ReliabilityContractId`; `MissionEventType` is exactly §33's thirteen; MissionState's
collections and six counters are required, immutable, may be empty, counters non-negative integers;
`StepId` is an opaque string unique per plan version, exempt from D-053's UUID rule; `Plan.steps` is an
immutable ordered collection; `allowed_actions` are opaque strings; A2A ids are external opaque
strings, exempt from D-053; `last_event` is `EventId | None`; `sequence` starts at 1 and
`state_version` tracks the latest applied sequence.

**Three genuine representability gaps surfaced and logged, not decided:** **D-098**
(`latest_artifact`) and **D-099** (`information_dependencies`) are optional fields whose
representation is deferred — but an optional field still needs a type, so each must either be excluded
from V0.1 or given one. **D-100**: by-id reference (D-089) leaves the ReliabilityContract object with
no home in MissionState, whose D-010a field set never held it.

**Representation resolved** (2026-09-18, human owner) — **D-078**–**D-083**, **D-087**, **D-098**–**D-100**:
milliseconds and token counts; `tenant_id` supplied by the single-tenant context; `CapabilityId` and
`ActionId`; `AgentTask.status` an opaque string; `Plan.version` from 1 per mission; timezone-aware UTC
with naive values rejected; empty collections legal; `ArtifactRef | None`; `information_dependencies`
as opaque strings; and **MissionState holds the authoritative `ReliabilityContract`**.

**Final V0.1 blockers resolved** (2026-09-18, human owner): **D-101** — the work-step kind is `agent`;
**D-084** — MissionState is created with its TaskGenome (no §33 event type introduces a genome, so it
must exist from `MISSION_CREATED`); **D-085** — one immutable `execution_id` per mission in V0.1, kept
across replans and pause/resume; **D-086** — `occurred_at` is required, preserving the producer's time
for external events and equal to `recorded_at` for internal ones.

**V0.1 blocking matrix: empty.** All seven contracts — `ReliabilityContract`, `TaskGenome`, `Plan`,
`PlanStep`, `MissionEvent`, `MissionState`, `AgentTask` — are **fully specified and constructible**.

Open items that **touch V0.1 without blocking it**:

| Id | Why it does not block |
|---|---|
| D-032 | the literal default `TenantId` belongs to the single-tenant context (D-079), not to any contract |
| D-036 | `AgentTask.status` is an opaque string, and nothing may branch on it (D-081) |
| D-007 | `CapabilityId` is opaque; the vocabulary is not needed to declare the field (D-080) |
| D-055 | `VERIFY` and `HUMAN_APPROVAL` stay control-flow kinds meanwhile — the conservative position |
| D-037 | D-086 works under a shared event shape; the internal/external split is a V0.6 question |
| D-012 | V0.1 carries no conditional payload (D-047) |

**The consolidated V0.1 contract specification is the approved design baseline** as of 2026-09-16.
Three questions it surfaced but which had never been logged are now Open items: D-067, D-068, D-069.

**D-045 resolved** (2026-09-16, human owner): **every `TaskGenome` must reference a
`ReliabilityContract`.** Without one there is no defined referent for satisfaction, required quality,
or mission-level budgets. This is the one V0.1 decision that departs from a literal reading of the
handoff (§30's "can have"), and is recorded as such. **D-066** logged: user-supplied vs synthesised.

**D-042 resolved** (2026-09-16, human owner): the V0.1 contract budget group is six mission-level
fields — `max_retries`, `max_replans`, `max_agent_calls`, `max_tool_calls`, `max_execution_time`,
`max_tokens` — recorded explicitly as a **reconciliation of the handoff's partial lists, not a
quotation**. No numerical defaults in V0.1. **D-065**, **D-043** and **D-044** left Open.

**All type-level V0.1 blockers are cleared.** **D-056 resolved** (2026-09-16, human owner):
`RiskLevel = low | medium | high`, a closed ordinal word-valued scale. The shape was derived from
D-030, D-051, §53 and invariant 14; the labels `low` and `high` are explicitly ratified additions
completing the handoff-supplied `medium`. Not reused for §40 action risk or §28 tool risk.

**D-053 and D-054 resolved** (2026-09-16, human owner): identifiers are UUID-backed opaque values
with distinct per-kind types, readability handled at the display layer; all contract timestamps are
explicit required inputs, with no model reading the wall clock during construction. Both recorded in
`docs/03_architecture.md` §11 as cross-cutting contract rules.

**D-031 resolved** (2026-09-16, human owner): V0.1's `ReliabilityContract` carries
`min_independent_evidence`; `TaskGenome` does **not** carry `evidence_requirements`, and no
replacement representation is defined. Nothing in V0.1 produces, consumes or checks evidence, and
**D-041** set the precedent by excluding evidence from `MissionState`. The substantive question is
retargeted as **D-070** to V0.4/V0.8.

**D-068 resolved** (2026-09-16, human owner): `TaskGenome` is **mission-owned** and does **not**
carry `mission_id` — containment by `MissionState` is the ownership relationship, and a
back-reference would make a genome/state mismatch representable. **This removes `mission_id` from
the approved consolidated V0.1 specification's `TaskGenome` field list.** **D-071** logged for
detached/reusable genome representations.

**Three field-level items remain for V0.1:** D-065, D-067, D-069.

**D-052 resolved** (2026-09-16, human owner): `MissionStatus` contains exactly `created`,
`completed`, `failed`, `paused`, with `status_reason` carrying the explanation. `PLANNING` and
`EXECUTING` were invented in a draft spec and are **not** added — every handoff-named state is an
entry, exit or suspension boundary, and in-progress substates fall on D-010a's excluded side.
**D-058** and **D-059** left Open.

**D-030 resolved** (2026-09-16, human owner): assessed task risk and tolerated risk are **distinct
quantities**, one field in each model. It was answered by implication by D-051 and was raised and
**ratified explicitly** rather than closed silently. How either value is calculated is out of scope
and recorded as **D-057**.

**D-049 and D-050 are resolved** (2026-09-16, human owner), which unblocks `PlanStep`:

- **D-049** — EIDOS has a **capability-bearing work-step category distinct from control-flow steps**.
  `capability` is required on work steps and absent from control steps. **D-055** left Open: whether
  `VERIFY` and `HUMAN_APPROVAL` are themselves work steps.
- **D-050** — `SEQUENTIAL` and `PARALLEL` are **not canonical `PlanStepKind` values**; ordering and
  parallelism are expressed through dependency edges. They may return later as authoring-surface
  syntax that normalizes to the same DAG with no separate execution semantics.

Both are recorded as **refinements** of D-004 and D-047. **Neither of those has been modified.**

Plus two minor representation questions: **D-053** (identifier representation) and **D-054**
(timestamps as explicit inputs vs clock defaults).

**Standing rule:** no placeholder enum, type, sentinel or inferred value may be invented to make code
compile. An Open item blocks the field it touches; it does not license a guess.

**Three V0.1 scoping decisions also settled** (2026-09-16, human owner): **D-033** (`tenant_id`
root-only), **D-047** (V0.1 Plan DSL defines structure but no predicate language — D-012 stays Open),
**D-048** (`AgentTask` included per §50, minimal, A2A fields optional, `status` open under D-036).

**Resolved so far** (2026-09-16, human owner):

- **D-013** — TaskGenome and ReliabilityContract are disjoint, thresholds are not duplicated, and
  the genome references the contract. Sub-ambiguities D-030 and D-031 left Open; each leaves one
  field undetermined.
- **D-019** — `tenant_id` is present and required on V0.1 root models with a single fixed default,
  and carries **no security meaning**. Sub-questions D-032, D-033 and D-034 left Open.
- **D-011** — layered event model. `event_id` is the idempotency key; EIDOS assigns a monotonic
  per-mission sequence at acceptance, and that sequence orders deterministic replay. No A2A producer
  ordering in V0.1. Sub-questions D-035 through D-038 left Open.
- **D-010a** — MissionState is a **materialized view over the event log**, holding only what the
  runtime must answer synchronously. Per-node runtime execution state stays out. The completeness
  burden shifts to the event log: **an event that is not recorded is not replayable.** Sub-questions
  D-010b, D-039, D-040, D-041 left Open.
- **D-009** — bounds split by category. Shape/complexity limits are **system safety limits**;
  execution budgets are carried by the **ReliabilityContract**. A mission may tighten but never
  exceed the ceiling, and an over-ceiling request is **rejected, never clamped**. **No numerical
  defaults in V0.1.** Sub-questions D-042 through D-046 left Open.
- **D-033** — `tenant_id` is **root-only**: required on TaskGenome, ReliabilityContract, Plan,
  MissionState, MissionEvent; not duplicated on nested PlanStep or AgentTask.
- **D-047** — V0.1 Plan DSL defines the eight step kinds, step IDs, capability, dependency edges and
  DAG structure, and **no predicate language and no conditional payload**. D-012 stays Open as a
  clean V0.2 decision.
- **D-048** — `AgentTask` is included in V0.1 per §50, minimal, with A2A fields optional. No A2A
  behaviour. `status` unconstrained pending D-036, and **nothing may branch on it**.

---

## V0.2 Plan Validation — implemented (2026-09-19)

`src/eidos/validation/` — depends only on the public surface of `eidos.contracts`. Design rulings:
D-104 (`max_depth` counts nodes), D-105 (only *declared* agent calls are checked structurally), D-106
(empty plans are legal), D-107 (JSON text is the untrusted ingress; typed `ValueError` subclasses),
D-108 (`EidosModel` exported), D-109 (shared test factories), D-110 (POLICY is `NOT_APPLICABLE`), plus
D-102 and D-103 from the scoping phase. Engineering contract: `docs/05_plan_dsl.md` §4.

| Module | Role | Tests (file) |
|---|---|---|
| `limits.py` | `SystemLimits` (nine required non-negative ints, **no defaults**), `LimitName`, fixed budget order | 44 (`test_validation_limits.py`) |
| `results.py` | `ValidationStage`, `StageStatus`, `ViolationCode`, `Violation`, `StageResult`, `PlanValidationReport` — model validators make a mislabelled report unconstructible | 54 (`test_validation_results.py`) |
| `graph.py` | Pure iterative algorithms: Tarjan SCC cycles, Kahn topological order, longest chain in nodes, **exact** maximum antichain width (Dilworth / Hopcroft–Karp) | 119 (`test_validation_graph.py`) |
| `stages.py` | `check_dependencies`, `check_cycles`, `check_capabilities`, `check_policy`, `check_resources`, `check_complexity`, `identity_violations` | 79 (`test_validation_stages.py`) |
| `pipeline.py` | `validate_plan_json`, `validate_plan`; stage ordering, skip rules, construction-failure attribution | 62 (`test_validation_pipeline.py`) |
| — | Static guards over the package source | 51 (`test_validation_guards.py`) |

V0.1 additions (D-107, D-108): `DuplicateStepIdError` and `UnknownDependencyError` (both `ValueError`
subclasses, messages unchanged) and the `EidosModel` export; 10 tests. Test infrastructure (D-109): the
shared factories moved from `tests/unit/contracts/conftest.py` to `tests/support/eidos_factories.py`, and
`tests/support` joined pytest's `pythonpath`; the 155 V0.1 tests were unchanged apart from a changed import line.

**What the evidence is.** Every count above was measured by running the suite, not estimated. Graph
algorithms are cross-checked against independent brute-force implementations on 80 seeded random graphs,
including the level-width counterexample (widest level 2, true width 3). 20,000-step chains run under the
default recursion limit. Reports and graph outputs are asserted identical across `PYTHONHASHSEED` values.
The guard tests were mutation-checked: adding a forbidden import, a `600000` literal, a numeric limit
literal, a module-level `SystemLimits`, mutable module state and a self-recursive function each made the
matching guard fail.

**Invariants, honestly.** 4 (ID-addressed DAG, no SEQUENTIAL/PARALLEL kinds), 5 (fixed stage order; a
skipped stage is never accepted), 9 (no model/vendor/SDK name in the package) and 11 (plans checked against
capabilities, never agent names) hold, and are exercised by tests. 7 is enforced **only** for what a static
plan can show — node count, depth, width, declared agent-call count, and contract-versus-ceiling; runtime
exhaustion and pausing for human review are V0.3+. **14 is not exercised**: the POLICY stage reports
`NOT_APPLICABLE` (D-110), so no governance check exists to verify. The determinism half of invariant 14
holds for what does exist (no prompt, model or I/O anywhere in the package).

**No performance figure is recorded.** Two tests assert that a 300-step width computation finishes inside a
deliberately generous 10-second bound; that is a regression tripwire, not a measurement, and no timing is
reported.

**Not built, by decision.** The compiler (V0.3); capability-to-agent availability (V0.4); any policy rule or
policy-injection mechanism (D-110); runtime retry / replan / tool-call / time / token accounting (D-105, D-043);
a capability vocabulary or registry (D-102); a predicate language (D-012, V0.3); LangGraph; a graph library.

**Tracked gaps (not V0.2's to close).** Plan lineage, `plan_id` uniqueness across a mission's plans and
version monotonicity (D-082) belong to the V0.5 reducer — a `Plan` alone cannot be checked for them. The
`risk_level <= max_risk_level` comparison was excluded (D-030, D-057 Open). **D-111** records eight
behaviours the approved design did not specify; each was implemented conservatively and awaits the owner.

---

## V0.3 LangGraph Runtime — complete as scoped (2026-09-20)

**Step 1 — the decision record — is done, Step 2 — the compiled form and `compile_plan` — is implemented,
Step 3 — the runtime and the sequential reference executor — is implemented, Step 4 — the LangGraph backend —
is implemented, and Step 5 — the scenario tests and the close-out — is done** (see "Step 2" to "Step 5" and "V0.3 close-out"
below). Nothing in V0.1 or V0.2 was changed by any of them, and neither the compiler nor the runtime was changed by Steps 4 or 5. The design behind these rulings is the V0.3 exploration (2026-09-19);
LangGraph behaviour cited there came from its documentation and was **unverified** until Step 4 installed and
exercised it (see "Step 4" below).

**Principle:** the Plan DSL remains the source of truth. LangGraph is an execution backend, not the
architectural authority. EIDOS owns Mission → Plan → Validate → Compile → Execute → Verify.

### Approved scope

| Ruling | Decision | Entry |
|---|---|---|
| A1 | Compile only `agent` and `VERIFY`; reject `ROUTE`, `RETRY`, `REPLAN`, `TERMINATE`, `HUMAN_APPROVAL` at compile time. D-012 stays Open. | D-112 |
| A2 | MissionState never enters LangGraph state; LangGraph state is only `outcomes`; a frozen `ExecutionContext`; V0.3 writes nothing to MissionState. **Resolves D-040.** | D-113 |
| A3 | Compiler input is `(Plan, accepted PlanValidationReport)`, with defensive structural re-checks; validation and compilation stay separate authorities. | D-114 |
| A4 | Packages `eidos.compiler`, `eidos.runtime`, `eidos.backends.langgraph`; only the last may import LangGraph. docs/03 amended. | D-115 |
| A5 | LangGraph is an optional extra, also in `dev`; core stays usable without it. | D-116 |
| A6 | Level-synchronous waves; run only if every predecessor `SUCCEEDED`, else `SKIPPED`; independent branches continue; halt after the current level. | D-117 |
| A7 | Seven node statuses; run outcomes `FINISHED` / `FAILED` / `HALTED`; `FINISHED` is not verified success; `HALTED` takes precedence. | D-118 |
| A8 | No automatic retry, no in-run replan; a replan is a caller-supplied new `Plan`. | D-119 |
| A9 | Resume by prior `SUCCEEDED` outcomes; invalid prior state is a `RunRejection`. | D-120 |
| A10 | `Verifier` returns `PASS` / `FAIL` / `INCONCLUSIVE` plus a reason; no scalar. | D-121 |
| A11 | Synchronous ports; explicit, required `AdmissionGuard`; D-018 scoped narrowly. | D-122 |
| A12 | No `MissionEvent`, no MissionState mutation; **invariant 15 is not exercised in V0.3**. | D-123 |
| — | `VERIFY` is a control step compiling to a `VerifyNode`; `HUMAN_APPROVAL` unsupported. A V0.3 implementation decision — **D-055 stays Open.** | D-124 |

New **Open** entries: **D-125** (plan-level `RETRY` versus a future runtime retry policy) and **D-126**
(the `MissionEvent` vocabulary cannot represent local node lifecycle events). New **Deferred** entry:
**D-127** (the explicit deferral list). **Settled V0.1 and V0.2 decisions were not reopened**, and the
handoff was not modified.

### Blocker status

| Blocker (from the exploration's decision audit) | Status |
|---|---|
| B1 — D-012 versus §50's mapping list | **Resolved** by D-112: the four conditional kinds are rejected, not compiled. D-012 stays Open. |
| B2 — D-040, the MissionState / LangGraph split | **Resolved** by D-113. |
| B3 — how plan-level `RETRY` relates to a runtime retry policy | **Deferred and logged** as Open D-125. No effect at V0.3. |
| B4 — D-018, the model/agent interface | **Scoped** to the execution-side port by D-122. D-018 stays Open. |
| B5 — invariant 15 versus the event vocabulary | **Declared not exercised** (D-123); the gap is Open D-126. |
| B6 — D-055 | **V0.3-specific decision** D-124. D-055 stays Open. |
| B7 — invariant 9 versus docs/03's package map | **Resolved** by D-115's layout; docs/03 amended. |

**No architecture blocker remains for starting V0.3 implementation.** D-043, D-058, D-061, D-010b, D-017,
D-039, D-015, D-059, D-046, D-007 and D-020 are not blockers under this scope.

### Proposed in the exploration and **not yet ruled**

These are implementation details, not decisions. Each is to be confirmed or adjusted by the slice that
introduces it, and logged in `decisions.md` if it turns out to matter.

- ~~The compiled form's exact shape and the compile-failure codes~~ — **implemented in Step 2** as
  implementation details (D-112 and D-114 delegate both); see "Step 2" below. The three codes proposed in the
  exploration became eight, for finer diagnostics.
- ~~The `ExecutionContext` field set; the halt-reason set; `RunRejection` codes; the `AdmissionGuard` request
  shape and purity; whether a `FINISHED` run with no passed `VERIFY` node is labelled unverified~~ —
  **implemented in Step 3** as implementation details; see "Step 3" below.
- ~~Whether `eidos.runtime` ships a sequential reference executor~~ — **ruled: D-128.**
- ~~How a backend fault surfaces~~ — **implemented in Step 4** as `BackendError`, an exception; see "Step 4" below.
- ~~The optional extra's name and any version constraint (D-116)~~ — **settled in Step 4**: `langgraph>=1.2.11,<2`.
- ~~LangGraph behaviours to verify by spike~~ — **verified in Step 4** (S1–S10); see "Step 4" below.

### Explicitly deferred (D-127)

D-012 (stays Open); semantics of the five rejected kinds; automatic retries; a planner and the driver loop;
the MissionState reducer and event log; LangGraph checkpointing and interrupts; runtime budget, time and token
accounting; the capability registry; async ports, A2A, MCP and RAG; policy semantics. **Recorded for
visibility:** V0.2's policy stage is `NOT_APPLICABLE`, so plans V0.3 compiles have had no policy evaluation;
only mock agents execute at V0.3, and whether real agents may run before a policy exists is a V0.4 question.

### Step 2 — the compiled form and `compile_plan` (implemented)

`src/eidos/compiler/` — four modules, no LangGraph, no runtime, no I/O; imports only `eidos.contracts`, the
public surface of `eidos.validation` (`PlanValidationReport`), pydantic and the standard library.

| Module | Public names | Tests (file) |
|---|---|---|
| `ir.py` | `CompiledPlan`, `WorkNode`, `VerifyNode`, `CompiledNode`, `SUPPORTED_STEP_KINDS` | 79 (`test_compiler_ir.py`) |
| `results.py` | `CompileReport`, `CompileViolation`, `CompileFailureCode` | 32 (`test_compiler_results.py`) |
| `compile.py` | `compile_plan(plan, validation_report) -> CompileReport` | 125 (`test_compile_plan.py`) |
| — | Static and import guards over the package source | 40 (`test_compiler_guards.py`) |

Test infrastructure added: `tests/support/eidos_compiler_factories.py` (a real-V0.2-report factory, and a
"forged" report factory that gives the compiler evidence which lies). **No existing test was modified.**

**Evidence, not assertion.** Every count above was measured by running the suite (**850 total = 574 + 276**).
The compiler tests were mutation-checked: removing the not-accepted check, the plan-mismatch check, cycle
detection or the unknown-dependency check; compiling non-`VERIFY` control kinds as `VerifyNode`; using a wrong
level formula; keeping repeated predecessors; and accepting a relabelled step each made a test fail (8 of 8).
The guard tests were mutation-checked the same way: a forbidden import, a LangGraph import, a runtime import,
a non-public validation import, a MissionState import, a `set()` call, a dict view, module-level mutable
state, self-recursion, a vendor name and a `print` call each made a guard fail (11 of 11). They found two real
problems while being written — LangGraph named in the compiler's docstrings, and set literals in
`results.py` — both fixed in the source, not the guard.

**Import and dependency guard result:** the compiler imports no LangGraph, no runtime, no backend, and nothing
that does I/O, reads a clock, draws randomness or holds process state. `import eidos.compiler` loads neither
`langgraph` nor `eidos.runtime` (checked in a fresh interpreter). `contracts` and `validation` do not import
the compiler. The compiler touches none of `MissionState`, `MissionEvent`, `AgentTask`, `TaskGenome` or
`ReliabilityContract`.

**Implementation details chosen (not decisions; none touches an invariant).** D-112 and D-114 explicitly leave
the compiled form's shape and the failure codes to implementation, so no new `decisions.md` entry was made.

- Nodes carry a `kind` discriminator reusing `PlanStepKind`, so the union round-trips through JSON.
- A node's predecessors are unique; the compiler collapses a repeated `depends_on` entry (the same edge) and the
  model rejects a repeated one. Predecessors keep `depends_on` order.
- The compiled form's identifiers are required (no default tenant), unlike `Plan`'s.
- **All** violations are reported together (evidence, then structure, then step kinds), not only the first.
- Eight failure codes (see `docs/05_plan_dsl.md` §4). Something that is not a `PlanValidationReport` counts as
  missing evidence. A control kind that is not `VERIFY` is unsupported by default, so a kind added to
  `PlanStepKind` later is rejected until deliberately supported.
- `MALFORMED_STEP` covers a step whose kind and shape disagree (reachable only by bypassing `Plan`
  construction) so that no capability is ever silently stripped.
- A cycle violation names the steps **on, or downstream of**, a cycle, not the exact cycle members — the
  compiler computes levels with its own Kahn pass rather than reusing V0.2's `graph` module, which is not part
  of `eidos.validation`'s public surface.

**Not done in Step 2, by scope:** execution of any kind (Step 3 followed) and LangGraph.

### Step 3 — the runtime and the sequential reference executor (implemented)

`src/eidos/runtime/` — six modules; imports only `eidos.contracts`, the public surface of `eidos.compiler`,
pydantic and the standard library. Ruled by **D-128** (the reference executor is part of V0.3).

| Module | Public names | Tests (file) |
|---|---|---|
| `results.py` | `NodeStatus`, `NodeResult`, `RunOutcome`, `HaltInfo`, `RunResult`, `PriorOutcomes`, `RunRejectionCode`, `RunRejection` | 73 (`test_runtime_results.py`) |
| `context.py` | `ExecutionContext`, `context_from_state` | 34 (`test_runtime_context.py`) |
| `ports.py` | `WorkExecutor`, `Verifier`, `AdmissionGuard`; `WorkResult`, `WorkStatus`, `VerificationResult`, `VerificationVerdict`, `AdmissionRequest`, `AdmissionDecision`, `AdmissionOutcome` | 37 (`test_runtime_ports.py`) |
| `preconditions.py` | `check_run_preconditions` | 42, with the executor (`test_runtime_prior.py`) |
| `executor.py` | `SequentialExecutor` | 178 (`test_runtime_executor.py`) |
| — | Static and import guards over the package source | 67 (`test_runtime_guards.py`) |

Test infrastructure added: `tests/support/eidos_runtime_factories.py` (scripted, recording ports and builders).
**No existing test was modified, and the compiler package was not changed.**

**Exact semantics implemented** (`decisions.md` D-117 to D-124; also `docs/03_architecture.md` §12):

- Levels come from the compiled plan and are never recomputed. Levels run in order; within a level, nodes run in
  ascending plan position; every node of a level is resolved before the next begins.
- A node is ready when all predecessors are settled in any status. It executes only if every predecessor
  `SUCCEEDED`; otherwise it is `SKIPPED` without dispatch and without being put to the guard. Independent
  branches continue after a failure. Nothing is retried; a node is dispatched at most once per run.
- Work results map `PRODUCED` → `SUCCEEDED`, `FAILED` → `FAILED`, `NO_RESULT` → `NO_RESULT`. A `VERIFY` node calls the
  verifier once with its predecessors' results: `PASS` → `SUCCEEDED`, `FAIL` → `VERIFICATION_FAILED`,
  `INCONCLUSIVE` → `VERIFICATION_INCONCLUSIVE`. A port that raises, or returns something that is not its typed
  result, yields `FAILED` — never a pass, never an inconclusive verdict.
- The guard is asked once per node that would be dispatched, with `(step_id, level, rank_in_level,
  dispatched_before_level)`. A `HALT` leaves the node `NOT_REACHED`; the rest of the level is still asked and
  resolved; every later level is then `NOT_REACHED` and the run is `HALTED`. A guard that raises or answers with
  anything else **fails closed** (halts).
- `HALTED` takes precedence. `FINISHED` is not verified success: `RunResult.verified` is true only for a
  finished run with a succeeded `VERIFY` node.
- Prior outcomes: `SUCCEEDED` nodes are carried over and never redispatched; anything else, an unknown step, a
  wrong kind, a contradiction with the plan's edges or another execution's identity is `INVALID_PRIOR_STATE`.
  Context mismatches are `WRONG_TENANT` / `WRONG_MISSION` / `WRONG_PLAN` / `WRONG_PLAN_VERSION`, checked first, in
  that order. All rejections are returned, never raised.
- MissionState is only *read*, once, by `context_from_state`, to build a frozen six-field `ExecutionContext`
  (identity, plan identity, `TaskGenome`). Nothing is written, and no `MissionEvent` exists in the runtime
  (D-123): **invariant 15 is not exercised**.

**Evidence, not assertion.** Every count above was measured by running the suite (**1,281 total = 850 + 431**).
Statuses on 60 seeded random plans are compared with an independent recursive computation, including dispatch
order, at-most-once dispatch and outcome; 40 more check the halting invariants, and a further test proves both
halted and unhalted runs occur. Results are asserted byte-identical across `PYTHONHASHSEED` values. The
executor and preconditions were mutation-checked: fail-open guard, retry, immediate halt, fail-fast, prior
redispatch, ordering by name, ignoring levels and 9 more executor breaks, plus 4 precondition breaks — **17 of
17** made a test fail. The guard tests were mutation-checked the same way — 23 violations (forbidden and
LangGraph imports, MissionEvent, MissionState outside `context.py`, a `while` loop, `async`, a bare
`except`, a set, a dict view, `model_copy`, runtime accounting, a concrete guard and more) — **23 of 23** were
caught. Writing them found three real problems, all fixed in the source, not the guard: LangGraph named in
the docstrings, protocol names in a docstring, and a level assigned by name.

**Import and dependency guard result:** the runtime imports no LangGraph, no backend package, and nothing that
does I/O, reads a clock, draws randomness or holds process state. `import eidos.runtime` loads neither
`langgraph` nor `eidos.backends` (checked in a fresh interpreter). No lower layer — contracts, validation,
compiler — imports the runtime. `MissionState` is imported only by `context.py`; `MissionEvent`, `AgentTask`
and `ReliabilityContract` by nothing. There is no `while` loop, no `async`, no default guard and no runtime
accounting.

**Implementation details chosen (not decisions; none touches an invariant).**

- A `NodeResult` carries `step_id`, `kind`, `status`, `artifact`, `reason`. A **usable result** is an opaque
  `ArtifactRef` the executor reported as produced (no artifact model exists, D-098); a succeeded work node
  carries its artifact, a succeeded `VERIFY` node carries the verifier's reason and no artifact, and every
  non-success states why. `NO_RESULT` belongs to work nodes and `VERIFICATION_*` to verify nodes; a verifier
  fault is `FAILED`.
- `RunResult` carries identity, `outcome`, `halt`, `results` (plan order) and `dispatched` (dispatch order).
  `HaltInfo` is the first denied node, its level and the guard's own reason as free text — there is no
  halt-reason enum. A node carried over from prior outcomes is `SUCCEEDED` in `results` and absent from
  `dispatched`, so a resumed run's result says exactly what it did.
- `run` returns `RunResult | RunRejection`, never raising; a rejection carries one code — the first failing
  check — and, for prior state, the steps concerned.
- `PriorOutcomes` carries identity so it cannot be applied to another execution or plan version. It may hold any
  status, so the executor — not the type — rejects a non-`SUCCEEDED` one; `succeeded_from(RunResult)` is the
  caller's explicit selection of successes.
- `AdmissionRequest.rank_in_level` counts only the nodes of that level that will be dispatched; nodes that are
  skipped or already settled by prior outcomes are not counted. `dispatched_before_level` counts only this run's
  dispatches.
- `SequentialExecutor` is a frozen dataclass of three required keyword-only ports, and keeps no state between
  runs. The preconditions live in their own module so every backend applies the same ones.
- The `ExecutionContext` checks that its genome belongs to its tenant. `context_from_state` takes the plan
  identity from the compiled plan and does not look the plan up in `state.plans`.

**One gap the specified signature exposes — logged as Open D-129.** The work port is `execute(context, node)`,
so a work node is not told what its predecessors produced; only the verifier is. In V0.3 an edge into a work
node carries ordering only. That is harmless with scripted doubles and matters as soon as real agents exist.

**Not done in Step 3, by scope:** LangGraph and its dependency, any backend, real or production mock agents (the
work executor is exercised only with scripted test doubles), A2A, MCP, model providers, events, MissionState
mutation, the reducer, checkpoints, automatic retry, in-run replanning, runtime clock, token or budget
accounting, the policy engine and a planner or driver loop.

### Step 4 — the LangGraph dependency, the spike, the adapter and conformance (implemented)

**The dependency (D-116).** `pyproject.toml` gains the optional extra `langgraph = ["langgraph>=1.2.11,<2"]`; `dev`
includes it as `eidos[langgraph]`; the base `dependencies` still hold only `pydantic>=2`. LangGraph **1.2.11** was
installed for the first time here. It has six direct requirements (`langchain-core`, `langgraph-checkpoint`,
`langgraph-prebuilt`, `langgraph-sdk`, `pydantic`, `xxhash`) and a **dependency closure of 38 distributions** (32 beyond `langgraph` and the `pydantic` family EIDOS already needs; measured with `importlib.metadata`), including `langsmith`,
`httpx`, `websockets`, `orjson` and `zstandard` — heavy for a graph runner. `Requires-Python` is `>=3.10`; only Python
3.12.10 was exercised, so 3.11 and 3.13 are **untested**, not confirmed.

**The spike — what LangGraph 1.2.11 actually does** (`tests/integration/langgraph/test_langgraph_spike.py`, 41 tests). Every
assumption the design rested on held, so nothing contradicted D-113 or D-117:

| # | Finding |
|---|---|
| S1 | A list-form join fires once, after all predecessors, whatever they recorded. A node that returns `None` or `{}` still triggers its successors. |
| S2 | Nodes of one super-step read a start-of-step snapshot and never see each other's writes. A disjoint-key reducer is order-independent; a key written twice raises. |
| S3 | Several entry edges and terminal nodes compile without `END`. **An empty graph is refused**, so an empty plan is answered without one. **`__start__`, `__end__` and any name containing `:` or `|` are rejected**, so nodes are named by plan position. |
| S4 | The minimum `recursion_limit` for a chain of n nodes is n + 1, settable per invocation. **The default is 10,007, read from an environment variable — not the documented 1,000.** |
| S5 | A graph runs with `checkpointer=None`, no `thread_id`, and keeps nothing between runs. |
| S6 | Footprint and Python support as above; `pyproject.toml` declares the extra as specified. |
| S7 | A level's nodes run **concurrently on worker threads** (a 3-way barrier releases), so ports must be thread-safe. Nodes of different levels never overlap. |
| S8 | A raising node is called once, is not retried, and its error propagates unchanged (with a note added). |
| S9 | An ordinary run makes no network call. |
| S10 | **With `LANGSMITH_TRACING` set in the environment, a bare LangGraph run POSTs every node's inputs and outputs to `api.smith.langchain.com`.** `tracing_context(enabled=False)` switches it off, in every worker thread. |

**Two surprises the documentation did not warn about.** The default recursion limit differs from the documented one
and comes from the environment, so the adapter always passes its own. And `langsmith`, pulled in by LangGraph,
registers a **pytest plugin** that would load into every test session; `pyproject.toml` now disables it
(`addopts = "-p no:langsmith_plugin"`), and a test proves a core session loads no part of the LangGraph family.

**The adapter** (`src/eidos/backends/langgraph/`: `executor.py`, `errors.py`, `__init__.py`; and `eidos/backends/__init__.py`).
`LangGraphExecutor` has the reference executor's signature and contract. It builds a fresh graph per run: one node per
compiled node named `n<position>`, roots off `START`, one list-form join per multi-predecessor node. LangGraph's
super-steps *are* EIDOS's levels. **The graph state is `outcomes` and nothing else (D-113)**; the context, plan and ports are
closed over. Everything a node decides — skip, guard, halt, dispatch — is a pure function of the start-of-step snapshot
and the static plan, by the same rules as the reference. Dispatch order, the halt and the outcome are derived from the
final outcomes, never from completion order. There is no checkpointer, `thread_id`, interrupt, retry policy, streaming or
store (D-127). A fault in LangGraph or the adapter raises `BackendError`; a port fault, a bad plan or a rejected run never
does. **Tracing is forced off, with no opt-in (D-130, Accepted)**.

| Where | What | Tests (file) |
|---|---|---|
| `tests/integration/langgraph/` | The spike | 41 (`test_langgraph_spike.py`) |
| | Conformance: 54 shaped scenarios, 9 rejections, resume chains, **150 seeded random plans**, concurrency perturbation | 222 (`test_langgraph_conformance.py`) |
| | The adapter itself: graph shape and state, what enters LangGraph, recursion limit, `BackendError`, no retry, no network, no tracing, determinism | 42 (`test_langgraph_backend.py`) |
| `tests/unit/backends/` | Static and import guards; core works with LangGraph blocked | 48 (`test_backends_guards.py`) |

Test infrastructure added: `tests/support/eidos_backend_factories.py` (lock-recording doubles and `conform`, which runs both
executors on identical inputs and asserts they agree exactly). **No existing test, and no earlier source file, was modified.**

**Evidence, not assertion.** Every count was measured (**1,634 total**). In every conformance scenario the
LangGraph result is **equal to, and serializes to the same bytes as**, the reference executor's; ports are compared as sets of
facts, never as an ordered log, because concurrent calls have no order. A test proves the random comparison covers every
node status, every run outcome, rejections and resumed runs. Results are identical across `PYTHONHASHSEED` values and equal to
the reference in each. The adapter's behaviour was **mutation-checked, 16 of 16 mutations caught**, and its static guards **17 of 17**; afterwards,
removing the tracing protection was caught by both an integration test and a guard.

**Core stays usable without LangGraph (D-116), demonstrated.** All **1,329 unit tests pass in a process where importing
`langgraph`, `langchain`, `langchain_core` or `langsmith` is impossible**, and none of them is loaded. Importing the adapter
without the extra raises an `ImportError` that says `pip install 'eidos[langgraph]'`.

**Implementation details chosen (not decisions; none touches an invariant).**

- `BackendError` is an exception, chained from the original. Everything a run can legitimately produce is typed and returned.
- The recursion limit is the plan's depth plus 2: the measured minimum overhead is 1, and one step of margin cannot make a
  validated acyclic plan loop.
- The guard is asked once per node that would be dispatched, by that node's own wrapper. `rank_in_level` and
  `dispatched_before_level` are counted from the recorded outcomes, so the answer does not depend on scheduling. The first
  denied node is recovered from the final outcomes by its `NOT_REACHED` reason, whose prefix is pinned to the reference by
  the conformance tests.
- Cost is quadratic in node count in the worst case (each wrapper scans the recorded outcomes). Plans are bounded by
  `max_nodes` (V0.2), so this is a bound, not a scaling target. A 10,000-step chain is also quadratic inside LangGraph's
  own state merge and is not run in the tests.
- The ports must be thread-safe: LangGraph runs a level's nodes on worker threads.

**Decided: D-130 (Accepted, 2026-09-20).** LangGraph's ambient tracing would export a mission's data to a third party if an
environment variable said so. The owner accepted the adapter's behaviour as written: tracing stays **off** in V0.3, with **no
opt-in**. Any later export of run data is a separate decision (telemetry proper is V0.9). D-129 stays Open.

**Not done in Step 4, by scope:** scenario tests (whole missions), real or production mock agents, A2A, MCP, model
providers, events, MissionState mutation, the reducer, checkpoints, automatic retry, in-run replanning, runtime accounting, the
policy engine, and a planner or driver loop. LangGraph checkpointing, interrupts, retry, streaming and stores are **not used**.

### Step 5 — scenario tests and the close-out (done)

`tests/scenarios/` now holds **49 tests** in five files. Each drives a real `MissionState` through V0.2 validation, the compiler, a
frozen execution context and **both** executors (`tests/support/eidos_scenario_factories.py`, whose `drive` asserts the LangGraph
backend returns exactly what the reference executor does), and asserts what the run *should* have been, written out by hand. Work,
verification and admission are scripted test doubles. **Nothing in `src/` was changed by Step 5.**

| File | Tests | What a scenario proves |
|---|---|---|
| `test_v03_baseline_mission.py` | 7 | A mission goes from state to a finished, verified run; ports are asked only what the plan requires; MissionState is read and never written; a finished run with no `VERIFY` is unverified; the empty plan; wide plans; repeatability |
| `test_v03_verification_and_replanning.py` | 11 | Failed, inconclusive and crashed verification fail the run (invariant 12); no usable result and a crashing agent are contained; a replan is a new, separately validated plan version with lineage and a reason, and nothing carries over from the old run |
| `test_v03_halt_and_resume.py` | 9 | An exhausted budget halts and pauses, never loops or truncates (invariant 7); halt outranks failure; a broken guard fails closed (invariant 14); resume over succeeded outcomes equals an uninterrupted run; no automatic retry |
| `test_v03_plan_gates.py` | 19 | Rule-breaking plans, non-DSL documents and unsupported step kinds are stopped before any executor is reached (invariants 3, 5, 13); a forged acceptance does not compile a broken plan |
| `test_v03_determinism.py` | 3 | A whole story (fail, replan, halt, resume) serializes to identical bytes under different `PYTHONHASHSEED`s |

**Evidence.** All **1,683** tests pass (measured). The scenarios were mutation-checked: **16 of 16 mutation runs were caught.** Eight broke
code the two executors share (the `verified` rule, the plan and prior-outcome preconditions, the compiler's evidence checks, the cycle
stage, the depth limit, what a resume carries); four broke the reference executor alone (caught by the conformance check inside `drive`);
four broke both executors identically, so only the hand-written expectations could catch them, and they did (a failing guard admitting,
an inconclusive or failed verdict counting as a pass, nothing skipped behind a failure).

**Findings the scenarios pinned (existing behaviour, not new decisions).**

- A node blocked by a failed predecessor is skipped **without being shown to the guard**, so a halt can only occur at a node that would
  otherwise have run. A `HALTED` run that also contains a failure needs a node the failure did not block.
- A guard's counts (`rank_in_level`, `dispatched_before_level`) cover **this run only** and exclude nodes carried over from prior outcomes.
  A budget spanning a pause and its resumption is therefore the caller's to supply; the runtime keeps no accounting across runs
  (D-043 and D-127, unchanged).
- A plan cannot reuse its predecessor's work. Prior outcomes belong to one plan (D-120), so a replanned plan runs from its own start, and
  a stale context or another plan's outcomes is a typed `RunRejection`, never adapted.
- A cyclic plan given a forged acceptance is refused by the compiler with `DEPENDENCY_CYCLE`; a cyclic plan given its honest report is
  refused with `VALIDATION_NOT_ACCEPTED` **and** `DEPENDENCY_CYCLE` (D-114's defensive re-check reports both).
- `tests/scenarios/README.md` asks scenarios to assert on the recorded *event* history. No events exist in V0.3 (D-123), so the
  scenarios assert on the `RunResult` and the port records instead; the README now says so. This is a consequence of D-123, not a new decision.

### V0.3 close-out

**Definition of done (CLAUDE.md §5), checked.** Implementation exists in `eidos.compiler`, `eidos.runtime` and `eidos.backends.langgraph`.
Tests exist at every layer: unit (compiler, runtime, guards), integration (real LangGraph 1.2.11: spike, conformance, adapter),
scenarios. All 1,683 pass; the 1,329 unit tests also pass with the LangGraph family blocked. Integration works: a validated plan
executes on LangGraph and matches the reference executor byte for byte. Failure cases are covered: rejections, faults, halts, resumes,
verification failures. Documentation matches the implementation (D-130 accepted and recorded; D-116 annotated). A git checkpoint exists for
every step.

**Invariants, honestly.** Exercised by V0.3 code and tests: 1 and 2 (MissionState is read once and never written), 3 (only the bounded
Plan DSL is accepted), 4 (the compiled form is the ID-addressed DAG), 5 (nothing executes unvalidated), 6 (a replan is a new plan version
with lineage; lineage validation across a mission's plans is the V0.5 reducer's concern, D-119), 9, 10 and 11 (no model, vendor or domain
in the runtime; plans request capabilities), 12 (verification is separate from completion), 14 (the admission guard is code and fails
closed), 18 (identifiers are in every model). Exercised in part: 7 (V0.2 enforces the node, depth and parallel-branch limits; at run time
only an admission halt exists, and the other budgets are deferred, D-127). **Not exercised, by ruling:** 8, 15 and 16 (no events, no replay, no
evidence lineage — D-123, D-126), 13 as a run outcome and 17 (no reliability-contract or estimate machinery until V1.2 and later).

**Against the handoff's V0.3 line (§50): "Map SEQUENTIAL, PARALLEL, ROUTE, VERIFY, RETRY, REPLAN into runtime nodes. Use mock agents
initially."** SEQUENTIAL and PARALLEL are the dependency structure of the DAG, executed level by level (D-117). VERIFY is a control node
(D-124). **ROUTE, RETRY and REPLAN are not mapped:** D-112 makes the compiler reject them, because their conditions have no defined form
(D-012, Open) and the handoff never relates plan-level retry to runtime retry (D-125, Open). **"Mock agents": none exist as product code.**
Every work node is executed by a scripted test double, which satisfied D-127's "only mock agents execute at V0.3", but a mock agent that can
be imported from `src/` was never built; whether V0.4 needs one is the owner's to say.

**What V0.4 inherits.** A runtime whose ports take a work executor, a verifier and an admission guard; a work port that passes a node no
predecessor outputs (D-129, Open); no capability registry (D-007); no policy engine, so plans V0.3 compiles have had no policy evaluation
(D-110, D-127).

### Sequence (proposed; each step after 1 needs the owner's go-ahead)

1. **Record the rulings.** *Done.*
2. **The compiled form, compile failures and `compile_plan`, with tests.** *Done.*
3. **Runtime types, `ExecutionContext`, ports, admission, prior outcomes and the sequential reference executor.** *Done* (D-128).
4. **The optional extra, the LangGraph spike, the adapter, and conformance with the reference executor.** *Done.*
5. **Scenario tests over whole missions, and the V0.3 close-out.** *Done.*

---

## V0.4 Real Local Agents — complete as scoped (2026-09-21)

**Step 1 — the exploration and the decision record — is done.** The exploration was read-only. The owner accepted Q1–Q15 with rulings, and
they are recorded as **D-131 to D-140 (Accepted)**. **D-006** (which capabilities exist) and **D-018** (where the model boundary lives) are
**resolved** and moved to Accepted. **D-007, D-012, D-055, D-125, D-126 and D-129 stay Open**, each annotated where a ruling touches it. Three
questions the rulings created were logged as D-141, D-142 and D-143 and then **resolved by the owner** as **D-144, D-145 and D-146** — see below.

### Approved scope

| Q | Ruling | Entry |
|---|---|---|
| Q1, Q2 | A fixed, hand-authored plan — Research, Analysis, `VERIFY` — over a supplied `TaskGenome`, run once (validate, compile, execute on LangGraph) with a real local model behind the model seam. Nothing generates plans: no planner, no candidate strategies, no system-driven replan. The runner is one small module, no CLI, no API. Exactly three logical agents. | D-131 |
| Q3 | Five capability IDs, exactly those under "Required capabilities" in §43: `Architecture`, `Security`, `Cost`, `Research`, `Verification` — **V0.4 only; D-007 stays Open.** Resolves D-006. | D-132 |
| Q4 | `VERIFY` uses the `Verifier` port and is bound by node kind, not capability. D-055 stays Open. | D-133 |
| Q5 | A registry resolves a capability to an agent; a descriptor is `agent_id`, version and capabilities only; an unbound capability is a typed pre-run rejection; V0.2 is unchanged. | D-134 |
| Q6 | `eidos.agents` owns a synchronous `ModelPort`; adapters live in `eidos.providers`; model, generation parameters and timeout are explicit, never defaulted. Resolves D-018. | D-135 |
| Q7–Q9 | Standard-library HTTP, no new dependency; installing the runtime and choosing a model are the owner's; the default suite is offline with a fake model, and real-model tests are an explicit opt-in, never a silent skip. | D-136 |
| Q10, Q11 | An in-memory artifact store under `(execution_id, step_id)`, one primary artifact per work step; `ArtifactRef` stays opaque; the `WorkExecutor` signature is unchanged; Research reads supplied documents. **D-129 stays Open.** | D-137 |
| Q12 | The verifier is a deterministic rule set returning `PASS`, `FAIL` or `INCONCLUSIVE`; no model gives a verdict. D-015 stays Open. | D-138 |
| Q13 | `ExecutionContext` carries the frozen `ReliabilityContract`; no universal output or answer field; D-041 not reopened. | D-139 |
| Q14, Q15 | Agents are read-only, no tools, no side effects; the `AdmissionGuard` stays explicit and caller-supplied, no production default; D-043 and D-046 stay Open. | D-140 |

### The three follow-up rulings (D-141 to D-143 resolved)

| Resolved | Ruling | Entry |
|---|---|---|
| D-141 | The V0.4 IDs are exactly `architecture`, `security`, `cost`, `research`, `verification` (lowercase; V0.4 only, D-007 stays Open). The Research Agent serves `research`; the Analysis Agent serves `architecture`, `security` and `cost`; the Verification Agent is reached through the `Verifier` port by `VERIFY` node kind and is not capability-bound. `verification` is a vocabulary member no work agent serves. | D-144 |
| D-142 | A minimal typed artifact model: `ref`, `content_type`, `content`, `source_refs`; primarily text or Markdown plus source references. Supplied documents are stored and addressed by `ArtifactRef`, namespaced by execution. No per-step input field. Research and Analysis read supplied and predecessor artifacts through the in-memory store; the `WorkExecutor` signature is unchanged. | D-145 |
| D-143 | Only clauses with an explicitly defined deterministic measurement are evaluated: schema validity, citation and source coverage, minimum distinct sources. `min_quality` is explicitly `NOT_EVALUATED`; no quality metric is invented. A `PASS` means the supported V0.4 rules passed, not that every clause was evaluated. By the same rule `max_risk_level` is also `NOT_EVALUATED` (D-057). | D-146 |

Also still Open, unchanged: D-007, D-012, D-015 (answered for V0.4 only), D-017, D-020, D-041, D-043, D-046, D-055, D-059, D-063 and D-064 (dormant: no scalar),
D-125, D-126 and D-129 (answered for V0.4 only).

### Implementation sequence

Each step is one component, one change and one acceptance condition (CLAUDE.md §4). Each ends with tests, an update of this file and `decisions.md`, and its own
commit; nothing is pushed until the owner says so. A step that makes a behavioural choice the rulings did not specify logs it as an **Open** entry, as V0.2's D-111 did.
Only Step 2 touches V0.1–V0.3 code; every other step is additive.

| Step | What | Decisions | Gate | Proves (including failure paths) |
|---|---|---|---|---|
| **1** | Record the rulings | D-131–D-146 | — | **Done** |
| **2** | `ExecutionContext` gains the frozen `ReliabilityContract`; `context_from_state` reads it once; the context's tenant, contract and genome must agree. Amends `src/eidos/runtime/context.py`, `tests/unit/runtime/test_runtime_context.py` and the `context_for` factory in `tests/support/eidos_runtime_factories.py` (the only places a context is built directly) | D-139 | none | Six-field pins updated because the specification changed (not to get green); mismatched contract rejected; MissionState still read once and never written; LangGraph state still only `outcomes`; conformance still byte-identical **Done** — 4 tests added (1,687 in all); 4 of 4 mutations of the new rules caught; conformance still byte-identical |
| **3** | The model seam: package `eidos.agents` created with only `ModelPort`, its typed request (explicit model, generation parameters, timeout), response (text plus measured facts) and failure types; a scripted fake model as test support | D-135 | none | Typed failures for timeout, outage and malformed or empty output; nothing defaulted; agents vendor-free; core layers import nothing new **Done** — package `eidos.agents` created with only the model seam; 56 tests; 10 of 10 mutations caught |
| **4** | `eidos.capabilities`: the five names, the agent descriptor, a deterministic registry, binding, and the typed pre-run rejection for an unbound capability | D-132, D-134, D-144 | none (D-141 resolved) | Exact-string matching; an unbound capability and a duplicate registration are refused; V0.2 unchanged; invariant 11 **Done** — 56 tests (1,799 in all); 12 of 12 mutations caught |
| **5** | The in-memory artifact store and the artifact content types | D-137, D-145 | none (D-142 resolved) | Thread-safe under concurrent writers; one artifact per key; a missing predecessor artifact and a cross-execution read are refused **Done** — `Artifact` (ref, content_type, content, source_refs) and the thread-safe in-memory store; 9 of 10 mutations caught, the tenth (a lock-free read) is an equivalent mutant under CPython that no test can observe |
| **6** | The three agents, against the fake model: Research and Analysis (read supplied or predecessor artifacts, call the model, produce a typed artifact) and the deterministic Verification rule set implementing `Verifier` | D-135, D-137, D-138, D-140, D-145, D-146 | none (D-142, D-143 resolved) | Malformed model output; a model outage; missing input; `PASS`, `FAIL` and `INCONCLUSIVE` each reachable; well-formed output that fails verification (docs/12, invariant 12); a static guard that agents do no I/O beyond their ports **Done** — `ResearchAgent`, `AnalysisAgent` and the deterministic `VerificationAgent` (rules: schema_validity, citation_coverage, minimum_distinct_sources; `min_quality` and `max_risk_level` NOT_EVALUATED); 77 tests (61 behaviour, 16 guard checks; 1,905 in all); 23 of 23 mutations caught |
| **7** | The dispatcher (a `WorkExecutor` over the registry), `VERIFY` bound by kind, and the single-pass runner (one module, name recorded in docs/03); scenarios on both backends with the fake model | D-131, D-133, D-134, D-140 | none new | Baseline finishes verified; verification fails; a model outage fails one node and the rest is contained; an unbound capability stops the run before dispatch; an admission halt; a second, different-domain mission (invariant 10); one implementation substituted for another (invariant 9); byte-identical results on both backends **Done** — `eidos.baseline`: `run_baseline`, `WorkDispatcher`, `BaselineReport`; 30 unit tests, 24 scenario tests on both backends and 2 determinism tests (1,961 in all); 11 of 11 mutations caught |
| **8** | `eidos.providers`: one adapter for the local model runtime over standard-library HTTP with explicit configuration, tested against a local fake HTTP server; an opt-in real-model marker; then **one real baseline run** | D-135, D-136 | **owner installs the runtime and chooses a model** | Success, timeout, refused connection, non-success status, malformed body; the real run's model, latency and verdict recorded **only from that run** **Done (2026-09-21).** The adapter `eidos.providers.OllamaModel`, the fake-runtime tests (47 integration tests, 15 guard checks; 18 of 18 mutations caught), the `real_model` marker and the opt-in tests were written first. The owner then ran the two opt-in tests once against `qwen3:4b`: the provider test passed with a typed response, and **the baseline mission `FAILED` (`verified` false) because the Research step's one model call returned no text (`empty_response`); the verifier was never reached.** Recorded exactly in "The first real baseline run"; the cause was then established by one owner-directed raw-response diagnostic (D-149: the reasoning model spent its whole output budget before answering) and D-150 (resolved: (a′) and (c) adopted) followed. The committed opt-in test (4,096 tokens, 240 s) was then run once and **the baseline finished with a verifier PASS** ("The committed real-model run"), which meets the step's real-run condition. |
| **9** | Close-out: final guards (a vendor name only in `eidos.providers`; agents read-only; core layers import none of the new packages), docs, this file, the definition of done, and which invariants are and are not exercised | — | — | Full suite; unit suite with LangGraph blocked; import audit; frozen paths untouched **Done (2026-09-21)** — see "V0.4 close-out review". |

### The first real baseline run (owner-run, 2026-09-21)

The owner installed the runtime, pulled the model and ran the two opt-in tests once: `python -m pytest -m real_model -s tests/integration/providers/test_ollama_real.py`.
Nothing here was run by Claude Code; it is recorded from the output the owner pasted. **The agents, the verifier, the adapter and the tests were not changed to
make the model pass.**

**What was run** (from the printed output): model `qwen3:4b`; generation temperature 0.0, seed 7, `max_output_tokens` 512; timeout 120.0 s per call. The test does not
record whether the GPU was used or how it was configured, and none of that is claimed.

**What the runtime reports about that model** (metadata Claude Code queried after the run with `ollama --version`, `ollama list` and `ollama show`; no inference):
Ollama 0.34.2; `qwen3:4b`, id `359d7dd4bcda`, 2.5 GB; architecture `qwen3`, 4.0B parameters, quantization Q4_K_M; capabilities `completion`, `tools` and `thinking`.
A tag can be re-pointed; the id is what identifies what was pulled.

**Result, as printed:**

| | Provider test | Baseline test |
|---|---|---|
| pytest | passed | passed |
| Model calls | 1 | 1 |
| Call result | `response`, 5 characters | `failure`: `empty_response`, "the model returned no text" |
| Prompt tokens | 30 | not recorded (a failure carries no measured facts) |
| Output tokens | 154 | not recorded |
| Elapsed | 10.156 s (printed as `10.15600000001723`) | not recorded |
| Mission | — | outcome `failed`, `verified` false |
| Steps | — | `gather` `no_result`, `analyse` `skipped`, `check` `skipped` |
| Reason on the last step (`check`) | — | "not dispatched: predecessor(s) did not succeed: 'analyse' (skipped)" |

Both tests together: **2 passed in 38.55 s** (pytest wall-clock, including whatever the runtime spent loading the model; not divided between the tests).

**What this establishes, and no more.**

- The provider works against a real runtime: one real HTTP round trip returned a typed `ModelResponse` with the runtime's own token counts.
- The baseline test passed because it asserts **structure only** (a `RunResult` came back). **It did not show the baseline succeeding and must not be read that way.**
  The mission failed, and correctly: the Research step got no text from the model, so it produced nothing (`NO_RESULT`); EIDOS did not fabricate an answer or count
  "an agent returned something" as success; nothing downstream ran on nothing; `verified` is false. That is invariants 12 and 13 holding against a real model.
- **The deterministic verifier was never reached in this run.** No real model output had been checked by it as of this run (a later run, D-150 option (a′), changed that): there is no real `PASS`, `FAIL` or `INCONCLUSIVE`, no citation
  coverage and no distinct-source count. Nothing about the quality of any model's output exists, and no quality metric was invented.
- Only the last step's reason was printed, so the Research step's own reason text is not in this record.

**Measured, and not measured.** One latency exists: the trivial completion, 10.156 s for 30 prompt tokens and 154 output tokens. **No throughput is derived from it:**
the elapsed time includes anything the runtime did before generating (for example loading the model on a first call), which the run did not separate. Not measured: any
latency for the baseline's call, repeatability (one run, one seed), behaviour under a different output budget, whether the GPU was used, and quality of any kind. Some of
these were later observed by the D-149 diagnostic, below.

**Observed first; the cause was established afterwards.** The trivial completion used 154 output tokens for a 5-character answer, and the baseline's Research call
returned no text. The runtime lists a `thinking` capability for this model and the adapter reads only the `response` field, so the candidate explanation was that the output
budget was consumed by reasoning the adapter never sees. **That was a hypothesis when this run was recorded**; the owner directed a diagnostic (D-149, option 1) and its
result follows.

### The D-149 diagnostic (owner-directed, 2026-09-21)

**Ruling: D-149, option 1 — diagnose first.** One real-model run of the same baseline test, with a **test-only** tap on the HTTP layer inside the test so that the raw body of the
baseline's own call is printed. The provider, the agents, the verifier, the model settings and production behaviour were not changed, and the temporary code was reverted
afterwards (the working tree equals its committed state; the patch and the raw response are kept outside the repository). Claude Code ran it once, at the owner's direction, with
the same model and settings as the recorded run — `qwen3:4b`, temperature 0.0, seed 7, 512 output tokens, 120 s timeout — at the runtime's default local address
`http://127.0.0.1:11434`. The address of the owner's own run was not printed, so that is an assumption about it; the runtime answered there.

**Request sent:** `model` `qwen3:4b`; `stream` false; `options` temperature 0.0, seed 7, `num_predict` 512; the Research agent's system instruction ("You are a research agent. Use
only the documents provided. Cite every claim with the exact reference of its source, written as [[reference]]. If the documents do not answer the goal, say so plainly."); and a
prompt of the mission goal ("Assess migration readiness"), the three supplied documents `doc:1` to `doc:3` and the task line "extract the findings that bear on the goal, in
Markdown, citing each source". 160 prompt tokens.

**Response received** — HTTP 200, 6,081 bytes; every top-level key, in order:

| Key | Value |
|---|---|
| `model` | `qwen3:4b` |
| `response` | `""` — **empty** |
| `thinking` | **2,581 characters (406 words) of reasoning**: it begins "I need to assess migration readiness based on the provided documents…" and **ends mid-sentence**, "…is a significant risk for migration readiness" |
| `done` | `true` |
| `done_reason` | **`length`** |
| `context` | a list of 672 integers (elided) |
| `prompt_eval_count` (cached) | 160 (0) |
| `eval_count` | **512** — equal to `num_predict` |
| `total_duration` | 30.256 s (30,255,937,500 ns) |
| `load_duration` | 7.678 s |
| `prompt_eval_duration` | 0.316 s |
| `eval_duration` | 22.249 s |

The durations are the runtime's own, in nanoseconds; the seconds shown are those divided by 10⁹.

**How EIDOS read it — the same as the recorded run:** `gather` `no_result`, reason "the model call failed (empty_response): the model returned no text"; `analyse` `skipped`
("not dispatched: predecessor(s) did not succeed: 'gather' (no_result)"); `check` `skipped`; outcome `failed`, `verified` false. pytest: 1 passed in 31.54 s (the test asserts
structure only).

**Cause, established for this call.** The runtime returns this model's reasoning in a separate `thinking` field and counts it against `num_predict`. All 512 tokens went to
reasoning; generation stopped at the limit (`done_reason` `length`) before any answer text; the `response` field the adapter reads was empty. The adapter's `empty_response` was
accurate about that field and silent about why. The reasoning was working through the three documents (it refers to them as `[[doc:1]]` to `[[doc:3]]`) and had not reached an answer.

**Runtime state observed after the run** (`ollama ps`, metadata only; the model was still loaded): 3.5 GB, **33% CPU / 67% GPU**, context 4096. This is the runtime's state after
this run, not a measurement of the first recorded run.

**Derived, and labelled as derived:** the runtime's own counters give 512 tokens in 22.249 s of generation, about **23.0 tokens/s**; loading took 7.678 s of the call's 30.256 s.
One run, on a model split between CPU and GPU: this is not a benchmark and no comparison is made.

**Not observed:** the raw body of the trivial "ready" call (its 154 output tokens for a 5-character answer are consistent with the same mechanism, which is an inference and not an
observation); what a larger budget, or reasoning switched off, would return; whether the reasoning would have finished and the answer been usable and verifiable. Two runs of the
baseline test, with the same seed, gave the same mission outcome; that is all the repeatability there is.

**What follows.** Option 1 decided only to diagnose. What to do about the finding was **D-150** (Open then; resolved later the same day); nothing in production changed.

### The D-150 option (a) run (owner-directed, 2026-09-21)

**Ruling: D-150, option (a) first — one run only.** For this one opt-in run, `max_output_tokens` was raised from 512 to **2,048**; everything else was unchanged (`qwen3:4b`,
temperature 0.0, seed 7, 120 s timeout, `http://127.0.0.1:11434`, the same baseline mission), and the ModelPort, the provider, the agent prompts, the verifier, the artifact model
and store, the runtime and the model choice were not touched. 2,048 was chosen so that a worst-case generation would fit inside the unchanged timeout, from the 23.0 tokens/s
measured in the D-149 diagnostic (about 89 s plus loading); **that estimate proved optimistic**, as below. The same temporary tap printed the raw bodies. Both it and the raised
limit were reverted afterwards (the working tree equals its committed state; the patches and the raw responses are kept outside the repository). The baseline dispatches Research and
then Analysis, so the one attempt made two model calls, and no others were made.

**Result: the first real output reached the store, and the second call failed the same way.**

| | Call 1 — Research (`gather`) | Call 2 — Analysis (`analyse`) |
|---|---|---|
| `response` | **753 characters** of Markdown: three sections, each citing one supplied document | **`""` — empty** |
| `thinking` | 4,226 characters (673 words) | **10,790 characters (1,709 words)**; ends at the heading "## What Drives the Cost", with no answer |
| `done_reason` | `stop` | **`length`** |
| `eval_count` / limit | 977 / 2,048 | **2,048 / 2,048** |
| `prompt_eval_count` | 160 | 322 |
| `total_duration` | 52.661 s (load 6.191 s) | **111.010 s** (load 0.003 s): 93% of the 120 s timeout, 9.0 s to spare |
| Runtime-reported generation rate | 21.2 tokens/s | 18.5 tokens/s |
| EIDOS's reading | `succeeded`; artifact `artifact:gather`; `source_refs` `doc:1`, `doc:2`, `doc:3` | `no_result`: "the model call failed (empty_response): the model returned no text" |

**Every step's result:** `gather` `succeeded` (artifact `artifact:gather`, `text/markdown`, 753 characters, cited sources `doc:1`, `doc:2`, `doc:3`); `analyse` `no_result` (reason as above);
`check` `skipped` ("not dispatched: predecessor(s) did not succeed: 'analyse' (no_result)"). Outcome `failed`, `verified` false. pytest: 1 passed in 165.25 s (the test asserts structure
only).

**Was `VERIFY` reached? No.** `check` was never dispatched, so **the verifier did not run and there is no PASS, FAIL or INCONCLUSIVE.** As of this run no real model output had been judged by it (the option (a′) run below changed that).

**What the second call shows.** The Analysis agent's fixed instruction asks the model to cite every claim and to say plainly when the material is not enough. The recorded reasoning drafted
the same analysis four times (with "Wait" three times), deliberated whether the material supports an "uncertain" section, and was cut off part-way through the fourth draft. That describes the
recorded reasoning text; it is not a judgment of the prompt, which was not changed.

**A derived constraint, labelled as derived.** Generation slowed from 21.2 to 18.5 tokens/s between the calls. At 18.5 tokens/s the 120 s timeout allows about 2,200 generated tokens on this
machine, so with the timeout unchanged there is almost no room above 2,048; a larger budget needs a larger timeout too. One run, two calls: not a benchmark, and the second call's runtime
state (model already loaded, a longer prompt) differs from the first's.

**Not observed:** whether the Analysis call would finish with a larger budget and timeout; reasoning switched off; another model. Nothing was changed on the strength of this result: D-150
stays Open, with its options, one of which (a) has now been tried once and was not sufficient on its own.

### D-150 option (c): the adapter says when an empty answer stopped at the output limit (owner-directed, 2026-09-21)

**Ruling: D-150 option (c), as its own step, before any further real-model run.** The smallest provider-local change, in `OllamaModel._interpret` (`src/eidos/providers/ollama.py`):

| The runtime's answer | The adapter returns |
|---|---|
| `response` empty and `done_reason` exactly `"length"` | `EMPTY_RESPONSE`, message "the model returned no text: generation stopped at the output limit (done_reason 'length') before any answer text" |
| `response` empty and `done_reason` `"stop"`, absent, or anything that is not exactly the string `"length"` (`null`, a number, a bool, a list, an object, `"LENGTH"`, `" length"`, `"length\n"`, `"lengthy"`, `""`) | `EMPTY_RESPONSE`, message unchanged: "the model returned no text" |
| `response` with text, whatever `done_reason` says | a `ModelResponse`, unchanged |

The failure **kind** is unchanged, so D-135's closed set of kinds, the ModelPort, the agents' mapping to `NO_RESULT`, the verifier, the runtime, the prompts and the settings are untouched; the
message reaches the step's reason ("the model call failed (empty_response): …") with no other change. **A non-empty answer cut off at the limit is deliberately still returned as a normal
response**: whether to flag that is the separate question recorded in D-150.

**Tests:** five test functions (16 cases) in `tests/integration/providers/test_ollama_adapter.py`, against the fake runtime: an empty answer at the limit says so and stays `EMPTY_RESPONSE` (three
empty forms); an empty answer that stopped normally, and one with no `done_reason`, keep the plain message; ten `done_reason` values that are not exactly `"length"` do not read as a cutoff; a
non-empty answer at the limit is still a response. **12 of 12 mutations caught** (a dropped, inverted or never-firing check; case-insensitive, whitespace-tolerant and substring matching; a changed
kind; a message that loses the limit or the plain prefix; a changed plain message; a non-empty answer turned into a failure; the wrong key). The full default suite: **2,053 passed, 2 deselected, in 74.98 s**
(2,037 before, plus these 16 cases). **No real model was run in this step.**

### The D-150 option (a′) run (owner-directed, 2026-09-21)

**Ruling: D-150, option (a′), one baseline attempt, after option (c).** For this one opt-in run only: `max_output_tokens` **4,096** and a **240 s** timeout; `qwen3:4b`, temperature 0.0,
seed 7, the same endpoint (`http://127.0.0.1:11434`) and the same baseline mission; no retry, no re-run, no side or diagnostic model calls; the adapter as changed by option (c). The
baseline made its two normal model calls. The same temporary test-only tap printed the raw bodies; it and the raised limit were reverted afterwards, the working tree equals its committed
state, and **the committed opt-in test still sets `max_output_tokens` 512**. The patches and the raw responses are kept outside the repository.

**Result: the baseline finished, and the verifier returned PASS.**

| | Research (`gather`) | Analysis (`analyse`) |
|---|---|---|
| `response` | **753 characters** of Markdown: three sections, each citing one supplied document | **842 characters** of Markdown: "What It Takes", "What Drives the Cost", "What Is Uncertain", nine bullets, each citing `doc:1`, `doc:2` or `doc:3` |
| `thinking` | 4,226 characters (673 words) | 12,588 characters (1,992 words) |
| `done_reason` | `stop` | `stop` |
| `eval_count` / limit | 977 / 4,096 | 2,582 / 4,096 |
| `prompt_eval_count` | 160 | 322 |
| Elapsed, as the adapter measured it | 53.078 s | 154.234 s |
| Runtime-reported `total_duration` | 53.049 s (load 5.792 s) | 154.208 s (load 0.006 s): 64% of the 240 s timeout, 85.8 s to spare |
| Runtime-reported generation rate | 20.8 tokens/s | 16.8 tokens/s |
| Step status / reason | `succeeded` / none | `succeeded` / none |
| Artifact | `artifact:gather`, `text/markdown`, 753 characters, `source_refs` `doc:1`, `doc:2`, `doc:3` | `artifact:analyse`, `text/markdown`, 842 characters, `source_refs` `doc:1`, `doc:2`, `doc:3` |

**Was `VERIFY` dispatched? Yes.** `check` `succeeded`, which is the verifier's **PASS**. Its reason, exactly: "schema_validity satisfied (1 artifact(s) well-formed); citation_coverage satisfied
(every artifact cites sources that exist); minimum_distinct_sources satisfied (3 distinct supplied source(s) reached, 3 required). NOT_EVALUATED: min_quality, max_risk_level (no defined
deterministic measurement). This verdict covers the V0.4 verification rules only; it is not a claim that the reliability contract is satisfied."

**Final `RunResult`:** outcome **`finished`**, `verified` **true**. pytest: 1 passed in 208.50 s (the test asserts structure only; the outcome above is what the run produced).

**Compared with the earlier runs (from the saved raw responses).** The Research call is **identical, byte for byte in `response` and `thinking`,** to the same call in the 2,048-token run
(temperature 0.0, seed 7). The Analysis call's cut-off reasoning from that run is an **exact prefix** of this run's reasoning: the model followed the same path and needed **534 more tokens**
than the 2,048 it had been given. So the output budget was the only thing that separated the failed run from this one.

**What the PASS is, and is not.** The verifier checked three things: the artifacts are well-formed, every cited reference exists, and three distinct supplied documents are reached by
following citations. It did not check that a cited document supports what it is cited for, and no quality is measured (D-146). For example the Analysis answer's last line,
"Probability of disk failure [[doc:3]]", cites a document that says only that nightly backups are written to the same disk as the database; the citation passes because `doc:3` exists.
That illustrates what the rules do not test; it is not a finding about the model.

**Derived, and labelled as derived.** The runtime's counters give 16.8 tokens/s for the 2,582-token Analysis generation (20.8 for Research). At 16.8 tokens/s a generation that ran to the
full 4,096 tokens would take about 244 s, longer than the 240 s timeout, so a call that ran to the limit could have timed out before finishing. One run, two calls: not a benchmark.

**Not observed:** repeatability beyond the Research comparison above (this is one attempt); other models; reasoning switched off; a budget between 2,048 and 4,096; and the opt-in test as
committed (512 tokens), which would fail as it did.

**Nothing else was changed on the strength of this result:** D-150 stayed Open and V0.4 was not closed; whether either should be was the owner's call.

**Later the same day:** the owner adopted (a′) as the committed configuration and the committed test was run once (next section); D-150 was then resolved and D-151 logged.

### The committed real-model run (owner-directed, 2026-09-21)

**Ruling: adopt D-150 option (a′), then run the committed test once.** The committed opt-in test's configuration was changed to `max_output_tokens` **4,096** and a **240 s** timeout (the
timeout is now a committed constant, `TIMEOUT_SECONDS`, instead of an environment variable); `qwen3:4b`, temperature 0.0, seed 7, the endpoint, the mission and all other behaviour
were unchanged. That change is its own commit, made **before** the run, so the run tested exactly what is committed. The run then executed **the baseline node of the committed test,
once, from a clean tree**: no tap, no retry, no re-run and no side or diagnostic call (the trivial-completion test in the same file was not selected, because it would have been an extra
model call). Only `EIDOS_REAL_MODEL_URL` (`http://127.0.0.1:11434`) and `EIDOS_REAL_MODEL_NAME` were set.

**Result, as printed:**

| | Research (`gather`) | Analysis (`analyse`) |
|---|---|---|
| Call result | `response`, 753 characters | `response`, 842 characters |
| Prompt / output tokens | 160 / 977 | 322 / 2,582 |
| Elapsed, as the adapter measured it | 59.531 s | 172.203 s (72% of the 240 s timeout, 67.8 s to spare) |
| Step status | `succeeded` | `succeeded` |

`check` (`VERIFY`) `succeeded` — the verifier's **PASS** — with the reason "schema_validity satisfied (1 artifact(s) well-formed); citation_coverage satisfied (every artifact cites sources
that exist); minimum_distinct_sources satisfied (3 distinct supplied source(s) reached, 3 required). NOT_EVALUATED: min_quality, max_risk_level (no defined deterministic measurement).
This verdict covers the V0.4 verification rules only; it is not a claim that the reliability contract is satisfied." Final `RunResult`: outcome **`finished`**, `verified` **true**. pytest:
1 passed in 232.93 s.

**Read against the earlier attempt.** The response lengths and token counts equal the (a′) run's (753 / 977 and 842 / 2,582), so the run reproduced under temperature 0.0 and seed 7. The
timings differ (59.531 s and 172.203 s against 53.078 s and 154.234 s): this run was about 12% slower on both calls. Two runs of the same configuration is all the repeatability there is.
The committed test prints neither `done_reason` nor `thinking`, so they were not captured; the (a′) run's raw bodies showed `stop` for both calls.

**Still true, and stated again.** The committed baseline test asserts structure only: pytest's green result does not by itself say the mission succeeded; the printed outcome, `verified`
and step statuses do. The PASS covers three V0.4 rules and measures no quality; it does not check that a cited document supports its claim. A call that ran to the full 4,096 tokens at the
slowest recorded rate could exceed the 240 s timeout, which would be a typed timeout failure.

### V0.4 known limitations (recorded, not redesigned)

- **Fresh step IDs (D-147).** Within one execution a newly executed work step must use a step ID no earlier-executed work step used, across plan
  versions. Artifact identity stays `(execution_id, step_id)` and `artifact:<step_id>`. An existing artifact for the step is refused before any model call.
  Same-plan resume is unaffected.
- **An analysis step cannot follow a `VERIFY` step (D-148, item 6).** A `VERIFY` node produces no artifact, so the analysis agent fails on it. An analysis
  step's predecessors are work steps at V0.4.

### The D-147 and D-148 rulings

D-147 was resolved with option (a) and D-148's ten details were accepted as written (2026-09-20); counts are 100 Accepted, 45 Open, 4 Deferred.
The D-147 guard is implemented (`refuse_a_reused_step`, used by the Research and Analysis agents) and mutation-checked 10 of 10; see the session log.

### Environment (recorded facts)

**During the exploration:** no local model runtime was installed on the owner's machine; the GPU has 4 GB of memory and the machine 15.7 GB of RAM. **Since:** the owner
installed Ollama 0.34.2 and pulled `qwen3:4b` (see "The first real baseline run"). The only model figures in this repository are the ones recorded there; no speed or
quality is claimed beyond them. Only the owner installs the runtime and chooses the model (D-136).

### V0.4 close-out review

**Status: closed 2026-09-21, on the owner's direction, after the two gates the owner set were met: the committed real-model test ran once and demonstrated Research → Analysis → VERIFY → PASS, and
the full default suite was green (2,053 passed, 2 deselected).** This review was prepared earlier the same day and is updated here; the dated run records above are unchanged.

**Against the handoff's V0.4 line (§50): "Add Research, Analysis, Verification. Make the baseline workflow work end-to-end."**

- **Delivered:** the three agents (`ResearchAgent`, `AnalysisAgent`, the deterministic `VerificationAgent`), a capability registry with typed pre-run binding, a
  single-pass runner and one local-runtime adapter. The baseline runs end to end **with a scripted model** on both backends, and a real `PASS`, `FAIL` and
  `INCONCLUSIVE` verdict is reachable from the verifier.
- **Shown with a real model, by the committed opt-in test, run once:** Research → Analysis → VERIFY → PASS — outcome `finished`, `verified` true (`qwen3:4b`, 4,096 output tokens, 240 s). The route
  there is recorded as it happened: at 512 tokens the first step failed (D-149: the reasoning model spent its whole budget), at 2,048 the second failed the same way (D-150 option a), and at 4,096
  with a 240 s timeout it finished (option a′, then the committed test). Read the PASS carefully: it covers three V0.4 rules (schema validity, that every cited reference exists, three distinct
  supplied sources) and measures no quality; it does not check that a cited document supports its claim; the committed test asserts structure only, so the printed outcome, not pytest's green,
  shows the result; and the demonstration is two runs of one configuration, on one machine, with one model and one mission.
- **The owner closed V0.4 on that basis** (2026-09-21), leaving D-151 (Open) deliberately unsolved.

**Definition of done (CLAUDE.md §5), checked.**

- *Implementation exists:* `eidos.agents`, `eidos.capabilities`, `eidos.baseline`, `eidos.providers`, and one amended core file, `eidos/runtime/context.py` (D-139).
- *Tests exist:* 1,605 unit (contracts 165, validation 409, compiler 276, runtime 435, backends 48, capabilities 56, agents 171, baseline 30, providers 15), 353 integration
  (LangGraph 306, providers 63) and 79 scenarios, plus 2 real-model tests deselected by default. The V0.3 close-out was 1,683; the default run is now 2,053 (2,037 when this review
  was first written, plus 16 cases for D-150 option (c)).
- *Tests pass:* the full default run — `python -m pytest`, recorded for this review — **2,053 passed, 2 deselected, in 83.95 s** (run on the committed tree before the close-out documentation commits, and again on the final tree before the push), and it includes the permanent test that runs the
  whole unit tree with LangGraph, LangChain and LangSmith unimportable and asserts none was loaded. The 2 deselected tests are the real-model tests; the baseline one was
  run separately, once, in its committed configuration (above). Mutation checks over Steps 2 to 8 and the D-147 guard: **97 of 98 caught**; the one that was not is an equivalent mutant (a lock-free read that CPython
  cannot make observable), documented at Step 5.
- *Integration works:* with a scripted model, the whole baseline on both backends with byte-identical reports; the adapter against a local fake runtime over real sockets
  (success, timeout, refused connection, non-success status, malformed body). With a real model, the committed opt-in test, run once, finished with a verifier PASS (above); the earlier attempts at smaller budgets failed, as recorded.
- *Failure cases covered:* malformed and empty model output, a model outage, missing input, `PASS` / `FAIL` / `INCONCLUSIVE` each reachable, well-formed output that fails
  verification, an unbound capability, an invalid plan, an unsupported step kind, an admission halt and resume, a reused step id (D-147), and — with a real model — a model
  that returned no text.
- *Documentation matches reality:* checked by this review, which found and corrected stale statements (below).
- *Git checkpoint:* one commit per step, and those above.

**Guards, cross-checked independently of the guard tests** (an AST import audit of `src/eidos` run for this review; the script is not committed).

- No core layer (`contracts`, `validation`, `compiler`, `runtime`, `backends`) imports `agents`, `capabilities`, `providers` or `baseline`. Nothing imports `providers`,
  `baseline` or `backends`; `providers` imports only `agents`.
- The only third-party imports are `pydantic` everywhere and LangGraph / LangSmith inside `eidos.backends.langgraph`. The base dependency is still `pydantic>=2`; V0.4
  added no dependency and no extra.
- No model, vendor or SDK name appears in `agents`, `capabilities` or `baseline`. Outside `providers` and `backends`, the only matches are prose references to
  `CLAUDE.md` and the V0.1 A2A identifiers (`A2ATaskId`, `A2AContextId`, D-095) — a protocol name, unchanged since V0.1.
- Agents are read-only: the static guard forbids I/O, network, clock, randomness, process state, opening files, printing and executing generated code, and allows only a short
  list of standard-library modules; no agent imports a provider.
- Frozen paths: the handoff is unchanged since the V0.3 tip (empty diff). Of the V0.1 to V0.3 source, exactly one file changed, `runtime/context.py` (D-139). Two groups of
  tests changed because the specification changed: the context's field set (D-139), updated and extended with four new tests, and a late "could not be recorded" that became an
  early refusal (D-147), now asserting that no model was called. None was weakened, deleted or skipped.

**Invariants, honestly.** Exercised by V0.4 code and tests: 1 and 2 (MissionState is only read; agents are read-only, D-140), 4 (the compiled DAG, unchanged), 5 (the runner
stops at the first gate that refuses; nothing executes unvalidated), 9 (the model sits behind a port; another implementation substitutes without a core change; a vendor
name appears only in `eidos.providers`), 10 (an unrelated-domain scenario needs no core change), 11 (plans request capabilities; the registry binds them), 12 (verification is
separate from completion: scripted well-formed output that fails verification, and a real model that returned nothing, were not counted as success; a real run's PASS names what was NOT_EVALUATED and does not claim contract satisfaction), 14 (the admission guard
is code and fails closed) and 18 (identifiers). **Exercised in part:** 3 (model output is text that is stored and read back, never executed and never run as a plan; the
model does not emit plans at V0.4, D-131, so the Plan-DSL half is not exercised), 6 (a replan is a new plan version in the same execution, with fresh step ids, D-147;
lineage across a mission's plans is the V0.5 reducer's concern), 7 (only an admission halt exists at run time; the other budgets stay deferred, D-127), 13 (a real run reported
failure instead of manufacturing an answer; only three reliability clauses are evaluated, `min_quality` and `max_risk_level` are `NOT_EVALUATED` and a `PASS` never claims
contract satisfaction; "the contract cannot be met" as a run outcome is not exercised, D-059 Open) and 16 (a citation is recorded as a `source_ref`, one link of the chain; there
is no retrieval query, tool or evidence chain). **Not exercised, by ruling:** 8 and 15 (no events and no replay, D-123, D-126) and 17 (no estimates).

**Findings for the owner.**

1. **D-149 (resolved, option 1) and D-150 (resolved: (a′) and (c) adopted, (b) and (d) not adopted):** the first real run failed because the reasoning model spent its whole 512-token budget before
   answering; the committed configuration is now 4,096 tokens and 240 s, and the adapter's failure message names an output-limit cutoff.
2. **The committed opt-in real test is still thin, and now carries the working configuration.** It prints each step's status and the last step's reason, not every step's reason, the raw model
   response or `done_reason`, and it asserts structure only. The D-149 diagnostic printed the raw responses with a temporary tap (reverted; the patch is kept outside the repository). Whether to keep a
   permanent version is the owner's call.
3. **A failed model call carries no measured facts**, so its latency and token counts are not recorded. Related, by reading the code and not observed in a run: the adapter returns a normal
   response whenever `response` has text, whatever `done_reason` says (**D-151, Open**, deferred).
4. **Stale documentation found and corrected by this review:** the README status line (it still said V0.2 and "no compiler, no runtime, no agents"); `docs/03`'s "approved, not
   built" heading and its "no real model has been run"; the V0.4 rows in this file's ladder and "not built yet" table; ten references that still called D-141 to D-143 "Open"
   (their own commit, annotations only); the opt-in test's docstring (comment only); and the two test READMEs.
5. **Carried from earlier steps, already recorded in D-148 and D-147:** "distinct" sources are not "independent" sources; `NOT_EVALUATED` clauses appear as prose in a
   verification reason, not as a typed field; the provider's timeout bounds each socket operation, not total elapsed time; an analysis step cannot follow a `VERIFY` step; a newly
   executed step needs a fresh id across plan versions.
6. **Still Open and untouched:** D-007, D-012, D-015 (a scalar), D-017, D-020, D-041, D-043, D-046, D-055, D-059, D-063, D-064, D-125, D-126 and D-129, and now D-151.
7. **What the first real PASS does and does not show.** It shows the chain working with a real model's output: two artifacts stored with their cited sources, a `VERIFY` step dispatched, a
   verdict returned, `finished` and `verified`. It does not show that the answers are good or that a cited document supports its claim: for example the Analysis answer's last line,
   "Probability of disk failure [[doc:3]]", cites a document that says only that nightly backups are written to the same disk as the database, and the citation passes because `doc:3` exists.
   Claim support is not one of the three rules and no quality is measured (D-146).
8. **The committed timeout is sized to the recorded calls, not to the budget.** At the slowest recorded generation rate a call that ran to the full 4,096 tokens would take about 244 s, longer than
   240 s; the longest recorded call used 2,582 tokens and took 172.203 s (72% of the timeout). A slower machine or a longer answer could time out, which is a typed `TIMEOUT` failure, not a hang.
   The committed baseline has been reproduced on one machine only (a 4 GB GPU; a later `ollama ps` showed 33% CPU / 67% GPU), with one model and one mission.

**Not measured, not claimed:** throughput or latency beyond the one trivial completion and the runtime-reported durations of the diagnostic and option runs recorded above (five baseline
attempts); any quality of any model's output; repeatability beyond what the saved responses show (the Research call identical across two runs; the Analysis call's earlier reasoning an exact
prefix of the later; the committed run's counts equal the (a′) run's); whether the GPU was used in the first recorded run (a later `ollama ps` showed 33% CPU / 67% GPU); recorded model outputs for replay (D-076 stays Open).

**Decisions taken at close-out (the owner's, 2026-09-21):**

1. **D-150 resolved:** option (a′) adopted — the committed opt-in test carries 4,096 output tokens and a 240 s timeout; option (c) adopted; option (b) not adopted; option (d) not adopted.
2. **D-151 logged (Open):** non-empty responses that stopped at the output limit; deferred, not redesigned in V0.4.
3. **V0.4 closed** once the committed real-model test had passed and the full default suite was green.
4. **Push** of the local commits to `origin/master`, once this close-out was verified; the pushed tip is what `git log origin/master` shows.

**What V0.4 leaves for later, for V0.5 and on:** D-151; D-129 (how a work node receives predecessors' outputs: answered for V0.4 by the in-memory store, not in general); D-076 (model outputs
are not recorded, so nothing is replayable); D-123 and D-126 (no events); D-059 (the contract-unsatisfied outcome); D-015 (no scalar); the known limitations (fresh step ids across plan versions,
D-147; an analysis step cannot follow a `VERIFY` step, D-148); and the committed baseline test asserting structure only.

### Carried forward, not decided

LangGraph runs a level's nodes on worker threads, so the agents, the store and the fake model must be thread-safe, and one small
GPU may serialise concurrent model calls; V0.5 replay will need model outputs recorded (D-076), which V0.4 makes capturable but does not record.

---

## V0.5 Mission State + Event Reducer — complete as scoped (2026-09-21)

**Step 1 — the exploration and the decision record — is done.** The exploration was read-only. The owner approved its proposal with nine rulings, recorded as **D-152 to D-159 (Accepted)**; they resolve
**D-010b, D-039 and D-126**. **D-160 (Accepted, 2026-09-21)** records the implementation details the owner then approved with eight rulings, and **D-161 (Deferred)** holds everything V0.5 excludes. The exploration also found
that the handoff's V0.5 line (events, state, reducer, checkpoints, replay) and the telemetry-to-memory chain differ in where they place telemetry (V0.9), memory (V1.0) and learning (V1.1); the ladder
does not move.

### Approved scope

| Ruling | Entry |
|---|---|
| V0.5 = MissionEvent / MissionState / StateReducer + the event log + checkpoint and replay + recording adapters + a thin, read-only `ExecutionRecord`. | D-152 |
| Typed payloads through an `EventRecord`; the V0.1 `MissionEvent` envelope is unchanged. | D-153 |
| Three new event types — `NODE_STARTED`, `NODE_SETTLED`, `MISSION_PAUSED` — resolving D-126 and superseding "exactly thirteen" (D-090): sixteen in all. | D-154 |
| A pure, outcome-returning reducer; contiguous sequence; idempotency by `event_id`; terminal states reject later events. Resolves D-039. | D-155 |
| One recorded pass is the mission's execution; a typed cause on failure; counters recorded, never enforced. D-043, D-059 and D-015 stay Open. | D-156 |
| The event log is authoritative; `MissionState` is only its view; `ExecutionRecord` is purely derived. In memory with a JSONL round trip; **no SQLite or durable store.** Resolves D-010b; D-017 and D-038 stay Open. | D-157 |
| Recording adapters outside the runtime; facts only; **`MeasuredFacts` is not modified and D-151 stays Open.** | D-158 |
| `ExecutionRecord`: thin, read-only, derived, no quality field. | D-159 |
| A2A, MCP, RAG, the telemetry platform, strategy memory, the selector, a planner, adaptive learning and cross-mission aggregation are out. | D-161 |

### The contract changes

- **V0.1 (`eidos.contracts`): one change.** `MissionEventType` gains `NODE_STARTED`, `NODE_SETTLED` and `MISSION_PAUSED` (13 to 16). `MissionEvent`, `MissionState` and `MissionStatus` are unchanged, and
  `test_no_payload_field_exists` stays true. The enum test that pins the thirteen changes because the specification changed.
- **New, `eidos.state` (pure; imports the core layers only):** `EventRecord` (an envelope plus a typed payload keyed by its type); payloads for the nine emitted types; the reducer, returning state and an
  outcome; the append-only log and intake; the checkpoint value; replay; and `ExecutionRecord`. Field lists are in D-160 (approved).
- **New, `eidos.recording` (adapter; injected clock and id source):** wrappers over the agents, verifier, admission guard and model port, and a run recorder. It holds no `MissionState`.
- **Unchanged:** the runtime, the executors, the compiler, the agents, the verifier, `WorkResult`, `RunResult`, `MeasuredFacts`, the D-122 and D-137 signatures, and `run_baseline`, apart from one additive,
  observational `observer=None` parameter (D-160 item 8, approved).

### Implementation sequence

Each step is one component, one change and one acceptance condition (CLAUDE.md §4), mutation-checked, in its own commit. Nothing is pushed until the owner says so. D-160 is approved, so no step waits on it.

| Step | What | Decisions | Proves |
|---|---|---|---|
| **1** | Record the rulings | D-152–D-161 | **Done** |
| **2** | Two commits: the enum (+3, tests updated), then `eidos.state` event records — the payloads, `EventRecord` and the strict JSON round trip | D-153, D-154, D-160 | A payload that does not match its type is refused; a type with no payload class is refused; the round trip is equal; the envelope is unchanged **Done** — the enum (13 to 16, commit aeb617e) and `eidos.state` event records: nine payload types, `EventRecord` (payload chosen by the envelope's type; tenant and mission must agree), strict JSON round trip; 129 tests (104 behaviour, 25 guard checks; 1,734 unit tests in all); 20 of 20 mutations caught after one isolating case was added (a first run missed a plan-of-another-tenant mutation) |
| **3** | The pure reducer: lifecycle, sequence, idempotency, terminal states, counters | D-155, D-156, D-160 | Determinism; a duplicate is ignored; out-of-order, stale, post-terminal and invalid events are rejected with the state byte-identical; only the reducer writes `MissionState`; no I/O or clock; hash-seed determinism **Done** — `eidos.state.reduce`: pure, returns state and an outcome (applied, duplicate, out of order, stale, post-terminal, invalid for the state); a fixed check order; the counters folded from recorded facts only; only the reducer constructs a `MissionState` (guarded); 44 tests added (173 in `tests/unit/state`; 1,778 unit tests in all); 29 of 29 mutations caught |
| **4** | The event log and intake, the checkpoint and replay | D-157 | The JSONL round trip; a checkpoint plus the tail equals a full replay; an invalid log is a typed rejection; replay imports no agent and makes no model call **Done** — `EventLog` and its intake (the intake assigns the sequence, ignores a repeated `event_id`, and appends only what the reducer applies), `replay`, `checkpoint_at` / `resume` (a checkpoint plus the tail equals a full replay at every sequence), and the strict JSONL round trip (a JSON string holding U+2028 survives); typed rejections, never a partial replay; no file, database or store; 56 tests added (229 in `tests/unit/state`; 1,834 unit tests in all); 23 of 23 mutations caught |
| **5** | `eidos.recording`: the clock and id ports, the wrappers and the run recorder | D-158, D-160 | Both backends give the same event stream under a fixed clock for the linear baseline; the runtime is unchanged; adapters hold no `MissionState` **Done** — `eidos.recording` (ports, recorder, wrappers, `record_baseline`); the observer hook was committed earlier as 5a. 84 unit tests plus a 6-test both-backends scenario: the linear baseline, a failed verification and an admission halt give byte-identical logs on both executors, and a parallel plan gives the same set of events with a contiguous sequence. Mutation check over `recorder.py`, `adapters.py` and `run.py`: 48 mutations; 6 survived the first pass (an unlocked `record`, the calls of a node that raised, the first-failing-node cause, the run-rejection reason, and an unreachable dispatched guard) and were closed by new tests, the guard removed as unreachable. Full default suite 2386 passed, 2 deselected (opt-in real-model tests, not run) |
| **6** | The `ExecutionRecord` projection | D-159 | The live record equals the replayed one; no quality field; `NOT_EVALUATED` preserved **Done** — `execution_record(records)` in `eidos.state`: a pure projection of a log (it replays first, so a log the reducer refuses gives the typed rejection); identity, the plan's steps with the agent each was bound to, per-step result, dispatch, duration, model calls and VERIFY verdict, the terminal status, cause and halt, the folded counters and the log bounds; no quality, confidence, score, rate or signature field (asserted over the field names); the verifier's `NOT_EVALUATED` wording is carried word for word. The record of a live log equals the record of the same log replayed from JSONL, every prefix of a log projects, and the record is the same on both executors and across hash seeds. It also counts repeated step events, because the reducer cannot refuse one (probe: `agent_calls_used` went from 2 to 3): recorded as a gap in D-162 item 1 (Open), with the implementation details in items 2 to 10. 27 unit tests and 1 scenario test added in the new files, and the existing state guards now also cover the new module (33 more tests in all); 38 of 38 mutations caught after strengthening (5 survived the first pass: repeated-start counting, first-versus-last record of a step, and plan selection in a replanned log; 4 more could not run until the mutation script matched CRLF working copies, and were caught on the re-run). Full default suite 2419 passed, 2 deselected |
| **7** | Scenarios and guards: the baseline recorded, serialized and replayed; verification FAIL, a model failure, a refused plan and an admission halt; hash-seed determinism | D-152–D-159 | The whole chain, including failure paths; an opt-in real-model recording only if the owner asks **Done** — `tests/scenarios/test_v05_chain.py` (84 tests) with the cases in `tests/support/eidos_v05_cases.py`: the verified baseline, an unverified finish, a failed verification, a model timeout, an empty response, a plan refused at each of the three gates, and an admission halt, each on both executors over the real V0.4 agents and a scripted model. Each asserts the log is the whole story (nothing refused or contradicted, one terminal event, contiguous sequence), the expected status, cause, verified flag and folded counters (fixed test values), the serialized log replaying to the live state, a checkpoint at every sequence plus the tail equalling the full replay, the `ExecutionRecord` equal live and replayed, and the recorded pass equal to an unrecorded one; a paused mission is resumed by a new pass over its successes; a fresh interpreter replays the text without loading an agent, provider, backend, baseline runner, capability registry or recorder; the whole story is byte-identical under four hash seeds. Mutation check of the chain scenarios alone: 16 mutations across the reducer, recorder, projection and replay; 2 survived the first pass (the status-reason wording and the bound agent ids) and were closed by per-case assertions. No real-model recording was run (not asked). Full default suite 2503 passed, 2 deselected |
| **7a** | The lifecycle and idempotency guard the owner approved after the close-out review: the intake and a fold from scratch refuse a repeated `NODE_STARTED` or `NODE_SETTLED` for the same step of a plan; no per-node state in `MissionState` | D-162 | A repeat is refused with `REPEATED_STEP_EVENT`, folds nothing and consumes no sequence; replay, restore, JSONL and the projection refuse a log that has one, at the same record the intake refuses; the same step id in another plan version is another step **Done** — `eidos.state.step_events`; 15 tests in `test_state_step_events.py`, one added to the reducer and one to the recorder tests, the projection tests adjusted (`repeated_step_events` removed: a replayed log has none); the existing state guards cover the new module (21 more tests in all); 21 of 21 mutations caught on the first pass. Full default suite 2,524 passed, 2 deselected |
| **8** | Close-out: the definition of done, which invariants are and are not exercised, the docs, this file | — | Full suite; unit suite with LangGraph blocked; import audit; frozen paths **Done** — after the owner's D-162 ruling: full suite 2,524 passed, 2 deselected; unit suite with the LangGraph family blocked 1,985 passed; an independent import audit found no layer violation; the handoff, `MissionState`, `MeasuredFacts` and the V0.3 and V0.4 packages are unchanged apart from what the owner approved; all twelve acceptance criteria met; V0.5 closed as scoped; pushed to origin/master |

### Acceptance criteria — all twelve met (2026-09-21)

1. Folding a recorded baseline log gives a `MissionState` equal to the live one. **Met.** The state the intake built while events were accepted equals a fold from scratch, for all nine cases on both executors (`test_v05_chain.py`; `test_state_log.py`).
2. Replay makes zero model calls, and `eidos.state` imports no agent, provider, capability or baseline module. **Met.** A fresh interpreter replays each serialized log and projects its record with none of `eidos.agents`, `providers`, `backends`, `baseline`, `recording` or `capabilities` loaded; the state package's own import guards and the independent audit agree.
3. A log survives the strict JSONL round trip, and `ExecutionRecord(log)` is equal before and after it. **Met**, as the function `execution_record(records)` (D-162 item 10): equal live and replayed for every case, and a JSON string holding U+2028 survives.
4. A duplicate is ignored; an out-of-order, stale or post-terminal event is rejected deterministically, and a rejection leaves the state byte-identical. **Met** (`test_state_reducer.py`, `test_state_log.py`, and for a repeated node event `test_state_step_events.py`): a duplicate is ignored; an out-of-order, stale, post-terminal or repeated-step event is rejected deterministically and leaves the state byte-identical. **The repeated-step case was a gap until the owner's ruling** (D-162 item 1): the intake and replay now refuse a repeated `NODE_STARTED` or `NODE_SETTLED` for the same step of a plan; the reducer's six outcomes are unchanged and `MissionState` gained no per-node state.
5. A checkpoint plus the tail of the log equals a full replay. **Met** at every sequence of every case on both executors, and a checkpoint survives serialization.
6. Only the reducer constructs or updates `MissionState`, enforced by a guard test. **Met** (`test_no_module_but_the_reducer_constructs_a_mission_state`, and the recorder is guarded against importing the reducer).
7. The record holds only reported or observed values and no quality field; `None` stays `None`; `NOT_EVALUATED` is preserved. **Met.** No field name of the record contains quality, confidence, score, rate, signature, risk, estimate or success; the verifier's `NOT_EVALUATED` wording is carried word for word; an unreported token count adds nothing and is counted.
8. Both backends give the same event stream under a fixed clock for the linear baseline. **Met**: byte-identical serialized logs for the linear baseline, a failed verification and an admission halt. For parallel branches only the same *set* of events and a contiguous sequence are asserted, over eight repeated runs.
9. Output is byte-identical across `PYTHONHASHSEED`s. **Met** for the log, the state and the record: in the state, recording and scenario tests (four seeds; every case on both executors).
10. Every failure path — verification FAIL, a model failure, a refused plan, an admission halt — yields the right terminal or paused status and a typed cause. **Met**: nine cases, each with its expected status, cause, verified flag, node statuses and folded counters (fixed test values).
11. The V0.3 and V0.4 code is unchanged except what the owner explicitly approves. **Met**: `agents`, `providers`, `backends`, `compiler`, `validation`, `capabilities` and `runtime` are unchanged since 96124f0; `baseline.py` gained the approved observer (D-160 item 8); `enums.py` gained the three approved event types (D-154); `mission_event.py` changed a docstring only.
12. The full default suite is green. **Met**: 2,524 passed, 2 deselected (the opt-in real-model tests, not run), 107.66 s, at the close-out.

### Carried forward, not decided

The exploration's statement about parallel-level event ordering was inferred from the recorded design (LangGraph runs a level's nodes on worker threads). It is now tested only as far as the set of events, the
contiguous sequence and the counters, over eight repeated runs; the order of a parallel level's events is not asserted, and can differ between runs (D-158 item 6). The acceptance scenario is the linear baseline. D-160 items 2 and 8, which departed from or went beyond the exploration, were approved by the owner (2026-09-21).


### V0.5 close-out review (2026-09-21; closed as scoped on the owner's rulings; pushed)

**The owner's rulings applied (2026-09-21).** D-162 item 1 approved with the recommended option: the event intake rejects a repeated `NODE_STARTED` or `NODE_SETTLED` for the same execution step, and **no per-node
state is added to `MissionState`**. D-162 items 2 to 10 are kept unless one contradicts an Accepted decision; **item 7 does** (D-158 item 1 lists the admission guard among the wrapped points), so it is not kept and is
recorded as **D-163** (Open at the time; resolved after this review, see the update below). D-151 stays Open. The real-model recording was not run.

**Verification, run for this close-out (after the guard).**

- **Full default suite:** 2,524 passed, 2 deselected (the two opt-in real-model tests, not run), 107.66 s.
- **Unit suite with the LangGraph family blocked (D-116):** 1,985 passed, 22.00 s (a plugin made `langgraph`, `langchain`, `langchain_core` and `langsmith` unimportable; an import was shown to fail).
- **An independent AST import audit of `src/eidos`** (separate from the guard tests): every package imports only the packages it may; no core layer imports `agents`, `providers`, `backends`, `capabilities`,
  `baseline` or `recording`; LangGraph only in `eidos.backends`; no vendor identifier outside `eidos.providers` and `eidos.backends`; no I/O, clock or random module in a core layer. Its one note is the V0.3
  backend importing `langsmith` to switch tracing off, in code V0.5 did not touch.
- **Frozen paths since V0.4 closed (96124f0):** the handoff is unchanged; `agents`, `providers`, `backends`, `compiler`, `validation`, `capabilities`, `runtime` and `contracts/mission_state.py` are unchanged, so
  **`MissionState` gained no field** and **`MeasuredFacts` is unchanged**; `contracts/mission_event.py` changed a docstring (its fields are unchanged); `contracts/enums.py` gained three event types (D-154); `baseline.py`
  gained the observer hook (D-160 item 8). Two existing tests were updated to the approved sixteen types and still pin the exact set; none was deleted, skipped or weakened.
- **Test counts, collected:** `tests/unit/state` 278, `tests/unit/recording` 88, `tests/unit/baseline` 44, `tests/scenarios` 170 (91 of them new), all unit tests 1,985, integration 369 with 2 deselected.
- **Mutation checks** (scratch tooling, not committed): the event records 20 of 20; the reducer 29 of 29; the log and replay 23 of 23; the recording package 48 of 48 after 6 survivors were closed; the projection 38 of
  38 after 5 survivors were closed; the chain scenarios alone 16 of 16 after 2 survivors were closed; **the step-event guard 21 of 21 on the first pass** (the key, the check, the intake, restore, the fold and the projection).
  Each survivor was a test gap, closed with a test or by removing an unreachable branch.

**Definition of done (CLAUDE.md §5), checked.** The implementation exists in `eidos.state` and `eidos.recording`, with the hook in `eidos.baseline`. Tests exist at every layer: unit (records, reducer, log, replay, the
step-event guard, projection, recording, guards), scenarios on both executors, and failure-path cases. All pass. Integration works: a recorded baseline over the real V0.4 agents replays to the same state and record on both
executors. Failure cases are covered (nine cases; a repeated node event; refused proposals, contradicted live settlements and observer faults are surfaced, not dropped). Documentation matches the implementation (`docs/03`,
`docs/06`, `docs/11`, `docs/12`, the README and the scenarios README; D-162 to D-164). A git checkpoint exists for every step. **All twelve acceptance criteria are met.**

**Invariants exercised by V0.5.** 2 (only the reducer writes `MissionState`; the recorder cannot import it); 8 (a duplicate is ignored; late, out-of-order, post-terminal and repeated-step events are refused
deterministically; every event carries identity, sequence and timestamps) — **with one open question, D-164, about a start recorded after the same step's settlement**; 9 (no vendor or model name in `eidos.state` or
`eidos.recording`); 12 (`completed` with `verified` false is distinct from verified; the verdict is recorded from the verifier); 15 (a completed mission replays from its recorded events with no agent run, tested in a
fresh interpreter); 18 (tenant, mission, execution, plan, agent and event ids and timestamps are in the records from the start).
**Not exercised:** 3, 4, 5, 6 (no planner; a second plan appears only in a projection test and a step-event test); 7 (the counters are recorded, never enforced, D-156); 10 and 11 (nothing domain-specific or
capability-binding was added); 13 (reliability contract, V1.2; D-059 Open); 14 (governance, V1.2); 16 (no evidence, source or retrieval query is recorded until V0.8); 17 (no estimate exists; the token counter is a
labelled lower bound).

**Findings.**

1. **The gap in the reducer is closed (D-162 item 1).** Found while building the projection (probe: a second `NODE_SETTLED` for a step took `agent_calls_used` from 2 to 3). The intake now refuses it; a fold from
   scratch refuses a log that has one, so the live intake and a replay refuse the same record. **Two choices are mine and are recorded for correction:** "the same execution step" is read as the same step *of the
   same plan* (a step id reused in another plan version is another step, so a replan can run again), and the outcome is a seventh `REPEATED_STEP_EVENT` that only the intake and the fold return. **A limit:**
   `resume(checkpoint, tail)` sees nothing before the checkpoint, as with the applied `event_id`s (D-038); it holds for a log that replays.
2. **D-163: the admission guard is not wrapped,** although D-158 item 1 lists it. D-160 item 1 puts `MISSION_PAUSED` last, after the not-reached nodes' settlements, which a live wrapper could not do. The
   behaviour follows D-160 item 1 and loses nothing; the recommendation was to amend D-158 item 1's wording, which the owner then did (see the update below).
3. **D-164 (Open): a `NODE_STARTED` after the same step's `NODE_SETTLED` is accepted.** It folds nothing, so no counter is affected; the ruling covered repeats only.
4. **Closed with two Open questions, one since resolved.** V0.5 was closed because all twelve acceptance criteria pass, which was the condition set; D-163 and D-164 were recorded and neither affects a criterion. The owner has since resolved D-163 and ruled that D-164 stays Open and does not reopen V0.5.
5. **No real-model recording was run** (not required). Every number in the V0.5 tests is a fixed test value from the scripted model and clock.
6. **The order of a parallel level's events is not deterministic across runs and is not asserted** (D-158 item 6); only the set, the contiguous sequence and the counters are.
7. **The token counter is a lower bound** (a provider that reports no count adds nothing; `responses_missing_token_counts` says by how many calls it may fall short), and **D-151 stays Open**: the log cannot tell a
   non-empty answer cut off at the output limit from a complete one.
8. **`execution_time_used_ms` is accumulated accounted node time,** not wall-clock duration (D-160 item 6); with parallel nodes it can exceed the elapsed time.

**Update (2026-09-21, after the review).** The owner resolved **D-163** by amending D-158 item 1 to match the recording and observer boundary as built: the agents, the verifier and the model port are wrapped, the
plan stages come from the `observer` hook on `run_baseline`, and a halt is read from the run's result. The recorder was not redesigned and no code changed. **D-164 stays Open by the owner's ruling, and V0.5 is not
reopened for it.** The default suite was rerun after the documentation change: **2,524 passed, 2 deselected, 118.44 s.** The V0.5 commits were then pushed to origin/master.

---

## V0.6 One A2A Boundary — protocol and contract design accepted, no code (2026-09-22)

**Step 1 — the exploration, the protocol research and the decision record — is done.** Read-only exploration (D-165 to D-176 drafted with options and a recommendation for each), then owner-directed research against the
published A2A Protocol Specification (a2a-protocol.org, v1.0) and the actual `a2a-sdk` dependency graph before any transport choice was made, then the owner's rulings, recorded as **D-165 to D-176 (Accepted)**. This
family resolves **D-023, D-035, D-036, D-037** and amends **D-160** ruling 4 (**D-176**, narrowly: an admission-guard `paused` mission is unchanged from V0.5; a `paused` mission caused by an A2A-awaiting pause is the
one exception, resumable on the same log). **No fifth `MissionStatus`. No code changed. Nothing in V0.1–V0.5's shipped behaviour is different** except that one amendment, which does not change anything reachable
before V0.6 code exists.

### The approved shape

- **Non-blocking execution (D-165):** `WorkStatus.SUBMITTED`, `NodeStatus.AWAITING`, `RunOutcome.AWAITING`, `RunResult.awaiting: tuple[AwaitingInfo, ...]` (more than one node can be simultaneously outstanding, unlike a
  halt). Submission itself stays one ordinary synchronous port call — A2A's own spec confirms the task id returns synchronously — only *completion* is asynchronous. Nothing protocol-specific ever touches `eidos.runtime`.
- **`AgentTask` (D-166, D-168):** `status` is the real ten-value wire `TaskState` set plus EIDOS-observed `TIMED_OUT`, never collapsed early; a separate, explicit, tested mapping to `NodeStatus` carries EIDOS's own
  decision about each state. Gains `plan_id`, `step_id`, `started_at` (all optional, additive — checked against D-048, D-033, D-082, D-095, D-096, D-098: no contradiction).
- **One continuous `EventLog` across the pause (D-167, subject to D-176):** confirmed against the shipped code that `record_baseline(log=...)` and `Recorder` already support this with no new plumbing; the one real
  blocker was the reducer's unconditional `PAUSED`-is-terminal check, resolved by **D-176**'s narrow, cause-keyed amendment.
- **`MissionStatus.PAUSED` reused (D-169, subject to D-176):** `MissionPausedPayload` carries exactly one of `halt: HaltInfo` or `awaiting: tuple[AwaitingInfo, ...]` (non-empty), the same "exactly one of two" idiom
  already used by `ReplayResult`/`LoadResult`. `HaltInfo` itself is untouched.
- **Caller-orchestrated resume (D-170):** no built-in mission driver or background auto-resume loop. The whole "wait, then continue" story is two ordinary calls a caller makes — append one event, then call
  `record_baseline` again — matching D-119/D-020's mission driver staying unassigned to any milestone.
- **Transport (D-171, resolves D-023):** a hand-rolled client over `httpx` plus the existing `pydantic`, speaking A2A v1.0's JSON-RPC directly — no `a2a-sdk` dependency (its core install alone pulls in `protobuf`,
  `google-api-core`, `googleapis-common-protos`, `json-rpc`, `culsans`, verified from its actual `pyproject.toml`). The EIDOS surface is exactly `message/send`, `tasks/get`, one webhook shape. Protocol conformance
  tests required.
- **No producer sequence (D-172, resolves D-035 negatively):** verified against the spec that none exists on the webhook path. Idempotency stays `event_id` (D-011, unchanged); lateness/duplication is a legal-transition
  guard keyed by `a2a_task_id`, narrower than first proposed once D-174 was settled: "at most one `STARTED`, at most one `COMPLETED`, per task" — the same shape D-162 already built for local node events.
- **Three separate timeout concepts, no new `SystemLimits` dimension (D-173):** transport timeout (adapter HTTP client), A2A task deadline (adapter-level config, produces `TIMED_OUT`), mission execution budget (existing
  counters, unchanged rule; a remote node's duration is computed from `occurred_at` timestamps via `AgentTask.started_at`, never a cross-process monotonic subtraction).
- **Exactly two event types (D-174):** `A2A_TASK_STARTED`, `A2A_TASK_COMPLETED` (already reserved in the vocabulary since D-090) — no new `MissionEventType` member. Completion carries a typed outcome; no separate
  `FAILED`/`TIMED_OUT`/`CANCELED` event types. An intermediate `WORKING` notification is observed by the adapter and produces no event.
- **Research Agent is the single boundary (D-175).**
- **The new reducer operation, named (D-176):** folding `agent_tasks` needs a third pattern beyond the two the reducer already has (append-only for `plans`; first-wins-refuse-the-repeat for node settlement, D-162) —
  find the existing `AgentTask` by `a2a_task_id` and replace that one tuple entry; `A2A_TASK_STARTED` appends instead, since D-172's guard already refuses a second `STARTED` for one id. `MissionState.agent_tasks` stays
  an immutable tuple (D-082 untouched); only the fold rule is new.

### Implementation sequence (proposed; unchanged in shape from the exploration, Step 1 now done)

| Step | What | Proves |
|---|---|---|
| **1** | Exploration, protocol research, the decision record | **Done** — D-165 to D-176 recorded; D-023, D-035, D-036, D-037 resolved; D-160 amended by D-176 |
| **2** | `AgentTask` contract extension: `plan_id`, `step_id`, `started_at`, the closed `TaskState`-plus-`TIMED_OUT` enum replacing the opaque `status` string | Round-trips with the new fields; the lifecycle enum rejects an unenumerated string; the four original V0.1 fields are unaffected **Done** — `AgentTaskStatus` (ten members, D-166) and the three new optional fields land in `eidos.contracts.agent_task`; `eidos.state.agent_tasks` (new) holds the two pieces of typed infrastructure D-166/D-176 called for, neither wired into the reducer: `node_status_for` (the explicit status-to-`NodeStatus` mapping, a total function over all ten members) and `fold_agent_task` (the D-176 find-and-replace-or-append primitive, keyed by `a2a_task_id`, refusing an ambiguous match rather than guessing). `eidos.runtime` is untouched — no A2A name reaches it. One pre-existing guard test's vendor-name list was corrected (`eidos.state`'s own guard forbade the word "a2a" everywhere in the package; D-166/D-176 now explicitly permit it there, so the guard was updated to match, not weakened — every other vendor name it checks is unchanged). 45 tests added (24 in `test_agent_task.py`, replacing one whose premise D-166 invalidated; 21 in the new `test_state_agent_tasks.py`); 13 of 13 mutations caught on the first pass. No A2A client, webhook, payload or reducer branch — those are later steps. Full default suite 2,563 passed, 2 deselected |
| **3** | Runtime extension: `WorkStatus.SUBMITTED`, `NodeStatus.AWAITING`, `RunOutcome.AWAITING`, `RunResult.awaiting`, `AwaitingInfo` | `RunResult`'s validator accepts the new shape the way it already does `halt`/`NOT_REACHED`; no executor control-flow change; mutation-checked like every other runtime change |
| **4** | `eidos.state`: `A2A_TASK_STARTED`/`A2A_TASK_COMPLETED` payloads, the `NodeStatus` mapping (D-166), the `agent_tasks` find-and-replace fold (D-176), the `agent_task_events.py` guard (D-172) | Duplicate `event_id` ignored; a second `STARTED`/`COMPLETED` for one `a2a_task_id` refused, live and on replay, at the same record; the `paused`-cause-aware terminal check (D-176) holds the admission-halt case byte-for-byte |
| **5** | `eidos.a2a` (new package): the hand-rolled client, the non-blocking `WorkAgent` implementation, the webhook receiver | A scripted/fake transport for unit tests, exactly as `ScriptedModel` stands in for a real model; the submission call is shown not to block |
| **6** | The recording adapter: appends to a caller-held, still-open `EventLog` after the owning run has returned | The resulting log replays; `checkpoint_at`/`resume`/`records_after` need no change |
| **7** | `tests/protocol/`: normal completion, timeout, duplicate event, late event, out-of-order event, agent restart, partial artifact, failure — written against D-166's lifecycle, per §59, before the implementation they cover | Every scenario asserts `MissionState` stays authoritative, the remote agent never mutates it, `task_id`/`context_id` are preserved |
| **8** | Scenario: submit → pause `AWAITING` → external completion → resume via `PriorOutcomes` → `VERIFY` → complete, on the reference executor | The whole mission's log — spanning the pause — replays from a fresh interpreter with no agent invoked |
| **9** | Close-out: full suite, LangGraph-blocked unit suite, import audit, frozen-path check, mutation checks, docs | Same rigor as V0.5's close-out |

### Carried forward, not decided

Nothing from D-023, D-035, D-036 or D-037 remains open. What genuinely stays open, unaffected by today's rulings: **D-038** (bounding/persisting the applied-`event_id` set — a longer-lived, paused mission does not change
its kind, only how long it might matter, and it stays with D-017); **D-017** (durable persistence, still not built); **D-129** (the general artifact/data-flow question — a remote task's artifact, once produced, is
written exactly once at final settlement, the same write-once rule D-147 already enforces, needing no store change); whether EIDOS ever actively cancels an in-flight A2A task (`tasks/cancel` — not built, not needed for
V0.6's minimal slice, left for a later milestone if wanted). Two small items are pinned by tests at implementation rather than decided here, matching D-118's own precedent: whether a `COMPLETED` report with no artifact
maps to `SUCCEEDED` or `NO_RESULT` (D-166 proposes: `NO_RESULT`, since a completed task with nothing usable is not a failure of execution), and the exact adapter-level deadline value for `TIMED_OUT` (D-173 — a number,
never invented here, same discipline as D-046).

---

## Intentionally not built yet

Per CLAUDE.md §3, a package is created only when the milestone that fills it begins. These
architectural components are **documented in `docs/03_architecture.md` but not scaffolded** (V0.4's four packages and V0.5's `state/` and `recording/` now exist and are no longer listed):

| Component | Arrives at |
|---|---|
| `planning/` — candidate strategy generation | V0.2+ |
| `policy/` — governance, autonomy, budgets | V1.2 engine (V0.2 has only a `NOT_APPLICABLE` stage in `validation/` — D-110) |
| `telemetry/` — structured events, metrics | V0.9 |
| `memory/` — strategy and execution memory | V1.0 |
| `evaluation/` — evaluation harness, experiments | V1.1 |
| `a2a/` | V0.6 |
| `mcp/` | V0.7 |
| `rag/` | V0.8 |
| `api/` — FastAPI | later (§53 schema not specified) |
| `frontend/` | V1.3 |
| Docker, CI workflows | V1.4 |

Also not created: `docs/architecture_review.md` — that is the *output* of an architecture review
pass (§60), not one of the §81 documents, and it is written when a review is actually run.

---

## Blocked on human owner

Implementation of these is blocked until the corresponding `decisions.md` entry is resolved.
Highest-impact first.

| Item | Blocks | Why it matters |
|---|---|---|
| **D-015** verification confidence computation | V0.4 verification, V1.2 | §31 compares a scalar confidence against a threshold while §18 forbids trusting a model-asserted score. Implementing §31 naively builds the exact anti-pattern the handoff warns against. **V0.4 (D-138):** the verifier is a deterministic rule set, no model verdict, no scalar; stays Open for a scalar (V1.2). |
| **D-043** declared plan limits vs execution counters | **V0.3** (corrected 2026-09-19; was mislabelled V0.2/V0.3) | V0.2 can only count *declared* steps on a static plan, so it needs no reconciliation. The ambiguity becomes live once the V0.3 runtime exists to count actual invocations. Most likely of the bound family to cause a real defect *then*. **V0.3 (D-119, D-127): dormant** — no runtime counting is performed and each node is dispatched at most once per run; still Open. |
| **D-046** numerical bound values | V0.2 values, V0.9+ tuning | Mechanism is unblocked (D-103). Governs only the actual numbers for all seven bound dimensions; never presented as tuned before V0.9 telemetry. |
| **D-111** V0.2 implementation details left unspecified | none blocking | Eight small behaviours implemented conservatively (identity mismatch under SCHEMA; strict `accepted`; dependency re-check; complexity skip rules; limits range; violation order; two exception exports; report carries `plan_id` only). Cheap to reverse; awaiting confirmation. |
| **D-072** omitted vs explicitly-at-ceiling | V0.9, V1.3 | Argues for retaining the requested value alongside the effective one, not for making fields required. |
| **D-066** contract user-supplied or synthesised | mission creation | Synthesis needs numbers D-046 defers; adopting it later would not contradict D-045. |
| **D-012** predicate language for ROUTE/RETRY/REPLAN/TERMINATE | **V0.3** (corrected 2026-09-18; was previously mislabelled V0.2/V0.3) | Deterministic routing needs a defined, validatable condition form. Blocks the compiler, not the V0.2 validator. **V0.3 (D-112, D-127):** does not resolve it — the four conditional kinds are rejected at compile time instead. |
| **D-007** capability vocabulary and matching | **V0.4** (corrected 2026-09-19; not a V0.2 blocker — D-102) | §6 and §7 use incompatible capability names. Untouched by D-102, which sidesteps it for V0.2 by checking against the mission's own `required_capabilities`. **V0.4 (D-132):** a V0.4-only, exact-string set of five; D-007 stays Open. |
| **D-076** payload completeness for replay | V0.5 (discharged for the emitted types by D-153 and D-157; stays Open) | D-010a puts the completeness burden on the event log. V0.5's payloads carry what the reducer and the `ExecutionRecord` need; artifact content and a stop reason are not in the log (D-129, D-151), and the obligation continues for every later event type. |
| **D-075** per-type payload definitions | V0.3–V0.8 (answered for V0.5's emitted types by D-153) | §33 names thirteen types and describes none; V0.5 defines payloads for the types it emits and no others. |
| **D-125** plan-level `RETRY` vs a runtime retry policy | none at V0.3 | Retry appears both as a §13 step kind and as §32 runtime recovery; the handoff never relates them. `RETRY` is compile-rejected and V0.3 has no automatic retry. |
| **D-129** how a work node receives its predecessors' outputs | V0.4 (none at V0.3) | The specified work port `execute(context, node)` passes a node no upstream results, so an edge into a work node carries ordering only; only the verifier receives its predecessors' results. `ArtifactRef` is opaque and no artifact model exists (D-098). **V0.4 (D-137):** answered for V0.4 by an in-memory artifact store; stays Open — a minimal four-field artifact model is defined for V0.4 (D-145). |
| **D-151** non-empty model responses that stopped at the output limit | later: when the model seam is next changed, or V0.5 (D-076) | The adapter returns a normal response whenever `response` has text, whatever `done_reason` says; the seam carries no stop reason; the three V0.4 verifier rules do not detect a cut-off answer. Not observed in any captured non-empty response (all `stop`). Deferred by the owner: not redesigned in V0.4, since no existing contract requires it. |
| **D-071** detached/reusable genome representations | V1.0 | §21 stores derived characteristics, not the genome, so the detached case may never arise. |
| **D-074** is §30's approval wording exactly `autonomy_level >= 3`? | V1.2 | §30 scopes to actions, §29 to the mission. If not equivalent, D-069 dropped a capability rather than a duplicate. |
| **D-059** contract-unsatisfied as `failed` or a fifth state | V0.4 | Invariant 13 requires it distinguishable from a crash; the handoff gives it no event name and no status value. |
| **D-055** `VERIFY`/`HUMAN_APPROVAL` as work steps | not V0.1 | Both remain control-flow kinds meanwhile. Answering after `PlanStep` exists turns an additive change into a rework. **V0.3 (D-124):** `VERIFY` compiles as a control step and `HUMAN_APPROVAL` is unsupported; the question stays Open. |
| **D-063** quality-estimate type | before V0.4 | §19 and invariant 17 require uncertainty representation; the type belongs to whatever produces estimates. |
| **D-064** `confidence` vs `quality` | V0.4; feeds D-042 | The handoff uses both words for what looks like one comparison. Two quantities would mean two contract thresholds. |
| **D-060** is §29 level 3 ordinal or a gate | V1.2 | Levels 0/1/2/4 describe capability; level 3 describes a process. Invariant 14 makes the difference real. |
| **D-062** naming for §40's autonomy budget | before implementation | Shares the word "autonomy" with §29's levels while being a different concept. |
| **D-034** `plan_id`/`event_id` in invariant 18 | none | Two identifiers entered an invariant by derivation, not decision. CLAUDE.md unamended pending the call. |
| **D-032** literal default for `tenant_id` | V0.1, constant only | Split out of D-019 and left Open by the owner. Now typed as a `TenantId` per D-053, so the value is a UUID choice. |
| **D-020** Strategy vs Plan | V0.2, V1.0 | Determines whether one contract or two is needed. |
| **D-029** RAG reformulation loop has no bound | V0.8 | Every other loop in the handoff is explicitly bounded; §24's retrieval loop is not. Invariant 7 says execution never loops. |
| **D-001** docs numbering inconsistency | none | Cosmetic; reported, not resolved. |
| **D-008** lint/type tooling | none | Not adopted, awaiting preference. |
| **D-025** branch/commit conventions | none | Bootstrap used the default branch and a plain message. |

Full detail for each is in [decisions.md](decisions.md).

---

## Session log

| Date | Milestone | Outcome |
|---|---|---|
| 2026-09-22 | **V0.6 Step 2 implemented: the `AgentTask`/state contract changes** | `AgentTaskStatus` (D-166's real ten-value vocabulary) and `plan_id`/`step_id`/`started_at` (D-168) added to `AgentTask`; `eidos.state.agent_tasks` (new) holds `node_status_for` (the D-166 status-to-`NodeStatus` mapping, a total function over all ten members) and `fold_agent_task` (the D-176 find-and-replace-or-append primitive, keyed by `a2a_task_id`, refusing an ambiguous match). Neither is wired into the reducer — no `A2A_TASK_STARTED`/`A2A_TASK_COMPLETED` payload or reducer branch exists yet, and none was built. No A2A client, webhook, transport or timeout configuration. `eidos.runtime` is untouched and stays protocol-neutral. One pre-existing `eidos.state` guard test's vendor-name list forbade the word "a2a" everywhere in the package; corrected to match D-166/D-176's explicit permission, every other vendor name it checks unchanged. 45 tests added (24 in `test_agent_task.py`, one renamed since D-166 invalidated its premise; 21 new in `test_state_agent_tasks.py`); 13 of 13 mutations caught on the first pass. Full default suite **2,563 passed, 2 deselected**, unit suite with the LangGraph family blocked **2,024 passed**. Committed as one focused commit; not pushed. Step 3 not started. |
| 2026-09-22 | **V0.6 protocol and contract design accepted (D-165 to D-176); no code** | Read-only exploration, then owner-directed research against the published A2A Protocol Specification (v1.0) and the actual `a2a-sdk` dependency graph, then two rounds of owner rulings. Recorded **D-165 to D-176 (Accepted)**: a non-blocking `SUBMITTED`/`AWAITING` execution shape; `AgentTask`'s closed ten-value lifecycle with a separate mapping to `NodeStatus`; one continuous `EventLog` across the pause; `AgentTask` gains `plan_id`/`step_id`/`started_at`; `MissionStatus.PAUSED` reused, payload-distinguished; caller-orchestrated resume, no built-in driver; a hand-rolled `httpx` client over A2A v1.0, no `a2a-sdk`; no producer sequence (verified none exists on the wire); three separate timeout concepts, no new `SystemLimits` dimension; exactly two event types; Research Agent as the sole boundary. Resolved **D-023, D-035, D-036, D-037**. **Found and reported, not silently resolved, a contradiction** between the newly-approved D-167/D-169 and the already-shipped D-160 ruling 4 (`paused` unconditionally terminal); the owner ruled **D-176**, a narrow, cause-keyed amendment — an admission-guard pause is unchanged; an A2A-awaiting pause is the one exception. Decision counts: **132 Accepted, 40 Open, 5 Deferred.** Updated `docs/07`, `docs/06`, `docs/12`, `docs/03`, `tests/protocol/README.md`, the README, this file. **No source code changed; the full default suite was rerun for confirmation** (unaffected, as expected). Step 2 not started. |
| 2026-09-21 | **D-163 resolved (D-158 item 1 amended); D-164 left Open; V0.5 pushed** | The owner resolved D-163 by amending D-158's wording to match the implemented recording and observer boundary (the agents, the verifier and the model port are wrapped; the plan stages come from the `observer` hook; a halt is read from the run's result). **No code changed and the recorder was not redesigned.** D-163 moved to Accepted (116 Accepted, 44 Open, 5 Deferred). D-164 stays Open and V0.5 was not reopened for it. Updated D-158, D-162, the README, `docs/03` and `docs/12`. Reran the default suite: **2,524 passed, 2 deselected (118.44 s)**. Pushed the V0.5 commits to origin/master. V0.6 not started. |
| 2026-09-21 | **V0.5 closed as scoped; D-162 ruled (the intake refuses repeated node events); D-163 and D-164 recorded (Open)** | The owner approved D-162 item 1 with the recommended option and kept items 2 to 10 unless one contradicted an Accepted decision. **Implemented the guard:** `eidos.state.step_events`, the intake and the fold refuse a repeated `NODE_STARTED` or `NODE_SETTLED` for the same step of a plan (`REPEATED_STEP_EVENT`), with no per-node state in `MissionState`; removed `ExecutionRecord.repeated_step_events` (a replayed log has none); 21 of 21 mutations caught. **Checked D-162 items 2 to 10 against the Accepted decisions:** item 7 contradicts the wording of D-158 item 1 (the admission guard is not wrapped), so it is **not** kept and is recorded as D-163 (Open); the adjacent question of a start after a settlement is D-164 (Open). Recorded D-162 as Accepted, updated the docs and this file. **Evidence:** full default suite **2,524 passed, 2 deselected (107.66 s)**; unit suite with the LangGraph family blocked **1,985 passed (22.00 s)**; an independent import audit (no layer violation); frozen paths unchanged (`MissionState` and `MeasuredFacts` untouched). All twelve acceptance criteria met; V0.5 closed as scoped. The real-model recording was not run. Nothing pushed. |
| 2026-09-21 | **V0.5 Step 8: close-out review prepared (not accepted)** | Ran the full default suite (**2,503 passed, 2 deselected, 136.19 s**), the unit suite with the LangGraph family blocked (**1,964 passed, 29.29 s**), an independent AST import audit of `src/eidos` (no layer violation) and a frozen-path check (the handoff and the V0.3 and V0.4 packages unchanged apart from the approved observer hook and three event types). Wrote "V0.5 close-out review" and marked each acceptance criterion with its evidence; **criterion 4 is met except for the D-162 item 1 gap**. Updated the README, `docs/03`, `docs/06`, `docs/11`, `docs/12`, the scenarios README, the ladder and the not-built table. V0.5 is not closed; nothing pushed. |
| 2026-09-21 | **V0.5 Steps 5b to 7: recording, the execution record and the chain scenarios; D-162 recorded (Open)** | `eidos.recording` (48 mutations, 6 survived and were closed), `ExecutionRecord` as `execution_record(records)` (38 mutations, 5 survived and were closed), and 84 chain scenarios over nine cases on both executors (16 mutations, 2 survived and were closed). **Found a gap while building the projection:** the reducer applies a repeated `NODE_SETTLED` for a step and folds its counters again (`agent_calls_used` 2 to 3, probed). Recorded, not fixed, as **D-162 (Open)** item 1 with four options; the details settled while building are items 2 to 10, awaiting confirmation. Corrected two numbers in a Step 6 progress row that had been overstated (30 tests and 9 survivors; the counts are 27 and 5 plus 1 scenario test). |
| 2026-09-21 | **D-160 approved with eight rulings (V0.5 Step 1, continued)** | The owner approved the implementation details: `VERIFICATION_FAILED` is not emitted (`NODE_SETTLED` carries the verdict; the type is retained); the optional, observational `observer=None` hook in `run_baseline` is approved; ordering is the EIDOS-assigned sequence only, never inferred from timestamps; `paused` is terminal; a finished run without a successful `VERIFY` is `MISSION_COMPLETED` with `verified` false and a refused plan is `PLAN_REJECTED` then `MISSION_FAILED`; `execution_time_used_ms` is accumulated accounted node execution time, not wall-clock, and no wall-clock metric is invented; D-151 stays Open and `MeasuredFacts` is not modified; and the implementation sequence proceeds. D-160 moved to Accepted. Counts: 114 Accepted, 43 Open, 5 Deferred. No source or test changed by this entry. |
| 2026-09-21 | **V0.5 scope approved; decisions recorded (no code)** | Read-only exploration, then the owner approved the proposal with nine rulings. Recorded **D-152 to D-159 (Accepted)**: the scope; typed payloads through `EventRecord` with the V0.1 envelope unchanged; `NODE_STARTED`, `NODE_SETTLED` and `MISSION_PAUSED` (sixteen types); a pure, outcome-returning reducer; the run-outcome mapping and the counters (recorded, not enforced); an authoritative in-memory event log with a JSONL round trip, checkpoint and replay (no SQLite); recording adapters and facts-only capture; and a thin derived `ExecutionRecord` — **resolving D-010b, D-039 and D-126**. **D-160 (Open):** implementation details awaiting confirmation. **D-161 (Deferred):** what V0.5 excludes. Annotated D-015, D-017, D-038, D-043, D-059, D-067, D-075, D-076, D-090, D-097, D-123, D-127, D-129 and D-151; **D-151, D-129, D-059, D-015, D-017 and the other unrelated Open entries stay Open**, and `MeasuredFacts` is not modified. One correction to the exploration is recorded in D-158: the `Verifier` port returns a verdict and a reason only, so typed per-rule outcomes are not recorded. Counts: 113 Accepted, 44 Open, 5 Deferred. No source or test changed. Not pushed. |
| 2026-09-21 | **V0.4 closed as scoped** | Owner-directed close-out sequence, each gate met in order: (1) option (a′) adopted in the committed opt-in test — 4,096 tokens and a committed 240 s timeout, its own commit, made before the run; (2) the committed baseline test run once from a clean tree — **`finished`, `verified` true, `gather`, `analyse` and `check` `succeeded`, verifier PASS**; (3) D-150 resolved ((a′) and (c) adopted, (b) and (d) not adopted); (4) D-151 logged (Open); (5) the full default suite green — **2,053 passed, 2 deselected, 83.95 s**. V0.4 closed on those two gates; the close-out review now reads "closed" and its "decisions requested" became "decisions taken"; the dated run records are unchanged. No architecture, provider, agent, verifier, runtime or prompt change. Counts: 102 Accepted, 46 Open, 4 Deferred. Push to `origin/master` follows verification, on the owner's direction. |
| 2026-09-21 | **The committed real-model test run once: `finished`, verifier PASS. D-150 resolved; D-151 logged (Open)** | Owner ruling: adopt option (a′). The committed opt-in test now carries `max_output_tokens` 4,096 and a committed 240 s timeout (own commit, made before the run); everything else unchanged. The baseline node of the committed test was run **once from a clean tree** (no tap, retry, re-run or side call; the trivial-completion test not selected): **outcome `finished`, `verified` true; `gather`, `analyse`, `check` all `succeeded`; VERIFY dispatched, verifier PASS; Research 753 characters, 977 tokens, 59.531 s; Analysis 842 characters, 2,582 tokens, 172.203 s (72% of the timeout); pytest 1 passed in 232.93 s.** Counts equal the earlier (a′) run's. **D-150 moved to Accepted:** (a′) and (c) adopted, (b) and (d) not adopted. **D-151 (Open) logged:** a non-empty response that stopped at the output limit is returned as a normal response and can pass verification unmarked; not observed in any run; deferred by the owner, not redesigned in V0.4. Counts: 102 Accepted, 46 Open, 4 Deferred. Not pushed. |
| 2026-09-21 | **D-150 option (a′) tried once: the baseline finished and the verifier returned PASS** | One real baseline attempt at `max_output_tokens` 4,096 and a 240 s timeout (model, temperature, seed, endpoint and mission unchanged; no retry, re-run or side calls; the adapter as changed by option (c); the temporary edit and tap reverted, tree equals `HEAD`, and the committed test still sets 512). **Research: `response` 753 characters, `thinking` 4,226, `done_reason` `stop`, 977 of 4,096 tokens, 53.049 s — identical to the 2,048-run's Research call. Analysis: `response` 842 characters, `thinking` 12,588, `done_reason` `stop`, 2,582 of 4,096 tokens, 154.208 s (64% of the timeout) — the 2,048-run's cut-off reasoning is an exact prefix of it. `VERIFY` dispatched: PASS (schema validity, citation coverage, 3 distinct sources; `min_quality` and `max_risk_level` NOT_EVALUATED). Outcome `finished`, `verified` true.** The PASS measures no quality and does not check that a citation supports its claim. Recorded exactly; nothing changed on the strength of it. D-150 stays Open; V0.4 is not closed. Not pushed. |
| 2026-09-21 | **D-150 option (c) implemented: an empty answer that stopped at the output limit says so** | Owner ruling. In `OllamaModel._interpret`, an empty `response` with `done_reason` exactly `"length"` is still an `EMPTY_RESPONSE` but its message now states that generation stopped at the output limit; every other empty answer keeps the plain message; a non-empty answer is unchanged. **No new kind, and the ModelPort, D-135, agents, verifier, runtime, prompts and settings are untouched.** Five tests (16 cases); **12 of 12 mutations caught**; full default suite **2,053 passed, 2 deselected, 74.98 s**. No real model was run in this step. D-150 stays Open (option (c) done; (a′), (b), (d) and the truncated-answer question remain). Not pushed. |
| 2026-09-21 | **D-150 option (a) tried once: Research succeeded, Analysis failed the same way** | One real baseline attempt at `max_output_tokens` 2,048 (everything else unchanged; the two model calls the mission dispatches; no others; the temporary edit and tap reverted, tree equals `HEAD`). **Research: `response` 753 characters citing `doc:1` to `doc:3`, `done_reason` `stop`, 977 of 2,048 tokens, 52.661 s — stored as `artifact:gather`. Analysis: `response` empty, `thinking` 10,790 characters, `done_reason` `length`, 2,048 of 2,048 tokens, 111.010 s (93% of the 120 s timeout).** `check` skipped; mission `failed`, `verified` false; **the verifier did not run.** Recorded exactly; nothing changed to make the model pass. D-150 stays Open (its option (a) tried once; (a′), (b), (c), (d) remain); a related gap found by reading the code is recorded in it. Counts: 101 Accepted, 46 Open, 4 Deferred. Not pushed. |
| 2026-09-21 | **D-149 resolved by the owner (option 1): the raw response of the baseline's call was printed once** | One real-model run of the baseline test (1 passed in 31.54 s), with a temporary test-only tap on the HTTP layer; the provider, agents, verifier and settings were not touched and the temporary code was reverted (the tree equals its committed state). **Result: `response` empty; `thinking` 2,581 characters ending mid-sentence; `done_reason` `length`; `eval_count` 512 = `num_predict`; `prompt_eval_count` 160; total 30.256 s (load 7.678 s, generation 22.249 s).** The runtime returns this model's reasoning in a separate field and counts it against the output budget; all 512 tokens went to reasoning before any answer, so EIDOS's "the model returned no text" was accurate about the field it reads. The mission outcome was the same as the recorded run (`FAILED`). D-149 moved to Accepted; **D-150 (Open)** logged for what to do about it. Counts: 101 Accepted, 46 Open, 4 Deferred. Not pushed. |
| 2026-09-21 | **V0.4 Step 9: close-out review prepared (not accepted)** | Ran the full default suite (**2,037 passed, 2 deselected, 74.56 s**), an independent AST import audit of `src/eidos` (no core layer imports a new package; no vendor name outside `eidos.providers` and the LangGraph backend; only `pydantic` and LangGraph third-party) and a frozen-path check (handoff unchanged; one V0.1–V0.3 source file changed, `runtime/context.py`). Wrote "V0.4 close-out review": the definition of done, the guards, the invariants exercised and not, the findings and the decisions requested. **Against the handoff's "baseline workflow works end-to-end", it works with a scripted model and has not been shown with a real one (D-149).** Corrected stale documentation (README status, docs/03, the ladder and "not built yet" table, the test READMEs, and ten "Open" references to D-141 to D-143 in their own commit). No source changed. V0.4 is not closed; nothing pushed. |
| 2026-09-21 | **V0.4 Step 8, part 2: the first real baseline run recorded** | The owner ran the two opt-in tests once against `qwen3:4b` (Ollama 0.34.2; temperature 0.0, seed 7, 512 output tokens, 120 s timeout): **2 passed in 38.55 s**. The provider test returned a typed 5-character response (30 prompt tokens, 154 output tokens, 10.156 s). **The baseline mission ended `FAILED`, `verified` false: the Research step's one model call returned no text (`empty_response`) so the step was `no_result`, Analysis and `VERIFY` were skipped, and the verifier was never reached** — no real verdict or quality figure exists. Recorded as printed; the agents, verifier, adapter and tests were not changed to make the model pass. Cause not established; a candidate (reasoning tokens consuming the budget) is unverified and is logged as Open **D-149**. Counts: 100 Accepted, 46 Open, 4 Deferred. Not pushed. |
| 2026-09-20 | **A test-structure defect found and fixed: the unit suite reached LangGraph** | Running the unit suite with the LangGraph family blocked (D-116) failed at collection: `tests/unit/baseline/test_baseline.py`, added in V0.4 Step 7, imported shared helpers that import the LangGraph backend. No product code was affected (`eidos.baseline` and the core never imported it), but the claim that core unit tests run without LangGraph had been true only at V0.3 and was not re-checked at V0.4 Steps 2 to 8 until now. Fixed by moving the pure mission, plan and registry helpers into `eidos_mission_factories` and `eidos_v04_registry` and pointing the unit tests at the reference-executor doubles. **All 1,605 unit tests now pass with LangGraph, LangChain and LangSmith unimportable and none loaded**, and a permanent test (`tests/integration/langgraph/test_unit_suite_without_langgraph.py`) runs that check on every default run; it was shown to fail when the defect is reintroduced. |
| 2026-09-20 | **D-147 guard implemented** | `refuse_a_reused_step` in `eidos.agents.base`, called by the Research and Analysis agents before anything else: if the step's artifact exists under `(execution_id, step_id)`, or `artifact:<step_id>` is already taken (for example by a supplied document), the step is refused with a `FAILED` result whose reason begins `step_id_reused:` and **no model call is made**. The write-once store remains the backstop for a race. Same-plan resume is unaffected: carried-over steps are not dispatched and a failed step wrote nothing. Tests changed because the specification changed (a late "could not be recorded" became an early refusal) and strengthened to assert no model call; new tests cover both halves of the identity, other executions, a failed step running again, resume, the race backstop, and the pinned VERIFY-predecessor limitation. Mutation-checked 10 of 10. No real-model test was run. Not pushed. |
| 2026-09-20 | **D-147 and D-148 accepted** | Owner rulings. **D-147 (option a):** within one execution a newly executed work step must use a fresh step ID across plan versions; artifact identity stays `(execution_id, step_id)` and `artifact:<step_id>`, with no plan-scoped keys or refs in V0.4; before any model call the agent checks for an existing artifact and, if there is one, refuses with a typed failure and makes no call; same-plan resume is preserved. **D-148:** all ten implementation details accepted as written; the **VERIFY-predecessor limitation** (an analysis step cannot follow a `VERIFY` step) recorded, not redesigned. Both moved to Accepted; D-137 annotated. Counts: 100 Accepted, 45 Open, 4 Deferred. This entry is the record only; the guard follows in its own step. |
| 2026-09-20 | **V0.4 Steps 2 to 8 (part 1): implemented; the real-model run is not** | Step 2: `ExecutionContext` carries the frozen `ReliabilityContract` (D-139). Step 3: `eidos.agents` and the `ModelPort` seam. Step 4: `eidos.capabilities` (five lowercase ids, registry, `bind_plan`). Step 5: the four-field artifact model and the in-memory store. Step 6: the Research, Analysis and deterministic Verification agents (`min_quality` and `max_risk_level` NOT_EVALUATED; a PASS never claims contract satisfaction). Step 7: `eidos.baseline` and 24 scenarios on both backends. Step 8 part 1: `eidos.providers.OllamaModel` over standard-library HTTP, tested against a local fake runtime; the `real_model` marker and opt-in tests written and never run against a model. Every step was mutation-checked: 4 of 4, 10 of 10, 12 of 12, 9 of 10 (the tenth an equivalent mutant), 23 of 23, 11 of 11 and 18 of 18 for Steps 2 to 8. 2,023 tests pass, 2 deselected. **Stopped before the real baseline run** so the owner can install the runtime and configure the GPU; nothing has been measured. Logged Open **D-147** (artifact keys across plan versions) and **D-148** (implementation details). Counts: 98 Accepted, 47 Open, 4 Deferred. Nothing pushed. |
| 2026-09-20 | **V0.4 follow-up rulings: D-141, D-142, D-143 resolved** | The owner resolved the three Open entries the V0.4 rulings raised. Recorded **D-144** (lowercase ids — `architecture`, `security`, `cost`, `research`, `verification`; Research serves `research`, Analysis serves the other three; Verification is reached by `VERIFY` node kind, not capability), **D-145** (a four-field artifact model; supplied documents addressed by `ArtifactRef`, namespaced by execution; no per-step input) and **D-146** (only clauses with a defined deterministic measurement are evaluated; `min_quality` is NOT_EVALUATED; a `PASS` never claims contract satisfaction). D-141 to D-143 moved to Accepted; D-132, D-098, D-137 and D-138 annotated. Counts: 98 Accepted, 45 Open, 4 Deferred. No source or test changed by this entry. |
| 2026-09-20 | **V0.4 Step 1 — exploration and decision record (no code)** | Read-only exploration of the V0.4 model, agent and capability boundary, then the owner's rulings on Q1–Q15. Recorded **D-131 to D-140 (Accepted)**: a fixed hand-authored baseline plan run once on LangGraph; five V0.4-only exact-string capabilities; `VERIFY` bound by kind; a registry with typed pre-run rejection of unbound capabilities; a synchronous `ModelPort` owned by `eidos.agents` with providers in `eidos.providers` and explicit, never-defaulted configuration; standard-library HTTP and an opt-in real-model test gate; an in-memory artifact store with the `WorkExecutor` signature unchanged; a deterministic verifier with no model verdict; the frozen `ReliabilityContract` in `ExecutionContext`; read-only agents and an explicit `AdmissionGuard`. **D-006 and D-018 resolved.** D-007, D-055, D-129 and D-015 annotated and left Open. **Three new Open entries:** D-141 (capability spelling, which agent serves what), D-142 (artifact content) and D-143 (contract clauses the verifier cannot evaluate). Counts: 92 Accepted, 48 Open, 4 Deferred. Nine-step sequence recorded. **No source or test changed.** Not pushed. |
| 2026-09-20 | **V0.3 Step 5 — scenario tests and close-out** | Added `tests/scenarios/` — **49 tests** in five files, each driving a real `MissionState` through V0.2 validation, the compiler, a frozen context and both executors (the LangGraph backend is asserted equal to the reference on every scenario): a baseline mission, verification failure and replanning (a replan is a new, separately validated plan version; nothing carries over), halt and resume (a broken guard fails closed; resume equals an uninterrupted run; no automatic retry), the plan gates (rule-breaking plans, non-DSL documents, unsupported kinds and forged acceptance stopped before any executor) and cross-interpreter determinism. **16 of 16 mutation runs caught**, including four that broke both executors identically so only the hand-written expectations could catch them. **1,683 tests pass; nothing in `src/` changed.** V0.3 closed as scoped: ROUTE, RETRY and REPLAN are not mapped (D-112, D-012, D-125 stay Open) and **no product mock agent exists** — flagged for the owner. D-129 stays Open. `tests/scenarios/README.md` and two stale READMEs corrected. Not pushed. |
| 2026-09-20 | **D-130 accepted** | Owner ruling: LangSmith / LangChain tracing stays **off** in V0.3, with **no opt-in**. D-130 moved from Open to Accepted; the Step 4 implementation is the decision as written, so no code changed. Any later export of run data is a separate decision (telemetry proper is V0.9). Counts: 80 Accepted, 47 Open, 4 Deferred. The stale Open-count line in `decisions.md` corrected. |
| 2026-09-20 | **V0.3 Step 4 — the LangGraph dependency, the spike, the adapter and conformance** | Declared the optional `langgraph` extra (`>=1.2.11,<2`, also in `dev`) and installed LangGraph 1.2.11 (38-distribution closure). Ran the spike **S1–S10 against the real library** — every design assumption held, so nothing contradicted D-113 or D-117 — and pinned the results as 41 characterization tests. Two findings the documentation did not carry: the **default recursion limit is 10,007 and environment-driven**, and `langsmith` registers a **pytest plugin** (now disabled in `pyproject.toml`). Implemented `eidos.backends.langgraph.LangGraphExecutor`: one node per compiled node named by position, LangGraph super-steps as levels, state `outcomes` only, no checkpointer/interrupt/retry, `BackendError` for faults. **Conformance: it returns byte-identical results to the reference executor** across 54 shaped scenarios, 9 rejections and 150 seeded random plans. **Found and fixed a data-egress risk:** with `LANGSMITH_TRACING` in the environment a bare run POSTs every node's inputs and outputs to a third party; the adapter forces tracing off, tests prove no network attempt, and it is logged as Open **D-130** with no opt-in. D-116 annotated with the settled version. Core tests verified to pass with LangGraph blocked. D-129 kept Open; no earlier architecture or source modified. Nothing pushed. |
| 2026-09-19 | **V0.3 Step 3 — the runtime and the sequential reference executor** | Implemented `src/eidos/runtime/`: typed results (`NodeResult`, `RunResult`, `PriorOutcomes`, `RunRejection`), a frozen six-field `ExecutionContext` (MissionState only read, once), the synchronous `WorkExecutor` / `Verifier` / `AdmissionGuard` ports, and `SequentialExecutor` — level-synchronous, plan-position order within a level, skip-without-dispatch behind any non-success, independent branches continuing, halt after the current level, no retry, prior `SUCCEEDED` outcomes carried over and never redispatched, invalid prior or context rejected with typed `RunRejection`s, port faults contained as `FAILED`, a faulting guard failing closed. Recorded **D-128** (the reference executor is part of V0.3; resolves D-115's open note) and logged **D-129** (Open): the specified work port passes a node no predecessor outputs. **431 new tests; 1,281 pass in total.** Executor and preconditions mutation-checked 17 of 17, guards 23 of 23. No LangGraph, backend, real agent, MissionState write or event. V0.1, V0.2, the compiler and the handoff untouched. Nothing pushed. |
| 2026-09-19 | **V0.3 Step 2 — the compiled form and `compile_plan`** | Implemented `src/eidos/compiler/`: the immutable, backend-neutral `CompiledPlan` (`WorkNode` / `VerifyNode`, each with `position`, `level` and `predecessors`; self-validating) and `compile_plan(plan, validation_report) -> CompileReport`, which rejects missing, unaccepted or other-plan evidence, re-checks the structure it depends on (duplicate ids, dangling dependencies, cycles) even when handed an accepted report, and rejects `ROUTE`, `RETRY`, `REPLAN`, `TERMINATE` and `HUMAN_APPROVAL` — including plans V0.2 accepted — without ever repairing or dropping a step. Never raises for an invalid plan or report. **276 new tests; 850 pass in total.** Compiler tests mutation-checked 8 of 8, guards 11 of 11. No LangGraph, runtime, ports, executor or MissionState write. **No new decision IDs**: D-112 and D-114 leave the compiled form's shape and failure codes to implementation. V0.1, V0.2 and the handoff untouched. Nothing pushed. |
| 2026-09-19 | **V0.3 Step 1 — architecture rulings recorded** | Explored the V0.3 boundary (design only) and recorded the owner's approvals as **D-112 to D-124**, two Open entries (**D-125** plan-level `RETRY` vs runtime retry policy; **D-126** `MissionEvent` vocabulary for local node lifecycle) and one Deferred register (**D-127**). Scope: only `agent` and `VERIFY` compile; the five other kinds are rejected at compile time and **D-012 stays Open**. **D-040 resolved** by D-113 (MissionState never enters LangGraph state). Level-synchronous execution, seven node statuses, no automatic retry or in-run replan, resume by prior `SUCCEEDED` outcomes, a `PASS`/`FAIL`/`INCONCLUSIVE` verifier with no scalar, synchronous ports with a required `AdmissionGuard`, and **invariant 15 explicitly not exercised**. D-055 recorded as a V0.3-specific implementation decision only — **not resolved**. docs/03 (package mapping), 05, 06 and 12 updated. Settled V0.1/V0.2 decisions not reopened; handoff not modified. **No source code written; nothing pushed.** |
| 2026-09-19 | **V0.2 Plan Validation implemented** | Ruled and recorded D-104..D-110, then implemented in the owner's order, one logical slice per commit: shared test factories moved to `tests/support` (155 tests unchanged); typed `DuplicateStepIdError` / `UnknownDependencyError` and the `EidosModel` export (+10 tests); `validation/limits.py`; `results.py`; iterative `graph.py` with exact antichain width; `stages.py` (incl. a dependency re-check for plans built without validation); `pipeline.py` with `validate_plan_json` / `validate_plan`; static guard tests. **574 tests pass (165 contracts + 409 validation).** POLICY reports `NOT_APPLICABLE`. Logged **D-111** (Open): eight implementation details the approved design left unspecified, implemented conservatively for the owner to confirm. docs/03, 05, 10, 12, README.md (its status line still said "no validator", stale since V0.1) and tests/unit/README updated; docs/10 D-043 row corrected to V0.3 (a missed remnant of the earlier D-043 correction). Nothing pushed. |
| 2026-09-19 | V0.2 rulings recorded | Human owner ruled on the V0.2 design exploration. **D-104**: `max_depth` counts *nodes* (single-node plan = depth 1). **D-105**: V0.2 statically checks only *declared* `max_agent_calls`; the other five budgets are checked only as contract-vs-system-ceiling; nothing is inferred from plan structure. **D-106**: empty plans are legal. **D-107**: JSON text is the untrusted ingress; two typed `ValueError` subclasses are added to V0.1 plan construction. **D-108**: `EidosModel` exported from `eidos.contracts`. **D-109**: shared test factories move to a uniquely named module, own commit, 155-test baseline kept. **D-110**: POLICY stage exists and reports `NOT_APPLICABLE` — no policy semantics, no injection mechanism. D-050 annotated with a pointer to D-104. No source code changed by this entry. |
| 2026-09-19 | V0.2 scoping decisions | **D-102 resolved** by the human owner: V0.2 capability validation is mission-scoped — every `agent` step's `capability` must appear in `TaskGenome.required_capabilities`, exact-string; no global vocabulary, no live-agent check (V0.4). This was a fourth option, not one of the three originally logged. **D-103 resolved**: production `SystemLimits` carries no built-in numeric defaults, values must be explicitly supplied, tests may use labelled fixtures, the handoff's illustrative numbers are not shipped as defaults; confirmed not to contradict D-046/D-009 (it is the stricter of two permitted readings of D-009 rider 5) and D-046's own "Needs" text is annotated as narrowed. **D-043 investigated**: V0.2 only ever validates a static plan, so it can only count *declared* steps; the declared-vs-actual ambiguity only becomes live at V0.3 when a runtime exists. Corrected in decisions.md, docs/05 and here; left Open. Also removed D-042 and D-045 from docs/05's "still open, blocking V0.2" list — both were already Accepted. D-012 confirmed V0.3, not reopened. No source code written. |
| 2026-09-18 | V0.2 scoping analysis | Analysed exactly what V0.2's eight §14 pipeline stages need from D-007, D-012 and D-046, stage by stage, rather than treating "V0.2 is blocked on all three" as one claim. **Found and fixed a self-introduced drift**: D-012 had been called both "a clean V0.2 decision" (decisions.md) and "blocks the compiler" (docs/05) in the same document, and listed as a V0.2 blocker in progress.md — none of V0.2's stages actually reads a step's condition, since V0.1 carries no conditional payload at all (D-047). Corrected across decisions.md, docs/05_plan_dsl.md and progress.md to consistently read V0.3. Schema validation, dependency validation and cycle detection confirmed buildable today with **zero** new decisions, against the V0.1 contracts as they stand. Logged **D-102** (how deep V0.2 capability validation checks, given no agent registry exists until V0.4 — independent of D-007's vocabulary substance) and **D-103** (whether D-046's two handoff-example numbers, `max_execution_time`/`max_tokens`, seed provisional V0.2 values while the other five bound dimensions stay fully open). Neither answered. No source code written. |
| 2026-09-18 | V0.1 Core Contracts — implemented | EXPLORE -> PLAN -> IMPLEMENT -> TEST -> VERIFY per CLAUDE.md §4. Confirmed exact field lists from decisions.md/docs before writing code; presented nine implementation-level ambiguities (A1-A9, none architectural) for approval, then implemented all seven V0.1 contracts exactly as decided plus the approved defaults. `pydantic>=2` and `pytest` installed via `pip install -e ".[dev]"` against the existing pyproject.toml — no dependency change. Fixed one stale doc cross-reference (D-073 mislabelled Open in docs/10) found during EXPLORE. Design choices worth noting: `PlanStep` is a discriminated union (`AgentStep`/`ControlStep`) so the capability required/absent rule is unrepresentable rather than merely rejected, matching docs/05's wording; `tenant_id` defaults to a documented nil-UUID placeholder per D-079, pending D-032; identifiers use `typing.NewType` (static-only distinction) per A2, with runtime consistency carried by the explicit MissionState cross-validators instead; `A2ATaskId`/`A2AContextId` were given NewType wrappers for consistency with every other identifier, which is a small extension beyond D-095's literal wording (a plain `str` would have been an equally faithful reading) — flagged, not hidden. 155 tests pass; full suite green. **No source-code behaviour beyond construction and validation; no cycle detection, runtime, reducer, or predicate language.** No architecture decision reopened. |
| 2026-09-16 | Bootstrap | Read handoff §1–§84. Created project rules, the twelve §81 documents, the decision record with 22 open items, two docstring-only packages, four test layers, and the initial git checkpoint. No runtime behaviour implemented. Two architectural decisions taken by the human owner and recorded: D-004 (Plan DSL canonical form is an ID-addressed DAG) and D-005 (V0.1 in-memory only). D-029 was found while writing `docs/09`: §24's retrieval loop is the only loop in the handoff with no stated bound. |
| 2026-09-16 | Risk vocabulary | **D-051 resolved**: task risk is one vocabulary shared by `TaskGenome.risk_level` and `ReliabilityContract.max_risk_level`; §40 action risk and §28 tool risk are separate concepts, untyped in V0.1; §40's five-point scale explicitly declined (experimental per §40 itself, action-shaped, and `medium/high` is not a single value); no replacement invented. Value set deferred as **D-056**. D-051 answered **D-030** by implication, which was raised rather than allowed to close silently; **D-030 ratified explicitly**: assessed and tolerated risk are distinct quantities, one field in each model, with calculation out of scope and logged as **D-057**. `docs/04` and `docs/10` updated. **No source code written.** |
| 2026-09-16 | PlanStep kind taxonomy | Analysed D-049 and D-050; both **resolved** by the human owner. **D-049 = option B**: a capability-bearing work-step category distinct from control-flow steps, `capability` required on the former and absent from the latter. Option C was eliminated on the handoff's own terms — with no capability-bearing kind, §14's capability-validation stage is vacuous and invariant 11 unenforceable. **D-050 = option D**: `SEQUENTIAL`/`PARALLEL` are not canonical kinds; ordering is the edge structure, and they may return only as authoring-surface sugar normalizing to the same DAG. This is the reading under which D-004 and §13 are both true as written. **D-055** logged Open: whether `VERIFY` and `HUMAN_APPROVAL` are themselves work steps. D-004 and D-047 unmodified. `PlanStep` is now unblocked. **No source code written.** |
| 2026-09-16 | V0.1 contract spec review | Drafted the V0.1 contract specification for review. Four findings surfaced and were logged as Open rather than resolved: **D-049** (`AGENT` is in §13's example but not its primitive list), **D-050** (`SEQUENTIAL`/`PARALLEL` may be redundant under D-004's DAG — a consequence of D-004 not visible when it was taken), **D-051** (the `RiskLevel` value set), **D-052** (`MissionStatus` values not named by the handoff). Two minor representation questions also logged: D-053, D-054. D-004 and D-047 left unmodified. A standing rule was recorded: no placeholder enum or inferred value may be invented to make code compile. **No source code written.** |
| 2026-09-16 | Pre-V0.1 decisions | Architectural review of the five decisions blocking V0.1, one at a time, each analysed against the handoff before being decided by the human owner. **All five resolved:** D-013 (disjoint TaskGenome/ReliabilityContract), D-019 (`tenant_id` required, no security meaning), D-011 (layered event model; `event_id` idempotency key, EIDOS-assigned mission sequence), D-010a (MissionState is a materialized view over the event log), D-009 (bounds split into system safety limits and mission budgets; reject never clamp; no V0.1 values). Sixteen sub-questions were split out and deliberately left Open rather than resolved by implication: D-030 through D-046 minus D-010a/b numbering. D-034 records that `plan_id` and `event_id` entered invariant 18 by derivation rather than decision — CLAUDE.md unamended pending the owner's call. `docs/04`, `docs/05`, `docs/06`, `docs/10`, `docs/12` synced. No code written. |
