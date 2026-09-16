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

> **Open — and load-bearing.** "sequence/version" does not define an ordering domain: a per-mission
> monotonic counter, a per-AgentTask counter, a per-producer counter, or a version vector are all
> consistent with the phrase, and each yields different duplicate/late-event semantics. The
> idempotency key is likewise undefined — `event_id` alone, or `(a2a_task_id, sequence)`. See
> `decisions.md` **D-011**. This blocks the reducer and every protocol test for duplicate, late and
> out-of-order events.

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

## 5. The state shape — unspecified

The handoff fixes **ownership** and **event names** but never enumerates:

- the fields of `MissionState`
- the reducer signature
- what a checkpoint contains, when one is taken, and at what granularity
- how plan versions (§15) are held in state
- how `AgentTask` records are keyed and held

See `decisions.md` **D-010**. This blocks both V0.1 `MissionState` and all of V0.5.

What *is* known from elsewhere in the handoff, and which any proposed field set must accommodate:

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
| D-010 | MissionState field set, reducer signature, checkpoint semantics | V0.1, V0.5 |
| D-011 | Event ordering domain and idempotency key | V0.1, V0.5, V0.6 |
| D-017 | Is the event log or a state snapshot authoritative for persistence and replay? | V0.5+ |
| D-019 | Does `tenant_id` appear in V0.1 models? | V0.1 |
| — | Whether §33's event list is closed or extensible, and how event payloads are typed | V0.1 |

## Out of scope for this document

The A2A wire protocol (`07_a2a_contract.md`), telemetry and metrics derived from events
(`11_evaluation.md`), recovery policy (`10_reliability.md`).
