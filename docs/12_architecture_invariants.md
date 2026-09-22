# 12 — Architecture Invariants

**Status:** DERIVED — current. **Normative.**
**Derived from:** handoff §8–§15, §24, §29–§33, §36, §44, §54, §67, §73, §74, §82, §84
**Authority:** This document is derived from `EIDOS_CLAUDE_CODE_HANDOFF.md` and subordinate to it.
If this document and the handoff conflict, stop and report the conflict to the human owner.

---

These are the rules EIDOS is not allowed to break. They are stated in short form in `CLAUDE.md` §2;
this document is the normative version, with the rationale, the handoff source, and how each one is
verified.

**A change that touches an invariant requires explicit human approval and an entry in
`decisions.md`.** Not a comment, not a commit message — an entry.

Where an invariant cannot yet be tested because the relevant milestone does not exist, the
verification column states the milestone at which the test becomes required. "Not yet testable" is
never a reason to weaken the rule.

---

## 1. MissionState is the only authoritative global state

**Source:** §9, §10

Nothing else is global truth. Remote agents may hold internal state, and LangGraph holds execution
state, but neither is authoritative for the mission.

**Rationale:** The failure mode being designed against is three competing global state systems —
LangGraph state, A2A state and agent internal state — each believing it is correct.

**Verified by:** V0.5 reducer unit tests; V0.6 protocol tests proving a remote agent's view does not
override MissionState.

**Refined:** `decisions.md` **D-010a** — MissionState is a **materialized view over the event log**,
holding only what the runtime must answer synchronously. Detailed per-node runtime execution state
stays out of it, so LangGraph's execution model never becomes part of the authoritative contract.
The completeness burden therefore sits on the **event log**: an event that is not recorded is not
replayable. **D-040** settled the exact split at V0.3 (**D-113**): MissionState never enters LangGraph state.

## 2. Only the state reducer mutates MissionState

**Source:** §9, §10

Agents never mutate it. Remote agent state stays remote and is mirrored into EIDOS solely as
`AgentTask` records, which carry no authority.

**Rationale:** A single writer is what makes the state reasoning tractable and replay possible.

**Verified by:** V0.5 unit tests; static review that no module outside `eidos.state` writes
MissionState. Candidate for an automated import/write check.

## 3. The LLM emits a bounded Plan DSL and nothing else

**Source:** §11, §12, §13

It never emits executable code, Python, or LangGraph graph construction — under any circumstance.
The pipeline is `LLM -> Plan DSL -> Validator -> Compiler -> LangGraph runtime`.

**Rationale:** §12 is explicit. Arbitrary LLM-generated graph topology produces un-debuggable
workflows, accidental cycles, runaway branching, uncontrolled recursion, inconsistent state,
excessive cost and untestable behaviour.

**Verified by:** V0.2 validator tests rejecting anything outside the approved primitives; review that
no code path passes model output to an executor, an evaluator, a code loader or a graph builder.

## 4. A plan's canonical representation is an ID-addressed DAG

**Source:** §13, §14; decided by the human owner as `decisions.md` **D-004**

Every step carries an explicit id; every dependency is an explicit edge. Validation and compilation
operate only on that form. Any nested or tree-shaped surface syntax is optional sugar and must be
normalized into the DAG **before** validation.

**Rationale:** §13's nested example cannot structurally contain a cycle and has no step identity to
depend on, yet §14 mandates dependency validation and cycle detection. Only the DAG form makes those
checks meaningful.

**Verified by:** V0.2 tests for dependency errors and cycles — which are vacuous under the tree
reading and meaningful under this one. If a nested syntax is added later, normalization needs its own
tests.

## 5. No plan executes unvalidated

**Source:** §14

Order: schema → dependencies → cycles → capabilities → policy → resources → complexity limits →
compile. A plan failing any stage is **rejected** — never repaired silently, never truncated to fit,
never partially executed.

**Rationale:** Validation is the only thing standing between a model's proposal and real execution.

**Verified by:** V0.2 tests per stage — valid plans, dependency errors, cycles, maximum depth,
maximum nodes, maximum parallel branches, unknown capabilities, invalid operations, policy
violations, resource violations (§58).

> **V0.2 status (2026-09-19):** implemented for every stage except policy, which reports
> `NOT_APPLICABLE` (D-110). "Invalid operations" is covered by schema validation — an unknown step
> `kind` is a schema violation. See `docs/05_plan_dsl.md` §4.

## 6. Plans are immutable and versioned

**Source:** §15

A live graph is never mutated in place. Replanning produces plan vN+1 with recorded lineage and a
recorded reason.

**Rationale:** Mission history must show `Plan v1 -> failed, reason: insufficient evidence` then
`Plan v2 -> completed`. This is what makes debugging and replay possible.

**Verified by:** V0.3 replan tests asserting a new version rather than mutation; V0.5 replay tests
reconstructing the version sequence.

## 7. Execution is bounded

**Source:** §14, §32

Bounded by `max_nodes`, `max_depth`, `max_parallel_branches`, `max_retries`, `max_replans`,
`max_agent_calls`, `max_tool_calls`, `max_execution_time`. Exhaustion **pauses the mission for human
review**. It never loops, never silently truncates, never retries forever.

```text
MISSION PAUSED
Reason: Maximum recovery budget exceeded.
Human review required.
```

**Rationale:** No infinite loops. Cost, latency and debuggability all depend on this.

**Verified by:** V0.2 rejection tests for over-budget plans; scenario tests for retry, replan, token
and tool budget exhaustion (§63).

**Resolved:** `decisions.md` **D-009** — bounds split by category. Shape/complexity limits
(`max_nodes`, `max_depth`, `max_parallel_branches`) are **system-level safety limits** protecting the
runtime from an LLM's output; execution budgets (`max_retries`, `max_replans`, `max_agent_calls`,
`max_tool_calls`, `max_execution_time`, `max_tokens`) are carried by the **ReliabilityContract**. A
mission may tighten a system limit, never exceed the ceiling, and an over-ceiling request is
**rejected with an explicit reason, never silently clamped**.

**Still open:** **D-046** — no numerical value is established in V0.1 by decision; values arrive at
V0.2 and are tuned from measurement, and a provisional bound is never presented as a tuned one (§67).
**D-043** — five limit names appear in both §14 and §32 while counting different things. **D-029** —
the Agentic RAG reformulation loop (§24) still has no stated bound at all, and is the one loop in the
handoff without one.

## 8. Events are idempotent

**Source:** §10

Duplicates are ignored. Late and out-of-order events are accepted or rejected **deterministically**
against the lifecycle. Every event carries identity, ordering and timestamp fields.

**Rationale:** An asynchronous remote agent lifecycle cannot be reconciled with centralized state
unless event processing is idempotent.

**Verified by:** V0.5 reducer tests; V0.6 protocol tests for duplicate event, late event,
out-of-order event, agent restart and partial artifact (§50, §63).

**Resolved:** `decisions.md` **D-011** — three roles separated. `event_id` is the **idempotency
key**; a **monotonic per-mission sequence assigned by EIDOS at acceptance** provides the total order
replay depends on; a producer-assigned per-`a2a_task_id` sequence for remote-lifecycle ordering is
**resolved, negatively, by D-172 (2026-09-22): none exists on the wire to adopt**, verified directly against the published A2A specification. Ordering authority sits with EIDOS, not the producer —
which follows from invariant 2 rather than from §10, which is silent on assignment. **D-036** (the `AgentTask` lifecycle state machine) is resolved by **D-166**: the real ten-value wire `TaskState`
set plus EIDOS-observed `TIMED_OUT`, giving "accept/reject deterministically" a defined content, and the D-172 guard it needed turned out narrower than expected — "at most one `STARTED`, at most one
`COMPLETED`, per task". **D-037** (shared vs separate event shapes) is resolved: the shared envelope V0.5 already built needed no change.

**Still open:** D-038 (bounding the processed-`event_id` set).

## 9. The runtime is model-independent

**Source:** §7, §36

No model, vendor or SDK name appears in `contracts`, `planning`, `validation`, `compiler`, `runtime`
or `state`. Models sit behind a capability interface. A model may be replaced without redesigning
EIDOS.

**Rationale:** "Never make the underlying model the product." The system must remain useful when the
underlying models change, and the architecture must not assume any single model stays dominant.

**Verified by:** a static check that core layers contain no provider identifier; V0.4 tests
substituting one capability implementation for another without touching core layers.

**Note:** resolved for the model-provider boundary by `decisions.md` **D-135** (D-018): `eidos.agents` owns a synchronous
`ModelPort`; adapters live in `eidos.providers`, the only place a vendor, model or SDK name may appear; configuration is
explicit and never defaulted. V0.4's substitution test is a fake model in place of a real one, and a second registration in
place of the first, without touching core layers.

## 10. The runtime is domain-agnostic

**Source:** §44, §46

No domain workflow is hardcoded into the runtime. EIDOS may *execute* a software-delivery workflow,
but must not *become* one.

**Rationale:** §44 is explicit that EIDOS must not become another AI software factory, because that
territory is already occupied and it would destroy the differentiation.

**Verified by:** review at each milestone that no domain-specific step, agent or vocabulary has
entered the runtime; scenario tests covering more than one domain once agents exist.

## 11. Plans request capabilities, not named agents

**Source:** §7, §13

Capability-to-agent binding happens at selection/execution time.

**Rationale:** Agents are replaceable capabilities. Binding a plan to a named agent would defeat
capability discovery, strategy comparison and model independence.

**Verified by:** V0.1 contract tests that a `PlanStep` carries a capability; V0.2 capability
validation tests.

**Note:** the capability vocabulary and matching semantics are unresolved — `decisions.md` D-007. **V0.4 (D-132, D-134, D-144):** a
V0.4-only, exact-string, lowercase set of five capabilities; a `VERIFY` node is bound by node kind (D-133); an unbound capability is a
typed rejection before anything is dispatched. D-007 stays Open.

## 12. Verification is separate from completion

**Source:** §31

"An agent returned output" is never success. Verification inspects evidence coverage, consistency,
schema correctness, policy compliance, output quality, tool path and relevant execution state.

**Rationale:** Without this, the system reports success whenever a model produces text.

**Verified by:** scenario tests where an agent returns well-formed output that fails verification and
triggers a replan (§43, §63).

**Note:** how verification confidence is computed is unresolved and is the highest-risk gap in the
specification — `decisions.md` D-015.

## 13. The reliability contract is enforced

**Source:** §30, §47

If it cannot be met, EIDOS reports that it cannot be met. It never manufactures confidence to produce
an answer.

Required output shape: `Evidence confidence: 0.88 / Required: 0.90 / STATUS: Insufficient evidence`.
Forbidden: `Answer confidence: 88% / Completed successfully`.

**Rationale:** The product's trustworthiness rests on this. §47 states the preference for "I cannot
satisfy the reliability contract" over "I will confidently guess."

**Verified by:** scenario tests asserting a contract-unsatisfied outcome rather than a
confident-looking result.

## 14. Governance is deterministic

**Source:** §28, §29

"Can perform" and "is allowed to perform" are separate checks, enforced in code, **never by prompt**.
Autonomy levels 0–4 gate actions; read actions are automatic, configuration changes require human
approval, deletion of a critical resource is blocked.

**Rationale:** A policy enforced by prompt is not a policy.

**Verified by:** V0.2 policy-validation tests rejecting plans containing disallowed actions; V0.7
unauthorized-call tests at the MCP boundary; scenario tests for policy violation.

> **V0.2 status (2026-09-19):** the POLICY stage exists in the pipeline and reports `NOT_APPLICABLE`
> (`decisions.md` D-110): no policy check is defined yet, because the autonomy semantics it would
> enforce are unresolved (D-060, D-061, D-074). Rejecting disallowed actions therefore remains future
> work; nothing in V0.2 verifies this invariant.

**Note:** the `autonomy_level` scale and its collision with §40's separate budget concept are
unresolved — `decisions.md` D-014.

## 15. Every step emits a structured event, and missions replay from events

**Source:** §33, §73

A completed mission is replayable from recorded events **without re-running agents**.

**Rationale:** Replay is what makes debugging, demonstration and post-hoc evaluation possible, and it
is the basis of the telemetry → evaluation → memory loop.

**Verified by:** V0.5 replay tests reconstructing a mission timeline from its event log alone, with
no agent invoked.

> **V0.3 status (2026-09-19):** **not exercised.** V0.3 emits no `MissionEvent` (D-123) because the current event
> vocabulary cannot represent local node lifecycle events (D-126, Open). Nothing in V0.3 verifies this
> invariant, and no V0.3 document may claim replayability from events.

## 16. Conclusions are traceable

**Source:** §74

Conclusion → evidence → source → retrieval query → agent → tool → verification.

**Rationale:** Trust. This is also what the Evidence Explorer view surfaces.

**Verified by:** V0.8 tests that retrieval queries are retained on evidence rather than discarded
after use; scenario tests walking a conclusion back to its sources.

## 17. Estimates are labelled as estimates

**Source:** §18, §19, §38

They carry uncertainty, and prediction error is recorded separately from outcomes — e.g. predicted
latency 5.5s, actual 6.1s, error 10.9%.

**Rationale:** §18 forbids fabricated confidence such as `LLM says: Plan B = 93.6% quality`. §19
requires uncertainty representation. §38 requires counterfactual plan comparisons to be treated as
estimates, not facts. Tracking prediction error is also how the planner learns it is biased.

**Verified by:** contract tests that an estimate type is distinguishable from a measurement type;
review that no estimate is stored or displayed in a field meaning "measured".

## 18. Identity fields exist from the start

**Source:** §54

`tenant_id`, `mission_id`, `execution_id`, `plan_id`, `agent_id`, `event_id`, `timestamp` exist in
data models from the beginning. Authentication and multi-tenancy are implemented later — **the MVP
must not become an authentication project.**

**Rationale:** Cheap to include now, expensive to retrofit. The architecture must not assume
single-user forever.

**Verified by:** V0.1 contract tests.

**Resolved:** `decisions.md` **D-019** — `tenant_id` is present and required on V0.1 root models,
with a single fixed default. It **has no security meaning in V0.1** and must not be treated as an
authentication, authorization or isolation mechanism.

**Note — this invariant's list is under review.** §54 names **five** identifiers: `tenant_id`,
`mission_id`, `execution_id`, `agent_id`, `timestamp`. The list above asserts **seven**, adding
`plan_id` (from §33) and `event_id` (from §10). Both additions are handoff-sourced but neither comes
from §54, and they entered this invariant by derivation at bootstrap rather than by decision. This
is recorded as `decisions.md` **D-034** and awaits the owner. CLAUDE.md is not being amended pending
that decision.

**Also open:** D-032 (the literal default value), D-033 (root-only vs propagation to nested models).

---

## Cross-cutting rules that are not invariants but are binding

These come from the handoff and are enforced through `CLAUDE.md` rather than through code:

- **No fabricated numbers.** Every metric published comes from an actual recorded run (§67).
- **Do not weaken tests to make them pass; do not silently remove failing tests; do not suppress
  runtime errors** (§61).
- **Never resolve an architectural ambiguity silently.** Record it in `decisions.md` as Open and
  raise it (project rule, added at bootstrap).
- **Scope discipline:** 2–3 candidate strategies, three logical agents, 2–3 MCP tools, one A2A
  boundary at V0.6 (§16, §27, §49, §50).
- **Build core-outward, never bottom-up** (§75).

---

## Open questions affecting invariants

| Id | Invariant affected | Question |
|---|---|---|
| D-015 | 12, 13 | How verification confidence is computed |
| ~~D-126~~ | 15 | **Resolved by D-154** (V0.5, built): `NODE_STARTED`, `NODE_SETTLED` and `MISSION_PAUSED` are added to the vocabulary |
| ~~D-039~~ | 2 | **Resolved by D-155** (V0.5): the reducer returns state and an outcome |
| ~~repeated node events~~ | 8 | **Resolved by D-162** (V0.5): the intake and replay refuse a repeated `NODE_STARTED` or `NODE_SETTLED` for the same step of a plan; `MissionState` gains no per-node state |
| D-164 | 8 | A `NODE_STARTED` recorded after the same step's `NODE_SETTLED` is accepted (out of lifecycle order; no counter is affected) |
| ~~D-163~~ | 15 | **Resolved by D-163** (V0.5): D-158 item 1 was amended; the recorder wraps the agents, the verifier and the model port, and a halt is read from the run's result, in D-160 item 1's order |
| ~~D-036~~ | 8 | **Resolved by D-166** (V0.6): the closed ten-value `AgentTask` lifecycle, plus EIDOS-observed `TIMED_OUT` |
| ~~D-035~~ | 8 | **Resolved by D-172** (V0.6), negatively: no producer-assigned sequence exists on the wire to adopt |
| ~~D-037~~ | 8 | **Resolved** (V0.6): the shared V0.5 envelope needed no change; A2A fields live only in its payloads |
| D-046 | 7 | Numerical bound values (V0.2; none established in V0.1 by decision) |
| D-043 | 7 | Declared plan limits vs actual execution counters share names but count differently |
| D-029 | 7 | The RAG reformulation loop has no stated bound |
| D-007 | 11 | Capability vocabulary and matching semantics |
| D-014 | 14 | `autonomy_level` scale and naming collision with §40 |
| D-034 | 18 | Do `plan_id` and `event_id` belong in this invariant's list? §54 names only five |
| D-033 | 18 | Does `tenant_id` propagate to nested models, or stay root-only? |
