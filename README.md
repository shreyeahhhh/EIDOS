# EIDOS — Execution Intelligence & Dynamic Orchestration System

> EIDOS is a model-independent adaptive AI runtime that dynamically plans, orchestrates, evaluates,
> and optimizes multi-agent workflows using A2A, MCP, LangGraph, and Agentic RAG.

*(Description taken verbatim from the project handoff, §1.)*

## Status

**V0.4 — real local agents; close-out review awaiting the owner.**

This repository contains the project rules, the architecture knowledge base, the decision record,
the V0.1 typed contracts (`eidos.contracts`), the V0.2 plan validator (`eidos.validation`), the V0.3
compiler and runtime (`eidos.compiler`, `eidos.runtime` and the LangGraph backend
`eidos.backends.langgraph`), and the V0.4 capability registry, three read-only agents (Research,
Analysis and a deterministic Verification rule set), a single-pass baseline runner and one
local-model adapter. The baseline works end to end with a scripted model. With a real local model it
has been run: at the first output budget the first step failed (the reasoning model spent the whole budget before answering); at a larger one the second step failed the same
way; with 4,096 output tokens and a 240 s timeout one attempt finished and the verifier returned PASS (three rules, no quality measured). The opt-in test as committed still sets the smaller
budget — see [progress.md](progress.md), D-149 and D-150. There is no
planner, no state reducer, no A2A, no MCP, no RAG, no persistence, no API and no frontend.

Current status and the milestone ladder: [progress.md](progress.md).
Decisions and unresolved questions: [decisions.md](decisions.md).
Rules every contributor (human or agent) follows: [CLAUDE.md](CLAUDE.md).

No quality metric appears anywhere in this repository. One real-model run is recorded in
[progress.md](progress.md) as a record of what happened, not as a benchmark. Per the project rules,
every metric published must come from an actual recorded run.

## What EIDOS is

EIDOS operates at the level of **execution strategy**. Its question is not "can an AI perform this
task?" but:

> Given a human objective and a set of available AI agents, models, tools, knowledge sources and
> constraints, how should the system decide the most appropriate way to execute that objective?

Its governing philosophy: **the LLM proposes; the runtime validates; the agents execute; the
evaluator measures; the system learns.**

```text
Human Objective -> Task Genome -> Capability Discovery -> Candidate Strategy Generation
  -> Plan Validation -> Strategy Selection -> Execution -> Verification -> Evaluation
  -> Execution Memory -> better future strategy selection
```

## What EIDOS is not

Not a chatbot, not a coding assistant, not a website builder, not a fixed multi-agent workflow, not
an agent marketplace, not an MCP or A2A gateway, and not a simple RAG application. It is also
explicitly not an "AI software development factory" — EIDOS may *execute* a software workflow, but
the runtime itself stays domain-agnostic.

## Documentation

The canonical specification is [`EIDOS_CLAUDE_CODE_HANDOFF.md`](EIDOS_CLAUDE_CODE_HANDOFF.md).
Everything in `docs/` is derived from it and subordinate to it.

| Document | Scope |
|---|---|
| [docs/01_problem.md](docs/01_problem.md) | The problem EIDOS addresses and why it exists |
| [docs/02_prd.md](docs/02_prd.md) | Product requirements, personas, user experience |
| [docs/03_architecture.md](docs/03_architecture.md) | System architecture and component boundaries |
| [docs/04_task_genome.md](docs/04_task_genome.md) | The Task Genome contract |
| [docs/05_plan_dsl.md](docs/05_plan_dsl.md) | The bounded Plan DSL and its validation pipeline |
| [docs/06_mission_state.md](docs/06_mission_state.md) | MissionState ownership, events, reducer |
| [docs/07_a2a_contract.md](docs/07_a2a_contract.md) | A2A boundary contract (deferred to V0.6) |
| [docs/08_mcp_contract.md](docs/08_mcp_contract.md) | MCP tool boundary contract (deferred to V0.7) |
| [docs/09_rag_architecture.md](docs/09_rag_architecture.md) | Agentic RAG architecture (deferred to V0.8) |
| [docs/10_reliability.md](docs/10_reliability.md) | Reliability contract, verification, recovery, governance |
| [docs/11_evaluation.md](docs/11_evaluation.md) | Telemetry, evaluation framework, experiments |
| [docs/12_architecture_invariants.md](docs/12_architecture_invariants.md) | The hard invariants, normatively stated |

## Intended local stack

The prototype is designed to run entirely locally at zero software cost (compute is the laptop's).
The full intended stack is recorded in the handoff §51 and §76; it is **not** installed yet.
Only the dependencies required by the current milestone are declared in `pyproject.toml`.

Currently declared: `pydantic>=2` (contracts); the optional extra `langgraph` (the LangGraph backend, V0.3 — D-116);
`dev` (`pytest`, plus the `langgraph` extra). The core never imports LangGraph, and its tests run without it.

## Development

```bash
python -m pytest
```

Runs every test root. The current test state and counts are recorded in [progress.md](progress.md).
The two real-model tests are excluded from that run and never skipped; they are selected explicitly
with `-m real_model` and need a local model runtime the owner has installed
(see `tests/integration/providers/test_ollama_real.py`).
