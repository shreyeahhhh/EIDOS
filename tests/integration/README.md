# tests/integration

**Layer definition (handoff §62):** LangGraph, Qdrant, MCP, A2A, database.

Integration tests verify that two or more real components work together, including components that
perform I/O. They are distinct from `tests/protocol/`, which tests protocol *lifecycle* behaviour,
and from `tests/scenarios/`, which tests whole missions.

## What belongs here

| Subject | Milestone |
|---|---|
| Compiled plan executing on the LangGraph runtime with mock agents | V0.3 — `tests/integration/langgraph/` (Step 4: the spike, the adapter, and conformance with the reference executor) |
| The whole core unit suite run with the LangGraph family unimportable (D-116) | V0.3, re-established at V0.4 — `tests/integration/langgraph/test_unit_suite_without_langgraph.py` |
| The local-runtime provider adapter against a local fake runtime over real sockets; real-model tests are an explicit opt-in (`-m real_model`), deselected by default and never skipped | V0.4 — `tests/integration/providers/` (Step 8) |
| Local agents wired into the runtime end-to-end | V0.4 — with a scripted model in `tests/scenarios/`; with a real model in `tests/integration/providers/test_ollama_real.py` (opt-in; the committed configuration, run once, finished with a verifier PASS: progress.md, D-149 and D-150) |
| Checkpointing and replay against real state storage | V0.5 |
| Semantic retrieval behind the process boundary: the real pinned model in the isolated Python 3.13 interpreter (`-m real_model`, deselected by default, never skipped, fail loudly), and, with a stub model and no model library, the boundary as an isolation guarantee and a semantic mission recorded and replayed with the worker gone | V1.3 Step 5 (D-226) — `tests/integration/semantic/` |
| Qdrant retrieval, reranking | deferred (D-222, D-226 ruling 3): not built, not assigned |
| The V1.4 storage layer: one repository contract run on the in-memory and, with `-m postgres` and `EIDOS_TEST_DATABASE_URL`, the PostgreSQL storage; PostgreSQL-only tests (migrations, deny-all RLS, restart and recovery, a race between two processes) | V1.4-B — `tests/integration/persistence/` (D-017 is answered for V1.4 by D-230; snapshots and other stores stay open) |
| The V1.4 HTTP surface end to end over the in-memory service, real JWT verification and a scripted model; the whole service path, restart, a store that fails part-way and concurrency | V1.4-B — `tests/integration/api/`, `tests/integration/service/` |
| `run_with_replanning`'s optional `tracker` under a forced replan | V1.4-B — `tests/integration/planning/test_v1_replanning_tracker.py` (D-231) |

## Rules

- No component under test is mocked away just to make the test pass. If a dependency must be
  substituted, the substitution is the point of the test, not a convenience.
- Never suppress a runtime error to get green (CLAUDE.md §6).

`tests/integration/langgraph/` needs the `langgraph` extra, which the `dev` extra includes. These tests import LangGraph
directly and fail loudly if it is missing; they are never skipped. Core tests in `tests/unit/` run without it.
