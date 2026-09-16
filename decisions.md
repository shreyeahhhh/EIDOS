# decisions.md — EIDOS Architectural Decision Record

Every decision that shapes EIDOS is recorded here. Nothing is decided silently.

**Statuses**

- `Accepted` — decided. Who decided it is stated explicitly.
- `Open` — an ambiguity, contradiction or gap that has been identified and **deliberately not
  resolved**. Requires the human owner. Implementation that depends on an Open item is blocked.
- `Deferred` — specified but intentionally not implemented until a named milestone.

**Rules**

- Only the human owner decides `Open` items. Claude Code records and raises them.
- A default that "looks obvious" is still a decision. It goes here before it goes into code.
- Changing an `Accepted` item that touches an invariant requires explicit human approval and a new
  entry superseding the old one.

Entry format: id, title, status, date, handoff source, context, decision/question, consequences.

---

## Accepted

### D-002 — Repository layout

- **Status:** Accepted · **Date:** 2026-09-16 · **Decided by:** Claude Code (bootstrap), approved by human owner
- **Source:** handoff §62, §81; project rule "keep the repository lean"
- **Context:** The project needs an importable Python package and a test structure before any
  contract work begins. The handoff specifies four test layers (§62) and twelve documents (§81) but
  does not specify a source tree.
- **Decision:** `src` layout with a single package `eidos`. Four test layers exactly as §62 names
  them: `tests/unit`, `tests/integration`, `tests/protocol`, `tests/scenarios`. Documents follow
  §81's list and numbering verbatim. **Packages are created only when the milestone that fills them
  begins** — future architecture is documented in `docs/03_architecture.md`, not scaffolded. At
  bootstrap this means `src/eidos/` and `src/eidos/contracts/` exist and nothing else does.
- **Consequences:** The source tree stays small and every directory has a current owner and purpose.
  Adding a package is a visible, reviewable act tied to a milestone. The four test directories exist
  ahead of their content because they define where tests belong, which is a documentation function.

### D-003 — Python version and dependency floor

- **Status:** Accepted · **Date:** 2026-09-16 · **Decided by:** Claude Code (bootstrap), approved by human owner
- **Source:** handoff §51, §76 (Python, Pydantic v2, Pytest). The handoff does not state a Python
  version.
- **Context:** A version and a dependency set are required for the package to be importable and for
  tests to run at all.
- **Decision:** `requires-python = ">=3.11"`. Runtime dependency: `pydantic>=2`. Dev dependency:
  `pytest`. Nothing else is declared until a milestone requires it.
- **Consequences:** Reversible tooling choice, not an architectural one. If the owner prefers a
  different floor, changing it costs one line. No LangGraph, FastAPI, Qdrant, Ollama,
  sentence-transformers, Redis, OpenTelemetry or frontend dependency is installed — each arrives at
  its own milestone per §50.

### D-004 — Plan DSL canonical representation is an ID-addressed DAG

- **Status:** Accepted · **Date:** 2026-09-16 · **Decided by:** human owner
- **Source:** handoff §13 (Plan DSL), §14 (validation pipeline)
- **Context:** §13's example plan is a *nested tree* (`{"type": "parallel", "steps": [...]}`), which
  structurally cannot contain a cycle. §14 nevertheless mandates dependency validation and cycle
  detection, which presumes identified steps and explicit edges. The two readings imply entirely
  different validators, so the representation had to be settled before any contract work.
- **Decision:** The canonical internal representation of a plan is an **ID-addressed DAG**: every
  step carries an explicit id and every dependency is an explicit edge. **Validation and compilation
  operate only on that form.** A nested or tree-shaped representation may be supported later as
  syntactic sugar, but it must be normalized into the DAG before validation runs.
- **Consequences:** Becomes invariant 4. Cycle detection and dependency validation are meaningful
  rather than vacuous. Plan contracts must carry step ids and edges from the first version. Any
  future nested surface syntax needs an explicit, tested normalization step — it can never reach the
  validator in tree form. The exact edge encoding (e.g. `depends_on` on each step vs a separate edge
  list) is **not** settled by this decision; see D-010's neighbourhood and raise it before
  implementing.

### D-005 — V0.1 is in-memory only; no persistence

- **Status:** Accepted · **Date:** 2026-09-16 · **Decided by:** human owner
- **Source:** handoff §50 (V0.1 Core Contracts), §51 (SQLite named in the local stack), §82
- **Context:** §51 names SQLite in the intended local stack, but §50's V0.1 is contracts only and
  §82 requires the first slice to be "small, deterministic, testable". Whether V0.1 persists
  anything was not stated.
- **Decision:** V0.1 stays implementation-light: **in-memory typed contracts, deterministic
  validation-oriented structures, and tests. No SQLite, no storage layer, no migrations.**
- **Consequences:** Contracts can be designed without a storage schema constraining them. Tests stay
  fast and hermetic. Persistence beyond V0.1 remains unresolved — see D-017.

### D-013 — TaskGenome and ReliabilityContract are disjoint; neither duplicates the other

- **Status:** Accepted · **Date:** 2026-09-16 · **Decided by:** human owner
- **Source:** handoff §5, §6, §30, §53; with §21 and §22 as the deciding consideration
- **Context:** Four concerns are named in both models. §6 lists `quality_threshold`,
  `latency_budget`, `resource_budget` and `evidence_requirements` in the Task Genome; §30 lists
  minimum quality, maximum latency, maximum tokens, maximum risk, minimum independent evidence and
  approval requirements in the Reliability Contract. The handoff never states which is
  authoritative, whether one derives from the other, or what happens when they disagree. The two
  sections are additionally irreconcilable in tone: §6 is mandatory ("should contain"), §30 is
  optional ("can have"). A mandatory structure cannot be a projection of an optional one.

  Four interpretations were analysed: (A) genome authoritative, contract a projection of it;
  (B) contract authoritative, genome copies its values; (C) two independent inputs with the contract
  overriding on conflict; (D) disjoint decomposition with no field in both.

- **Decision: interpretation D.**
  - **TaskGenome** describes the task and its intrinsic requirements.
  - **ReliabilityContract** defines execution acceptance constraints.
  - **Constraint thresholds are not duplicated across the two models.**
  - **TaskGenome references the ReliabilityContract rather than copying its threshold values.**

- **Rationale:** The decisive argument is §21 and §22, not tidiness. §21 stores "task_genome
  characteristics" as strategy-memory material and §22 ranks strategies for "a future similar task",
  which makes the genome load-bearing as a **task-similarity key**. Constraints are not part of task
  similarity: a migration assessment with a 10-minute budget and the same assessment with a
  60-minute budget are the same task with different acceptance criteria. Under A or B they would be
  different genomes and would stop matching each other in strategy memory — degrading the project's
  central learning mechanism **invisibly**, with no error and no failing test.

  C was rejected on the handoff's own reasoning: it institutionalises two sources of truth for one
  value and pushes a precedence rule onto every reader. That is structurally the failure mode §9 and
  §10 spend their length eliminating for MissionState; reproducing it one layer up for constraints
  would be internally inconsistent. It also permits internally inconsistent missions that still
  validate.

  D's cost is departure from §6's literal field list. Two things soften it: §6 hedges with
  "conceptually equivalent" rather than prescribing a schema, and under composition the values
  remain reachable *through* the genome, so the genome still functions as "a contract, not metadata"
  in the sense §6 intends. §53's API concept already separates `goal` from a nested `constraints`
  object, which is consistent with D.

- **Consequences:**
  - No precedence rule is needed anywhere, because no value has two homes. No drift, no
    synchronisation obligation, no conflict-resolution branch in planner, validator, policy,
    verifier, telemetry or UI.
  - Invariant 13 gains a single unambiguous referent: "could not satisfy the reliability contract"
    names exactly one object.
  - The genome remains a clean similarity key for V1.0/V1.1 strategy memory.
  - Composes directly with **D-009**: what applies when §30's optional contract is absent is a
    D-009 question (bounds origin), not a D-013 question, and remains Open.
  - **D-016** attaches to whichever model hosts the quality threshold — now the ReliabilityContract.
  - Two sub-ambiguities are **deliberately left Open** by the human owner and are recorded as D-030
    and D-031. Until they are answered, one field of each model remains undetermined. D-013 resolves
    the structural question only.

### D-019 — `tenant_id` is present and required on V0.1 root models

- **Status:** Accepted · **Date:** 2026-09-16 · **Decided by:** human owner
- **Source:** handoff §54; with §21, §33 and §73 as the deciding consideration
- **Context:** §54 says data models "should **conceptually include** identifiers **such as**"
  `tenant_id`, `mission_id`, `execution_id`, `agent_id`, `timestamp`, while warning that the MVP
  must not become an authentication project. "Conceptually include" reads two ways: the field
  exists now carrying a placeholder, or the design is merely *shaped* to accept it later. Three
  options were analysed: (A) present, required, fixed default; (B) omitted until the multi-tenancy
  milestone; (C) present but nullable.

- **Decision: option A.**
  - `tenant_id` is **present and required** on V0.1 root models.
  - It carries a **single fixed default value**.
  - It has **no security meaning in V0.1** and **must not** be treated as an authentication,
    authorization, or isolation mechanism.

- **Rationale:** The cost asymmetry decides it. Option A's cost is cosmetic — a constant-valued
  field — and is paid once, in V0.1. Option B's cost is structural, paid later, and **partly
  unrecoverable**: the event log (§73), telemetry records (§33) and strategy memory (§21) are
  permanent artifacts that accumulate across the life of the project. Records written before the
  field exists can never be correctly attributed afterwards, and backfilling a guessed tenant onto
  real historical data would collide with §67's rule that every numerical claim comes from an actual
  experiment. Since accumulated history is the input to the project's central thesis, degrading it
  is not a cost worth paying to save one field.

  Option C was rejected independently of A-vs-B: nullable identity forces a `None` branch on every
  reader and creates two states — "no tenant" and "default tenant" — that mean the same thing while
  comparing unequal, at exactly the boundary where correctness will eventually matter most.

- **Consequences:**
  - The no-security caveat is **binding** and must be restated wherever the field is documented.
    The realistic failure mode of this decision is a future reader mistaking a defaulted
    `tenant_id` for an access-control boundary. That is mitigated by documentation, not by code.
  - Invariant 18 holds as written; no invariant amendment is required. (Option B would have needed
    one.)
  - Persistence (**D-017**) gains a required column rather than a retrofitted one.
  - Three sub-questions are **deliberately left Open** by the human owner: **D-032** (the literal
    default value), **D-033** (root-only vs propagation to nested models), **D-034** (whether
    `plan_id` and `event_id` belong in invariant 18's list at all).

### D-011 — Event identity and ordering: layered model; V0.1 scope is `event_id` plus an EIDOS-assigned mission sequence

- **Status:** Accepted · **Date:** 2026-09-16 · **Decided by:** human owner
- **Source:** handoff §10, §8, §33, §73; with invariant 2 as the deciding consideration on authority
- **Context:** §10 requires every external event to carry "some form of" `event_id`, `a2a_task_id`,
  `sequence/version`, `timestamp`, and mandates idempotent processing with deterministic accept or
  reject for late and out-of-order events. It does **not** define the ordering domain (per-mission
  counter, per-`a2a_task_id` counter, per-producer counter, or version vector), does **not** define
  the idempotency key (`event_id` alone vs `(a2a_task_id, sequence)`), does **not** say who assigns
  the ordering value, and addresses only *external* events although eleven of §33's thirteen event
  types are internal.

  Four options were analysed: (A) single per-mission counter with `event_id` idempotency;
  (B) per-`a2a_task_id` counter with composite idempotency; (C) version vector / per-producer
  causality; (D) a layered decomposition separating the three roles §10 conflates.

- **Decision: option D for the overall event model**, with V0.1 scoped deliberately narrower.

  The overall model separates three distinct roles rather than overloading one field:
  1. **Identity** — `event_id`, the idempotency key, meaningful for all event types.
  2. **Mission order** — a monotonic per-mission sequence assigned by EIDOS.
  3. **Remote-lifecycle order** — a producer-assigned per-`a2a_task_id` sequence used only to
     validate a remote event against that task's lifecycle. **Deferred; see D-035.**

  **For V0.1 specifically:**
  - `event_id` **is** the idempotency key.
  - EIDOS assigns a **monotonic per-mission sequence** when an event is **accepted into the EIDOS
    event stream**.
  - That mission sequence **is** the ordering used for deterministic replay.
  - **A2A-specific producer ordering is not introduced in V0.1.**

- **Rationale:** D is a decomposition of §10 rather than a selection among its readings. §10's
  `sequence/version` is doing three jobs simultaneously — identity, mission ordering, and remote
  lifecycle ordering — and most of the ambiguity dissolves once they are separated. A serves replay
  but cannot express lateness for a specific remote task; B serves remote lifecycle but has no
  meaning for the eleven internal event types and leaves the idempotency key undefined for every
  event V0.1 will actually emit; C imports distributed-systems machinery disproportionate to a V0.6
  target of exactly one A2A boundary (§50) and to §52's warning against premature distribution.

  **Ordering authority sits with EIDOS**, not the producer. This follows from invariant 2 — a remote
  agent is precisely the component that must not control EIDOS state — rather than from §10, which
  is silent on assignment. Assigning at acceptance also makes the sequence a property of the EIDOS
  event stream rather than of any external system's reliability.

- **Consequences:**
  - The `MissionEvent` shape is determined for V0.1, which was the blocking question.
  - Replay (§73, invariant 15) has a total order per mission and is deterministic.
  - Duplicate suppression is well-defined for all thirteen §33 event types, including the eleven
    internal ones §10 does not describe.
  - Deliberately **not** resolved, and recorded as Open at the owner's instruction: **D-035**
    (A2A producer-assigned per-task sequence), **D-036** (the `AgentTask` lifecycle state machine
    that "validate against lifecycle" presupposes), **D-037** (one common event shape vs separate
    internal/external shapes), **D-038** (bounding and persisting the processed-`event_id` set).
  - D-036 is the sharpest of those: §10 mandates deterministic accept/reject against a lifecycle,
    and §8 gives `AgentTask.status` without enumerating states or legal transitions. Until D-036 is
    answered, the V0.6 protocol tests for late and out-of-order events cannot be written.

### D-010a — MissionState is a materialized view over the event log

- **Status:** Accepted · **Date:** 2026-09-16 · **Decided by:** human owner
- **Source:** handoff §9, §10, §11, §15, §32, §33, §73
- **Context:** The stated gap was that §9 fixes MissionState's *ownership* without ever enumerating
  its shape. The gap underneath it is a **boundary question**: §9 asserts MissionState is the *only*
  authoritative global state, §11 assigns LangGraph management of *execution state*, and §9's own
  diagram shows the reducer writing into "LangGraph checkpoint/state". Two state stores demonstrably
  exist and one is asserted uniquely authoritative. That is coherent only if LangGraph's state is
  subordinate — but the handoff never says where the line falls, so "which fields" had no principled
  answer, only an arbitrary one.

  Three boundaries were analysed: (A) maximal MissionState including per-node execution status, with
  LangGraph holding a projection; (B) minimal MissionState holding mission-level facts, with
  per-node progress in LangGraph checkpoints; (C) a "hold only what cannot be recomputed" rule.

- **Decision: Boundary B.**

  MissionState is a **materialized view over the event log** and contains exactly the information
  the runtime must answer **synchronously**:

  - mission identity
  - TaskGenome
  - mission status and reason
  - plan versions and lineage
  - active plan
  - remote `AgentTask` records
  - budget consumption counters

  **Detailed per-node runtime execution state does not enter the authoritative MissionState merely
  because LangGraph has such state.**

- **Rationale:** The objection that appears fatal to B — "then replay is incomplete" — dissolves on
  a careful reading of §73: replay consumes the **event log**, not MissionState. Completeness is a
  property the event log must have; MissionState need only be the fold over it. Per-node progress
  can be fully reconstructible from events without being a MissionState field.

  A was rejected because it would quietly make LangGraph's execution model part of the authoritative
  contract. §11, §12 and §15 spend their length keeping the runtime replaceable and the plan
  declarative; encoding node-level runtime status into the one authoritative state object would undo
  that, and would make every node transition a global state write.

  C collapses on inspection: MissionState *is* `fold(events)`, so under a strict "only what cannot be
  recomputed" rule it would hold nothing.

  The field set above is **derived rather than chosen**. Each entry corresponds to a question the
  runtime must answer before it can act: may this mission continue (§32 budgets); which plan version
  is active and what is the lineage of failed ones (§15); what is the state of each remote task
  (§8, §10); is human review required (§32); what is this mission and what would count as acceptable
  (§6, §30).

- **Consequences:**
  - The last V0.1 blocker on the `MissionState` contract is removed.
  - The completeness burden shifts onto the **event log**, not onto MissionState. This is a real
    obligation on every subsequent milestone: an event that is not recorded is not replayable.
  - **This substantially pre-answers D-017.** If MissionState is a materialized view, the event log
    is the durable artifact and any snapshot is an optimisation. **D-017 is not being resolved
    here** — it is flagged so the consequence is visible rather than arriving later as a fait
    accompli.
  - Four questions deliberately left Open by the owner: **D-039** (reducer signature, at V0.5),
    **D-010b** (checkpoint semantics, at V0.5), **D-040** (the exact MissionState/LangGraph boundary,
    at V0.3), **D-041** (evidence and final mission-result fields, at V0.4 and V0.8).
  - The reducer signature turned out **not** to be a V0.1 blocker. V0.1 needs the contract; the
    reducer is V0.5 work. The V0.1 decision is correspondingly smaller than first proposed.

### D-009 — Bounds split by category: system safety limits vs mission execution budgets

- **Status:** Accepted · **Date:** 2026-09-16 · **Decided by:** human owner
- **Source:** handoff §5, §14, §30, §32; with §12's purpose for bounded synthesis as the deciding
  consideration
- **Context:** §14 lists eight plan limits and says a plan exceeding them "must be rejected"; §32
  repeats five of them as execution-time hard limits; §30's contract carries maximum latency and
  maximum tokens; §5 has the *user* state maximum latency and a resource/token budget. The handoff
  never says which source is authoritative, and gives no values outside two examples.

  Four options were analysed: (A) all bounds are static system configuration; (B) all bounds come
  from the ReliabilityContract; (C) split by category with a system ceiling; (D) contract-only with
  defaults and no ceiling.

- **Decision: option C.**
  1. **Runtime shape/complexity limits are system-level safety limits.** Examples include
     `max_nodes`, `max_depth`, `max_parallel_branches`.
  2. **Mission-specific execution budgets are carried by the ReliabilityContract.** Examples include
     `max_retries`, `max_replans`, `max_agent_calls`, `max_tool_calls`, `max_execution_time`,
     `max_tokens`.
  3. **A mission may tighten a system limit but may never exceed the system safety ceiling.**
  4. **Do not silently clamp an invalid contract.** If a requested contract value exceeds the system
     ceiling, **reject it with an explicit validation reason**.
  5. **Do not establish numerical defaults in V0.1.** Bound values remain Open until the V0.2
     validation work, where they can be defined and later tuned from actual measurements.

- **Rationale:** A contradicts §5 and §30, which demonstrably let the user state maximum latency and
  a token budget; under A those inputs would be decorative. B inverts the purpose of bounded
  synthesis: §12 and §14 bound plan shape to protect **the runtime** from an LLM's output, not to
  express user preference, and a user-chosen graph-depth limit is close to meaningless. Splitting by
  category puts each limit where its purpose lies — shape limits protect the runtime, budgets
  express mission intent.

  Rider 4 follows from invariant 5. §14 requires a plan exceeding its limits to be **rejected**;
  silently clamping an over-large contract would apply the opposite rule one layer up, and would hide
  from the user that they did not get what they asked for.

  Rider 5 follows from §67 and CLAUDE.md §7. Only two numbers in this area are handoff-sourced —
  `max_execution_time` ≈ 600s (§6) and `max_tokens` = 10,000 (§30) — and both appear as *examples*.
  Any other value would be invention presented as engineering.

- **Consequences:**
  - The last V0.1 blocker is closed. The `ReliabilityContract` contract can be defined.
  - Two objects exist rather than one, and `effective = min(system, contract)` becomes a rule every
    reader of a limit must know. That cost is accepted deliberately.
  - Resource validation and graph-complexity validation (two of §14's eight stages) have a defined
    source of authority, though not yet values.
  - MissionState's budget counters (**D-010a**) must correspond to whatever budget set **D-042**
    settles.
  - Six questions deliberately left Open: **D-042** (exact contract budget field list), **D-043**
    (declared plan limits vs actual execution counters), **D-044** (whether `max_tokens` formally
    joins §14's and §32's lists), **D-045** (behaviour when no contract is supplied), **D-046**
    (numerical values), and **D-029** (the Agentic RAG reformulation bound).

### D-033 — `tenant_id` is root-only; nested models do not duplicate it

- **Status:** Accepted · **Date:** 2026-09-16 · **Decided by:** human owner
- **Source:** handoff §54 (silent on this point); follows D-019
- **Context:** D-019 established that `tenant_id` is required on "root models" without defining the
  root set. Root-only avoids redundancy, since nested models are reachable through a root that
  already carries the value. Propagation would make records self-describing when extracted from
  their root, which matters for telemetry rows and for anything later stored in a vector collection
  (§25's `executions` / `strategies`).

- **Decision:** **root-only.** `tenant_id` is **required** on:
  `TaskGenome`, `ReliabilityContract`, `Plan`, `MissionState`, `MissionEvent`.
  It is **not** duplicated on nested `PlanStep` or `AgentTask`.

- **Consequences:**
  - The root set is now fixed, which also settles which models are roots for every later identity
    question.
  - Accepted risk, recorded so it is not rediscovered later: if strategy-memory or telemetry records
    are eventually stored **detached** from their mission root (§21, §25), the tenant will have to be
    carried by the storage layer or re-attached at write time. That is a V1.0 concern, not a V0.1
    one, but it is a real cost of this choice rather than a free simplification.

### D-047 — V0.1 Plan DSL scope: structure without conditional semantics

- **Status:** Accepted · **Date:** 2026-09-16 · **Decided by:** human owner
- **Source:** handoff §13, §50; follows D-004; scopes but does **not** resolve D-012
- **Context:** Four of §13's eight primitives — `ROUTE`, `RETRY`, `REPLAN`, `TERMINATE` — are
  conditional, and no predicate or expression language is specified for any of them (D-012). Either
  V0.1 carries an opaque placeholder for conditional payloads, or it defines plan structure only and
  defers conditions entirely.

- **Decision:** V0.1 defines:
  - the **eight PlanStep kinds**,
  - **explicit step IDs**,
  - **capability**,
  - **dependency edges**,
  - **DAG structure**.

  V0.1 does **not** define a predicate or condition language for `ROUTE`, `RETRY`, `REPLAN` or
  `TERMINATE`. Conditional payloads and predicate semantics are deferred to V0.2 under **D-012**.

- **Rationale:** An opaque placeholder field would be an untyped value crossing a module boundary,
  which CLAUDE.md §8 forbids, and would invite something to start depending on its shape before the
  shape is decided. Defining structure without semantics keeps V0.1 fully typed and leaves D-012 a
  clean decision rather than a migration.

- **Consequences:**
  - The `PlanStep` contract is complete and typed for V0.1 with no placeholder fields.
  - **D-012 remains Open** and is unaffected. This decision scopes V0.1; it does not choose a
    predicate language.
  - V0.2 will add conditional payloads to `PlanStep`, which is an additive contract change rather
    than a reinterpretation of an existing field.
  - A V0.1 plan containing a conditional kind is structurally valid but semantically incomplete.
    Nothing in V0.1 executes plans, so this is inert — but it must not silently become executable at
    V0.3 without D-012.

### D-048 — `AgentTask` is included in V0.1, minimal and future-compatible

- **Status:** Accepted · **Date:** 2026-09-16 · **Decided by:** human owner
- **Source:** handoff §8, §50; interacts with D-036
- **Context:** §50 explicitly lists `AgentTask` among the V0.1 Core Contracts, but V0.1 has no A2A,
  so every `a2a_*` field is inert and `status` has no enumerated lifecycle (D-036). Including it
  risks a hollow model; deferring it to V0.6 would depart from §50's explicit list.

- **Decision:** **include it in V0.1, because §50 explicitly includes it.** Minimal and
  future-compatible:
  - `agent_id`
  - `a2a_task_id` — optional
  - `a2a_context_id` — optional
  - `status`
  - `latest_artifact` — optional
  - `last_event` — optional

  **No A2A behaviour is implemented in V0.1.** `status` semantics remain Open under **D-036**.

- **Consequences:**
  - The V0.1 contract set matches §50's list exactly, with no omission to explain.
  - The A2A fields being optional is what makes the model honest in a world without A2A, and what
    lets V0.6 populate them without a contract change.
  - `status` cannot be a closed enumeration until D-036 defines the state set and legal transitions.
    Until then it is deliberately unconstrained, and **nothing may branch on its value** — a
    transition check written against an undefined lifecycle would encode D-036 silently.
  - Per **D-033**, `AgentTask` is nested and does **not** carry `tenant_id`.

---

## Open — require the human owner

These are ambiguities, contradictions and gaps found in the handoff during the bootstrap read. None
has been resolved. Work that depends on one of them is blocked until the owner decides.

Count: 40. Highest-impact first is **D-015** (how verification confidence is computed), then
**D-049** and **D-050** (the `PlanStepKind` value set), then **D-007** (capability vocabulary) and
**D-012** (predicate language) for V0.2.

**Standing rule for all Open items:** no placeholder enum, type, sentinel or inferred value may be
invented to make code compile. An Open item blocks the field it touches; it does not license a
guess. Where a type cannot be written without an answer, the field waits.

**All five decisions blocking V0.1 were resolved on 2026-09-16** and moved to Accepted: **D-013**,
**D-019**, **D-011**, **D-010a**, **D-009**. Each exposed sub-questions that the owner deliberately
kept Open rather than resolving by implication — D-030 and D-031 from D-013; D-032 through D-034
from D-019; D-035 through D-038 from D-011; D-010b and D-039 through D-041 from D-010a; D-042
through D-046 from D-009. Three further V0.1 scoping decisions followed: **D-033**, **D-047**,
**D-048**.

Open items still touching V0.1: **D-014**, **D-016**, **D-030**, **D-031**, **D-042**, **D-045** —
each affecting one field, one flag or one type — plus **D-049**, **D-050**, **D-051** and **D-052**,
which were found while writing the V0.1 contract specification and **do block** the contracts they
touch. D-014 and D-016 predate the blocking-decision round and were not part of it. **D-053** and
**D-054** are minor and affect representation rather than structure.

D-049 and D-050 are the consequential ones: together they determine the `PlanStepKind` value set, and
D-050 arises from a consequence of **D-004** that was not visible when D-004 was taken. Neither
D-004 nor D-047 has been modified.

The Open count rising as decisions are made is expected and healthy: each resolution replaces one
vague question with several precise ones, and a precise Open item is cheap to answer while a vague
one is not.

### D-001 — Documentation numbering is internally inconsistent in the handoff

- **Status:** Open · **Source:** handoff §58, §60 vs §81
- **Finding:** §81 is the explicit "create these documents" list and numbers the architecture
  document `docs/03_architecture.md` (with `02` being `02_prd.md`). The example prompts in §58 and
  §60 instruct Claude to read `docs/02_architecture.md`.
- **Action taken:** Files were created exactly as §81 lists them, because §81 is the instruction to
  create files and §58/§60 are illustrative prompts. **This is not a resolution of the
  inconsistency** — it is compliance with the one section that gives a file-creation instruction.
  The contradiction inside the handoff stands and is reported here.
- **Needs:** Owner to confirm the numbering, or amend the handoff.

### D-006 — Which capabilities exist in the MVP agent set

- **Status:** Open · **Source:** handoff §49 vs §16, §43
- **Finding:** §49 says start with exactly three logical agents — Research, Analysis, Verification —
  and "do not build 10+". But the flagship demo (§43) and the candidate strategies (§16) both use
  five: Research, Security, Architecture, Analysis, Verification.
- **Needs:** Which capability set exists at V0.4? If three, the §43 demo cannot be run as written.

### D-007 — Capability vocabulary and matching semantics

- **Status:** Open · **Source:** handoff §6 vs §7
- **Finding:** The §6 Task Genome example requires `architecture_analysis` and `security_analysis`.
  The §7 registry example contains neither — it lists `research`, `document_analysis`,
  `evidence_extraction`, `vulnerability_analysis`, `dependency_analysis`, `technical_analysis`,
  `cost_analysis`, `evidence_validation`, `contradiction_detection`. A genome written per §6 would
  not match a registry populated per §7.
- **Needs:** Is capability matching exact-string against a controlled vocabulary, hierarchical
  (e.g. `analysis.security`), or similarity-based? Is there a canonical capability list, and who
  owns it? This blocks capability validation (§14) and capability discovery.

### D-008 — Lint and type-checking tooling not adopted

- **Status:** Open · **Source:** handoff §76 (does not name any linter or type checker)
- **Finding:** A linter and a type checker would normally be adopted at bootstrap, but the handoff's
  technology stack does not name one. Adopting `ruff`/`mypy` unasked would be an unapproved
  decision.
- **Action taken:** Neither is declared in `pyproject.toml`. `.gitignore` already ignores their
  caches so adding them later is frictionless.
- **Needs:** Owner to decide whether to adopt, and which.

### D-010b — Checkpoint semantics

- **Status:** Open · **Source:** handoff §9, §11 · **Split out of D-010; deliberately not resolved**
- **Finding:** §11 lists checkpoints among LangGraph's responsibilities and §9's diagram terminates
  at "LangGraph checkpoint/state", but checkpoint **granularity**, **trigger** and **contents** are
  never specified. D-010a settles the MissionState field set; it does not settle what a checkpoint
  is.
- **Effect while Open:** none on V0.1. Blocks V0.5.
- **Needs:** What a checkpoint contains, when one is taken, and whether resuming from a checkpoint
  replays events forward from it or restores a snapshot directly. Entangled with **D-017**.

### D-039 — The reducer signature

- **Status:** Open · **Source:** handoff §9, §10 · **Split out of D-010a, left Open by the owner**
- **Finding:** §10 requires duplicates to be ignored and late or out-of-order events to be accepted
  or rejected **deterministically**. A signature of `(state, event) -> state` makes a rejection
  indistinguishable from a no-op, leaving §33's telemetry nothing to count and making the
  determinism requirement untestable. A signature returning state **plus an outcome** makes it
  observable. Raising on duplicate or late events was considered and is a poor fit: §10 treats both
  as expected traffic rather than errors, and exceptions would be awkward to drive from a replay
  loop.
- **Effect while Open:** none on V0.1 — the reducer is V0.5 work; V0.1 needs only the contract.
- **Needs:** Decide at V0.5, alongside the reducer itself.

### D-040 — The exact MissionState / LangGraph execution-state boundary

- **Status:** Open · **Source:** handoff §9 vs §11 · **Split out of D-010a, left Open by the owner**
- **Finding:** §9 asserts MissionState is the *only* authoritative global state; §11 assigns
  LangGraph management of *execution state*; §9's own diagram shows the reducer writing into
  "LangGraph checkpoint/state". Two state stores demonstrably exist. D-010a sets the **principle** —
  detailed per-node runtime execution state does not enter authoritative MissionState merely because
  LangGraph holds such state — but the specific split is inherited work at V0.3 when a runtime
  exists.
- **Effect while Open:** none on V0.1. Material at V0.3.
- **Needs:** The concrete division once the runtime is being built, consistent with D-010a's
  principle and invariant 1.

### D-041 — Evidence and final mission-result fields in MissionState

- **Status:** Open · **Source:** handoff §30, §31, §74 · **Split out of D-010a, left Open by the owner**
- **Finding:** D-010a's field set deliberately excludes evidence and the final mission result.
  Evidence arrives with Agentic RAG at V0.8 and evidence lineage (§74, invariant 16); the mission
  result and its contract-satisfaction verdict (§30, invariant 13) arrive with verification at V0.4.
  Excluded by scope discipline, not by oversight.
- **Effect while Open:** none on V0.1.
- **Needs:** Decide at V0.4 (result) and V0.8 (evidence), each as its own milestone question.

### D-012 — Predicate language for conditional primitives

- **Status:** Open · **Source:** handoff §13
- **Finding:** `ROUTE`, `RETRY`, `REPLAN` and `TERMINATE` are all conditional, and routing must be
  deterministic (§11, §29), but **no expression or predicate language is specified** for any of
  them. Without one, either the condition is opaque (breaking determinism and validation) or an
  expression language is invented.
- **Needs:** How a condition is expressed, what it may read from MissionState, and how it is
  validated. Blocks the compiler and the ROUTE primitive.
- **V0.1 scope settled by D-047, which does not resolve this item.** V0.1 defines plan *structure*
  only — kinds, step IDs, capability, edges, DAG — and carries **no conditional payload at all**,
  rather than an opaque placeholder. D-012 therefore remains a clean V0.2 decision rather than a
  migration away from a guessed shape.

### D-014 — `autonomy_level` scale, and its collision with "autonomy budget"

- **Status:** Open · **Source:** handoff §6, §29, §40
- **Finding:** Two issues. (a) The §6 genome example sets `"autonomy_level": 1` and §29 defines
  levels 0–4; the same scale is implied but never stated. (b) §40 introduces an "autonomy budget /
  autonomy debt" — an accumulating risk score — which is a **different concept sharing the same
  word**, and §40 itself marks it experimental.
- **Needs:** Confirmation that §6's field uses the §29 scale, and a distinct name for the §40
  concept so the two never collide in code.

### D-015 — How verification confidence is computed

- **Status:** Open · **Source:** handoff §18, §19, §31, §47 · **Highest risk item**
- **Finding:** §31 compares `confidence = 0.88` against `required = 0.90` to drive a replan. But §18
  explicitly forbids treating a model-asserted number as ground truth ("do not implement a fake
  `LLM says: Plan B = 93.6% quality`"), and §19 requires measurable proxies plus represented
  uncertainty. The procedure that turns evidence coverage, consistency, schema correctness, policy
  compliance and retrieval confidence into the scalar in §31 is **not specified**.
- **Why it matters:** Implementing §31 naively produces exactly the anti-pattern §18 forbids, and
  it would sit at the centre of the system's reliability story. This is the single most dangerous
  gap found.
- **Needs:** A defined, measurable confidence function — or an explicit decision that verification
  is a pass/fail rule set rather than a scalar comparison.

### D-016 — The quality function behind `quality_threshold`

- **Status:** Open · **Source:** handoff §6, §19, §30
- **Finding:** `quality_threshold: 0.90` is a contract field and "minimum quality 90%" is a
  reliability-contract clause, but no measurement procedure for "quality" is defined anywhere.
  §19 offers candidate proxies (historical success rate, verification pass rate, evidence coverage,
  schema validity, retrieval confidence, contradiction rate, failure rate) without selecting or
  combining them.
- **Needs:** Definition, or a decision to express the threshold in proxy terms instead. Related to
  D-015.

### D-017 — Persistence beyond V0.1

- **Status:** Open · **Source:** handoff §51, §54, §76
- **Finding:** SQLite is named for local use and PostgreSQL "later", but no schema, no migration
  approach and no boundary between MissionState-in-memory and MissionState-persisted is specified.
  D-005 settles V0.1 only.
- **Needs:** When persistence enters, what it stores (events? state snapshots? both — and which is
  authoritative for replay per §73), and the storage interface.

### D-018 — Where the model-provider abstraction boundary lives

- **Status:** Open · **Source:** handoff §36 vs §51
- **Finding:** §36 forbids model dependence anywhere in EIDOS; §51 names Ollama plus a local open
  model as the concrete LLM. The handoff shows a "Model/Agent Interface" in a diagram but does not
  say which module owns it, what its interface is, or which layers may import it.
- **Needs:** The owning module and its interface. Invariant 9 forbids vendor names in contracts,
  planning, validation, compiler, runtime and state — so the boundary must be defined before any
  code calls a model.

### D-020 — "Strategy" and "Plan" are used interchangeably

- **Status:** Open · **Source:** handoff §13, §16, §17, §38, §53
- **Finding:** §16 generates "candidate strategies" labelled Plan A/B/C; §13 defines a Plan DSL;
  §53's API response carries `strategy_id`; §17 lists strategy factors (model selection, retrieval
  strategy, context allocation) that are *not* expressible in the §13 plan primitives.
- **Needs:** Are a Strategy and a Plan the same object, or is a Strategy a Plan plus binding
  decisions (agent, model, retrieval, context) that the DSL does not encode? This determines whether
  one contract or two is needed, and what a `strategy_signature` (D-021) actually signs.

### D-021 — Strategy signature / "Strategy Genome" encoding

- **Status:** Open · **Source:** handoff §21, §39
- **Finding:** §21 requires storing a `strategy_signature` in strategy memory and §39 sketches a
  Strategy Genome as a structured signature, but §39 explicitly frames it as a future research
  concept with no defined encoding, and no comparison or similarity semantics are given.
- **Needs:** Deferred by nature; recorded so it is not invented in passing. Depends on D-020.

### D-022 — Frontend stack

- **Status:** Open · **Source:** handoff §51 vs §76
- **Finding:** §51 offers "React/TypeScript or Streamlit for early prototype"; §76 lists React,
  TypeScript and Tailwind CSS. Unresolved, though not blocking until V1.3.
- **Needs:** A choice before V1.3.

### D-023 — A2A implementation: SDK, version, transport

- **Status:** Open · **Source:** handoff §8, §51, §76
- **Finding:** A2A (Agent2Agent) is named as the agent protocol and §8 specifies the conceptual
  mapping (`agent_id`, `a2a_task_id`, `a2a_context_id`, `status`, `latest_artifact`, `last_event`),
  but no SDK, protocol version or transport is named.
- **Needs:** A choice before V0.6. Related to D-011, since the wire format determines what ordering
  guarantees are actually available.

### D-024 — Placement of the FAISS vs Qdrant experiment

- **Status:** Open · **Source:** handoff §26
- **Finding:** §26 proposes a FAISS-vs-Qdrant comparison *and* says not to introduce both into the
  core runtime without a clear research reason, with Qdrant as the default. The natural reading is
  that the experiment lives outside the core runtime, but that is a reading, not a statement.
- **Needs:** Confirmation that the comparison is an out-of-runtime experiment rather than a runtime
  abstraction with two backends.

### D-025 — Branch and commit conventions

- **Status:** Open · **Source:** handoff §56, §61, §79 (git checkpoints required; conventions not
  specified)
- **Finding:** §61 makes "a Git checkpoint exists" part of the definition of done and §79 requires
  committing before a context change, but no branch strategy, commit-message convention or
  merge policy is specified.
- **Needs:** Owner preference. Until then, the bootstrap uses the default branch with a plain
  descriptive commit message, and nothing is pushed without explicit instruction.

### D-029 — The Agentic RAG reformulation loop has no stated bound

- **Status:** Open · **Source:** handoff §24 vs §14, §32 · **Found while writing `docs/09`**
- **Finding:** §24's Agentic RAG flow contains a loop: evaluate evidence -> "Enough?" -> if NO,
  reformulate -> retrieve again -> evaluate. `rag_rounds` is measured per mission (§33), but **no
  `max_rag_rounds` appears in either bound list** (§14 plan limits, §32 execution limits). Every
  other loop in the handoff — retries, replans, execution time, agent calls, tool calls — is
  explicitly bounded. This one is not.
- **Why it matters:** Invariant 7 states execution is bounded and never loops. Taken literally, §24
  describes a loop whose only termination condition is an evidence judgement that is itself
  unspecified (D-015). Implementing §24 as written could produce unbounded retrieval.
- **Needs:** Either a `max_rag_rounds` bound added to the budget set, or an explicit statement that
  the loop terminates only on the evidence judge plus the overall `max_execution_time`. Blocks V0.8,
  and should be settled when D-009 is settled.

### D-030 — `risk_level` (§6) vs "Maximum risk" (§30)

- **Status:** Open · **Source:** handoff §6 vs §30 · **Split out of D-013, left Open by the owner**
- **Finding:** §6 places `risk_level` in the Task Genome; §30 places "Maximum risk: Medium" in the
  Reliability Contract. These may be two different quantities — the **assessed** risk of the task
  versus the **tolerated** risk the user accepts — in which case they are a comparison pair
  (`assessed <= tolerated`) and both survive under D-013's disjoint decomposition, one in each
  model. Or they may be the same quantity named twice, in which case one of them disappears.
- **Why it was not folded into D-013:** D-013 settles the structural rule that no threshold has two
  homes. It does not settle whether these two named values *are* the same threshold. Answering that
  by implication would be a silent resolution, which CLAUDE.md §7 forbids.
- **Effect while Open:** one field of TaskGenome and one field of ReliabilityContract remain
  undetermined. Partially blocks V0.1 — the models can otherwise be specified.
- **Needs:** Owner to state whether assessed risk and tolerated risk are distinct quantities.

### D-031 — `evidence_requirements` (§6) vs "Minimum independent evidence" (§30)

- **Status:** Open · **Source:** handoff §6 vs §30 · **Split out of D-013, left Open by the owner**
- **Finding:** §30's "Minimum independent evidence: 3" is plainly a numeric acceptance threshold and
  belongs in the ReliabilityContract under D-013. §6's `evidence_requirements` is ambiguous: it
  could be the same numeric threshold — in which case it is a duplicate and moves to the contract —
  or a descriptive intrinsic requirement of the task, for example "must cite the architecture
  documentation", in which case it is task identity and stays in the genome. The handoff does not
  disambiguate, and §5's user-facing mission lists "Evidence requirements" without further detail.
- **Why it was not folded into D-013:** same reasoning as D-030.
- **Effect while Open:** whether `evidence_requirements` appears in TaskGenome at all is
  undetermined. Partially blocks V0.1 — one field only.
- **Needs:** Owner to state whether §6's `evidence_requirements` is a threshold or a description.
  If it is both, that is a third answer and the field splits across the two models.

### D-032 — The literal default value of `tenant_id`

- **Status:** Open · **Source:** handoff §54 (silent) · **Split out of D-019, left Open by the owner**
- **Finding:** D-019 establishes that `tenant_id` is required and carries a single fixed default.
  §54 provides no value, and the choice is not neutral: a value that reads as a sentinel behaves
  differently under a future migration than one that reads as a real tenant, and a value that looks
  like an identifier invites being parsed as one.
- **Effect while Open:** does not block the model definitions — only the constant.
- **Needs:** Owner to choose the value, and to state whether it is a reserved sentinel that real
  tenants may never take.

### D-034 — Do `plan_id` and `event_id` belong in invariant 18's identifier list?

- **Status:** Open · **Source:** CLAUDE.md invariant 18 vs handoff §54 · **Raised by Claude Code; split out of D-019, left Open by the owner**
- **Finding:** §54 names five identifiers: `tenant_id`, `mission_id`, `execution_id`, `agent_id`,
  `timestamp`. Invariant 18 as drafted at bootstrap asserts **seven**, adding `plan_id` and
  `event_id`. Both additions are handoff-sourced — `plan_id` from §33's telemetry list, `event_id`
  from §10's event requirements — but **neither comes from §54**, and §54's "such as" makes its list
  open rather than exhaustive, which is what made the addition seem unremarkable at the time.
- **Why it is recorded:** the two identifiers entered an invariant by derivation rather than by
  decision. Invariants are the one thing in this repository that must not accrete silently.
- **Effect while Open:** none on V0.1 field definitions. CLAUDE.md is **not** being amended pending
  this decision.
- **Needs:** Owner to either ratify the seven-identifier list or reduce invariant 18 to §54's five
  and let `plan_id`/`event_id` be required by their own sections instead.

### D-035 — Do A2A events carry a producer-assigned per-`a2a_task_id` sequence?

- **Status:** Open · **Source:** handoff §10 · **Split out of D-011, left Open by the owner**
- **Finding:** D-011 adopts the layered model in principle but scopes V0.1 to identity plus an
  EIDOS-assigned mission sequence. Whether remote events additionally carry a producer-assigned
  per-task sequence — layer 3 of the model — is deferred. A producer-assigned value is only
  trustworthy for detecting ordering within that producer's own stream, which is the sole use it
  would have.
- **Effect while Open:** none on V0.1. Blocks V0.6 lateness detection for remote tasks.
- **Needs:** Owner decision at V0.6, informed by **D-023** (the A2A wire format determines what
  ordering guarantees are actually available to carry).

### D-036 — The `AgentTask` lifecycle state machine

- **Status:** Open · **Source:** handoff §10 vs §8 · **Split out of D-011, left Open by the owner**
- **Finding:** §10 mandates that late and out-of-order events be "validated against lifecycle" and
  accepted or rejected **deterministically**. §8 gives `AgentTask` a `status` field but **never
  enumerates the states or the legal transitions**. Without that state machine, "validate against
  lifecycle" has no defined content and "deterministically" cannot be satisfied.
- **Effect while Open:** none on V0.1, which has no remote tasks. **Blocks V0.6 protocol tests for
  late event, out-of-order event, agent restart and partial artifact** (§50, §63) — those tests
  cannot be written against an unspecified lifecycle without encoding the decision silently.
- **Needs:** The state set and the legal transition table, including which states are terminal and
  what an event arriving for a terminal task does.

### D-037 — One common event shape, or separate internal and external shapes?

- **Status:** Open · **Source:** handoff §10 vs §33 · **Split out of D-011, left Open by the owner**
- **Finding:** §10 specifies the field set for "every **external** event", including `a2a_task_id`.
  But eleven of §33's thirteen event types are **internal** — `MISSION_CREATED`, `PLAN_GENERATED`,
  `PLAN_REJECTED`, `PLAN_COMPILED`, `MCP_TOOL_CALLED`, `RAG_SEARCH`, `EVIDENCE_REJECTED`,
  `VERIFICATION_FAILED`, `REPLAN_TRIGGERED`, `MISSION_COMPLETED`, `MISSION_FAILED` — and
  `a2a_task_id` is meaningless on them. Either internal and external events have different shapes,
  or they share one shape on which `a2a_task_id` is optional.
- **Effect while Open:** V0.1 emits only internal events, so it can proceed. The question becomes
  material at V0.6.
- **Needs:** Owner decision. Note that a shared shape with optional fields is easier now and vaguer
  later; separate shapes are stricter but require a discriminated hierarchy from the start.

### D-038 — Bounding and persisting the processed-`event_id` set

- **Status:** Open · **Source:** implied by D-011; not addressed in the handoff · **Raised by Claude Code, left Open by the owner**
- **Finding:** D-011 makes `event_id` the idempotency key, which requires the reducer to know which
  event ids have already been applied. That set **grows without bound** over a mission's life.
  In-memory at V0.1 this is harmless. It becomes a real question at V0.5, when checkpointing means
  the set must survive a restart, and at **D-017**, when persistence means it must be stored and
  queried.
- **Effect while Open:** none on V0.1. Blocks nothing yet.
- **Needs:** A bounding strategy (window, watermark, or full retention) and a decision on whether the
  set is derived from the persisted event log or stored separately. Should be settled alongside
  D-017.

### D-042 — The exact list of ReliabilityContract budget fields

- **Status:** Open · **Source:** handoff §14, §30, §32 · **Split out of D-009, left Open by the owner**
- **Finding:** D-009 establishes that mission execution budgets live in the ReliabilityContract and
  gives six *examples* — `max_retries`, `max_replans`, `max_agent_calls`, `max_tool_calls`,
  `max_execution_time`, `max_tokens`. §14's own list is prefixed "such as", so it is open rather
  than exhaustive, and §30's contract example carries only two of the six.
- **Effect while Open:** partially blocks V0.1 — the `ReliabilityContract` model can be defined in
  structure but its budget field list is not final.
- **Needs:** The definitive field list, and which fields are required vs optional. Interacts with
  **D-045**: an optional field and an absent contract are different situations.

### D-043 — Declared plan limits vs actual execution counters

- **Status:** Open · **Source:** handoff §14 vs §32 · **Raised by Claude Code; split out of D-009, left Open by the owner**
- **Finding:** Five limit names appear in **both** §14 (validation-time, causing plan **rejection**)
  and §32 (execution-time, causing mission **pause**). A shared name conceals two different
  quantities: `max_agent_calls` at validation counts *declared steps in the plan*, while at
  execution it counts *actual invocations including retries*. A plan with 4 agent steps under
  `max_retries: 2` can consume up to 12 agent calls. Both checks are legitimate; they are not the
  same number.
- **Why it matters:** this is the item in the D-009 family most likely to produce a real defect.
  Two limits sharing a name while counting different things passes review and fails in production.
- **Effect while Open:** none on V0.1. Material at V0.2 (validation) and V0.3 (runtime counters).
- **Needs:** Either two distinctly named limits, or one limit with a stated counting rule that both
  enforcement points share.

### D-044 — Does `max_tokens` formally belong to the §14 and §32 bound lists?

- **Status:** Open · **Source:** handoff §30, §33, §63 vs §14, §32 · **Split out of D-009, left Open by the owner**
- **Finding:** `max_tokens` appears in §30's Reliability Contract, tokens are measured per mission in
  §33, and "token budget exceeded" is a required failure test in §63 — but the limit appears in
  **neither** §14's plan-limit list **nor** §32's execution hard-limit list. §14's "such as" makes
  both lists open, which is how the omission passes unnoticed.
- **Effect while Open:** none on V0.1. Material at V0.2 and V1.2.
- **Needs:** Confirmation that `max_tokens` is enforced at the same points as the other budgets, and
  whether a token bound is checkable at validation time at all (it may be inherently dynamic).

### D-045 — What applies when no ReliabilityContract is supplied

- **Status:** Open · **Source:** handoff §30 · **Deferred here from D-013; left Open by the owner**
- **Finding:** §30 says every mission **"can have"** a Reliability Contract — optional. D-009 places
  the mission execution budgets inside it. If a mission supplies no contract, it is unstated whether
  system ceilings apply as effective limits, whether a default contract is synthesised, or whether
  the mission is rejected for lack of acceptance criteria.
- **Why it matters:** invariant 13 requires EIDOS to report when it cannot satisfy the contract.
  With no contract, it is undefined what "satisfied" means — and a mission with no acceptance
  criteria arguably cannot fail, which would hollow out the reliability story.
- **Effect while Open:** partially blocks V0.1 — determines whether `TaskGenome`'s reference to a
  contract is required or optional.
- **Needs:** Owner decision. Note the three options are not equivalent: system-ceilings-as-defaults
  is permissive, a synthesised default contract is explicit, and rejection is strictest.

### D-049 — Is `AGENT` a ninth `PlanStepKind`?

- **Status:** Open · **Source:** handoff §13 (example vs enumerated list) · **Found while writing the V0.1 contract specification**
- **Finding:** §13 enumerates eight allowed primitives — `SEQUENTIAL`, `PARALLEL`, `ROUTE`, `VERIFY`,
  `RETRY`, `REPLAN`, `HUMAN_APPROVAL`, `TERMINATE`. §13's **own example** contains
  `{ "type": "agent", "capability": "research" }`, and **`agent` is not in that list**.

  All eight enumerated primitives are control-flow constructs. The step that actually performs work
  and carries a `capability` is the unlisted one. Invariant 11 requires plans to request
  capabilities, so some step kind must hold a capability — and the handoff shows that kind only in
  an example.
- **Why it matters:** it determines the `PlanStepKind` value set and which kind carries `capability`.
  **D-047 approved "the eight PlanStep kinds"** on the understanding that §13's list was complete.
  If `AGENT` is a ninth kind, D-047's scope statement needs revisiting — it is not wrong, but it is
  incomplete.
- **Effect while Open:** blocks the `PlanStep` contract. **No placeholder kind is to be invented to
  make code compile.**
- **Needs:** Owner to decide whether `AGENT` is a ninth kind, whether capability-bearing steps are
  expressed some other way, or whether §13's list was simply not exhaustive.

### D-050 — Are `SEQUENTIAL` and `PARALLEL` redundant under an ID-addressed DAG?

- **Status:** Open · **Source:** handoff §13 vs **D-004** · **Found while writing the V0.1 contract specification**
- **Finding:** §13's example is the **nested tree** form. D-004 replaced that with an ID-addressed
  DAG as the canonical representation. In a DAG, "these two steps run in parallel" is expressed by
  **the absence of a dependency edge** between them, and "A then B" by the presence of one. Ordering
  *is* the edge structure.

  `SEQUENTIAL` and `PARALLEL` as explicit **step kinds** therefore encode information the graph
  already carries — and can contradict it. A `PARALLEL` step whose children have edges between them
  is self-inconsistent, and nothing in the current model says which wins.
- **Why it matters:** this is a consequence of D-004 that was **not visible when D-004 was taken**.
  It touches two Accepted decisions, D-004 and D-047. Neither is being modified.
- **Effect while Open:** blocks the `PlanStepKind` value set alongside D-049.
- **Needs:** Owner to choose among: drop both as step kinds and let edges carry ordering; keep them
  as grouping or annotation with an explicit rule that edges are authoritative on conflict; or keep
  D-047's eight as approved and accept the redundancy with a documented precedence rule.

### D-051 — The `RiskLevel` value set

- **Status:** Open · **Source:** handoff §5, §6, §30 vs §40 · **Found while writing the V0.1 contract specification**
- **Finding:** §5, §6 and §30 all use the single value "medium" without giving a scale. §40 gives a
  five-point scale for **action** risk: very low, low, medium, high, extreme. Whether task risk
  (§6's `risk_level`), tolerated risk (§30's "Maximum risk") and action risk (§40) share one value
  set is never stated.
- **Relationship to D-030:** D-030 asks whether assessed and tolerated risk are **distinct
  quantities**. D-051 asks what **values** either may take. They are independent: the answers could
  be "two quantities, one shared scale", "two quantities, two scales", or "one quantity".
- **Effect while Open:** blocks the risk-typed fields on both `TaskGenome` and `ReliabilityContract`.
  **No placeholder enum is to be invented to make code compile.**
- **Needs:** The value set or sets, and whether §40's action-risk scale is the same vocabulary.

### D-052 — `MissionStatus` values not named by the handoff

- **Status:** Open · **Source:** handoff §32, §33 · **Raised by Claude Code; left Open by the owner**
- **Finding:** Four mission states are handoff-named: `MISSION_CREATED`, `MISSION_COMPLETED`,
  `MISSION_FAILED` (§33's event types) and the paused state from §32's
  `MISSION PAUSED — human review required`. A working status enum would plausibly also need states
  covering planning and execution, but **no such states are named anywhere in the handoff** — they
  were a derivation in the draft contract specification, not a handoff fact.
- **Effect while Open:** the `MissionState.status` value set is undetermined beyond the four named
  states. **No inferred states are to be added to make code compile.**
- **Needs:** Owner to either confirm the additional states or restrict the enum to what §32 and §33
  name.

### D-053 — Identifier representation

- **Status:** Open · **Source:** not addressed in the handoff · **Raised by Claude Code; minor**
- **Finding:** The handoff names many identifiers (§10, §33, §54) but never specifies their
  representation — UUID, opaque string, or a structured/prefixed form. The draft specification
  proposed opaque strings generated as UUIDs; that proposal has not been ruled on.
- **Effect while Open:** minor. Affects every contract's identity fields, but is cheap to change
  while nothing is persisted (D-005).
- **Needs:** Confirmation, so the choice is recorded rather than made by whoever writes the first
  model.

### D-054 — Where timestamps come from

- **Status:** Open · **Source:** implied by CLAUDE.md §8; not addressed in the handoff · **Raised by Claude Code; minor**
- **Finding:** The draft specification proposed that timestamps are **explicit required inputs, never
  defaulted from the clock**, so that contract construction stays deterministic and tests do not
  depend on wall-clock time. CLAUDE.md §8 requires deterministic components to avoid wall-clock
  dependence in logic, but contracts are not named in that list, so the rule does not decide this by
  itself.
- **Relationship to D-011:** D-011 already requires `MissionEvent` to carry both `occurred_at`
  (producer clock) and `recorded_at` (EIDOS ingestion), and the reducer must not read the clock. This
  item asks whether the same discipline applies to every other model's timestamps.
- **Effect while Open:** minor, but it determines whether V0.1 unit tests are deterministic.
- **Needs:** Confirmation.

### D-046 — Numerical bound values

- **Status:** Open · **Source:** handoff §6, §30 (examples only) · **Deferred to V0.2 by D-009 rider 5**
- **Finding:** No bound has a stated default anywhere in the handoff. Exactly two numbers exist in
  this area and both appear as illustrative examples: `latency_budget_ms: 600000` (§6) and
  `Maximum tokens: 10,000` (§30). Every other value would be invention.
- **Effect while Open:** none on V0.1 by decision — D-009 rider 5 states that no numerical defaults
  are established in V0.1.
- **Needs:** Provisional values at V0.2 when validation exists, **explicitly marked arbitrary until
  measured**, then tuned from telemetry at V0.9+. Per §67 and CLAUDE.md §7 a provisional bound must
  never be presented as a tuned one.

---

## Deferred — specified, deliberately not implemented

### D-026 — A2A boundary deferred to V0.6

- **Status:** Deferred · **Source:** handoff §8, §10, §50
- The A2A boundary contract is documented in `docs/07_a2a_contract.md` from what the handoff
  specifies. §50 places it at V0.6, after MissionState and the event reducer are reliable (§50
  V0.5: "Before adding A2A, state handling must already be reliable"). No A2A code, dependency or
  package exists.

### D-027 — MCP tool boundary deferred to V0.7

- **Status:** Deferred · **Source:** handoff §27, §28, §50
- Documented in `docs/08_mcp_contract.md`. §27 caps the initial tool set at 2–3 (`search_documents`,
  `retrieve_evidence`) and warns against 20 tools in V1. No MCP code, dependency or package exists.

### D-028 — Agentic RAG and Qdrant deferred to V0.8

- **Status:** Deferred · **Source:** handoff §24, §25, §26, §50
- Documented in `docs/09_rag_architecture.md`. §25 notes the collection schema "should be designed
  later". No Qdrant, embedding model, reranker, dependency or package exists.
