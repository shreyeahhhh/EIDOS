# 03 — Architecture

**Status:** DERIVED — current
**Derived from:** handoff §7, §8, §9, §10, §11, §12, §16, §17, §27, §33, §34, §35, §36, §50, §75, §77, §78, §83
**Authority:** This document is derived from `EIDOS_CLAUDE_CODE_HANDOFF.md` and subordinate to it.
If this document and the handoff conflict, stop and report the conflict to the human owner.

> Handoff §58/§60 refer to this document as `docs/02_architecture.md`. §81 numbers it `03`. That
> inconsistency is inside the handoff and is reported, not resolved — see `decisions.md` D-001.

---

## 1. Component hierarchy

Work core-outward, never bottom-up (§75).

```text
LEVEL 1 — Core thesis     Adaptive execution strategy selection
LEVEL 2 — Runtime         Task Genome, Plan DSL, Compiler, LangGraph, MissionState
LEVEL 3 — Interoperability A2A, MCP
LEVEL 4 — Intelligence    Agentic RAG, Strategy memory, Pilot execution, Adaptive routing
LEVEL 5 — Reliability     Verification, Policies, Autonomy, Recovery
LEVEL 6 — Optimization    Caching, Historical performance, Exploration, Strategy learning
LEVEL 7 — Product         Frontend, API, Deployment
```

## 2. The planning pipeline

This is the architecture's spine and the source of invariants 3, 4 and 5.

```text
LLM
 -> Plan DSL            (bounded, declarative, never code)
 -> Validator           (deterministic)
 -> Compiler            (deterministic)
 -> LangGraph runtime
```

**LangGraph is the execution runtime for validated plans, not the strategy generator** (§11). It
manages execution state, sequencing, parallel branches, routing, retries, checkpoints, controlled
replanning and termination.

**The LLM never generates executable LangGraph code** (§11, §12). Allowing an LLM to emit arbitrary
runtime graph topology risks un-debuggable workflows, accidental cycles, runaway branching,
uncontrolled recursion, inconsistent state, excessive cost and untestable behaviour. The bounded
Plan DSL exists precisely to prevent this.

## 3. State architecture

**MissionState is the only authoritative global state** (§9). This is a hard invariant.

```text
A2A events/results
        -> EIDOS event handling
        -> MissionState reducer
        -> LangGraph checkpoint/state
```

Agents must **never** directly mutate MissionState. Remote agents keep their own internal state;
EIDOS holds only the state it needs to reason about the mission.

The failure mode being designed against (§10) is three competing global state systems:

```text
LangGraph state  <->  A2A state  <->  Agent internal state
```

Instead:

```text
Global MissionState  +  Remote AgentTask records  +  Event-based synchronization
```

Details in `06_mission_state.md`.

## 4. Capability architecture

Agents are not hard-coded into workflows. EIDOS maintains an **Agent Capability Registry** (§7).

An agent exposes: `agent_id`, `version`, `capabilities`, `supported_inputs`, `supported_outputs`,
`required_permissions`, `supported_tools`, `historical_latency`, `historical_success`,
`historical_verification_rate`, `availability`.

Providers may include a local open-source model, an OpenAI model, an Anthropic model, a Google
model, a specialized model, an external remote agent, or a human reviewer. **The architecture must
not assume any single model remains dominant** (§7).

Plans request **capabilities, not named agents** (invariant 11). Capability-to-agent binding happens
at selection/execution time.

> **Open:** the capability vocabulary in §6 and the one in §7 do not match, and the matching
> semantics (exact / hierarchical / similarity) are unspecified. See `decisions.md` D-007. **This no
> longer blocks V0.2** — `decisions.md` **D-102** scopes V0.2 capability validation to the mission's
> own `TaskGenome.required_capabilities`, needing no cross-mission vocabulary. D-007 now blocks only
> V0.4, when a real agent registry needs a real vocabulary to bind against.
>
> **V0.4 (D-132, D-134, D-144):** the registry binds against a **V0.4-only, exact-string set of five capabilities** —
> `architecture`, `security`, `cost`, `research`, `verification`. **D-007 stays Open;** nothing global is decided. The Research
> Agent serves `research`; the Analysis Agent serves `architecture`, `security` and `cost`; the Verification Agent is reached
> through the `Verifier` port by `VERIFY` node kind, not by capability.

## 5. Model independence

> **Never make the underlying model the product.** The model is a worker. (§36)

```text
                      EIDOS
                        |
               Model/Agent Interface
                        |
        +---------------+---------------+
   Local Model      External Model   Other Model
        +---------------+---------------+
                        |
                  Capabilities
```

A model may be replaced without redesigning EIDOS. Different capabilities may use different models
depending on the task and policy. This is invariant 9: no model, vendor or SDK name appears in
contracts, planning, validation, compiler, runtime or state.

> **Resolved (D-135, D-018):** `eidos.agents` owns a synchronous `ModelPort` and its typed request, response and failure types;
> every provider adapter lives in `eidos.providers`, the only place a vendor, model or SDK name may appear. The model, the
> generation parameters and the timeout are **explicit inputs, never defaulted.** (V0.3's D-122 defined only the
> *execution-side* ports, owned by `eidos.runtime`; that is unchanged.)

## 6. Interoperability boundaries

### A2A — the agent boundary

A2A (Agent2Agent) is the communication layer between independent agent systems. It is used at
**meaningful independent-agent boundaries only**. Do not force every internal function call through
A2A to claim A2A support (§8). Tightly coupled internal nodes run locally; independently deployable
agent capabilities use A2A.

Remote tasks have their own lifecycle and identifiers and are represented **separately** from global
mission state, as `AgentTask` records. Detail in `07_a2a_contract.md`. Deferred to V0.6.

### MCP — the tool boundary

```text
Agent -> MCP -> Permission / Policy -> Tool or resource
```

Agents do not directly access environment capabilities (§27). The initial tool set is deliberately
small — `search_documents`, `retrieve_evidence`. **Do not create 20 MCP tools in V1.** Detail in
`08_mcp_contract.md`. Deferred to V0.7.

## 7. Strategy architecture

For each mission EIDOS generates a **small number** of candidate strategies — start with 2–3, never
an unlimited number (§16). Bounded alternatives are enough for meaningful experiments.

Strategy factors (§17): agent selection, agent ordering, parallelization, model selection, tool
selection, retrieval strategy, verification strategy, retry strategy, replanning strategy, context
allocation.

Strategies are weighed against quality, latency, resource usage, reliability, risk, tool calls,
agent calls, evidence requirements and autonomy constraints.

The cold-start problem is handled progressively (§18): rules and heuristics → small pilot → measure
actual signals → continue/abandon/replan → store real execution data → use historical evidence for
future decisions. A model-asserted quality score is **not** ground truth.

> **Open:** whether a "Strategy" is the same object as a "Plan" or a Plan plus binding decisions the
> DSL does not encode. See `decisions.md` D-020. Several §17 factors (model selection, retrieval
> strategy, context allocation) are not expressible in the §13 plan primitives.

## 8. The feedback loop

AgentOps is not a dashboard. The architecture is (§34):

```text
Execution telemetry -> Evaluation -> Performance memory -> Future strategy selection
```

closing the loop:

```text
Plan -> Execute -> Observe -> Evaluate -> Remember -> Plan better
```

This loop is central to EIDOS.

## 9. Context optimization

Prompt caching is not the product feature; a broader **Context Optimization** layer is (§35).
Potential levels: prompt/context cache, retrieval cache, tool-result cache, task-state cache.
Stable system rules are reusable; repeated retrieval results and unchanged tool results are cache
candidates; the current user request is dynamic. Measure cache hit rate, tokens saved, latency
saved. The caching provider is not locked; in-process or local Redis during development.

## 10. Target local deployment

Everything runs locally (§77):

```text
                     EIDOS
                       |
                   FastAPI
                       |
                  LangGraph
                       |
       +---------------+---------------+
   Research         Analysis       Verification
     Agent            Agent            Agent
       |               |               |
       +------------ A2A --------------+
                       |
                      MCP
                       |
             +---------+---------+
          Qdrant      SQLite    Files
             |
        Agentic RAG
             |
         Local LLM
```

Future cloud architecture is sketched in §78: web frontend → EIDOS API → control/planner → local
worker and A2A workers → agents → MCP → Qdrant/PostgreSQL/tools. **Do not prematurely build it.**

## 11. Package boundaries

Per CLAUDE.md §3, a package is created only when the milestone that fills it begins. This section is
the architectural map; `progress.md` tracks which of these exist.

| Package | Responsibility | Milestone | Exists |
|---|---|---|---|
| `eidos.contracts` | Typed contracts: TaskGenome, ReliabilityContract, MissionState, MissionEvent, Plan, PlanStep, AgentTask | V0.1 | **yes** |
| `eidos.capabilities` | The V0.4 capability set (five exact-string, lowercase names, D-132, D-144), the agent descriptor and a deterministic registry that resolves a capability to an agent; an unbound capability is a typed pre-run rejection (D-134) | V0.4 (V0.2 needed neither — D-102) | **yes** — vocabulary, descriptor, registry and `bind_plan` (Step 4) |
| `eidos.planning` | Candidate strategy generation, strategy selection | V0.2+ | no |
| `eidos.validation` | The validation pipeline of §14 — depends only on `eidos.contracts` | V0.2 | **yes** |
| `eidos.compiler` | Validated `Plan` + accepted `PlanValidationReport` → an immutable, backend-neutral compiled form; deterministic; compiles only `agent` and `VERIFY` (D-112, D-114); imports no LangGraph | V0.3 | **yes** — the compiled form and `compile_plan` only (Step 2) |
| `eidos.runtime` | Backend-neutral execution: level-synchronous semantics, node and run results, synchronous execution ports, frozen `ExecutionContext` including the frozen `ReliabilityContract` (D-113, D-115, D-117, D-118, D-122, D-139); imports no LangGraph | V0.3 | **yes** — ports, results, `ExecutionContext` and the sequential reference executor (Step 3) |
| `eidos.backends.langgraph` | The LangGraph adapter — the **only** package that may import LangGraph (D-115); an optional dependency extra, also in `dev` (D-116) | V0.3 | **yes** — `LangGraphExecutor`, held to the reference executor (Step 4) |
| `eidos.agents` | Research, Analysis and Verification — exactly three logical agents (D-131); owns the synchronous `ModelPort` (D-135) and the in-memory artifact store (D-137); read-only, no tools (D-140); vendor-free | V0.4 | **yes** — the model seam (Step 3), the artifact model and store (Step 5), and the Research, Analysis and deterministic Verification agents (Step 6) |
| `eidos.providers` | Model-provider adapters — the **only** place a vendor, model or SDK name may appear (D-135); standard-library HTTP, no new dependency (D-136) | V0.4 | **yes** — `OllamaModel`, tested against a local fake runtime and run once against a real local model (Step 8): the baseline mission failed at its first step because the reasoning model spent its whole output budget before answering (D-149 diagnosis; what to do next is D-150, Open) |
| `eidos.baseline` (one module) | The single-pass baseline runner and the work dispatcher: validate, compile, bind, execute on a backend handed to it, report; stops at the first gate that refuses; backend-neutral, no CLI, no API (D-131) | V0.4 | **yes** — `run_baseline`, `WorkDispatcher`, `BaselineReport` (Step 7) |
| `eidos.state` | Reducer, checkpoints, replay | V0.5 | no |
| `eidos.policy` | Governance, autonomy levels, budgets | V1.2 (V0.2 has only a `NOT_APPLICABLE` stage in `eidos.validation` — D-110) | no |
| `eidos.telemetry` | Structured events, metrics | V0.9 | no |
| `eidos.memory` | Strategy and execution memory | V1.0 | no |
| `eidos.evaluation` | Evaluation harness, experiments | V1.1 | no |
| `eidos.a2a` | A2A boundary | V0.6 | no |
| `eidos.mcp` | MCP tool boundary | V0.7 | no |
| `eidos.rag` | Agentic RAG, retrieval, reranking, evidence judging | V0.8 | no |
| `eidos.api` | FastAPI surface | later | no |

### Contract representation rules

These apply to every contract in `eidos.contracts` and are cross-cutting rather than per-model.

**Identifiers — `decisions.md` D-053.** Opaque **UUID-backed** values, represented through **distinct
per-kind types** (`TenantId`, `MissionId`, `ExecutionId`, `PlanId`, `EventId`, `AgentId`, and the
other kinds the contracts define).

UUID-backed because `event_id` is the idempotency key under **D-011** and must be collision-free
across processes once V0.6 introduces a second identifier producer; §53's `mission_1842` implies a
counter, which is a coordination point EIDOS has no mechanism for. Distinct types because nine
identifier kinds flowing through seven contracts is where a plan id gets passed where a mission id
belongs.

**Readability is a display-layer concern**, not a representation one — replay traces (§73), the
Execution Replay and Evidence Explorer views (§41) and telemetry (§33) render short forms rather than
the contracts carrying readable values.

**Timestamps — `decisions.md` D-054.** **All contract timestamps are explicit required inputs. No
contract model may silently obtain the current wall-clock time during construction.**

The deciding argument is **replay**: invariant 15 requires a completed mission to be reconstructible
from recorded events, and a clock-defaulting timestamp would stamp reconstruction time onto
historical state, making the replay unfaithful in fields nobody intended to change. There is also a
back-door argument — the reducer produces new `MissionState` values, so a clock-defaulting model
would reintroduce into the reducer the very clock dependence the dependency rules below forbid it.

This is **D-011's principle applied consistently**: that decision already requires `MissionEvent` to
carry `occurred_at` (producer clock) and `recorded_at` (EIDOS ingestion), with the reducer reading
neither from the clock.

**Identifier exemptions from D-053's UUID rule.** Five identifier kinds are **string-backed** rather
than UUID-backed, each for a stated reason:

| Type | Why exempt | Decision |
|---|---|---|
| `StepId` | authored by the planner inside the Plan DSL; unique only within one plan version | D-092 |
| `CapabilityId` | §13's own example writes `"capability": "research"`; emitted in the DSL | D-080 |
| `ActionId` | §6 lists actions as plain names | D-080 |
| `a2a_task_id`, `a2a_context_id` | assigned by the remote A2A system; EIDOS only mirrors them | D-095 |
| `ArtifactRef` | produced by remote agents, as D-095 | D-098 |

**Units and time.** Durations are **integer milliseconds** and token budgets are **integer token
counts**; conversion to minutes or seconds happens at the API or UI boundary, never in a contract
(**D-078**). Timestamps are **timezone-aware UTC**, and naive values are **rejected** (**D-083**).

**Tenant.** `tenant_id` is always present on root models; in single-tenant V0.1 the value is supplied by
the single-tenant context rather than by each caller, and it carries **no security meaning** (**D-079**).

### Dependency rules

- Core layers — `contracts`, `validation`, `compiler`, `runtime`, `state` — must not import agent,
  provider, protocol or storage implementations.
- Deterministic components — validator, compiler, reducer, policy — perform no I/O, no network
  calls, no LLM calls, hold no hidden global state and do not depend on wall-clock time in logic.
- `contracts` depends on nothing inside `eidos`.
- **Only `eidos.backends.langgraph` may import LangGraph** (D-115). The compiler, the runtime and every
  other core layer must not; LangGraph is an execution backend, not the architectural authority.

## 12. Execution semantics — V0.3

Implemented in `eidos.runtime` by the **sequential reference executor** (D-128) — the semantic oracle a backend
is held to. It is not the production concurrency backend. Full detail: `decisions.md` D-117 to D-124.

**Level-synchronous (D-117).** Each node's `level` comes from the compiled plan and is never recomputed.
Levels run in order; within a level nodes run in ascending plan position; every node of a level is resolved
before the next level begins. A node is *ready* when all its predecessors are settled, in any status. It
executes only if **every** predecessor `SUCCEEDED`; otherwise it is `SKIPPED` without a dispatch. Independent
branches continue after a failure, and nothing is retried: a node is dispatched at most once per run.

**Statuses and outcomes (D-118).** Seven node statuses — `SUCCEEDED`, `FAILED`, `NO_RESULT`,
`VERIFICATION_FAILED`, `VERIFICATION_INCONCLUSIVE`, `SKIPPED`, `NOT_REACHED` — and three run outcomes:
`FINISHED`, `FAILED`, `HALTED`. `HALTED` takes precedence. **`FINISHED` is not verified success**: a
`RunResult` reports `verified` only for a finished run in which a `VERIFY` node succeeded.

**Ports (D-122).** Three synchronous, narrow ports owned by the runtime: `WorkExecutor.execute(context, node)`,
`Verifier.verify(context, node, predecessors)` and `AdmissionGuard.admit(request)`. The guard is **required**;
there is no default and no production guard. A work node carries only a requested capability, never an agent.
A fault in a port — an exception, or a return that is not the port's typed result — becomes `FAILED`, never a
pass and never an inconclusive verdict. A guard that faults **fails closed**: the run halts.

**Halting.** The guard is asked once for each node that would be dispatched, told only its level, its rank among
that level's dispatched nodes and how many nodes earlier levels dispatched. A `HALT` leaves that node
`NOT_REACHED`; the rest of the level is still resolved, then every later level is `NOT_REACHED` and the run is
`HALTED`.

**Resume (D-120).** A later run may be given prior `SUCCEEDED` outcomes; those nodes are carried over and never
redispatched. Anything else in the prior — another status, an unknown step, a contradiction with the plan's
edges, or an identity that is not this execution's — is a typed `RunRejection`, never silently adapted. A
context or prior that does not match the compiled plan is likewise rejected before anything runs.

**Not here.** LangGraph; MissionState writes (`ExecutionContext` is a frozen snapshot, and MissionState is only
read to build it); events (invariant 15 is **not exercised**, D-123); automatic retry or in-run replan (D-119);
runtime budget, time or token accounting; real agents. Open: how a work node receives its predecessors' outputs
(D-129).

### The LangGraph backend — V0.3 Step 4

`eidos.backends.langgraph.LangGraphExecutor` has the same signature and contract as the reference executor
(D-128) and is tested to return an **equal `RunResult` or `RunRejection`, byte for byte**, for the same
compiled plan, context, prior outcomes and deterministic ports. LangGraph supplies mechanics; EIDOS supplies
every semantic.

- One LangGraph node per compiled node, named by plan position (LangGraph rejects names such as `__start__`
  and anything containing `:` or `|`, which a step id could be). Roots hang off `START`; a node with several
  predecessors has one list-form join edge. The compiled plan's edges are the graph's edges.
- LangGraph's super-steps *are* levels. Nodes of a level run **concurrently on worker threads**, so ports must
  be thread-safe; the result never depends on which finishes first.
- **The graph state is `outcomes` and nothing else (D-113).** A level's nodes read a start-of-step snapshot, and
  each writes only its own key. The context, plan and ports are closed over by the wrappers, so MissionState is
  never in the state. There is no checkpointer, `thread_id`, interrupt, LangGraph retry, streaming or store
  (D-127). A port that fails is recorded as `FAILED` by the wrapper and never reaches LangGraph.
- Dispatch order, the halt and the outcome are derived from the final outcomes and the plan, never from
  completion order. An empty plan is answered without building a graph, because LangGraph refuses one.
- The recursion limit is passed explicitly — the plan's depth plus a measured overhead — because LangGraph's
  own default comes from an environment variable. **Tracing is forced off:** an ambient `LANGSMITH_TRACING`
  would otherwise export every node's inputs and outputs to a third party. That stays off, with no opt-in
  (**D-130**, Accepted).
- A fault in LangGraph or in the adapter raises `BackendError`. Nothing a run can legitimately produce is ever
  raised.

LangGraph is an optional extra (D-116), heavy for what it does — a closure of 38 distributions, including an HTTP client,
`websockets` and LangSmith — and the core and its tests run without it.

### The V0.4 boundary — model, agent and capability seams (built; the first real-model run failed at its first step — D-149, D-150)

Recorded in D-131 to D-148 and implemented in V0.4 Steps 2 to 8; `progress.md` tracks the steps and the close-out review.

```text
eidos.baseline (runner) ---> validation, compiler, runtime, capabilities, agents   (handed a backend; imports none)
agents                ---> runtime ports (it implements them), contracts, ModelPort (it owns it)
capabilities          ---> contracts, compiler          (binding reads a CompiledPlan)
providers             ---> agents' ModelPort         (the only vendor-aware layer)
core: contracts, validation, compiler, runtime     (import none of the above; the one change is the frozen contract on ExecutionContext, D-139)
```

Four seams:

- **Execution seam (exists, D-122).** `WorkExecutor.execute(context, node)` and `Verifier.verify(context, node, predecessors)`.
  V0.4 supplies implementations; neither signature changes (D-137). A `VERIFY` node is bound to the `Verifier` port by **node
  kind**, not by capability (D-133); a work node is bound through the registry.
- **Capability seam (D-132, D-134, D-144).** Five exact-string, lowercase names for V0.4 only; an agent descriptor is `agent_id`, version and
  capabilities. Binding happens when the run is constructed, and an unbound capability is a typed rejection before anything runs.
  V0.2 validation does not learn which agents exist.
- **Model seam (D-135).** Text in, text out, plus facts the provider measured. Only agents call it; only providers implement it.
  Explicit model, generation parameters and timeout; failures are typed.
- **Artifact seam (D-137).** An in-memory store under `(execution_id, step_id)`, one primary artifact per work step; `ArtifactRef`
  stays opaque. Agents read predecessors' outputs and the supplied documents from the store. An artifact has four fields — `ref`,
  `content_type`, `content`, `source_refs` — and supplied documents are addressed by `ArtifactRef`, namespaced by execution (D-145). Identity is `(execution_id, step_id)` and `artifact:<step_id>`; within one
  execution a newly executed work step needs a fresh step id across plan versions, and an agent refuses a step whose artifact already exists **before any model call** (D-147).

**Scope (D-131).** A fixed, hand-authored plan — Research, Analysis, `VERIFY` — over a supplied `TaskGenome`, driven once.
No planner, no candidate strategies, no system-driven replan, no events or history, no A2A, MCP or RAG. Agents are read-only with no
tools (D-140). Verification is a deterministic rule set with no model verdict (D-138); the frozen `ReliabilityContract` is in
`ExecutionContext` (D-139). The `AdmissionGuard` is caller-supplied, with no default.

---

## Open questions

| Id | Question |
|---|---|
| D-007 | Capability vocabulary and matching semantics — not a V0.2 blocker (D-102) |
| D-020 | Strategy vs Plan — one object or two |
| D-009 | Where execution bounds originate |
| D-024 | Whether the FAISS/Qdrant comparison is an out-of-runtime experiment |
| D-129 | How a work node receives its predecessors' outputs — answered for V0.4 by D-137 (in-memory store); stays Open |


## Out of scope for this document

Contract field definitions (`04`–`09`), reliability mechanics (`10_reliability.md`), evaluation
design (`11_evaluation.md`), the normative invariant list (`12_architecture_invariants.md`).
