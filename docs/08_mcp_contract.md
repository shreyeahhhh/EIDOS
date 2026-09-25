# 08 — MCP Contract

**Status:** DERIVED — **V1.2 (decisions.md D-203, 2026-09-24): scope frozen; Step 2 (2026-09-25) implemented only the pure, transport-free tool contracts and deterministic admission (§4a), and (Step 3) their recording as additive facts (§4b); no MCP client, server or
dependency exists yet.** Earlier deferred and unassigned (D-184, 2026-09-22).
**Derived from:** handoff §27, §28, §29, §33, §50, §63
**Authority:** This document is derived from `EIDOS_CLAUDE_CODE_HANDOFF.md` and subordinate to it.
If this document and the handoff conflict, stop and report the conflict to the human owner.

> **No MCP is implemented.** There is no `eidos.mcp` package, no MCP dependency and no tool provider; only
> the transport-free contracts, admission (§4a) and the recording seam for tool-call facts (§4b) exist. §50 named this V0.7 in the handoff's own original sequence; the owner has since
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

## 4a. Tool contracts and admission as implemented (V1.2 Step 2, D-203)

Pure and transport-free: no I/O, no clock, no process, no MCP. `ToolDescriptor`, `ToolRegistry` and `ToolArgumentSpec` (`eidos.capabilities`) are the **pinned allowlist** EIDOS writes itself; a
tool's read-only declaration, action, arguments and bounds are the entry's, and nothing a provider reports about itself is ever read. `ToolPort`, `ToolRequest`, `ToolResult`, `ToolFailure` and
`bound_result` (`eidos.agents`) are the seam, shaped like `ModelPort` (D-135); a failure is returned, never raised. `admit_tool_call` (`eidos.policy`) is a total pure function returning one typed
decision, `INVOKE`, `SERVE_STORED` or a typed `DENY`, after one precondition, an explicit finite integer `max_tool_calls` (an unset value is unresolved configuration, denied `BUDGET_UNRESOLVED`, and is never unlimited, never zero and never a default; D-205
ruling 1), decided before duplicate detection so that a stored duplicate is not served either (D-205 item 2), applying these rules in this fixed order, the first failure deciding the denial: unknown tool, not read-only, action not exactly among
`allowed_actions`, `autonomy_level` below 1, arguments not matching the entry's schema, an exact duplicate `(execution_id, tool_id, args_digest)` with a stored result (served with no invocation and
no budget), and the per-plan-attempt `max_tool_calls` budget scoped `(execution_id, plan_id)`. Tool policy is call-time only; a plan never names a tool. Where D-203 was silent, the readings taken are
recorded as **D-205** (partly ruled 2026-09-25; the rest Open).

## 4b. Tool-call facts as recorded (V1.2 Step 3, D-203, D-206)

A tool call is recorded without a new event type: as an additive `tool_calls` tuple of `ToolCallFacts` on the `NODE_SETTLED` of the work node that made it, in call order, exactly as model calls are (D-160).
`MCP_TOOL_CALLED` stays an unused vocabulary slot. A fact holds the tool id as the caller named it; one of eight typed outcomes (`result`; the five invocation failures `unavailable`, `timeout`, `tool_error`,
`malformed_result` and `result_too_large`; `served_stored`, a duplicate answered from a stored result; and `denied`, with one of the seven admission denial reasons); the request digest; the artifact references the
answer became; the answer's size in bytes; and the elapsed milliseconds. Each kind carries only what can be true of it. The reducer folds `tool_calls_used` from the calls that reached a tool (the result and the five
failures) and nothing else, so a served duplicate and a denial cost nothing; it stays the whole-mission running total (D-204 item 2), and each step's own facts give the per-attempt detail. Replay reproduces the facts
and the counter from the log alone, with no tool and no transport; a log written before the field existed reads back unchanged. Nothing here invokes a tool: the facts reach the recorder through the tracker's tool
collection, and producing them from admission decisions and tool results is Step 4.

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
| D-009 | `max_tool_calls` value and its source of authority. **V1.2 (D-205 ruling 1):** an unset value is unresolved configuration and admission denies it (`BUDGET_UNRESOLVED`); no default or ceiling is invented, and the value and its source of authority stay Open |
| — | **Resolved (D-203):** EIDOS is a client only, over stdio, with a minimal hand-rolled stdlib client; no SDK. (Was: which MCP SDK, and whether EIDOS hosts tools as an MCP server, consumes them as a client, or both.) |
| — | Concrete argument and result schemas for `search_documents` and `retrieve_evidence` — deliberately unspecified until V0.7, and coupled to the RAG design (`09_rag_architecture.md`). **Narrowed (D-203):** V1.2 uses only `search_documents` (keyword matching, no RAG); its schemas are fixed at Step 2 of the V1.2 order; `retrieve_evidence` stays deferred. **Step 2 (2026-09-25):** the argument-schema *representation* is fixed (flat string and integer arguments with explicit bounds); the concrete `search_documents` entry exists only as a test-support instance; **D-205 ruling 3:** no production value is invented, and Step 4 establishes the concrete production and test fixture location and documents its timeout, result-size bound and schema-digest treatment |
| — | Whether tool-level policy is evaluated at plan-validation time (§14 "policy validation"), at call time, or both. **Call time only in V1.2 (D-203); the plan-validation POLICY stage stays `NOT_APPLICABLE`, D-110** |
| — | Default timeout values, and what a duplicate tool call means — idempotency at the tool boundary is required by the §50 test list but its key is not defined. **Duplicate call resolved (D-203 ruling 5):** the key is `(execution_id, tool_id, args_digest)`; a duplicate is served from the stored artifact, invokes no tool and uses no invocation budget. Timeouts are set per allowlist entry and a request has no default (Step 2); the concrete `search_documents` values are Step 4's to establish and document (D-205 ruling 3) |

## Out of scope for this document

Agentic RAG behaviour behind the retrieval tools (`09_rag_architecture.md`), the autonomy model
(`10_reliability.md`), the A2A agent boundary (`07_a2a_contract.md`).
