# tests/integration

**Layer definition (handoff §62):** LangGraph, Qdrant, MCP, A2A, database.

Integration tests verify that two or more real components work together, including components that
perform I/O. They are distinct from `tests/protocol/`, which tests protocol *lifecycle* behaviour,
and from `tests/scenarios/`, which tests whole missions.

## What belongs here

| Subject | Milestone |
|---|---|
| Compiled plan executing on the LangGraph runtime with mock agents | V0.3 — `tests/integration/langgraph/` (Step 4: the spike, the adapter, and conformance with the reference executor) |
| The local-runtime provider adapter against a local fake runtime over real sockets; real-model tests are an explicit opt-in (`-m real_model`), deselected by default and never skipped | V0.4 — `tests/integration/providers/` (Step 8) |
| Local agents wired into the runtime end-to-end | V0.4 |
| Checkpointing and replay against real state storage | V0.5 |
| Qdrant retrieval, embeddings, reranking | V0.8 |
| Database/storage layer, once persistence exists | open — decision D-017 |

## Rules

- No component under test is mocked away just to make the test pass. If a dependency must be
  substituted, the substitution is the point of the test, not a convenience.
- Never suppress a runtime error to get green (CLAUDE.md §6).

`tests/integration/langgraph/` needs the `langgraph` extra, which the `dev` extra includes. These tests import LangGraph
directly and fail loudly if it is missing; they are never skipped. Core tests in `tests/unit/` run without it.
