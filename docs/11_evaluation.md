# 11 — Evaluation, Telemetry and Experiments

**Status:** DERIVED — current · target milestones **V0.9** (telemetry), **V1.0/V1.1** (strategy memory and learning)
**Derived from:** handoff §17, §18, §19, §20, §21, §22, §23, §33, §34, §37, §38, §39, §65, §66, §67, §68
**Authority:** This document is derived from `EIDOS_CLAUDE_CODE_HANDOFF.md` and subordinate to it.
If this document and the handoff conflict, stop and report the conflict to the human owner.

---

## 1. The closed loop

AgentOps is **not merely a dashboard** (§34). The architecture is:

```text
Execution telemetry -> Evaluation -> Performance memory -> Future strategy selection
```

closing:

```text
Plan -> Execute -> Observe -> Evaluate -> Remember -> Plan better
```

That feedback loop is central to EIDOS.

## 2. Telemetry

Every meaningful execution event is structured (§33). Event types are listed in
`06_mission_state.md` §4.

Every mission produces measurable data:

```text
mission_id        rag_rounds        quality
plan_id           tokens            evidence_confidence
agent_calls       latency           cache_hit_rate
a2a_messages      retries           policy_violations
mcp_calls         replans           human_interventions
```

V0.9 adds structured event logging and measures latency, tokens, agent calls, tool calls, A2A
interactions, RAG rounds, retries and quality (§50).

**V0.5 (D-152, D-158, D-159, built)** records only the minimum the MissionState counters and a derived `ExecutionRecord` need — dispatches, model calls, provider-reported tokens
and recorded durations — as events. It is not the telemetry platform, and no quality or rate is computed.

Intended observability stack: OpenTelemetry plus local structured logs (§51, §76). Not installed.

## 3. Cold start

Before execution, EIDOS cannot know how well a strategy will perform. **Do not implement a fake
`LLM says: Plan B = 93.6% quality` and pretend it is ground truth** (§18).

The progressive mechanism:

```text
Cold start -> Rules + heuristics -> Small pilot -> Measure actual signals
-> Continue / abandon / replan -> Store real execution data
-> Use historical evidence for future decisions
```

## 4. Pilot execution and value of information

Run a **small pilot** before fully committing to a strategy (§20):

```text
Plan A -> small research sample
Plan B -> small research sample
Plan C -> small research sample
```

Observe evidence strength, retrieval quality, agent responsiveness, early failures, cost and
latency. Then eliminate clearly inferior plans.

The research question:

> Is the cost of obtaining additional information smaller than the expected cost of executing a bad
> strategy?

This can be framed as a Value-of-Information decision. **Do not implement mathematically complex
V.O.I. first. Start with a simple heuristic** (§20).

## 5. Counterfactual planning

Lightweight comparison of alternatives (§38), for example three plans with differing estimated
latency, estimated quality and agent count.

**These must be treated as estimates, not facts.** Where possible use historical data; where
uncertainty is high, use a small pilot. This is invariant 17.

## 6. Historical strategy memory

After each mission, store (§21):

```text
task_class                  retrieval_strategy      quality
task_genome characteristics verification_strategy   failures
strategy_signature          latency                 retries
agents_selected             token_usage             replans
agent_order                 tool_calls              human_interventions
parallelization             agent_calls
model_selection
```

The distinction that matters (§21):

| Traditional RAG memory | EIDOS strategy memory |
|---|---|
| "What information did we retrieve?" | **"How did we solve a similar problem, and how well did that approach work?"** |

## 7. Strategy learning

**Do not start with reinforcement learning** (§22). Start with:

```text
task type + historical strategy outcomes
```

For a future similar task, retrieve historical strategy performance and rank candidates.

Later, **if sufficient real data exists**, explore contextual bandits, Bayesian optimization, learned
routing, and more advanced strategy-selection mechanisms. §22 states these are **optional research
extensions, not V1 requirements**.

## 8. Exploration vs exploitation

Once enough historical data exists, EIDOS should not always choose the historically strongest
strategy (§23):

```text
mostly exploit proven strategies + occasionally explore alternatives
```

with an illustrative 90/10 split. §23 states **the exact mechanism is not fixed yet** and that this
is a later-stage experiment. It is recorded, not designed.

## 9. Strategy Genome

A future research concept (§39): encode strategies as structured signatures, e.g. retrieval,
research topology, analysis topology, verification placement, caching mode, model progression.
Historical signatures can then be compared across tasks, letting EIDOS reason about **strategy
patterns**.

§39 presents this as a concept without a defined encoding or comparison semantics. See
`decisions.md` **D-021**, which depends on **D-020**.

## 10. Evaluation framework

**The project must have measurable experiments. Do not only demonstrate successful runs** (§65).

Compare:

```text
Fixed sequential  vs  Fixed parallel  vs  Adaptive EIDOS
```

Measure: answer quality, evidence quality, latency, token usage, agent calls, tool calls, A2A
messages, RAG rounds, retries, replans, failure rate, cache hit rate, human interventions, policy
violations.

## 11. Cold-start experiment

Explicit evaluation conditions (§66):

```text
0 historical tasks
25 historical tasks
100 historical tasks
```

Compare strategy-selection behaviour and ask: does historical data improve strategy selection? Does
it reduce latency? Does it reduce resource use? Does it preserve or improve quality? How does pilot
execution affect decision quality?

This turns a known vulnerability into a research contribution.

## 12. Architectural experiment ladder

A benchmark sequence (§68):

```text
V1 single agent                    V5 + adaptive strategy selection
V2 fixed multi-agent               V6 + pilot execution
V3 + A2A/MCP                       V7 + historical strategy memory
V4 + Agentic RAG                   V8 + caching/governance/recovery
```

**The objective is not for every later version to win every metric. The objective is to understand
trade-offs** (§68).

## 13. Honesty rule

> **Do not fabricate results. Every numerical claim in README/portfolio must come from actual
> experiments.** (§67)

This is CLAUDE.md §7 and applies to every document in this repository. No metric appears anywhere
here today because no measurement has been taken.

## 14. Context optimization measurement

The caching layer (§35) is measured by cache hit rate, tokens saved and latency saved. `cache_hit_rate`
is one of the per-mission telemetry fields (§33).

---

## Open questions

| Id | Question |
|---|---|
| D-020 | Strategy vs Plan — determines what a `strategy_signature` signs |
| D-021 | Strategy signature encoding and comparison semantics — deferred by §39 itself |
| D-016 | The quality function whose output is stored as `quality` per mission |
| D-015 | How `evidence_confidence` is computed |
| D-017 | Where strategy memory is persisted, and whether it shares the Qdrant collections sketched in §25 |
| — | `task_class` (§21) is stored per mission but never defined — how a task is classified, and whether it derives from the Task Genome |
| — | The similarity function for "a future similar task" (§22) |
| — | Which baselines the "Fixed sequential / Fixed parallel" comparisons (§65) are implemented as, and whether they are runtime modes or separate harnesses |

## Out of scope for this document

Verification mechanics (`10_reliability.md`), RAG internals (`09_rag_architecture.md`), the frontend
Strategy Lab and Failure Lab (`02_prd.md`).
