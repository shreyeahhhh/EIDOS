# EIDOS — Execution Intelligence & Dynamic Orchestration System

> EIDOS is a model-independent adaptive AI runtime that dynamically plans, orchestrates, evaluates,
> and optimizes multi-agent workflows using A2A, MCP, LangGraph, and Agentic RAG.

*(Description taken verbatim from the project handoff, §1.)*

## Status

**Bootstrap — architecture only. No EIDOS runtime behaviour is implemented yet.**

This repository currently contains the project rules, the architecture knowledge base, the decision
record, and empty package boundaries. There is no planner, no validator, no compiler, no runtime,
no agents, no A2A, no MCP, no RAG, no persistence and no frontend.

Current status and the milestone ladder: [progress.md](progress.md).
Decisions and unresolved questions: [decisions.md](decisions.md).
Rules every contributor (human or agent) follows: [CLAUDE.md](CLAUDE.md).

No performance, quality or latency numbers appear anywhere in this repository, because no
measurement has been taken. Per the project rules, every metric published must come from an actual
recorded run.

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

Currently declared: `pydantic>=2` (contracts), `pytest` (tests).

## Development

```bash
python -m pytest
```

Collects zero tests today. That is the expected result for the bootstrap milestone — it verifies the
src layout and test roots are wired, nothing more.
