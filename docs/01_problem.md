# 01 — Problem

**Status:** DERIVED — current
**Derived from:** handoff §2, §3, §4, §44, §45, §46, §69, §71, §83
**Authority:** This document is derived from `EIDOS_CLAUDE_CODE_HANDOFF.md` and subordinate to it.
If this document and the handoff conflict, stop and report the conflict to the human owner.

---

## 1. The problem

Most AI systems answer the question *"can an AI perform this task?"*

EIDOS addresses a higher-level problem:

> Given a human objective and a set of available AI agents, models, tools, knowledge sources and
> constraints, how should the system decide the most appropriate way to execute that objective?

EIDOS therefore operates at the level of **execution strategy**, not task execution.

## 2. Why the obvious approach is not enough

Frontier models and commercial coding agents already do:

```text
Prompt -> Agent -> Subagents -> Tools -> Result
```

A system whose novelty is that chain is increasingly easy for commercial systems to reproduce. So
EIDOS must not compete with frontier models on raw intelligence.

Nor can novelty come from the infrastructure list. Existing projects already cover agent control
planes, A2A/MCP gateways, agent registries, agent runtimes, agent governance, agent compilers,
adaptive routing, MCP security and multi-agent software development (§45). `A2A + MCP + LangGraph +
RAG + routing` is infrastructure, not differentiation.

## 3. The position EIDOS takes

**Models and agents are replaceable capabilities.** EIDOS owns the layer above them:

- task representation
- capability selection
- strategy generation
- strategy comparison
- constraint enforcement
- execution coordination
- verification
- reliability
- resource optimization
- historical strategy memory
- execution evaluation
- future strategy improvement

The system must remain useful when the underlying models change.

The intended differentiation, stated plainly (§45):

> **Adaptive execution-strategy intelligence based on measured outcomes.**

## 4. The core loop

```text
Human Objective
      -> Task Genome
      -> Capability Discovery
      -> Candidate Strategy Generation
      -> Plan Validation
      -> Strategy Selection
      -> Execution
      -> Verification
      -> Evaluation
      -> Execution Memory
      -> Better Future Strategy Selection
```

Governing philosophy:

> **The LLM proposes; the runtime validates; the agents execute; the evaluator measures; the system
> learns.**

## 5. What EIDOS is not

EIDOS is **not primarily** a chatbot, an AI website builder, a coding assistant, a fixed multi-agent
workflow, a generic agent marketplace, a generic MCP gateway, a generic A2A gateway, or a simple RAG
application. Any of these may appear as a demonstration or a component, but none is EIDOS's
identity.

### Specifically not an AI software factory

An earlier idea — user gives a website prompt, multiple agents build the website — is territory
already occupied. The repository `githubphilomath/main-project` is explicitly a Multi-Agent
Autonomous Software Development Platform with an Orchestrator, Requirement Analysis, Architecture,
Coding, Debugging, Testing, Documentation and Deployment agents, plus LangGraph, an agent registry,
triple RAG, FastAPI, PostgreSQL/Supabase, Chroma, logging, monitoring, evaluation, retry/recovery
and Docker.

Its fundamental question is: *can multiple AI agents autonomously build a software application?*

EIDOS's question is:

> Given multiple possible agent capabilities and execution plans, which strategy should be used for
> this task, under specific quality, latency, resource, risk and autonomy constraints, and how can
> future strategy selection improve from observed outcomes?

EIDOS may **execute** software-building workflows, but the runtime itself must remain
domain-agnostic. This is invariant 10.

## 6. Who it is for

**Primary persona** — an AI/IT solutions architect, technical project lead or enterprise technical
decision-maker with a complicated goal who does not want to coordinate multiple AI systems by hand.
Their interaction is: *"Here is what I need accomplished. Here are the constraints and permissions.
Figure out how to do it reliably."* To them EIDOS is an AI mission planner and execution manager.

**Secondary persona** — an AI platform engineer who registers agents, exposes capabilities,
registers MCP tools, monitors performance, observes A2A interactions, evaluates models, inspects
execution traces, understands routing decisions and manages policies.

The primary user should not need to know what A2A, MCP, LangGraph or RAG are.

## 7. Demonstration domains

Strong example workloads (§71): migration readiness assessment, incident investigation, architecture
review, security investigation, business/technical risk analysis, complex document analysis, and
software development as a *secondary* workload.

The defining characteristic is that the user supplies an **objective**, not a command aimed at one
specific agent.

## 8. Why this is future-facing

The project is aimed at the later stages of this trajectory (§69):

```text
AI generates answers -> AI executes tasks -> AI agents collaborate
-> Systems manage agent ecosystems -> Systems optimize agent collaboration
-> Systems learn which collaboration strategies work
```

## 9. The architectural thesis

> **Don't build an AI that merely knows how to perform a task. Build a runtime that knows how to
> decide how AI should perform the task, verifies whether that decision worked, and uses the
> evidence to make better decisions in the future.**

---

## Open questions

None specific to this document. The problem statement is fully specified in the handoff.

## Out of scope for this document

Product requirements (`02_prd.md`), architecture (`03_architecture.md`), and any implementation
concern.
