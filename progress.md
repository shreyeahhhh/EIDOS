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
- [x] `decisions.md` — 4 Accepted, 22 Open, 3 Deferred
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

**V0.1 cannot begin cleanly until the blocking items below are answered.** The ones that must be
resolved first are D-010 (MissionState fields and reducer contract), D-013 (TaskGenome vs
ReliabilityContract overlap and authority), D-011 (event ordering and idempotency key) and D-019
(`tenant_id` in V0.1 models). D-009 (bound values and their origin) is needed before the bounds land
in any contract.

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
| **D-010** MissionState fields, reducer signature, checkpoints | V0.1, V0.5 | The state shape is never enumerated in the handoff. |
| **D-013** TaskGenome vs ReliabilityContract overlap | V0.1 | Four fields appear in both with no stated relationship. |
| **D-011** event ordering and idempotency key | V0.1, V0.5, V0.6 | "sequence/version" is undefined; duplicate and late-event semantics depend on it. |
| **D-009** bound values and their origin | V0.2 | Every budget dimension is named; none has a value or a source of authority. |
| **D-012** predicate language for ROUTE/RETRY/REPLAN/TERMINATE | V0.2, V0.3 | Deterministic routing needs a defined, validatable condition form. |
| **D-007** capability vocabulary and matching | V0.2, V0.4 | §6 and §7 use incompatible capability names. |
| **D-006** MVP agent set: 3 or 5 capabilities | V0.4 | §49 says three; §16/§43 use five. |
| **D-016** the quality function | V0.1, V1.0 | `quality_threshold` has no measurement procedure. |
| **D-019** `tenant_id` in V0.1 models | V0.1 | Cheap now, expensive to retrofit. |
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
