# 02 — Product Requirements

**Status:** DERIVED — current
**Derived from:** handoff §4, §5, §41, §42, §43, §47, §48, §49, §51, §52, §53, §54, §70, §72, §73, §74
**Authority:** This document is derived from `EIDOS_CLAUDE_CODE_HANDOFF.md` and subordinate to it.
If this document and the handoff conflict, stop and report the conflict to the human owner.

---

## 1. Product category

EIDOS is an **Adaptive Agent Orchestration & Optimization Runtime**.

## 2. Core user experience

The user interacts with a **Mission Center**, not a chat interface.

A mission is defined by:

```text
Goal
Constraints
Required confidence
Maximum latency
Resource/token budget
Risk tolerance
Allowed actions
Evidence requirements
Human-approval requirements
```

Example mission as the user states it:

```text
GOAL              Assess migration readiness.
CONFIDENCE        >= 90%
MAXIMUM TIME      10 minutes
RISK              Medium
ALLOWED ACTIONS   Read documents / Read repository / Query monitoring data
DISALLOWED        Modify production / Delete resources
```

EIDOS converts this into a structured Task Genome (`04_task_genome.md`).

## 3. What the ordinary user sees

```text
Goal -> Strategy -> Execution -> Evidence -> Result
```

Technical detail is available **on demand**, never as the default interface:

```text
Goal -> Task Genome -> Strategy -> LangGraph -> A2A -> MCP -> RAG -> Telemetry
```

The primary interface must not look like `A2A / MCP / LangGraph / Qdrant / Redis / Pydantic`. Those
are implementation details (§42).

## 4. Frontend views

Required views (§41), all deferred to V1.3:

| View | Purpose |
|---|---|
| **Mission Center** | User enters goal, constraints, permissions |
| **Strategy View** | Candidate strategies and the reason one was selected |
| **Live Execution** | Agent activity, A2A communications, MCP calls, RAG activity, verification, retries, replanning |
| **Evidence Explorer** | Navigate conclusion → evidence → source → retrieval query → agent → verification |
| **Execution Replay** | The mission as a timeline, replayed from recorded events |
| **Strategy Lab** | Historical strategy performance |
| **Failure Lab** | Deliberate failure injection: agent unavailable, tool unavailable, bad retrieval, conflicting evidence, malformed output, timeout, budget exceeded, policy violation |

Design principle (§72): the frontend makes the hidden AI architecture understandable. Show actual
system events. Avoid animated "AI thinking" visuals.

## 5. Product-level requirements

### 5.1 Reliability is visible, not assumed

EIDOS must be able to say **"Mission could not satisfy the requested reliability contract"** and
must not force a confident-looking answer merely because a model produced output (§30, §47).

Required:

```text
Evidence confidence: 0.88
Required:            0.90
STATUS: Insufficient evidence
```

Forbidden:

```text
Answer confidence: 88%
Completed successfully
```

### 5.2 Every conclusion is traceable

Conclusion → evidence → source → retrieval query → agent → tool → verification (§74). This is what
makes the output trustworthy.

### 5.3 Every mission is replayable

A completed mission should be replayable from recorded events. **Replay consumes recorded events; it
does not re-run the agents** (§73).

### 5.4 Numbers are measured, never asserted

Every numerical claim in the README, the docs or any portfolio material must come from an actual
experiment (§67). No fabricated results.

## 6. MVP definition

The MVP proves only this chain (§49):

```text
Task -> Task Genome -> 2-3 candidate strategies -> Plan validation
-> LangGraph execution -> Evaluation -> Execution history
```

With exactly three logical agents: **Research, Analysis, Verification**. Not 10+.

> **Open:** the flagship demo (§43) and the candidate strategies (§16) use five capabilities —
> Research, Security, Architecture, Analysis, Verification — which contradicts the three named here.
> See `decisions.md` D-006. Unresolved.

## 7. Scope control

The system has many possible components: A2A, MCP, LangGraph, RAG, Qdrant, caching, agent registry,
strategy memory, telemetry, governance, failure recovery, frontend, deployment. **Do not implement
them simultaneously.** The first objective is a functioning vertical slice (§48).

The build order is the milestone ladder in `progress.md`, taken from §50.

## 8. Flagship demonstration

Mission: *"Assess whether our application is ready for migration to a new infrastructure."* (§43)

EIDOS determines the required capabilities, generates candidate strategies, executes one, and — if
verification fails on insufficient evidence — replans, retrieves more, and re-verifies. The final
output reports the result, the confidence, the evidence count, and the execution facts (agents, A2A
interactions, MCP calls, RAG rounds, retries, latency, policy violations, human interventions).

Those output fields are defined; **their values must come from a real run.**

## 9. Zero-cost requirement

The prototype must be buildable without spending money (§51). Intended local stack: Ollama with a
local open model, sentence-transformers embeddings, local Qdrant, SQLite initially, optional
in-process or local Redis cache, FastAPI, LangGraph, A2A, MCP, OpenTelemetry with local structured
logs, React/TypeScript or Streamlit for an early prototype, Docker, Pytest, Git/GitHub, GitHub
Actions.

No paid LLM API is required for the core prototype. **Software cost can be zero; compute is not
free** — the owner's laptop provides it.

Only dependencies required by the current milestone are declared. See `decisions.md` D-003.

## 10. API concept

Eventually (§53):

```http
POST /missions
{
  "goal": "Assess migration readiness",
  "constraints": {
    "minimum_confidence": 0.90,
    "maximum_latency_seconds": 600,
    "risk_tolerance": "medium"
  }
}
```

returning a mission id, status, strategy id, confidence and execution facts.

The handoff states explicitly that this is **conceptual and the exact API schema must be formally
specified later**. It is therefore not treated as a contract.

## 11. Deployment direction

Local-first, cloud-ready, model-independent, service-oriented (§52). Progression: local Python →
Docker Compose → single cloud VM → API + workers + database → separate A2A agent services →
distributed deployment. **Do not jump to Kubernetes** and do not prematurely build distributed cloud
infrastructure.

## 12. Multi-tenancy

The first prototype may be single-user, but the architecture must not assume that forever. Data
models should conceptually include `tenant_id`, `mission_id`, `execution_id`, `agent_id`,
`timestamp`. Authentication and multi-tenancy are implemented later — **the MVP must not become an
authentication project** (§54).

> **Open:** whether V0.1 contracts carry `tenant_id` as a real field now. See `decisions.md` D-019.

---

## Open questions

| Id | Question |
|---|---|
| D-006 | MVP agent set — three capabilities (§49) or five (§16, §43)? |
| D-019 | Does `tenant_id` appear in V0.1 models? |
| D-022 | Frontend stack — React/TypeScript or Streamlit for the early prototype? |
| D-013 | How mission constraints map onto TaskGenome vs ReliabilityContract |

## Out of scope for this document

Architecture (`03_architecture.md`), contracts (`04`–`09`), reliability mechanics
(`10_reliability.md`), evaluation (`11_evaluation.md`).
