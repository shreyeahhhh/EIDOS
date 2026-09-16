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
- [x] `decisions.md` — 16 Accepted, 39 Open, 3 Deferred (counts current as of the latest decision below)
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

**But V0.1 is not fully unblocked.** Two Open items predating this round still touch V0.1 and were
not part of the five:

- **D-014** — does `autonomy_level` use §29's 0–4 scale? Determines a `TaskGenome` field's type.
- **D-016** — the quality function. Determines whether the contract's quality threshold is a plain
  value or a structured type.

A further three affect one field or one flag each: **D-031** (`evidence_requirements` threshold or
description), **D-042** (exact contract budget field list), **D-045** (no contract supplied).

**Two items still block the fields they type:**

- **D-056** — the concrete task-risk value set. D-051 settled the structure; the handoff supplies no
  task-risk scale and §40's was explicitly declined. `TaskGenome` and `ReliabilityContract` should
  be written **last** among the seven contracts for this reason.
- **D-052** — `MissionStatus` values beyond the four states §32 and §33 name.

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
| **D-030** assessed vs tolerated risk | V0.1, one field | Split out of D-013 and left Open by the owner. |
| **D-031** `evidence_requirements` threshold or description | V0.1, one field | Split out of D-013 and left Open by the owner. |
| **D-036** `AgentTask` lifecycle state machine | V0.6 | §10 mandates deterministic accept/reject "against lifecycle"; §8 never enumerates states or transitions. V0.6 protocol tests cannot be written without it. |
| **D-043** declared plan limits vs execution counters | V0.2, V0.3 | Five limit names appear in both §14 and §32 while counting different things. Most likely of the bound family to cause a real defect. |
| **D-046** numerical bound values | V0.2 | None established in V0.1 by decision; tuned from V0.9 telemetry, never presented as tuned before then. |
| **D-042** exact contract budget field list | V0.1, field list | §14's list is "such as"; §30's example carries two of six. |
| **D-045** no ReliabilityContract supplied | V0.1, one flag | §30 makes the contract optional; with no contract, "satisfied" is undefined. |
| **D-012** predicate language for ROUTE/RETRY/REPLAN/TERMINATE | V0.2, V0.3 | Deterministic routing needs a defined, validatable condition form. |
| **D-007** capability vocabulary and matching | V0.2, V0.4 | §6 and §7 use incompatible capability names. |
| **D-006** MVP agent set: 3 or 5 capabilities | V0.4 | §49 says three; §16/§43 use five. |
| **D-016** the quality function | V0.1, V1.0 | `quality_threshold` has no measurement procedure. |
| **D-056** task-risk value set | **V0.1, two field types** | Structure settled by D-051; the handoff supplies no task-risk scale and §40's was declined. Product judgement, not derivable. |
| **D-055** `VERIFY`/`HUMAN_APPROVAL` as work steps | not V0.1 | Both remain control-flow kinds meanwhile. Answering after `PlanStep` exists turns an additive change into a rework. |
| **D-052** `MissionStatus` value set | **V0.1, one field's type** | Only four states are handoff-named; planning/execution states are not. |
| **D-014** `autonomy_level` scale | V0.1, one field's type | Predates the blocking round; §6's example uses `1`, §29 defines 0–4, the link is never stated. |
| **D-016** quality function | V0.1, one field's type | Predates the blocking round; determines whether the quality threshold is a plain value or structured. |
| **D-034** `plan_id`/`event_id` in invariant 18 | none | Two identifiers entered an invariant by derivation, not decision. CLAUDE.md unamended pending the call. |
| **D-032** literal default for `tenant_id` | V0.1, constant only | Split out of D-019 and left Open by the owner. |
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
