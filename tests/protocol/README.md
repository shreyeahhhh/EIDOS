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

## Blocked

The duplicate-, late- and out-of-order-event tests cannot be written until the event ordering domain
and the idempotency key are defined — `decisions.md` **D-011**. Writing them against a guessed key
would encode a silent architectural decision.

Currently empty. The first protocol tests arrive with V0.6.
