# EIDOS — Execution Intelligence & Dynamic Orchestration System

> EIDOS is a model-independent adaptive AI runtime that dynamically plans, orchestrates, evaluates,
> and optimizes multi-agent workflows using A2A, MCP, LangGraph, and Agentic RAG.

*(Description taken verbatim from the project handoff, §1.)*

EIDOS works at the level of **execution strategy**. Its question is not "can an AI do this task?" but
*given an objective, the available agents, models, tools and constraints, how should the work be done —
and can the result be checked?* Its governing idea: **the LLM proposes; the runtime validates; the agents
execute; the verifier checks; the whole run is recorded and replayable.**

## Contents

- [What you can do with it](#what-you-can-do-with-it)
- [How a mission runs](#how-a-mission-runs)
- [Repository layout](#repository-layout)
- [Getting started](#getting-started)
- [Documentation](#documentation)
- [Project rules](#project-rules)
- [Status](#status)
- [What EIDOS is not](#what-eidos-is-not)

## What you can do with it

Sign in to the web app, give EIDOS a goal (optionally with your own text files, or a public web page to
read), and get back an answer that **names its sources**, with the plan, every step and every source open
to inspection and replay. The final check is that the answer is well-formed and cites sources that really
exist — it does **not** judge whether the answer is correct, and the app says so.

## How a mission runs

```text
Goal -> Task Genome -> Candidate strategies -> Plan (validated before it runs)
     -> Execution under hard limits -> Verification -> Answer + sources
     (a failed step -> a new plan, or an honest stop; every event is recorded, so a run replays without re-running agents)
```

Three logical agents (Research, Analysis, Verification), one optional tool (a safe web-page reader), two
model providers behind one interface (Ollama for local development, Groq for hosted use).

## Repository layout

| Path | What is there |
|---|---|
| `src/eidos/` | The Python package: typed contracts, plan validator, compiler and runtime, event log and state reducer, agents, strategy generation / selection / expansion, replanning, telemetry and experience memory, model providers, the web-fetch tool, and the product backend (`api`, `service`, `persistence`) |
| `frontend/` | The Next.js web app — landing page, sign-up and sign-in, the mission workspace. See [frontend/README.md](frontend/README.md) |
| `tests/` | `unit`, `integration`, `protocol`, `scenarios` |
| `docs/` | The engineering knowledge base, derived from the handoff |
| `Dockerfile`, `render.yaml` | Backend container and Render deployment |

## Getting started

**Tests** (the default run needs no database and no credential):

```bash
python -m pytest
```

Opt-in suites are never skipped silently: `-m postgres` (needs `EIDOS_TEST_DATABASE_URL` pointing at a
*disposable* database — the fixture drops and recreates the `eidos` schema) and `-m real_model` (needs a
local model runtime). Current test counts live in [progress.md](progress.md).

**Backend:** how to run it, with its environment variables, is in
[docs/13_product_backend.md](docs/13_product_backend.md) (section 12.3) and
[docs/14_deployment.md](docs/14_deployment.md).

**Frontend:**

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000 (copy .env.local.example to .env.local first)
npm test             # also: npm run typecheck, npm run lint, npm run build
```

## Documentation

The canonical specification is [`EIDOS_CLAUDE_CODE_HANDOFF.md`](EIDOS_CLAUDE_CODE_HANDOFF.md); everything in
`docs/` is derived from it and subordinate to it.

| Document | Scope |
|---|---|
| [docs/01_problem.md](docs/01_problem.md) · [02_prd.md](docs/02_prd.md) | The problem, and the product requirements |
| [docs/03_architecture.md](docs/03_architecture.md) | System architecture and component boundaries |
| [docs/04_task_genome.md](docs/04_task_genome.md) · [05_plan_dsl.md](docs/05_plan_dsl.md) · [06_mission_state.md](docs/06_mission_state.md) | The Task Genome, the bounded Plan DSL and its validation, MissionState / events / reducer |
| [docs/07_a2a_contract.md](docs/07_a2a_contract.md) · [08_mcp_contract.md](docs/08_mcp_contract.md) · [09_rag_architecture.md](docs/09_rag_architecture.md) | The A2A boundary, the tool boundary, the knowledge / evidence layer |
| [docs/10_reliability.md](docs/10_reliability.md) · [11_evaluation.md](docs/11_evaluation.md) · [12_architecture_invariants.md](docs/12_architecture_invariants.md) | Reliability and governance, telemetry and evaluation, the hard invariants |
| [docs/13_product_backend.md](docs/13_product_backend.md) · [14_deployment.md](docs/14_deployment.md) | The product backend (API, schema, tenancy), and deployment |

## Project rules

[CLAUDE.md](CLAUDE.md) holds the rules every contributor, human or agent, follows: the architecture
invariants, the explore → plan → implement → test → verify → commit workflow, and the honesty rules (no
fabricated numbers; never weaken or skip a failing test). [decisions.md](decisions.md) records every
decision and open question; [progress.md](progress.md) is the authoritative, current build log.

## Status

Built and tested: the typed contracts, validator, compiler and runtime; the event log, replay and state
reducer; the three agents with verification; strategy generation, selection and expansion; within-mission
replanning; telemetry and experience memory; the product backend (FastAPI over Supabase PostgreSQL, JWT
auth, per-user workspaces); the web app; the web-fetch tool. Docker and Render configuration exist, but
**actual deployment has not been verified.**

Deliberately deferred, not built: adaptive learning across missions, a general policy engine and
human-approval flow, an MCP server in the deployed service, knowledge-base management, and per-user rate
limits. No quality metric is published anywhere in this repository: every metric in a document comes from
a recorded run, and the one real-model run is logged in [progress.md](progress.md) as a record, not a
benchmark.

## What EIDOS is not

Not a chatbot, a coding assistant, a website builder, a fixed multi-agent workflow, an agent marketplace,
an MCP or A2A gateway, or a simple RAG application. The runtime stays domain-agnostic.
