# progress.md — EIDOS Implementation Tracking

Status only. Rules live in [CLAUDE.md](CLAUDE.md). Decisions and open questions live in
[decisions.md](decisions.md). The canonical specification is `EIDOS_CLAUDE_CODE_HANDOFF.md`.

---

## Current state

**Milestone: V0.2 Plan Validation — implemented and tested (on top of V0.1 Core Contracts).**

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

**V0.3 (LangGraph Runtime): scope approved; Step 2 implemented.** The architecture rulings are recorded as
D-112 to D-127 (2026-09-19). Step 2 added `src/eidos/compiler/` — the immutable compiled form and
`compile_plan` — and nothing else: there is **no runtime, no executor, no ports, no LangGraph adapter and no
LangGraph dependency yet**. See "V0.3 LangGraph Runtime" below. **850 tests pass** (165 in
`tests/unit/contracts/`, 409 in `tests/unit/validation/`, 276 in `tests/unit/compiler/`).

There is still no planner, no runtime, no agents, no state reducer, no A2A, no MCP, no RAG, no persistence,
no telemetry, no API and no frontend.

No measurement of any kind has been taken, so no metric appears anywhere in this repository.

### Bootstrap deliverables

- [x] `CLAUDE.md` — permanent rules, 18 architecture invariants
- [x] `progress.md` — this file
- [x] `decisions.md` — 78 Accepted, 46 Open, 4 Deferred (counts current as of the latest decision below)
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
| **V0.3** LangGraph Runtime | Map `SEQUENTIAL`, `PARALLEL`, `ROUTE`, `VERIFY`, `RETRY`, `REPLAN` into runtime nodes. Mock agents. | **In progress — scope approved 2026-09-19 (D-112 to D-127); Step 2 done: the compiled form and `compile_plan` (276 tests).** Narrowed from §50's list: only `agent` and `VERIFY` compile; `ROUTE`, `RETRY`, `REPLAN`, `TERMINATE`, `HUMAN_APPROVAL` are rejected at compile time and D-012 stays Open. **Not started:** the runtime, execution ports, admission guard, level scheduling, mock agents and the LangGraph adapter. |
| **V0.4** Real Local Agents | Research, Analysis, Verification. Baseline workflow end-to-end. | Not started — blocked (D-006) |
| **V0.5** MissionState + Event Reducer | `MissionEvent`, `MissionState`, `StateReducer`, checkpoints, replay. §50: state handling must be reliable **before** A2A. | Not started — blocked (D-010, D-011) |
| **V0.6** One A2A Boundary | Move exactly one agent into an independent process. Test: normal completion, timeout, duplicate event, late event, agent restart, partial artifact, failure. | Not started — deferred (D-026) |
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

## V0.3 LangGraph Runtime — scope approved; Step 2 implemented (2026-09-19)

**Step 1 — the decision record — is done, and Step 2 — the compiled form and `compile_plan` — is
implemented** (see "Step 2" below). Nothing in V0.1 or V0.2 was changed by either. The design behind these rulings is the V0.3 exploration (2026-09-19);
LangGraph behaviour cited there came from its documentation and is **unverified** until it is installed and
exercised.

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
- The `ExecutionContext` field set; the halt-reason set; `RunRejection` codes beyond invalid prior state
  (for example a context mismatch); how a backend fault surfaces (proposed: an exception, not an outcome).
- The `AdmissionGuard` request shape and purity requirement (proposed: a pure function of level facts, so
  its answer does not depend on scheduling order).
- **Whether `eidos.runtime` ships a sequential reference executor** (proposed as production code and as the
  conformance oracle for the LangGraph backend). Not part of A1–A12; flagged in D-115.
- Whether a `FINISHED` run with no passed `VERIFY` node is labelled unverified (proposed).
- The optional extra's name and any version constraint (D-116) — settled against what is installed.
- LangGraph behaviours to verify by spike before the adapter is designed in detail: join semantics when a
  predecessor did not succeed; deterministic results under a disjoint-key merge; terminal and multi-entry
  wiring; setting the recursion limit per run; running with no checkpointer; dependency footprint and Python
  3.11–3.13 support; a blocking synchronous port under parallel execution.

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

**Not done in Step 2, by scope:** the runtime executor, the reference executor, execution ports, the
admission guard, the verification runtime, level scheduling, mock agents, retry, the replan driver, event
emission, any MissionState write, and LangGraph and its dependency.

### Sequence (proposed; each step after 1 needs the owner's go-ahead)

1. **Record the rulings.** *Done.*
2. **The compiled form, compile failures and `compile_plan`, with tests.** *Done* — the exploration's steps 2
   and 3 were delivered together, as instructed.
3. Runtime result types, ports and `ExecutionContext`.
4. Level semantics and mock agents (plus the reference executor, if confirmed).
5. The optional extra, the LangGraph spike and the adapter.
6. Differential and scenario tests.
7. Guards, docs and this file.

---

## Intentionally not built yet

Per CLAUDE.md §3, a package is created only when the milestone that fills it begins. These
architectural components are **documented in `docs/03_architecture.md` but not scaffolded**:

| Component | Arrives at |
|---|---|
| `capabilities/` — capability vocabulary and agent registry | V0.4 (V0.2 needed neither — D-102) |
| `planning/` — candidate strategy generation | V0.2+ |
| `runtime/` — backend-neutral execution semantics, results, ports (D-115) | V0.3 |
| `backends/langgraph/` — the LangGraph adapter; the only importer of LangGraph (D-115) | V0.3 |
| `agents/` — Research, Analysis, Verification | V0.4 |
| `state/` — reducer, checkpoints, replay | V0.5 |
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
| **D-015** verification confidence computation | V0.4 verification, V1.2 | §31 compares a scalar confidence against a threshold while §18 forbids trusting a model-asserted score. Implementing §31 naively builds the exact anti-pattern the handoff warns against. |
| **D-039** reducer signature | V0.5 | A determinism requirement that produces no observable output cannot be tested. |
| **D-010b** checkpoint semantics | V0.5 | Contents, granularity and trigger unspecified. Entangled with D-017. |
| **D-036** `AgentTask` lifecycle state machine | V0.6 | §10 mandates deterministic accept/reject "against lifecycle"; §8 never enumerates states or transitions. V0.6 protocol tests cannot be written without it. |
| **D-043** declared plan limits vs execution counters | **V0.3** (corrected 2026-09-19; was mislabelled V0.2/V0.3) | V0.2 can only count *declared* steps on a static plan, so it needs no reconciliation. The ambiguity becomes live once the V0.3 runtime exists to count actual invocations. Most likely of the bound family to cause a real defect *then*. **V0.3 (D-119, D-127): dormant** — no runtime counting is performed and each node is dispatched at most once per run; still Open. |
| **D-046** numerical bound values | V0.2 values, V0.9+ tuning | Mechanism is unblocked (D-103). Governs only the actual numbers for all seven bound dimensions; never presented as tuned before V0.9 telemetry. |
| **D-111** V0.2 implementation details left unspecified | none blocking | Eight small behaviours implemented conservatively (identity mismatch under SCHEMA; strict `accepted`; dependency re-check; complexity skip rules; limits range; violation order; two exception exports; report carries `plan_id` only). Cheap to reverse; awaiting confirmation. |
| **D-072** omitted vs explicitly-at-ceiling | V0.9, V1.3 | Argues for retaining the requested value alongside the effective one, not for making fields required. |
| **D-066** contract user-supplied or synthesised | mission creation | Synthesis needs numbers D-046 defers; adopting it later would not contradict D-045. |
| **D-012** predicate language for ROUTE/RETRY/REPLAN/TERMINATE | **V0.3** (corrected 2026-09-18; was previously mislabelled V0.2/V0.3) | Deterministic routing needs a defined, validatable condition form. Blocks the compiler, not the V0.2 validator. **V0.3 (D-112, D-127):** does not resolve it — the four conditional kinds are rejected at compile time instead. |
| **D-007** capability vocabulary and matching | **V0.4** (corrected 2026-09-19; not a V0.2 blocker — D-102) | §6 and §7 use incompatible capability names. Untouched by D-102, which sidesteps it for V0.2 by checking against the mission's own `required_capabilities`. |
| **D-006** MVP agent set: 3 or 5 capabilities | V0.4 | §49 says three; §16/§43 use five. |
| **D-076** payload completeness for replay | V0.5, with D-039 | D-010a puts the completeness burden on the event log; deferring payloads defers when that becomes testable. |
| **D-075** per-type payload definitions | V0.3–V0.8 | §33 names thirteen types and describes none. |
| **D-125** plan-level `RETRY` vs a runtime retry policy | none at V0.3 | Retry appears both as a §13 step kind and as §32 runtime recovery; the handoff never relates them. `RETRY` is compile-rejected and V0.3 has no automatic retry. |
| **D-126** `MissionEvent` vocabulary for local node lifecycle | V0.5 or later | The thirteen §33 types (D-090) cannot represent a local node starting, finishing, failing or being skipped, and there is no payload (D-067). Invariant 15 is not exercised in V0.3 (D-123). |
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
| **D-018** model-provider abstraction boundary | V0.4 | Invariant 9 forbids vendor names in core layers; the boundary's owner is unspecified. **V0.3 (D-122):** only the execution-side port interface is defined; this stays Open. |
| **D-029** RAG reformulation loop has no bound | V0.8 | Every other loop in the handoff is explicitly bounded; §24's retrieval loop is not. Invariant 7 says execution never loops. |
| **D-001** docs numbering inconsistency | none | Cosmetic; reported, not resolved. |
| **D-008** lint/type tooling | none | Not adopted, awaiting preference. |
| **D-025** branch/commit conventions | none | Bootstrap used the default branch and a plain message. |

Full detail for each is in [decisions.md](decisions.md).

---

## Session log

| Date | Milestone | Outcome |
|---|---|---|
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
