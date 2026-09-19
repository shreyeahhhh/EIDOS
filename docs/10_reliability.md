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

⚠️ **The last line of that example is not a contract field** — `decisions.md` **D-069**. Every other
clause is a *value*; that one is a *rule*, stated as prose with no number and no defined subject
("high-risk" is undefined against D-056's `low | medium | high`, which is **task** risk, not action
risk). Approval is a **governance concern**, routed through §29's `autonomy_level`, with per-step
`HUMAN_APPROVAL` (§13) and per-tool policy (§28) as **separate mechanisms**. Four mechanisms in the
handoff touch approval; two of them are mission-wide, and carrying both would duplicate one idea.

This is a **second departure from §30's example**, after D-045. See **D-074** for the unresolved part:
§30's wording is scoped to *actions* while §29's Level 3 is scoped to the *mission*, so the two may
not be exactly equivalent.

**Relationship to the Task Genome — resolved (`decisions.md` D-013, decided by the human owner).**

The two models are disjoint. **TaskGenome** describes the task and its intrinsic requirements;
**ReliabilityContract** defines execution acceptance constraints. Constraint thresholds are **not
duplicated** across them, and the genome **references** the contract rather than copying its values.
Because no value has two homes, no precedence rule exists or is needed. See `docs/04_task_genome.md`
§4 and `decisions.md` D-013 for the rationale.

Both pairs D-013 exposed are now settled: **D-030** — assessed and tolerated risk are distinct
quantities, one field in each model; **D-031** — this contract carries `min_independent_evidence`
while the genome carries no parallel `evidence_requirements` field (**D-070** holds the remaining
question).

**The contract is required — `decisions.md` D-045.** Every `TaskGenome` must reference a
`ReliabilityContract`. §30's "**can** have" was read as describing a system capability rather than
granting permission to omit: with no contract, invariant 13 has no referent for "satisfied", §31's
threshold comparison has no right-hand side, D-042's six budgets have no mission-level home, and
§49's evaluation step has nothing to evaluate. **This is the one V0.1 decision that departs from a
literal reading of the handoff's wording**, and D-045 records it as such.

> **Still open:** **D-066** — whether the contract is always user-supplied or may be synthesised by
> EIDOS. Synthesis is currently unbuildable because it needs numbers that **D-046** defers to V0.2,
> and adopting it later would not contradict D-045. Field optionality is settled: the six budgets
> are optional (**D-065**) and the three non-budget fields are required (**D-073**).

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

### Threshold versus estimate — `decisions.md` D-016

**Resolved, decided by the human owner.** The handoff uses "quality" for **two things that behave
differently**, and they are now separated:

| | Nature | Carries uncertainty? | V0.1 |
|---|---|---|---|
| `ReliabilityContract.min_quality` | a **user-stated requirement** (§30's `Minimum quality: 90%`, §6's `0.90`) | **no** | **typed as a plain scalar** |
| Any quality figure the **system produces** | an **estimate or measurement** (§19's subject) | **yes** — §19, invariant 17 | **not introduced** |

Applying §19's "represent uncertainty" to a requirement is incoherent — a user does not require
"somewhere between 0.90 and 0.95". §47's output format shows the two meeting at a comparison:
a produced `Evidence confidence: 0.88` against a required `0.90`.

The estimate type is **not** introduced in V0.1 because nothing in V0.1 produces an estimate — no
verification, no planner, no telemetry. It would be an unreachable type, the same reasoning that
excluded `PLANNING`/`EXECUTING` in D-052. **Invariant 17's obligation is deferred to its proper
owner, not discharged.**

> **Still open:** **D-063** — the concrete estimate type (interval, distribution, or value plus
> method) and where prediction error is recorded. Needed **before V0.4**.
> **D-064** — whether §31/§47's `confidence` and §30's `quality` are the **same quantity**. The
> handoff uses both words for what looks like one comparison. If they are two, the contract needs
> two thresholds, which feeds back into **D-042**.
> **D-015** — untouched, and still the question of *how proxies are combined*. D-016 typed a
> threshold; it did not define a measurement.

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

**Value set — `decisions.md` D-056, decided by the human owner.**

```text
RiskLevel = low | medium | high
```

A **closed, ordinal, word-valued** three-level scale, used by both `TaskGenome.risk_level` and
`ReliabilityContract.max_risk_level`.

The handoff contains **no task-risk scale** — it supplies only the value `medium` (§5, §6, §30, and
§53's `"risk_tolerance": "medium"`). The scale's *shape* is derived: ordinal (D-030's comparison plus
invariant 14), containing `medium` (or the handoff's own examples become unrepresentable), closed and
small (invariant 14; §4/§5 put it in front of a non-technical user), not §40's (D-051), and
word-valued rather than numeric (§53 carries a string) — deliberately asymmetric with
`AutonomyLevel`, which §29 states numerically. The labels `low` and `high` are **explicitly ratified
additions**, not derivations.

⚠️ **This scale is not reused for §40 action risk or §28 tool risk.** **D-062** must give §40's
budget its own name and scale; two risk vocabularies coexisting is fine, two sharing a name is the
D-014 problem recurring.

**The runtime must enforce this deterministically** (invariant 14). Enforcement lives in code, never
in a prompt.

Policy validation is also a stage of plan validation (§14), so a plan requiring a disallowed action
is rejected before execution rather than blocked mid-flight.

**Resolved — `decisions.md` D-014.** `TaskGenome.autonomy_level` uses this §29 scale. §29 is the only
autonomy enumeration in the handoff, and §6's example value `1` is consistent with both its
read-only mission and §29's Level 1. No additional levels are invented.

> **Still open:** **D-060** — §29's levels may not form one ordered dimension. Levels 0, 1, 2 and 4
> describe what the system *may do*; **level 3 describes a *process***, and the examples above map an
> **action** to a **gate** rather than to a level. If the scale is ordinal throughout, enforcement is
> a comparison; if level 3 cuts across it, enforcement is a branch. Invariant 14 makes this a real
> distinction.
>
> **D-061** — approval is expressible twice, as mission-wide level 3 and as the `HUMAN_APPROVAL`
> step kind (§13). Their relationship is unstated, and two mechanisms for one concept is the pattern
> D-013 and §9/§10 both reject.

### Autonomy budget — experimental

§40 sketches an accumulating risk score: read documentation is very low risk, query database low,
change config medium/high, restart service high, delete critical resource extreme. If a policy
threshold is exceeded, human approval is required.

§40 states this **should remain experimental until its semantics are properly designed.** It is
recorded, not designed.

> ⚠️ **D-062 — this concept must be given a name distinct from `autonomy_level` before it is ever
> implemented.** It shares the word "autonomy" with §29's levels while being a different thing, and
> that collision is what made D-014 necessary. It is also entangled with **D-051**: §40's
> action-risk scale was declined as the task-risk vocabulary, so whatever this budget accumulates
> needs its own defined scale.

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

**Budget group — `decisions.md` D-042.** The V0.1 contract carries **six** mission-level budgets:

```text
max_retries        max_agent_calls      max_execution_time
max_replans        max_tool_calls       max_tokens
```

⚠️ **This is a reconciliation of three partial lists, not a quotation.** No section of the handoff
enumerates this contract. §30 shows the only actual contract and carries two of these six; §14's
list is prefixed "such as"; §32 names five as execution hard limits; §53's API shows none. §30 is an
*example*, so treating it as partial is justified — but the reading is recorded as a reading.

§30's **non-budget** clauses are governed elsewhere and are not part of this group: `min_quality`
(**D-016**), `max_risk_level` (**D-051**/**D-056**), `min_independent_evidence` (**D-031** — carried
by this contract in V0.1; the genome does **not** carry a parallel `evidence_requirements` field,
and whether one is ultimately needed is **D-070**), and `High-risk actions: require human approval`,
which is a **rule rather than a number** (**D-069**).

Every one of the six needs a **system counterpart**, or D-009's `min(system, contract)` rule is
undefined for it.

**Optionality.** **The three non-budget fields — `min_quality`, `max_risk_level`,
`min_independent_evidence` — are required** (`decisions.md` **D-073**). §30's example carries all
three and no demonstration of omission exists anywhere, which is the same evidentiary standard that
made the budgets optional — applied to opposite evidence. They also have **no system-ceiling
fallback**: there is no system-wide "minimum quality". Optional criteria inside a contract **D-045**
made required would hollow that decision out one level down.

**All six budget fields are optional** (`decisions.md` **D-065**). When a budget is
omitted the applicable **system ceiling** applies; when supplied, the mission may **tighten** the
ceiling but **may not exceed** it (D-009). The fallback is **structural, not numeric** — ceilings
have no values until V0.2 (**D-046**).

The decisive evidence is that **§30's own example contract omits four of the six**, so omission is
legal by demonstration rather than by inference. §5 shows the user stating only two of the six, and
§53's API carries none — while `max_retries`, `max_replans`, `max_agent_calls` and `max_tool_calls`
appear at exactly two places in the whole handoff, §14 and §32, and nowhere user-facing.

D-045's rationale is unaffected: the contract is required so acceptance criteria always exist, and
that weight sits on `min_quality`, `max_risk_level` and `min_independent_evidence`, not on budgets.

> **Still open:** **D-072** (whether "omitted" and "explicitly at the ceiling" must stay
> distinguishable for §19 prediction-error tracking and the §41 views), **D-043** (declared plan
> limits vs actual execution counters), **D-044** (`max_tokens` is in §30 and §63 but in **neither**
> §14's nor §32's list), **D-066** (user-supplied vs synthesised), **D-046** (the values themselves),
> **D-029** (the Agentic RAG reformulation bound). **D-073 (non-budget field optionality) is
> resolved** — see the "Optionality" paragraph above.
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
| D-063 | The concrete quality-**estimate** type required by §19 and invariant 17 | before V0.4 |
| D-064 | Are §31/§47 `confidence` and §30 `quality` the same quantity? | V0.4; feeds D-042 |
| D-057 | How either risk value is determined — model-asserted or rule-derived (matters for invariant 14) | V0.2 policy validation |
| D-057 | How either risk value is determined — model-asserted or rule-derived | V0.2 policy validation |
| D-031 | Is `evidence_requirements` a threshold or a description? | V0.1, one field |
| D-074 | Is §30's approval wording exactly `autonomy_level >= 3`? §30 scopes to actions, §29 to the mission | V1.2 |
| D-072 | Must "omitted" stay distinguishable from "explicitly at the ceiling"? | V0.9, V1.3 |
| D-069 | Is §30's `High-risk actions: require human approval` a contract field, or a V1.2 policy rule? | **V0.1, field existence** |
| D-045 | What applies when no ReliabilityContract is supplied | V0.1, one flag |
| D-043 | Declared plan limits vs actual execution counters | **V0.3** (V0.2 checks declared steps only — D-105) |
| D-044 | Does `max_tokens` formally belong to the §14/§32 bound lists? | V0.2, V1.2 |
| D-046 | Numerical bound values | V0.2, tuned from V0.9 telemetry |
| D-060 | Is §29's level 3 ordinal, or a gate cutting across the scale? | V1.2 |
| D-061 | Mission-wide `autonomy_level` vs the `HUMAN_APPROVAL` step kind | V0.3/V1.2 |
| D-062 | A distinct name and semantics for §40's autonomy budget | before any implementation |
| — | What "fallback capability" selection means in §32, and whether it is expressible in the Plan DSL primitives | V1.2 |
| — | How a paused mission resumes after human review, and whether resumption produces a new plan version | V1.2 |

## Out of scope for this document

Plan validation mechanics (`05_plan_dsl.md`), state and events (`06_mission_state.md`), measurement
and experiments (`11_evaluation.md`).
