# 05 — Plan DSL

**Status:** DERIVED — current · target milestones **V0.1** (contracts) and **V0.2** (validation)
**Derived from:** handoff §11, §12, §13, §14, §15, §16, §32
**Authority:** This document is derived from `EIDOS_CLAUDE_CODE_HANDOFF.md` and subordinate to it.
If this document and the handoff conflict, stop and report the conflict to the human owner.

---

## 1. Why the DSL exists

Letting an LLM generate arbitrary runtime graph topology is explicitly forbidden (§12):

```text
BAD:  LLM -> arbitrary graph code -> LangGraph
```

because it risks un-debuggable workflows, accidental cycles, runaway branching, uncontrolled
recursion, inconsistent state, excessive cost and untestable behaviour.

Instead there is a **bounded Mission Plan DSL**. The planner outputs a structured plan specification
rather than Python or LangGraph code (§13).

```text
LLM -> Plan DSL -> Validator -> Compiler -> LangGraph runtime
```

**The LLM composes approved primitives; a deterministic compiler verifies the plan.** This is
invariant 3, and it is not negotiable.

## 2. Canonical representation — ID-addressed DAG

**Decision D-004, taken by the human owner.**

The canonical internal representation of a plan is an **ID-addressed DAG**:

- every step carries an **explicit id**
- every dependency is an **explicit edge**

**Validation and compilation operate only on that form.**

A nested or tree-shaped representation may be supported later as **syntactic sugar**, but it must be
normalized into the DAG *before* validation runs. Tree-shaped input never reaches the validator.

### Why this was decided

§13's example is nested:

```json
{
  "type": "parallel",
  "steps": [
    { "type": "agent", "capability": "research" },
    { "type": "agent", "capability": "security_analysis" }
  ]
}
```

A nested tree cannot structurally contain a cycle, and has no step identity to express a dependency
against. Yet §14 mandates **dependency validation** and **cycle detection**. Under the tree reading
both checks are vacuous. The DAG reading makes them meaningful. The two readings imply entirely
different validators, so the representation had to be settled before any contract work began.

### What D-004 does not settle

The concrete edge encoding — `depends_on` listed on each step, versus a separate edge list — is
**not** decided. Raise it before implementing. Neither is the step-id namespace (unique within a
plan version, or globally).

## 3. Allowed primitives

Initially (§13), and only these:

```text
SEQUENTIAL
PARALLEL
ROUTE
VERIFY
RETRY
REPLAN
HUMAN_APPROVAL
TERMINATE
```

Adding a primitive is an architectural change requiring human approval and a `decisions.md` entry.

V0.3 maps `SEQUENTIAL`, `PARALLEL`, `ROUTE`, `VERIFY`, `RETRY` and `REPLAN` into runtime nodes
(§50). `HUMAN_APPROVAL` and `TERMINATE` are not listed in the V0.3 mapping.

> **Open:** `ROUTE`, `RETRY`, `REPLAN` and `TERMINATE` are all conditional, and routing must be
> deterministic, but **no predicate or expression language is specified** for any of them. Without
> one, either the condition is opaque — breaking determinism and validation — or an expression
> language gets invented. See `decisions.md` **D-012**. This blocks the compiler.

## 4. Validation pipeline

Validation happens **before** execution. No plan executes unvalidated (invariant 5). The order is
fixed by §14:

```text
Planner
 -> Plan JSON
 -> Schema validation
 -> Dependency validation
 -> Cycle detection
 -> Capability validation
 -> Policy validation
 -> Resource validation
 -> Graph complexity limits
 -> Compile
```

A plan that fails any stage is **rejected**. It is never repaired silently, never truncated to fit,
and never partially executed.

### Stage notes

| Stage | Depends on |
|---|---|
| Schema validation | The Plan/PlanStep contract (V0.1) |
| Dependency validation | Explicit edges (D-004) |
| Cycle detection | Explicit edges (D-004) |
| Capability validation | The capability vocabulary — **blocked, D-007** |
| Policy validation | The policy engine and autonomy model (`10_reliability.md`) |
| Resource validation | Bound values and their source — **blocked, D-009** |
| Graph complexity limits | Bound values — **blocked, D-009** |

## 5. Bounds

Plans must have limits (§14):

```text
max_nodes
max_depth
max_parallel_branches
max_retries
max_replans
max_agent_calls
max_tool_calls
max_execution_time
```

**A plan exceeding those limits must be rejected.**

§32 repeats the execution-side hard limits: max retries, max replans, max execution time, max agent
calls, max tool calls. No infinite loops.

> **Open:** the handoff names every dimension and gives **no values**, and does not say whether
> bounds come from static policy configuration, the per-mission ReliabilityContract, the Task
> Genome, or a combination. See `decisions.md` **D-009**. Resource validation and complexity-limit
> validation cannot be implemented until this is answered.

## 6. Immutable versioned plans

Never mutate a live graph in place (§15, invariant 6).

```text
Plan v1 -> execution -> failure -> replanner -> Plan v2 -> execution
```

Mission history must show the lineage and the reason:

```text
Plan v1 -> failed
Reason  -> insufficient evidence

Plan v2 -> completed
```

This is what makes debugging and replay possible.

## 7. Candidate plans

For every mission EIDOS may generate a **small number** of candidate strategies — start with 2–3
(§16). **Do not generate an unlimited number.** Bounded alternatives are sufficient for meaningful
experiments.

§16 illustrates three shapes: fully sequential; three parallel branches converging on analysis then
verification; and an ordered variant that front-loads architecture before targeted research.

> **Open:** whether a candidate "Strategy" is exactly a Plan, or a Plan plus binding decisions
> (model selection, retrieval strategy, context allocation) that the §13 primitives cannot express.
> See `decisions.md` **D-020**.

## 8. Implementation constraints

- `Plan` and `PlanStep` live in `eidos.contracts` (V0.1), Pydantic v2, carrying explicit step ids
  and explicit edges.
- The validator lives in `eidos.validation` (V0.2) and the compiler in `eidos.compiler` (V0.3).
  Both are **deterministic**: no I/O, no network, no LLM calls, no hidden global state.
- Neither may contain a model, vendor or SDK reference (invariant 9).
- Per handoff §58, the Plan DSL validator is built **test-first**, with tests for valid plans,
  dependency errors, cycles, maximum depth, maximum nodes, maximum parallel branches, unknown
  capabilities, invalid operations, policy violations and resource violations.

---

## Open questions

| Id | Question | Blocks |
|---|---|---|
| D-012 | Predicate language for ROUTE / RETRY / REPLAN / TERMINATE | V0.2, V0.3 |
| D-009 | Bound values and where bounds originate | V0.2 |
| D-007 | Capability vocabulary and matching semantics | V0.2 |
| D-020 | Strategy vs Plan — one contract or two | V0.2, V1.0 |
| — | Edge encoding (`depends_on` per step vs separate edge list) and step-id namespace — explicitly left open by D-004 | V0.1 |
| — | Whether `HUMAN_APPROVAL` and `TERMINATE` are compiled at V0.3; §50 omits them from the V0.3 mapping | V0.3 |

## Out of scope for this document

Runtime execution semantics (`03_architecture.md`, and the V0.3 work), MissionState
(`06_mission_state.md`), policy and autonomy enforcement (`10_reliability.md`).
