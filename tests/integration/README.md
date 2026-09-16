# tests/integration

**Layer definition (handoff §62):** LangGraph, Qdrant, MCP, A2A, database.

Integration tests verify that two or more real components work together, including components that
perform I/O. They are distinct from `tests/protocol/`, which tests protocol *lifecycle* behaviour,
and from `tests/scenarios/`, which tests whole missions.

## What belongs here

| Subject | Milestone |
|---|---|
| Compiled plan executing on the LangGraph runtime with mock agents | V0.3 |
| Local agents wired into the runtime end-to-end | V0.4 |
| Checkpointing and replay against real state storage | V0.5 |
| Qdrant retrieval, embeddings, reranking | V0.8 |
| Database/storage layer, once persistence exists | open — decision D-017 |

## Rules

- No component under test is mocked away just to make the test pass. If a dependency must be
  substituted, the substitution is the point of the test, not a convenience.
- Never suppress a runtime error to get green (CLAUDE.md §6).

Currently empty. The first integration tests arrive with V0.3.
