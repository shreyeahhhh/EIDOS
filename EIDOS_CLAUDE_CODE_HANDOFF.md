# EIDOS — Complete Engineering Handoff

## Handoff Purpose

This document is the canonical context for building **EIDOS**.

Claude Code must understand the complete product vision, architecture, constraints, risks, technical decisions, differentiation strategy, development methodology, and future deployment direction before modifying the repository.

The project is intentionally architecture-first.

The human owner wants to understand and demonstrate **AI systems engineering, agent orchestration, protocols, reliability, optimization, evaluation, and architecture**, rather than spending most of the project manually writing large amounts of application code.

Claude Code is an implementation/review/debugging partner.

Claude Code is **not the final architect**.

The architecture, contracts, invariants, boundaries, and research questions defined in this document must not be casually changed.

---

# 1. Project Identity

## Project name

**EIDOS**

## Full form

**Execution Intelligence & Dynamic Orchestration System**

## Short GitHub description

> EIDOS is a model-independent adaptive AI runtime that dynamically plans, orchestrates, evaluates, and optimizes multi-agent workflows using A2A, MCP, LangGraph, and Agentic RAG.

## Product category

EIDOS is an:

**Adaptive Agent Orchestration & Optimization Runtime**

It is **not primarily**:

- an AI chatbot,
- an AI website builder,
- a coding assistant,
- a fixed multi-agent workflow,
- a generic agent marketplace,
- a generic MCP gateway,
- a generic A2A gateway,
- a simple RAG application.

Those may be demonstrations or components, but they are not EIDOS's identity.

---

# 2. Core Product Idea

EIDOS solves a higher-level problem than “can an AI perform a task?”

The central question is:

> **Given a human objective and a set of available AI agents, models, tools, knowledge sources, and constraints, how should the system decide the most appropriate way to execute that objective?**

EIDOS therefore operates at the level of **execution strategy**.

The fundamental loop is:

```text
Human Objective
      ↓
Task Genome
      ↓
Capability Discovery
      ↓
Candidate Strategy Generation
      ↓
Plan Validation
      ↓
Strategy Selection
      ↓
Execution
      ↓
Verification
      ↓
Evaluation
      ↓
Execution Memory
      ↓
Better Future Strategy Selection
```

The core philosophy is:

> **The LLM proposes; the runtime validates; the agents execute; the evaluator measures; the system learns.**

---

# 3. Why This Project Exists

Modern frontier models and coding agents are increasingly capable of:

- decomposing complex tasks,
- delegating to subagents,
- using tools,
- searching information,
- writing software,
- executing commands,
- running long-lived workflows.

Therefore a project whose novelty is merely:

```text
Prompt
→ Agent
→ Subagents
→ Tools
→ Result
```

is increasingly easy for commercial systems such as Claude Code, Codex, and future model/agent systems to reproduce.

The project must therefore avoid competing with frontier models on raw intelligence.

Instead:

**Models and agents are treated as replaceable capabilities.**

EIDOS is responsible for:

- task representation,
- capability selection,
- strategy generation,
- strategy comparison,
- constraint enforcement,
- execution coordination,
- verification,
- reliability,
- resource optimization,
- historical strategy memory,
- execution evaluation,
- future strategy improvement.

The system should remain useful even when the underlying models change.

---

# 4. Target Personas

## Primary Persona

The primary target is an **AI/IT Solutions Architect, Technical Project Lead, or enterprise technical decision-maker**.

They have a complicated goal but do not want to manually coordinate multiple AI systems.

Their interaction is:

> “Here is what I need accomplished. Here are the constraints and permissions. Figure out how to do it reliably.”

Example:

> “Assess whether our application is ready for migration to a new infrastructure. Use our documentation, repository, and monitoring information. Do not modify production systems. Give me an evidence-backed assessment with at least 90% confidence.”

EIDOS is their **AI mission planner and execution manager**.

## Secondary Persona

The secondary persona is an **AI platform engineer / AI engineer**.

They care about:

- registering agents,
- exposing capabilities,
- registering MCP tools,
- monitoring performance,
- observing A2A interactions,
- evaluating models,
- inspecting execution traces,
- understanding routing decisions,
- managing policies.

## Important Product Decision

The primary user should not need to know what A2A, MCP, LangGraph or RAG are.

The UI should present:

```text
Goal
→ Strategy
→ Execution
→ Evidence
→ Result
```

Advanced technical details can be opened on demand:

```text
Goal
→ Task Genome
→ Strategy
→ LangGraph
→ A2A
→ MCP
→ RAG
→ Telemetry
```

---

# 5. User Experience

The user interacts with a **Mission Center**, not a traditional chat interface.

A mission contains:

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

Example:

```text
GOAL
Assess migration readiness.

CONFIDENCE
≥ 90%

MAXIMUM TIME
10 minutes

RISK
Medium

ALLOWED ACTIONS
Read documents
Read repository
Query monitoring data

DISALLOWED
Modify production
Delete resources
```

EIDOS converts this into a structured Task Genome.

---

# 6. Task Genome

The Task Genome is one of the central EIDOS concepts.

It converts natural-language intent into a structured representation.

It should contain fields conceptually equivalent to:

```text
goal
required_capabilities
information_dependencies
risk_level
quality_threshold
latency_budget
resource_budget
autonomy_level
evidence_requirements
allowed_actions
```

Example:

```json
{
  "goal": "Assess migration readiness",
  "required_capabilities": [
    "architecture_analysis",
    "security_analysis",
    "cost_analysis",
    "research",
    "verification"
  ],
  "risk_level": "medium",
  "quality_threshold": 0.90,
  "latency_budget_ms": 600000,
  "autonomy_level": 1,
  "allowed_actions": [
    "read_documents",
    "read_repository",
    "query_monitoring"
  ]
}
```

The Task Genome is a **contract**, not just metadata.

---

# 7. Agent Capability Model

Agents are not hard-coded into every workflow.

EIDOS maintains an Agent Capability Registry.

Example:

```text
Research Agent
  capabilities:
    research
    document_analysis
    evidence_extraction

Security Agent
  capabilities:
    vulnerability_analysis
    dependency_analysis

Analysis Agent
  capabilities:
    technical_analysis
    cost_analysis

Verification Agent
  capabilities:
    evidence_validation
    contradiction_detection
```

An agent should also expose metadata such as:

```text
agent_id
version
capabilities
supported_inputs
supported_outputs
required_permissions
supported_tools
historical_latency
historical_success
historical_verification_rate
availability
```

Potential providers include:

```text
Local open-source model
OpenAI model
Anthropic model
Google model
Specialized model
External remote agent
Human reviewer
```

The architecture must not assume that any single model remains dominant.

---

# 8. A2A's Role

**A2A means Agent2Agent.**

It is the communication layer between independent agent systems.

Conceptually:

```text
EIDOS
   │
   │ A2A
   ▼
Research Agent
   │
   │ performs work
   ▼
Result / Artifact
   │
   │ A2A
   ▼
EIDOS
```

A2A should be used at **meaningful independent-agent boundaries**.

Do not force every internal function call through A2A just to claim A2A support.

The architecture should be able to say:

> tightly coupled internal nodes can run locally; independently deployable agent capabilities use A2A.

A2A remote tasks have their own lifecycle and identifiers.

EIDOS must represent remote tasks separately from global mission state.

Suggested mapping:

```text
AgentTask
  agent_id
  a2a_task_id
  a2a_context_id
  status
  latest_artifact
  last_event
```

---

# 9. State Ownership Rule

This is a hard architectural invariant.

## MissionState is the only authoritative global state.

Agents must **never directly mutate MissionState**.

The architecture is:

```text
A2A events/results
        ↓
EIDOS event handling
        ↓
MissionState reducer
        ↓
LangGraph checkpoint/state
```

Remote agents can have their own internal state.

EIDOS only maintains the state necessary to reason about the mission.

This avoids multiple sources of truth.

---

# 10. State Synchronization Strategy

A major risk is reconciling:

```text
centralized LangGraph state
```

with:

```text
decentralized asynchronous A2A task lifecycle
```

Do not allow:

```text
LangGraph state
 ↕
A2A state
 ↕
Agent internal state
```

to become three competing global state systems.

Use:

```text
Global MissionState
+
Remote AgentTask records
+
Event-based synchronization
```

Every external event should contain some form of:

```text
event_id
a2a_task_id
sequence/version
timestamp
```

Events must be processed idempotently.

Duplicate event:

```text
already processed
→ ignore
```

Out-of-order/late event:

```text
validate against lifecycle
→ accept/reject deterministically
```

No agent should directly write the global mission state.

---

# 11. LangGraph's Role

LangGraph is the **execution runtime** for validated plans.

It should manage:

- execution state,
- sequencing,
- parallel branches,
- routing,
- retries,
- checkpoints,
- controlled replanning,
- termination.

LangGraph is **not** the strategy generator.

The pipeline is:

```text
LLM
 ↓
Plan DSL
 ↓
Validator
 ↓
Compiler
 ↓
LangGraph runtime
```

Never let the LLM directly generate executable LangGraph code.

---

# 12. Dynamic Graph Synthesis Risk

Do not let an LLM generate arbitrary runtime graph topology.

Bad:

```text
LLM
 ↓
arbitrary graph code
 ↓
LangGraph
```

This risks:

- un-debuggable workflows,
- accidental cycles,
- runaway branching,
- uncontrolled recursion,
- inconsistent state,
- excessive cost,
- difficult testing.

Instead, create a **bounded Mission Plan DSL**.

---

# 13. Plan DSL

The planner outputs a structured plan specification rather than Python/LangGraph code.

Example:

```json
{
  "type": "parallel",
  "steps": [
    {
      "type": "agent",
      "capability": "research"
    },
    {
      "type": "agent",
      "capability": "security_analysis"
    }
  ]
}
```

Allowed primitives should initially be:

```text
SEQUENTIAL
PARALLEL
ROUTE
VERIFY
RETRY
REPLAN
HUMAN_APPROVAL
TERMINATE
```

The LLM composes these approved primitives.

The deterministic compiler verifies the plan.

---

# 14. Plan Validation

Validation must happen before execution.

The pipeline:

```text
Planner
 ↓
Plan JSON
 ↓
Schema validation
 ↓
Dependency validation
 ↓
Cycle detection
 ↓
Capability validation
 ↓
Policy validation
 ↓
Resource validation
 ↓
Graph complexity limits
 ↓
Compile
```

Plans must have limits such as:

```text
max_nodes
max_depth
max_parallel_branches
max_retries
max_replans
max_agent_calls
max_tool_calls
max_execution_time
```

A plan exceeding those limits must be rejected.

---

# 15. Immutable Plan Versions

Never mutate a live graph in place.

Use versioned plans:

```text
Plan v1
 ↓
execution
 ↓
failure
 ↓
replanner
 ↓
Plan v2
 ↓
execution
```

Mission history should clearly show:

```text
Plan v1 → failed
Reason → insufficient evidence

Plan v2 → completed
```

This makes debugging and replay possible.

---

# 16. Candidate Strategy Generation

For every mission, EIDOS can generate a **small number of candidate strategies**.

Example:

### Plan A

```text
Research
 ↓
Security
 ↓
Analysis
 ↓
Verification
```

### Plan B

```text
Research ─────┐
Security ─────┼→ Analysis → Verification
Architecture ──┘
```

### Plan C

```text
Architecture
 ↓
Targeted Research
 ↓
Security + Analysis
 ↓
Verification
```

Important:

**Do not generate an unlimited number of candidate plans.**

Start with 2–3.

Bounded alternatives are enough for meaningful experiments.

---

# 17. Strategy Optimization

EIDOS's primary differentiator is not “which agent should I call?”

It is:

> **Which execution strategy should I use for this task?**

Potential strategy factors:

```text
agent selection
agent ordering
parallelization
model selection
tool selection
retrieval strategy
verification strategy
retry strategy
replanning strategy
context allocation
```

Strategy quality must be considered alongside:

```text
quality
latency
resource usage
reliability
risk
tool calls
agent calls
evidence requirements
autonomy constraints
```

---

# 18. Cold-Start Problem

This is a critical engineering problem.

Before execution, EIDOS cannot magically know exactly how well a strategy will perform.

Do not implement a fake:

```text
LLM says:
Plan B = 93.6% quality
```

and pretend it is ground truth.

Instead use a progressive mechanism:

```text
Cold start
 ↓
Rules + heuristics
 ↓
Small pilot
 ↓
Measure actual signals
 ↓
Continue / abandon / replan
 ↓
Store real execution data
 ↓
Use historical evidence for future decisions
```

---

# 19. Quality Estimation Strategy

At first, use measurable proxies instead of speculative “future quality.”

Possible proxies:

```text
historical success rate
historical verification pass rate
evidence coverage
schema validity
retrieval confidence
contradiction rate
failure rate
```

Represent uncertainty.

Instead of:

```text
quality = 0.93
```

potentially use:

```text
quality estimate = 0.90–0.95
```

or a confidence interval/uncertainty representation where appropriate.

Track prediction error separately.

Example:

```text
predicted latency = 5.5 seconds
actual latency     = 6.1 seconds
error               = 10.9%
```

The planner can learn that its estimates are systematically biased.

---

# 20. Pilot Execution / Value of Information

One of the more advanced EIDOS ideas is to run a **small pilot** before fully committing to a strategy.

Example:

```text
Plan A → small research sample
Plan B → small research sample
Plan C → small research sample
```

Observe:

```text
evidence strength
retrieval quality
agent responsiveness
early failures
cost
latency
```

Then eliminate clearly inferior plans.

The conceptual research question is:

> **Is the cost of obtaining additional information smaller than the expected cost of executing a bad strategy?**

This can be framed as a Value-of-Information style decision.

Do not implement mathematically complex V.O.I. first.

Start with a simple heuristic.

---

# 21. Historical Strategy Memory

After each mission, store information such as:

```text
task_class
task_genome characteristics
strategy_signature
agents_selected
agent_order
parallelization
model_selection
retrieval_strategy
verification_strategy
latency
token_usage
tool_calls
agent_calls
quality
failures
retries
replans
human_interventions
```

The important distinction is:

Traditional RAG memory:

> “What information did we retrieve?”

EIDOS strategy memory:

> **“How did we solve a similar problem, and how well did that approach work?”**

---

# 22. Strategy Learning

Do not start with reinforcement learning.

Start with:

```text
task type
+
historical strategy outcomes
```

Example:

```text
Task Type: research

Strategy A
success 82%
latency 5.2s

Strategy B
success 91%
latency 6.0s

Strategy C
success 77%
latency 3.8s
```

For a future similar task, retrieve historical strategy performance and rank candidates.

Later, if sufficient real data exists, explore:

- contextual bandits,
- Bayesian optimization,
- learned routing,
- more advanced strategy-selection mechanisms.

These are optional research extensions, not V1 requirements.

---

# 23. Exploration vs Exploitation

Once enough historical data exists, EIDOS should not always choose the historically strongest strategy.

A conceptual mechanism is:

```text
mostly exploit proven strategies
+
occasionally explore alternatives
```

Example:

```text
90% exploitation
10% exploration
```

The exact mechanism is not fixed yet.

This is a later-stage experiment.

---

# 24. Agentic RAG

EIDOS must not use only:

```text
question
→ embedding
→ vector search
→ LLM
```

That is basic RAG.

The intended Agentic RAG flow is:

```text
Information required
        ↓
Determine what is missing
        ↓
Generate retrieval strategy
        ↓
Retrieve
        ↓
Rerank
        ↓
Evaluate evidence
        ↓
Enough?
   ┌────┴─────┐
   NO         YES
   ↓           ↓
Reformulate  Continue
   ↓
Retrieve again
```

Retrieval itself becomes part of execution planning.

---

# 25. Qdrant's Role

Qdrant is the planned local vector database.

It should support:

```text
document retrieval
knowledge memory
historical task memory
strategy memory
performance-related retrieval
```

Do not assume Qdrant is only for PDF chunks.

Potential conceptual collections:

```text
knowledge
tasks
strategies
executions
evidence
```

The exact schema should be designed later.

---

# 26. FAISS vs Qdrant

FAISS can be useful as an experimental baseline.

Qdrant is preferred for the actual architecture because it behaves more like a vector database with metadata/filtering concerns.

Potential experiment:

```text
FAISS
vs
Qdrant
```

Measure:

```text
retrieval latency
memory
filtering capability
setup complexity
behavior at different corpus sizes
```

Do not introduce both into the core runtime unless there is a clear research reason.

Qdrant should be the default.

---

# 27. MCP's Role

MCP is the **tool/resource boundary**.

Agents should not directly access every environment capability.

Instead:

```text
Agent
 ↓
MCP
 ↓
Permission / Policy
 ↓
Tool or resource
```

Initial MCP tools should be deliberately few.

Recommended initial examples:

```text
search_documents
retrieve_evidence
```

Later:

```text
repository.search
database.query
file.read
monitoring.query
```

Do not create 20 MCP tools in V1.

---

# 28. MCP Permission Semantics

Every tool should eventually have metadata equivalent to:

```text
tool name
description
allowed agents
read/write class
risk level
cacheability
timeout
```

The policy system should determine:

```text
Can this agent use this tool?
Can it use it now?
Can it use it without approval?
```

---

# 29. Governance and Autonomy

EIDOS should distinguish:

```text
Can perform
```

from:

```text
Allowed to perform
```

Use autonomy levels:

```text
Level 0
Recommend only

Level 1
Safe read-only actions

Level 2
Reversible actions

Level 3
Human approval required

Level 4
Authorized autonomous execution
```

Example:

```text
Read document
→ automatic

Query database
→ automatic

Modify configuration
→ human approval

Delete critical resource
→ blocked
```

The runtime must enforce this deterministically.

---

# 30. Reliability Contract

Every mission can have a Reliability Contract.

Example:

```text
Minimum quality: 90%
Maximum latency: 8 minutes
Maximum tokens: 10,000
Maximum risk: Medium
Minimum independent evidence: 3
High-risk actions: Require human approval
```

EIDOS must be able to say:

> **Mission could not satisfy the requested reliability contract.**

It must not force a confident-looking answer merely because the model produced output.

---

# 31. Verification

Mission completion is not equivalent to “agent returned output.”

Verification should inspect:

```text
evidence coverage
consistency
schema correctness
policy compliance
output quality
tool path
relevant execution state
```

Example:

```text
Analysis
 ↓
Verification
 ↓
confidence = 0.88
required = 0.90
 ↓
FAIL
 ↓
Replan
```

---

# 32. Failure Recovery

The runtime should support controlled recovery:

```text
agent failure
 ↓
classify
 ↓
retry if appropriate
 ↓
fallback capability
 ↓
replan if necessary
```

Hard limits:

```text
max retries
max replans
max execution time
max agent calls
max tool calls
```

No infinite loops.

After the recovery budget is exhausted:

```text
MISSION PAUSED

Reason:
Maximum recovery budget exceeded.

Human review required.
```

---

# 33. Execution Telemetry

Every meaningful execution event should be structured.

Examples:

```text
MISSION_CREATED
PLAN_GENERATED
PLAN_REJECTED
PLAN_COMPILED
A2A_TASK_STARTED
A2A_TASK_COMPLETED
MCP_TOOL_CALLED
RAG_SEARCH
EVIDENCE_REJECTED
VERIFICATION_FAILED
REPLAN_TRIGGERED
MISSION_COMPLETED
MISSION_FAILED
```

Every mission should produce measurable data such as:

```text
mission_id
plan_id
agent_calls
a2a_messages
mcp_calls
rag_rounds
tokens
latency
retries
replans
quality
evidence_confidence
cache_hit_rate
policy_violations
human_interventions
```

---

# 34. AgentOps

AgentOps is not merely a dashboard.

The important architecture is:

```text
Execution telemetry
        ↓
Evaluation
        ↓
Performance memory
        ↓
Future strategy selection
```

This creates the closed loop:

```text
Plan
 ↓
Execute
 ↓
Observe
 ↓
Evaluate
 ↓
Remember
 ↓
Plan better
```

That feedback loop is central to EIDOS.

---

# 35. Context Optimization and Caching

Prompt caching is not the primary product feature.

Use a broader **Context Optimization** layer.

Potential levels:

```text
prompt/context cache
retrieval cache
tool-result cache
task-state cache
```

Examples:

```text
stable system rules
→ reusable

repeated retrieval result
→ cache candidate

unchanged tool result
→ cache candidate

current user request
→ dynamic
```

Measure:

```text
cache hit rate
tokens saved
latency saved
```

The exact caching provider is not locked.

During local development, in-process caching or Redis can be used.

---

# 36. Model Independence

One of the most important EIDOS principles:

> **Never make the underlying model the product.**

The model is a worker.

Conceptually:

```text
                      EIDOS
                        │
               Model/Agent Interface
                        │
        ┌───────────────┼───────────────┐
        ↓               ↓               ↓
   Local Model      OpenAI Model    Anthropic Model
        │               │               │
        └───────────────┼───────────────┘
                        ↓
                  Capabilities
```

A model may be replaced without redesigning EIDOS.

For example:

```text
Research → local model
Coding → external frontier model
Verification → another model
```

depending on the task and policy.

---

# 37. Model Arena

A future EIDOS feature can compare multiple model providers for a capability.

Example:

```text
Task: code review

Model A
Quality: 91%
Latency: 2.1 sec

Model B
Quality: 96%
Latency: 5.2 sec

Model C
Quality: 89%
Latency: 1.4 sec
```

EIDOS then selects according to the mission:

```text
high-risk task
→ higher quality model

speed-sensitive task
→ faster model
```

This is a future extension, not an MVP requirement.

---

# 38. Counterfactual Planning

One of the intended advanced features is lightweight comparison of alternative strategies.

Example:

```text
PLAN A
estimated latency: 9.2 min
estimated quality: high
agents: 5

PLAN B
estimated latency: 5.7 min
estimated quality: high
agents: 4

PLAN C
estimated latency: 3.4 min
estimated quality: medium
agents: 2
```

These must be treated as **estimates**, not facts.

Where possible, use historical data.

Where uncertainty is high, use a small pilot.

---

# 39. Strategy Genome

A future research concept is to encode strategies as structured signatures.

Conceptually:

```text
[
  retrieval=adaptive,
  research=parallel,
  analysis=sequential,
  verification=late,
  cache=semantic,
  model=small→large
]
```

Historical strategy signatures can be compared between tasks.

This allows EIDOS to reason about **strategy patterns**.

---

# 40. Autonomy Budget / “Autonomy Debt”

A conceptual advanced feature is an autonomy/risk budget.

Different actions have different risk.

Example:

```text
Read documentation → very low
Query database → low
Change config → medium/high
Restart service → high
Delete critical resource → extreme
```

The runtime can accumulate an autonomy/risk score.

If the policy threshold is exceeded, human approval is required.

This concept should remain experimental until its semantics are properly designed.

---

# 41. Frontend

The frontend should have approximately these views.

## Mission Center

User enters:

```text
goal
constraints
permissions
```

## Strategy View

Shows candidate strategies and selection reason.

## Live Execution

Shows:

```text
agent activity
A2A communications
MCP calls
RAG activity
verification
retries
replanning
```

## Evidence Explorer

Allows the user to navigate:

```text
Conclusion
 ↓
Evidence
 ↓
Source
 ↓
Retrieval query
 ↓
Agent
 ↓
Verification
```

## Execution Replay

Shows the mission as a timeline.

Example:

```text
00:00 mission received
00:02 task genome created
00:04 capabilities discovered
00:07 strategies generated
00:09 Plan B selected
00:11 research started
00:11 security started
00:18 MCP call
00:25 evidence insufficient
00:26 replan
...
```

## Strategy Lab

Shows historical strategy performance.

Example:

```text
Strategy A
success 88%
average 8.7 min

Strategy B
success 95%
average 5.9 min
```

## Failure Lab

Allows deliberate failure injection.

Possible failures:

```text
agent unavailable
tool unavailable
bad retrieval
conflicting evidence
malformed output
timeout
budget exceeded
policy violation
```

The user sees how the system recovers.

---

# 42. What Not to Expose to Ordinary Users

Do not make the main interface look like:

```text
A2A
MCP
LangGraph
Qdrant
Redis
Pydantic
```

Those are technical implementation details.

Ordinary interface:

```text
Mission
Strategy
Execution
Evidence
Result
```

Technical mode can expose:

```text
Task Genome
Plan DSL
state transitions
A2A task IDs
MCP tools
RAG queries
telemetry
strategy history
```

---

# 43. Example Flagship Demo

Use a complex technical task rather than a trivial question.

Example mission:

> “Assess whether our application is ready for migration to a new infrastructure.”

EIDOS might determine:

```text
Required capabilities:
Architecture
Security
Cost
Research
Verification
```

Candidate strategy:

```text
Research ───────┐
Security ───────┼→ Analysis → Verification
Architecture ───┘
```

During execution:

```text
Research Agent
   ↕
Security Agent
   ↓
Analysis Agent
   ↓
Verification Agent
```

If verification fails:

```text
Verification
 ↓
insufficient evidence
 ↓
replan
 ↓
additional retrieval
 ↓
verification
```

Final output:

```text
MISSION COMPLETE

Result: READY WITH CONDITIONS

Confidence: 94%
Evidence: 24 sources
Agents: 4
A2A interactions: 13
MCP calls: 8
RAG rounds: 2
Retries: 1
Latency: 6m 12s
Policy violations: 0
Human interventions: 1
```

---

# 44. Website Generation Is Not the Product

An earlier idea was:

> User gives a website prompt → multiple agents create the website.

An existing GitHub project already occupies that territory.

The repository `githubphilomath/main-project` is explicitly a **Multi-Agent Autonomous Software Development Platform**.

Its documented architecture contains:

```text
Orchestrator Agent
Requirement Analysis Agent
Architecture Agent
Coding Agent
Debugging Agent
Testing Agent
Documentation Agent
Deployment Agent
```

It also has LangGraph, Agent Registry, triple RAG, FastAPI, PostgreSQL/Supabase, Chroma, Gemini, logging, monitoring, evaluation, retry/recovery, and Docker. Its documented workflow is essentially requirements → architecture → coding → debugging → testing → documentation → deployment.

Therefore EIDOS must **not become another “AI software development factory.”**

EIDOS can execute software-building workflows, but the **runtime itself must remain domain-agnostic**.

---

# 45. Competitive Positioning

A GitHub/web investigation found existing projects covering many individual pieces:

```text
agent control planes
A2A/MCP gateways
agent registries
agent runtimes
agent governance
agent compilers
adaptive routing
MCP security
multi-agent software development
```

Examples previously investigated include:

```text
agent-control-plane
mcp-gateway-registry
A1
agent-compiler
a2a-mcp-multi-agent
aMaze
OpenGeni
SuperX
```

These projects mean EIDOS cannot claim novelty merely from:

```text
A2A
+
MCP
+
LangGraph
+
RAG
+
routing
```

Those are infrastructure components.

The intended differentiation is:

> **Adaptive execution-strategy intelligence based on measured outcomes.**

---

# 46. Differentiation From Existing Software-Generation Repository

The existing repository's fundamental question is:

> Can multiple AI agents autonomously build a software application?

EIDOS's question is:

> **Given multiple possible agent capabilities and execution plans, which strategy should be used for this task, under specific quality, latency, resource, risk and autonomy constraints, and how can future strategy selection improve from observed outcomes?**

The distinction:

```text
Existing software factory:
Business task
 → fixed agent workflow
 → software result

EIDOS:
Human objective
 → Task Genome
 → capability discovery
 → alternative strategies
 → strategy evaluation
 → bounded execution
 → verification
 → performance measurement
 → strategy memory
 → improved future planning
```

---

# 47. Reliability Philosophy

EIDOS should prefer:

```text
“I cannot satisfy the reliability contract.”
```

over:

```text
“I will confidently guess.”
```

It should make uncertainty visible.

For example:

```text
Evidence confidence: 0.88
Required:             0.90

STATUS:
Insufficient evidence
```

not:

```text
Answer confidence: 88%
Completed successfully
```

---

# 48. Scope-Control Philosophy

The system has many possible components:

```text
A2A
MCP
LangGraph
RAG
Qdrant
caching
agent registry
strategy memory
telemetry
governance
failure recovery
frontend
deployment
```

Do not implement all of them simultaneously.

The first objective is a functioning **vertical slice**.

---

# 49. MVP Definition

The MVP should prove only:

```text
Task
 ↓
Task Genome
 ↓
2–3 candidate strategies
 ↓
Plan validation
 ↓
LangGraph execution
 ↓
Evaluation
 ↓
Execution history
```

Start with exactly three logical agents:

```text
Research Agent
Analysis Agent
Verification Agent
```

Do not build 10+ agents.

---

# 50. Development Roadmap

## V0.1 — Core Contracts

Build:

```text
TaskGenome
ReliabilityContract
MissionState
MissionEvent
Plan
PlanStep
AgentTask
```

No real agents yet.

No A2A.

No MCP.

No frontend.

## V0.2 — Plan DSL

Build:

```text
schema validation
cycle detection
dependency validation
depth limits
node limits
parallel branch limits
capability validation
policy validation
```

## V0.3 — LangGraph Runtime

Map:

```text
SEQUENTIAL
PARALLEL
ROUTE
VERIFY
RETRY
REPLAN
```

into runtime nodes.

Use mock agents initially.

## V0.4 — Real Local Agents

Add:

```text
Research
Analysis
Verification
```

Make the baseline workflow work end-to-end.

## V0.5 — Mission State + Event Reducer

Build:

```text
MissionEvent
MissionState
StateReducer
Checkpoints
Replay
```

Before adding A2A, state handling must already be reliable.

## V0.6 — One A2A Boundary

Move only one agent into an independent process.

Example:

```text
EIDOS
 ↓ A2A
Research Agent
```

Test:

```text
normal completion
timeout
duplicate event
late event
agent restart
partial artifact
failure
```

## V0.7 — MCP

Add only 2–3 real tools.

Example:

```text
search_documents
retrieve_evidence
```

Test:

```text
successful call
invalid arguments
timeout
unavailable tool
unauthorized call
duplicate call
```

## V0.8 — Agentic RAG

Add:

```text
Qdrant
local embeddings
retrieval
reranking
evidence judge
```

## V0.9 — Telemetry

Add structured event logging.

Measure:

```text
latency
tokens
agent calls
tool calls
A2A interactions
RAG rounds
retries
quality
```

## V1.0 — Strategy Optimization

Add:

```text
historical strategy memory
strategy ranking
constraint-based strategy selection
pilot execution
```

## V1.1 — Adaptive Learning

Add:

```text
strategy memory
historical ranking
exploration
empirical estimation
prediction-error tracking
```

## V1.2 — Reliability/Governance

Add:

```text
policy engine
autonomy levels
human approval
failure recovery
replan limits
execution budgets
```

## V1.3 — Frontend

Build:

```text
Mission Center
Strategy View
Live Execution
Evidence Explorer
Replay
Strategy Lab
Failure Lab
```

## V1.4 — Deployment

Use:

```text
Docker Compose
 ↓
single cloud environment
 ↓
API + workers + DB
 ↓
optional separate A2A agents
```

Do not jump directly to Kubernetes.

---

# 51. Zero-Cost Requirement

The prototype must be buildable without spending money.

Planned local stack:

```text
LLM
→ Ollama + local open model

Embeddings
→ sentence-transformers

Vector DB
→ Qdrant local

Database
→ SQLite initially

Optional cache
→ in-process or local Redis

Backend
→ FastAPI

Orchestration
→ LangGraph

Agent protocol
→ A2A

Tool protocol
→ MCP

Observability
→ OpenTelemetry + local structured logs

Frontend
→ React/TypeScript or Streamlit for early prototype

Containers
→ Docker

Testing
→ Pytest

Source control
→ Git + GitHub

CI
→ GitHub Actions
```

No paid LLM API is required for the core prototype.

Important distinction:

**software cost can be ₹0; compute is not free.**

The user's laptop provides the compute.

---

# 52. Deployment Goal

The user eventually wants EIDOS to become a real web service.

Therefore design the local version as:

```text
local-first
cloud-ready
model-independent
service-oriented
```

Deployment progression:

```text
Local Python
 ↓
Docker Compose
 ↓
Single cloud VM
 ↓
API + workers + database
 ↓
Separate A2A agent services
 ↓
Distributed deployment
```

Do not prematurely build a distributed cloud infrastructure.

---

# 53. API Concept

Eventually expose something conceptually like:

```http
POST /missions
```

with:

```json
{
  "goal": "Assess migration readiness",
  "constraints": {
    "minimum_confidence": 0.90,
    "maximum_latency_seconds": 600,
    "risk_tolerance": "medium"
  }
}
```

Potential result:

```json
{
  "mission_id": "mission_1842",
  "status": "completed",
  "strategy_id": "strategy_b",
  "confidence": 0.94,
  "latency_ms": 372000,
  "agent_calls": 4,
  "a2a_messages": 13,
  "mcp_calls": 8
}
```

This is conceptual; exact API schema must be formally specified later.

---

# 54. Multi-Tenancy Future Consideration

The first prototype may be single-user.

But the architecture should not assume that forever.

Data models should conceptually include identifiers such as:

```text
tenant_id
mission_id
execution_id
agent_id
timestamp
```

Authentication/multi-tenancy should be implemented later.

Do not allow the MVP to become an authentication project.

---

# 55. Claude Code's Role

Claude Code should be treated as:

**Implementation + debugging + test generation + review + experimentation assistant.**

Not:

**the Principal Architect who decides what EIDOS should be.**

Human owner responsibilities:

```text
product decisions
architecture
contracts
research questions
tradeoffs
scope
acceptance criteria
```

Claude responsibilities:

```text
implementation
unit tests
integration tests
refactoring
debugging
documentation updates
local experiments
code review
```

Tests are the objective verifier.

---

# 56. Development Methodology

Every change must follow:

```text
EXPLORE
 ↓
PLAN
 ↓
IMPLEMENT
 ↓
TEST
 ↓
VERIFY
 ↓
COMMIT
```

Never:

```text
“Build EIDOS completely.”
```

A task should be:

```text
one component
one change
one acceptance condition
```

---

# 57. Recommended Claude Code Prompt Style

## Explore

> Read the relevant architecture and implementation files. Do not modify anything. Identify the current design and potential conflicts with the architecture invariants.

## Plan

> Propose the smallest implementation plan that satisfies the requirement. Identify modified files, affected invariants, required tests, and failure modes. Do not implement yet.

## Implement

> Implement only the approved plan. Do not change unrelated architecture. Write tests for new behavior. Run focused tests, then the complete suite.

## Verify

> Review the implementation against the architecture invariants and relevant specifications. Do not modify the code. Report violations, missing tests, or hidden coupling.

---

# 58. Example Claude Prompt — Plan DSL

```text
Read:

docs/05_plan_dsl.md
docs/12_architecture_invariants.md

Implement only the Plan DSL validator.

First create tests for:

- valid plans
- dependency errors
- cycles
- maximum depth
- maximum nodes
- maximum parallel branches
- unknown capabilities
- invalid operations
- policy violations
- resource violations

Do not modify the Plan DSL specification.

Do not implement LangGraph.

Do not implement agents.

Run focused tests and the full test suite.
```

---

# 59. Example Claude Prompt — A2A Integration

```text
Read:

docs/06_mission_state.md
docs/07_a2a_contract.md
docs/12_architecture_invariants.md

Add exactly one A2A boundary between EIDOS and Research Agent.

Requirements:

- MissionState remains authoritative.
- The remote agent must not directly mutate MissionState.
- Map A2A lifecycle events into idempotent EIDOS events.
- Handle duplicate events.
- Handle late events.
- Handle timeout.
- Handle remote failure.
- Handle partial artifacts.
- Preserve task_id and context_id.

Write protocol integration tests before implementation.

Do not modify unrelated agents or architecture.
```

---

# 60. Example Claude Prompt — Architecture Review

```text
Read:

docs/02_architecture.md
docs/05_plan_dsl.md
docs/06_mission_state.md
docs/07_a2a_contract.md
docs/12_architecture_invariants.md

Do not change source code.

Act as a Principal Systems Engineer.

Look for:

- state ownership conflicts
- race conditions
- hidden coupling
- arbitrary graph generation
- unbounded execution
- A2A lifecycle inconsistencies
- failure handling gaps
- security bypasses
- unnecessary complexity

Write findings to:

docs/architecture_review.md
```

---

# 61. Testing Philosophy

A feature is not complete because Claude says:

> “Implemented successfully.”

A feature is complete only when:

```text
implementation exists
+
tests exist
+
tests pass
+
integration works
+
architecture invariants hold
+
failure cases are covered
+
documentation reflects reality
+
Git checkpoint exists
```

Do not weaken tests merely to make them pass.

Do not silently remove failing tests.

Do not suppress runtime errors.

---

# 62. Testing Layers

Use:

```text
tests/unit/
tests/integration/
tests/protocol/
tests/scenarios/
```

Unit tests:

```text
schemas
validators
reducers
scoring
policy
```

Integration tests:

```text
LangGraph
Qdrant
MCP
A2A
database
```

Protocol tests:

```text
A2A lifecycle
MCP tools
idempotency
timeouts
failure events
```

Scenario tests:

```text
full missions
replanning
verification failures
budget exhaustion
policy violations
```

---

# 63. Failure Scenarios That Must Eventually Be Tested

At minimum:

```text
agent timeout
agent failure
agent restart
duplicate A2A event
late A2A event
out-of-order event
partial artifact
MCP tool timeout
MCP tool unavailable
malformed tool output
bad retrieval
conflicting evidence
verification failure
token budget exceeded
tool budget exceeded
retry budget exceeded
replan budget exceeded
policy violation
```

---

# 64. Failure Lab

Create a future UI where the developer/user can intentionally trigger:

```text
Agent unavailable
Tool unavailable
Conflicting evidence
Bad retrieval
Malformed output
Timeout
Token budget exceeded
Policy violation
```

The purpose is to visibly demonstrate:

```text
Failure
 ↓
Classification
 ↓
Retry/fallback/replan
 ↓
Recovery
```

or:

```text
Failure
 ↓
Recovery budget exceeded
 ↓
Human review
```

---

# 65. Evaluation Framework

The project must have measurable experiments.

Do not only demonstrate successful runs.

Compare:

```text
Fixed sequential
vs
Fixed parallel
vs
Adaptive EIDOS
```

Measure:

```text
answer quality
evidence quality
latency
token usage
agent calls
tool calls
A2A messages
RAG rounds
retries
replans
failure rate
cache hit rate
human interventions
policy violations
```

---

# 66. Cold-Start Experiment

Create explicit evaluation conditions:

```text
0 historical tasks
25 historical tasks
100 historical tasks
```

Compare strategy-selection behavior.

Questions:

```text
Does historical data improve strategy selection?

Does it reduce latency?

Does it reduce resource use?

Does it preserve or improve quality?

How does pilot execution affect decision quality?
```

This turns a known vulnerability into a research contribution.

---

# 67. Strategy Experiment

Compare:

```text
Strategy A
sequential

Strategy B
parallel

Strategy C
adaptive
```

Potential outputs:

```text
quality
latency
tokens
tool calls
failure
```

Do not fabricate results.

Every numerical claim in README/portfolio must come from actual experiments.

---

# 68. Architectural Experiment Ladder

A useful benchmark sequence:

```text
Version 1
Single agent

Version 2
Fixed multi-agent

Version 3
Multi-agent + A2A/MCP

Version 4
+ Agentic RAG

Version 5
+ Adaptive strategy selection

Version 6
+ Pilot execution

Version 7
+ Historical strategy memory

Version 8
+ Caching/governance/recovery
```

The objective is not to make every later version win every metric.

The objective is to understand **trade-offs**.

---

# 69. Why This Project Is Intended to Be Future-Facing

The project is explicitly designed around a trajectory:

```text
AI generates answers
        ↓
AI executes tasks
        ↓
AI agents collaborate
        ↓
Systems manage agent ecosystems
        ↓
Systems optimize agent collaboration
        ↓
Systems learn which collaboration strategies work
```

EIDOS targets the final stages.

---

# 70. Portfolio Positioning

The user's comparison portfolio was technically strong.

Visible strengths included:

```text
LangGraph
RAG
multi-agent systems
enterprise APIs
ServiceNow
automation
DevOps
FastAPI
Gmail/Calendar APIs
Ansible
ML
evaluation
production-style workflows
```

The purpose of EIDOS is **not** to beat that portfolio by listing more technologies.

It should differentiate through architectural depth:

```text
A2A
MCP
bounded workflow synthesis
task representation
strategy optimization
counterfactual/pilot planning
strategy memory
execution learning
reliability contracts
autonomy constraints
evidence lineage
AgentOps feedback loop
```

The project's strength should be:

**system design + measurable experiments + reliability + optimization.**

---

# 71. Targeted Demonstration Domain

Strong example workloads:

```text
migration readiness assessment
incident investigation
architecture review
security investigation
business/technical risk analysis
complex document analysis
software development as a secondary workload
```

The important thing is that the user gives an **objective**, not a command for one specific agent.

---

# 72. Frontend Design Principle

Frontend should make the hidden AI architecture understandable.

Primary visible concepts:

```text
Mission
Requirements
Strategy
Execution
Evidence
Verification
Result
```

Advanced visible concepts:

```text
Task Genome
Agent capabilities
A2A communication
MCP tool calls
RAG traces
Plan DSL
State transitions
Telemetry
Strategy history
```

Avoid excessive animated “AI thinking” visuals.

Show actual system events.

---

# 73. Replay Requirement

Every completed mission should ideally be replayable from recorded events.

Example:

```text
Mission created
 ↓
Task Genome generated
 ↓
Capabilities discovered
 ↓
Strategy A/B/C generated
 ↓
Plan B selected
 ↓
Research started
 ↓
Security started
 ↓
MCP called
 ↓
Evidence evaluated
 ↓
Replan triggered
 ↓
Verification passed
 ↓
Mission completed
```

Replay should consume recorded events, not rerun the agents.

---

# 74. Evidence Lineage

Every major conclusion should ideally be traceable:

```text
Conclusion
 ↓
Evidence
 ↓
Source
 ↓
Retrieval query
 ↓
Agent
 ↓
Tool
 ↓
Verification
```

This is important for trust.

---

# 75. Current Project Hierarchy

The following hierarchy should guide implementation:

```text
LEVEL 1 — Core thesis
Adaptive execution strategy selection

LEVEL 2 — Runtime
Task Genome
Plan DSL
Compiler
LangGraph
MissionState

LEVEL 3 — Interoperability
A2A
MCP

LEVEL 4 — Intelligence
Agentic RAG
Strategy memory
Pilot execution
Adaptive routing

LEVEL 5 — Reliability
Verification
Policies
Autonomy
Recovery

LEVEL 6 — Optimization
Caching
Historical performance
Exploration
Strategy learning

LEVEL 7 — Product
Frontend
API
Deployment
```

Do not work from the bottom upward.

Work from the core outward.

---

# 76. Technology Stack

The intended technology stack is:

```text
Python
FastAPI
LangGraph
A2A
MCP
Ollama
Qdrant
sentence-transformers
local Cross-Encoder/reranker
Pydantic v2
SQLite
PostgreSQL later
Redis optional
React
TypeScript
Tailwind CSS
Docker
OpenTelemetry
Pytest
Git
GitHub
GitHub Actions
JSON Schema/custom Plan DSL
```

Not every technology is required in V0.1.

---

# 77. Local Zero-Cost Configuration

The first complete local architecture should look like:

```text
                     EIDOS
                       │
                   FastAPI
                       │
                  LangGraph
                       │
       ┌───────────────┼───────────────┐
       ▼               ▼               ▼
   Research         Analysis       Verification
     Agent            Agent            Agent
       │               │               │
       └──────────── A2A ──────────────┘
                       │
                      MCP
                       │
             ┌─────────┼─────────┐
             ▼         ▼         ▼
          Qdrant      SQLite    Files
             │
        Agentic RAG
             │
         Ollama LLM
```

Everything runs locally.

---

# 78. Future Cloud Architecture

Eventually:

```text
                        INTERNET
                            │
                            ▼
                      Web Frontend
                            │
                            ▼
                       EIDOS API
                            │
                            ▼
                    Control / Planner
                            │
                   ┌────────┴────────┐
                   ▼                 ▼
              Local Worker      A2A Workers
                                      │
                       ┌──────────────┼─────────────┐
                       ▼              ▼             ▼
                    Agent A        Agent B       Agent C
                       │
                      MCP
                       │
              ┌────────┼─────────┐
              ▼        ▼         ▼
           Qdrant   PostgreSQL  Tools
```

---

# 79. Claude Context Hygiene

Do not rely on one endlessly growing Claude Code session.

When a context becomes difficult to manage:

```text
update progress.md
update decisions.md
ensure tests pass
commit
start fresh context
```

The new session must read:

```text
CLAUDE.md
progress.md
decisions.md
relevant docs
```

Do not rely on an arbitrary “60% context” rule.

The important thing is that project state survives context changes.

---

# 80. Subagent Usage

Use Claude subagents for:

```text
independent repository exploration
API research
test review
isolated analysis
parallel investigations
```

Do not create subagents for trivial tasks.

Main Claude should integrate their findings.

Subagents must not independently redefine the EIDOS architecture.

---

# 81. Immediate Repository Documentation

Create these documents before major implementation:

```text
docs/01_problem.md
docs/02_prd.md
docs/03_architecture.md
docs/04_task_genome.md
docs/05_plan_dsl.md
docs/06_mission_state.md
docs/07_a2a_contract.md
docs/08_mcp_contract.md
docs/09_rag_architecture.md
docs/10_reliability.md
docs/11_evaluation.md
docs/12_architecture_invariants.md
```

These documents are the project knowledge base.

---

# 82. First Claude Code Instruction

When this handoff is first loaded, Claude Code must **not start coding immediately**.

First:

1. Read this entire document.
2. Summarize EIDOS in its own words.
3. Identify contradictions or ambiguities in the specification.
4. Produce an architecture-risk review.
5. Produce a proposed repository skeleton.
6. Produce a dependency/install plan.
7. Identify which decisions require human approval.
8. Do not implement source code until the architecture contracts are reviewed.

The first implementation milestone is:

```text
TaskGenome
+
ReliabilityContract
+
MissionState
+
MissionEvent
+
Plan DSL
+
tests
```

There should be **no A2A, no MCP, no RAG, no frontend, and no autonomous model planner in the first implementation slice.**

The first goal is to establish a **small, deterministic, testable foundation**.

---

# 83. Final Definition

**EIDOS — Execution Intelligence & Dynamic Orchestration System**

> EIDOS is a model-independent adaptive AI runtime that transforms high-level human objectives into structured missions, discovers suitable AI capabilities, generates and validates bounded multi-agent execution strategies, selects strategies under quality, latency, resource, reliability and autonomy constraints, executes them through LangGraph, enables independent-agent collaboration through A2A, exposes governed tools and resources through MCP, performs adaptive Agentic RAG and evidence verification, records execution telemetry, and uses historical outcomes to improve future strategy selection.

Its fundamental loop is:

```text
             HUMAN OBJECTIVE
                    │
                    ▼
              TASK GENOME
                    │
                    ▼
           CAPABILITY DISCOVERY
                    │
                    ▼
          STRATEGY GENERATION
                    │
                    ▼
           PLAN VALIDATION
                    │
                    ▼
          STRATEGY SELECTION
                    │
                    ▼
               EXECUTION
                    │
           ┌────────┴────────┐
           ▼                 ▼
         A2A                MCP
           │                 │
     Agent collaboration   Tools/data
           │                 │
           └────────┬────────┘
                    ▼
              AGENTIC RAG
                    │
                    ▼
               VERIFICATION
                    │
             ┌──────┴──────┐
             ▼             ▼
           PASS           FAIL
             │             │
             ▼             ▼
           RESULT        REPLAN
                           │
                           └──────→ execution

                    RESULT
                      │
                      ▼
                  EVALUATION
                      │
                      ▼
              EXECUTION MEMORY
                      │
                      ▼
             STRATEGY LEARNING
                      │
                      └──────→ future missions
```

The ultimate architectural thesis is:

> **Don't build an AI that merely knows how to perform a task. Build a runtime that knows how to decide how AI should perform the task, verifies whether that decision worked, and uses the evidence to make better decisions in the future.**

---

# 84. Final Rules for Claude Code

Before modifying EIDOS, always ask:

```text
What problem does this change solve?
Which architectural document defines it?
Which invariant does it affect?
What is the smallest implementation?
What tests prove it?
What failure cases exist?
Can the feature be demonstrated using a real execution trace?
```

Never optimize for number of files, frameworks, agents, or features.

Optimize for:

```text
correctness
clarity
boundedness
observability
measurability
reliability
architectural coherence
```

EIDOS should become a **rock-solid experimental runtime first and a polished web service second**.
