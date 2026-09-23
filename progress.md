# progress.md — EIDOS Implementation Tracking

Status only. Rules live in [CLAUDE.md](CLAUDE.md). Decisions and open questions live in
[decisions.md](decisions.md). The canonical specification is `EIDOS_CLAUDE_CODE_HANDOFF.md`.

---

## Current state

**Milestone: V1.0 Execution Experience / Strategy Memory — architecture accepted (D-198, 2026-09-23); Steps 1 and 2 of 7 implemented: `eidos.memory.experience` (`ExecutionExperience`, `evaluate_experience`), a pure, factual, immutable record of one completed mission's measured facts, built directly from `Strategy`/`TaskGenome`/`TelemetryRecord`; `eidos.memory.relevance` (`TaskRelevance`, `task_relevance`, `relevant_experience`, `experience_for`), pure deterministic task/strategy relevance filtering — exact capability/risk/autonomy matching for task relevance, exact structural shape matching for strategy relevance, no embeddings, no scalar similarity score, no staleness — no quality/confidence score, no strategy signature, no persistent `strategy_id` on any existing contract; none pushed. On top of the first controlled EIDOS benchmark ("Benchmark 1" — deliberately unassigned a milestone number, D-196/D-197), implemented (2026-09-23): `tests/support/eidos_benchmark_harness.py` (the reusable harness) and `tests/scenarios/test_benchmark_execution_control.py` (13 tests, five task classes, conditions A/B/C/D1/D2), on top of V0.9 Telemetry — Steps 2, 3 and 4 implemented (`eidos.telemetry`, a pure multi-execution projection over already-recorded facts; Step 3 connects the full live chain from `TaskGenome` through candidate generation, selection, Strategy-to-Plan expansion, validation, execution/recording and telemetry projection, for one real mission; Step 4 closes two evidence gaps an inspection found, `execution_time_used_ms` and `plan_rejected_at`), on top of V0.8 Strategy Selection (architecture accepted, D-186 to D-193, Steps 2, 3, 5, 6, 7 and 8 of its sequence implemented — Step 3 a boundary-hardening audit, no contract change; Step 4 a design-only step accepted as D-190 to D-193; Step 5 the model-assisted `Selector` adapter, `eidos.selectors`; Step 6 a deterministic selection-integration suite proving the boundary end to end; Step 7 the Strategy-to-Plan expansion design, D-194/D-195; Step 8 its implementation, `eidos.expansion`; none pushed), V0.7 Strategy & Candidate Generation (closed as scoped, D-178 to D-185, none pushed), V0.6 One A2A Boundary (protocol/contract design accepted, Steps 1–6 of 9 implemented, D-177; none pushed), V0.5 Mission State + Event Reducer (complete as scoped, D-152 to D-164, pushed), V0.4 Real Local Agents (complete as scoped, D-131 to D-151), V0.1 Core Contracts, V0.2 Plan Validation and V0.3 LangGraph Runtime (complete as scoped, D-112 to D-130). *(This is the correct, D-196-resolved meaning of "V0.9" — Telemetry, not Strategy-to-Plan expansion, which is filed as V0.8 Steps 7–8 above.)*

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

**V0.6 (One A2A Boundary): protocol and contract design accepted (2026-09-22; D-165 to D-177); Steps 1–6 of 9 implemented, none pushed.** The owner directed research against the published A2A Protocol Specification and the actual `a2a-sdk` dependency graph before any transport choice, then ruled on all twelve items, resolving **D-023, D-035, D-036, D-037** and amending **D-160** ruling 4 narrowly (**D-176**): an admission-guard `paused` mission is unchanged from V0.5; a `paused` mission caused by an A2A-awaiting pause is the one exception, resumable on the same log; no fifth `MissionStatus`. Step 2 extended the `AgentTask` contract (`AgentTaskStatus`, `plan_id`/`step_id`/`started_at`) and added `eidos.state.agent_tasks` (the D-166 mapping, the D-176 fold primitive). Step 3 extended `eidos.runtime` with the non-blocking `SUBMITTED`/`AWAITING` shape. Step 4 wired `A2A_TASK_STARTED`/`A2A_TASK_COMPLETED` into the reducer, the log's intake and replay, with the D-176 terminal exception. Step 5 built `eidos.a2a` — the hand-rolled JSON-RPC client (re-verified against the live spec, correcting two Step 1 assumptions), the Research Agent's remote `WorkAgent`, and the webhook-to-`EventProposal` converter — and found a real gap: nothing in the (then-)Accepted design un-paused a mission once its one exempted `A2A_TASK_COMPLETED` was accepted, so D-167's own described resume flow could not record further events on the same log (reported, not silently patched). **The owner ruled D-177**, resolving it: an explicit, narrow, never-automatic `EventLog.accept_resumed`/`reducer.reduce_resumed` pair, reading the log's own history rather than adding a `MissionState` field — `reduce()`, `accept()`, `MissionState`, `MissionStatus` and D-176 are all unchanged. **Step 6 built the recording adapter** (`eidos.recording.a2a.record_a2a_notification`) that bridges one externally received webhook delivery into a caller-owned `EventLog`, composing `eidos.a2a.webhook.notification_to_proposal` with the log's own unmodified `accept` — no new event vocabulary, no automatic resume. Each step required its own explicit go-ahead; none reopened a settled decision. See "V0.6 One A2A Boundary" below.

**V0.7 (Strategy & Candidate Generation): architecture accepted (2026-09-22; D-178 to D-185, resolving D-020); Steps 2 to 5 implemented, not pushed, prepared for close-out.** V0.6 is complete and pushed at `ab980c7`; V0.7 redefines what this milestone number means (originally MCP — now resolved, D-184: MCP/RAG are deferred and unassigned, not renumbered into this sequence). Step 1 was architecture/design only: `Strategy` is a distinct object from `Plan` (**D-178**, resolving the long-Open **D-020**) — an execution shape, never a `StepId`, a dependency edge or an agent binding; the approved structural dimensions are topology/parallelism (a sequential tuple of capability stages), verification posture (two members — only one deterministic Verifier exists, D-133) and capability allocation, with agent/model/tool/retry-replan posture explicitly excluded (**D-179**); feasibility filtering (not yet built) will reuse the existing `SystemLimits`/`ReliabilityContract`, no new numeric ceiling (**D-180**); `max_candidates` will be an explicit generation-time parameter, not a `SystemLimits` field — CLAUDE.md's own "two or three" is the ceiling, not reopened (**D-181**); `StrategyId` is plain, UUID-backed identity, no version, no signature — **D-021** (the "Strategy Genome") stays Open and untouched (**D-182**). **Step 2 built the data contracts alone**: `eidos.planning` (`Strategy`, `StrategyStage`, `VerificationPosture`), a new core layer depending only on `eidos.contracts` at this step. **Step 3 built the bounded candidate-generation boundary**: `CandidateGenerator` (a `Protocol`), the deterministic reference `RuleBasedCandidateGenerator` (exactly three rule-based shapes — linear, parallel, staged — gated so a guaranteed duplicate is never constructed), and the orchestration function `generate_candidate_strategies` (structural dedup, a capability-membership re-check distinct from D-180's own future feasibility filtering, identity injection via a new `StrategyIdSource` Protocol mirroring `eidos.recording.ports.IdSource`, and capping at an explicit, required `max_candidates`). `StrategyShape` — Step 2's dropped, then explicitly anticipated, identity-free intermediate type — was reintroduced now that `CandidateGenerator` is its first real consumer; `Strategy` itself is unchanged. No new decision was required: the approved Strategy contract expressed everything needed. **Step 4 built the feasibility gate** D-180 already approved the reuse for: `check_feasibility(strategy, task_genome, reliability_contract, limits) -> FeasibilityReport`, three narrower, strategy-level analogues of V0.2's CAPABILITY/COMPLEXITY/RESOURCE stages — no new numeric limit anywhere, and `eidos.validation.stages`/`.pipeline` (the actual Plan validator) are never imported or called. `generate_candidate_strategies` now stamps identity on every distinct shape before checking feasibility, splits feasible from infeasible, and caps only the feasible pool at `max_candidates`; Step 3's own narrow, ad hoc capability-only re-check — always a placeholder for this — is retired in its favour. **Step 5 resolved the three questions Step 1 left explicitly Open**, by owner ruling, no code change: **D-183** (candidates are feasibility-filtered before selection; full Plan validation runs once, only on the selected strategy's expanded Plan — never on every candidate), **D-184** (MCP/RAG are deferred, unassigned extensions outside the V0.7–V1.0 sequence, not renumbered into it), **D-185** (candidate generation and feasibility are not `MissionEvent`s in V0.7). No Strategy selection, no LLM-assisted generation, no Strategy-to-Plan expansion — those remain later steps, each requiring its own go-ahead. See "V0.7 Strategy & Candidate Generation" below.

There is still no MCP, no RAG, no persistence, no telemetry (V0.9, unbuilt — D-196), no API and no frontend. A2A itself is built (`eidos.a2a`, V0.6 Steps 1–6, none pushed). A full planner does not yet exist either — V0.7 Steps 2 to 4 add the `Strategy` data contracts, a bounded, deterministic `CandidateGenerator`, and the feasibility gate (`eidos.planning`); V0.8 Steps 2, 3, 5 and 6 add the selection boundary itself (`Selector`, `DeterministicSelector`, `select_strategy`), a model-assisted `Selector` (`eidos.selectors.ModelAssistedSelector`), and a deterministic integration suite proving the two compose; V0.8 Step 8 adds Strategy-to-Plan expansion (`eidos.expansion.expand_strategy`) — the produced `Plan` still goes through the existing, unmodified V0.2 validation and V0.3 compiler, unchanged.

Real-model runs have been recorded (V0.4; see "The first real baseline run" and the sections after it). They record what happened in those runs and are not a benchmark: no quality
metric exists anywhere in this repository, and the only latencies recorded are the first run's one trivial completion and the runtime-reported durations of the later runs' calls.

### Bootstrap deliverables

- [x] `CLAUDE.md` — permanent rules, 18 architecture invariants
- [x] `progress.md` — this file
- [x] `decisions.md` — 155 Accepted, 39 Open, 5 Deferred (counts current as of the latest decision below)
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
| **V0.6** One A2A Boundary | Move exactly one agent into an independent process. Test: normal completion, timeout, duplicate event, late event, agent restart, partial artifact, failure. | **In progress — protocol/contract design accepted 2026-09-22 (D-165 to D-177), resolving D-023, D-035, D-036, D-037; D-160 amended by D-176. Steps 1–6 of 9 implemented (`AgentTask`/state contracts, the `eidos.runtime` non-blocking extension, the `eidos.state` event/reducer integration, the `eidos.a2a` client/agent/webhook boundary, the `eidos.recording.a2a` recording adapter); none pushed. Step 5's own found-and-reported resume gap is resolved by D-177 (`EventLog.accept_resumed`/`reducer.reduce_resumed`, explicit, never automatic) — see "V0.6 One A2A Boundary".** |
| **V0.7** Strategy & Candidate Generation *(redefined 2026-09-22, D-184)* | Introduce the `Strategy` representation and the bounded candidate-generation boundary: `Strategy` distinct from `Plan` (D-178), the approved structural dimensions (D-179), feasibility reusing `SystemLimits`/`ReliabilityContract` (D-180), an explicit `max_candidates` parameter (D-181), plain `StrategyId` identity (D-182), the candidate/selection/Plan-validation ordering (D-183), MCP/RAG deferred and unassigned (D-184), no `MissionEvent` for candidate generation (D-185). No Strategy selection, no LLM-assisted generation, no Strategy-to-Plan expansion. | **Closed as scoped — 2026-09-22.** All five steps implemented: the `Strategy`/`StrategyStage`/`VerificationPosture` data contracts (Step 2), the bounded, deterministic `CandidateGenerator` boundary (Step 3), the feasibility gate (Step 4), and the three remaining architectural questions resolved (Step 5, D-183–D-185) — `eidos.planning`, none pushed. See "V0.7 Strategy & Candidate Generation" below. |
| **V0.8** Strategy Selection *(redefined 2026-09-22; originally Agentic RAG, D-028 — see note)* | Given a bounded, feasibility-filtered candidate set, select one `Strategy` without turning the selector into an uncontrolled LLM planner, and expand the selected `Strategy` into a concrete `Plan`: `Selector` contract (D-186, D-187), the deterministic reference `DeterministicSelector` (D-188), a typed, replay-ready `SelectionResult` (D-189), the Strategy-to-Plan expansion layer `eidos.expansion` (D-194, D-195). No Strategy Memory, no ranking infrastructure. | **Steps 2, 3, 5, 6, 7 and 8 implemented — architecture accepted 2026-09-22 (D-186 to D-193, D-194–D-195 2026-09-23): the `Selector`/`DeterministicSelector`/`SelectionResult` contracts and the `select_strategy` orchestration boundary (Step 2); a boundary-hardening audit finding the boundary already sufficient (Step 3); a model-assisted `Selector`, `eidos.selectors.ModelAssistedSelector` (Step 5); a deterministic selection-integration suite proving the boundary end to end (Step 6); the Strategy-to-Plan expansion design (Step 7, D-194/D-195); its implementation, `eidos.expansion` (Step 8) — none pushed.** See "V0.8 Strategy Selection" below. |

> **Note:** V0.7 was originally "MCP" and V0.8 "Agentic RAG" (D-027/D-028). **Resolved 2026-09-22 (D-184):** MCP
> and RAG are deferred, unassigned extensions outside the V0.7–V1.0 strategy-intelligence sequence — neither is
> renumbered into it; each gets a milestone only when a concrete requirement or benchmark needs it. V0.8 is now
> **Strategy Selection**.
>
> **Note (2026-09-23, D-196, Accepted):** at V0.7 Step 1 the owner also named "V0.9 (benchmark)" and "V1.0
> (Strategy Memory)," alongside V0.9's own older, far more numerous "Telemetry" meaning (14+ references
> predating that naming) — a collision D-184 itself flagged and left open at the time. This session briefly
> added a third claimant ("V0.9 Strategy-to-Plan Expansion") by promoting an instruction header to a milestone
> label without checking it first. **Resolved by D-196:** V0.9 stays **Telemetry**, unchanged, below; the future
> controlled benchmark is deferred and unassigned a number, exactly like MCP/RAG above, until a concrete
> requirement fixes its slot; Strategy-to-Plan expansion is filed as **V0.8 Steps 7–8** (the row above),
> matching D-183's own pre-existing "Strategy-to-Plan expansion (V0.8+, not built)" phrasing. Nothing historical
> was renumbered; only this session's own mislabeling moved.
| **V0.9** Telemetry | Structured event logging. Measure latency, tokens, agent calls, tool calls, A2A interactions, RAG rounds, retries, quality. | **Steps 2, 3 and 4 implemented 2026-09-23, none pushed.** Step 2: `eidos.telemetry.project` — a pure, multi-execution projection over already-recorded facts (`ExecutionRecord`, D-159). Step 3: `eidos.recording.ports.UuidStrategyIds`/`UuidPlanIds` (the real id sources `eidos.planning`/`eidos.expansion` were always missing) plus one integration test proving the complete live chain — `TaskGenome` → candidate generation → deterministic selection → Strategy-to-Plan expansion → validation → execution/recording → telemetry projection — for one real mission. Step 4: an inspection found `execution_time_used_ms` (one of `MissionState`'s own six counters) missing from `TelemetryRecord` entirely, and no plan-rejection information at all — both closed with pure copies from `ExecutionRecord`, nothing newly measured. No quality/confidence/rate (D-015/D-016 stay Open), no model identifier, no `strategy_id` on `Plan`/`MissionState`, no mission driver, no MCP/RAG/cache/policy/human-intervention fields. See "V0.9 Telemetry" below. |
| **V1.0** Strategy Optimization | Historical strategy memory, strategy ranking, constraint-based selection, pilot execution. | **Architecture accepted 2026-09-23 (D-198); Steps 1 and 2 of 7 implemented (`eidos.memory.experience` — `ExecutionExperience`/`evaluate_experience`; `eidos.memory.relevance` — `TaskRelevance`/`task_relevance`/`relevant_experience`/`experience_for`), none pushed.** See "V1.0 Execution Experience / Strategy Memory" below. |
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

## V0.6 One A2A Boundary — protocol and contract design accepted; Steps 1–6 of 9 implemented, D-177 resolves Step 5's own gap, none pushed (2026-09-22)

**Step 1 — the exploration, the protocol research and the decision record — is done.** Read-only exploration (D-165 to D-176 drafted with options and a recommendation for each), then owner-directed research against the
published A2A Protocol Specification (a2a-protocol.org, v1.0) and the actual `a2a-sdk` dependency graph before any transport choice was made, then the owner's rulings, recorded as **D-165 to D-176 (Accepted)**. This
family resolves **D-023, D-035, D-036, D-037** and amends **D-160** ruling 4 (**D-176**, narrowly: an admission-guard `paused` mission is unchanged from V0.5; a `paused` mission caused by an A2A-awaiting pause is the
one exception, resumable on the same log). **No fifth `MissionStatus`.** Nothing in V0.1–V0.5's shipped behaviour is different except that one amendment. Steps 2–6 (below) have since built the `AgentTask`/state
contract changes, the `eidos.runtime` non-blocking extension, the `eidos.state` event/reducer integration, the `eidos.a2a` client/agent/webhook boundary itself, and the `eidos.recording.a2a` recording adapter. Step 5
also found that a resumed mission could not yet record further events on the same log (D-167's own described flow; see Step 5's row below) — resolved by **D-177** (see its own subsection, right after the
implementation sequence table): an explicit, never-automatic `EventLog.accept_resumed`/`reducer.reduce_resumed` pair, reading the log's own history rather than adding a `MissionState` field. Still no fifth `MissionStatus`.
Step 6 (see its own subsection, right after D-177's) formalised the one hop D-177 made possible: carrying a webhook delivery to a caller-owned `EventLog`, as a named, tested unit rather than inline caller code.

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
| **3** | Runtime extension: `WorkStatus.SUBMITTED`, `NodeStatus.AWAITING`, `RunOutcome.AWAITING`, `RunResult.awaiting`, `AwaitingInfo` | `RunResult`'s validator accepts the new shape the way it already does `halt`/`NOT_REACHED`; mutation-checked like every other runtime change **Done** — `eidos.runtime` gains the four new members plus `AwaitingInfo` (mirrors `HaltInfo`'s shape, no protocol-specific field, D-165 rule 1). `RunResult.awaiting` is a tuple (more than one node can be independently awaiting, D-165 rule 4) and — unlike `halt`, which correlates 1:1 with `outcome is HALTED` — is a plain fact list, populated whenever a result is `AWAITING` even if a later halt makes `outcome` `HALTED` instead; nothing about a genuinely-submitted node is hidden by that precedence. **The reference executor's own dispatch and readiness logic needed real, if surgical, extension** (this progress row's original wording — "no executor control-flow change" — turned out wrong once the design was worked through, and is corrected here rather than left standing): `_dispatch_work`'s mapping became an exhaustive, explicit dict (matching the existing verify-side idiom) so `WorkStatus.SUBMITTED` cannot silently fall through to the wrong `NodeStatus`; the readiness check distinguishes a *doomed* blocker (genuinely concluded without succeeding) from a *pending* one (only `AWAITING` or itself `NOT_REACHED`) — a node behind only pending blockers becomes `NOT_REACHED`, not `SKIPPED`, exactly mirroring how `NOT_REACHED` already covers "the run halted first"; this propagates correctly through multiple levels via the ordinary per-node check, with **no bulk cascade** the way a halt has — independent branches, and later levels that do not depend on the awaiting node, are dispatched and can finish normally. Outcome precedence extends D-118 rule 4: `HALTED` still outranks everything, including one or more awaiting nodes elsewhere in the same run; `AWAITING` outranks `FINISHED`/`FAILED`. No `WorkExecutor` implementation anywhere in the codebase was touched — nothing produces `SUBMITTED` yet. 36 tests added across `test_runtime_results.py`, `test_runtime_ports.py` and `test_runtime_executor.py` (3 existing exact-enumeration/field-list tests updated, matching the D-154 precedent, since D-165 extended what they pinned); 18 of 18 mutations caught on the first pass. Full default suite 2,595 passed, 2 deselected; unit suite with the LangGraph family blocked 2,056 passed |
| **4** | `eidos.state`: `A2A_TASK_STARTED`/`A2A_TASK_COMPLETED` payloads, the `NodeStatus` mapping (D-166), the `agent_tasks` find-and-replace fold (D-176), the `agent_task_events.py` guard (D-172) | Duplicate `event_id` ignored; a second `STARTED`/`COMPLETED` for one `a2a_task_id` refused, live and on replay, at the same record; the `paused`-cause-aware terminal check (D-176) holds the admission-halt case byte-for-byte **Done** — `A2ATaskStartedPayload`/`A2ATaskCompletedPayload` land in `eidos.state.payloads` (D-166, D-174); `MissionPausedPayload` is rewritten to the D-169 XOR shape (`halt: HaltInfo \| None`, `awaiting: tuple[AwaitingInfo, ...]`, exactly one present — this was already approved in D-169, just not yet built). `reducer.py` gains two `_apply` branches: `A2A_TASK_STARTED` folds a new `SUBMITTED` `AgentTask` via `fold_agent_task`; `A2A_TASK_COMPLETED` requires a correlated, existing `AgentTask` (refusing D-172's "no prior `STARTED`" case explicitly, and a plan/step mismatch separately) and folds an updated copy — neither touches a counter, matching D-176's own docstring rule; that stays `NODE_SETTLED`'s job later, through existing V0.5/D-167 machinery. The D-176 terminal exception is a new `_resumable_completion` helper: a `paused` mission still takes an `A2A_TASK_COMPLETED` **only** when it correlates to an `AgentTask` the state itself still shows non-concluded (`SUBMITTED`/`WORKING`/`UNSPECIFIED`) — checked against what the state holds, never against *why* it paused, since `MissionState` records no such reason and none was added. **A judgment call, flagged rather than silently made:** this reading does not itself distinguish an admission-halt pause from an awaiting one — an admission-halt pause that happens to coexist with an independently outstanding A2A task still takes that task's completion too, since the effect only ever touches `agent_tasks`, never `status`, so a halt's terminality is never reopened by it. Both the ordinary case (halt, nothing outstanding, refused) and this edge case (halt, something outstanding, still folded) are tested and documented in place; D-176 did not itself spell out this interaction, so it was not decided silently. New `eidos.state.agent_task_events` mirrors `step_events.py` exactly one layer over (keyed by `a2a_task_id` instead of `(plan_id, step_id)`), with a new `ReduceOutcome.REPEATED_AGENT_TASK_EVENT` mirroring `REPEATED_STEP_EVENT`; wired into `log.py`'s intake and `replay.py`'s `_fold` (now threading a second `seen` set) exactly the way D-162's guard already was. `execution_record.py` gained the necessary, previously-unbuilt `awaiting` field and a real bug fix in `_run_outcome` (it would have mapped every awaiting-caused pause to `HALTED`) — a direct, unavoidable consequence of the `MissionPausedPayload` shape change, not scope creep. One guard test (`test_no_module_derives_a_model_without_validation`) caught a first draft using `model_copy` to build the completed `AgentTask`; fixed to use the full constructor, like every other reducer-built value. Two pre-existing exact-enumeration tests were updated for the vocabulary growing from nine to eleven emitted types and six to seven `ReduceOutcome` members (matching the D-154/D-165 precedent, not weakened) after a real word-boundary hit on the state package's vendor-name guard forced one docstring sentence to be reworded without the word "MCP" (the guard is intentional — MCP is Anthropic's own protocol name — unlike the already-carved A2A exemption). 39 tests added or updated (15 in the new `test_state_agent_task_events.py`; 18 net-new plus 1 renamed in `test_state_reducer.py`; 3 net-new plus 2 renamed in `test_state_event_records.py`); 21 of 21 mutations caught on the first pass. No A2A client, webhook, transport, timeout, driver, resume automation or fifth `MissionStatus` — those stay later steps. Full default suite 2,674 passed, 2 deselected |
| **5** | `eidos.a2a` (new package): the hand-rolled client, the non-blocking `WorkAgent` implementation, the webhook receiver | A scripted/fake transport for unit tests, exactly as `ScriptedModel` stands in for a real model; the submission call is shown not to block **Done** — `eidos.a2a` built as eight modules. `wire.py`: Pydantic models for the verified A2A v1.0 wire shapes, re-checked directly against `github.com/a2aproject/A2A`'s `specification/a2a.proto` and `adrs/adr-001-protojson-serialization.md` (2026-09-22) rather than trusted from Step 1 — **this found two real corrections**, both implemented, neither a contract change: (1) `TaskState` wire values are the full `TASK_STATE_*` SCREAMING_SNAKE_CASE proto names (ADR-001's own stated breaking change), confirmed by the spec's own worked example, not the pre-unification lowercase form Step 2 flagged as unverified; (2) the JSON-RPC method names are PascalCase matching gRPC (`SendMessage`, `GetTask`), not the `message/send`/`tasks/get` form D-171's prose used. `convert.py`: `agent_task_status_of` (a name lookup, D-166) and `text_artifact_of` (only a usable text part converts; an unsupported `media_type` or nothing usable degrades to no artifact, the same `NO_RESULT` path D-166 already defined, not a new rule). `transport.py`: the one `Transport.post_json` seam and `HttpxTransport`, the only module that imports `httpx` (a new optional `a2a` extra, D-171 — `eidos.providers`'s own dependency-footprint guard test updated to match, the same maintenance Step 4's exact-enumeration tests needed). `client.py`: `send_message`/`get_task`, always sending `return_immediately: true` (a real, load-bearing finding: the wire default is `false`, which would make a spec-compliant server block the call and silently defeat D-165 rule 5 if missed) and never the separate push-notification-config RPCs (inline `task_push_notification_config` instead, D-171 item 2's minimal surface); four failure kinds, never collapsed (item 7): `NETWORK`, `TRANSPORT_TIMEOUT`, `MALFORMED_RESPONSE`, `PROTOCOL_ERROR` — D-173 item 2's "EIDOS-observed timeout" is deliberately not a fifth kind here at all, since it is a different mechanism entirely (`deadline.py`). `agent.py`: `A2AWorkAgent`, the first remote-backed `WorkAgent` (D-175), reusing `refuse_a_reused_step`/`render_artifacts` from the existing local-agent helpers, never `ModelPort`; correlation facts (`a2a_task_id`/`a2a_context_id`) that `WorkResult` cannot carry (D-165 rule 1) are exposed through `submitted_task(step_id)`, one layer scoped to this class rather than a separate injectable tracker. `webhook.py`: `notification_to_proposal` — a pure function, not a server (nothing in EIDOS stands one up); correlates a webhook's wire `taskId` against `MissionState.agent_tasks` (no second correlation store, item 3); only a concluding status is ever proposed as an event (D-174); a completed task's usable text is written to the same `ArtifactStore` a local agent writes to, so Analysis and Verification (unchanged, still local, D-175) read a remote result exactly as a local one. `deadline.py`: `check_deadline`, D-173 item 2's separate "EIDOS-observed timeout" mechanism — a pure question over `AgentTask.started_at`, never polled automatically (D-170). **A genuine gap found and reported, not silently patched:** the full remote-boundary scenario test proves the *runtime*-level resume works completely (a second `run_baseline` pass with `PriorOutcomes` correctly finishes the mission), but the *event-recording* side cannot follow it on the same log — once the D-176 exception accepts the one `A2A_TASK_COMPLETED` a `paused` mission is allowed, `MissionState.status` stays `paused`, and nothing in the currently Accepted design ever moves it back to a status where an ordinary event is accepted again, contradicting D-167's own description ("record_baseline... again... produces the post-hoc `NODE_SETTLED` and... the mission's real terminal event — entirely through machinery that already exists"). Pinned as an explicit, asserted fact in the scenario test (not left as prose) rather than touched in `eidos.state` (out of Step 5's scope; Step 4 is already committed). 119 tests added (`test_a2a_wire.py`, `test_a2a_convert.py`, `test_a2a_transport.py` — against `httpx.MockTransport`, no real socket — `test_a2a_client.py`, `test_a2a_agent.py`, `test_a2a_webhook.py`, `test_a2a_deadline.py`, `test_a2a_scenario.py`, `test_a2a_guards.py`); 33 of 33 mutations caught on the first pass. Full default suite 2,793 passed, 2 deselected. No `eidos.recording` change, no automatic resume, no `tasks/cancel`, no streaming, no authentication subsystem, no fifth `MissionStatus`. Committed as one focused commit; not pushed. Step 6 not started |
| **6** | The recording adapter: appends to a caller-held, still-open `EventLog` after the owning run has returned | The resulting log replays; `checkpoint_at`/`resume`/`records_after` need no change **Done** — `eidos.recording.a2a.record_a2a_notification(log, raw, *, store, execution_id, tenant_id, mission_id, event_id, occurred_at, recorded_at) -> A2ARecordingResult` is the one narrow hop D-177 made possible: it composes `eidos.a2a.webhook.notification_to_proposal` (unchanged) with the caller's own `EventLog.accept` (unchanged) and nothing else — `log` is a parameter on every call, never a constructor field this module keeps, so ownership is never ambiguous; it never calls `accept_resumed`, never resumes, never runs another execution round. `A2ARecordingResult` carries `webhook: WebhookResult` and `intake: IntakeResult \| None` (set only when `webhook.outcome is PROPOSED`) plus a `recorded` convenience property — no new outcome vocabulary: the five required distinctions (malformed external event, invalid correlation, duplicate lifecycle event, invalid event proposal, invalid state transition, successful recording) fall directly out of the existing `WebhookOutcome`/`ReduceOutcome` values, composed, never collapsed. **Lives in `eidos.recording`, not `eidos.a2a`** — the guard test `test_a2a_guards.py::test_nothing_else_in_the_tree_imports_eidos_a2a_yet` had itself anticipated this ("Step 6 will be the first, when it is approved"); `eidos.recording` is not a core layer, so `eidos.recording.a2a` importing `eidos.a2a` violates nothing in item 11's boundary list. **Deliberately not re-exported from `eidos/recording/__init__.py`**: `eidos.a2a` needs the optional `a2a` extra (`httpx`, D-171), and importing plain `eidos.recording` must stay free of it (its own existing guard test says so, unchanged and still passing) — verified directly: `import eidos.recording` loads no `httpx`; `from eidos.recording.a2a import record_a2a_notification` does. A caller imports the submodule explicitly. Both guard files were extended, not weakened, to state this precisely: `test_a2a_guards.py` now names `eidos/recording/a2a.py` as the one permitted importer; `test_recording_guards.py` gained `eidos.a2a` in its allowed-layers set, carved `"a2a"` out of its vendor-name check (mirroring the same carve-out `eidos.state` and `eidos.a2a` itself already made), and gained a new guard proving only `a2a.py` — never `__init__.py`, never any other module — reaches for it. No new `MissionEventType`, no new `ReduceOutcome`, no new `MissionStatus`: none was needed. 11 tests added in the new `tests/unit/recording/test_recording_a2a.py` (A2A_TASK_STARTED reaching the log unaffected; malformed delivery and unknown-task correlation never reaching the log; a completion applying through an AWAITING pause without auto-resuming; both idempotency shapes — a repeated `event_id` and a repeated `a2a_task_id` — refused distinctly; a delivery recorded against the wrong mission's log refused as an invalid proposal; a delivery after the mission finished refused as an invalid state transition; the adapter proven stateless across two independent logs; replay equivalence; a full end-to-end submit → await → pause → webhook → recording adapter → `accept_resumed` → finish); one new guard test in `test_recording_guards.py`, one guard test renamed (not weakened) in `test_a2a_guards.py`. Mutation check: 6 of 6 caught on the first pass. Full default suite 2,830 passed, 2 deselected. Committed as one focused commit; not pushed. Step 7 not started |
| **7** | `tests/protocol/`: normal completion, timeout, duplicate event, late event, out-of-order event, agent restart, partial artifact, failure — written against D-166's lifecycle, per §59, before the implementation they cover | Every scenario asserts `MissionState` stays authoritative, the remote agent never mutates it, `task_id`/`context_id` are preserved |
| **8** | Scenario: submit → pause `AWAITING` → external completion → resume via `PriorOutcomes` → `VERIFY` → complete, on the reference executor | The whole mission's log — spanning the pause — replays from a fresh interpreter with no agent invoked |
| **9** | Close-out: full suite, LangGraph-blocked unit suite, import audit, frozen-path check, mutation checks, docs | Same rigor as V0.5's close-out |

### D-177 — the resume gap Step 5 found, resolved (implemented, 2026-09-22)

Step 5's row above records the gap exactly as found: once D-176's exception accepted one `A2A_TASK_COMPLETED` into a `paused` mission, nothing un-paused `MissionState.status`, so a caller could not record the following
round of ordinary events (the newly-unblocked nodes' `NODE_STARTED`/`NODE_SETTLED`, the eventual terminal event) on the *same* log — contradicting D-167's own description of that flow. The owner ruled **D-177**: resumption
is a distinct, explicit `EventLog` operation, never automatic, that reads the log's own history rather than adding a `MissionState` field. **`reduce()`, `accept()`, `MissionState`, `MissionStatus` and D-176's
`A2A_TASK_COMPLETED` handling are all unchanged** — verified by rerunning every existing test in `eidos.state` and `eidos.a2a` unmodified. Two narrow additions: **`reducer.reduce_resumed`** (a sibling to `reduce`, sharing
every check but the `paused`-refusal, via a shared internal `_reduce`) and **`EventLog.accept_resumed`** (a sibling to `accept`, which finds the mission's actual most recent `MISSION_PAUSED` record via a new
`most_recent_pause`, refuses unconditionally if it was a halt, and requires every step an awaiting pause named to now show a concluded `AgentTask` via a new `resumable_pause` before folding through `reduce_resumed`).
`MissionState.status` stays `paused` through the whole resumed round — it changes only at the next ordinary terminal event, exactly as it always has; no fifth `MissionStatus`. `replay._fold` needed the identical rule as
a direct, necessary consequence (not a reopening of D-157): it now tracks the same `most_recent_pause`/`resumable_pause` logic incrementally so a log extended past an `accept_resumed` call still replays to the same
state; `checkpoint_at`/`resume` inherit the same known limitation `seen`/`task_seen` (D-162/D-172) already carry — a checkpoint taken strictly inside an unresolved pause cannot fold a tail across a later resume (to check
a log end to end, replay it, unchanged advice). **Checked directly against the case that breaks any simpler design:** an admission-halt-paused mission with an independently outstanding, later-concluding A2A task — the
completion is still accepted by unmodified D-176 machinery, but `accept_resumed` still refuses it, because the log's history (not `agent_tasks`, which looks identical either way once the task concludes) says the pause
was a halt; and a genuinely new halt recorded *during* a resumed round is picked up by the next `most_recent_pause` call and makes the mission terminal again, correctly, with no extra state. 33 tests added across a new
`tests/unit/state/test_state_d177_resume.py` (19) and extensions to `tests/unit/a2a/test_a2a_scenario.py` (now completes the full submit → await → pause → webhook → resume → finish flow it always meant to prove) and
`tests/unit/providers/test_providers_guards.py`'s own footprint check was unaffected. Mutation check: 14 of 14 caught on the first pass. Full default suite: see the session log entry below. Committed as one focused
commit; not pushed.

### Step 6 — the recording adapter (implemented, 2026-09-22)

D-177 made a paused mission's completion explicitly resumable; Step 6 is the caller-facing piece that actually gets a webhook delivery onto the log in the first place, formalised rather than left as the inline code
`tests/unit/a2a/test_a2a_scenario.py` had to write by hand since Step 5. **No new decision was needed and none was recorded** — the smallest change turned out to be a composition of two already-Accepted, already-tested
mechanisms (`notification_to_proposal`, `EventLog.accept`), not a new API surface, so the "stop and report a proposed contract first" instruction that governed D-177 did not apply here; this itself was checked, not
assumed, before writing any code. `eidos.recording.a2a.record_a2a_notification(log: EventLog, raw, *, store, execution_id, tenant_id, mission_id, event_id, occurred_at, recorded_at) -> A2ARecordingResult` does exactly
one thing: parse and correlate `raw` against `log`'s own `agent_tasks`, and, only if that yields a proposal, offer it to `log.accept` — the *same* log the caller passed in, borrowed for the call and never held onto,
replaced or wrapped. `A2ARecordingResult` is `webhook: WebhookResult, intake: IntakeResult | None` (`None` exactly when nothing was ever offered to the log) plus a `recorded` property — no third outcome vocabulary
layered on top of the two the contracts already define. It never calls `accept_resumed`, never resumes, never runs another execution round, never touches `MissionState` directly, and holds no state of its own (proved:
two independent logs given to two calls never see each other). It lives in `eidos.recording` (an adapter package, not a core layer) rather than `eidos.a2a` (which speaks only outward, per item 11's own boundary) —
`test_a2a_guards.py`'s own prior wording had already anticipated this exact shape ("Step 6 will be the first, when it is approved"). Because `eidos.a2a` needs the optional `a2a` extra (`httpx`, D-171), the new module is
deliberately **not** re-exported from `eidos/recording/__init__.py`, so importing `eidos.recording` itself stays free of `httpx` — verified directly by subprocess import, and pinned by a new guard test proving only this
one module, never the package's own `__init__.py`, reaches for `eidos.a2a`. 11 new tests in `tests/unit/recording/test_recording_a2a.py`, one new guard test, one guard test renamed (not weakened). Mutation check: 6 of 6
caught on the first pass. Full default suite: see the session log entry below. Committed as one focused commit; not pushed. **Step 7 not started.**

### Carried forward, not decided

Nothing from D-023, D-035, D-036 or D-037 remains open. What genuinely stays open, unaffected by today's rulings: **D-038** (bounding/persisting the applied-`event_id` set — a longer-lived, paused mission does not change
its kind, only how long it might matter, and it stays with D-017); **D-017** (durable persistence, still not built); **D-129** (the general artifact/data-flow question — a remote task's artifact, once produced, is
written exactly once at final settlement, the same write-once rule D-147 already enforces, needing no store change); whether EIDOS ever actively cancels an in-flight A2A task (`tasks/cancel` — not built, not needed for
V0.6's minimal slice, left for a later milestone if wanted). Two small items are pinned by tests at implementation rather than decided here, matching D-118's own precedent: whether a `COMPLETED` report with no artifact
maps to `SUCCEEDED` or `NO_RESULT` (D-166 proposes: `NO_RESULT`, since a completed task with nothing usable is not a failure of execution), and the exact adapter-level deadline value for `TIMED_OUT` (D-173 — a number,
never invented here, same discipline as D-046).

---

## V0.7 Strategy & Candidate Generation — closed as scoped (2026-09-22; D-178 to D-185); none pushed

V0.6 closed and pushed at `ab980c7` (all Steps 1–6 plus D-177). The owner then redefined this milestone number:
originally "MCP" (D-027), V0.7 is now **Strategy & Candidate Generation** — introducing the representation of an
execution strategy and the bounded candidate-generation boundary the fundamental loop names (handoff §2, §83):
*Capability Discovery → Candidate Strategy Generation → Feasibility filtering → bounded candidate set →
[V0.8 Strategy Selection] → Plan validation → execution.* Where MCP/RAG now land is resolved by **D-184**:
deferred, unassigned, not renumbered into the V0.7–V1.0 sequence (see "Carried forward, not decided" below).
**Steps 1–5 are complete; the owner confirmed close-out on 2026-09-22** (the "V0.7 close-out review" subsection
below, prepared at Step 5, is now the closure record — mirroring the same prepare-then-confirm sequence V0.4 and
V0.5 each used).

### Step 1 — architecture and design only (accepted 2026-09-22; no code)

Read-only exploration of `TaskGenome`, `Plan`/`PlanStep`, the V0.2 validation stages, `eidos.compiler`,
`eidos.capabilities`, `SystemLimits`, `ReliabilityContract` and the identifier conventions (D-053), against the
long-Open **D-020** ("Strategy" and "Plan" used interchangeably) and `docs/03_architecture.md` §7's own earmark
for `eidos.planning`. Proposed, and the owner approved, five decisions:

- **D-178** (resolves D-020): `Strategy` is a **distinct object from `Plan`** — an execution shape (capability
  stages, a verification posture), never a `StepId`, a dependency edge or an agent binding. A selected strategy
  may eventually (V0.8+, not built) expand into a concrete `Plan`, through the unmodified V0.2/V0.3 pipeline —
  a `Strategy` grants no validation or compilation shortcut, ever.
- **D-179**: the V0.7 structural dimensions are exactly three — topology/parallelism (a sequential tuple of
  capability stages, each a parallel group), verification posture (two members: `NONE`/`FINAL` — only one
  deterministic `Verifier` exists, D-133, nothing richer to choose between yet) and capability allocation.
  Agent selection (invariant 11), model selection (invariant 9), tool/retrieval selection (no MCP, no RAG yet)
  and retry/replan posture (D-012, D-125 both Open; the compiler rejects `RETRY`/`REPLAN` outright, D-114) are
  explicitly excluded, each for a named, already-existing reason — not by oversight.
- **D-180**: feasibility filtering (not yet built) will reuse the **existing** `SystemLimits`/`ReliabilityContract`
  — a narrower, structural analogue of exactly V0.2's CAPABILITY/COMPLEXITY/RESOURCE stages, no new numeric
  ceiling invented. `eidos.planning` becomes a new **core layer**, alongside contracts/validation/compiler/
  runtime/state — deterministic, no I/O, no clock, no hidden state.
- **D-181**: `max_candidates` will be an explicit, required, no-default generation-time parameter (D-103's "no
  ambient configuration" discipline) — **not** a `SystemLimits` field (a plan-shape ceiling is a different kind
  of thing from a candidate-count knob). CLAUDE.md's own "two or three" is the ceiling; not reopened here.
- **D-182**: `StrategyId` is a plain, UUID-backed identifier (D-053's default) — no version (strategies are not
  replanned in place the way `Plan` is) and no signature/"genome" encoding. **D-021 stays Open and untouched.**

Three questions were surfaced and explicitly left Open, not resolved: (1) the handoff's own diagrams (§2, §83)
place Plan Validation *between* candidate generation and Strategy Selection, while this session's target flow
places it *after* selection — V0.7 does not need this resolved (it stops before either point); (2) the MCP/RAG
milestone renumbering (above); (3) whether candidate generation ever becomes a `MissionEvent`.

### Step 2 — the `Strategy` data contracts (implemented, 2026-09-22)

Scope held exactly to the contracts D-178/D-179/D-182 approved — no `CandidateGenerator`, no feasibility
filtering, no Strategy-to-Plan expansion, no selection. New package `eidos.planning` (`docs/03_architecture.md`'s
own long-standing earmark), a core layer depending only on `eidos.contracts` at this step:

- **`StrategyId`** (`eidos.contracts.identifiers`) — UUID-backed (D-053 default; no exemption applies).
- **`VerificationPosture`** (`eidos.planning.strategy`) — `StrEnum`, exactly `NONE`/`FINAL` (D-179 item 2).
- **`StrategyStage`** — `capabilities: tuple[CapabilityId, ...]` with `Field(min_length=1)`; a capability may
  repeat within one stage (two parallel calls to the same capability is a legitimate shape — a deliberate
  difference from `AgentDescriptor.capabilities`, D-134, which is a set by nature, not a multiset).
- **`Strategy`** — `tenant_id` (defaults, D-079), `mission_id`, `strategy_id`, `stages: tuple[StrategyStage, ...]`
  (may be empty, mirroring D-106's "empty plans pass"), `verification`, `rationale: str` (non-empty). Frozen,
  strict, extra-forbidden — the same `EidosModel` base every other contract uses.
- **`StrategyShape` was reconsidered and dropped.** The Step 1 proposal split an identity-free "shape" the
  generator would produce from an identity-stamped `Strategy` an orchestrator would wrap it into, mirroring
  `eidos.recording`'s injected-`IdSource` discipline. With no `CandidateGenerator` built yet in this step, that
  split has no consumer — introducing it now would be exactly the "field/type that sounds useful" CLAUDE.md
  warns against. `Strategy` is flat, like `Plan` is flat; the split can be added, additively, whenever the
  generator is actually built.

Guard tests (`tests/unit/planning/test_planning_guards.py`, mirroring `test_compiler_guards.py`'s own discipline)
pin: the package's exact module list; no I/O/network/clock/randomness import; imports only `eidos.contracts` (not
yet `eidos.validation` — D-180 permits it once feasibility filtering is built); never imports
`agents`/`providers`/`backends`/`a2a`/`recording`/`capabilities`/`runtime`; no vendor/model name; none of
D-179's excluded concepts (`AgentId`, `StepId`, `model`, `tool(s)`, `max_retries`/`max_replans`, ...) appear as
an imported symbol or a field name on `Strategy`/`StrategyStage`; no module-level mutable state; importing the
package loads nothing from any other layer. 57 tests total (39 in `test_planning_strategy.py`: valid
construction, immutability, the empty-stage rejection, capability/`StrategyId` typing, verification posture,
every forbidden-concept rejection named in D-179, JSON round-trip and equality/hash behaviour matching `Plan`'s
own conventions; 18 in `test_planning_guards.py`). Mutation check: 9 of 9 caught on the first pass (every
`Field(min_length=...)`/required-field constraint in `strategy.py`, plus both `VerificationPosture` values).
Full default suite **2,887 passed, 2 deselected**. Committed as one focused commit; not pushed.

### Step 3 — the bounded candidate-generation boundary (implemented, 2026-09-22)

The Jev-inspired principle translated to strategy level, made real: EIDOS constructs the feasible decision space;
a future model may choose from it, but never defines what is valid. Scope held exactly to "the candidate-generation
layer" — no Strategy selection, no LLM-assisted generation, no Strategy Memory, no Strategy-to-Plan expansion, no
feasibility filtering (D-180's own, separate, later concern: `SystemLimits`/`ReliabilityContract` shape/resource
ceilings). **No new decision was required** — checked, not assumed, before coding: the approved `Strategy`
contract (D-178/D-179) already expressed everything a deterministic generator needed to produce.

- **`CandidateGenerator`** (`eidos.planning.generator`) — a `Protocol`, `generate(task_genome) -> tuple[StrategyShape, ...]`.
  A pure function of `task_genome.required_capabilities` only (D-102's own mission-scoped set — never
  `CapabilityRegistry`, which resolves capability to *agent*, a separate, later concern, D-134), so there is no
  code path through which it could construct a stage naming an unavailable capability.
- **`RuleBasedCandidateGenerator`** — the deterministic reference implementation. `required_capabilities` is
  deduplicated first (first-occurrence order preserved: nothing in `TaskGenome` forbids a repeated entry, and a
  strategy built from raw duplicates would misrepresent capability *allocation*). Exactly three rule-based shapes,
  each **gated** so a guaranteed duplicate is never even constructed (not left for dedup to clean up, though
  dedup is still the backstop): **linear** (one stage per capability — the only shape for 0 or 1 capabilities),
  **parallel** (every capability in one stage — identical content to linear below 2 capabilities, so withheld
  then), **staged** (the first capability alone, the rest together — identical content to linear below 3
  capabilities, so withheld then). **Verification is not an independent axis to permute**: `FINAL` whenever
  anything is allocated, `NONE` for the empty case — multiplying every topology by every posture would inflate
  candidate count without a meaningfully different execution approach, exactly what "do not generate meaningless
  permutations" warns against; a future generator may treat it as independent once a second real posture exists
  (D-179's own limit — one deterministic `Verifier`, D-133).
- **`generate_candidate_strategies`** (`eidos.planning.pipeline`) — the orchestration boundary, "genuinely
  required" because three concerns apply to *any* `CandidateGenerator`, not only the reference one: **structural
  deduplication** (first occurrence of each distinct `(stages, verification)` wins — `rationale` is not part of
  identity), a **capability-membership re-check** (the same "check twice" discipline `check_dependencies` already
  established for `Plan`: every shape's every stage is re-verified against `required_capabilities`, independent of
  whether the generator that produced it kept the rule — a violation is reported in `rejected`, never silently
  dropped, never raised, since an untrusted or future LLM-assisted generator naming an unavailable capability is
  an *expected* case to defend against), and **identity injection** — `strategy_id` is drawn here, never inside
  `generator.py`'s deterministic core, via a new `StrategyIdSource` Protocol (`next_strategy_id() -> StrategyId`)
  mirroring `eidos.recording.ports.IdSource` one layer earlier (D-158 item 3); **no real, uuid-drawing
  implementation lives in `eidos.planning` at all** — a caller supplies one, exactly as a caller supplies a real
  `IdSource` to `eidos.recording` today, keeping the whole package free of randomness (a stronger guard than
  `eidos.compiler`'s own "confined to one file" carve-out). `max_candidates` is required, no default (D-181); a
  negative value is refused outright (Python slicing with a negative count would silently drop from the end, not
  truncate — not what "at most N" means). `CandidateGenerationResult` (`candidates`, `rejected`, `truncated`) never
  ranks, scores or names a "best"/"preferred"/"winner" — candidate generation is not selection (V0.8, not built).
- **`StrategyShape` reintroduced.** Step 2 dropped it for having no consumer; `CandidateGenerator` is that
  consumer now, exactly as Step 2's own report anticipated ("additive, not a breaking change"). `Strategy` itself
  is completely unchanged from Step 2.

New files `eidos/planning/generator.py`, `results.py`, `pipeline.py`; `strategy.py` gained `StrategyShape` only.
Guard tests extended: the exact module list now includes all four; the "only `eidos.contracts`" boundary still
holds (nothing in Step 3 needed `eidos.validation` either); two new guards prove no ranking vocabulary anywhere
in `CandidateGenerationResult` and that none of D-179's excluded concepts appear in any of the three new files.
63 new tests (16 in `test_planning_generator.py`: every shape family, the gating thresholds, determinism,
capability-membership, genome-order preservation, repeated-capability collapse; 24 in `test_planning_pipeline.py`:
capping, truncation observability, dedup — including that a *different* verification posture on the same topology
is correctly kept distinct, closing a real mutation-testing gap found while verifying this — identity injection,
two deliberately misbehaving fake generators proving the capability re-check, JSON round-trip, the no-ranking
guard; 2 new guard tests; the remaining count from the module-list/import updates). Mutation check: **16 of 16
caught** (3 initially missed — the dedup key silently ignoring `verification`, and two field constraints with no
direct construction-level test — each closed with a new test, not by weakening a mutation). Full default suite
**2,950 passed, 2 deselected**. Committed as one focused commit; not pushed.

### Step 4 — the feasibility gate (implemented, 2026-09-22)

*Candidate generation creates possibilities; feasibility filtering determines which possibilities are actually
legal under EIDOS's deterministic constraints* — governance never depends on an LLM behaving correctly. Reuses
only what D-180 already approved (`TaskGenome.required_capabilities`, `ReliabilityContract`, `SystemLimits`); no
new numeric limit anywhere, and `SystemLimits` itself gains no feasibility-specific field.

- **`check_feasibility(strategy, task_genome, reliability_contract, limits) -> FeasibilityReport`**
  (`eidos.planning.feasibility`) — three narrower, strategy-level analogues of V0.2's CAPABILITY/COMPLEXITY/
  RESOURCE stages, never SCHEMA/DEPENDENCY/CYCLE/POLICY (a `Strategy` has no step id, edge or document shape to
  fail those against), and never a call into `eidos.validation.stages`/`.pipeline` — strategy feasibility is not
  Plan validation, proven by a guard mirroring `test_compiler_guards.py`'s own "does not reimplement the V0.2
  stages" check almost exactly (absence of the literal symbol names, not merely non-import).
  1. **CAPABILITY**: every capability in every stage ⊆ `required_capabilities`; the converse is not required
     (D-179's own asymmetry, matching V0.2's own capability stage for `Plan`).
  2. **COMPLEXITY**: stage count vs `max_depth`; the widest single stage vs `max_parallel_branches`; total
     capability occurrences across every stage vs `max_nodes` — strategy-level *estimates* (`verification` is not
     counted, unlike a real compiled `VERIFY` node would be; the real `Plan` a selected strategy expands into is
     checked exactly, for real, later, by the unmodified pipeline).
  3. **RESOURCE**: the same total capability occurrences against the *effective* `max_agent_calls` —
     `min(system ceiling, contract value)`, the identical formula V0.2's own resource stage already uses. At the
     `Plan` level COMPLEXITY's node count and RESOURCE's declared-agent-step count differ (a compiled plan can
     hold non-agent nodes); at the `Strategy` level every stage entry *is* a capability occurrence, so one total
     legitimately feeds both — a fact about what a `Strategy` currently represents, not a shortcut.
  Typed violations only, never a bare bool, never raised for ordinary infeasibility: a new `FeasibilityViolationCode`
  (five members, deliberately separate from `eidos.validation.results.ViolationCode` — most of that vocabulary
  describes a concrete `Plan` document a `Strategy` does not have) and cross-field model validators making a
  mislabelled violation unconstructible, mirroring `Violation`'s own design rule in `eidos.validation.results`
  almost verbatim.
- **`generate_candidate_strategies` updated, not duplicated.** Order is now generate → dedupe → stamp identity on
  *every* distinct shape (so a candidate's `strategy_id` is stable whether or not it turns out feasible, and
  `check_feasibility` always receives a real, fully-identified `Strategy`, matching its own public signature) →
  feasibility-check every one → split feasible/infeasible → cap only the **feasible** pool at `max_candidates` (an
  infeasible candidate never occupies a bounded-set slot). Step 3's own narrow, ad hoc capability-only re-check —
  always a placeholder for the real gate D-180 had already approved — is retired in this gate's favour, not kept
  running alongside it. `RejectedCandidate` now carries the full, identity-stamped `strategy` and its
  `FeasibilityReport`, not a free-text reason.
- **The reference generator's own shapes are unchanged.** Tightening limits changes which shapes *survive*, never
  what `RuleBasedCandidateGenerator` itself *produces* — pinned by a direct test comparing its raw output before
  and after a tight-limit run.

Guard tests extended: the exact module list now includes `feasibility.py`; the "only `eidos.contracts`" boundary
is refined to "`eidos.contracts` and exactly `eidos.validation.limits`" — never bare `eidos.validation`, never
`.stages`/`.pipeline`/`.results` (checked both by import and, mirroring the compiler's own precedent, by the
literal absence of `validate_plan`/`check_capabilities`/`check_resources`/`check_complexity`/`ValidationStage`/
`PlanValidationReport` anywhere in `feasibility.py` or `pipeline.py`); `compiler` added to the forbidden-roots list
alongside the pre-existing `agents`/`providers`/`backends`/`a2a`/`recording`/`capabilities`/`runtime`; the
"loads no extra layer" subprocess check now correctly treats `eidos.validation`'s own transitive load as expected
(Python must initialise a parent package before any submodule — that is import mechanics, not a call) while still
proving every other layer stays unloaded. 36 new tests (23 in the new `test_planning_feasibility.py`: all sixteen
required scenarios plus boundary cases for each of the three checks and the typed-violation construction rules; 13
net-new/changed in `test_planning_pipeline.py`, rewritten for the new signature and the `RejectedCandidate` shape),
plus 2 new guard tests. Mutation check: **12 of 12 caught** (3 initially missed — the `<=` resource boundary, total
capability occurrences coincidentally equalling stage count in the first draft's own test shapes, and `truncated`
computed from the stamped count instead of the feasible one — each closed with a new, more discriminating test).
Full default suite **2,986 passed, 2 deselected**. Committed as one focused commit; not pushed.

### Step 5 — resolve the remaining planning boundary; prepare close-out (2026-09-22)

A documentation/decision step, not an implementation one: inspection found nothing left inside V0.7's own scope
that needed new source code. **`strategy.py` and `feasibility.py` are byte-for-byte unchanged since Step 4
(`b1e6702`)** — confirmed by diff, not assumed. The three questions Step 1 raised and explicitly left Open are now
resolved by explicit owner ruling, recorded exactly as decisions.md entries, matching the established D-165–D-182
format:

- **D-183 — Strategy candidate ordering.** `Generate candidates → deterministic Strategy Feasibility →
  Strategy Selection (V0.8) → Strategy-to-Plan expansion (V0.8+) → the existing, unmodified full Plan Validation →
  compilation.` Only feasible strategies enter selection; full V0.2 Plan validation is never run against every
  candidate, only once, against the selected strategy's expanded `Plan`. Confirms the reading Steps 2–4 were
  already built against — no code changes follow, it fixes V0.8's own future ordering.
- **D-184 — MCP/RAG milestone placement.** MCP and RAG are deferred, **unassigned** extensions outside the
  V0.7–V1.0 strategy-intelligence sequence (Strategy contracts → generation → feasibility → selection → benchmark
  → memory) — neither gets a milestone number until a concrete requirement or benchmark needs it. D-027/D-028
  (originally: MCP at V0.7, RAG at V0.8) are annotated, not reopened in substance. The "Intentionally not built
  yet" table below is updated accordingly.
- **D-185 — Candidate generation events.** Candidate generation and feasibility filtering are **not**
  `MissionEvent` lifecycle events in V0.7; `MissionEventType` gains no member, and a `Strategy` is not a
  `MissionState` field. Strategy-related event vocabulary may be introduced later, only when replay, evaluation
  or Strategy Memory (V1.0) actually needs it.

**Verification, run for this step.** Focused planning suite: **156 passed** (unchanged from Step 4 — no source
changed). Full default suite: **2,986 passed, 2 deselected** (identical to Step 4's own count, confirming nothing
regressed and nothing new was silently added). No new non-trivial logic exists, so no new mutation run was needed
— the existing 9 (Step 2) + 16 (Step 3) + 12 (Step 4) mutation results stand unchanged. An independent check that
`eidos.planning` still imports only `eidos.contracts` and `eidos.validation.limits`, never the Plan validator, a
provider, an agent, a backend, A2A or the compiler: unchanged (the same 48 guard tests in
`test_planning_guards.py` that already prove this, re-run, still green). `decisions.md` and `progress.md` are the
only files this step touched.

**V0.7 close-out review — closed as scoped on the owner's confirmation ("V0.7 is closed as scoped.", 2026-09-22).**

*Definition of done (CLAUDE.md §5), checked against V0.7's own stated scope* (handoff §2/§83's
`Capability Discovery → Candidate Strategy Generation → Feasibility filtering → bounded candidate set →
[V0.8 Strategy Selection]`): the implementation exists (`eidos.planning`: `strategy.py`, `generator.py`,
`pipeline.py`, `feasibility.py`, `results.py`); tests exist at every layer (contracts, the reference generator,
the orchestration boundary, the feasibility gate, static guards) and all pass; the pieces integrate (a real
`TaskGenome` flows through `generate_candidate_strategies` to a bounded, feasibility-filtered, identity-stamped
`CandidateGenerationResult`, exercised end to end in the pipeline tests); failure/edge cases are covered (empty
capability sets, malformed/misbehaving fake generators, every feasibility ceiling individually and combined,
negative `max_candidates`); documentation matches the implementation (this file, `decisions.md`, `README.md`,
`docs/03_architecture.md`); a git checkpoint exists for every step (`ff0ad1e`, `3abaa7c`, `b1e6702`, and this
step's own commit below).

*What V0.7 delivers, against Step 1's own proposal:* a `Strategy` contract distinct from `Plan` expressing exactly
the three approved dimensions and nothing else (topology/parallelism, verification posture, capability
allocation — never a `StepId`, an `AgentId`, a model/vendor/tool name, or a retry/replan field, each checked by a
dedicated test and a static guard); a bounded, deterministic `CandidateGenerator` that can only ever name a
capability the mission's own `TaskGenome` requires; a feasibility gate reusing exactly the existing
`SystemLimits`/`ReliabilityContract` with no new numeric ceiling and no call into the Plan validator; `max_candidates`
as an explicit, required, never-padded, never-defaulted parameter (D-181, CLAUDE.md's own "two or three" the
ceiling); identity (`StrategyId`) injected at the orchestration boundary, never drawn inside the deterministic
core; and, as of this step, the three architectural questions Step 1 could not answer on its own now ruled on.

*What V0.7 deliberately does not deliver* (all explicitly out of scope, confirmed absent by the guard tests and by
inspection, not merely by omission): Strategy selection, ranking or a "best"/"preferred"/"winner" concept of any
kind (V0.8); Strategy-to-Plan expansion (V0.8+); an LLM-assisted `CandidateGenerator` (a future adapter, same
`Protocol`); Strategy Memory, adaptive learning, or any historical-outcome mechanism (V1.0); MCP, RAG, Qdrant
(D-184: deferred, unassigned); a `MissionEvent` for candidate generation (D-185); any change to `Plan`, the V0.2
validator, the V0.3 compiler, or `MissionState` (none was touched in any Step 2–5 commit).

*Invariants exercised by V0.7:* 9 (no model, vendor or SDK name anywhere in `eidos.planning` — a dedicated static
guard, not only a convention); 11 (a `Strategy`, like a `Plan`, requests capabilities, never agents — applied one
level earlier than `Plan` itself, D-179); 14 (the feasible decision space is constructed by code, from
`TaskGenome.required_capabilities` and `SystemLimits`, before any model could ever choose among it — the Jev
principle translated, D-179/D-183's own point). **Not exercised, by scope, not by gap:** 1–8, 10, 12, 13, 15–18 —
V0.7 builds no execution, no `MissionState` write, no event, no verification, no governance and no evidence
mechanism; none of those invariants has anything in this milestone to hold against yet.

*Findings.* Nothing found requiring a code change. The one design choice worth naming again: `StrategyShape` was
dropped in Step 2 (no consumer) and reintroduced in Step 3 (once `CandidateGenerator` became that consumer) —
exactly as Step 2's own report predicted, not a reversal. No real-model, real-generator or real-selector run
exists or is claimed; every number in every V0.7 test is a fixed, deterministic test value.

*Not decided by this step, and not V0.7's to decide:* D-021 (the "Strategy Genome"/signature) stays Open,
untouched by D-182 or anything here. V0.8's own design (the selector itself, how it consumes
`CandidateGenerationResult`, how a selected strategy expands into a `Plan`) is not started and not sketched
further than D-183 already fixes the ordering for.

**Closed (2026-09-22).** The owner confirmed: *"V0.7 is closed as scoped."* No further gate was set (unlike V0.4's
two explicit gates or V0.5's twelve numbered acceptance criteria) — the close-out review above, prepared at Step 5
with every criterion already met, is the closure record itself. V0.7's own commits: `ff0ad1e` (Step 2), `3abaa7c`
(Step 3), `b1e6702` (Step 4), `12122ad` (Step 5) — **entirely local, none pushed.** Pushing follows only on a
separate, explicit instruction, the same standing discipline every prior milestone in this repository has
followed. V0.8 (Strategy Selection) has since started — see "V0.8 Strategy Selection" below.

---

## V0.8 Strategy Selection — Steps 2, 3, 5, 6, 7 and 8 implemented, none pushed (2026-09-22 to 2026-09-23)

V0.7 closed as scoped at `6fb8cb3`. V0.8 is the next link the fundamental loop names (handoff §2, §83):
*feasible Strategy candidates → [V0.8 Strategy Selection] → selected Strategy → Strategy-to-Plan expansion
(future) → the existing Plan Validation → compilation/execution.* The central problem: choose one strategy from
a bounded, already-feasible candidate set without turning the selector into an uncontrolled LLM planner — the Jev
principle applied one step further than V0.7's own candidate generation: EIDOS constructs the feasible decision
space (V0.7), then a bounded mechanism chooses *within* it, never *beyond* it.

### Step 1 — architecture and design only (accepted 2026-09-22; no code)

One load-bearing finding drove the whole design: `eidos.agents.model.ModelPort` (D-135) is **text-in, text-out
only** (`complete(request) -> ModelResponse | ModelFailure`) — a model can never return a `Strategy` directly,
only text. This is not a limitation to design around; it is the mechanism that makes "the selector may choose
only from the supplied candidate set" enforceable in code rather than by policy: a selector can only ever *name*
a candidate (by id), never *produce* one. A second finding: `FeasibilityReport` carries only violations, so two
feasible candidates are indistinguishable from it alone — comparing candidates structurally needs the stage
count/width/capability-occurrence facts `check_feasibility` already computes internally and discards; these are
fully derivable from `Strategy.stages`, the existing public field, so **no V0.7 contract needed to change**.

**"Laya" appears nowhere in this repository** — not in the handoff, not in `decisions.md`, not in any `docs/`
file — confirmed by an explicit search, not assumed absent. Treated purely as a hypothetical future `Selector`
implementation; nothing about its actual semantics is invented.

Proposed and the owner approved four decisions:

- **D-186**: a selected `Strategy` is always one of the supplied feasible candidates; a `Selector` returns only a
  `StrategyId`, never a `Strategy` value or Plan DSL — enforced by the orchestration boundary's membership check,
  not by convention alone.
- **D-187**: the `Selector` contract — `select(candidates, task_genome) -> SelectorChoice`
  (`SelectedCandidate | SelectorFailure`, mirroring `ModelResult`'s own shape) — paired with a deterministic
  orchestration function `select_strategy(...)` performing the zero/one-candidate short-circuit and the final
  admissibility check, mirroring `CandidateGenerator`/`generate_candidate_strategies`'s own two-layer split
  (D-178 onward). Lives in `eidos.planning`, per `docs/03_architecture.md`'s own pre-existing package table.
- **D-188**: the reference `DeterministicSelector`'s tie-break is structural, never scored: fewest total
  capability occurrences, then fewest stages, then generation order. No scalar quality score anywhere.
- **D-189**: `SelectionResult` is a complete, typed, replay-ready value; it is not a `MissionEvent`, not a
  `MissionState` field, and carries no identity of its own (no `SelectionId`) — mirrors D-185's own deferral for
  candidate generation, for the identical reason.

Genuinely unresolved after Step 1 (none blocking Step 2): the exact tie-break rule needed the owner's explicit
confirmation before implementation (now given, as D-188); where a future model-assisted `Selector` would live is
not decided (not `eidos.planning` — a core layer that cannot import `eidos.agents`); Laya's real semantics remain
unknown; Strategy-to-Plan expansion's mechanism (not just its ordering, D-183) is untouched.

### Step 2 — the selection contracts and orchestration boundary (implemented, 2026-09-22)

Scope held exactly to D-186–D-189 — no Strategy Memory, no ranking infrastructure, no model call, no
Strategy-to-Plan expansion. Two new modules in `eidos.planning` (still a core layer: no new dependency beyond
what Steps 2–4 already had; `selector.py`/`selection.py` import only `eidos.contracts`, never
`eidos.validation`/`eidos.agents` — admissibility was already fully decided by feasibility filtering, so the
selector needs no `SystemLimits`/`ReliabilityContract` at all):

- **`selector.py`** — `structural_cost(strategy) -> (total capability occurrences, stage count)`, a tuple, never
  a scalar; `SelectedCandidate`, `SelectorFailureKind` (three members: `UNAVAILABLE`, `TIMEOUT`,
  `MALFORMED_CHOICE`), `SelectorFailure`, `SelectorChoice = SelectedCandidate | SelectorFailure`; the `Selector`
  Protocol; `DeterministicSelector`, the reference implementation (`min(candidates, key=structural_cost)` —
  `min()`'s own stability preserves generation order on an exact tie, so no separate tie-break code is needed).
- **`selection.py`** — `select_strategy(selector, candidates, task_genome) -> SelectionResult`: zero candidates →
  `NO_FEASIBLE_CANDIDATES`, selector never called; exactly one → selected directly, selector never called;
  otherwise the selector is invoked and its claim is checked against the *actual* candidate tuple by identity of
  `strategy_id` — a match returns the **exact existing `Strategy` object**, never a reconstructed copy; no match
  is `INVALID_CANDIDATE_RETURNED`, never substituted; a `SelectorFailure` is `SELECTOR_FAILED` with the message
  preserved, never retried, never silently falling back to any other mechanism. `check_feasibility` is **not**
  re-run here — every candidate offered to a selector is, by construction, already admissible; the membership
  check is an identity check, not a second feasibility pass.
- **`SelectionOutcome`/`SelectionResult`** added to the existing `results.py` (one file for every report-shaped
  result `eidos.planning` returns, mirroring `eidos.validation.results`'s own single-file precedent rather than
  fragmenting further). `SelectionResult` gained a cross-field validator — `selected` set if and only if
  `outcome` is `SELECTED`, `reason` set for every other outcome — mirroring `eidos.state.reducer.ReduceResult`'s
  own "a mislabelled result is unconstructible" rule.

**Two things checked during implementation, not silently assumed, both confirming the approved design needed no
change:**

1. **`SelectorFailureKind` vs. `ModelFailureKind` (D-135).** Reuse is architecturally impossible, not merely
   undesirable: `eidos.planning` is a core layer and the existing guards already forbid it importing
   `eidos.agents`. A new, narrower, three-member vocabulary (no `EMPTY_RESPONSE` analogue) is required by the
   layer boundary itself — the identical reason `FeasibilityViolationCode` (V0.7 Step 4) is already a separate
   vocabulary from `eidos.validation.results.ViolationCode` rather than an import.
2. **Duplicate `StrategyId`s within one candidate tuple.** Nothing in the approved `Strategy`/candidate-generation
   contracts (D-178 onward) states or enforces global uniqueness of `strategy_id` across a tuple. Python's own
   `next()`-over-a-tuple membership lookup already resolves a duplicate deterministically — the first matching
   occurrence in the tuple's own order — with no special-casing needed. **No new rejection rule was invented**;
   the existing, already-deterministic behavior is pinned by two dedicated tests rather than silently trusted.

`SelectorFailure.message` gained `Field(min_length=1)` (not present in the illustrative shape given, but
matching `ModelFailure.message`'s own established convention exactly, per "preserve strict Pydantic conventions
already used by the project") — the one field-level addition beyond the literal proposed shape, and consistent
with it, not a deviation from it.

66 new tests: 26 in the new `test_planning_selector.py` (protocol shape; `SelectedCandidate`/`SelectorFailure`/
`SelectorFailureKind` construction, immutability and extra-field rejection; `structural_cost` — empty, one stage,
multiple stages, multiple occurrences within one stage, tuple-not-scalar; `DeterministicSelector` — minimum cost,
occurrences-before-stage-count, stage-count tie-break, exact-tie generation-order preservation in both
directions, determinism across repeated calls and fresh instances, no mutation of the candidates tuple or its
contents); 25 in the new `test_planning_selection.py` (every orchestration branch named in the implementation
target, including both duplicate-`StrategyId` tests and a `SelectionResult` contract suite); 15 guard tests
updated or added (module list; `SelectorFailureKind`'s narrower-than-`ModelFailureKind` vocabulary; no forbidden
field name on any new model; no ranking/scoring vocabulary on `SelectionResult`; no `selection_id` field;
`litellm`/`rag` added to the vendor-name guard, matching the boundary list this step was asked to prove). Mutation
check: **10 of 10 caught on the first pass**. Full default suite **3,052 passed, 2 deselected**. **D-186 to D-189
(Step 1's own approved design) were formally recorded in `decisions.md` as part of this step** — approved in chat
when Step 2 was authorized, written up here now; decision counts: 146 Accepted, 39 Open, 5 Deferred. **No
additional, new `decisions.md` entry was required beyond that** — both checks made during implementation
(`SelectorFailureKind` vs. `ModelFailureKind`; duplicate `StrategyId` handling) confirmed the approved design was
already sufficient; neither exposed a genuinely new architectural question. Committed as one focused commit; not
pushed. *(Step 3 has since run a boundary-hardening audit — see the row below.)*

### Step 3 — boundary hardening audit (2026-09-23; no contract change)

An inspection step, not a redesign: checked all eleven stated selection-boundary semantics (feasible-only
candidates reach selection; the selector cannot create a `Strategy`; identity is `StrategyId`, never text; the
exact candidate object is returned; zero-candidate/selector-failure are explicit outcomes; one candidate bypasses
the selector; an invalid id never becomes a selection; no automatic retry or fallback; feasibility is never
re-run; `DeterministicSelector` stays pure; the candidate tuple's own bound stays upstream) against what Step 2
actually enforces — by type, by implementation, or by the `SelectionResult` cross-field validator already added
in Step 2. **Conclusion: the Step 2 boundary was already sufficient for all eleven.** Nothing needed a contract
change, so nothing was proposed as a new decision — the "implementation correctness only" branch of the decision
discipline this step was given applied throughout.

Two genuine, narrow gaps were found: **nothing pinned** (as opposed to merely being true by inspection) that
`selector.py`/`selection.py` never call or re-run feasibility, and **nothing pinned** that `eidos.planning.__all__`
exports exactly what the package's own submodule imports intend, no more and no less. Both closed with new static
guard tests, mirroring exactly the precedent `test_feasibility_does_not_reimplement_or_call_the_plan_validator`
already set for the layer below. **Both guards immediately found real, harmless issues and were verified against
them before being trusted:** the feasibility-independence guard caught its own module docstrings — `selector.py`
and `selection.py` each explained *why* feasibility/the Plan validator's own vocabulary isn't reused by naming the
symbol literally in prose, the same false-positive class Step 4's own `feasibility.py` guard hit and was fixed the
same way — reworded to descriptive prose, zero logic changed; the exports guard was sanity-checked by deliberately
removing one `__all__` entry and confirming the test failed, then restoring it. The feasibility-independence guard
was also sanity-checked the other way — a fake call to the (unimported) feasibility gate was inserted and
confirmed caught — before being reverted.

No focused/negative test gap was found in `SelectionResult`'s own cross-field validator: re-reading it shows its
`else` branch (every non-`SELECTED` outcome) has no per-member branching, so Step 2's one representative negative
test per rule already exercises the identical code path all three non-`SELECTED` outcomes share — adding one more
per enum member would test nothing the existing suite doesn't already prove, so none was added, matching "do not
invent tests for theoretical completeness."

2 new guard tests (`test_selection_does_not_rerun_or_reimplement_feasibility`,
`test_all_exports_exactly_what_init_imports_from_its_own_submodules`) plus 2 docstring rewordings (no logic
change — confirmed by diff). No new non-trivial source branch exists to mutation-test; both new guards were
verified by direct, deliberate-violation sanity checks instead (above), the same discipline this project already
applies to guard tests rather than running them through the scratch mutation tool. Full planning suite **224
passed** (was 222). Full default suite **3,054 passed, 2 deselected**. `strategy.py`, `generator.py`,
`pipeline.py`, `feasibility.py`, `results.py`, `__init__.py` (V0.7 and the rest of V0.8 Step 2) confirmed
untouched by diff. **No new `decisions.md` entry.** Committed as one focused commit; not pushed.

### Step 4 — model-assisted Selector architecture, design only (accepted 2026-09-22; no code)

Answered, in writing, before any implementation: the exact model context (`TaskGenome.goal` plus each candidate's
`stages`/`verification`/`rationale` only — never `required_capabilities`, `risk_level`, `autonomy_level`, the raw
`StrategyId`, or `structural_cost`); the label scheme (position-derived `CANDIDATE_1..N`, never the real id); the
output contract (exactly one bracketed label, reusing `eidos.agents.base`'s own existing `[[ref]]` citation
convention rather than inventing a new syntax); the full parsing-edge-case table; the `ModelFailure` ->
`SelectorFailureKind` mapping (confirmed the existing three-member vocabulary already suffices — no new member);
that this is an independent `Selector` implementation with **no** automatic fallback to `DeterministicSelector`
(mirrors D-170's "no automatic driver"); and that package placement is *outside* `eidos.planning` (needs
`eidos.agents.ModelPort`, which the core layer's own guards already forbid), exact location deferred to Step 5's
own inspection. Recorded as **D-190 to D-193** (below). No source code, no new package, no model call — approval
for implementation was requested and given separately, for Step 5.

### Step 5 — implement the model-assisted Selector (2026-09-23)

**Package placement, decided by inspection before any file was created.** `eidos.planning`'s own package
docstring already states a model-assisted `Selector` "is a future adapter *outside* this core layer" — confirmed,
not assumed. The chosen location is a new sibling package, **`eidos.selectors`**, one file
(`model_assisted.py`) plus `__init__.py`. This mirrors two existing precedents exactly: `eidos.providers` adapts
a vendor to `ModelPort` outside the core layer that cannot name a vendor; `eidos.backends` adapts a workflow
library to the runtime's executor port outside the core layer that cannot import it. `eidos.selectors` is the
same shape one layer up — it adapts `ModelPort` to the existing `Selector` Protocol outside the core layer that
cannot import `eidos.agents`. No generic "AI selector framework" was created: `ModelAssistedSelector` simply
implements the Protocol V0.8 Step 2 already defined, holding no state beyond `model`/`settings`.

**Request construction (D-190, D-191).** `_label_candidates` builds `CANDIDATE_1..N` strictly from the supplied
tuple's own position (`enumerate(candidates, start=1)`) — never from `strategy_id`, never from randomness. The
label -> `StrategyId` map lives only for one `select` call. Candidate data is serialized with `json.dumps` into a
fixed-field-order object (`id`, `stages`, `verification`, `rationale` — insertion order, no `sort_keys` needed)
nested under `{"goal": ..., "candidates": [...]}`; JSON was chosen for the *data* specifically because it is safe
against arbitrary adversarial content in a `rationale` string, unlike a bespoke delimited format would be. The
system prompt states the bounded task and the closed output contract; the user prompt explicitly frames the JSON
block as data, not instructions — stated plainly as best-effort only, never the actual security boundary.

**Output parsing (D-192).** `_CANDIDATE_LABEL = re.compile(r"\[\[([^\[\]\n]+)\]\]")`, the exact same pattern as
`eidos.agents.base._CITATION`, reused for a different closed vocabulary. Distinct bracketed tokens are collected
in order of first appearance (`cited_refs`'s own de-duplication idiom); exactly one distinct, resolvable token ->
`SelectedCandidate`; zero, two-or-more-distinct, or an unresolvable token are all `MALFORMED_CHOICE`. No natural
language is ever parsed — "I choose Candidate 2." resolves to zero brackets, hence `MALFORMED_CHOICE`, exactly as
specified.

**Model failures (D-193).** `_FAILURE_KIND_OF` maps `TIMEOUT`->`TIMEOUT`, `UNAVAILABLE`->`UNAVAILABLE`,
`MALFORMED_RESPONSE`->`MALFORMED_CHOICE`, `EMPTY_RESPONSE`->`MALFORMED_CHOICE` — no new `SelectorFailureKind`
member; every `ModelFailure` case already maps onto the three Step 2 approved. `ModelAssistedSelector.select`
never retries and never falls back to `DeterministicSelector` on any failure path — proven by a dedicated guard
(absence of the literal name anywhere in the package, sanity-checked by a manufactured violation before being
trusted) as well as by construction.

**Prompt-injection tests.** Five dedicated cases: an injected instruction in the goal ("ignore previous
instructions..."), a rationale instructing the model to answer with an out-of-set label (`CANDIDATE_999`), a
rationale asking for a different response format entirely, a rationale containing JSON-like text (proves
serialization stays well-formed and the embedded text is carried as an inert string value, never merged into the
structure), and a rationale containing bracket-like text (`[[refs]]`) that could be confused with the model's own
answer token. In every case the test demonstrates the **parser/membership boundary**, not the model, is what
prevents an out-of-set answer — even a `ScriptedModel` explicitly scripted to answer with the injected
`[[CANDIDATE_999]]` token still cannot produce anything but `MALFORMED_CHOICE`, because the label is not in the
per-call map built from the real candidate tuple.

**Tests: 71 new, in `tests/unit/selectors/`** — `test_selectors_model_assisted.py` (request construction, output
parsing, model-failure mapping, `ModelAssistedSelector` itself, integration with `select_strategy`, the five
prompt-injection cases) and `test_selectors_guards.py` (module list; standard-library/`eidos` import allowlist;
no vendor/protocol/Laya name; no `MissionEvent`/Strategy-Memory/Plan-DSL/Laya concept mentioned; no
`DeterministicSelector` fallback, sanity-checked; no module-level mutable list/set state; no raw prompt/response
persistence concept; no `SelectorFailureKind` member beyond the approved three; `eidos.planning` never imports
`eidos.selectors`, checked from both directions; a plain `import eidos.planning` still loads nothing from
`eidos.selectors`). `test_planning_guards.py` was extended, not weakened, by two one-line additions: `selectors`
added to the forbidden-roots set `eidos.planning` may never import, and to the transitive-load subprocess check —
strengthening the exact boundary this step introduces a way to violate.

**Two docstring false positives, same class as V0.7 Step 4 and V0.8 Step 3's own:** the new guard tests initially
tripped on their own explanatory prose — `__init__.py`'s docstring named `DeterministicSelector`/`Laya`/
"telemetry" literally while explaining what this package deliberately does *not* do. Fixed by rewording to
descriptive prose only (e.g. "the deterministic reference selector," "a possible future scoring-based selector
implementation") — zero logic changed, confirmed by re-running the guard immediately after each edit.

**Mutation check: 7 of 7 caught on the first pass** — label mapping (start index), deterministic ordering
(reversed candidate order), parser cardinality (accepting 2+ distinct labels), unknown-label handling (silently
falling back to the first candidate instead of failing), the `ModelFailure` mapping table (one entry pointed at
the wrong `SelectorFailureKind`), `StrategyId` exposure (leaking the raw id into the JSON payload), and fallback
behavior (a malformed answer silently resolved to the first candidate instead of `SELECTOR_FAILED`). The
membership-boundary target was not separately mutated: `selection.py`/`select_strategy` are untouched by this
step (confirmed by diff) and remain covered by the existing, unchanged 224 planning tests. Each mutation was
applied to a pristine copy, confirmed to fail the suite, then reverted and confirmed restored, mirroring the
project's established mutation-testing discipline exactly.

Full planning suite: **224 passed** (unchanged from Step 3 — this step added no code to `eidos.planning`). All
guard tests repo-wide: **532 passed**. Full default suite: **3,125 passed, 2 deselected**. `strategy.py`,
`generator.py`, `pipeline.py`, `feasibility.py`, `results.py`, `selector.py`, `selection.py`, `__init__.py` (all
of V0.7 and V0.8 Steps 2–3) confirmed untouched by diff. **No new `decisions.md` entry beyond D-190–D-193**
(formally recorded as part of this step, mirroring Step 2's own "approved in chat, written up when implemented"
pattern) — nothing implementation revealed needed a further decision. Committed as one focused commit; not
pushed.

### Step 6 — selection integration + deterministic end-to-end evaluation (2026-09-23; no `decisions.md` entry)

**Part 1, the actual gap.** Inspected before writing anything: `CandidateGenerationResult.candidates` (V0.7 Step
4) is already exactly the `tuple[Strategy, ...]` `select_strategy` (V0.8 Step 2) takes as its own second
parameter — the two already-public functions compose directly, with no adapter, wiring function or new
abstraction required. **The gap was a missing test, not a missing component.** Confirmed by the diff at the end
of this step: zero lines changed anywhere under `src/eidos/planning/` or `src/eidos/selectors/`. The one new
test-support addition, `generate_feasible` (`eidos_planning_factories.py`), is a thin, branch-free composition of
`generate_candidate_strategies` with the existing fixtures — proof of the composition, not a new mechanism.

**New suite: `tests/integration/planning/`** (33 tests, four files) — chosen over `tests/scenarios/` because this
step explicitly stops at `SelectionResult`: no `Plan` is built or executed (Strategy-to-Plan expansion does not
exist yet, D-183's own ordering), so it is not a "whole mission" in `tests/scenarios/`'s own sense; it is exactly
`tests/integration/README.md`'s own definition — two or more real components (the reference generator, the
feasibility gate, both `Selector` implementations) working together, deliberately substituting only a
`ScriptedModel` for the one component this project never calls for real in the default suite (D-136's own
established substitution point).

- **`test_selection_pipeline.py`** (12 tests, Part 2) — `TaskGenome` → `RuleBasedCandidateGenerator` → feasibility
  → `DeterministicSelector`, over the specified shapes: zero capabilities and one capability each yield a single
  feasible candidate and **bypass the selector entirely** (a `CountingSelector` test double proves 0 calls, not
  merely that the outcome looks right); two capabilities yield linear+parallel and the selector is actually
  invoked (D-188's tie-break picks the 1-stage shape); three capabilities yield all three structurally distinct
  shapes; a tight `max_depth` rejects only the 3-stage linear shape while parallel+staged still reach the selector
  (proving rejected candidates never reach it, by direct set-disjointness, not by absence of a crash); `max_nodes
  = 0` rejects every candidate, `NO_FEASIBLE_CANDIDATES`, selector never called; the selected `Strategy` is the
  exact feasible-tuple object, checked by `is`; identical input reproduces identical candidate order and selection
  across repeated runs; `SelectionResult` round-trips through `model_validate_json` (not
  `model_validate(json.loads(...))` — strict-mode `EidosModel` only coerces `str -> UUID`/enum when validating
  directly from JSON text, mirroring `eidos.state.records`'s own established round-trip; caught immediately by
  running the test, not assumed).
- **`test_model_assisted_selection.py`** (12 tests, Part 3) — the same pipeline through `ModelAssistedSelector`
  with a `ScriptedModel`: a valid choice; an out-of-set label (`SELECTOR_FAILED`); malformed prose; a `ModelFailure`
  (`TIMEOUT`/`UNAVAILABLE`, parametrized); a genome whose own `goal` carries an injected instruction telling the
  model to answer with an out-of-set label, and a model scripted to actually obey it — still only ever
  `MALFORMED_CHOICE`, never an accepted out-of-set id; a model scripted to *ignore* the injection and answer with
  a real label — still only ever resolves to a real, feasible `StrategyId`; one and zero feasible candidates each
  bypass the model entirely (`model.calls == 0`); a model failure never silently falls back to a deterministic
  choice (`SELECTOR_FAILED`, not `SELECTED`, even though feasible candidates existed); the same scripted answer
  reproduces the same `SelectionResult` across repeated calls; a model-assisted `SelectionResult` round-trips
  through JSON with zero model calls at replay time.
- **`test_selector_comparison.py`** (5 tests, Part 4) — a test-only `SelectionComparison` dataclass (selector name,
  outcome, selected id, feasible-set membership, `structural_cost`, failure reason — no score/rank/best field,
  pinned directly against the dataclass's own field names) built from both selectors run over the *identical*
  candidate tuple: agreement is recorded as equality, a difference is recorded as inequality, neither is called
  correct or better; a `SELECTOR_FAILED` case reports the fact (`structural_cost` is `None`, a reason string is
  present) rather than a missing result.
- **`test_selection_integration_boundaries.py`** (4 tests, Part 6) — this suite itself never imports
  `eidos.compiler`/`.runtime`/`.backends`/`.baseline` (structural proof that "no Plan is built or executed" is
  true of the test file, not only claimed in its docstring); a combined, real run of both packages together (built
  from bare `eidos.contracts`/`eidos.validation` constructors, deliberately not through the shared test-support
  factory hub — see the finding below) loads no `eidos.a2a`/`.recording`/`.backends`/`.providers`/`.state`/
  `.baseline` and no LangGraph/LangChain/LangSmith/`httpx`/`requests`/`mcp`; `eidos.planning`'s own source still
  never imports `eidos.selectors`; `eidos.selectors`'s own source still depends only on
  `eidos.agents`/`.contracts`/`.planning`.

**One genuine, harmless finding, checked rather than assumed.** The first version of the combined-import subprocess
check also forbade `eidos.compiler`/`.runtime`/`.capabilities` and failed — not because `eidos.planning` or
`eidos.selectors` import them (the per-package guards already prove neither does), but because `eidos.agents`
itself (needed for `ModelPort`, D-190) already, legitimately, imports them for its own unrelated `WorkAgent`/
artifact concerns — pre-existing V0.4 architecture, untouched by V0.8. The check was corrected to assert what
actually matters (no protocol/vendor/storage-layer package, no LangGraph/vendor SDK), not to weaken it to pass;
the corrected version was then sanity-checked the other way, by a manufactured `import eidos.recording` added
temporarily to `model_assisted.py` — caught by both this new integration check and the existing Step 5 unit guard
simultaneously, then reverted.

**Mutation testing.** No new non-trivial *production* logic exists to mutate — confirmed by `git diff --stat` on
`src/eidos/planning/` and `src/eidos/selectors/` showing zero changes for this entire step. The new guard logic
(all in `test_selection_integration_boundaries.py`) was instead verified the way this project already verifies
guards: two separate manufactured violations (a fake `import eidos.compiler` inside a test file; a fake
`import eidos.recording` inside `model_assisted.py`), each confirmed caught, then reverted.

**Part 7 (benchmark boundary): not built, only noted.** The future V0.9 benchmark will likely need, as plain
recorded facts and nothing fabricated: a mission/task identifier, candidate and feasible-candidate counts, the
selected `StrategyId`, which selector implementation ran, the selection outcome, the selected candidate's
structural properties, a model call count, a model failure kind when one occurs, and — only once Plan expansion
and execution exist — a verified execution result. No metric on this list is computed, recorded or claimed by
Step 6; `SelectionResult` is unchanged.

**Part 8 (decisions): none created.** Checked against D-186 to D-193 first: every property Step 6 needed to prove
(membership, bypass behavior, no fallback, JSON round-trip) was already a consequence of the existing, unchanged
contracts — nothing here exposed a genuine new architectural question. The one real finding (`eidos.agents`'s own
pre-existing transitive dependencies) is a fact about already-accepted V0.4 architecture, not a new decision.

Full planning suite: **224 passed** (unchanged — no `eidos.planning` code touched). All guard tests repo-wide:
**532 passed** (unchanged — the new checks live in `tests/integration/`, outside that filter, and are reported
separately above). New integration suite: **33 passed**. Full default suite: **3,158 passed, 2 deselected** (was
3,125; +33, none skipped or weakened). `src/eidos/planning/` and `src/eidos/selectors/` confirmed byte-for-byte
untouched by `git diff --stat`. Committed as one focused commit; not pushed. **The V0.9 benchmark has not
started.**

### Carried forward, not decided (as of Step 6)

Everything Step 1 left unresolved stays exactly as recorded, except where Steps 4–5 explicitly resolved it
(package placement, D-190 to D-193): none of the rest was touched by Steps 2, 3, 4, 5 or 6's own, narrower scope.
Laya's real semantics remain unknown. *(Strategy-to-Plan expansion's own mechanism has since been designed and
implemented — see Steps 7 and 8 below.)*

Steps 7 and 8 continue the same milestone: selected Strategy → **[Strategy-to-Plan expansion]** → concrete
`Plan` → the existing, unmodified V0.2 validation → V0.3 compilation/execution — filed here, not as a separate
"V0.9," per D-196 (V0.9 remains Telemetry; the future benchmark stays unassigned; this work matches D-183's own
pre-existing "Strategy-to-Plan expansion (V0.8+, not built)" phrasing).

### Step 7 — architecture and design only (accepted 2026-09-23; no code)

Inspection first, not invention. **D-179 already answers the dependency mapping in its own words** — *"stage
i+1 depends on the whole of stage i"* — so the central structural question was already decided before this step
began; the work was to apply it precisely to `PlanStep.depends_on` edges, not to invent a new rule. Two decisive
findings from reading the actual source, not assumed:

1. **`eidos.planning`'s own existing guard already forbids `StepId`** (`test_no_forbidden_strategy_concept_is_imported`,
   enforcing D-179's exclusion of step ids and edges from `Strategy`) — so the expander cannot live inside
   `eidos.planning`; it must be a new sibling core layer, the same way `eidos.compiler` sits beside
   `eidos.validation` rather than inside it.
2. **`eidos/agents/analysis.py`** already, in practice, depends on `WorkNode.predecessors` to fetch upstream
   artifacts from the store and **fails the step if a predecessor produced nothing** — so the dependency edges
   the expander draws are not just a DAG-shape/depth concern, they are functionally required by a real agent
   (D-129 stays formally Open about the abstract port signature, but D-137's V0.4 answer already, actually,
   works this way today). The real, already-shipped V0.4 baseline plan (`{"gather": "", "analyse": "gather",
   "check": "analyse"}`) independently confirms the same shape for `VERIFY`: `check` depends only on `analyse`,
   never transitively on `gather` — matching `eidos.agents.verification`'s own documented behavior ("over the
   artifacts the VERIFY node's predecessors produced").

Worked both examples from the brief by hand against the actual contracts (not assumed): `[research] → [analysis,
writing]`, `FINAL` produces three `AgentStep`s plus one `VERIFY` step depending on exactly the two final-stage
ids; `[research, analysis]`, `NONE` produces two independent root `AgentStep`s and no `VERIFY` step. Proposed,
not decided, two candidate decisions (everything else was either already covered by D-178/D-179/D-183/D-112, or
an ordinary implementation detail not requiring one): a new sibling core layer `eidos.expansion` with a named
dependency set, and that `FINAL` depends on exactly the final stage's own step ids, never every agent step.
Explicitly did not resolve D-129. No code, no `decisions.md` change — proposal only, per "propose, don't decide."
*(This step was first documented as "V0.9 Step 1"; renamed to V0.8 Step 7 by D-196 — see the note above "Step 7."
No content changed, only the label.)*

### Step 8 — implement the expander (2026-09-23)

**D-194 and D-195 recorded** (the two decisions Step 7 proposed, approved verbatim) before implementation began,
mirroring the established "record, then build" pattern (V0.8 Step 2's own precedent). New core layer
**`eidos.expansion`** (`expand.py` — `PlanIdSource` Protocol, `expand_strategy(strategy, *, ids) -> Plan`),
depending only on `eidos.contracts` and `eidos.planning`, nothing else — verified by both a static per-module
import guard and a subprocess check of the actual combined import graph.

**Identity**: `step_id` is string-backed and D-092-exempt from D-053's UUID default, so it is a **pure,
deterministic derivation** from `(stage_index, position_in_stage, capability)` — no injected source needed, and
two occurrences can never collide since their `(stage_index, position_in_stage)` pair is already unique across
the whole Plan. `plan_id` is UUID-backed with no exemption, so it is drawn **only** from an injected
`PlanIdSource`, mirroring `StrategyIdSource` one layer down exactly. `tenant_id`/`mission_id` copy from the
`Strategy` unchanged; the produced `Plan` is always fresh (`version=1`, `parent_plan_id=None`,
`replan_reason=None`).

**Expansion rules implemented exactly as specified**: one capability occurrence → one `AgentStep`, never
deduplicated; capabilities within one stage share no edge; every stage after stage 0 depends on the complete set
of step ids from the immediately preceding stage; `NONE` emits no `VERIFY` step; `FINAL` emits exactly one
`VERIFY` step depending exactly on the final stage's own step ids; empty stages produce an empty `Plan`
regardless of verification posture (no "final stage" exists for a floating `VERIFY` to depend on).

**Two docstring false positives, same class as every prior step this project has hit**: the new guards initially
tripped on `expand.py`'s own explanatory prose naming `check_feasibility` literally while explaining it is never
called, and on the subprocess transitive-load check initially (wrongly) forbidding `eidos.validation`, which
`eidos.planning` already, approvedly, loads transitively (D-180) — fixed the same two ways this project always
fixes this class of finding: reword the docstring (zero logic change), and correct the check to exclude the
already-approved transitive load, mirroring `test_planning_guards.py`'s own identical exclusion and reasoning one
layer down. Neither was a weakening — both were verified immediately after the fix.

**43 new tests** in `tests/unit/expansion/`: `test_expansion_expand.py` (23 — empty strategy, one/multiple
capabilities per stage, multi-stage fan-out, both worked examples verbatim, `FINAL` vs `NONE`, `FINAL` with empty
stages, duplicate capability occurrences including into the final stage's own `VERIFY` predecessors, `PlanId`
sourced only from the injection point and called exactly once, deterministic and unique step ids, tenant/mission
propagation, fresh-Plan lineage fields, `VERIFY` depending on exactly the final stage and never an earlier one,
no mutation of the input `Strategy`, an ill-formed `StrategyStage` rejected by Pydantic before `expand_strategy`
is ever reached, a representative `Plan` passing full V0.2 validation, and the same `Plan` compiling under V0.3);
`test_expansion_determinism.py` (3 — a representative multi-stage `Strategy` expands to byte-identical JSON under
three different `PYTHONHASHSEED`s, mirroring `tests/scenarios/test_v03_determinism.py`'s own established
subprocess pattern); `test_expansion_guards.py` (17 — module list; forbidden stdlib imports; depends only on
`eidos.contracts`/`eidos.planning`; never `eidos.validation`/`.compiler`/`.runtime`/`.state`/`.agents`/etc.; no
feasibility call, sanity-checked against a manufactured import; no V0.2 validation-rule duplication; no vendor
name; no dynamic-code builtin call; no module-level mutable state; lower layers never import `eidos.expansion`;
importing `eidos.expansion` loads no compiler/runtime/agent/protocol layer, sanity-checked).

**Mutation check: 7 of 7 caught on the first pass** — step-id derivation dropping the position component
(occurrence collision), a stage depending on itself instead of the preceding stage, `VERIFY` scoped to every
agent step generated so far instead of the final stage alone, the `FINAL`/`NONE` branch condition inverted,
`plan_id` drawn from the `Strategy` instead of the injected source, `tenant_id` swapped for `mission_id`, and the
empty-stage guard removed (a floating `VERIFY` step on an empty Plan). Each applied to a pristine copy, confirmed
to fail the suite, then reverted and confirmed restored.

Full planning suite: **224 passed** (unchanged — this step added no code to `eidos.planning`). All guard tests
repo-wide: **549 passed** (was 532; +17). Full default suite: **3,201 passed, 2 deselected** (was 3,158; +43).
`src/eidos/planning/` and `src/eidos/selectors/` confirmed byte-for-byte untouched by `git diff --stat`. D-129
stays Open, not closed. Committed as one focused commit; not pushed. *(This step was first documented as "V0.9
Step 2"; renamed to V0.8 Step 8 by D-196 — no content changed, only the label.)* No further Strategy-to-Plan
expansion step has started.

### Carried forward, not decided (as of Step 8)

D-129 stays Open — this step built dependency edges compatible with the mechanism that already, actually works
today (D-137), without resolving the broader abstract question. Replanning lineage through Strategy selection
(threading a real `version`/`parent_plan_id`/`replan_reason` through `expand_strategy`) is not sketched. Laya's
real semantics remain unknown.

---

## V0.9 Telemetry — Steps 2, 3 and 4 implemented, none pushed (2026-09-23)

The D-196-resolved meaning of "V0.9" — Telemetry, not Strategy-to-Plan expansion (filed as V0.8 Steps 7–8 above).
V0.8 is complete at `6f191c8` (V0.9's own numbering resolved separately at `3ff21d3`, D-196).

### Step 1 — architecture and design only (accepted 2026-09-23; no code)

Inspection first. `eidos.state.execution_record`'s own module docstring already states the governing boundary,
verbatim: *"It describes one execution. It is not strategy memory (V1.0) and not the telemetry platform (V0.9)."*
— D-159 item 3, already Accepted. Telemetry's job was therefore already scoped by an existing decision before
this step began: a further pure projection over the same already-recorded facts, generalized across executions,
never a second authoritative store. `docs/11_evaluation.md` (a bootstrap-era, DERIVED document) independently
confirms the same boundary in its own words and already reserves three separate future packages —
`eidos.telemetry` (V0.9), `eidos.memory` (V1.0), `eidos.evaluation` (V1.1) — none of which this step builds
beyond the first.

Inventory taken directly from source, not assumed: most of the handoff §33 field list is **already recorded**
(`ExecutionRecord`'s own counters, per-node facts, mission outcome) or **cleanly derivable** (per-status node
counts, a remote-task count from existing `A2ATaskStartedPayload` events, a wall-clock span from the log's own
bounds). Two things are available only *transiently*: the model identifier already flows through
`RecordingModel.complete()` but is never extracted into `ModelCallFacts`. One thing does not exist at all:
`Strategy`→`Plan` linkage — no execution today is ever produced from a `Strategy` (no mission driver calls
`expand_strategy` yet), so nothing can carry a `strategy_id` regardless of what Telemetry does. Both are flagged
as future, separate, narrow extension points — neither built now.

No durable storage proposed (the existing JSONL log is already enough for a pure projection); no benchmark logic
sketched (`docs/11_evaluation.md` §10–12 already describes that separately, untouched); no quality/confidence
field (D-015/D-016 stay Open, unfabricated). No code, no `decisions.md` change — proposal only.

### Step 2 — implement the projection (2026-09-23)

**No new decision was required** — the package boundary was already anticipated in `docs/03_architecture.md`'s
own pre-existing table (`eidos.telemetry`, V0.9), and D-159 already fixed the Event-Log/`ExecutionRecord`/
Telemetry boundary this step builds on rather than revisits.

New core layer **`eidos.telemetry`** (`project.py` — `TelemetryRecord`, `project(records) -> TelemetryRecord |
ReplayRejection`), depending only on `eidos.contracts`, `eidos.runtime` and `eidos.state` — verified by both a
static per-module import guard and a subprocess check of the actual combined import graph. **Pure and
deterministic, exactly like `execution_record` itself**: no I/O, no clock, no randomness; `project` takes an
in-memory `Iterable[EventRecord]` — precisely `execution_record`'s own signature — and composes it rather than
re-folding events. No filesystem loader was built: nothing in this step's approved scope needed one, and the
brief's own boundary correction (keep the pure projection free of I/O; any outer loader stays strictly separate)
is honoured by simply not building a loader at all yet, rather than building one and then having to keep it
apart.

**Fields added, all genuinely derived**: identity; the six existing budget counters; mission/run outcome and
verification status; eight per-`NodeStatus` counts; the model-call count; a `remote_task_count` (counts
`A2ATaskStartedPayload` occurrences — named protocol-neutrally, not `a2a_task_count`, since the field itself
never needs to know which remote-execution boundary produced the submission, and the module never imports the
protocol package itself); the log's own event count and bounds; and `mission_wall_clock_ms`, the bounds' own
span. **Left deliberately signed, not clamped to zero**: `ExecutionRecord`'s own bounds are documented as "never
an ordering," so a pathological log could record an earlier bound after a later one — clamping that away would
hide a real anomaly rather than report it (D-158 item 4's "facts only," applied one layer up).

**Explicitly not added**, exactly as scoped: a model identifier on `ModelCallFacts`; `strategy_id`; any
quality/confidence/ranking/scoring field; any new `MissionEvent` type; any durable store; any benchmark or
Strategy Memory logic; any new external dependency.

**Two docstring/guard false positives, the same established class this project always hits and fixes the same
way**: the literal word "A2A" in two explanatory sentences tripped the vendor-name guard (mirroring
`eidos.recording`'s own precedent of treating "a2a" as a protocol name worth flagging by default) — fixed by
rewording the prose *and*, more substantively, renaming the field itself from `a2a_task_count` to
`remote_task_count`, since the field genuinely has no reason to name a specific protocol; and the transitive-load
subprocess check initially (wrongly) forbade `eidos.compiler`/`eidos.validation`, which `eidos.runtime` (an
approved dependency, needed for `NodeStatus`/`RunOutcome`) already, legitimately, loads for its own
pre-existing `ExecutionContext` — the identical class of finding V0.8 Step 6 made for `eidos.agents`, fixed the
same way: the check corrected to exclude the already-approved transitive load, not weakened.

**34 new tests** in `tests/unit/telemetry/`: `test_telemetry_project.py` (15 — a verified baseline's every copied
field cross-checked directly against `execution_record`'s own independently-computed value; the fixed test
values; determinism across repeated calls and a plain generator input; JSONL round-trip reconstruction equal to
the live projection; per-status node counts for a fully-succeeded mission, a halted mission with `NOT_REACHED`
nodes, and a plan-rejected mission with zero node activity; a remote-task count derived from a hand-built log
carrying `A2ATaskStartedPayload`/`A2ATaskCompletedPayload`; a failed model call leaving `tokens_used` at 0 rather
than guessed; `mission_wall_clock_ms` shown distinct from accumulated node duration; no mutation of the input;
the same typed `ReplayRejection` `execution_record` itself gives for an empty log); `test_telemetry_guards.py`
(19 — module list; forbidden stdlib imports; depends only on `eidos.contracts`/`.runtime`/`.state`; never
`eidos.agents`/`.providers`/`.backends`/`.a2a`/`.recording`/`.capabilities`/`.selectors`/`.planning`/`.expansion`/
`.baseline`/`.compiler`/`.validation`; never imports the reducer; does not duplicate event-folding logic
(`execution_record(` must actually appear; `reduce(`/`replay(`/`EventLog(` must not); no vendor name; no
quality/ranking/scoring field on `TelemetryRecord`; no `strategy_id`/`model` field; no dynamic-code builtin call;
no module-level mutable state; lower layers never import `eidos.telemetry`; importing it loads no agent/provider/
backend/protocol layer, sanity-checked against a manufactured import that all three relevant guards caught
simultaneously).

**Mutation check: 7 of 7 caught on the first pass** — node-status counting collapsed to a single status instead
of accumulating, the remote-task count counting every record instead of only submissions, the wall-clock span
computed from one bound twice, a missing seconds-to-milliseconds conversion, `tokens_used` silently substituted
with a different counter, `verified` hardcoded to `False`, and `ReplayRejection` propagation removed entirely.
Each applied to a pristine copy, confirmed to fail the suite, then reverted and confirmed restored.

Full existing `tests/unit/state/` and `tests/unit/recording/` suites unchanged: **508 passed** (proves the V0.5/
V0.6 event/replay authority this step reads from, never writes to, is untouched). All guard tests repo-wide:
**568 passed** (was 549; +19). Full default suite: **3,235 passed, 2 deselected** (was 3,201; +34). No source file
outside `src/eidos/telemetry/` and `tests/unit/telemetry/` was created or modified. No `decisions.md` entry was
required. Committed as one focused commit; not pushed. *(Step 3 has since connected this projection to a real,
live mission — see the row below.)*

### Step 3 — connect the full live chain (2026-09-23)

Inspected first (no code): grepped for every caller of `expand_strategy` and found exactly one, its own module
and its own unit tests — the whole gap was that nothing connects a `Strategy` to a live mission, and tracing why
led to a single, precise finding: `generate_candidate_strategies` and `expand_strategy` each need an injected id
source (`StrategyIdSource`, `PlanIdSource`), and neither has a real implementation anywhere — only the `Protocol`
definitions and fixed-value test doubles. Both Protocols' own docstrings already say where a real one belongs:
"a caller supplies one, exactly as a caller supplies a real `IdSource` to `eidos.recording` today." Everything
else downstream — `run_baseline`, `record_baseline`, `project` — already composes with a `Plan` regardless of its
origin (D-178's own promise), confirmed empirically at V0.9 Step 2. D-183 already governs the exact ordering this
step connects; nothing was reopened.

**Implemented exactly the inspected minimum.** Two real, UUID-backed id sources — `UuidStrategyIds`,
`UuidPlanIds` — added to `eidos.recording.ports`, mirroring `UuidEventIds` exactly (a frozen, slotted dataclass,
one method, `uuid.uuid4()`). Placed there, not in a new package: `eidos.recording` is already the project's one
established home for a real Clock/IdSource adapter (D-158 item 3), and neither `eidos.planning` nor
`eidos.expansion` — both deterministic core layers — may draw randomness themselves. No new Protocol, no new
abstraction: each class satisfies the existing `StrategyIdSource`/`PlanIdSource` Protocols structurally, and
`eidos.recording` did not need to start importing `eidos.planning`/`eidos.expansion` to add them — only the
plain `StrategyId`/`PlanId` types, already in `eidos.contracts`.

**One new integration test**, `tests/integration/planning/test_strategy_to_telemetry_integration.py`, proving the
complete, real composition for one mission: a `TaskGenome` (`research`/`cost`/`security`) through
`RuleBasedCandidateGenerator` (3 real, distinct candidates, real `StrategyId`s) → `DeterministicSelector` +
`select_strategy` (the selector genuinely invoked and choosing among real candidates, not the single-candidate
bypass) → `expand_strategy` (a real `PlanId`, tenant/mission identity and stage topology verified against the
selected `Strategy` itself) → `validate_plan` (accepted) → `record_baseline` over real V0.4 agents and a scripted
model (every node succeeds, verified) → `project` (a `TelemetryRecord` whose own identity — tenant, mission,
execution, plan id and version — matches the executed mission exactly, and whose counts match the real run). A
second test proves two independent passes over the same genome never repeat a `StrategyId` or `PlanId`. No
production glue code beyond the two id sources was needed — the composition is direct, already-typed function
calls, exactly as the inspection predicted.

**One genuine, pre-existing guard correctly caught a real scope change, not a false positive.** V0.8 Step 6's own
`test_this_integration_suite_never_imports_the_plan_or_execution_layer` asserted that *every* `test_*.py` in
`tests/integration/planning/` avoids the compiler/runtime/backends/baseline layer — true when it was written, no
longer true now that this step's own file exists specifically to compile and execute a real Plan. Fixed by
scoping the guard to the four files it was actually written for, with the new file's own opposite claim stated in
its own docstring instead — not a weakening, a correction to match what the directory now legitimately contains.

**No decisions.md entry**: D-183 already governs this ordering; adding a real id-source implementation was
already anticipated by `StrategyIdSource`/`PlanIdSource`'s own docstrings, not a new architectural choice. No
V0.1–V0.8 contract was touched (confirmed by diff: only `eidos.recording` and one test guard file changed) and no
implementation contradiction was found.

**Mutation check: 2 of 2 caught** — each id source returning a fixed id instead of drawing a fresh one. Relevant
existing suites unchanged: `tests/unit/planning/` **224 passed**, `tests/unit/expansion/` **43 passed**,
`tests/unit/recording/` **106 passed**, `tests/unit/state/` **402 passed**, `tests/unit/telemetry/` **34 passed**.
All guard tests repo-wide: **568 passed** (unchanged — no new guard test was added; the existing `eidos.recording`
guards already cover the addition, confirmed by running them directly). Full default suite: **3,237 passed, 2
deselected** (was 3,235; +2). Committed as one focused commit; not pushed. *(Step 4 has since closed two evidence
gaps this step's own inspection left open — see the row below.)*

### Carried forward, not decided (as of Step 3)

The model-identifier and `strategy_id`-on-`Plan`/`MissionState` extension points stay exactly as flagged —
neither is decided or built. D-129 stays Open. No durable telemetry store exists. No mission driver or automatic
loop exists (D-170 unchanged) — this step's own composition is a single, manual, test-proven call sequence, never
an automatic one. The future benchmark (`eidos.evaluation`, V1.1) and Strategy Memory (`eidos.memory`, V1.0)
remain entirely unbuilt and undesigned.

### Step 4 — close the two evidence gaps inspection found (2026-09-23)

Inspected first (no code, a separate turn): asked whether the current execution/event/telemetry chain preserves
enough trustworthy evidence for a future controlled benchmark. Checked `TelemetryRecord`'s own fields directly
against `MissionState`'s six budget counters and found **`execution_time_used_ms` missing entirely** — an
implementation gap against `TelemetryRecord`'s own docstring promise ("every field is copied or derived from
`ExecutionRecord`"), not a deliberate scope choice anyone had ruled on. Also found `TelemetryRecord` carries no
plan-rejection information at all, even though `ExecutionRecord.plan_rejected_at` already computes it — "invalid
-plan interception," a metric a benchmark would need, could not be read from `TelemetryRecord` in any form.
Separately determined that persistent `Strategy`→`Plan` lineage is **not** required for the benchmark: the same
caller that selects a `Strategy` already holds it in scope when it later calls `expand_strategy` and `project`,
so external, in-process correlation suffices (mirrors D-185/D-189's own "nothing persisted until something
actually needs it persisted" discipline) — the need only arises at V1.0 Strategy Memory, a separate, later
question. No `strategy_id` was proposed or added.

**Implemented exactly the two fields inspection proposed, both pure copies from `ExecutionRecord`, nothing newly
measured**: `execution_time_used_ms: int` and `plan_rejected_at: PlanRejectionStage | None`. Deliberately **not**
`plan_rejection_reasons` — kept `TelemetryRecord` flat (a scalar enum, not a per-case detail tuple), consistent
with its own established "counts and typed enums" shape. `execution_time_used_ms` is never combined with
`mission_wall_clock_ms` into a third number (D-158 item 4's "labelled by source, never combined," applied here
too) — a new test builds a genuinely parallel two-step topology (`gather`/`analyse` as independent roots, not
`verified_baseline()`'s own linear chain) and proves `execution_time_used_ms` (12,005 ms, the sum of both nodes'
own recorded durations) exceeds `mission_wall_clock_ms` (9,000 ms, the event-log span) — the exact "fast because
parallel vs. fast because cheap" distinction the gap analysis named.

**6 tests added or extended** in `tests/unit/telemetry/test_telemetry_project.py` (37 total, was 34): the
existing field-for-field cross-check against `ExecutionRecord` extended with both new fields; the existing
fixed-value and plan-rejection tests extended with explicit assertions; one new test proving `plan_rejected_at`
reflects the actual recorded gate (`COMPILATION`, not just the default `VALIDATION`) rather than a hardcoded
value; one new test cross-checking `execution_time_used_ms` against `ExecutionRecord` directly; one new test for
the parallel-exceeds-wall-clock property above. Existing JSONL round-trip and determinism tests needed no
changes — they already compare whole objects, so both new fields were exercised automatically. All 19 existing
guard tests pass unchanged (no new vocabulary, no new dependency).

**No decisions.md entry**: both additions complete an already-Accepted decision's own stated intent (D-159 item
1's "the folded counters," `TelemetryRecord`'s own Step 2 docstring promise) rather than deciding anything new;
`TelemetryRecord` is V0.9's own type, not a V0.1–V0.8 contract, and nothing about `EventRecord`, `MissionState`,
`ExecutionRecord`, the reducer, or `eidos.recording` was touched (confirmed by diff: only the three
`eidos.telemetry`-related files changed) — no implementation contradiction was found.

**Mutation check: 2 of 2 caught** — `execution_time_used_ms` swapped for the wall-clock value, and the
`plan_rejected_at` assignment dropped entirely. Relevant existing suites unchanged: `tests/unit/state/` +
`tests/unit/recording/` **508 passed**. All guard tests repo-wide: **568 passed** (unchanged — no new guard test
needed). Full default suite: **3,240 passed, 2 deselected** (was 3,237; +3). Committed as one focused commit; not pushed.

### Carried forward, not decided

`plan_rejection_reasons` (the full, per-violation tuple) stays out of `TelemetryRecord` on purpose — reachable
one hop away in `ExecutionRecord`/the raw log. A separate, unconfirmed question found but not fixed this step:
`ExecutionRecord.plan_rejected_at`/`plan_rejection_reasons` only ever match a `PlanRejectedPayload` for the
*same* `plan_id` as the currently active plan — an earlier, rejected plan *version*'s own rejection history
(relevant once replanning is exercised) would not surface there either, and this step did not touch
`ExecutionRecord` itself to look further. Model identifier, `strategy_id`, quality/confidence scores, the
benchmark and Strategy Memory all remain exactly as deferred at Steps 1–3.

---

## Benchmark 1 — Execution-Control Comparison (2026-09-23; deliberately unassigned a milestone number, D-196/D-197)

**A controlled engineering/reproducibility evaluation, not a statistically significant study.** It answers one
question only — "does EIDOS's validated execution-control layer measurably change interception, verification
and reproducibility compared with an unvalidated path, on the same scripted tasks?" — never "is EIDOS superior"
and never a claim of statistical significance (CLAUDE.md §7). Inspection first (two design turns, no files
touched, covering research question, baselines, task classes, metrics, repetition, confounders, cold/hot-path
separation, and the multi-plan-version `ExecutionRecord` gap — determined not to block this benchmark, since no
replan loop exists to reach it), then an owner-approved implementation with 13 explicit final decisions on
conditions, task classes, metrics and scope.

**Location (D-197):** `tests/support/eidos_benchmark_harness.py` — the one reusable harness, pythonpath'd, never
collected, mirroring every other `eidos_*_factories.py` module — and
`tests/scenarios/test_benchmark_execution_control.py` — the actual assertions and case tables, already a
collected `testpaths` entry. Found by inspection, not assumed: no `scripts/`/`tools/`/`benchmarks/` directory
exists anywhere in the repository, and `progress.md`'s own "Intentionally not built yet" table already reserves
`evaluation/` for a *different*, later milestone (V1.1) — so neither `src/eidos/evaluation` nor any new
top-level directory could be created without contradicting an already-Accepted decision. No `pyproject.toml`
change. **No core contract, `MissionEvent`, or `src/eidos` package was added or changed** — every condition
composes only already-shipped `eidos` code.

**Four conditions.** **A — Direct Agent Baseline:** one `WorkAgent` called directly, bypassing `Plan`,
validation, the compiler, `eidos.runtime` execution, the `EventLog` and `Telemetry` entirely — runner-side
capture only. **B — Fixed Workflow:** a hand-authored `Plan` through the existing, unmodified
`validate_plan → compile_plan → bind_plan → execute → verify → record_baseline → project` chain. **C —
LLM-Generated Workflow:** a model's Plan-DSL JSON text through the existing, unmodified `validate_plan_json`
ingress (D-107) — a rejected plan is captured from its own `PlanValidationReport` and never reaches
`record_baseline`; an accepted one continues through the identical path B uses. **D — EIDOS Validated Strategy
Execution:** the proven chain (`generate_candidate_strategies → select_strategy → expand_strategy →
validate_plan → record_baseline → project`), with **D1** (`DeterministicSelector`, D-188) and **D2**
(`ModelAssistedSelector`, V0.8 Step 5) run wherever ≥2 candidates give the selector an actual choice — both see
the identical feasible candidate set. D2 always names `CANDIDATE_1` (the linear shape); `DeterministicSelector`'s
own tie-break (D-188) always resolves to the parallel shape once ≥2 capabilities exist — so D1 and D2 are
guaranteed to disagree, exactly the comparison D2 exists to make. Neither selector's own contract was modified.

**Five task classes**, each carrying only the failure sub-cases that make semantic sense for its own topology:
sequential reasoning (valid, agent/model failure, verification failure), parallel independent subtasks (valid,
one branch fails while the others succeed), verification-heavy (valid, missing/insufficient evidence),
constrained/failure-prone (agent/model failure, a deterministic `AdmissionGuard` halt), invalid-plan
interception (a valid-plan sanity case, a plan requesting an undeclared capability, and — condition C only — a
syntactically malformed JSON document at the untrusted ingress). Condition D never appears in the invalid-plan
class: `expand_strategy` only ever produces a `Plan` that `validate_plan` already accepts (D-183), so D
structurally cannot exercise interception — a reportable finding, not a gap.

**A genuine finding, not previously flagged:** verification *failure* does not produce `MISSION_COMPLETED` with
`verified=false`, as an earlier design pass assumed. A `VERIFY` node that FAILs is itself not `SUCCEEDED`, so
`RunResult`'s own consistency check makes the whole run `FAILED`, not `FINISHED` — the mission never reaches
`MISSION_COMPLETED` at all, carrying `MissionFailureCause.VERIFICATION_FAILED` instead. (`COMPLETED` with
`verified=false` is reserved for a *finished* run with no `VERIFY` step at all — `VerificationPosture.NONE`.)
Caught by running the benchmark itself and correcting the assertions to match, not by inspection alone — an
even stronger finding for the benchmark's own central question, since it means EIDOS treats an unverifiable
answer with the same seriousness as an execution failure, never a quiet asterisk on a "completed" mission.

**Cold vs hot path.** Candidate generation, feasibility, selection and expansion are timed by the runner's own
`time.perf_counter`, separately from validation-onward — confirmed by inspection that `record_baseline`'s first
event (`MISSION_CREATED`) fires only after the cold path has already finished, so `TelemetryRecord`'s own
bounds never see it. Nothing was added to core telemetry or a new `MissionEvent` to close this gap (D-185 stays
exactly as it is) — runner-side timing only. The same blind spot applies to D2's own selector model call, which
happens during the cold path and is invisible to `TelemetryRecord.model_call_count`; the harness recovers it
separately as `selector_model_calls`, proven present (`== 1`) whenever D2 runs.

**Metrics reported as a vector, per condition/task-class/case — never combined into a score, ranking or tier**
(D-188's own "never weighted or combined into a single number," applied one layer up): `dispatched_anything`,
`mission_status`, `run_outcome`, `verified`, `failure_cause`, `plan_rejected_at`, `execution_time_used_ms`,
`mission_wall_clock_ms`, `model_call_count`, `selector_model_calls`, `tokens_used` (always labelled
`tokens_are_scripted=True` — every model call in this benchmark is `ScriptedModel`, D-136's own established
substitution point, never a real provider measurement), `cold_path_ms`, `hot_path_ms`, and a `digest` (sha256 of
the deterministic serialization) for the reproducibility check. `pytest -s -v` on the test file is the
benchmark's own metric-vector report.

**Reproducibility** mirrors `tests/scenarios/test_v03_determinism.py`'s own hash-of-serialized-output technique:
two independent runs of the identical condition/case must produce byte-identical digests. D1/D2 draw genuinely
fresh `strategy_id`/`plan_id` per call by design (proven already in
`tests/integration/planning/test_strategy_to_telemetry_integration.py`), so the reproducibility case fixes both
id sources (`FixedStrategyIdSource`/`FixedPlanIdSource`) to isolate the property actually under test — everything
*else* about the outcome, byte-identical across repeats. Also re-run under two different `PYTHONHASHSEED` values
(0 and 12345): identical pass/fail result both times.

**Tests, mutation, guards, full suite.** 13 new tests in `tests/scenarios/test_benchmark_execution_control.py`.
**Mutation check: 9 of 9 caught** (inverting condition C's accept/reject branch; dropping each of
`failure_cause`/`plan_rejected_at`/`verified`/`run_outcome`/`dispatched_anything` from the telemetry-to-result
mapping; dropping D2's `selector_model_calls` wiring; removing a task class's own injected failure; removing the
reproducibility case's fixed id sources). All guard tests repo-wide: **568 passed** (unchanged — no new guard
needed; the two new files compose only already-shipped, already-guarded `eidos` code). Relevant existing suites
(`tests/scenarios/`, `tests/integration/planning/`, `tests/unit/{planning,expansion,telemetry,recording,state}/`):
**1,030 passed**, unchanged. Full default suite: **3,253 passed, 2 deselected** (was 3,240; +13, matching exactly
the 13 new tests — no existing test's outcome changed). `git status --porcelain` before committing showed only
the two new files; no V0.1–V0.9 source file was touched.

**Not implemented, explicitly deferred:** Strategy Memory, adaptive/historical strategy selection (D2 is a
selector *comparison*, never adaptive — nothing here reads or writes history across calls), MCP, agentic RAG,
Qdrant, Laya, DSPy, a telemetry database, a frontend, automatic replanning, a background mission driver, any new
`MissionEvent`, any new core contract, any semantic quality/ranking score, statistical-significance machinery,
persistent `strategy_id`, any change to `DeterministicSelector`'s or `ModelAssistedSelector`'s own contract, and
a future "Benchmark 2" for experience-informed selection (would need Strategy Memory first). The previously
flagged `ExecutionRecord` multi-plan-version gap (V0.9 Step 4) remains exactly as found — not reachable by this
benchmark, since no condition here ever produces more than one plan version in one execution.

---

## V1.0 Execution Experience / Strategy Memory — architecture accepted, Steps 1 and 2 of 7 implemented (2026-09-23)

**Research question**: "can measured execution experience from previous missions improve future strategy
selection?" Two design turns preceded any code (an inspection-and-proposal turn, then a detailed decision
revision resolving nine named open items — cold start, relevance, staleness, package boundary, guards, the
exact selection algorithm, storage, Benchmark 2, invariants) — recorded in full as **D-198**. Architecture
principle, unchanged from the brief: a **hot path** (`TaskGenome → candidates → feasibility → selection →
Strategy→Plan → validation → execution → verification`, unmodified except that selection may now optionally
consult memory) and a **cold path** (`completed execution → evaluate_experience → ExecutionExperience → Strategy
Memory → future selection`, which never runs during a mission and never destabilizes the hot path).

**Step 1** (this commit): `eidos.memory.experience` — `ExecutionExperience` (an immutable, `EidosModel`-frozen,
purely factual record: identity; `strategy_id` plus its structural shape, `strategy_stage_shapes`/
`strategy_verification` — no signature, D-021 stays untouched; task characteristics usable for relevance,
`task_required_capabilities`/`task_risk_level`/`task_autonomy_level`; every cost/outcome fact `TelemetryRecord`
already carries, copied verbatim) and `evaluate_experience(strategy, task_genome, telemetry, *, recorded_at) ->
ExecutionExperience` — a pure function, no I/O, no clock read (`recorded_at` is caller-supplied). **No quality
score, no confidence score, no strategy signature, no embeddings, no artifact text, no subjective judgment of
any kind** (D-198 ruling 1). **No `strategy_id` added to `Plan`, `MissionState`, `TelemetryRecord`,
`ExecutionRecord`, or any `MissionEvent`** — the Strategy↔execution linkage lives only inside
`ExecutionExperience` itself, made once by the caller who already holds both objects when a mission concludes
(D-198 ruling 2, extending V0.9 Step 4's own "external correlation suffices" finding one layer further).

New package `eidos.memory` (the exact slot `docs/03_architecture.md`'s own table already reserved for V1.0 — no
new decision was needed to justify its existence, only its internal shape). Depends only on `eidos.contracts`,
`eidos.planning`, `eidos.runtime`, `eidos.state`, `eidos.telemetry` — the identical dependency shape
`eidos.telemetry` itself already has, one layer further; no I/O, no clock, no randomness, no vendor name (guard
tests enforce every one of these, mirroring `test_planning_guards.py`'s own discipline exactly, scoped to the
two modules Step 1 actually built).

**Tests**: 9 behavior tests (`tests/unit/memory/test_memory_experience.py`) built against a real, hand-built log
projected by the unmodified `project` (`eidos_state_factories.verified_baseline`), covering field-for-field
mapping, strategy-shape/task-characteristic extraction, `recorded_at` purity (never derived internally), frozen/
strict/round-trip contract discipline, and — found necessary only by running mutation testing, not by
inspection — a dedicated hand-built `TelemetryRecord` with every count field given a distinct value: today's
runtime never dispatches a retry or a replan (D-170), so every *real* `TelemetryRecord` has
`retries_used == replans_used == 0`, and a field swap between them was silently undetectable against the real
baseline fixture alone. 19 guard tests (`tests/unit/memory/test_memory_guards.py`).

**Mutation check: 7 of 7 caught**, after closing the one genuine gap above (initially 6/7 — the
`retries_used`/`replans_used` swap was missed until the distinct-value fixture was added, then re-run clean).
Relevant existing suites unchanged: `tests/unit/telemetry/`+`tests/unit/planning/`+`tests/unit/state/`
**663 passed**. All guard tests repo-wide: **587 passed** (was 568; +19, exactly the new memory guards — nothing
existing changed). Full default suite: **3,281 passed, 2 deselected** (was 3,253; +28, exactly the 9 behavior +
19 guard tests this step added — no existing test's outcome changed). Re-run clean under two different
`PYTHONHASHSEED` values (0 and 98765). `git status --porcelain` before committing showed only
`src/eidos/memory/` and `tests/unit/memory/` — nothing in any existing package touched.

**Step 2** (this commit): `eidos.memory.relevance` — no new `decisions.md` entry needed; D-198 already specified
this exactly. Two separate relevance questions, two separate pure functions, never conflated: **task relevance**
(`TaskRelevance` — a closed, three-member `StrEnum`, `SAME`/`SIMILAR`/`IRRELEVANT`, never a scalar; `task_relevance(experience,
task_genome)`; `relevant_experience(candidates, task_genome, history)`, a plain filter over `history` in its own
order — `SAME` requires an exact match of required capabilities as a set, risk level and autonomy level;
`SIMILAR` keeps risk/autonomy exact and loosens only capability comparison to a non-empty intersection; any
risk/autonomy mismatch is `IRRELEVANT` regardless of capability overlap, no cross-level transfer, ever; no
staleness/recency/decay) and **strategy relevance** (`experience_for(candidate, task_relevant)` — exact
tuple-of-tuples structural shape matching plus verification-posture equality; `StrategyId` is never compared,
since it is fresh every generation round, D-182). `relevant_experience` only filters — proven by a dedicated
guard (`relevance.py` never mentions `structural_cost`/`DeterministicSelector`/`ExperienceInformedSelector`/
`SelectorChoice`/"tier") that it computes nothing resembling the Step 4 selection algorithm.

**`relevant_experience`'s own `candidates` parameter is accepted but not read** inside this step — kept only for
signature symmetry with the eventual `Selector.select(candidates, task_genome)` call site (Step 4, not built
yet); flagged explicitly, not hidden, since a parameter with no effect on its own function's behavior is worth
noting plainly.

**Tests**: 17 behavior tests (`tests/unit/memory/test_memory_relevance.py`), covering exact-same-shape, capability
overlap, no-overlap, risk mismatch, autonomy mismatch (each independently — both proven irrelevant even with
identical capabilities), duplicate-capability set handling, irrelevant-history exclusion, insertion-order
preservation, exact/different/verification-mismatched strategy-shape matching, fresh-`StrategyId` insensitivity,
empty-history, multi-candidate partitioning, and purity/no-mutation on both functions. 2 new guard tests
(`TaskRelevance`'s exact three-member vocabulary pinned; the selection-algorithm-absence check above) plus the
existing parametrized guards extending automatically to the new module (module-list, forbidden-imports,
dependency-direction, vendor-name, forbidden-concept-word, no-IO-builtin checks) — **21 guard tests total for
this step's own addition**. Two genuine docstring false positives, the same established class this project has
hit every time a guard's forbidden word appears in a module's own explanatory prose (not a call): "RAG"/
"embeddings" in the module docstrings describing what task relevance deliberately excludes, and "tiers" in this
step's own new prose colliding with its own new selection-algorithm-absence guard's forbidden word "tier" —
fixed by rewording only (no logic change, confirmed by re-running the exact same mutation suite unchanged
afterward).

**Mutation check: 7 of 7 caught** (dropping either half of the risk/autonomy gate independently; inverting the
gate from OR- to AND-mismatch; swapping which branch returns `SAME` vs `SIMILAR`; inverting
`relevant_experience`'s own filter to keep only irrelevant records; dropping either half of `experience_for`'s
shape/verification match independently). Full memory suite: 54 passed (was 28; +26 — 17 behavior + 9 guard,
including the parametrized extensions to `relevance.py`). Relevant existing suites unchanged:
`tests/unit/telemetry/`+`tests/unit/planning/`+`tests/unit/state/` 663 passed. All guard tests repo-wide: 596
passed (was 587; +9). Full default suite: **3,307 passed, 2 deselected** (was 3,281; +26, exactly this step's
own 17 behavior + 9 guard tests — no existing test's outcome changed). Re-run clean under two different
`PYTHONHASHSEED` values (0 and 54321). `git status --porcelain` before committing showed
only `src/eidos/memory/relevance.py` (new), `tests/unit/memory/test_memory_relevance.py` (new),
`src/eidos/memory/__init__.py` (extended exports) and `tests/unit/memory/test_memory_guards.py` (extended for
Step 2) — nothing in any existing package touched.

**Not implemented, explicitly deferred to their own steps**: `ExperienceStore`/the JSONL
adapter (Step 3), `ExperienceInformedSelector` (Step 4), the selector-guard revisions (Step 5), the end-to-end
integration test (Step 6), Benchmark 2 (Step 7) — see D-198 for the full, already-approved design of each. MCP,
Agentic RAG, Qdrant, Laya, DSPy, reinforcement learning, fine-tuning, embeddings, an LLM judge, automatic
replanning, a background driver, a frontend, a production database, and any new `MissionEvent` all stay
explicitly out of scope for all of V1.0, not only this step.

---

## Intentionally not built yet

Per CLAUDE.md §3, a package is created only when the milestone that fills it begins. These
architectural components are **documented in `docs/03_architecture.md` but not scaffolded** (V0.4's four packages, V0.5's `state/` and `recording/`, V0.6's `a2a/`, and V0.7 Step 2's `planning/` — the `Strategy` data contracts only, no generator/selector yet — now exist and are no longer listed):

| Component | Arrives at |
|---|---|
| `policy/` — governance, autonomy, budgets | V1.2 engine (V0.2 has only a `NOT_APPLICABLE` stage in `validation/` — D-110) |
| `telemetry/` — structured events, metrics | V0.9 |
| `memory/` — strategy and execution memory | V1.0 |
| `evaluation/` — evaluation harness, experiments | V1.1 |
| `mcp/` | **Deferred, no milestone assigned (D-184)** — not part of the V0.7–V1.0 strategy-intelligence sequence; assigned only when a concrete requirement or benchmark needs it |
| `rag/` | **Deferred, no milestone assigned (D-184)** — see `mcp/`'s row |
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
| 2026-09-23 | **V1.0 Step 2 implemented: `eidos.memory.relevance` (`TaskRelevance`, `task_relevance`, `relevant_experience`, `experience_for`)** | No new `decisions.md` entry needed — D-198 already specified this step's own rules exactly. Two separate, pure, deterministic relevance questions: task relevance (`TaskRelevance`, a closed three-member `StrEnum` — `SAME` requires exact required-capabilities-as-a-set, risk-level and autonomy-level match; `SIMILAR` keeps risk/autonomy exact and loosens only capability comparison to a non-empty intersection; any risk/autonomy mismatch is `IRRELEVANT` regardless of capability overlap, no cross-level transfer, ever; `relevant_experience` is a plain filter over `history`, preserving its own order, never ranking) and strategy relevance (`experience_for` — exact tuple-of-tuples structural shape plus verification-posture matching; `StrategyId` never compared, fresh every generation round, D-182). `relevant_experience`'s own `candidates` parameter is accepted but not read in this step — kept for signature symmetry with the eventual `Selector.select(candidates, task_genome)` call site (Step 4), flagged explicitly rather than silently included. 17 behavior tests (`tests/unit/memory/test_memory_relevance.py`) covering exact-same-shape, capability overlap, no overlap, risk mismatch, autonomy mismatch (each independently), duplicate-capability set handling, irrelevant-history exclusion, insertion-order preservation, exact/different/verification-mismatched strategy-shape matching, fresh-`StrategyId` insensitivity, empty history, multi-candidate partitioning, and purity/no-mutation. Two genuine docstring false positives, the same established class hit every prior step: "RAG"/"embeddings" named literally in prose describing what relevance deliberately excludes, and this step's own new selection-algorithm-absence guard's forbidden word "tier" colliding with this step's own prose describing three relevance "tiers" — both fixed by rewording only, confirmed by re-running the identical mutation suite unchanged afterward. 2 new guard tests (`TaskRelevance`'s exact three-member vocabulary pinned; `relevance.py` proven, by absence, to never mention `structural_cost`/`DeterministicSelector`/`ExperienceInformedSelector`/`SelectorChoice`/"tier" — the Step 4 selection algorithm this step must never anticipate). Mutation check: 7 of 7 caught (dropping either half of the risk/autonomy gate independently; inverting the gate from OR- to AND-mismatch; swapping which branch returns `SAME` vs `SIMILAR`; inverting `relevant_experience`'s own filter to keep only irrelevant records; dropping either half of `experience_for`'s shape/verification match independently). Full memory suite: 54 passed (was 28; +26). Relevant existing suites unchanged: `tests/unit/telemetry/`+`tests/unit/planning/`+`tests/unit/state/` 663 passed. All guard tests repo-wide: 596 passed (was 587; +9). Full default suite: 3,307 passed, 2 deselected (was 3,281; +26, exactly this step's own tests). Re-run clean under two different `PYTHONHASHSEED` values. `git status --porcelain` before committing showed only `src/eidos/memory/relevance.py` (new), `tests/unit/memory/test_memory_relevance.py` (new), and `src/eidos/memory/__init__.py`/`tests/unit/memory/test_memory_guards.py` (extended) — nothing in any existing package touched. Committed as one focused commit; not pushed. Five steps remain (storage, the selector, guard revisions, an end-to-end integration test, Benchmark 2) — Step 3 not started. |
| 2026-09-23 | **V1.0 Step 1 implemented: `eidos.memory.experience` (`ExecutionExperience`, `evaluate_experience`)** | Two design turns preceded any code: an inspection-and-proposal turn (found no quality/confidence/persistence/signature mechanism exists anywhere to build on — D-015/D-016/D-017/D-021 all confirmed still Open; found the exact "adapter needs a dependency the core layer can't have" precedent `eidos.selectors`/`ModelAssistedSelector` already set applies identically to an experience-informed selector needing `eidos.memory`; found `tests/unit/selectors/test_selectors_guards.py` already, by name, forbids the string `"StrategyMemory"` — a genuine, correctly-written-at-the-time guard this work must now deliberately, not silently, revise), then a decision revision resolving nine named open items (cold start, relevance, staleness, package boundary, guards, the exact lexicographic selection algorithm, storage, Benchmark 2, invariants) — recorded in full as **D-198**. New package `eidos.memory` (the exact slot `docs/03_architecture.md`'s own table already reserved for V1.0 — no new decision needed to justify its existence, only its internal shape). Step 1 only: `ExecutionExperience` — an immutable, `EidosModel`-frozen, purely factual record (identity; `strategy_id` plus structural shape, no signature; task characteristics usable for relevance; every cost/outcome fact `TelemetryRecord` already carries, copied verbatim) — and `evaluate_experience(strategy, task_genome, telemetry, *, recorded_at) -> ExecutionExperience`, a pure function, no I/O, no clock read (`recorded_at` is caller-supplied). No quality/confidence score, no strategy signature, no embeddings, no subjective judgment. No `strategy_id` added to `Plan`/`MissionState`/`TelemetryRecord`/`ExecutionRecord`/any `MissionEvent` — the linkage lives only inside `ExecutionExperience`, made once by the caller who already holds both objects (extends V0.9 Step 4's own "external correlation suffices" finding one layer further). Depends only on `eidos.contracts`/`eidos.planning`/`eidos.runtime`/`eidos.state`/`eidos.telemetry` — the identical shape `eidos.telemetry` itself already has, one layer further; no I/O/clock/randomness/vendor name (guard-enforced). 9 behavior tests (`tests/unit/memory/test_memory_experience.py`), built against a real hand-built log projected by the unmodified `project`. Mutation testing found a genuine gap, not assumed: today's runtime never dispatches a retry or a replan (D-170), so every *real* `TelemetryRecord` has `retries_used == replans_used == 0`, and a field swap between them was silently undetectable against the real baseline fixture alone (6/7 caught on the first pass) — closed by adding a dedicated hand-built `TelemetryRecord` with every count field given a distinct value, then re-run clean (**7/7 caught**). 19 guard tests (`tests/unit/memory/test_memory_guards.py`), mirroring `test_planning_guards.py`'s own discipline, scoped to the two modules this step actually built. Relevant existing suites unchanged: `tests/unit/telemetry/`+`tests/unit/planning/`+`tests/unit/state/` 663 passed. All guard tests repo-wide: 587 passed (was 568; +19). Full default suite: 3,281 passed, 2 deselected (was 3,253; +28, exactly this step's own new tests). Re-run clean under two different `PYTHONHASHSEED` values. `git status --porcelain` before committing showed only `src/eidos/memory/` and `tests/unit/memory/`. Committed as one focused commit; not pushed. Six steps remain (relevance, storage, the selector, guard revisions, an end-to-end integration test, Benchmark 2), each its own separately-approved step. *(Step 2 has since been implemented — see the row above.)* |
| 2026-09-23 | **Benchmark 1 implemented: the first controlled EIDOS benchmark (deliberately unassigned a milestone number, D-196/D-197)** | Two prior design turns (no code): inspection covering the research question, baselines, task classes, metrics, repetition tiers, confounders, cold/hot-path separation, and the multi-plan-version `ExecutionRecord` gap (found not to block this benchmark, since no replan loop exists to reach it); then a second, stronger design turn with the owner's 13 final decisions on conditions, task classes, metrics and scope. Inspected the repository first (per explicit instruction) to find the location, not assume it: no `scripts/`/`tools/`/`benchmarks/` directory exists anywhere, and `progress.md`'s own table already reserves `evaluation/` for V1.1 specifically, so neither `src/eidos/evaluation` nor any new top-level directory could be created — recorded as **D-197**. Built one reusable harness, `tests/support/eidos_benchmark_harness.py` (pythonpath'd, uncollected, mirroring every other `eidos_*_factories.py` module), and the assertions/case tables in `tests/scenarios/test_benchmark_execution_control.py` — already a collected `testpaths` entry, already scoped by CLAUDE.md §6 to almost exactly this benchmark's own task classes. Four conditions, composing only already-shipped `eidos` code: **A** (direct `WorkAgent` call, bypassing Plan/validation/compiler/runtime/EventLog/Telemetry entirely), **B** (a hand-authored Plan through the existing, unmodified execution/recording/telemetry chain), **C** (a model's Plan-DSL JSON through the existing, unmodified `validate_plan_json` ingress — a rejected plan captured from its own report and never dispatched), **D1/D2** (the proven Strategy pipeline with `DeterministicSelector`/`ModelAssistedSelector`, both over the identical feasible candidate set — a selector comparison, never adaptive). Five task classes, each carrying only the failure sub-cases that make semantic sense for its own topology (sequential reasoning, parallel independent subtasks, verification-heavy, constrained/failure-prone, invalid-plan interception); condition D never appears in the invalid-plan class, since `expand_strategy` only ever produces a `Plan` `validate_plan` already accepts (D-183) — a finding, not a gap. **A genuine finding surfaced by running the benchmark, not by inspection alone:** a `VERIFY` failure does not produce `MISSION_COMPLETED` with `verified=false` as an earlier design pass assumed — a failed `VERIFY` node is itself not `SUCCEEDED`, so the whole run is `FAILED` with cause `VERIFICATION_FAILED`, never reaching `MISSION_COMPLETED` at all (`COMPLETED`/`verified=false` is reserved for a finished run with no `VERIFY` step at all). Cold path (candidate generation/feasibility/selection/expansion) and hot path (validation onward) are timed by the runner's own `time.perf_counter`, since `record_baseline`'s first event fires only after the cold path has already finished — `TelemetryRecord` never sees it; D2's own selector model call, made during the cold path, is likewise invisible to `TelemetryRecord.model_call_count` and is recovered separately as `selector_model_calls`. Metrics reported as a vector, never combined (D-188's own discipline, one layer up) — `pytest -s -v` on the test file is the report. Reproducibility mirrors `test_v03_determinism.py`'s own hash-of-serialized-output technique; D1/D2's genuinely fresh `strategy_id`/`plan_id` per call are fixed for that one case only, to isolate the property under test; also re-run clean under two different `PYTHONHASHSEED` values. 13 new tests. Mutation check: 9 of 9 caught (inverting C's accept/reject branch; dropping each of five fields from the telemetry-to-result mapping; dropping D2's selector-call wiring; removing an injected failure; removing the reproducibility case's fixed id sources). All guard tests repo-wide: 568 passed (unchanged — the two new files compose only already-guarded `eidos` code, no new guard needed). Relevant existing suites (`tests/scenarios/`, `tests/integration/planning/`, `tests/unit/{planning,expansion,telemetry,recording,state}/`): 1,030 passed, unchanged. Full default suite: 3,253 passed, 2 deselected (was 3,240; +13, exactly the new tests — no existing test's outcome changed). `git status --porcelain` before committing showed only the two new files. No core contract, `MissionEvent`, or `src/eidos` package added or changed. Strategy Memory, adaptive/historical selection, MCP, RAG, a telemetry database, automatic replanning, a background driver, persistent `strategy_id`, any selector-contract change, and a future "Benchmark 2" for experience-informed selection all stay explicitly deferred. Committed as one focused commit; not pushed. |
| 2026-09-23 | **V0.9 Step 4 implemented: two evidence gaps closed on `TelemetryRecord`** | Inspected first (a separate turn, no code): asked whether the execution/event/telemetry chain preserves enough evidence for a future controlled benchmark. Checked `TelemetryRecord`'s own fields directly against `MissionState`'s six budget counters and found `execution_time_used_ms` missing entirely — an implementation gap against `TelemetryRecord`'s own Step 2 docstring promise ("every field is copied or derived from `ExecutionRecord`"), not a deliberate choice. Also found no plan-rejection information at all, even though `ExecutionRecord.plan_rejected_at` already computes it — "invalid-plan interception" could not be read from `TelemetryRecord` in any form. Separately determined persistent `Strategy`→`Plan` lineage is **not** required for the benchmark: the same caller that selects a `Strategy` already holds it in scope when it later expands and projects, so external, in-process correlation suffices — no `strategy_id` was proposed. Implemented exactly the two fields proposed, both pure copies from `ExecutionRecord`: `execution_time_used_ms: int` and `plan_rejected_at: PlanRejectionStage | None` — deliberately not `plan_rejection_reasons`, keeping `TelemetryRecord` flat. `execution_time_used_ms` is never combined with `mission_wall_clock_ms` (D-158 item 4); a new test builds a genuinely parallel two-step topology and proves `execution_time_used_ms` (12,005 ms, both nodes' own recorded durations summed) exceeds `mission_wall_clock_ms` (9,000 ms, the event-log span) — the "fast because parallel vs. fast because cheap" distinction the gap analysis named. 6 tests added or extended in `tests/unit/telemetry/test_telemetry_project.py` (37 total, was 34); existing JSONL round-trip/determinism tests needed no changes (they already compare whole objects). All 19 existing guard tests pass unchanged. No `decisions.md` entry: both additions complete an already-Accepted decision's own stated intent (D-159 item 1), not a new one; `EventRecord`/`MissionState`/`ExecutionRecord`/the reducer/`eidos.recording` all confirmed untouched by diff — no implementation contradiction found. Mutation check: 2 of 2 caught (the two fields swapped for each other; the rejection assignment dropped). Relevant existing suites unchanged: `tests/unit/state/`+`tests/unit/recording/` 508 passed. All guard tests repo-wide: 568 passed (unchanged). Full default suite: 3,240 passed, 2 deselected (was 3,237; +3). Committed as one focused commit; not pushed. No further V0.9 step started. |
| 2026-09-23 | **V0.9 Step 3 implemented: the full live chain connected** | Inspected first (no code): grepped every caller of `expand_strategy` and found only its own module and its own unit tests — the entire gap was one missing pair of real id sources. `generate_candidate_strategies` and `expand_strategy` each need an injected id source (`StrategyIdSource`, `PlanIdSource`); only `Protocol` definitions and fixed-value test doubles existed for either, and both Protocols' own docstrings already named where a real one belongs — "exactly as a caller supplies a real `IdSource` to `eidos.recording` today." Everything downstream (`run_baseline`, `record_baseline`, `project`) already composes with any `Plan` regardless of origin (D-178). D-183 already governs the exact ordering connected; nothing reopened. Added **`UuidStrategyIds`**/**`UuidPlanIds`** to `eidos.recording.ports`, mirroring `UuidEventIds` exactly (frozen, slotted, one `uuid.uuid4()` method each) — placed there because `eidos.recording` is already the project's one home for a real Clock/IdSource adapter (D-158 item 3), and the two deterministic core layers that need them may not draw randomness themselves; no new Protocol, no new abstraction, no new `eidos.recording` dependency on `eidos.planning`/`eidos.expansion` (only the plain `StrategyId`/`PlanId` types from `eidos.contracts`). One new integration test, `tests/integration/planning/test_strategy_to_telemetry_integration.py`: a real `TaskGenome` (research/cost/security) → `RuleBasedCandidateGenerator` (3 real candidates, real `StrategyId`s) → `DeterministicSelector`+`select_strategy` (genuinely invoked, choosing among real candidates) → `expand_strategy` (real `PlanId`, tenant/mission identity and stage topology verified against the selected `Strategy` itself) → `validate_plan` (accepted) → `record_baseline` over real V0.4 agents and a scripted model (every node succeeds, verified) → `project` (a `TelemetryRecord` whose identity matches the executed mission exactly). A second test proves two independent passes never repeat a `StrategyId`/`PlanId`. One pre-existing guard (V0.8 Step 6's own `test_this_integration_suite_never_imports_the_plan_or_execution_layer`) correctly flagged a genuine scope change, not a false positive — this step's own new file exists specifically to compile and execute a real Plan, the opposite of what that guard checked for every file in the directory; fixed by scoping the guard to the four files it was actually written for. Mutation check: 2 of 2 caught (each id source returning a fixed id instead of drawing a fresh one). Relevant existing suites unchanged: planning 224, expansion 43, recording 106, state 402, telemetry 34. All guard tests repo-wide: 568 passed (unchanged — no new guard test needed; the existing `eidos.recording` guards already cover the addition). Full default suite: 3,237 passed, 2 deselected (was 3,235; +2). No V0.1–V0.8 contract touched (confirmed by diff: only `eidos.recording` and one test guard file changed) and no implementation contradiction found. No new `decisions.md` entry. Committed as one focused commit; not pushed. *(Step 4 has since closed two evidence gaps — see the row above.)* |
| 2026-09-23 | **V0.9 Step 2 implemented: `eidos.telemetry.project`** | Step 1 (design only, 2026-09-23) found `eidos.state.execution_record`'s own module docstring already states the Event-Log/`ExecutionRecord`/Telemetry boundary verbatim ("not the telemetry platform (V0.9)," D-159 item 3, already Accepted) and that `docs/11_evaluation.md` (bootstrap-era, DERIVED) independently confirms it and already reserves `eidos.telemetry`/`eidos.memory`/`eidos.evaluation` as three separate future packages. Inventory: most of handoff §33's field list is already recorded or cleanly derivable; the model identifier flows through `RecordingModel.complete()` but is never captured; `strategy_id` cannot be captured at all yet since no mission driver ever produces an execution from a `Strategy`. Both flagged as future, narrow, separate extension points, neither built. No new decision needed: the package boundary was already anticipated in `docs/03_architecture.md`'s own table, and D-159 already fixed the boundary this step builds on. Implemented `project(records: Iterable[EventRecord]) -> TelemetryRecord \| ReplayRejection` — pure, deterministic, composes `execution_record` rather than re-folding events; no filesystem loader was built, since nothing in the approved scope needed one. Fields: identity, the six existing budget counters, mission/run outcome, verification status, eight per-`NodeStatus` counts, model-call count, a protocol-neutral `remote_task_count` (not `a2a_task_count` — the field never needs to name which remote-execution boundary produced a submission), event bounds, and a deliberately signed `mission_wall_clock_ms` (never clamped to zero, since `ExecutionRecord`'s own bounds are documented as "never an ordering" — clamping would hide a real anomaly, D-158 item 4). No model identifier, no `strategy_id`, no quality/confidence/ranking field, no new `MissionEvent` type, no durable store, no benchmark logic — exactly as scoped. Two docstring/guard false positives (the literal word "A2A" in explanatory prose; the transitive-load subprocess check wrongly forbidding the already-approved `eidos.compiler`/`.validation` load via `eidos.runtime`) fixed by rewording plus a genuine field rename (`a2a_task_count` → `remote_task_count`, protocol-neutral on its own merits) and by correcting the check to exclude the approved transitive load — the identical class of finding V0.8 Step 6 made for `eidos.agents`. 34 new tests in `tests/unit/telemetry/` (15 behavior, 19 guards). Mutation check: 7 of 7 caught (status-counting collapse, remote-task count counting everything, wall-clock span from one bound twice, missing ms conversion, `tokens_used` substituted, `verified` hardcoded false, `ReplayRejection` propagation removed). Existing `tests/unit/state/`+`tests/unit/recording/` suites unchanged: 508 passed. All guard tests repo-wide: 568 passed (was 549). Full default suite: 3,235 passed, 2 deselected (was 3,201; +34). No source outside `src/eidos/telemetry/`/`tests/unit/telemetry/` touched. No new `decisions.md` entry. Committed as one focused commit; not pushed. *(Step 3 has since connected this projection to a real, live mission — see the row above.)* |
| 2026-09-23 | **D-196 accepted: "V0.9" milestone-number collision resolved** | Before starting any further Strategy-to-Plan work, resolved D-196 exactly as proposed and approved: **V0.9 stays Telemetry**, unchanged (14+ pre-existing references across `progress.md`/`decisions.md`/`docs/03_architecture.md`, dating to the project's earliest days, none of them touched); **the future controlled benchmark stays unassigned a milestone number**, deferred exactly like MCP/RAG already are under D-184, until a concrete requirement fixes its actual slot; **the Strategy-to-Plan expansion design and implementation, first logged this session as "V0.9 Step 1/2," are renamed to `V0.8 Step 7` and `V0.8 Step 8`** — folded into V0.8 Strategy Selection's own step sequence, matching D-183's own pre-existing, twice-repeated "Strategy-to-Plan expansion (V0.8+, not built)" phrasing exactly. This also closes the *other* half of the gap D-184 itself found and left open at V0.7 Step 1 (whether V0.9 stops meaning Telemetry) — D-184's own text and ruling are untouched, only extended. Documentation-only: **D-194/D-195's architectural content is unchanged**, only their own "Source"/"Affects" cross-references were corrected from "V0.9 Step 1/2" to "V0.8 Step 7/8"; D-129 stays Open, not closed. Edits: `decisions.md` (D-196 rewritten Open→Accepted; D-194/D-195 cross-references corrected; a table-splitting formatting defect from the prior turn's D-196 insertion was also fixed — one deferral-table row had been accidentally stranded outside its own table, now restored), `progress.md` (top milestone line, current-state paragraph, milestone ladder — the standalone "V0.9 Strategy-to-Plan Expansion" row removed, V0.8's row extended, the ladder note rewritten to state the resolution, the "V0.9 Telemetry" row's stale "number collision" annotation removed; the "## V0.9 Strategy-to-Plan Expansion" section folded into "## V0.8 Strategy Selection" as Steps 7–8, internal "Step 1"/"Step 2" self-references corrected to "Step 7"/"Step 8"; this session-log table), `README.md` (status line, the V0.9 paragraph folded into V0.8's, the collision note rewritten as a resolution note), `docs/03_architecture.md` (the D-194/D-195 blockquote and the `eidos.expansion` package-table row's milestone column corrected). No source code, test, or git commit history touched — commit hashes and messages for `df35e1f`/`9c2d8b9`/`6f191c8` are unchanged and unrenamed. No new implementation started. |
| 2026-09-23 | **V0.8 Step 8 implemented: `expand_strategy` (`eidos.expansion`)** *(first logged as "V0.9 Step 2"; renamed by D-196 — see the row above)* | Step 7 (design only, 2026-09-23) found D-179 already answers the dependency mapping verbatim ("stage i+1 depends on the whole of stage i") and that `eidos.planning`'s own existing guard forbids `StepId`, so the expander cannot live there; proposed, and this step formally recorded, **D-194** (a new sibling core layer, `eidos.expansion`, depending only on `eidos.contracts` and `eidos.planning`) and **D-195** (`FINAL` verification depends on exactly the final stage's own step ids, never every agent step — matching the real V0.4 baseline precedent and how `eidos.agents.verification` actually reads a `VerifyNode`'s predecessors). Implemented `expand.py` (`PlanIdSource` Protocol; `expand_strategy(strategy, *, ids) -> Plan`): one capability occurrence → one `AgentStep`, never deduplicated; a stage's steps fan out from the complete set of the preceding stage; `NONE` emits no `VERIFY`, `FINAL` emits exactly one depending on the final stage; empty stages produce an empty Plan regardless of posture. `step_id` is a pure, deterministic derivation from `(stage_index, position, capability)` (string-backed, D-092-exempt); `plan_id` is drawn only from the injected `PlanIdSource` (UUID-backed, no exemption) — mirrors `StrategyIdSource` exactly. Two docstring/guard false positives (the established class: `check_feasibility` named literally in explanatory prose; the transitive-load subprocess check wrongly forbidding the already-approved `eidos.validation` load) fixed the same two ways this project always fixes them — reworded, and the check corrected to exclude the approved transitive load, mirroring `test_planning_guards.py`'s own identical exclusion. 43 new tests in `tests/unit/expansion/` (23 behavior — both worked examples from Step 7 verbatim, empty/duplicate/multi-stage cases, a representative Plan passing full V0.2 validation and V0.3 compilation; 3 hash-seed determinism; 17 guards, including a sanity-checked no-feasibility-call guard and a sanity-checked transitive-load check). Mutation check: 7 of 7 caught (step-id collision, self-referencing stage, VERIFY over-scoped to every agent step, FINAL/NONE branch inverted, `plan_id`/`tenant_id` swapped for the wrong source field, the empty-stage guard removed). Full planning suite unchanged **224 passed**; all guard tests repo-wide **549 passed**; full default suite **3,201 passed, 2 deselected**. `eidos.planning`/`eidos.selectors` source confirmed untouched by diff. D-129 stays Open, not closed. **D-196 recorded (Open at the time)**: "V0.9" then had three meanings on record (Telemetry, the benchmark, Strategy-to-Plan Expansion) — found and reported, nothing renamed or reordered to resolve it yet. Committed as one focused commit; not pushed. *(D-196 has since been Accepted and this step relabeled V0.8 Step 8 — see the row above.)* |
| 2026-09-23 | **V0.8 Step 6 implemented: selection integration + deterministic end-to-end evaluation** | Inspected first: `CandidateGenerationResult.candidates` was already exactly the `tuple[Strategy, ...]` `select_strategy` takes, so no new wiring or abstraction was built — confirmed by zero diff under `src/eidos/planning/` or `src/eidos/selectors/` for the entire step. New `tests/integration/planning/` (33 tests): the full deterministic pipeline (`TaskGenome` → `RuleBasedCandidateGenerator` → feasibility → `DeterministicSelector`) across zero/one/two/three-capability genomes and limits that reject one or every candidate; the same pipeline through `ModelAssistedSelector` with a `ScriptedModel`, including prompt-injection-like candidate text that only ever resolves through the closed label set; a factual (never ranked) comparison of both selectors over the identical candidate set; combined import-graph boundary checks. One genuine, harmless finding, checked not assumed: `eidos.agents` itself already, legitimately, transitively loads `eidos.compiler`/`.runtime`/`.capabilities` for its own pre-existing `WorkAgent` concerns — the guard was corrected to assert what actually matters, not weakened, then sanity-checked against a manufactured `eidos.recording` import caught by both the new integration guard and the existing Step 5 unit guard simultaneously. No new `decisions.md` entry — everything needed was already a consequence of D-186–D-193. Full planning suite unchanged **224 passed**; all guard tests unchanged **532 passed**; full default suite **3,158 passed, 2 deselected** (was 3,125; +33). Committed as one focused commit; not pushed. *(Step 5 was implemented in the prior commit; Step 6 is this row's own work.)* |
| 2026-09-23 | **V0.8 Step 5 implemented: the model-assisted `Selector` (`eidos.selectors.ModelAssistedSelector`)** | Step 4 (design only, 2026-09-22) proposed D-190 to D-193; this step formally recorded them in `decisions.md` (150 Accepted, 39 Open, 5 Deferred) and implemented exactly what they specify. New sibling adapter package **`eidos.selectors`** (not inside `eidos.planning`, which cannot import `eidos.agents`/`ModelPort` — confirmed by the package's own existing docstring, not assumed), one module `model_assisted.py`, chosen by explicit analogy to `eidos.providers`/`eidos.backends`: each adapts an external dependency to a Protocol the core layer defines, from outside the core layer. `ModelAssistedSelector` implements the existing `Selector` Protocol unchanged. Candidates are labelled `CANDIDATE_1..N` strictly by tuple position (D-191) — never the raw `StrategyId`; the model sees only `TaskGenome.goal` plus each candidate's `stages`/`verification`/`rationale` (D-190), serialized as fixed-field-order JSON. The model's answer is parsed by a regex identical to `eidos.agents.base`'s own `_CITATION` convention, reused for this closed vocabulary (D-192): exactly one distinct, resolvable bracketed label succeeds; zero, 2+, or an out-of-set label are all `MALFORMED_CHOICE`; natural-language answers are never parsed. `ModelFailure` maps onto the existing three-member `SelectorFailureKind` with no new member (D-193); no automatic fallback to `DeterministicSelector` exists anywhere, proven by a dedicated, sanity-checked guard. Five prompt-injection tests demonstrate the parser/membership boundary — not the model — is what rejects an out-of-set or malformed answer, including a `ScriptedModel` explicitly scripted to answer with an injected out-of-set label. Two docstring false positives (the new guards flagged their own explanatory prose naming `DeterministicSelector`/`Laya`/"telemetry" literally) fixed by rewording only, the same class already seen in V0.7 Step 4 and V0.8 Step 3. 71 new tests in `tests/unit/selectors/`; `test_planning_guards.py` strengthened (not weakened) with two one-line additions guarding the new package name. Mutation check: 7 of 7 caught on the first pass (label-index, ordering, parser cardinality, unknown-label fallback, failure-mapping, `StrategyId` exposure, silent-fallback). Full planning suite unchanged at **224 passed**; all guard tests repo-wide **532 passed**; full default suite **3,125 passed, 2 deselected**. All of V0.7 and V0.8 Steps 2–3 confirmed untouched by diff. Committed as one focused commit; not pushed. *(Step 6 has since run a deterministic selection-integration suite — see the row above.)* |
| 2026-09-23 | **V0.8 Step 3: boundary-hardening audit (no contract change)** | Checked all eleven stated selection-boundary semantics against what Step 2 already enforces (by type, by implementation, or by `SelectionResult`'s own cross-field validator). **Conclusion: the Step 2 boundary was already sufficient for all eleven** — nothing needed a contract change, so no new decision was proposed. Two narrow gaps found and closed with new static guard tests (nothing pinned, though true by inspection, that `selector.py`/`selection.py` never call or re-run feasibility; nothing pinned that `eidos.planning.__all__` exports exactly what the package's own submodule imports intend). **Both guards immediately caught real, harmless issues**, verified before being trusted: the feasibility-independence guard flagged its own module docstrings quoting the feasibility symbol names in explanatory prose (the same false-positive class Step 4's `feasibility.py` guard hit; fixed the same way — reworded to descriptive prose, zero logic changed, confirmed by diff); the exports guard was sanity-checked by deliberately breaking `__all__` and confirming the failure, then restoring it; the feasibility-independence guard was separately sanity-checked by inserting a fake call to the feasibility gate and confirming it was caught, then reverting. No gap found in `SelectionResult`'s own validator — its non-`SELECTED` branch has no per-member logic, so Step 2's one representative negative test already covers all three non-`SELECTED` outcomes; no redundant tests were added. 2 new guard tests, 2 docstring-only rewordings (no logic change). No new non-trivial branch existed to mutation-test; both new guards were instead verified by direct, deliberate-violation checks. Full planning suite **224 passed**. Full default suite **3,054 passed, 2 deselected**. `strategy.py`/`generator.py`/`pipeline.py`/`feasibility.py`/`results.py`/`__init__.py` confirmed untouched by diff. No new `decisions.md` entry. Committed as one focused commit; not pushed. *(Step 4 has since run as a design-only step, and Step 5 has since implemented the model-assisted Selector it proposed — see the row above.)* |
| 2026-09-23 | **V0.8 Step 2 implemented: the Selector contracts and orchestration boundary (`Selector`, `DeterministicSelector`, `select_strategy`)** | V0.8 Step 1 (design only, 2026-09-22) proposed D-186 to D-189; this step formally recorded them in `decisions.md` (146 Accepted, 39 Open, 5 Deferred) and implemented exactly what they specify, no more. New `eidos.planning.selector` (`structural_cost` — a tuple, never a scalar; `SelectedCandidate`; `SelectorFailureKind`, three members, deliberately narrower than `ModelFailureKind` since `eidos.planning` cannot import `eidos.agents`; `SelectorFailure`; the `Selector` protocol; `DeterministicSelector`, choosing minimum `structural_cost` via `min()`'s own tie-stability) and `eidos.planning.selection` (`select_strategy`: zero candidates → `NO_FEASIBLE_CANDIDATES` with no selector call; exactly one → selected directly, no selector call; otherwise the selector is invoked and its claim is checked against the real candidate tuple by `strategy_id` — a match returns the exact existing object, never a copy; no match is `INVALID_CANDIDATE_RETURNED`; a failure is `SELECTOR_FAILED`, message preserved, never retried). `SelectionOutcome`/`SelectionResult` added to the existing `results.py`, with a cross-field validator mirroring `eidos.state.reducer.ReduceResult`'s own "unconstructible if mislabelled" rule. `check_feasibility` is deliberately not re-run at this boundary — every candidate is already admissible by construction. Two things were checked during implementation, not assumed, both confirming the approved design needed no change: `SelectorFailureKind` cannot reuse `ModelFailureKind` (architecturally impossible, not just undesirable — the existing core-layer guard already forbids importing `eidos.agents`); duplicate `StrategyId`s within one candidate tuple resolve deterministically via Python's own `next()`-first-match, so no new rejection rule was invented, only pinned by two dedicated tests. `SelectorFailure.message` gained `Field(min_length=1)`, matching `ModelFailure`'s own established convention. 66 new tests (26 in `test_planning_selector.py`, 25 in `test_planning_selection.py`, 15 guard tests updated/added — including `litellm`/`rag` added to the vendor-name list). Mutation check: 10 of 10 caught on the first pass. Full default suite **3,052 passed, 2 deselected**. Committed as one focused commit; not pushed. *(Step 3 has since run a boundary-hardening audit — see the row above.)* |
| 2026-09-22 | **V0.7 closed as scoped** | The owner confirmed: *"V0.7 is closed as scoped."* No additional gate was set beyond the close-out review Step 5 already prepared (all deliverables built, all exclusions confirmed absent, D-183/D-184/D-185 ruled on) — verified once more before recording: `strategy.py`/`feasibility.py` unchanged since `b1e6702`; focused planning suite **156 passed**; the 48 static guard tests **all green** (no forbidden dependency, no Plan-validator call, no vendor/model name, no `AgentId`, no wall-clock/randomness); full default suite **2,986 passed, 2 deselected**, identical to Step 4 and Step 5's own counts. V0.7's four commits (`ff0ad1e`, `3abaa7c`, `b1e6702`, `12122ad`) stay entirely local; this closure entry is its own commit, also not pushed — pushing follows only a separate, explicit instruction. D-021 stays Open, intentionally outside V0.7. *(V0.8 Strategy Selection has since started — see the row above.)* |
| 2026-09-22 | **V0.7 Step 5: the three remaining architectural questions resolved (D-183, D-184, D-185); close-out prepared** | A documentation/decision step, not an implementation one — inspection found nothing left inside V0.7's own scope needing new source code; `strategy.py`/`feasibility.py` confirmed byte-for-byte unchanged since Step 4 (`b1e6702`) by diff, not assumed. **D-183:** candidates are feasibility-filtered before selection; full V0.2 Plan validation runs once, only on the selected strategy's expanded `Plan`, never on every candidate — confirms the reading Steps 2–4 were already built against, fixes only V0.8's future ordering. **D-184:** MCP and RAG are deferred, unassigned extensions outside the V0.7–V1.0 strategy-intelligence sequence; neither gets a milestone number until a concrete requirement or benchmark needs it; D-027/D-028 annotated, not reopened. **D-185:** candidate generation and feasibility are not `MissionEvent`s in V0.7; `MissionEventType` gains no member; a `Strategy` is not a `MissionState` field. A "V0.7 close-out review" was prepared (definition of done checked against V0.7's own scope, what is/is not delivered, invariants exercised — 9, 11, 14 — and not, findings, what stays Open for V0.8) but **not declared closed**, matching the V0.4/V0.5 precedent of a prepared review the owner then confirms separately. Focused planning suite unchanged at 156 passed; full default suite unchanged at **2,986 passed, 2 deselected** (identical counts to Step 4, confirming nothing regressed and nothing was silently added). No new non-trivial logic, so no new mutation run. Decision counts: 142 Accepted, 39 Open, 5 Deferred. Committed as one focused commit; not pushed. V0.7 is ready for the owner's close-out decision; V0.8 not started. |
| 2026-09-22 | **V0.7 Step 4 implemented: the feasibility gate (`check_feasibility`, `FeasibilityReport`)** | *Candidate generation creates possibilities; feasibility filtering determines which possibilities are actually legal* — governance never depends on an LLM behaving correctly. Reuses only D-180's own already-approved contracts (`TaskGenome.required_capabilities`, `ReliabilityContract`, `SystemLimits`); no new numeric limit anywhere. `check_feasibility(strategy, task_genome, reliability_contract, limits) -> FeasibilityReport` runs three narrower, strategy-level analogues of V0.2's CAPABILITY/COMPLEXITY/RESOURCE stages — never SCHEMA/DEPENDENCY/CYCLE/POLICY (a `Strategy` has nothing for those to check), and never a call into `eidos.validation.stages`/`.pipeline`: strategy feasibility is not Plan validation, proven by a guard mirroring the compiler's own "does not reimplement V0.2" check. CAPABILITY: every stage capability ⊆ `required_capabilities`, converse not required. COMPLEXITY: stage count vs `max_depth`, widest stage vs `max_parallel_branches`, total capability occurrences vs `max_nodes` — strategy-level estimates, `verification` not counted. RESOURCE: the same total against the effective `max_agent_calls` (`min(ceiling, contract value)`, V0.2's own formula) — at the Strategy level this legitimately reuses COMPLEXITY's own total, since every stage entry *is* a capability occurrence (no non-agent node concept exists yet at this level). Typed violations only, a new `FeasibilityViolationCode` (five members, deliberately separate from `eidos.validation.results.ViolationCode`), cross-validated so a mislabelled violation is unconstructible, mirroring `Violation`'s own design rule almost verbatim. `generate_candidate_strategies` reordered: generate → dedupe → stamp identity on every distinct shape → feasibility-check every one → split feasible/infeasible → cap only the feasible pool — retiring Step 3's own ad hoc capability-only re-check, always a placeholder for this gate. `RejectedCandidate` now carries the full, identity-stamped `strategy` and its `FeasibilityReport`, not a free-text reason. The reference generator's own shapes are proven unchanged by tightening limits — only which shapes survive changes. 36 new tests, 2 new guard tests. Mutation check: 12 of 12 caught (3 initially missed, each closed with a more discriminating test). Full default suite **2,986 passed, 2 deselected**. Committed as one focused commit; not pushed. *(Step 5 has since resolved the three remaining architectural questions and prepared close-out — see the row above.)* |
| 2026-09-22 | **V0.7 Step 3 implemented: the bounded candidate-generation boundary (`CandidateGenerator`, `RuleBasedCandidateGenerator`, `generate_candidate_strategies`)** | The Jev-inspired principle made real: EIDOS constructs the feasible decision space, a future model may choose from it but never defines what is valid. No new decision needed — the approved `Strategy` contract already expressed everything required. `CandidateGenerator` is a pure function of `task_genome.required_capabilities` only (never `CapabilityRegistry` — that binds capability to agent, a separate, later concern). `RuleBasedCandidateGenerator` produces up to three gated shapes — linear, parallel, staged — each withheld outright when it would be structurally identical to a simpler one, rather than left for deduplication to catch; verification posture is derived (`FINAL` when anything is allocated, `NONE` otherwise), not permuted as an independent axis, to avoid inflating candidate count without a meaningfully different approach. `generate_candidate_strategies` is the "genuinely required" orchestration boundary: structural dedup (generator-agnostic), a capability-membership re-check distinct from D-180's own later feasibility filtering (an untrusted/future generator's mistake is reported in `rejected`, never silently dropped, never raised), and identity injection through a new `StrategyIdSource` Protocol mirroring `eidos.recording.ports.IdSource` one layer earlier — **no real, uuid-drawing implementation lives in `eidos.planning` at all**, keeping the whole package free of randomness. `max_candidates` stays required, no default (D-181); a negative value is refused rather than silently misinterpreted by Python's own slice semantics. `StrategyShape` (dropped in Step 2 for lack of a consumer) is reintroduced now that `CandidateGenerator` is that consumer — `Strategy` itself is unchanged. 63 new tests across `test_planning_generator.py` and `test_planning_pipeline.py`, plus 2 new guard tests. Mutation check: 16 of 16 caught (3 initially missed — a dedup key silently ignoring verification posture, and two field constraints with no direct test — each closed with a new test). Full default suite **2,950 passed, 2 deselected**. Committed as one focused commit; not pushed. *(Step 4 has since been implemented — see the row above.)* |
| 2026-09-22 | **V0.7 Step 2 implemented: the `Strategy` data contracts (`eidos.planning`)** | Scope held exactly to what D-178/D-179/D-182 approved: `StrategyId` (`eidos.contracts.identifiers`, UUID-backed, D-053 default), `VerificationPosture` (`StrEnum`, exactly `NONE`/`FINAL`), `StrategyStage` (`capabilities: tuple[CapabilityId, ...]`, `min_length=1`, a capability may repeat — a deliberate multiset, unlike `AgentDescriptor.capabilities`'s set, D-134), `Strategy` (`tenant_id`/`mission_id`/`strategy_id`/`stages`/`verification`/`rationale`, frozen, strict, extra-forbidden, the same `EidosModel` base every contract uses). **`StrategyShape` (Step 1's proposed identity-free intermediate type) was reconsidered and dropped**: with no `CandidateGenerator` built yet, it has no consumer, and introducing it now would be exactly the premature type CLAUDE.md warns against — `Strategy` stays flat, like `Plan`. New package `eidos.planning`, a core layer (joining contracts/validation/compiler/runtime/state) depending only on `eidos.contracts` at this step. Guard tests (mirroring `test_compiler_guards.py`) pin the exact module list, forbidden imports, the import boundary, no vendor/model names, and — directly testing D-179's own exclusions — that none of `AgentId`/`StepId`/`model`/`tool(s)`/`max_retries`/`max_replans` appears as an imported symbol or a field name on `Strategy`/`StrategyStage`. 57 new tests (39 construction/immutability/typing/forbidden-concept/serialization tests, 18 guard tests). Mutation check: 9 of 9 caught on the first pass. Full default suite **2,887 passed, 2 deselected**. Committed as one focused commit; not pushed. Step 3 not started. |
| 2026-09-22 | **V0.7 Step 1: architecture and design accepted (D-178 to D-182, resolving D-020); no code** | Read-only exploration of `TaskGenome`, `Plan`, the V0.2 stages, `eidos.compiler`, `eidos.capabilities`, `SystemLimits`, `ReliabilityContract` and D-053's identifier conventions, against the long-Open D-020 and `docs/03_architecture.md` §7's own `eidos.planning` earmark. Proposed and the owner approved five decisions: **D-178** (Strategy is a distinct object from Plan — resolves D-020); **D-179** (the three V0.7 structural dimensions — topology/parallelism, a two-member verification posture, capability allocation — and the explicit exclusions: agent/model/tool selection, retry/replan posture, each for a named existing reason); **D-180** (feasibility filtering, not yet built, reuses the existing `SystemLimits`/`ReliabilityContract`, no new ceiling; `eidos.planning` becomes a new core layer); **D-181** (`max_candidates` is an explicit, required generation-time parameter, not a `SystemLimits` field; CLAUDE.md's own "two or three" stays the ceiling, not reopened); **D-182** (`StrategyId` is plain UUID-backed identity, no version, no signature — D-021 stays Open, untouched). **Three questions explicitly left Open, not resolved:** the handoff's own diagram ordering of Plan Validation relative to Strategy Selection vs. this session's target flow; the MCP/RAG milestone renumbering now that V0.7 means Strategy, not MCP; whether candidate generation ever becomes a `MissionEvent`. Decision counts: 139 Accepted, 39 Open, 5 Deferred. Updated `docs/03`, this file. No source code changed. Not pushed. |
| 2026-09-22 | **V0.6 Step 6 implemented: the recording adapter (`eidos.recording.a2a.record_a2a_notification`)** | The narrow, transport-neutral bridge from one externally received A2A webhook delivery to a caller-owned `EventLog`, made possible by D-177 and requested next. Composes `eidos.a2a.webhook.notification_to_proposal` (unchanged) with the caller's own `EventLog.accept` (unchanged) — no new API surface was needed, so no new decision was recorded; this was checked, not assumed, before writing code. `log: EventLog` is a parameter on every call, never a constructor field, so ownership is never in question; the adapter never calls `accept_resumed`, never resumes, never runs another execution round, never touches `MissionState` directly, and was proved to hold no state of its own (two independent logs, two calls, no crosstalk). `A2ARecordingResult` (`webhook: WebhookResult`, `intake: IntakeResult \| None`, a `recorded` property) adds no new outcome vocabulary — the five required distinctions (malformed delivery, invalid correlation, duplicate lifecycle event, invalid event proposal, invalid state transition, successful recording) fall directly out of the existing `WebhookOutcome`/`ReduceOutcome` values, composed, never collapsed. **Lives in `eidos.recording`, not `eidos.a2a`** (an adapter package may depend on the A2A boundary; a core layer may not, and `eidos.a2a` itself must still be reached by nothing else) — and is **deliberately not re-exported from `eidos/recording/__init__.py`**, so a plain `import eidos.recording` stays free of the optional `a2a` extra's `httpx` dependency (D-171), verified directly by subprocess import; a caller imports `eidos.recording.a2a` explicitly. Both packages' static guard tests were extended to state this precisely, not weakened: `test_a2a_guards.py` now names the one permitted importer instead of forbidding all of them (its own prior wording had already anticipated this exact shape); `test_recording_guards.py` gained `eidos.a2a` as an allowed layer, carved `"a2a"` out of its vendor-name check (mirroring `eidos.state`'s and `eidos.a2a`'s own prior carve-outs), and gained a new guard proving only `a2a.py` — never `__init__.py`, never any other module — reaches for it. 11 new tests in `tests/unit/recording/test_recording_a2a.py` (A2A_TASK_STARTED unaffected; malformed/unknown-task deliveries never reaching the log; a completion applying through an AWAITING pause without auto-resuming; a repeated `event_id` and a repeated `a2a_task_id` refused distinctly; the wrong mission's log refused as invalid; a finished mission's late delivery refused as an invalid transition; statelessness across two logs; replay equivalence; a full end-to-end submit → await → pause → webhook → recording adapter → `accept_resumed` → finish), one new guard test, one guard test renamed. Mutation check: 6 of 6 caught on the first pass. Full default suite **2,830 passed, 2 deselected**. Committed as one focused commit; not pushed. Step 7 not started. |
| 2026-09-22 | **D-177 ruled and implemented: explicit resume of a `paused` mission (`EventLog.accept_resumed`, `reducer.reduce_resumed`)** | Resolved the gap Step 5 found and reported: once D-176 accepted one `A2A_TASK_COMPLETED` into a `paused` mission, nothing un-paused `MissionState.status`, so a caller could not record the following round of ordinary events on the same log. The owner ruled resumption is a distinct, **never-automatic** `EventLog` operation reading the log's own history, not a new `MissionState` field. **`reduce()`, `accept()`, `MissionState`, `MissionStatus` and D-176's `A2A_TASK_COMPLETED` handling are all unchanged** — verified by rerunning every existing test unmodified. Added `reducer.reduce_resumed` (a sibling to `reduce`, sharing every check but the `paused`-refusal via a shared internal `_reduce`), `reducer.most_recent_pause`/`reducer.resumable_pause` (pure, shared by both `log.py` and `replay.py`), and `EventLog.accept_resumed` (a sibling to `accept`, refactored through a shared `_accept_via` so neither duplicates the D-162/D-172 repeat-guard bookkeeping). **Checked directly against the case that breaks any simpler design** (an admission-halt-paused mission with an independently outstanding, later-concluding A2A task — indistinguishable from a resolved awaiting pause by `agent_tasks` alone): `accept_resumed` still refuses it correctly, because it reads the log's actual history, not state alone; a genuinely new halt recorded *during* a resumed round is picked up by the next history scan and makes the mission terminal again, with no extra state. `replay._fold` needed the identical rule as a direct, necessary consequence (a log a live caller correctly extended past a resume must still replay to the same state) — `checkpoint_at`/`resume` inherit the same known "no history before the checkpoint" limitation `seen`/`task_seen` already carry, documented and pinned by its own test rather than silently accepted. 19 new tests in `tests/unit/state/test_state_d177_resume.py` (all ten of the owner's required scenarios) plus `tests/unit/a2a/test_a2a_scenario.py` extended to complete the full submit → await → pause → webhook → resume → finish flow it always meant to prove. Mutation check: 14 of 14 caught on the first pass. Full default suite **2,812 passed, 2 deselected**. Recorded as **D-177 (Accepted)**; counts 133 Accepted, 40 Open, 5 Deferred. Committed as one focused commit; not pushed. Step 6 not started. |
| 2026-09-22 | **V0.6 Step 5 implemented: `eidos.a2a` (the client, the Research Agent's remote `WorkAgent`, the webhook converter); a real resume gap found and reported** | Re-verified the wire format directly against the live spec rather than trusting Step 1: found and corrected two real details (`TaskState` is `TASK_STATE_*` SCREAMING_SNAKE_CASE, confirmed by ADR-001 and the spec's own example; JSON-RPC methods are PascalCase — `SendMessage`/`GetTask` — not `message/send`/`tasks/get`), neither a contract change. Built `wire.py` (the verified Pydantic wire types), `convert.py` (`agent_task_status_of`, `text_artifact_of`), `transport.py` (`Transport`/`HttpxTransport`, the only module importing `httpx` — a new optional `a2a` extra, D-171), `client.py` (`send_message` always sends `return_immediately: true` — the wire default is `false` and would silently make a real server block the call — and `get_task`; four failure kinds, never collapsed: `NETWORK`, `TRANSPORT_TIMEOUT`, `MALFORMED_RESPONSE`, `PROTOCOL_ERROR`), `agent.py` (`A2AWorkAgent`, D-175's remote Research Agent; correlation facts `WorkResult` cannot carry, D-165 rule 1, exposed via `submitted_task(step_id)`), `webhook.py` (`notification_to_proposal`, a pure function — not a server — correlating via `MissionState.agent_tasks`, item 3, and writing a completed task's usable text to the same `ArtifactStore` a local agent uses), and `deadline.py` (`check_deadline`, D-173 item 2's separate EIDOS-observed timeout, never polled automatically). **Found and reported, not silently patched:** the full scenario test proves the runtime-level resume (`run_baseline` again with `PriorOutcomes`) works completely, but the event-recording side cannot follow on the same log — once D-176's exception accepts the one `A2A_TASK_COMPLETED`, `MissionState.status` stays `paused` and nothing currently moves it back, contradicting D-167's own description of that flow. Pinned as an asserted fact in `test_a2a_scenario.py`, not touched in `eidos.state` (Step 4 is already committed; this is the owner's call). 119 tests added across nine files, including `test_a2a_transport.py` against `httpx.MockTransport` (no real socket) and `test_a2a_guards.py` (layer boundaries, D-171's dependency footprint). Mutation check: 33 of 33 caught on the first pass. Full default suite **2,793 passed, 2 deselected**. Scope held to `eidos.a2a` and its tests (plus the one `eidos.providers` guard test D-171's new extra required updating). No `eidos.recording` change, no automatic resume, no `tasks/cancel`, no streaming. Committed as one focused commit; not pushed. Step 6 not started. |
| 2026-09-22 | **V0.6 Step 4 implemented: the `eidos.state` event/reducer integration (`A2A_TASK_STARTED`/`A2A_TASK_COMPLETED`, the D-176 exception)** | `A2ATaskStartedPayload`/`A2ATaskCompletedPayload` added; `MissionPausedPayload` rewritten to the D-169 XOR shape it was approved with but not yet built (`halt` or `awaiting`, exactly one). Reducer branches: `A2A_TASK_STARTED` folds a new `SUBMITTED` `AgentTask`; `A2A_TASK_COMPLETED` requires a correlated existing one (refusing "no prior `STARTED`" and a plan/step mismatch as typed rejections) and folds the update — neither touches a counter, that stays `NODE_SETTLED`'s job later. The D-176 terminal exception (`_resumable_completion`) checks only what the state holds — a correlated, non-concluded `AgentTask` — never *why* the mission paused. **Flagged, not silently decided:** this means an admission-halt pause that happens to coexist with an independently outstanding A2A task still takes that task's completion (it only ever touches `agent_tasks`, never `status`, so the halt's own terminality is never reopened); both that edge case and the ordinary "nothing outstanding, still refused" case are tested. New `eidos.state.agent_task_events` mirrors `step_events.py` one layer over, keyed by `a2a_task_id`, with a new `ReduceOutcome.REPEATED_AGENT_TASK_EVENT`; wired into `log.py`'s intake and `replay.py`'s fold. `execution_record.py` gained the `awaiting` field and a real bug fix in `_run_outcome` (would have mapped every awaiting-caused pause to `HALTED`) as a direct, necessary consequence of the payload shape change. One guard test caught a first draft's use of `model_copy` to build the completed `AgentTask`; fixed to the full constructor. Two exact-enumeration tests were updated for growth from nine to eleven emitted types and six to seven `ReduceOutcome` members; a real hit on the vendor-name guard (the literal word "MCP") forced one docstring sentence to be reworded. 39 tests added or updated (15 new in `test_state_agent_task_events.py`; 18 net-new plus 1 renamed in `test_state_reducer.py`; 3 net-new plus 2 renamed in `test_state_event_records.py`). Mutation check: 21 of 21 caught on the first pass. Full default suite **2,674 passed, 2 deselected**. Scope held to `eidos.state` and its tests only. No A2A client, webhook, transport, timeout, driver, resume automation or fifth `MissionStatus`. Committed as one focused commit; not pushed. Step 5 not started. |
| 2026-09-22 | **V0.6 Step 3 implemented: the runtime extension (`WorkStatus.SUBMITTED`, `NodeStatus.AWAITING`, `RunOutcome.AWAITING`, `AwaitingInfo`)** | `eidos.runtime` gains the four D-165 members with no protocol name anywhere in the package (verified: `AwaitingInfo` carries no correlation field, mirroring `HaltInfo`). `RunResult.awaiting` is a tuple, populated whenever a result is `AWAITING` regardless of `outcome` (unlike `halt`, tied 1:1 to `HALTED`). The reference executor's dispatch mapping and readiness check needed real extension — corrected the Step 3 table row, which had predicted none: an exhaustive `WorkStatus` mapping, and a doomed-vs-pending blocker distinction so a node behind only an awaiting predecessor becomes `NOT_REACHED` (not `SKIPPED`), propagating transitively through the ordinary per-node check with no bulk cascade, so independent branches and unrelated later levels still finish normally. Outcome precedence: `HALTED` > `AWAITING` > `FINISHED`/`FAILED`, extending D-118 rule 4. No `WorkExecutor` implementation was touched; nothing produces `SUBMITTED` yet. 36 tests added (3 existing exact-enumeration/field-list tests updated to match, the D-154 precedent). Mutation check: 18 of 18 caught on the first pass. Full default suite **2,595 passed, 2 deselected**; unit suite with the LangGraph family blocked **2,056 passed**. Scope held to `eidos.runtime` and its tests only — nothing in `eidos.contracts`, `eidos.state`, `eidos.compiler`, `eidos.validation`, `eidos.capabilities`, `eidos.agents`, `eidos.providers`, `eidos.backends` or `eidos.recording` was touched. Step 4 not started. |
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
