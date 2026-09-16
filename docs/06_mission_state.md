# 06 — Mission State

**Status:** DERIVED — ownership rules current; **field set OPEN** · target milestones **V0.1** (contracts) and **V0.5** (reducer, checkpoints, replay)
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

## 5. The state shape

**Resolved — `decisions.md` D-010a, decided by the human owner.**

**MissionState is a materialized view over the event log.** It contains exactly the information the
runtime must answer **synchronously**:

- mission identity
- TaskGenome
- mission status and reason
- plan versions and lineage
- active plan
- remote `AgentTask` records
- budget consumption counters

**Detailed per-node runtime execution state does not enter the authoritative MissionState merely
because LangGraph has such state.**

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

> **Still open:** **D-039** (reducer signature — V0.5), **D-010b** (checkpoint semantics — V0.5),
> **D-040** (the exact MissionState/LangGraph split — V0.3), **D-041** (evidence and final
> mission-result fields — V0.4 and V0.8). None blocks V0.1.

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
- V0.1 is in-memory only — no persistence (D-005).
- §50 is explicit: **"Before adding A2A, state handling must already be reliable."** V0.5 precedes
  V0.6 for this reason, and that ordering is not to be shortcut.

---

## Open questions

| Id | Question | Blocks |
|---|---|---|
| D-039 | The reducer signature — does it return an outcome alongside state? | V0.5 |
| D-010b | Checkpoint contents, granularity and trigger | V0.5 |
| D-040 | The exact MissionState / LangGraph execution-state split | V0.3 |
| D-041 | Evidence and final mission-result fields | V0.4, V0.8 |
| D-036 | The `AgentTask` lifecycle state machine "validate against lifecycle" presupposes | V0.6 |
| D-037 | One shared event shape, or separate internal and external shapes? | V0.6 |
| D-035 | Do A2A events carry a producer-assigned per-task sequence? | V0.6 |
| D-038 | Bounding and persisting the processed-`event_id` set | V0.5+ |
| D-017 | Is the event log or a state snapshot authoritative for persistence and replay? | V0.5+ |
| D-033 | Does `tenant_id` propagate to nested models, or stay root-only? | V0.1 |
| — | Whether §33's event list is closed or extensible, and how event payloads are typed | V0.1 |

## Out of scope for this document

The A2A wire protocol (`07_a2a_contract.md`), telemetry and metrics derived from events
(`11_evaluation.md`), recovery policy (`10_reliability.md`).
