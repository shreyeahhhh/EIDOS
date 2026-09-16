# 04 — Task Genome

**Status:** DERIVED — current · target milestone **V0.1**
**Derived from:** handoff §5, §6, §29, §30, §54
**Authority:** This document is derived from `EIDOS_CLAUDE_CODE_HANDOFF.md` and subordinate to it.
If this document and the handoff conflict, stop and report the conflict to the human owner.

---

## 1. Purpose

The Task Genome converts natural-language intent into a structured representation. It is **a
contract, not metadata** (§6). Everything downstream — capability discovery, strategy generation,
validation, policy enforcement, verification — reads it.

```text
Human mission statement -> Task Genome -> capability discovery -> strategy generation
```

## 2. Fields

The handoff specifies fields "conceptually equivalent to" the following (§6):

| Field | Meaning per handoff |
|---|---|
| `goal` | The objective, in structured form |
| `required_capabilities` | Capabilities the task needs |
| `information_dependencies` | Information the task depends on |
| `risk_level` | Risk classification of the task |
| `quality_threshold` | Minimum acceptable quality |
| `latency_budget` | Maximum acceptable time |
| `resource_budget` | Maximum acceptable resource/token use |
| `autonomy_level` | How autonomously EIDOS may act |
| `evidence_requirements` | What evidence the result must carry |
| `allowed_actions` | Actions permitted for this mission |

Handoff example (§6):

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

Note that the example omits `information_dependencies`, `resource_budget` and
`evidence_requirements`, and names the latency field `latency_budget_ms`. The handoff describes the
field list as "conceptually equivalent", so exact field names are an implementation decision that
must be taken explicitly, not inferred from the example.

## 3. Relationship to the mission the user states

The user-facing mission (§5) carries: goal, constraints, required confidence, maximum latency,
resource/token budget, risk tolerance, allowed actions, evidence requirements, human-approval
requirements. EIDOS converts this into the Task Genome.

## 4. Relationship to the Reliability Contract

**Resolved — `decisions.md` D-013, decided by the human owner.**

The two models are **disjoint**:

- **TaskGenome** describes the task and its intrinsic requirements.
- **ReliabilityContract** defines execution acceptance constraints.
- **Constraint thresholds are not duplicated across the two models.**
- **TaskGenome references the ReliabilityContract rather than copying its threshold values.**

Consequently the constraint fields §6 lists — `quality_threshold`, `latency_budget`,
`resource_budget` — are not restated in the genome. They are reachable through the referenced
contract. §6 describes its field list as "conceptually equivalent" rather than prescribing a schema,
and §53's API concept already separates `goal` from a nested `constraints` object.

The deciding consideration was §21 and §22: the genome is load-bearing as a **task-similarity key**
for strategy memory. Constraints are not part of task similarity — the same assessment under a
10-minute and a 60-minute budget is the same task with different acceptance criteria. Holding
constraints in the genome would make those two look like different tasks and degrade strategy-memory
recall invisibly. Full rationale and the interpretations rejected are in `decisions.md` D-013.

Because no value has two homes, **no precedence rule exists or is needed.**

> **Still open — two sub-ambiguities the owner deliberately left unresolved.** D-013 settles the
> structural rule only; it does not settle whether these particular pairs are the same quantity:
>
> - **D-030 — resolved.** `risk_level` (assessed/intrinsic risk of the task) and
>   `ReliabilityContract.max_risk_level` (maximum risk the mission may tolerate) are **distinct
>   quantities**, one in each model. This is the case where a shared name is a comparison pair rather
>   than a duplicate. **D-051** supplies the shared vocabulary that makes the comparison well-formed;
>   **D-056** still owes the value set. How either value is *calculated* is deliberately out of
>   scope — see **D-057**.
> - **D-031** — `evidence_requirements` (§6) vs "Minimum independent evidence" (§30): §6's field may
>   be a numeric threshold (contract) or a descriptive task requirement (genome). **Still open** —
>   one field of this model remains undetermined.

## 5. Autonomy level

§6's example sets `"autonomy_level": 1`. §29 defines a five-level scale:

```text
Level 0  Recommend only
Level 1  Safe read-only actions
Level 2  Reversible actions
Level 3  Human approval required
Level 4  Authorized autonomous execution
```

The example's `1` is consistent with the mission it describes (read documents, read repository,
query monitoring), but the handoff never states that §6's field uses the §29 scale.

Separately, §40 introduces an "autonomy budget / autonomy debt" — an accumulating risk score — which
is a **different concept using the same word**, and which §40 itself marks experimental.

See `decisions.md` **D-014**.

## 6. Capabilities

`required_capabilities` is the input to capability discovery. The vocabulary problem is material:
§6 requires `architecture_analysis` and `security_analysis`, and the §7 registry example contains
neither. A genome written per §6 would not match a registry populated per §7.

See `decisions.md` **D-007**. Capability validation (§14) cannot be written until this is resolved.

## 7. Identity fields

§54 states that data models should conceptually include `tenant_id`, `mission_id`, `execution_id`,
`agent_id` and `timestamp`, while warning that the MVP must not become an authentication project.

**Resolved — `decisions.md` D-019, decided by the human owner.**

`tenant_id` is **present and required** on V0.1 root models and carries a **single fixed default
value**.

> ⚠️ **`tenant_id` has no security meaning in V0.1.** It must not be treated as an authentication,
> authorization, or isolation mechanism. There is no auth behind it, no enforcement, and no
> isolation. It is an identity slot reserved so that permanent artifacts — the event log (§73),
> telemetry records (§33) and strategy memory (§21) — are attributable when multi-tenancy is
> eventually built. Records written without it could never be correctly attributed afterwards, and
> backfilling a guessed tenant onto real historical data would violate §67.

**Root set — `decisions.md` D-033, decided by the human owner.** `tenant_id` is **root-only**. It is
required on `TaskGenome`, `ReliabilityContract`, `Plan`, `MissionState` and `MissionEvent`, and is
**not** duplicated on nested `PlanStep` or `AgentTask`.

Accepted risk, recorded so it is not rediscovered later: if strategy-memory or telemetry records are
eventually stored **detached** from their mission root (§21, §25), the tenant must be carried by the
storage layer or re-attached at write time. A V1.0 concern, but a real cost of this choice.

> **Still open:** **D-032** (the literal default value) and **D-034** (whether `plan_id` and
> `event_id` legitimately belong in invariant 18's identifier list, given §54 names only five).

## 8. Implementation constraints

- Pydantic v2, in `eidos.contracts`.
- Typed and validated. No untyped dicts cross the module boundary.
- No model, vendor or SDK reference (invariant 9).
- No I/O, no network, no LLM call — construction and validation only (V0.1 is in-memory, D-005).
- Unit tests in `tests/unit/` must cover construction, field validation, and **rejection of invalid
  input**, not only the happy path.

---

## Open questions

| Id | Question | Blocks |
|---|---|---|
| D-057 | How is `risk_level` determined? §5's user-stated tolerance maps to the contract; the assessed value's provenance is unspecified | V0.2 policy validation |
| D-056 | The concrete **task-risk value set**. D-051 settled the structure; the handoff contains no task-risk scale, and §40's was explicitly declined | **V0.1, the field's type** |
| D-031 | Is `evidence_requirements` a numeric threshold or a descriptive task requirement? | V0.1, one field |
| D-007 | Capability vocabulary and matching semantics | V0.2 capability validation |
| D-014 | Does `autonomy_level` use the §29 0–4 scale, and what is §40's concept called instead? | V0.1 |
| D-016 | What measurement procedure sits behind `quality_threshold`? | V0.1 |
| D-014 | Does `autonomy_level` use the §29 0–4 scale? | V0.1, one field's type |
| D-045 | Is the ReliabilityContract reference required or optional? | V0.1, one flag |
| — | Exact field names and units (e.g. `latency_budget` vs `latency_budget_ms`), and which of the ten fields are required vs optional. The handoff's list is explicitly "conceptual" and its example is partial. | V0.1 |

## Out of scope for this document

How genomes are produced from natural language (that is a planner concern), strategy generation
(`03_architecture.md`), reliability enforcement (`10_reliability.md`).
