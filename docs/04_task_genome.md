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

**Unresolved.** Four concerns appear in both the Task Genome (§6) and the Reliability Contract
(§30): quality threshold, latency budget, resource/token budget, and autonomy/approval requirements.
The handoff never states whether the contract is derived from the genome, is a separate user input,
or overrides the genome.

This blocks V0.1. See `decisions.md` **D-013**.

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
Invariant 18 reads as "these exist from the start"; whether V0.1 carries `tenant_id` as a real field
has not been confirmed.

See `decisions.md` **D-019**.

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
| D-013 | TaskGenome vs ReliabilityContract — which is authoritative, and is one derived from the other? | V0.1 |
| D-007 | Capability vocabulary and matching semantics | V0.2 capability validation |
| D-014 | Does `autonomy_level` use the §29 0–4 scale, and what is §40's concept called instead? | V0.1 |
| D-016 | What measurement procedure sits behind `quality_threshold`? | V0.1 |
| D-019 | Does `tenant_id` appear in V0.1? | V0.1 |
| — | Exact field names and units (e.g. `latency_budget` vs `latency_budget_ms`), and which of the ten fields are required vs optional. The handoff's list is explicitly "conceptual" and its example is partial. | V0.1 |

## Out of scope for this document

How genomes are produced from natural language (that is a planner concern), strategy generation
(`03_architecture.md`), reliability enforcement (`10_reliability.md`).
