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
`08_mcp_contract.md`. Assigned to V1.2 by D-203 (D-184 had left it unassigned until a concrete requirement existed: the
Research agent returns `NO_RESULT` when no documents are supplied). V1.2's slice is one local read-only stdio server exposing
`search_documents`, reached through a `ToolPort` inside the Research agent behind a deterministic admission gate. Not implemented yet.

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

> **Resolved (D-178, 2026-09-22):** a Strategy is a **distinct object from Plan** — an execution shape
> (capability stages, a verification posture) that never carries a `StepId`, a dependency edge or an
> agent binding. A selected strategy may eventually (V0.8+, not built yet) expand into a concrete
> `Plan`, through the unmodified V0.2/V0.3 pipeline. **D-179** narrows the §17 factor list to what the
> rest of the system can already support: topology/parallelism (the stage shape itself), verification
> posture (two members — only one deterministic Verifier exists, D-133) and capability allocation.
> Agent selection, model selection, tool/retrieval selection and retry/replan posture are explicitly
> excluded — the first three by invariants 9/11, the last because D-012/D-125 are still Open and the
> compiler rejects `RETRY`/`REPLAN` outright. **D-021** (a `strategy_signature`/"Strategy Genome") stays
> Open and untouched — `StrategyId` (D-182) is plain identity, not a signature.
>
> **D-183:** candidates are filtered by `eidos.planning.feasibility.check_feasibility` (D-180) before
> selection; the existing, unmodified full Plan Validation pipeline runs once, only on the *selected*
> strategy's expanded `Plan` — never on every candidate. This is the reading §2/§83's own diagrams left
> ambiguous (`... Candidate Strategy Generation → Plan Validation → Strategy Selection ...`), now ruled
> on. **D-184:** MCP and RAG are deferred, unassigned extensions outside the V0.7–V1.0
> strategy-intelligence sequence — see §11's package table. **D-185:** candidate generation and
> feasibility filtering are not `MissionEvent`s in V0.7; `MissionEventType` gains no member for either.
> **V0.7 closed as scoped, 2026-09-22.**
>
> **V0.8 (Strategy Selection, 2026-09-22):** given a bounded, feasibility-filtered candidate set, choose
> one `Strategy` without the selector becoming an uncontrolled LLM planner — the same bounded-decision
> principle one step further. **D-186:** a `Selector` returns only a `StrategyId`, never a `Strategy`
> value or Plan DSL (`ModelPort`, D-135, is text-in/text-out only, so a model literally cannot return a
> `Strategy` — the mechanical reason this is enforceable in code). **D-187:** `Selector.select(candidates,
> task_genome) -> SelectorChoice`, paired with a deterministic orchestration boundary,
> `select_strategy`, that short-circuits zero/one-candidate cases and is the one place a selector's
> claim is checked against the real candidate set by `strategy_id` — never re-running
> `check_feasibility`, which already decided admissibility once. **D-188:** the reference
> `DeterministicSelector` orders candidates by a structural tuple (total capability occurrences, then
> stage count), never a scalar score. **D-189:** `SelectionResult` is a typed, replay-ready value only —
> no `SelectionId`, no `MissionEvent`, no Strategy Memory yet, mirroring D-185's own deferral. Step 2
> implemented exactly this. **D-190 to D-193** (V0.8 Step 5): a model-assisted `Selector`,
> `eidos.selectors.ModelAssistedSelector`, implementing the same `Selector` Protocol from a new sibling
> adapter package outside `eidos.planning` (which cannot import `eidos.agents`/`ModelPort`) — the model
> sees only the goal and each candidate's stages/verification/rationale (D-190), candidates are labelled
> `CANDIDATE_1..N` by tuple position, never the raw `StrategyId` (D-191), the model's answer is exactly
> one bracketed label parsed by the existing citation-token convention (D-192), and there is no automatic
> fallback to `DeterministicSelector` (D-193). **D-194, D-195** (V0.8 Step 8): a selected `Strategy` expands
> into a concrete `Plan` in a new sibling core layer, `eidos.expansion` — not inside `eidos.planning`, whose
> own existing guard already forbids it from ever importing `StepId` — depending only on `eidos.contracts`
> and `eidos.planning`. One capability occurrence becomes one `AgentStep`; a stage's steps depend on the
> whole of the preceding stage (D-179's own definition, applied literally); `FINAL` verification appends
> exactly one `VERIFY` step depending on the final stage's own step ids alone, never transitively on an
> earlier stage (D-195, matching the real V0.4 baseline precedent). The produced `Plan` still goes through
> the existing, unmodified V0.2 validation and V0.3 compiler — no shortcut, per D-178.
>
> **V0.9 Step 2** (D-196 confirms this is Telemetry's own numbering, not Strategy-to-Plan expansion): a new
> core layer, `eidos.telemetry`, projects already-recorded facts across many executions — `TelemetryRecord`,
> built by composing `execution_record` (D-159) rather than re-folding events. Depends only on
> `eidos.contracts`, `eidos.runtime` and `eidos.state`; no I/O, no clock, no randomness. No model identifier,
> no `strategy_id`, no quality/confidence/ranking field, no durable store, no benchmark logic — each flagged
> as a separate, future, narrow extension point, none built here.

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
| `eidos.capabilities` | The V0.4 capability set (five exact-string, lowercase names, D-132, D-144), the agent descriptor and a deterministic registry that resolves a capability to an agent; an unbound capability is a typed pre-run rejection (D-134) | V0.4 (V0.2 needed neither — D-102) | **yes** — vocabulary, descriptor, registry and `bind_plan` (Step 4); the tool descriptor and pinned tool registry (`tools.py`: `ToolDescriptor`, `ToolRegistry`, `ToolArgumentSpec`; V1.2 Step 2, D-203; no capability added) |
| `eidos.planning` | Candidate strategy generation, strategy selection | V0.7 (contracts, generator, feasibility) / V0.8 (selection) | **yes** — the `Strategy`/`StrategyStage`/`VerificationPosture` data contracts (V0.7 Step 2), the bounded `CandidateGenerator` boundary (V0.7 Step 3), the feasibility gate (V0.7 Step 4, closed as scoped), and the `Selector`/`DeterministicSelector`/`select_strategy` selection boundary (V0.8 Step 2, D-186–D-189); a model-assisted selector and Strategy-to-Plan expansion are each a separate package, not built here (see `eidos.selectors`/`eidos.expansion` below) |
| `eidos.validation` | The validation pipeline of §14 — depends only on `eidos.contracts` | V0.2 | **yes** |
| `eidos.compiler` | Validated `Plan` + accepted `PlanValidationReport` → an immutable, backend-neutral compiled form; deterministic; compiles only `agent` and `VERIFY` (D-112, D-114); imports no LangGraph | V0.3 | **yes** — the compiled form and `compile_plan` only (Step 2) |
| `eidos.runtime` | Backend-neutral execution: level-synchronous semantics, node and run results, synchronous execution ports, frozen `ExecutionContext` including the frozen `ReliabilityContract` (D-113, D-115, D-117, D-118, D-122, D-139); imports no LangGraph | V0.3 | **yes** — ports, results, `ExecutionContext` and the sequential reference executor (Step 3) |
| `eidos.backends.langgraph` | The LangGraph adapter — the **only** package that may import LangGraph (D-115); an optional dependency extra, also in `dev` (D-116) | V0.3 | **yes** — `LangGraphExecutor`, held to the reference executor (Step 4) |
| `eidos.agents` | Research, Analysis and Verification — exactly three logical agents (D-131); owns the synchronous `ModelPort` (D-135) and the in-memory artifact store (D-137); read-only, no tools (D-140); vendor-free; the one addition to what it may depend on is `eidos.policy`, for the tool-admission seam only (D-205 ruling 4) | V0.4 | **yes** — the model seam (Step 3), the artifact model and store (Step 5), and the Research, Analysis and deterministic Verification agents (Step 6); the tool seam (`tool.py`: `ToolPort`, `ToolRequest`, `ToolResult`, `ToolFailure`, `bound_result`; V1.2 Step 2, D-203, the same shape as the model seam), which no agent calls yet |
| `eidos.providers` | Model-provider adapters — the **only** place a vendor, model or SDK name may appear (D-135); standard-library HTTP, no new dependency (D-136) | V0.4 | **yes** — `OllamaModel`, tested against a local fake runtime and run against a real local model (Step 8): at the first output budget the baseline failed at its first step because the reasoning model spent its whole budget before answering (D-149); at 2,048 tokens the second step failed the same way; the committed opt-in test (4,096 tokens, 240 s), run once, finished with a verifier PASS (D-150, resolved; the truncated-answer question is D-151, Open) |
| `eidos.selectors` | `Selector` implementations that need a dependency the core `eidos.planning` layer cannot have — adapts `eidos.agents.ModelPort` to the existing `Selector` Protocol, exactly as `eidos.providers` adapts a vendor to `ModelPort` and `eidos.backends` adapts a workflow library to the runtime's executor port (D-190–D-193) | V0.8 Step 5 | **yes** — `ModelAssistedSelector` (`model_assisted.py`); no automatic fallback to `DeterministicSelector`, no Laya integration, no raw prompt/response recording |
| `eidos.expansion` | Expands a selected `Strategy` into a concrete `Plan` — a new core layer, sibling to `eidos.planning`, which cannot hold this itself (its own existing guard forbids importing `StepId`, D-179); depends only on `eidos.contracts` and `eidos.planning` (D-194, D-195) | V0.8 Step 8 | **yes** — `expand_strategy`/`PlanIdSource` (`expand.py`); no feasibility re-check, no V0.2 validation duplication; stamps caller-supplied replan lineage (`version`/`parent_plan_id`/`replan_reason`, V1.1 Step 1, D-199) and, for `version > 1`, gives every work step a fresh `v{version}_` namespaced id (D-200, D-147); it never decides when to replan |
| `eidos.replanning` (one module) | Within-mission replanning orchestration: generates the bounded candidate set once, runs one attempt at a time on one continuous `EventLog`, appends an `ExecutionExperience` after every attempt, and — for a replan-eligible outcome within the mission's configured `max_replans` — records `REPLAN_TRIGGERED`, expands plan vN+1 from the next untried candidate (same `Selector`, attempted `StrategyId`s excluded) and runs it; a narrow sibling to `eidos.baseline`, composing existing layers only; imported by no core layer (D-199) | V1.1 Step 4 | **yes** — `run_with_replanning`/`ReplanRun`/`ReplanRejection` (`replanning.py`); a mission with no selectable first strategy returns a typed `ReplanRejection`, never raises (D-201); no new selector, no new failure cause, no automatic retry beside the replan, no A2A/MCP/RAG. Limits (D-202): per-plan limits are enforced for each attempt and `max_replans` bounds the attempts; cumulative mission-wide budget enforcement across attempts is deferred (D-043, D-127, D-156); exhausting `max_replans` ends the mission on the final attempted plan's own outcome, which is not necessarily `PAUSED` |
| `eidos.baseline` (one module) | The single-pass baseline runner and the work dispatcher: validate, compile, bind, execute on a backend handed to it, report; stops at the first gate that refuses; backend-neutral, no CLI, no API (D-131) | V0.4 | **yes** — `run_baseline`, `WorkDispatcher`, `BaselineReport` (Step 7) |
| `eidos.state` | The typed `EventRecord` payloads, the pure reducer, the append-only event log with a JSONL round trip, checkpoint, replay and the derived read-only `ExecutionRecord` (D-152 to D-159); imports the core layers only — never agents, providers, capabilities or baseline; no clock, no I/O | V0.5 | **yes** — the payloads and `EventRecord` (Steps 2a and 2b), the pure reducer (Step 3), the event log with its intake, checkpoint, replay and strict JSONL form (Step 4), `ExecutionRecord` (Step 6) and the refusal of a repeated node event at the intake and in replay (D-162 item 1); additive `ToolCallFacts` on `NODE_SETTLED`, the reducer's `tool_calls_used` fold and `StepRecord.tool_calls` (V1.2 Step 3, D-203; no new event type) |
| `eidos.recording` | Recording adapters: an injected clock and id source, and wrappers over the existing injection points (agents, verifier, model port) that propose events to the log; holds no `MissionState`; the runtime emits nothing (D-158); there is no admission-guard wrapper, a halt is read from the run's result (D-158 item 1, amended by D-163). Also the one home for a real `StrategyId`/`PlanId` source (V0.9 Step 3) — `eidos.planning`/`eidos.expansion` are deterministic core layers and may not draw one themselves | V0.5 | **yes** — the clock and id ports (`UuidEventIds`, plus `UuidStrategyIds`/`UuidPlanIds`, V0.9 Step 3), the recorder, the wrappers and `record_baseline` (Step 5b), with the observer hook on `run_baseline` (Step 5a); plus `record_attempt` (one recorded attempt against a caller-held log, never recording the terminal event) and `terminal_payload_for` (the pure classification of an attempt's terminal payload), shared by `record_baseline` and `eidos.replanning` (V1.1 Step 4, D-199); the tracker's tool collection and the recorder's `note_tool_calls` hand-off (V1.2 Step 3, D-203; no tool is invoked here) |
| `eidos.a2a` | The A2A boundary: a hand-rolled client over `httpx` speaking A2A v1.0 directly (D-171, no `a2a-sdk`), the non-blocking `WorkAgent` implementation for the Research Agent (D-175), the webhook receiver, and the recording adapter that appends to a caller-held, still-open `EventLog` (D-167). Holds no `MissionState`, decides nothing about when to resume a mission (D-170) | V0.6 | **yes** — Steps 1–6 of 9: the `AgentTask`/state contract changes, the runtime extension for a non-blocking work outcome, the event/reducer integration, `wire.py`/`convert.py`/`transport.py`/`client.py`/`agent.py`/`webhook.py`/`deadline.py`, and the recording adapter (D-165 to D-177); `tests/protocol/` scenarios and the remaining steps (7–9 of 9) are not built |
| `eidos.policy` | Deterministic governance. At V1.2 only the pure tool-admission function (D-203); the general policy engine, autonomy levels 2 to 4 and human approval are deferred and unassigned | V1.2, minimal slice only (D-203; Step 2 of its order); V0.2 has only a `NOT_APPLICABLE` stage in `eidos.validation` — D-110 | **yes, minimal** — `admit_tool_call`, `args_digest` and the typed `ToolAdmission`/`ToolDenial`/`ToolInvocationRecord` (`tool_admission.py`, V1.2 Step 2); pure, imports `eidos.contracts` and `eidos.capabilities` only; an unset `max_tool_calls` is denied `BUDGET_UNRESOLVED`, never resolved, and before any duplicate lookup (D-205 ruling 1 and item 2); the general policy engine is not built |
| `eidos.telemetry` | A pure, deterministic multi-execution projection over already-recorded facts — one more projection beside `eidos.state.execution_record` (D-159), never a second authoritative store; depends only on `eidos.contracts`, `eidos.runtime` and `eidos.state` | V0.9 | **yes** — `TelemetryRecord`/`project` (`project.py`, Step 2); no model identifier, no `strategy_id`, no quality/confidence field, no durable store, no benchmark logic |
| `eidos.memory` | Strategy and execution memory | V1.0 | **yes** — `ExecutionExperience`/`evaluate_experience` (`experience.py`, Step 1), task/strategy relevance filtering (`relevance.py`, Step 2), the `ExperienceStore` Protocol and `JsonlExperienceStore` (`store.py`, Step 3); D-198. V1.0's adaptive-memory work is complete, including the end-to-end adaptive-loop integration proof (Step 6) and Benchmark 2 (Step 7) |
| `eidos.evaluation` | Evaluation harness, experiments | Unassigned: the handoff's V1.1 (Adaptive Learning) items are deferred, D-202 | no |
| `eidos.mcp` | MCP tool boundary: a minimal hand-rolled stdlib stdio client implementing the agents' `ToolPort`; transport only, imported by no core layer (D-203) | V1.2 (D-203; Step 5 of its order) | no |
| `eidos.rag` | Agentic RAG, retrieval, reranking, evidence judging | Deferred, unassigned (D-184) | no |
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

### The V0.4 boundary — model, agent and capability seams (built; the committed real-model baseline, run once, finished with a verifier PASS — D-149, D-150)

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

### The V0.5 boundary — events, state and history (built)

Recorded in D-152 to D-162 and built in V0.5 (Steps 2 to 7); `progress.md` tracks the steps and the close-out review.

```text
V0.4 baseline (unchanged) --existing injection points--> eidos.recording   (injected clock and id source)
                                                          | event proposals; no access to MissionState
                                                          v
                          intake (eidos.state): assigns the sequence, ignores a repeated event_id
                                                          v
                          append-only event log (authoritative; strict JSONL round trip)
                                                          v
      reducer (eidos.state: pure, no clock, no I/O; the ONLY writer of MissionState) --> MissionState (a view)
                                                          v   read-only, recomputable
                          checkpoint (state + last sequence) | replay (log) | ExecutionRecord (log)
```

- **Authority (invariants 1 and 2).** Producers propose, the intake orders, the reducer alone writes state, and every projection is read-only. Recording adapters hold no `MissionState`.
- **The V0.1 contracts change in one place:** `MissionEventType` gains `NODE_STARTED`, `NODE_SETTLED` and `MISSION_PAUSED` (sixteen types, D-154). `MissionEvent` stays an envelope; a typed payload travels
  beside it in an `EventRecord` (D-153).
- **Layering.** `eidos.state` imports the core layers and never agents, providers, capabilities or baseline; `eidos.recording` imports `eidos.state` and what it wraps (the agents' and the runtime's ports, the
  baseline runner and the capability registry) and never a provider or a backend. The runtime, executors, compiler, agents and verifier are unchanged, and the runtime emits no event (D-123, D-158). The one
  change to V0.4 code is the optional, observational `observer` on `run_baseline`, which records the plan and each gate with real times and can neither change the pass nor stop it (D-160 item 8).
- **Facts only.** Counters are folded from recorded facts and never enforced; a value is provider-reported or recorder-observed, or absent. `MeasuredFacts` is not modified, so no stop reason is recorded
  (D-151, Open).
- **Idempotency of node events.** The reducer holds no per-node state (D-113) and none is added, so the **intake** refuses a repeated `NODE_STARTED` or `NODE_SETTLED` for the same step of a plan, and a fold from scratch
  refuses a log that has one; the log keeps the set of steps seen, `MissionState` does not (D-162 item 1). One question stays open: whether a start after
  the same step's settlement is refused (D-164). The admission guard is not wrapped: a halt is read from the run's result (D-158 item 1, amended by D-163).
- **Not in V0.5:** a durable store (D-017), A2A, MCP, RAG, the telemetry platform, strategy memory, a selector, a planner, adaptive learning and cross-mission aggregation (D-161).

---

## Open questions

**D-020** (Strategy vs Plan — one object or two) is resolved — see `decisions.md` D-178, §7 above.

| Id | Question |
|---|---|
| D-007 | Capability vocabulary and matching semantics — not a V0.2 blocker (D-102) |
| D-009 | Where execution bounds originate |
| D-024 | Whether the FAISS/Qdrant comparison is an out-of-runtime experiment |
| D-129 | How a work node receives its predecessors' outputs — answered for V0.4 by D-137 (in-memory store); stays Open |
| D-151 | Non-empty model responses that stopped at the output limit — deferred; not handled in V0.4 |


## Out of scope for this document

Contract field definitions (`04`–`09`), reliability mechanics (`10_reliability.md`), evaluation
design (`11_evaluation.md`), the normative invariant list (`12_architecture_invariants.md`).
