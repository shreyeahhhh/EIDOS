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
| `evidence_requirements` | What evidence the result must carry — ⚠️ **not in V0.1**, see D-031/D-070 |
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

**The reference is required — `decisions.md` D-045.** Every `TaskGenome` must reference a
`ReliabilityContract`. EIDOS's reliability and evaluation semantics require explicit acceptance
criteria: without a contract there is no defined referent for satisfaction, required quality, or
mission-level budgets. Invariant 13 would have nothing to report against, §31's comparison would have
nothing on its right-hand side, and §49's evaluation step would have nothing to evaluate.

This is the one V0.1 decision that **departs from a literal reading of the handoff's wording** —
§30 says a mission "can have" a contract. It is recorded as such in D-045. Whether the contract is
always user-supplied or may be synthesised is **D-066**. Per-field optionality is settled: the six
budgets are optional (**D-065**), the three non-budget fields are required (**D-073**).

> **The sub-ambiguities D-013 left open are now all resolved.** D-013 settled the structural rule
> only; these settle the particular pairs:
>
> - **D-030 — resolved.** `risk_level` (assessed/intrinsic risk of the task) and
>   `ReliabilityContract.max_risk_level` (maximum risk the mission may tolerate) are **distinct
>   quantities**, one in each model. This is the case where a shared name is a comparison pair rather
>   than a duplicate. **D-051** supplies the shared vocabulary that makes the comparison well-formed;
>   **D-056** still owes the value set. How either value is *calculated* is deliberately out of
>   scope — see **D-057**.
> - **D-051 / D-056 — resolved.** The shared task-risk vocabulary is
>   `RiskLevel = low | medium | high`, a closed ordinal word-valued scale. Not reused for §40 action
>   risk or §28 tool risk.
> - **D-031 — resolved.** V0.1's `TaskGenome` **does not carry `evidence_requirements`**;
>   `min_independent_evidence` lives on the `ReliabilityContract` per §30. Nothing in V0.1 produces,
>   consumes or checks evidence — verification is V0.4, the evidence judge V0.8 — and **D-041**
>   already set this precedent by excluding evidence fields from `MissionState`. Whether the field is
>   ultimately a duplicate of the contract clause or a distinct descriptive requirement is **D-070**,
>   deferred to V0.4/V0.8. **No replacement representation may be defined meanwhile.**

## 5. Autonomy level

§6's example sets `"autonomy_level": 1`. §29 defines a five-level scale:

```text
Level 0  Recommend only
Level 1  Safe read-only actions
Level 2  Reversible actions
Level 3  Human approval required
Level 4  Authorized autonomous execution
```

**Resolved — `decisions.md` D-014, decided by the human owner.** `TaskGenome.autonomy_level` uses
this §29 scale. No additional levels are invented.

§29 is the **only** autonomy enumeration in the handoff, and the evidence is consistent: §6's example
value `1` matches both the read-only mission it describes and §29's "Level 1 Safe read-only actions".
This is deliberately *unlike* the risk case (**D-056**), where the handoff supplies no task-risk
scale at all — here declining the scale would discard evidence rather than avoid an invention.

Nothing enforces this in V0.1; the policy engine is V1.2. Only the field's type was at stake. Note
that `autonomy_level` carries more enforcement weight than `risk_level`, because §29 is the
governance spine — per D-051, §29 uses no risk scale at all.

> **Still open:**
> - **D-060** — §29's levels may not be one ordered dimension. Levels 0, 1, 2 and 4 describe what the
>   system *may do* and are monotonic; **level 3 describes a *process*, not a capability class**, and
>   §29's own `Modify configuration → human approval` example maps an action to a **gate** rather
>   than to a level. Whether `autonomy_level` is truly ordinal is unresolved.
> - **D-061** — approval is expressible twice: mission-wide level 3, and the `HUMAN_APPROVAL`
>   `PlanStepKind` (§13). Their relationship is unstated. Two mechanisms for one concept is the
>   pattern D-013 and §9/§10 both reject.
> - **D-062** — §40's "autonomy budget / autonomy debt" is a **different concept sharing the word**.
>   It must be given a distinct name before it is ever implemented. §40 itself marks it experimental.

## 6. Capabilities

`required_capabilities` is the input to capability discovery. The vocabulary problem is material:
§6 requires `architecture_analysis` and `security_analysis`, and the §7 registry example contains
neither. A genome written per §6 would not match a registry populated per §7.

See `decisions.md` **D-007** for the cross-mission vocabulary question, which remains genuinely
open. **It no longer blocks V0.2**: `decisions.md` **D-102** scopes V0.2 capability validation to a
check the V0.1 contracts already support without it — every `agent` `PlanStep`'s `capability` must
appear in this genome's own `required_capabilities`, exact-string, no external vocabulary or
registry needed. D-007 remains material at V0.4, when a real agent registry needs a real vocabulary
to bind against.

## 6a. Mission ownership — `decisions.md` D-068

**`TaskGenome` is mission-owned and does NOT carry `mission_id`.** Ownership is expressed through
**containment** by `MissionState`, which under **D-010a** already holds `task_genome`. Adding a
back-reference would put one value in two places and make "a genome for mission X inside a state for
mission Y" representable — the duplication **D-013** rejected for constraints and §9/§10 reject for
state.

The reusable-descriptor reading was rejected on the handoff's own terms. Every creation reference is
per-mission (§5, §41, §73, and the loop in §2/§46/§83); §54's identifier list contains no genome id;
and **D-045** makes the genome reference a mission-specific contract, which a reusable genome could
not coherently carry.

The decisive detail is in §21, which stores **`task_class`** *and* **`task_genome characteristics`**
as two separate entries. If the genome were itself the similarity key, `task_class` would be
redundant — and the second entry is not `task_genome` but its **characteristics**, i.e. features
*derived from* the genome. §22 confirms this by keying learning on `task type`.

> **Still open:** **D-071** — whether detached or reusable genome representations are ever needed. If
> a genome is stored apart from its `MissionState` (§21, §25, §33), attribution must come from the
> storage layer. Adding a back-reference then would be additive.

## 6b. Field presence — `decisions.md` D-077

| Field | Presence | Basis |
|---|---|---|
| `tenant_id` | required | D-019 |
| `goal` | required | present in §6's example |
| `required_capabilities` | required | present in §6's example |
| `information_dependencies` | **optional** | **omitted from §6's own example** — D-065's demonstration-of-omission standard |
| `risk_level` | required | present in §6's example |
| `autonomy_level` | required | present in §6's example |
| `allowed_actions` | required | present in §6's example |
| `reliability_contract` | required | D-045 |

An optional field may be absent. A required collection may be **empty** — **D-087** settles that
empty collections are legal in V0.1.

## 6c. Representation — `decisions.md` D-080, D-089, D-094, D-099, D-100

| Field | Representation |
|---|---|
| `required_capabilities` | immutable collection of **`CapabilityId`** (D-080) |
| `allowed_actions` | immutable collection of **`ActionId`** (D-080, refining D-094) |
| `information_dependencies` | optional immutable collection of opaque strings (D-099) |
| `reliability_contract_id` | **`ReliabilityContractId`** — a reference, not the contract (D-089, D-100) |

`CapabilityId` and `ActionId` are **string-backed and exempt from D-053's UUID rule**: §13's own example
writes `"capability": "research"`, and the planner emits capabilities inside the Plan DSL. No capability
or action vocabulary is defined yet (D-007).

The full `ReliabilityContract` is held by **MissionState**, not by the genome (**D-100**).

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
| D-070 | Is `evidence_requirements` a duplicate of `min_independent_evidence`, or a distinct descriptive requirement — and if distinct, what representation? | V0.4 / V0.8 |
| D-031 | Is `evidence_requirements` a numeric threshold or a descriptive task requirement? | V0.1, one field |
| D-071 | Will detached or reusable genome representations ever be needed? | V1.0 strategy memory |
| D-007 | Capability vocabulary and matching semantics | V0.4 (not V0.2 — see D-102) |
| D-014 | Does `autonomy_level` use the §29 0–4 scale, and what is §40's concept called instead? | V0.1 |
| D-015 | How measurable proxies combine into an evaluated quality figure | V0.4, V1.2 |
| D-060 | Is §29's level 3 an ordinal point or a gate cutting across the scale? | V1.2 policy engine |
| D-061 | Mission-wide `autonomy_level` vs the `HUMAN_APPROVAL` step kind | V0.3/V1.2 |
| D-066 | Is the contract always user-supplied, or may EIDOS synthesise one? | mission creation; depends on D-046 |
| — | Exact field names and units (e.g. `latency_budget` vs `latency_budget_ms`), and which of the ten fields are required vs optional. The handoff's list is explicitly "conceptual" and its example is partial. | V0.1 |

## Out of scope for this document

How genomes are produced from natural language (that is a planner concern), strategy generation
(`03_architecture.md`), reliability enforcement (`10_reliability.md`).
