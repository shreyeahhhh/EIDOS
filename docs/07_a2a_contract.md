# 07 — A2A Contract

**Status:** DERIVED — **DEFERRED to V0.6.** Specification only; nothing is implemented.
**Derived from:** handoff §8, §9, §10, §50, §59, §62, §63
**Authority:** This document is derived from `EIDOS_CLAUDE_CODE_HANDOFF.md` and subordinate to it.
If this document and the handoff conflict, stop and report the conflict to the human owner.

> **Nothing in this document is implemented.** There is no `eidos.a2a` package, no A2A dependency
> and no remote agent. Per §50, A2A arrives at V0.6 — **after** MissionState and the event reducer
> are reliable. See `decisions.md` D-026.

---

## 1. What A2A is and where it belongs

**A2A means Agent2Agent.** It is the communication layer between independent agent systems.

```text
EIDOS --A2A--> Research Agent --performs work--> Result / Artifact --A2A--> EIDOS
```

A2A is used at **meaningful independent-agent boundaries** only.

> **Do not force every internal function call through A2A just to claim A2A support.** (§8)

The architecture should be able to state: tightly coupled internal nodes run locally; independently
deployable agent capabilities use A2A.

## 2. Remote task representation

A2A remote tasks have their own lifecycle and identifiers. **EIDOS must represent remote tasks
separately from global mission state** (§8).

Suggested mapping:

```text
AgentTask
  agent_id
  a2a_task_id
  a2a_context_id
  status
  latest_artifact
  last_event
```

This record mirrors the remote task. It confers no authority: the remote agent does not own any part
of MissionState.

**V0.1 shape — `decisions.md` D-048, decided by the human owner.** `AgentTask` **is** included in
V0.1 because §50 explicitly lists it among the Core Contracts, kept minimal and future-compatible:
`agent_id`, `status`, and four optional fields — `a2a_task_id`, `a2a_context_id`, `latest_artifact`,
`last_event`.

**No A2A behaviour is implemented in V0.1.** The A2A fields being optional is what makes the model
honest in a world without A2A, and what lets V0.6 populate them without a contract change.

⚠️ `status` semantics remain Open under **D-036**. Until the state set and legal transitions are
defined, `status` is deliberately unconstrained and **nothing may branch on its value** — a
transition check written against an undefined lifecycle would encode D-036 silently.

Per **D-033**, `AgentTask` is a nested model and does **not** carry `tenant_id`.

## 3. The non-negotiable rules

From §9, §10 and §59, expressed as invariants 1, 2 and 8:

1. **MissionState remains authoritative.**
2. **The remote agent must never directly mutate MissionState.**
3. A2A lifecycle events map into **idempotent EIDOS events**.
4. Duplicate events are ignored.
5. Late and out-of-order events are validated against the lifecycle and accepted or rejected
   **deterministically**.
6. `task_id` and `context_id` are preserved.

The event path is fixed:

```text
A2A events/results -> EIDOS event handling -> MissionState reducer -> checkpoint
```

## 4. V0.6 scope

Move **exactly one** agent into an independent process (§50):

```text
EIDOS --A2A--> Research Agent
```

One boundary. Not three.

## 5. Required tests

§50 names the V0.6 test set explicitly:

```text
normal completion
timeout
duplicate event
late event
agent restart
partial artifact
failure
```

§63's minimum failure-scenario list adds: agent timeout, agent failure, agent restart, duplicate A2A
event, late A2A event, out-of-order event, partial artifact.

§59 requires that **protocol integration tests are written before the implementation.** These belong
in `tests/protocol/`.

## 6. Prerequisites

V0.6 cannot begin until:

| Prerequisite | Where |
|---|---|
| MissionState field set and reducer contract decided | `decisions.md` D-010 |
| Event ordering domain and idempotency key decided | `decisions.md` D-011 |
| A2A SDK, protocol version and transport chosen | `decisions.md` D-023 |
| V0.5 complete — "before adding A2A, state handling must already be reliable" (§50) | `progress.md` |

D-011 is the sharpest of these: the wire format determines what ordering guarantees are actually
available, and the duplicate/late-event semantics in §4 above cannot be specified without it.

---

## Open questions

| Id | Question |
|---|---|
| D-023 | Which A2A SDK, protocol version and transport |
| D-011 | Event ordering domain and idempotency key — constrains what the wire format must carry |
| D-010 | MissionState fields and reducer contract |
| — | Which agent moves across the boundary first. §50's example is the Research Agent, phrased as an example rather than a decision |
| — | Timeout values, retry policy at the boundary, and how a partial artifact is represented |
| — | How `a2a_context_id` relates to `mission_id` and `execution_id` |

## Out of scope for this document

MissionState internals (`06_mission_state.md`), the MCP tool boundary (`08_mcp_contract.md`),
recovery policy (`10_reliability.md`).
