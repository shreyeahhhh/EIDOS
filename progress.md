# progress.md — EIDOS Implementation Tracking

Status only. Rules live in [CLAUDE.md](CLAUDE.md). Decisions and open questions live in
[decisions.md](decisions.md). The canonical specification is `EIDOS_CLAUDE_CODE_HANDOFF.md`.

---

## Current state

**Milestone: BOOTSTRAP — complete.**
**Next milestone: V0.1 Core Contracts — not started, partially blocked (see "Blocked on human owner").**

No EIDOS runtime behaviour exists. There is no planner, no validator, no compiler, no runtime, no
agents, no state reducer, no A2A, no MCP, no RAG, no persistence, no telemetry, no API and no
frontend. The repository contains project rules, the derived documentation set, the decision record,
two empty package boundaries and four empty test layers.

No measurement of any kind has been taken, so no metric appears anywhere in this repository.

### Bootstrap deliverables

- [x] `CLAUDE.md` — permanent rules, 18 architecture invariants
- [x] `progress.md` — this file
- [x] `decisions.md` — 41 Accepted, 57 Open, 3 Deferred (counts current as of the latest decision below)
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
| **V0.1** Core Contracts | `TaskGenome`, `ReliabilityContract`, `MissionState`, `MissionEvent`, `Plan`, `PlanStep`, `AgentTask`. No real agents, no A2A, no MCP, no frontend. In-memory only (D-005). | Not started — partially blocked |
| **V0.2** Plan DSL | Schema validation, cycle detection, dependency validation, depth limits, node limits, parallel-branch limits, capability validation, policy validation. | Not started — blocked (D-004 settles the DAG form; D-007, D-009, D-012 still open) |
| **V0.3** LangGraph Runtime | Map `SEQUENTIAL`, `PARALLEL`, `ROUTE`, `VERIFY`, `RETRY`, `REPLAN` into runtime nodes. Mock agents. | Not started |
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

## Next milestone — V0.1 Core Contracts

Scope from §50 and §82. In-memory typed contracts, deterministic validation-oriented structures,
and tests. **No persistence (D-005). No behaviour beyond construction and validation.**

Planned modules under `src/eidos/contracts/`:

- `TaskGenome` — §6
- `ReliabilityContract` — §30
- `MissionState` — §9, §10
- `MissionEvent` — §10, §33
- `Plan`, `PlanStep` — §13, as an ID-addressed DAG (D-004)
- `AgentTask` — §8

Each needs unit tests in `tests/unit/` covering construction, field validation, rejection of invalid
input, and the failure paths — not only the happy path (§61, CLAUDE.md §6).

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

**All architectural V0.1 decisions are settled; what remains is representation.** None of D-077–D-083
touches an invariant — but together they mean **no contract is currently constructible without an
invention**, which is a sharper statement than "five of seven are writable" made earlier in this
session. Per-contract blockers:

| Contract | Blocked by |
|---|---|
| `AgentTask` | D-081 |
| `ReliabilityContract` | D-078 |
| `TaskGenome` | D-077, D-078, D-079, D-080 |
| `Plan` | D-077, D-082 |
| `PlanStep` | D-077, D-080 |
| `MissionEvent` | D-077, D-079, D-083 |
| `MissionState` | D-077, D-078, D-079, D-082, D-083 |

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

## Intentionally not built yet

Per CLAUDE.md §3, a package is created only when the milestone that fills it begins. These
architectural components are **documented in `docs/03_architecture.md` but not scaffolded**:

| Component | Arrives at |
|---|---|
| `capabilities/` — capability vocabulary and agent registry | V0.2 / V0.4 |
| `planning/` — candidate strategy generation | V0.2+ |
| `validation/` — plan validation pipeline | V0.2 |
| `compiler/` — Plan DSL → runtime graph | V0.3 |
| `runtime/` — LangGraph execution | V0.3 |
| `agents/` — Research, Analysis, Verification | V0.4 |
| `state/` — reducer, checkpoints, replay | V0.5 |
| `policy/` — governance, autonomy, budgets | V0.2 hooks / V1.2 engine |
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
| **D-040** MissionState / LangGraph split | V0.3 | Principle set by D-010a; the concrete division is inherited work when a runtime exists. |
| **D-039** reducer signature | V0.5 | A determinism requirement that produces no observable output cannot be tested. |
| **D-010b** checkpoint semantics | V0.5 | Contents, granularity and trigger unspecified. Entangled with D-017. |
| **D-036** `AgentTask` lifecycle state machine | V0.6 | §10 mandates deterministic accept/reject "against lifecycle"; §8 never enumerates states or transitions. V0.6 protocol tests cannot be written without it. |
| **D-043** declared plan limits vs execution counters | V0.2, V0.3 | Five limit names appear in both §14 and §32 while counting different things. Most likely of the bound family to cause a real defect. |
| **D-046** numerical bound values | V0.2 | None established in V0.1 by decision; tuned from V0.9 telemetry, never presented as tuned before then. |
| **D-084** MissionState before TaskGenome | **V0.1** | §73/§41 show `Mission created` before `Task Genome generated`; D-010a's fold starts at `MISSION_CREATED`. |
| **D-085** `execution_id` at creation | **V0.1** | Mission-to-execution cardinality unstated. |
| **D-086** `occurred_at` for internal events | **V0.1** | No separate producer clock for internal events; V0.1 emits only internal events. Tied to D-037. |
| **D-087** collection emptiness | V0.1 or V0.2 | Narrowed by D-091; still open for `required_capabilities`, `allowed_actions`, `Plan.steps`. |
| **D-100** where the ReliabilityContract lives | **V0.1** | D-089's by-id reference leaves the contract with no container; D-010a's MissionState never held it. The runtime cannot reach the limits its counters measure against. |
| **D-098** `latest_artifact` representation | **V0.1** | Deferred until artifacts are defined — but an optional field still needs a type. Exclude from V0.1, or choose one. |
| **D-099** `information_dependencies` representation | **V0.1** | Same tension as D-098. No example of its content exists anywhere in the handoff. |
| **D-078** units for time and token budgets | **V0.1** | The handoff uses ms (§6), seconds (§53) and minutes (§30) for latency. D-046's values would be meaningless without a canonical unit. |
| **D-079** `tenant_id` required vs defaulted | **V0.1, five roots** | D-019 says both "required" and "carries a default"; those conflict. Determines whether D-032 is needed at all. |
| **D-080** `capability` representation | **V0.1** | D-049 gave work steps a capability; the carrier's type was never decided. "Opaque identifier" was a Claude Code assumption, not a decision. |
| **D-081** `AgentTask.status` representation | **V0.1** | D-048 left semantics open under D-036 but said nothing about type. Any enum would pre-empt D-036. |
| **D-082** `MissionState` collections and `Plan.version` | **V0.1** | Plan ordering, `agent_tasks` keying (§8 gives AgentTask no id), counter types, and the version rule are all unstated. |
| **D-083** timestamp representation | **V0.1** | D-054 settled where timestamps come from, not what they are. Matters for cross-process ordering at V0.6. |
| **D-072** omitted vs explicitly-at-ceiling | V0.9, V1.3 | Argues for retaining the requested value alongside the effective one, not for making fields required. |
| **D-066** contract user-supplied or synthesised | mission creation | Synthesis needs numbers D-046 defers; adopting it later would not contradict D-045. |
| **D-012** predicate language for ROUTE/RETRY/REPLAN/TERMINATE | V0.2, V0.3 | Deterministic routing needs a defined, validatable condition form. |
| **D-007** capability vocabulary and matching | V0.2, V0.4 | §6 and §7 use incompatible capability names. |
| **D-006** MVP agent set: 3 or 5 capabilities | V0.4 | §49 says three; §16/§43 use five. |
| **D-076** payload completeness for replay | V0.5, with D-039 | D-010a puts the completeness burden on the event log; deferring payloads defers when that becomes testable. |
| **D-075** per-type payload definitions | V0.3–V0.8 | §33 names thirteen types and describes none. |
| **D-071** detached/reusable genome representations | V1.0 | §21 stores derived characteristics, not the genome, so the detached case may never arise. |
| **D-074** is §30's approval wording exactly `autonomy_level >= 3`? | V1.2 | §30 scopes to actions, §29 to the mission. If not equivalent, D-069 dropped a capability rather than a duplicate. |
| **D-059** contract-unsatisfied as `failed` or a fifth state | V0.4 | Invariant 13 requires it distinguishable from a crash; the handoff gives it no event name and no status value. |
| **D-055** `VERIFY`/`HUMAN_APPROVAL` as work steps | not V0.1 | Both remain control-flow kinds meanwhile. Answering after `PlanStep` exists turns an additive change into a rework. |
| **D-063** quality-estimate type | before V0.4 | §19 and invariant 17 require uncertainty representation; the type belongs to whatever produces estimates. |
| **D-064** `confidence` vs `quality` | V0.4; feeds D-042 | The handoff uses both words for what looks like one comparison. Two quantities would mean two contract thresholds. |
| **D-060** is §29 level 3 ordinal or a gate | V1.2 | Levels 0/1/2/4 describe capability; level 3 describes a process. Invariant 14 makes the difference real. |
| **D-062** naming for §40's autonomy budget | before implementation | Shares the word "autonomy" with §29's levels while being a different concept. |
| **D-034** `plan_id`/`event_id` in invariant 18 | none | Two identifiers entered an invariant by derivation, not decision. CLAUDE.md unamended pending the call. |
| **D-032** literal default for `tenant_id` | V0.1, constant only | Split out of D-019 and left Open by the owner. Now typed as a `TenantId` per D-053, so the value is a UUID choice. |
| **D-020** Strategy vs Plan | V0.2, V1.0 | Determines whether one contract or two is needed. |
| **D-018** model-provider abstraction boundary | V0.4 | Invariant 9 forbids vendor names in core layers; the boundary's owner is unspecified. |
| **D-029** RAG reformulation loop has no bound | V0.8 | Every other loop in the handoff is explicitly bounded; §24's retrieval loop is not. Invariant 7 says execution never loops. |
| **D-001** docs numbering inconsistency | none | Cosmetic; reported, not resolved. |
| **D-008** lint/type tooling | none | Not adopted, awaiting preference. |
| **D-025** branch/commit conventions | none | Bootstrap used the default branch and a plain message. |

Full detail for each is in [decisions.md](decisions.md).

---

## Session log

| Date | Milestone | Outcome |
|---|---|---|
| 2026-09-16 | Bootstrap | Read handoff §1–§84. Created project rules, the twelve §81 documents, the decision record with 22 open items, two docstring-only packages, four test layers, and the initial git checkpoint. No runtime behaviour implemented. Two architectural decisions taken by the human owner and recorded: D-004 (Plan DSL canonical form is an ID-addressed DAG) and D-005 (V0.1 in-memory only). D-029 was found while writing `docs/09`: §24's retrieval loop is the only loop in the handoff with no stated bound. |
| 2026-09-16 | Risk vocabulary | **D-051 resolved**: task risk is one vocabulary shared by `TaskGenome.risk_level` and `ReliabilityContract.max_risk_level`; §40 action risk and §28 tool risk are separate concepts, untyped in V0.1; §40's five-point scale explicitly declined (experimental per §40 itself, action-shaped, and `medium/high` is not a single value); no replacement invented. Value set deferred as **D-056**. D-051 answered **D-030** by implication, which was raised rather than allowed to close silently; **D-030 ratified explicitly**: assessed and tolerated risk are distinct quantities, one field in each model, with calculation out of scope and logged as **D-057**. `docs/04` and `docs/10` updated. **No source code written.** |
| 2026-09-16 | PlanStep kind taxonomy | Analysed D-049 and D-050; both **resolved** by the human owner. **D-049 = option B**: a capability-bearing work-step category distinct from control-flow steps, `capability` required on the former and absent from the latter. Option C was eliminated on the handoff's own terms — with no capability-bearing kind, §14's capability-validation stage is vacuous and invariant 11 unenforceable. **D-050 = option D**: `SEQUENTIAL`/`PARALLEL` are not canonical kinds; ordering is the edge structure, and they may return only as authoring-surface sugar normalizing to the same DAG. This is the reading under which D-004 and §13 are both true as written. **D-055** logged Open: whether `VERIFY` and `HUMAN_APPROVAL` are themselves work steps. D-004 and D-047 unmodified. `PlanStep` is now unblocked. **No source code written.** |
| 2026-09-16 | V0.1 contract spec review | Drafted the V0.1 contract specification for review. Four findings surfaced and were logged as Open rather than resolved: **D-049** (`AGENT` is in §13's example but not its primitive list), **D-050** (`SEQUENTIAL`/`PARALLEL` may be redundant under D-004's DAG — a consequence of D-004 not visible when it was taken), **D-051** (the `RiskLevel` value set), **D-052** (`MissionStatus` values not named by the handoff). Two minor representation questions also logged: D-053, D-054. D-004 and D-047 left unmodified. A standing rule was recorded: no placeholder enum or inferred value may be invented to make code compile. **No source code written.** |
| 2026-09-16 | Pre-V0.1 decisions | Architectural review of the five decisions blocking V0.1, one at a time, each analysed against the handoff before being decided by the human owner. **All five resolved:** D-013 (disjoint TaskGenome/ReliabilityContract), D-019 (`tenant_id` required, no security meaning), D-011 (layered event model; `event_id` idempotency key, EIDOS-assigned mission sequence), D-010a (MissionState is a materialized view over the event log), D-009 (bounds split into system safety limits and mission budgets; reject never clamp; no V0.1 values). Sixteen sub-questions were split out and deliberately left Open rather than resolved by implication: D-030 through D-046 minus D-010a/b numbering. D-034 records that `plan_id` and `event_id` entered invariant 18 by derivation rather than decision — CLAUDE.md unamended pending the owner's call. `docs/04`, `docs/05`, `docs/06`, `docs/10`, `docs/12` synced. No code written. |
