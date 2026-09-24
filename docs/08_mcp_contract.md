# 08 — MCP Contract

**Status:** DERIVED — **V1.2 (decisions.md D-203, 2026-09-24): scope frozen, nothing implemented yet.** Earlier deferred and
unassigned (D-184, 2026-09-22).
**Derived from:** handoff §27, §28, §29, §33, §50, §63
**Authority:** This document is derived from `EIDOS_CLAUDE_CODE_HANDOFF.md` and subordinate to it.
If this document and the handoff conflict, stop and report the conflict to the human owner.

> **Nothing in this document is implemented.** There is no `eidos.mcp` package, no MCP dependency
> and no tool. §50 named this V0.7 in the handoff's own original sequence; the owner has since
> redefined V0.7 as Strategy & Candidate Generation (`decisions.md` D-178 onward) and ruled, as
> **D-184**, that MCP is not renumbered into the V0.7–V1.0 strategy-intelligence sequence — it gets a
> milestone only when a concrete requirement or benchmark needs it. **D-203 then assigned it to V1.2**, with one pinned read-only tool, a client only and a hand-rolled
> stdlib stdio client, no SDK, no new plan step and no new event (tool calls are `tool_calls` facts on `NODE_SETTLED`). See `decisions.md` D-027, D-184, D-203.

---

## 1. What MCP is for

MCP is the **tool/resource boundary**. Agents do not directly access every environment capability
(§27):

```text
Agent -> MCP -> Permission / Policy -> Tool or resource
```

Every tool call passes through policy. This is the mechanism behind invariant 14 — "can perform" and
"is allowed to perform" are separate, deterministic checks.

## 2. Tool set — deliberately small

Initial tools (§27):

```text
search_documents
retrieve_evidence
```

Later, when justified:

```text
repository.search
database.query
file.read
monitoring.query
```

> **Do not create 20 MCP tools in V1.** (§27)

V0.7 adds only 2–3 real tools (§50). Adding a tool beyond that set requires human approval per
CLAUDE.md §3.

## 3. Tool metadata

Every tool should eventually carry metadata equivalent to (§28):

```text
tool name
description
allowed agents
read/write class
risk level
cacheability
timeout
```

## 4. Policy questions the system must answer

The policy system determines (§28):

```text
Can this agent use this tool?
Can it use it now?
Can it use it without approval?
```

These map onto the autonomy model in §29 (see `10_reliability.md`): read actions are automatic,
configuration changes require human approval, deletion of a critical resource is blocked.

`read/write class` and `risk level` are the tool-side inputs to that decision. The **enforcement is
deterministic and lives in code, never in a prompt** (invariant 14).

## 5. Telemetry

`MCP_TOOL_CALLED` is a named structured event (§33), and `mcp_calls` is one of the per-mission
measurements. The tool boundary is therefore also a measurement point: tool calls are budgeted
(`max_tool_calls`, §14/§32) and counted (§33).

`cacheability` in the tool metadata connects to the tool-result cache level of the context
optimization layer (§35).

## 6. Required tests

§50 names the V0.7 test set explicitly:

```text
successful call
invalid arguments
timeout
unavailable tool
unauthorized call
duplicate call
```

§63's minimum failure-scenario list adds: MCP tool timeout, MCP tool unavailable, malformed tool
output, tool budget exceeded.

These belong in `tests/protocol/`.

## 7. Prerequisites

| Prerequisite | Where |
|---|---|
| Bound values including `max_tool_calls`, and where bounds originate | `decisions.md` D-009 |
| Minimal deterministic tool admission (allowlist, exact `allowed_actions` match, `autonomy_level` >= 1, read-only, `max_tool_calls`) | D-203, V1.2. The general policy engine and autonomy model stay deferred and unassigned |
| MCP SDK / server-client topology choice | Resolved by D-203: client only, stdio, hand-rolled stdlib, no SDK |

---

## Open questions

| Id | Question |
|---|---|
| D-009 | `max_tool_calls` value and its source of authority |
| — | **Resolved (D-203):** EIDOS is a client only, over stdio, with a minimal hand-rolled stdlib client; no SDK. (Was: which MCP SDK, and whether EIDOS hosts tools as an MCP server, consumes them as a client, or both.) |
| — | Concrete argument and result schemas for `search_documents` and `retrieve_evidence` — deliberately unspecified until V0.7, and coupled to the RAG design (`09_rag_architecture.md`). **Narrowed (D-203):** V1.2 uses only `search_documents` (keyword matching, no RAG); its schemas are fixed at Step 2 of the V1.2 order; `retrieve_evidence` stays deferred |
| — | Whether tool-level policy is evaluated at plan-validation time (§14 "policy validation"), at call time, or both. **Call time only in V1.2 (D-203); the plan-validation POLICY stage stays `NOT_APPLICABLE`, D-110** |
| — | Default timeout values, and what a duplicate tool call means — idempotency at the tool boundary is required by the §50 test list but its key is not defined. **Duplicate call resolved (D-203 ruling 5):** the key is `(execution_id, tool_id, args_digest)`; a duplicate is served from the stored artifact, invokes no tool and uses no invocation budget. Default timeouts stay open until Step 2 (set per tool descriptor) |

## Out of scope for this document

Agentic RAG behaviour behind the retrieval tools (`09_rag_architecture.md`), the autonomy model
(`10_reliability.md`), the A2A agent boundary (`07_a2a_contract.md`).
