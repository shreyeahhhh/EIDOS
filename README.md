# EIDOS — Execution Intelligence & Dynamic Orchestration System

> EIDOS is a model-independent adaptive AI runtime that dynamically plans, orchestrates, evaluates,
> and optimizes multi-agent workflows using A2A, MCP, LangGraph, and Agentic RAG.

*(Description taken verbatim from the project handoff, §1.)*

## Status

**V0.8 — Strategy Selection: architecture accepted, Steps 2, 3, 5, 6, 7 and 8 implemented (the Selector contracts and orchestration boundary; a boundary-hardening audit; the model-assisted Selector adapter, `eidos.selectors`; a deterministic selection-integration suite; the Strategy-to-Plan expansion design and its implementation, `eidos.expansion`), none pushed. V0.7 — Strategy & Candidate Generation: closed as scoped, none pushed. V0.6 — A2A: Steps 1–6 of 9 implemented and pushed. V0.5 — the event log and the state reducer: complete as scoped. V0.4 — real local agents: complete as scoped. *(V0.9 remains Telemetry, unbuilt — decisions.md D-196.)*

This repository contains the project rules, the architecture knowledge base, the decision record,
the V0.1 typed contracts (`eidos.contracts`), the V0.2 plan validator (`eidos.validation`), the V0.3
compiler and runtime (`eidos.compiler`, `eidos.runtime` and the LangGraph backend
`eidos.backends.langgraph`), and the V0.4 capability registry, three read-only agents (Research,
Analysis and a deterministic Verification rule set), a single-pass baseline runner and one
local-model adapter. The baseline works end to end with a scripted model. With a real local model (`qwen3:4b`) the committed opt-in test, run once, finished — Research, Analysis and
verification — with a verifier PASS at 4,096 output tokens and a 240 s timeout; smaller budgets had failed, as recorded in [progress.md](progress.md) (D-149, D-150). The PASS covers three
deterministic rules and measures no quality, and the committed test asserts structure only. One question is deliberately left open (D-151). There is no
planner, no A2A, no MCP, no RAG, no persistence, no API and no frontend.

V0.5 adds the typed event records, a pure state reducer, an in-memory event log with a JSONL round trip, checkpoint and replay (`eidos.state`), recording adapters around the baseline
(`eidos.recording`) and a derived, read-only `ExecutionRecord`. A recorded baseline replays to the same `MissionState` and the same record with no agent run, and the intake refuses a repeated node event for a step (D-162). One question stays open (D-164), and a
real-model recording has not been run.

V0.6 moves the Research Agent behind one A2A boundary (D-175). The protocol/contract design is decided (`decisions.md` D-165 to D-177), researched directly against the published A2A Protocol
Specification rather than assumed: a non-blocking `SUBMITTED`/`AWAITING` execution shape, `AgentTask`'s real lifecycle, one continuous event log across the pause, a hand-rolled `httpx` client (no
`a2a-sdk`), and no fifth `MissionStatus`. Steps 1–5 of 9 are implemented — the `AgentTask`/state contract changes, the `eidos.runtime` non-blocking extension, the `eidos.state`
event/reducer integration, and `eidos.a2a` itself (the client, the Research Agent's remote `WorkAgent`, the webhook-to-event converter) — none pushed. Re-verifying the wire format against the
live spec while building the client corrected two Step 1 assumptions (`TaskState` casing, the JSON-RPC method names). Step 5 also found a real gap — nothing un-paused a mission once its one
exempted completion event was accepted, so a resumed mission could not record further events on the same log — reported, not silently patched, and resolved by **D-177**: an explicit, never-
automatic `EventLog.accept_resumed`/`reducer.reduce_resumed` pair that reads the log's own history rather than adding a `MissionState` field. Step 6 built the one hop D-177 made possible —
`eidos.recording.a2a.record_a2a_notification`, the recording adapter that bridges one externally received webhook delivery into a caller-owned `EventLog`, composing the unchanged webhook converter with the
unchanged `EventLog.accept` and nothing else. All six steps are committed and pushed to `origin/master`. See [progress.md](progress.md), "V0.6 One A2A Boundary".

V0.7 introduces the representation of an execution strategy and the bounded candidate-generation boundary — the
model chooses from a runtime-bounded set of feasible strategies rather than inventing an unrestricted workflow.
Step 1 (architecture only) resolved the long-open **D-020** ("Strategy" and "Plan" used interchangeably) as
**D-178**: a `Strategy` is a distinct object from `Plan`, an execution shape that never carries a `StepId`, a
dependency edge or an agent binding. **D-179** fixes the three dimensions it may express — topology/parallelism,
a two-member verification posture, and capability allocation — with agent/model/tool selection and retry/replan
posture explicitly excluded. **D-180**–**D-182** fix that feasibility filtering will reuse the existing
`SystemLimits`/`ReliabilityContract` (no new ceiling), that `max_candidates` is an explicit parameter (CLAUDE.md's
own "two or three" stays the bound), and that `StrategyId` is plain identity (no version, no signature — **D-021**
stays Open). Step 2 built the data contracts — `eidos.planning` (`Strategy`, `StrategyStage`,
`VerificationPosture`). Step 3 built the bounded candidate-generation boundary itself: `CandidateGenerator` (a
`Protocol`, pure function of `TaskGenome.required_capabilities` only), the deterministic reference
`RuleBasedCandidateGenerator` (linear/parallel/staged shapes, gated so a guaranteed duplicate is never even
constructed; verification posture derived, not permuted as an independent axis), and `generate_candidate_strategies`
(structural dedup and identity injection via a new `StrategyIdSource` — no uuid-drawing implementation lives in
`eidos.planning` itself). Step 4 built the feasibility gate: `check_feasibility` runs three narrower,
strategy-level analogues of V0.2's CAPABILITY/COMPLEXITY/RESOURCE stages, reusing the existing `SystemLimits`/
`ReliabilityContract` — no new numeric limit anywhere, and the actual Plan validator (`eidos.validation.stages`/
`.pipeline`) is never imported or called. `generate_candidate_strategies` now stamps identity, filters through
this gate, and caps only the feasible pool. Step 5 resolved the three questions Step 1 left open, by owner ruling,
with no code change: **D-183** (candidates are feasibility-filtered before selection; full Plan validation runs
once, only on the selected strategy's expanded `Plan`), **D-184** (MCP and RAG are deferred, unassigned extensions
outside the V0.7–V1.0 sequence — not renumbered into it), **D-185** (candidate generation and feasibility are not
`MissionEvent`s in V0.7). **V0.7 is closed as scoped** (the owner's own confirmation, 2026-09-22). See
[progress.md](progress.md), "V0.7 Strategy & Candidate Generation".

V0.8 is the next link the fundamental loop names: feasible Strategy candidates → **[V0.8 Strategy Selection]** →
selected Strategy → Strategy-to-Plan expansion (future) → the existing Plan Validation → compilation/execution.
The central problem: choose one strategy from a bounded, already-feasible candidate set without turning the
selector into an uncontrolled LLM planner. Step 1 (architecture only) found that `ModelPort` (D-135) is text-in,
text-out only — a model can never return a `Strategy` directly, only name one — the mechanical reason a selector
structurally cannot invent a strategy. Recorded **D-186** (a selector returns only a `StrategyId`, never a
`Strategy` value or Plan DSL), **D-187** (the `Selector` contract — `select(candidates, task_genome) ->
SelectorChoice` — paired with a deterministic orchestration boundary, `select_strategy`, that performs the
zero/one-candidate short-circuit and the actual membership check no untrusted selector can bypass), **D-188**
(the reference `DeterministicSelector`'s tie-break is a structural tuple, never a scalar quality score), and
**D-189** (`SelectionResult` is a typed, replay-ready value only — no `SelectionId`, no `MissionEvent`, no
Strategy Memory yet). Step 2 implemented exactly that: `eidos.planning.selector` and `.selection`, still a core
layer, still no `eidos.agents`/`ModelPort` dependency. Step 3 audited the boundary against eleven stated
semantics and found it already sufficient (no contract change). Step 4 (design only) proposed, and Step 5
implemented, a model-assisted `Selector`: **D-190** (the model sees only the goal and each candidate's
stages/verification/rationale), **D-191** (candidates are labelled `CANDIDATE_1..N` by tuple position, never the
raw `StrategyId`), **D-192** (the model's answer is exactly one bracketed label, parsed by the same closed-token
convention agents already use to cite sources), **D-193** (no automatic fallback to `DeterministicSelector`).
`ModelAssistedSelector` lives in a new sibling adapter package, `eidos.selectors`, outside the core `eidos.planning`
layer — the same shape `eidos.providers` and `eidos.backends` already use for a dependency the core cannot have.
Step 6 proved the boundary end to end: `CandidateGenerationResult.candidates` was already exactly the
`tuple[Strategy, ...]` `select_strategy` takes, so no new wiring was built — only `tests/integration/planning/`,
33 tests exercising both selectors over the same deterministically-generated, feasibility-filtered candidate sets
(bounded candidates, rejected strategies never reaching the selector, a factual — never ranked — comparison
between the two selectors, and JSON round-trip/replay safety with no model call). See
[progress.md](progress.md), "V0.8 Strategy Selection".

Steps 7 and 8 continue the same milestone: selected Strategy → **[Strategy-to-Plan expansion]** → concrete `Plan`
→ the existing, unmodified V0.2/V0.3 pipeline. `eidos.expansion.expand_strategy` — a new sibling core layer to
`eidos.planning` (whose own existing guard forbids it from ever importing `StepId`, D-179) — maps one capability
occurrence to one `AgentStep`, never deduplicated; a stage's steps depend on the whole of the preceding stage,
D-179's own definition applied literally; `FINAL` verification appends exactly one `VERIFY` step depending on the
final stage's own step ids alone, matching the real V0.4 baseline precedent (D-194, D-195). `step_id` is a pure,
deterministic derivation; `plan_id` is drawn only from an injected `PlanIdSource`, mirroring `StrategyIdSource`
one layer down. The produced `Plan` is an ordinary value — no shortcut around the existing, unmodified V0.2
validation or V0.3 compiler pipeline exists (D-178). **Note (D-196):** this work was first logged as "V0.9 Step
1/2"; V0.9 itself remains **Telemetry**, unchanged (the older, far more established meaning), and a future
controlled benchmark stays unassigned a number, exactly like MCP/RAG under D-184 — this work is filed as V0.8
Steps 7–8 instead, matching D-183's own pre-existing "Strategy-to-Plan expansion (V0.8+, not built)" phrasing.
See [progress.md](progress.md), "V0.8 Strategy Selection".

Current status and the milestone ladder: [progress.md](progress.md).
Decisions and unresolved questions: [decisions.md](decisions.md).
Rules every contributor (human or agent) follows: [CLAUDE.md](CLAUDE.md).

No quality metric appears anywhere in this repository. One real-model run is recorded in
[progress.md](progress.md) as a record of what happened, not as a benchmark. Per the project rules,
every metric published must come from an actual recorded run.

## What EIDOS is

EIDOS operates at the level of **execution strategy**. Its question is not "can an AI perform this
task?" but:

> Given a human objective and a set of available AI agents, models, tools, knowledge sources and
> constraints, how should the system decide the most appropriate way to execute that objective?

Its governing philosophy: **the LLM proposes; the runtime validates; the agents execute; the
evaluator measures; the system learns.**

```text
Human Objective -> Task Genome -> Capability Discovery -> Candidate Strategy Generation
  -> Plan Validation -> Strategy Selection -> Execution -> Verification -> Evaluation
  -> Execution Memory -> better future strategy selection
```

## What EIDOS is not

Not a chatbot, not a coding assistant, not a website builder, not a fixed multi-agent workflow, not
an agent marketplace, not an MCP or A2A gateway, and not a simple RAG application. It is also
explicitly not an "AI software development factory" — EIDOS may *execute* a software workflow, but
the runtime itself stays domain-agnostic.

## Documentation

The canonical specification is [`EIDOS_CLAUDE_CODE_HANDOFF.md`](EIDOS_CLAUDE_CODE_HANDOFF.md).
Everything in `docs/` is derived from it and subordinate to it.

| Document | Scope |
|---|---|
| [docs/01_problem.md](docs/01_problem.md) | The problem EIDOS addresses and why it exists |
| [docs/02_prd.md](docs/02_prd.md) | Product requirements, personas, user experience |
| [docs/03_architecture.md](docs/03_architecture.md) | System architecture and component boundaries |
| [docs/04_task_genome.md](docs/04_task_genome.md) | The Task Genome contract |
| [docs/05_plan_dsl.md](docs/05_plan_dsl.md) | The bounded Plan DSL and its validation pipeline |
| [docs/06_mission_state.md](docs/06_mission_state.md) | MissionState ownership, events, reducer |
| [docs/07_a2a_contract.md](docs/07_a2a_contract.md) | A2A boundary contract (V0.6, Steps 1–6 implemented and pushed) |
| [docs/08_mcp_contract.md](docs/08_mcp_contract.md) | MCP tool boundary contract (deferred, unassigned — D-184) |
| [docs/09_rag_architecture.md](docs/09_rag_architecture.md) | Agentic RAG architecture (deferred, unassigned — D-184) |
| [docs/10_reliability.md](docs/10_reliability.md) | Reliability contract, verification, recovery, governance |
| [docs/11_evaluation.md](docs/11_evaluation.md) | Telemetry, evaluation framework, experiments |
| [docs/12_architecture_invariants.md](docs/12_architecture_invariants.md) | The hard invariants, normatively stated |

## Intended local stack

The prototype is designed to run entirely locally at zero software cost (compute is the laptop's).
The full intended stack is recorded in the handoff §51 and §76; it is **not** installed yet.
Only the dependencies required by the current milestone are declared in `pyproject.toml`.

Currently declared: `pydantic>=2` (contracts); the optional extra `langgraph` (the LangGraph backend, V0.3 — D-116);
`dev` (`pytest`, plus the `langgraph` extra). The core never imports LangGraph, and its tests run without it.

## Development

```bash
python -m pytest
```

Runs every test root. The current test state and counts are recorded in [progress.md](progress.md).
The two real-model tests are excluded from that run and never skipped; they are selected explicitly
with `-m real_model` and need a local model runtime the owner has installed
(see `tests/integration/providers/test_ollama_real.py`).
