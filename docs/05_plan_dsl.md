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

### Step categories — `decisions.md` D-049

**Resolved, decided by the human owner.** §13's eight-item list contains only control-flow
constructs, while §13's **own example** carries work in a step of `"type": "agent"` holding a
`"capability"` — which is not in the list. §13's wording is the tell: the LLM "**composes** these
approved primitives", and what is composed is never named. §50 confirms it from the other direction:
V0.3 maps six primitives into runtime nodes, then says "Use mock agents initially", so agents are
invoked by something outside the mapping list.

EIDOS therefore has **two step categories**:

| Category | Carries `capability` | Purpose |
|---|---|---|
| **Work step** — `kind = "agent"` (D-101) | **required** | Performs work through a requested capability (invariant 11) |
| **Control-flow step** | **absent** | Shapes execution |

A control step carrying a capability, and a work step without one, are both **unrepresentable**
rather than merely invalid. This matters because `capability` is not optional metadata — it is what
invariant 11 and §14's capability-validation stage act on.

### Ordering is expressed by edges — `decisions.md` D-050

**Resolved, decided by the human owner.** `SEQUENTIAL` and `PARALLEL` are **not canonical
`PlanStepKind` values**. **Ordering and parallelism are expressed through dependency edges in the
ID-addressed DAG**: `A → B` is sequential, and two steps with no path between them are parallel.

They **may** exist later as optional authoring-surface syntax, but such syntax **must normalize to
the same canonical DAG** and **must not introduce separate execution semantics**.

This follows from D-004 rather than overriding §13. D-004 already states that nested or tree-shaped
surface syntax is optional sugar normalized before validation — and §13's example *is* that tree
syntax, in which a `parallel` node with a `steps` array is a grouping construct that becomes
meaningless once steps have IDs and edges. Keeping both as step kinds would put two representations
of one fact in the model plus a precedence rule, the pattern D-013 refused for constraints and §9/§10
refuse for state.

Nothing is lost: §16's Plan A and Plan B differ exactly in parallelism, and the edges fully
distinguish them — a chain versus a fan-in.

**Neither D-004 nor D-047 has been modified.** Both are Accepted as written; D-049 and D-050 are
recorded as refinements of them.

### The canonical kind set

```text
agent               <- the work step: capability-bearing (D-101)
ROUTE
VERIFY              <- pending D-055
RETRY
REPLAN
HUMAN_APPROVAL      <- pending D-055
TERMINATE
```

> ⚠️ **D-055 is Open.** `VERIFY` and `HUMAN_APPROVAL` may themselves be work steps rather than
> control-flow steps: §7's registry has a Verification Agent and §6 lists `verification` among
> required capabilities, while §7 lists **"Human reviewer"** among the providers a capability may be
> bound to. If both are work steps, the control set reduces to `ROUTE`, `RETRY`, `REPLAN`,
> `TERMINATE`. Both remain control-flow kinds meanwhile — the conservative position — and **no
> reclassification may be made silently while writing the contract.**

V0.3 maps `SEQUENTIAL`, `PARALLEL`, `ROUTE`, `VERIFY`, `RETRY` and `REPLAN` into runtime nodes
(§50). `HUMAN_APPROVAL` and `TERMINATE` are not listed in the V0.3 mapping.

> **V0.3 scope — `decisions.md` D-112, decided by the human owner.** The V0.3 compiler compiles **only
> `agent` and `VERIFY`** (`VERIFY` to a `VerifyNode` — D-124, a V0.3 implementation decision that does
> not answer D-055). It **rejects at compile time** `ROUTE`, `RETRY`, `REPLAN`, `TERMINATE` and
> `HUMAN_APPROVAL`, with a typed compile failure and no placeholder node, so these kinds never silently
> become executable. This narrows §50's mapping list. **D-012 remains Open.** V0.2 still accepts plans
> containing those kinds (D-047); rejecting them is the compiler's job. Compiler input is a `Plan` plus
> an accepted `PlanValidationReport` (D-114).

> **Open:** `ROUTE`, `RETRY`, `REPLAN` and `TERMINATE` are all conditional, and routing must be
> deterministic, but **no predicate or expression language is specified** for any of them. Without
> one, either the condition is opaque — breaking determinism and validation — or an expression
> language gets invented. See `decisions.md` **D-012**. This blocks compiling these four kinds; V0.3
> rejects them instead (D-112).

**V0.1 scope — `decisions.md` D-047, decided by the human owner.** V0.1 defines the **eight step
kinds**, **explicit step IDs**, **capability**, **dependency edges** and **DAG structure**. It
defines **no predicate or condition language**, and carries **no conditional payload at all** — not
even an opaque placeholder, which would be an untyped value crossing a module boundary (CLAUDE.md
§8) and would invite dependencies on a shape nobody has chosen.

Conditional payloads and predicate semantics arrive **at V0.3, with D-012**, as an **additive**
contract change rather than a reinterpretation of an existing field — not at V0.2, since none of
§14's eight V0.2 pipeline stages reads or checks a condition (D-012 blocks the compiler, not the
validator). A V0.1 plan containing a conditional kind is structurally valid but semantically
incomplete; nothing in V0.1 or V0.2 executes plans, so this is inert — but such a plan **must not
silently become executable at V0.3** without D-012.

### Field presence — `decisions.md` D-077

**`Plan`:** `tenant_id`, `plan_id`, `mission_id`, `version`, `steps` are **required**;
`parent_plan_id` and `replan_reason` are **optional** — §15 is explicit that `Plan v1` precedes any
replan, so a v1 plan has no parent and no reason **by construction**.

**`PlanStep`:** `step_id`, `kind` and `depends_on` are **required**. **`depends_on` may be an empty
collection** — that is how a DAG root is expressed. `capability` is governed by **D-049**: required
on work steps, absent from control steps.

### Representation — `decisions.md` D-088, D-092, D-093

- **`Plan.mission_id`** stays **required** (**D-088**) — a deliberate asymmetry with D-068, on the
  ground that a plan is a mission-specific versioned artifact that should self-identify outside
  MissionState. Consequence: a plan whose `mission_id` differs from its containing state's is
  representable and must be checked.
- **`step_id`** is a distinct opaque **`StepId`** string, **unique within a plan version**, and **exempt
  from D-053's UUID rule** (**D-092**). LLM-authored ids such as `research_1` are valid. This settles
  the namespace question D-004 left open.
- **`Plan.steps`** is an **immutable ordered collection** of `PlanStep`, **not** a map keyed by
  `step_id`; uniqueness is **validated separately** (**D-093**). Empty is legal in V0.1 (**D-087**).
- **`Plan.version`** is a **positive integer starting at 1**, increasing monotonically **within a
  mission** (**D-082**).
- **`PlanStep.capability`** on work steps is a **`CapabilityId`** — string-backed, exempt from D-053,
  since §13's own example writes `"capability": "research"` (**D-080**).

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

| Stage | Depends on | V0.2 |
|---|---|---|
| Schema validation | The Plan/PlanStep contract (V0.1) | implemented |
| Dependency validation | Explicit edges (D-004) | implemented |
| Cycle detection | Explicit edges (D-004) | implemented |
| Capability validation | `TaskGenome.required_capabilities` — **resolved, D-102** (mission-scoped; no vocabulary or registry needed at V0.2) | implemented |
| Policy validation | The policy engine and autonomy model (`10_reliability.md`) — unresolved (D-060/D-061/D-074) | **`NOT_APPLICABLE`** (D-110); nothing is checked and nothing is invented |
| Resource validation | Bound values supplied by the caller (D-009, D-103) | implemented |
| Graph complexity limits | Bound values supplied by the caller (D-009, D-103) | implemented |

### V0.2 implementation — `eidos.validation`

Two entry points, both returning a `PlanValidationReport` and **never raising for an invalid plan**:

```text
validate_plan_json(text, state, limits)   # untrusted ingress: a JSON document (D-107)
validate_plan(plan, state, limits)        # an already-constructed Plan
```

`limits` is a **required** argument (`SystemLimits`, D-103): every field is required, none has a
default, and no limits object is defined in the package. Values are always supplied by the caller;
the actual numbers remain D-046 (Open).

**The report.** Exactly one `StageResult` per stage, always in the fixed order above (COMPILE is V0.3
and not a validation stage). Each has one of four statuses:

| Status | Meaning |
|---|---|
| `PASSED` | the check ran and found nothing |
| `FAILED` | the check ran and found at least one `Violation` |
| `SKIPPED` | the check could not run, and the `detail` says why — **never** counted as a pass |
| `NOT_APPLICABLE` | no check is defined (POLICY, D-110) — **not** a pass either |

`report.accepted` is true only if every stage is `PASSED` or `NOT_APPLICABLE`; `report.fully_evaluated`
is true if none is `SKIPPED`. A report with `NOT_APPLICABLE` policy is accepted **without** the policy
stage having approved anything; the stage's `detail` says so.

**What each stage checks.**

| Stage | Rule |
|---|---|
| Schema | JSON syntax; the `Plan` contract's strict field validation; and that `plan.mission_id` / `plan.tenant_id` match the `MissionState` (mismatch is reported here — D-111 item 1) |
| Dependency | `step_id` unique within the plan; every `depends_on` resolves. Re-verified on constructed plans (D-111 item 3) |
| Cycle | Every dependency cycle, including a step that depends on itself — the plan V0.1 accepts and V0.2 rejects. Each cycle is reported (strongly connected component), members in plan order |
| Capability | Every `agent` step's `capability` is **exactly** (string equality — no case-folding, no trimming) one of `TaskGenome.required_capabilities` (D-102). The converse is not required. Control steps are ignored |
| Policy | `NOT_APPLICABLE` (D-110) |
| Resource | Each of the six contract budgets, if set, must not exceed the system ceiling — **rejected, never clamped** (D-009). The number of `agent` steps the plan **declares** must not exceed the effective `max_agent_calls`, `min(system ceiling, contract value)`, or the ceiling alone if the contract omits it (D-065). Retries, replans, tool calls, time and tokens are **not** inferred from plan structure (D-105); "declared" is not "actual" (D-043, V0.3) |
| Complexity | `max_nodes`; `max_depth` = longest dependency path **counted in nodes** (D-104: a single step has depth 1); `max_parallel_branches` = **exact maximum antichain width** (D-050) |

**Antichain width is exact, not a level count.** The widest level of a DAG is only a lower bound: for
steps `s→q`, `s→t`, `t→r` and an isolated `p`, the widest level holds 2 steps but `{p, q, t}` is an
antichain of 3. Width is computed by Dilworth's theorem — steps minus a maximum matching on the
transitive closure — with an iterative Hopcroft–Karp. Its cost grows with the number of comparable
pairs, so a plan over `max_nodes` is rejected **before** width is computed.

**Stage dependencies, reported rather than hidden.** Text that does not become a `Plan`: every stage
after the failing one is `SKIPPED`. A plan of another mission or tenant: CAPABILITY and RESOURCE are
`SKIPPED` rather than run against the wrong mission's genome and contract. Invalid step ids or
dependencies: CYCLE and COMPLEXITY are `SKIPPED`, the graph being undefined. A cyclic plan within
`max_nodes`: COMPLEXITY is `SKIPPED`. An empty plan is legal and passes (D-106).

**Determinism.** No I/O, network, LLM, clock, randomness or hidden state; the graph algorithms are
iterative (a 20,000-step chain does not reach the recursion limit); every ordering derives from
`plan.steps` order, never from set or hash iteration. Reports are asserted byte-identical across
process hash seeds. `tests/unit/validation/test_validation_guards.py` reads the package source and
fails on forbidden imports, vendor names, the handoff's illustrative `600000` / `10,000`, numeric
limit literals and self-recursion.

**Not in V0.2.** The compiler (V0.3); capability-to-agent availability (V0.4); any policy rule; any
runtime counting of retries, replans, tool calls, time or tokens; plan lineage, `plan_id` uniqueness
and version monotonicity across a mission's plans (D-082 — a V0.5 reducer concern); the
`risk_level` versus `max_risk_level` comparison (D-030 / D-057, Open).

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

**D-050 sharpens two of these.** Now that ordering is carried solely by edges, the shape limits have
unambiguous graph definitions: `max_depth` is the **longest path** through the DAG, and
`max_parallel_branches` is the **maximum antichain width**. **D-046** must set its values against
those definitions rather than against a tree's nesting depth.

§32 repeats the execution-side hard limits: max retries, max replans, max execution time, max agent
calls, max tool calls. No infinite loops.

**Source of authority — resolved (`decisions.md` D-009).** Bounds split by category:

- **`max_nodes`, `max_depth`, `max_parallel_branches`** are **system-level safety limits**. They
  protect the runtime from an LLM's output (§12, §14) and are not user-settable.
- **`max_retries`, `max_replans`, `max_agent_calls`, `max_tool_calls`, `max_execution_time`,
  `max_tokens`** are **mission execution budgets**, carried by the ReliabilityContract.

A mission may **tighten** a system limit but never exceed the system ceiling, and a contract value
above the ceiling is **rejected with an explicit validation reason** — never silently clamped
(invariant 5). Full rationale in `decisions.md` D-009 and `docs/10_reliability.md` §6.

**Mechanism vs. values — `decisions.md` D-103.** V0.2's resource-validation and graph-complexity
mechanisms are fully buildable and testable now: production `SystemLimits` carries **no built-in
numeric defaults**, every field is required at construction, and tests use explicitly labelled
fixture values. The handoff's two illustrative numbers (`latency_budget_ms: 600000`,
`Maximum tokens: 10,000`) are **not** copied into shipped defaults.

> **Still open, but not blocking the mechanism:** **D-046** (the actual values themselves — governed
> entirely separately from whether the mechanism can be built, per D-103), **D-044** (`max_tokens` in
> the §14/§32 lists — not reinvestigated this round; still recorded as open). **D-042** and **D-045**
> are **Accepted**, not open, and are removed from this list — corrected 2026-09-18, they had been
> listed here as blockers after already being decided. **D-043** (declared vs. actual limit counting)
> is **not a V0.2 blocker** — corrected 2026-09-18; investigation found it only becomes live once the
> V0.3 runtime exists to reconcile against the V0.2 declared-count check. See D-043's own entry.

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
| D-055 | Are `VERIFY` and `HUMAN_APPROVAL` work steps rather than control-flow steps? | not V0.1; rework risk if answered after `PlanStep` exists. **V0.3 (D-124):** `VERIFY` compiles as a control step, `HUMAN_APPROVAL` is unsupported; the question stays Open |
| D-012 | Predicate language for ROUTE / RETRY / REPLAN / TERMINATE | Blocks compiling these kinds; V0.3 rejects them (D-112, D-127); not a V0.2 validator requirement |
| D-046 | Numerical bound values (the mechanism is unblocked; D-103) | V0.2 values, V0.9+ tuning |
| D-043 | Declared plan limits vs actual execution counters | **V0.3** (corrected 2026-09-18; not a V0.2 blocker) |
| D-007 | Capability vocabulary and matching semantics | **V0.4** (corrected 2026-09-18; not a V0.2 blocker — see D-102) |
| D-020 | Strategy vs Plan — one contract or two | V0.2, V1.0 |
| D-111 | Eight V0.2 implementation details the approved design left unspecified, implemented conservatively — awaiting the owner's confirmation | none blocking |
| — | Edge encoding (`depends_on` per step vs separate edge list) and step-id namespace — explicitly left open by D-004 | V0.1 |
| D-125 | How plan-level `RETRY` relates to a future runtime retry policy | none at V0.3 (`RETRY` is rejected) |

## Out of scope for this document

Runtime execution semantics (`03_architecture.md`, and the V0.3 work), MissionState
(`06_mission_state.md`), policy and autonomy enforcement (`10_reliability.md`).
