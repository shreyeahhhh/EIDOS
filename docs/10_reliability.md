# 10 — Reliability, Verification, Governance and Recovery

**Status:** DERIVED — current · verification confidence **OPEN** · target milestone **V1.2** (policy engine), with contracts at **V0.1**
**Derived from:** handoff §18, §19, §29, §30, §31, §32, §40, §47, §63, §64
**Authority:** This document is derived from `EIDOS_CLAUDE_CODE_HANDOFF.md` and subordinate to it.
If this document and the handoff conflict, stop and report the conflict to the human owner.

---

## 1. Reliability philosophy

EIDOS prefers:

```text
"I cannot satisfy the reliability contract."
```

over:

```text
"I will confidently guess."
```

It makes uncertainty visible (§47). Required:

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

This is invariant 13.

## 2. Reliability Contract

Every mission can carry one (§30). Example:

```text
Minimum quality:             90%
Maximum latency:             8 minutes
Maximum tokens:              10,000
Maximum risk:                Medium
Minimum independent evidence: 3
High-risk actions:           Require human approval
```

EIDOS must be able to report **"Mission could not satisfy the requested reliability contract"** and
must not force a confident-looking answer merely because the model produced output.

**Relationship to the Task Genome — resolved (`decisions.md` D-013, decided by the human owner).**

The two models are disjoint. **TaskGenome** describes the task and its intrinsic requirements;
**ReliabilityContract** defines execution acceptance constraints. Constraint thresholds are **not
duplicated** across them, and the genome **references** the contract rather than copying its values.
Because no value has two homes, no precedence rule exists or is needed. See `docs/04_task_genome.md`
§4 and `decisions.md` D-013 for the rationale.

> **Still open:** D-013 settles the structural rule only. Two pairs remain unresolved at the owner's
> instruction — **D-030** (`risk_level` assessed vs "Maximum risk" tolerated) and **D-031**
> (`evidence_requirements` as threshold vs description). Each leaves one field of this model
> undetermined.
>
> Separately, what applies when §30's optional contract is **absent** is a **D-009** question
> (bounds origin), not a D-013 question, and remains Open.

## 3. Verification

**Mission completion is not "an agent returned output"** (§31, invariant 12).

Verification inspects:

```text
evidence coverage
consistency
schema correctness
policy compliance
output quality
tool path
relevant execution state
```

The illustrated flow:

```text
Analysis -> Verification -> confidence = 0.88, required = 0.90 -> FAIL -> Replan
```

### The unresolved centre of this document

§31 compares a scalar confidence against a threshold. §18 forbids treating a model-asserted number
as ground truth — it explicitly rejects `LLM says: Plan B = 93.6% quality` as fake. §19 requires
measurable proxies and represented uncertainty.

**The procedure that turns the seven inspected properties above into the scalar in §31 is not
specified anywhere in the handoff.**

Implementing §31 naively — asking a model for a confidence number — produces exactly the
anti-pattern §18 forbids, at the centre of the system's reliability story. This is the highest-risk
gap identified in the handoff. See `decisions.md` **D-015**.

Two shapes are possible and the choice is the owner's: a defined, measurable confidence function
over proxies, or a pass/fail rule set with no scalar at all.

## 4. Quality estimation

At first, use measurable proxies instead of speculative "future quality" (§19). Candidate proxies:

```text
historical success rate
historical verification pass rate
evidence coverage
schema validity
retrieval confidence
contradiction rate
failure rate
```

**Represent uncertainty.** Instead of `quality = 0.93`, use a range such as `0.90–0.95`, or another
uncertainty representation where appropriate.

**Track prediction error separately:**

```text
predicted latency = 5.5 seconds
actual latency    = 6.1 seconds
error             = 10.9%
```

The planner can then learn that its estimates are systematically biased. This is invariant 17:
estimates are labelled as estimates, carry uncertainty, and prediction error is recorded separately
from outcomes.

> **Open:** which proxies are selected, and how they combine into the `quality_threshold` contract
> field. See `decisions.md` **D-016**.

## 5. Governance and autonomy

EIDOS distinguishes **"can perform"** from **"allowed to perform"** (§29).

Autonomy levels:

```text
Level 0  Recommend only
Level 1  Safe read-only actions
Level 2  Reversible actions
Level 3  Human approval required
Level 4  Authorized autonomous execution
```

Illustrative mapping:

```text
Read document            -> automatic
Query database           -> automatic
Modify configuration     -> human approval
Delete critical resource -> blocked
```

**Risk vocabularies — `decisions.md` D-051, decided by the human owner.**

Risk appears in four places in the handoff and they are **not one concept**:

| Concept | Where | Typed in V0.1? |
|---|---|---|
| Risk of the **task** (assessed / intrinsic) | §6 `risk_level` | yes — task-risk vocabulary |
| Maximum risk the mission may **tolerate** | §30 "Maximum risk" | yes — **same** task-risk vocabulary |
| Risk of an **action** | §40 | **no** — separate concept |
| Risk of a **tool** | §28 | **no** — separate concept |

`TaskGenome.risk_level` and `ReliabilityContract.max_risk_level` are **distinct quantities**
(`decisions.md` **D-030**) sharing **one vocabulary** (**D-051**), so that assessed and tolerated
risk can be compared **deterministically** (invariant 14). This is the case where a shared name is a
comparison pair rather than a duplicate, so both survive D-013's disjoint decomposition — one in each
model. Action risk and tool risk are separate concepts and the task-risk type is **not** reused for
them in V0.1.

**How either value is calculated is deliberately out of scope** and recorded as **D-057**. §5's
user-stated "Risk tolerance" maps cleanly onto the contract field; the provenance of the assessed
value is unspecified, and whether it is model-asserted or rule-derived matters for invariant 14.

**§40's five-point scale was explicitly declined** as the V0.1 task-risk enum: §40 marks itself
experimental, its anchors are all verbs and so action-shaped, and `Change config → medium/high` is
not a single value. Note that §29 — the governance section that actually drives enforcement — uses
**no risk scale at all**; it runs on autonomy levels 0–4 and direct action-to-outcome mapping.

> ⚠️ **D-056 is Open: the concrete task-risk value set.** The handoff contains no task-risk scale,
> and none may be invented. `TaskGenome` and `ReliabilityContract` should be written **last** among
> the seven V0.1 contracts for this reason.

**The runtime must enforce this deterministically** (invariant 14). Enforcement lives in code, never
in a prompt.

Policy validation is also a stage of plan validation (§14), so a plan requiring a disallowed action
is rejected before execution rather than blocked mid-flight.

> **Open:** whether §6's `autonomy_level` uses this 0–4 scale, and what §40's separate "autonomy
> budget / autonomy debt" concept is called so the two never collide. See `decisions.md` **D-014**.

### Autonomy budget — experimental

§40 sketches an accumulating risk score: read documentation is very low risk, query database low,
change config medium/high, restart service high, delete critical resource extreme. If a policy
threshold is exceeded, human approval is required.

§40 states this **should remain experimental until its semantics are properly designed.** It is
recorded, not designed.

## 6. Failure recovery

Controlled recovery (§32):

```text
agent failure -> classify -> retry if appropriate -> fallback capability -> replan if necessary
```

Hard limits:

```text
max retries
max replans
max execution time
max agent calls
max tool calls
```

**No infinite loops.** After the recovery budget is exhausted:

```text
MISSION PAUSED

Reason:
Maximum recovery budget exceeded.

Human review required.
```

This is invariant 7. Budget exhaustion pauses for human review; it never loops, never silently
truncates, never retries forever.

**Source of authority — resolved (`decisions.md` D-009, decided by the human owner).**

Bounds split by **category**, because each category exists for a different purpose:

| Category | Examples | Owner | Why |
|---|---|---|---|
| **Runtime shape / complexity safety limits** | `max_nodes`, `max_depth`, `max_parallel_branches` | **System** | §12 and §14 bound plan shape to protect *the runtime* from an LLM's output, not to express user preference |
| **Mission execution budgets** | `max_retries`, `max_replans`, `max_agent_calls`, `max_tool_calls`, `max_execution_time`, `max_tokens` | **ReliabilityContract** | §5 and §30 have the user state latency and token budgets directly |

Two riders:

- **A mission may tighten a system limit but may never exceed the system safety ceiling.**
- **Never silently clamp.** A contract value exceeding the ceiling is **rejected with an explicit
  validation reason** — invariant 5's reject-never-repair rule applied one layer up. Clamping would
  hide from the user that they did not get what they asked for.

**No numerical defaults are established in V0.1.** Values arrive at V0.2 with the validation work and
are tuned from measurement thereafter. Only two numbers in this area are handoff-sourced —
`latency_budget_ms: 600000` (§6) and `Maximum tokens: 10,000` (§30) — and both are *examples*.
Per §67 a provisional bound must never be presented as a tuned one.

> **Still open:** **D-042** (the exact contract budget field list), **D-043** (declared plan limits
> vs actual execution counters), **D-044** (whether `max_tokens` formally joins the §14/§32 lists),
> **D-045** (what applies when no contract is supplied), **D-046** (the values themselves), and
> **D-029** (the Agentic RAG reformulation bound).
>
> **D-043 is the one most likely to cause a real defect.** Five limit names appear in both §14
> (validation, rejecting a plan) and §32 (execution, pausing a mission), and the shared names count
> different things: `max_agent_calls` at validation counts declared plan steps, at execution it
> counts actual invocations including retries. A plan with 4 agent steps under `max_retries: 2` can
> consume 12 agent calls.

## 7. Failure scenarios that must be tested

§63's minimum list:

```text
agent timeout            MCP tool timeout          token budget exceeded
agent failure            MCP tool unavailable      tool budget exceeded
agent restart            malformed tool output     retry budget exceeded
duplicate A2A event      bad retrieval             replan budget exceeded
late A2A event           conflicting evidence      policy violation
out-of-order event       verification failure
partial artifact
```

Each belongs to the test layer matching its boundary: protocol tests for A2A and MCP lifecycle
behaviour, scenario tests for budget exhaustion, verification failure and policy violation.

## 8. Failure Lab

A future UI (§64, §41) lets the developer or user deliberately trigger: agent unavailable, tool
unavailable, conflicting evidence, bad retrieval, malformed output, timeout, token budget exceeded,
policy violation.

Its purpose is to demonstrate visibly:

```text
Failure -> Classification -> Retry / fallback / replan -> Recovery
```

or:

```text
Failure -> Recovery budget exceeded -> Human review
```

Deferred to V1.3 with the rest of the frontend. The *mechanisms* it exercises are V1.2 and earlier,
and must be testable without a UI.

---

## Open questions

| Id | Question | Blocks |
|---|---|---|
| D-015 | How verification confidence is computed from measurable proxies — or whether verification is pass/fail with no scalar | V0.4, V1.2 |
| D-016 | Which quality proxies, and how they combine into `quality_threshold` | V0.1, V1.0 |
| D-057 | How either risk value is determined — model-asserted or rule-derived (matters for invariant 14) | V0.2 policy validation |
| D-056 | The concrete **task-risk value set** — deferred by D-051; the handoff supplies none | **V0.1, the field's type** |
| D-031 | Is `evidence_requirements` a threshold or a description? | V0.1, one field |
| D-042 | The exact list of ReliabilityContract budget fields | V0.1, field list |
| D-045 | What applies when no ReliabilityContract is supplied | V0.1, one flag |
| D-043 | Declared plan limits vs actual execution counters | V0.2, V0.3 |
| D-044 | Does `max_tokens` formally belong to the §14/§32 bound lists? | V0.2, V1.2 |
| D-046 | Numerical bound values | V0.2, tuned from V0.9 telemetry |
| D-014 | `autonomy_level` scale, and naming for §40's separate budget concept | V0.1 |
| — | What "fallback capability" selection means in §32, and whether it is expressible in the Plan DSL primitives | V1.2 |
| — | How a paused mission resumes after human review, and whether resumption produces a new plan version | V1.2 |

## Out of scope for this document

Plan validation mechanics (`05_plan_dsl.md`), state and events (`06_mission_state.md`), measurement
and experiments (`11_evaluation.md`).
