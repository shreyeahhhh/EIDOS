# 06 — Mission State

**Status:** DERIVED — current · target milestones **V0.1** (contracts) and **V0.5** (reducer, checkpoints, replay)
**Derived from:** handoff §8, §9, §10, §11, §15, §32, §33, §73
**Authority:** This document is derived from `EIDOS_CLAUDE_CODE_HANDOFF.md` and subordinate to it.
If this document and the handoff conflict, stop and report the conflict to the human owner.

---

## 1. The ownership rule

**This is a hard architectural invariant** (§9, invariants 1 and 2).

> **MissionState is the only authoritative global state.**

Agents must **never** directly mutate MissionState. The path is:

```text
A2A events/results
        -> EIDOS event handling
        -> MissionState reducer
        -> LangGraph checkpoint/state
```

Remote agents may have their own internal state. EIDOS maintains only the state it needs to reason
about the mission. This exists to avoid multiple sources of truth.

## 2. The synchronization problem

The major risk (§10) is reconciling centralized LangGraph state with a decentralized, asynchronous
A2A task lifecycle. The forbidden outcome is three competing global state systems:

```text
LangGraph state  <->  A2A state  <->  Agent internal state
```

The architecture instead uses:

```text
Global MissionState
+
Remote AgentTask records
+
Event-based synchronization
```

`AgentTask` mirrors a remote task without granting it authority. Its suggested shape (§8):

```text
AgentTask
  agent_id
  a2a_task_id
  a2a_context_id
  status
  latest_artifact
  last_event
```

## 3. Events

Every external event should contain some form of (§10):

```text
event_id
a2a_task_id
sequence/version
timestamp
```

**Events must be processed idempotently** (invariant 8):

```text
Duplicate event         -> already processed -> ignore
Out-of-order/late event -> validate against lifecycle -> accept/reject deterministically
```

**No agent writes the global mission state.**

**Resolved — `decisions.md` D-011, decided by the human owner.**

§10's `sequence/version` is doing three jobs at once. The adopted model separates them:

1. **Identity** — `event_id`. **This is the idempotency key.** Meaningful for all event types.
2. **Mission order** — a **monotonic per-mission sequence assigned by EIDOS** when an event is
   **accepted into the EIDOS event stream**. This is the ordering used for deterministic replay.
3. **Remote-lifecycle order** — a producer-assigned per-`a2a_task_id` sequence, used only to validate
   a remote event against that task's lifecycle. **Deferred — not introduced in V0.1** (D-035).

Ordering authority sits with **EIDOS**, not the producer. This follows from invariant 2: a remote
agent is precisely the component that must not control EIDOS state. Assigning the sequence at
acceptance makes it a property of the EIDOS event stream rather than of any external system's
reliability.

**V0.1 scope:** `event_id` as idempotency key, plus the EIDOS-assigned mission sequence. No
A2A-specific producer ordering.

> **Still open:** **D-035** (A2A producer sequence), **D-036** (the `AgentTask` lifecycle state
> machine), **D-037** (one shared event shape vs separate internal/external shapes), **D-038**
> (bounding and persisting the processed-`event_id` set). None blocks V0.1.
>
> **D-036 is the sharpest.** §10 mandates deterministic accept/reject against a lifecycle, and §8
> gives `AgentTask.status` without enumerating states or legal transitions. The V0.6 protocol tests
> for late event, out-of-order event, agent restart and partial artifact cannot be written until it
> is answered.

## 4. Event types

§33 names the structured events:

```text
MISSION_CREATED
PLAN_GENERATED
PLAN_REJECTED
PLAN_COMPILED
A2A_TASK_STARTED
A2A_TASK_COMPLETED
MCP_TOOL_CALLED
RAG_SEARCH
EVIDENCE_REJECTED
VERIFICATION_FAILED
REPLAN_TRIGGERED
MISSION_COMPLETED
MISSION_FAILED
```

This list is presented in the handoff as examples, not as a closed enumeration. Several
correspond to milestones that do not exist yet (A2A at V0.6, MCP at V0.7, RAG at V0.8), so the
V0.1 `MissionEvent` contract must be able to carry them without the corresponding subsystems
existing.

### The V0.1 event shape — `decisions.md` D-067

**Resolved, decided by the human owner.** For V0.1, `MissionEvent` contains **only the envelope**:

```text
event_id   tenant_id   mission_id   sequence   occurred_at   recorded_at   type
```

**There is no `payload` field in V0.1.**

§33 names thirteen event types whose payloads plainly differ — a rejection reason, a tool call, a
verification failure, a mission outcome — and **describes none of them**. §10 enumerates an event's
fields and **does not list a payload at all**. CLAUDE.md §8 forbids untyped dicts crossing a module
boundary, so a generic container is not an available fallback.

Nothing in V0.1 emits an event, so defining thirteen payload shapes spanning V0.3–V0.8 would be
thirteen inventions no test could exercise. This follows the same reasoning that excluded the
quality-estimate type (**D-016**), `evidence_requirements` (**D-031**), evidence and result fields
(**D-041**) and the `PLANNING`/`EXECUTING` statuses (**D-052**).

**Intended future direction, recorded but not built:** a **typed, discriminated payload
representation keyed by event type** — never an untyped mapping.

> **Still open:** **D-037** (one shared event shape vs separate internal/external shapes),
> **D-075** (per-type payload definitions, resolving incrementally as milestones land),
> **D-076** (what payloads must *contain* for faithful replay).
>
> **D-076 carries the real risk.** D-010a makes MissionState a materialized view over the event log,
> so *an event that is not recorded is not replayable*. Deferring payloads defers the point at which
> that obligation becomes **testable**. It is not created by D-067 — only postponed.

## 5. The state shape

**Resolved — `decisions.md` D-010a, decided by the human owner.**

**MissionState is a materialized view over the event log.** It contains exactly the information the
runtime must answer **synchronously**:

- mission identity
- TaskGenome — contained **by value**; the genome carries no `mission_id`, because this containment
  *is* the ownership relationship (**D-068**)
- mission status and reason
- plan versions and lineage
- active plan
- remote `AgentTask` records
- the authoritative `ReliabilityContract` — added by **D-100**
- budget consumption counters — corresponding to **D-042**'s six contract budgets:
  `max_retries`, `max_replans`, `max_agent_calls`, `max_tool_calls`, `max_execution_time`,
  `max_tokens`

**Detailed per-node runtime execution state does not enter the authoritative MissionState merely
because LangGraph has such state.**

### Field presence — `decisions.md` D-077

**`MissionState`:** `tenant_id`, `mission_id`, `created_at`, `updated_at`, `state_version`, `status` are
**required**; `status_reason` and `active_plan_id` are **optional** (§32 shows a reason only on
`paused`; §73 shows a mission existing before any plan is selected).

`task_genome` is **required** — a mission is created with its genome (**D-084**). No §33 event type
introduces a genome, so it must exist from `MISSION_CREATED`. `execution_id` is **required and
immutable**, one per mission in V0.1; replans create plan versions, and pause/resume keeps the same
execution (**D-085**). `plans`, `agent_tasks` and the six counters are **required** (**D-091**).

**`MissionEvent`:** `event_id`, `tenant_id`, `mission_id`, `sequence`, `recorded_at`, `type` are
**required** — §10 says **every** event carries its field set. `occurred_at` is also **required**
(**D-086**): it is the domain occurrence time — the producer's timestamp for external events, and equal
to `recorded_at` for EIDOS-internal events, set at acceptance. The reducer never invents timestamps.

### Representation — `decisions.md` D-090, D-091, D-097, D-100

- **`plans`, `agent_tasks` and the six budget counters are required** (**D-091**). The collections are
  **immutable** and **may be empty**; the counters are **non-negative integers**. The execution-time
  counter is in **milliseconds** (**D-078**). `plans` is **ordered**; `agent_tasks` is an unkeyed
  immutable collection (**D-082**).
- **Timestamps** are timezone-aware **UTC**; naive values are **rejected** (**D-083**).
- **`MissionEventType`** is **exactly the thirteen types in §33** (**D-090**) — including A2A, MCP and
  RAG types that cannot occur in V0.1. This differs from D-052's exclusion of unreachable *states*;
  recorded so the difference is visible. **V0.5 (D-154, approved, not built):** three local-execution types are added — `NODE_STARTED`, `NODE_SETTLED` and `MISSION_PAUSED` — so there are sixteen.
- **`sequence` starts at 1**; **`state_version`** is a non-negative integer equal to the latest applied
  mission sequence (**D-097**). Reducer and checkpoint semantics are decided for V0.5 by D-155 and D-157 (approved, not built).

**The contract lives here — `decisions.md` D-100.** MissionState holds the authoritative
**`reliability_contract: ReliabilityContract`**; the genome holds only `reliability_contract_id`. This
amends D-010a's field set by one field, and it is what lets MissionState answer "what would count as
acceptable" synchronously — it now reaches both the budget **counters** and the **limits** they are
measured against, so D-009's `min(system, contract)` rule is computable from state. The contract id
appears twice (genome reference and contract), so a mismatch is representable and must be checked.

### Why this boundary

§9 asserts MissionState is the *only* authoritative global state; §11 assigns LangGraph management
of *execution state*; §9's diagram shows the reducer writing into "LangGraph checkpoint/state". Two
state stores exist and one is asserted uniquely authoritative — coherent only if LangGraph's is
subordinate.

The apparent objection to a minimal MissionState — that replay would be incomplete — **dissolves on
§73**: replay consumes the **event log**, not MissionState. Completeness is a property the event log
must have. Per-node progress is reconstructible from events without being a state field.

The alternative, folding per-node execution status into MissionState, would make LangGraph's
execution model part of the authoritative contract — undoing the work §11, §12 and §15 do to keep
the runtime replaceable and the plan declarative.

### The obligation this creates

The completeness burden sits on the **event log**. **An event that is not recorded is not
replayable.** This binds every later milestone, not just V0.5.

It also substantially pre-answers **D-017**: if MissionState is a materialized view, the event log
is the durable artifact and a snapshot is an optimisation. D-017 is *not* resolved — the consequence
is recorded so it is visible rather than arriving later as a fait accompli.

> **V0.5 (2026-09-21):** **D-039** (the reducer returns state and an outcome) is decided by D-155 and **D-010b** (a checkpoint is a value) by D-157, both approved and not built.
>
> **Still open:** **D-041** (evidence and final mission-result fields — V0.4 and V0.8). None blocks V0.1.
> **D-040** (the exact MissionState/LangGraph split) is **resolved by D-113**: MissionState never
> enters LangGraph state, LangGraph state holds only `outcomes`, and V0.3 writes nothing to MissionState.

**Representation — resolved.** **D-053**: identifiers are opaque **UUID-backed** values with distinct
per-kind types (`TenantId`, `MissionId`, `ExecutionId`, `PlanId`, `EventId`, `AgentId`, …), with
readability handled at the display layer. **D-054**: **all contract timestamps are explicit required
inputs** — no model may read the wall clock during construction, which keeps construction
deterministic and keeps replay faithful. Both are stated in full in `docs/03_architecture.md` §11.

### Mission status — `decisions.md` D-052

**Resolved, decided by the human owner.** `MissionStatus` contains **exactly four** states:

```text
created    completed    failed    paused
```

`status_reason` carries the explanation associated with `paused` or other status outcomes — §32's
"Maximum recovery budget exceeded", for instance.

**The handoff never enumerates mission statuses.** These four are supported by three kinds of
evidence: `created`/`completed`/`failed` from §33's event names, `completed` additionally as the only
actual `status` value anywhere (§53) and as §43's display text, and `paused` from §32's rendered
`MISSION PAUSED / Human review required`.

**`PLANNING` and `EXECUTING` are deliberately absent.** Every handoff-named state is an entry, exit
or suspension **boundary**; the omitted states are precisely the *in-progress* ones. That is
coherent — the handoff describes missions from the outside, through events, API responses and UI
displays. In-progress substates are runtime progress information, which **D-010a** excludes from
authoritative MissionState and **D-040** deferred to V0.3 (resolved by **D-113**). Nothing in V0.1 could reach such a state in
any case, since there is no planner, validator or runtime.

The runtime's real need — distinguishing "can still accept events" from "terminal" from "suspended"
— is met by four: *created and not yet completed, failed or paused* is the active condition. At V0.5
the reducer will need "terminal" defined for rejecting late events, the same shape of problem
**D-036** poses for `AgentTask`.

**Accepted cost:** `created` names the state a mission occupies for most of its life, which reads
oddly. Accepted knowingly as a naming consequence, not a correctness one.

> **Still open:** **D-058** — whether `paused` later needs a more specific name or a split, once
> there is a second reason to suspend a mission (a `HUMAN_APPROVAL` step, a policy hold).
> **D-059** — whether "could not satisfy the reliability contract" (§30, §47, invariant 13) is
> `failed` with a reason or a **fifth terminal state**. The handoff gives that outcome no event name
> in §33 and no status value in §53. Invariant 13 requires it to be distinguishable from a crash or
> a timeout; if it collapses into `failed`, that distinction lives entirely in `status_reason` and
> every consumer must parse a reason rather than read a state. Material at V0.4.

### Constraints the field set satisfies

Each field above answers a question the runtime must resolve before acting. These are derivations
from the handoff, not choices:

| Requirement | Source |
|---|---|
| Plan lineage: v1 failed with a reason, v2 completed | §15 |
| Remote task mirrors as `AgentTask` records | §8 |
| Recovery budget counters: retries, replans, execution time, agent calls, tool calls | §32 |
| Mission can enter a paused state awaiting human review | §32 |
| Per-mission measurements: agent calls, A2A messages, MCP calls, RAG rounds, tokens, latency, retries, replans, quality, evidence confidence, cache hit rate, policy violations, human interventions | §33 |
| Identity: `tenant_id`, `mission_id`, `execution_id`, `agent_id`, `timestamp` | §54 |

None of these is a decision. They are constraints any decided field set must satisfy.

## 6. Replay

Every completed mission should be replayable from recorded events (§73, invariant 15).

**Replay consumes recorded events. It does not re-run the agents.**

The replay timeline shown in §73 runs: mission created → task genome generated → capabilities
discovered → strategies generated → plan selected → agents started → MCP called → evidence evaluated
→ replan triggered → verification passed → mission completed.

This implies the event log is sufficient to reconstruct state — which in turn constrains whether the
event log or a state snapshot is the authoritative record for persistence. That question is open;
see `decisions.md` **D-017**.

## 7. Implementation constraints

- `MissionState`, `MissionEvent` and `AgentTask` live in `eidos.contracts` (V0.1). The reducer,
  checkpoints and replay live in `eidos.state` (V0.5).
- The reducer is **deterministic**: no I/O, no network, no LLM calls, no hidden global state, no
  wall-clock dependence in logic. Timestamps arrive on events; the reducer does not read the clock.
- Only the reducer writes MissionState. Nothing else, anywhere, at any layer.
- V0.5 (approved, not built): events are produced by recording adapters outside the runtime and enter the log through an intake that assigns the sequence; the event log is authoritative and
  `ExecutionRecord` is derived from it (D-152 to D-159).
- V0.1 is in-memory only — no persistence (D-005).
- §50 is explicit: **"Before adding A2A, state handling must already be reliable."** V0.5 precedes
  V0.6 for this reason, and that ordering is not to be shortcut.

---

## Open questions

| Id | Question | Blocks |
|---|---|---|
| D-059 | Is "could not satisfy the reliability contract" `failed` with a reason, or a fifth terminal state? | V0.4 |
| D-058 | Should `paused` later become more specific, or split? | V0.3+ |
| ~~D-039~~ | **Resolved by D-155** — the reducer returns state and an outcome | V0.5 |
| ~~D-010b~~ | **Resolved for V0.5 by D-157** — a checkpoint is a value taken on request; storage stays with D-017 | V0.5 |
| ~~D-126~~ | **Resolved by D-154** — `NODE_STARTED`, `NODE_SETTLED` and `MISSION_PAUSED` are added (sixteen types) | V0.5 |
| D-041 | Evidence and final mission-result fields | V0.4, V0.8 |
| D-036 | The `AgentTask` lifecycle state machine "validate against lifecycle" presupposes | V0.6 |
| D-037 | One shared event shape, or separate internal and external shapes? | V0.6 |
| D-035 | Do A2A events carry a producer-assigned per-task sequence? | V0.6 |
| D-038 | Bounding and persisting the processed-`event_id` set | V0.5+ — answered for V0.5 only (D-155, D-157); stays Open |
| D-017 | Is the event log or a state snapshot authoritative for persistence and replay? | V0.5+ — the log is authoritative for V0.5 (D-157); persistence stays Open |
| D-033 | Does `tenant_id` propagate to nested models, or stay root-only? | V0.1 |
| D-075 | Per-type payload definitions — §33 names thirteen types and describes none | V0.3–V0.8, incrementally — answered for V0.5's emitted types (D-153); stays Open |
| D-076 | What payloads must carry for faithful replay under invariant 15 | V0.5 — discharged for the emitted types (D-153, D-157); stays Open |

## Out of scope for this document

The A2A wire protocol (`07_a2a_contract.md`), telemetry and metrics derived from events
(`11_evaluation.md`), recovery policy (`10_reliability.md`).
