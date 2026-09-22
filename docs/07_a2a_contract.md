# 07 — A2A Contract

**Status:** DERIVED — **the V0.6 protocol/contract design is accepted (2026-09-22, D-165 to D-177); Steps 1–5 of 9 are implemented (the `AgentTask`/state contract changes, the `eidos.runtime`
non-blocking extension, the `eidos.state` event/reducer integration, and `eidos.a2a` itself: the client, the Research Agent's remote `WorkAgent`, the webhook converter) — see `progress.md`,
"V0.6 One A2A Boundary". Step 5 found a real gap (a resumed mission could not record further events on the same log); D-177 resolved it with an explicit, never-automatic resume operation.**
**Derived from:** handoff §8, §9, §10, §50, §59, §62, §63
**Authority:** This document is derived from `EIDOS_CLAUDE_CODE_HANDOFF.md` and subordinate to it.
If this document and the handoff conflict, stop and report the conflict to the human owner.

> **`eidos.a2a` now exists** (Step 5): the hand-rolled JSON-RPC client, the Research Agent's remote
> `WorkAgent`, and the webhook-to-event converter. Re-verifying the wire format directly against the
> live spec while building it corrected two details Step 1 had assumed from an earlier reading —
> `TaskState`'s wire casing and the JSON-RPC method names — see `progress.md`'s Step 5 row for both.
> What Steps 2–4 built lives in `eidos.contracts`, `eidos.runtime` and `eidos.state` — the receiving
> end of the contract below; Step 5 is the sending end. No mission driver, no automatic resume, no
> `tasks/cancel`, no streaming.
>
> **D-177 (resolved):** the completion webhook alone never resumes a mission — `MissionState.status`
> stays `paused` through it. A caller resumes explicitly, through `EventLog.accept_resumed`, which
> reads the log's own history (never a new `MissionState` field) to tell a genuinely resolved
> awaiting pause apart from a permanently terminal admission-guard halt. See `progress.md`'s D-177
> subsection and `decisions.md` D-177 for the full contract.
>
> **The design below is now decided**, not merely proposed: `decisions.md` D-165 to D-177, researched
> directly against the published A2A Protocol Specification (a2a-protocol.org, v1.0) rather than
> assumed. `progress.md`'s "V0.6 One A2A Boundary" section summarises it. Sections 1 to 5 below are
> unchanged by that design — it refines and extends them, it does not contradict them.

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

`status` semantics are decided by **D-166** (resolves D-036): the real ten-value wire `TaskState` set
plus EIDOS-observed `TIMED_OUT`, never collapsed early, with a separate mapping to `NodeStatus`. Not
yet implemented — `AgentTask.status` in code is still the opaque string D-081 left it as, pending
V0.6 Step 2.

Per **D-033**, `AgentTask` is a nested model and does **not** carry `tenant_id`.

**Representation.** `a2a_task_id` and `a2a_context_id` are **externally assigned opaque strings**,
exempt from D-053's UUID rule, because the remote A2A system assigns them and EIDOS only mirrors them
(**D-095**). `last_event` is **`EventId | None`** — a reference, never an embedded event (**D-096**).

`latest_artifact` is **`ArtifactRef | None`**, where `ArtifactRef` is an opaque, string-backed
reference exempt from D-053, following D-095 since artifacts come from remote agents (**D-098**). **No
`Artifact` model is created** — the handoff never defines what an artifact contains. `status` is
still an **opaque string in code today** — D-081's reason for keeping it so is discharged by **D-166**
(§2 above), which defines the closed lifecycle; the field itself becomes typed at V0.6 Step 2, not yet.

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
| MissionState field set and reducer contract decided | resolved — `decisions.md` D-010a (V0.1), D-155/D-157 (V0.5) |
| Event ordering domain and idempotency key decided | resolved — `decisions.md` D-011 (V0.1) |
| A2A SDK, protocol version and transport chosen | resolved — `decisions.md` **D-171**: a hand-rolled `httpx` client over A2A v1.0, no `a2a-sdk` |
| V0.5 complete — "before adding A2A, state handling must already be reliable" (§50) | resolved — `progress.md`, closed 2026-09-21 |

All four prerequisites are resolved. What is **not** yet true is code: V0.6 Step 2 (the `AgentTask` contract extension) has not started (`progress.md`).

---

## Open questions

None of the questions this document originally raised are still open. D-023, D-011 and D-010 are resolved (table above). "Which agent moves first" is **D-175** (Research Agent). "Timeout values..." is
**D-173** (three separate concepts, layered as described there; the exact adapter-level deadline number is pinned at implementation, never invented, same discipline as D-046). "How `a2a_context_id` relates to
`mission_id`/`execution_id`" is answered by not forcing a relationship: per the published spec, `a2a_context_id` is opaque and server-assigned on first use, exactly as **D-095** already anticipated; EIDOS never
derives it from or ties it to an EIDOS identifier.

What remains genuinely open, from `decisions.md`'s own "Carried forward, not decided" note on V0.6 (in `progress.md`): **D-038** (bounding/persisting the applied-`event_id` set, unaffected in kind by a
longer-lived mission), **D-017** (durable persistence), and whether EIDOS ever actively cancels an in-flight A2A task (not built, not needed for V0.6's minimal slice).

## Out of scope for this document

MissionState internals (`06_mission_state.md`), the MCP tool boundary (`08_mcp_contract.md`),
recovery policy (`10_reliability.md`).
