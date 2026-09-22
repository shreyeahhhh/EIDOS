# tests/protocol

**Layer definition (handoff §62):** A2A lifecycle, MCP tools, idempotency, timeouts, failure events.

Protocol tests verify that EIDOS handles a protocol's *lifecycle* correctly — especially the ugly
parts: duplicates, late arrivals, restarts, partial results and timeouts. These are the tests that
defend invariants 1, 2 and 8.

**Handoff §59 requires these tests to be written before the implementation they cover.**

## What belongs here

### A2A — V0.6 (§50)

```text
normal completion    duplicate event    agent restart      failure
timeout              late event         partial artifact
```

Plus, from §63: out-of-order event.

Each must assert that MissionState remains authoritative, that the remote agent never mutates it,
and that `task_id` and `context_id` are preserved.

### MCP — V0.7 (§50)

```text
successful call    timeout             unauthorized call
invalid arguments  unavailable tool    duplicate call
```

Plus, from §63: malformed tool output.

## Status (2026-09-22)

The duplicate-, late- and out-of-order-event tests could not be written until the event ordering
domain, the idempotency key and the `AgentTask` lifecycle were defined. That citation was stale —
`decisions.md` **D-011** was resolved back at V0.1; the real blockers were **D-035**, **D-036** and
**D-037**, all Open until today. **They are now resolved**: `decisions.md` **D-165 to D-176**
(2026-09-22) accept the full A2A contract design, researched directly against the published A2A
Protocol Specification (a2a-protocol.org, v1.0) — no producer sequence exists to guess at (D-172);
the `AgentTask` lifecycle is the real ten-value wire `TaskState` set plus EIDOS-observed `TIMED_OUT`
(D-166); the shared event envelope V0.5 already built needs no change (D-037's resolution).

**Still currently empty.** These tests are written against the runtime and state contracts V0.6 Step
2 onward adds (`plan_id`/`step_id`/`started_at` on `AgentTask`, `WorkStatus.SUBMITTED`,
`NodeStatus.AWAITING`, the `A2A_TASK_STARTED`/`A2A_TASK_COMPLETED` payloads) — none of which exists
in code yet (`progress.md`, "V0.6 One A2A Boundary"). The design is decided; the implementation has
not started.
