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

### D-049 — EIDOS has a capability-bearing work-step category distinct from control-flow steps

- **Status:** Accepted · **Date:** 2026-09-16 · **Decided by:** human owner
- **Source:** handoff §13 (example vs enumerated list), §14, §50; invariant 11
- **Refines:** D-047. **D-047 is not modified** — this decision completes the kind taxonomy that
  D-047's scope statement assumed was already complete.
- **Context:** §13 enumerates eight primitives, every one of which is a control-flow construct.
  §13's **own example** contains a step of `"type": "agent"` carrying a `"capability"`, and `agent`
  is **not** in that list. §13's wording — "the LLM **composes** these approved primitives" — implies
  something is composed, and the handoff never names it. §50's V0.3 maps six primitives into runtime
  nodes and then says "Use mock agents initially", so agents are invoked at V0.3 by something that
  is not in the mapping list either.

  Three interpretations were analysed: (A) `AGENT` is a ninth entry in one flat kind enum; (B) two
  categories, capability-bearing work steps and control-flow steps; (C) the eight are complete and
  `agent` in the example is shorthand or an error.

- **Decision: option B.** EIDOS has a **capability-bearing work-step category distinct from
  control-flow steps**. `capability` is **required** for work steps and **absent** from control-flow
  steps.

- **Rationale:** C was eliminated on the handoff's own terms rather than on preference: under C
  nothing carries a capability, which makes §14's capability-validation stage vacuous and invariant
  11 unenforceable — two independent handoff requirements would have nothing to operate on. A
  capability-bearing kind must therefore exist.

  B was preferred to A because `capability` is not optional metadata; it is the thing invariant 11
  and §14's validation stage act on. Under A, `capability` would be required for exactly one enum
  value and meaningless for the others — a constraint the type system cannot express and the
  validator would have to enforce by convention. B makes it structural. Moving from A to B later
  would be a contract change rather than a refinement, so the choice was made now.

- **Consequences:**
  - The `PlanStep` contract is unblocked on this axis.
  - Work and control steps are distinguishable by construction, so "a control step carrying a
    capability" and "a work step without one" are both unrepresentable rather than merely invalid.
  - Capability validation (§14 stage 4) has a well-defined target, and **D-007**'s vocabulary
    attaches to the work category only.
  - **D-055** records the unresolved question of whether `VERIFY` and `HUMAN_APPROVAL` are
    themselves work steps. Left Open by the owner; both remain control-flow kinds meanwhile, which
    is the conservative position.

### D-050 — `SEQUENTIAL` and `PARALLEL` are not canonical `PlanStepKind` values

- **Status:** Accepted · **Date:** 2026-09-16 · **Decided by:** human owner
- **Source:** handoff §13, §14, §50 vs **D-004**
- **Refines:** D-004 and D-047. **Neither is modified.** This decision records a consequence of
  D-004 that was not visible when D-004 was taken.
- **Context:** §13 lists both as primitives and its example is the nested tree form — a `parallel`
  node with a `steps` array. D-004 made the canonical representation an ID-addressed DAG in which
  ordering **is** the edge structure: `A → B` is sequential, and two nodes with no path between them
  are parallel. As step kinds, `SEQUENTIAL` and `PARALLEL` re-encode what the edges already state and
  can contradict them — a `PARALLEL` step whose children have edges between them is
  self-inconsistent, with nothing to say which representation wins.

  Four interpretations were analysed: (A) drop both as kinds; (B) keep as grouping with edges
  authoritative on conflict; (C) keep as inert annotation; (D) they belong to the deferred
  authoring-surface sugar layer, not the canonical form.

- **Decision: option D.**
  - `SEQUENTIAL` and `PARALLEL` are **not canonical `PlanStepKind` values**.
  - **Ordering and parallelism are expressed through dependency edges in the ID-addressed DAG.**
  - They **may** exist later as optional authoring-surface syntax, but such syntax **must normalize
    to the same canonical DAG** and **must not introduce separate execution semantics**.

- **Rationale:** D-004 already states that nested or tree-shaped surface syntax is optional sugar
  normalized into the DAG before validation. §13's example **is** that tree syntax, and
  `SEQUENTIAL`/`PARALLEL` are precisely its grouping constructs — a `parallel` node with a `steps`
  array is meaningless once steps have IDs and edges. D is therefore the only reading under which
  **D-004 and §13 are both true as written**, rather than one overriding the other.

  B was rejected as structurally the same pattern this repository has already rejected twice: two
  representations of one fact plus a precedence rule, which **D-013** refused for constraints and
  §9/§10 refuse for state. C was rejected because an inert field in a contract reliably acquires
  meaning later, at which point the conflict returns with no decision behind it.

  Nothing is lost. §17 treats parallelization as a strategy factor and §16's Plan A and Plan B differ
  in exactly that, but the edges fully distinguish them — Plan A is a chain, Plan B a fan-in.

- **Consequences:**
  - The canonical `PlanStepKind` set shrinks by two. Combined with D-049 it is: the work-step
    category, plus `ROUTE`, `VERIFY`, `RETRY`, `REPLAN`, `HUMAN_APPROVAL`, `TERMINATE` — the last two
    pending **D-055**.
  - §14's limits remain computable and are now unambiguous: `max_depth` is the **longest path** and
    `max_parallel_branches` is the **maximum antichain width** of the DAG. This sharpens **D-046**,
    which must set values against those definitions.
  - §50's V0.3 instruction to "map SEQUENTIAL, PARALLEL … into runtime nodes" is satisfied by mapping
    the graph's structure onto LangGraph's sequential and concurrent execution. LangGraph has no
    "parallel node" — it has edges and concurrent branches.
  - The deferred authoring surface inherits a binding constraint: **normalize to the same canonical
    DAG, introduce no separate execution semantics.** Any future sugar layer needs normalization
    tests proving exactly that.
  - One thing edges do **not** express: "must run concurrently" as opposed to "may". Independent
    nodes may be serialized by the runtime under `max_parallel_branches`. This was raised and the
    owner accepted "may" as sufficient.

### D-051 — Task risk is one shared vocabulary; action risk and tool risk are separate concepts; the value set is deferred

- **Status:** Accepted · **Date:** 2026-09-16 · **Decided by:** human owner
- **Source:** handoff §5, §6, §28, §29, §30, §40
- **Context:** Risk appears in four places and only one states values. §5 ("Risk tolerance"), §6
  (`risk_level`) and §30 ("Maximum risk") each use the single word *medium*. §40 gives the only
  enumeration — very low, low, medium, high, extreme — for **action** risk. §28 lists a per-tool
  "risk level" with no values. The four measure different things: risk of the task, risk the user
  tolerates, risk of an action, risk of a tool. Notably §29, the governance section that actually
  drives enforcement, uses **no risk scale at all** — it runs on autonomy levels 0–4 and direct
  action-to-outcome mapping.

- **Decision:**
  1. `TaskGenome.risk_level` and `ReliabilityContract.max_risk_level` represent **the same task-risk
     vocabulary**, so that assessed risk and tolerated risk can be compared **deterministically**.
  2. **Action risk (§40) and tool risk (§28) are separate concepts.** The task-risk type is neither
     reused for them nor assigned to them in V0.1.
  3. **§40's five-point values are not adopted** as the V0.1 task-risk enum. §40 is explicitly
     experimental, and its `Change config → medium/high` entry is not a single enum value.
  4. **No replacement value set is invented.**
  5. The concrete task-risk value set is recorded as **Open** and deferred until an explicit
     product/architecture decision — see **D-056**.

- **Rationale:** A single shared scale for §6 and §30 is forced by the comparison itself: a
  deterministic `assessed <= tolerated` check requires both sides to be ordinally comparable, and
  invariant 14 requires that determinism to live in code. Beyond those two fields nothing in the
  handoff requires a shared vocabulary, and the four concepts plainly measure different things — so
  unifying all four would assert a relationship the handoff never states.

  Declining §40's values avoids repeating a mistake already made once in this project: **D-014** had
  to separate §40's "autonomy budget" from §29's autonomy levels because they collided on a word.
  Importing §40's *other* vocabulary into two core contracts would risk the same class of coupling a
  second time, and would promote an artifact the handoff itself marks "experimental until its
  semantics are properly designed" into a permanent contract type.

- **Consequences:**
  - `TaskGenome` and `ReliabilityContract` remain blocked on **D-056** and should be written **last**
    among the seven V0.1 contracts.
  - §28's tool risk and §40's action risk stay untyped in V0.1. Neither is on the V0.1 path, and §29
    governance does not need a risk scale to function — a point that removes any urgency to settle
    D-056 hastily.
  - `ReliabilityContract.require_approval_above_risk` (§30) is the one field that genuinely needs an
    ordinal threshold comparison, and it draws on the same task-risk vocabulary.
  - **D-046** is unaffected: risk is not a numeric bound.
  - This decision answered **D-030** by implication — "so that assessed and tolerated risk can be
    compared" presupposes two distinct quantities. Rather than let it close silently, D-030 was
    raised and **ratified explicitly by the owner on the same date**. See D-030 under Accepted.

### D-030 — Assessed task risk and tolerated risk are distinct quantities

- **Status:** Accepted · **Date:** 2026-09-16 · **Decided by:** human owner
- **Source:** handoff §6 vs §30; ratified explicitly rather than inherited from D-051
- **Context:** §6 places `risk_level` in the Task Genome; §30 places "Maximum risk" in the
  Reliability Contract. Either they are two different quantities — assessed versus tolerated — or
  the same quantity named twice, in which case one disappears under D-013's disjoint decomposition.

- **Decision:** they are **distinct quantities**.
  - `TaskGenome.risk_level` — the **assessed / intrinsic** risk associated with the mission or task.
  - `ReliabilityContract.max_risk_level` — the **maximum risk the mission is permitted to tolerate**.

  They **may be compared during later validation**. **This decision does not define how either value
  is calculated.**

- **Why it was ratified separately:** D-051 stated that the two fields share one vocabulary "so that
  assessed risk and tolerated risk can be compared deterministically", which presupposes two
  distinct quantities and therefore answered this item by implication. Closing D-030 on that basis
  would have been a silent resolution of the kind CLAUDE.md §7 forbids, so it was raised and
  ratified explicitly instead. The record now shows a decision, not an inference.

- **Consequences:**
  - Both fields survive, one in each model, consistent with **D-013**'s disjoint decomposition — this
    is the case where a shared *name* is a comparison pair rather than a duplicate.
  - **D-051** supplies the shared vocabulary that makes the comparison well-formed; **D-056** still
    owes the value set, so both fields remain untypeable for now.
  - The stated non-scope — how either value is calculated — is recorded as **D-057**. `max_risk_level`
    has an obvious source in §5's user-stated "Risk tolerance"; the provenance of the assessed value
    does not, and that gap is the substance of D-057.
  - Where the comparison is enforced is a validation question (§14 stage 5), not settled here.

### D-052 — `MissionStatus` contains exactly the four handoff-supported states

- **Status:** Accepted · **Date:** 2026-09-16 · **Decided by:** human owner
- **Source:** handoff §32, §33, §43, §53; constrained by D-010a
- **Context:** **The handoff never enumerates mission statuses anywhere.** Four states are
  supported, from three different kinds of evidence: `created`, `completed` and `failed` are
  inferred from §33's event names `MISSION_CREATED` / `MISSION_COMPLETED` / `MISSION_FAILED`;
  `completed` is additionally the **only actual `status` value** in the handoff (§53's conceptual API
  response) and appears as display text in §43; `paused` comes from §32's rendered
  `MISSION PAUSED / Maximum recovery budget exceeded / Human review required`.

  A draft V0.1 contract specification proposed six states, adding `PLANNING` and `EXECUTING` and
  renaming the paused state to `PAUSED_FOR_REVIEW`. **Two of those were invented and one was
  renamed** — none is a handoff fact. D-052 was logged to surface exactly that drift.

- **Decision:** `MissionStatus` contains **exactly four** states:
  `created`, `completed`, `failed`, `paused`.

  `PLANNING` and `EXECUTING` are **not** added in V0.1. `status_reason` carries the explanation
  associated with `paused` or other status outcomes. **No additional in-progress states are
  invented.**

- **Rationale:** Every handoff-named state is an **entry, exit or suspension boundary**; the omitted
  ones are precisely the *in-progress* states. That pattern is coherent rather than accidental — the
  handoff describes missions from the outside, through telemetry events, API responses and UI
  displays, where boundaries are what matter. In-progress substates are runtime progress
  information, and **D-010a** already excludes detailed runtime execution state from authoritative
  MissionState, with **D-040** deferring the exact split to V0.3.

  Three supporting reasons: nothing in V0.1 can *reach* an in-progress state, since there is no
  planner, validator or runtime — such a state would be unreachable in the contract. Adding enum
  values later is additive while removing them is breaking, so minimal is the cheap direction. And
  the runtime's genuine need — distinguishing "can still accept events" from "terminal" from
  "suspended" — is satisfiable with four, since "created and not yet completed, failed or paused"
  *is* the active condition.

- **Consequences:**
  - `MissionState.status` is typeable; `MissionState` is unblocked on this axis.
  - **Accepted cost:** `created` names the state a mission occupies for most of its life, which reads
    oddly. This is a naming consequence, not a correctness one, and was accepted knowingly rather
    than overlooked.
  - When the reducer arrives at V0.5, "terminal" will need a definition for rejecting late events —
    the same shape of problem **D-036** poses for `AgentTask`. Four states are sufficient for that.
  - Two questions deliberately left Open: **D-058** (whether `paused` later needs a more specific
    name or a split) and **D-059** (whether "could not satisfy the reliability contract" is `failed`
    with a reason or a distinct terminal state).

### D-014 — `TaskGenome.autonomy_level` uses §29's 0–4 scale

- **Status:** Accepted · **Date:** 2026-09-16 · **Decided by:** human owner
- **Source:** handoff §6, §29, §40
- **Context:** §29 is the **only** section in the handoff that enumerates autonomy levels. §6 lists
  `autonomy_level` as a Task Genome field with the example value `1` but never states which scale it
  draws on. §40 introduces an "autonomy budget / autonomy debt" — an accumulating score — which is a
  different concept sharing the same word.

  Four options were analysed: (A) adopt §29's scale as-is; (B) adopt it with the open questions it
  raises recorded rather than absorbed; (C) treat §6's field as a different, unspecified scale;
  (D) defer the type entirely as was done for risk in D-056.

- **Decision: option B.** `TaskGenome.autonomy_level` uses the 0–4 scale defined in §29:

  ```text
  0  Recommend only
  1  Safe read-only actions
  2  Reversible actions
  3  Human approval required
  4  Authorized autonomous execution
  ```

  **No additional levels are invented.**

- **Rationale:** C was rejected because nothing supports it — §29 is the only autonomy enumeration in
  the document, and inventing a second scale would violate the standing rule. D was rejected because
  this case is **not parallel to D-056**, despite the surface similarity: for risk the handoff
  supplies no task-risk scale at all, whereas here it supplies a scale at the right level of
  abstraction, at the right site, with a consistent example value (`1` matching §6's read-only
  mission and §29's "Level 1 Safe read-only actions"). Declining it would discard evidence the
  handoff actually provides rather than avoid an invention.

  B was preferred over A so that the scale's known awkwardness is documented rather than silently
  absorbed into a core contract.

- **Consequences:**
  - `TaskGenome.autonomy_level` is typeable; the field is unblocked.
  - `autonomy_level` carries more enforcement weight than `risk_level` does, because **§29 is the
    governance spine** — D-051 established that §29 uses no risk scale at all and runs on autonomy
    levels plus direct action-to-outcome mapping.
  - Nothing enforces this in V0.1; the policy engine is V1.2 (§50). Only the field's type was at
    stake.
  - Three questions deliberately left Open: **D-060** (is level 3 ordinal or a gate), **D-061**
    (mission-wide level versus the `HUMAN_APPROVAL` step kind), **D-062** (a distinct name and
    semantics for §40's concept, so the collision that made D-014 necessary cannot recur in code).

### D-016 — `min_quality` is a plain scalar threshold, not an estimate

- **Status:** Accepted · **Date:** 2026-09-16 · **Decided by:** human owner
- **Source:** handoff §6, §18, §19, §30, §31, §47; invariant 17
- **Context:** The handoff uses "quality" for **two things that behave completely differently** and
  never distinguishes them. §30's `Minimum quality: 90%` and §6's `quality_threshold: 0.90` are
  **user-stated requirements** — inputs with no uncertainty. §19's subject is what the system
  **produces**, and it insists those carry uncertainty: "instead of `quality = 0.93`, potentially
  use `quality estimate = 0.90–0.95`". Applying §19's uncertainty requirement to a requirement is
  incoherent — a user does not require "somewhere between 0.90 and 0.95".

  Four options were analysed: (A) scalar threshold, with estimates a separate type; (B) the threshold
  itself structured and uncertain; (C) defer the type as in D-056; (D) define both the threshold and
  the estimate type now.

- **Decision: option A.** `ReliabilityContract.min_quality` is a **plain scalar threshold**
  representing a user-stated minimum requirement. It is **not an estimate** and therefore **does not
  carry uncertainty**. The handoff's example value `0.90` is the basis for the field.

  **The eventual quality-estimate type is not introduced in V0.1.** It belongs to the later
  components that actually produce estimates, and must satisfy §19's uncertainty requirements and
  invariant 17.

- **Rationale:** B was rejected as incoherent for a requirement. C was rejected because — unlike
  D-056 — the handoff supplies concrete values for this field twice (`0.90` in §6, `90%` in §30) plus
  a concrete comparison in §31; the evidence exists. D was rejected because **nothing in V0.1
  produces an estimate**: there is no verification, no planner, no telemetry, so the estimate type
  would be unreachable — the same reasoning that excluded `PLANNING` and `EXECUTING` in D-052.

  §47's required output format supports A directly: it compares a **produced** value against a
  **required** one, which are two types meeting at a comparison rather than one type used twice.

- **Consequences:**
  - `ReliabilityContract.min_quality` is typeable. The contract remains blocked on **D-056** for
    `max_risk_level` and on **D-042** for its budget list, so this does not unblock the model on its
    own.
  - Invariant 17's obligation is **not discharged, only deferred to its proper owner** — the
    producers of estimates. **D-063** records the type they will need.
  - **D-015 is untouched** and remains the question of how measurable proxies are combined into an
    evaluated quality figure. D-016 typed a threshold; it did not define a measurement.
  - **D-064** records a distinct question surfaced here: whether §31/§47's `confidence` and §30's
    `quality` are the same quantity. If they are two, the contract may need two thresholds, which
    would feed back into D-042.

### D-042 — The V0.1 ReliabilityContract budget group is six mission-level fields

- **Status:** Accepted · **Date:** 2026-09-16 · **Decided by:** human owner
- **Source:** reconciliation of handoff §5, §14, §30, §32, §53; governed by D-009
- **Context:** Three partial lists exist and none is closed. §30 shows the **only actual contract**
  in the handoff and carries two budget-like values — maximum latency and maximum tokens — alongside
  four non-budget clauses. §14 lists eight plan limits prefixed "such as". §32 lists five execution
  hard limits. §5 describes what the user states. §53's conceptual API carries three constraints and
  **no budgets at all**. D-009 already removed the shape limits (`max_nodes`, `max_depth`,
  `max_parallel_branches`) to the system level.

- **Decision:** the V0.1 budget group contains **six** mission-level fields:

  ```text
  max_retries        max_agent_calls      max_execution_time
  max_replans        max_tool_calls       max_tokens
  ```

  **This is a reconciliation of the handoff's partial lists, not a claim that the handoff explicitly
  enumerates a complete contract schema.**

  Per **D-009**: system-level safety ceilings exist conceptually; the mission contract may tighten
  them; a mission may not exceed them; over-requesting a ceiling must eventually be **rejected, not
  clamped**.

  **No numerical default values are introduced in V0.1** (D-009 rider 5, D-046).

- **Rationale:** Adopting only §30's two would strand `max_retries`, `max_replans`,
  `max_agent_calls` and `max_tool_calls` with no mission-level home, when §32 calls them hard limits
  and §63 requires a test for each being exceeded — and D-009 leaves the contract as the only
  candidate. Treating §30 as partial is justified because it **is** an example, not a schema.

  The honest weakness, recorded deliberately: **no section of the handoff enumerates this contract.**
  This decision is a defensible reading of three partial lists, not a quotation, and is marked as
  such so that later work does not mistake it for something the handoff stated.

- **Consequences:**
  - **D-010a's budget counters** in MissionState now have a definite set to correspond to. Deciding
    the list also fixes the counters.
  - Every contract budget needs a **system counterpart**, or D-009's `min(system, contract)` rule is
    undefined for it. That constraint now applies to exactly these six.
  - §30's non-budget clauses are governed elsewhere and are **not** part of this group:
    `min_quality` (**D-016**, settled), `max_risk_level` (**D-051**/**D-056**),
    `min_independent_evidence` (**D-031**), and §30's `High-risk actions: require human approval`,
    which is a **rule rather than a number** and may not belong in the contract's numeric surface at
    all.
  - Three questions deliberately left Open: **D-065** (required vs optional per field), **D-043**
    (whether declared-plan limits and actual-execution limits need distinct fields — if so, this
    six-field list grows), **D-044** (the formal treatment of `max_tokens` in the §14/§32 limit sets,
    where it is currently absent despite appearing in §30 and §63).

### D-045 — Every TaskGenome must reference a ReliabilityContract

- **Status:** Accepted · **Date:** 2026-09-16 · **Decided by:** human owner
- **Source:** handoff §5, §30, §31, §47, §49, §53; invariant 13
- **Context:** §30 opens with *"Every mission **can** have a Reliability Contract"* — the single
  piece of direct evidence, and one word carrying considerable weight. It reads either as marking
  the field optional, or as describing a capability of the system rather than granting permission to
  omit it. §30's remaining sentences are entirely about **enforcement**, and the section never says
  what happens without a contract.

  Four options were analysed: (A) required; (B) optional with system ceilings as fallback;
  (C) optional in the model but synthesised at mission creation; (D) defer.

- **Decision: option A.** **Every `TaskGenome` must reference a `ReliabilityContract`.** The
  `ReliabilityContract` is **required** in the V0.1 contract model.

- **Rationale (owner's):** EIDOS's reliability and evaluation semantics require explicit acceptance
  criteria. Without a ReliabilityContract the system has no defined referent for satisfaction,
  required quality, or mission-level budget constraints.

  Supporting analysis: invariant 13 requires EIDOS to report when it cannot satisfy the contract —
  with no contract, "satisfied" is undefined and a mission without acceptance criteria cannot fail
  to meet them. Under **D-016** `min_quality` is the threshold verification checks against, so §31's
  comparison would have nothing on its right-hand side. Under **D-009**/**D-042** the contract is the
  only mission-level home for the six budgets. And §49's MVP chain ends in **evaluation**, which
  against nothing is not evaluation. Option B is coherent but places a null check at the centre of
  the reliability story; option C is attractive but currently unbuildable, since synthesis needs
  numbers that **D-046** defers.

  This is the one decision in the V0.1 round that **departs from a literal reading of the handoff's
  wording**, and it is recorded as such.

- **This decision does NOT define:**
  - whether the contract is always supplied explicitly by the user — **D-066**
  - whether some contract fields are optional — **D-065**
  - whether EIDOS may synthesise a contract later — **D-066**
  - any default numerical values — **D-046**

- **Consequences:**
  - `TaskGenome`'s contract reference is non-optional, so every consumer of `min_quality`,
    `max_risk_level` and the six budgets has a referent without a null branch.
  - **D-059** (is contract-unsatisfied a distinct terminal state) stays meaningful for every mission,
    rather than only for those that happen to carry a contract.
  - **D-065** now carries the whole weight of optionality on its own, at field level.
  - Adopting synthesis later (**D-066**) would not contradict this decision.

### D-056 — `RiskLevel = low | medium | high`

- **Status:** Accepted · **Date:** 2026-09-16 · **Decided by:** human owner
- **Source:** §5, §6, §30, §53 supply the value `medium`; the scale's **shape** is derived from
  D-030, D-051, §53 and invariant 14; the flanking **labels are an explicit owner ratification**
- **Context:** **The handoff contains no task-risk scale.** Three sites use exactly one value —
  §5 `RISK / Medium`, §6 `"risk_level": "medium"`, §30 `Maximum risk: Medium` — and §53's API shows
  `"risk_tolerance": "medium"` as a lowercase string. The only enumeration anywhere is §40's, which
  **D-051 declined**. So this was an absence to be filled by decision, not an ambiguity to be
  resolved by reading.

- **Decision:** `RiskLevel = low | medium | high` — a **closed, ordinal, word-valued three-level
  scale**.
  - `TaskGenome.risk_level` uses this scale.
  - `ReliabilityContract.max_risk_level` uses this scale.
  - The labels `low` and `high` are **explicitly ratified additions** completing the
    handoff-supported `medium` value.
  - **This scale is not reused** for §40 action risk or §28 tool risk; those remain separate Open
    concepts.

- **Rationale — what was derived, and what was ratified.** Five properties follow from decisions
  already accepted, and the scale satisfies all of them:
  1. **Ordinal** — D-030 makes assessed and tolerated risk distinct quantities compared as
     `assessed <= tolerated`, and invariant 14 requires that comparison to be deterministic.
  2. **Contains `medium`** — the strongest derived constraint. §5, §6, §30 and §53 all use it; a
     scale without it makes the handoff's own examples unrepresentable.
  3. **Closed and small** — invariant 14 needs a fixed comparison, and §4/§5 put this in front of a
     non-technical user in the Mission Center.
  4. **Not §40's five points** — settled by D-051.
  5. **Word-valued, not numeric** — §53 carries it as a string and §5 presents a word. This is
     deliberately *asymmetric* with `AutonomyLevel`, which §29 states numerically.

  Three points is the minimal set satisfying 1–3: `medium` is given, and it needs exactly one
  neighbour on each side to be ordinal with a midpoint. A five-point alternative was rejected
  because any five-point risk scale **resembles §40's**, and D-051 declined §40's precisely to avoid
  the coupling D-014 had to untangle — adopting a differently-labelled five-point scale would invite
  the same collision by resemblance.

  **The labels `low` and `high` are not derived.** They are the conventional minimal completion, and
  they were ratified explicitly by the owner rather than inferred.

- **Consequences:**
  - `RiskLevel` is typeable. **`TaskGenome.risk_level` and `ReliabilityContract.max_risk_level` are
    unblocked**, and with them the last *type-level* V0.1 blocker is cleared.
  - **D-062** must not reuse this scale or its name for §40's autonomy/risk budget. Two risk
    vocabularies coexisting is fine; two sharing a name is the D-014 problem recurring.
  - **D-057** remains Open and untouched: how either value is *determined* is still unspecified.
  - Granularity is a reversible choice while nothing is persisted (D-005). If §40's budget or §28's
    tool risk later need a finer mapping, widening this scale is a contract change to be decided,
    not assumed.

### D-053 — Identifiers are UUID-backed opaque values with distinct per-kind types

- **Status:** Accepted · **Date:** 2026-09-16 · **Decided by:** human owner
- **Source:** not addressed by the handoff; constrained by D-011, §54, §10, §33, §53
- **Context:** The handoff names nine identifier kinds across §10, §33, §54 and §8, and specifies a
  representation for none of them. Its single concrete example is §53's `"mission_id":
  "mission_1842"` — a prefixed readable string — but §53 labels itself conceptual.

- **Decision:** identifiers use **opaque UUID-backed values**, represented through **distinct
  per-identifier types** where practical: `TenantId`, `MissionId`, `ExecutionId`, `PlanId`,
  `EventId`, `AgentId`, and the other identifier kinds the contracts define. The underlying
  representation is UUID-backed; the per-kind typing prevents accidental cross-use.

  **Readability is handled at the display and logging layer, not by changing the representation.**

- **Rationale:** UUID-backed because **`event_id` is the idempotency key** under D-011, and it must
  be collision-free across processes once V0.6 introduces a second process generating identifiers.
  §53's `mission_1842` implies a counter, and a counter is a coordination point EIDOS has no
  mechanism for; §53 being conceptual, it is read as illustrating a shape rather than mandating a
  sequence.

  Distinct types because nine identifier kinds flowing through seven contracts is precisely where
  a plan id gets passed where a mission id belongs — a failure the type system can prevent for the
  cost of one declaration each.

- **Consequences:**
  - Applies to every contract's identity fields.
  - **Accepted cost:** identifiers are unreadable in raw form, which touches the places EIDOS most
    needs legibility — replay traces (§73), the Execution Replay and Evidence Explorer views (§41),
    and telemetry (§33). Recovered at the **display layer** (for example rendering a short prefix),
    which is where the decision places it.
  - Cheap to revisit while nothing is persisted (**D-005**); expensive after **D-017**.

### D-054 — All contract timestamps are explicit required inputs

- **Status:** Accepted · **Date:** 2026-09-16 · **Decided by:** human owner
- **Source:** not addressed by the handoff; follows D-011 and invariant 15
- **Context:** **D-011** already requires `MissionEvent` to carry both `occurred_at` (producer clock)
  and `recorded_at` (EIDOS ingestion), and requires the reducer not to read the clock. Whether that
  discipline generalises to every other model's timestamps — `MissionState.created_at` /
  `updated_at`, `Plan`, and the rest — was unstated. CLAUDE.md §8 names validator, compiler, reducer
  and policy as needing freedom from wall-clock dependence, but **not** contracts, so §8 does not
  decide this by itself.

- **Decision:** **all contract timestamps are explicit required inputs.** **No contract model may
  silently obtain the current wall-clock time during construction.**

- **Rationale:** The deciding argument is **replay**, not test convenience. Invariant 15 requires a
  completed mission to be replayable from recorded events. If `MissionState` timestamps defaulted to
  the clock, a replayed state would differ from the original in fields nobody intended to change,
  and the replay would not be a faithful reconstruction — it would silently stamp reconstruction
  time onto historical state.

  There is also a back-door argument: the reducer produces new `MissionState` values, so a
  clock-defaulting `MissionState` would reintroduce into the reducer exactly the clock dependence
  CLAUDE.md §8 forbids it.

  This is **D-011's principle applied consistently**, not a new rule.

- **Consequences:**
  - Construction is deterministic, so V0.1 unit tests are reproducible without freezing time.
  - Replay reconstructs state with historical timestamps rather than replay-time ones.
  - **Accepted cost:** every caller must supply a time, which is verbose at call sites.
  - Whatever supplies the time becomes an explicit dependency rather than an ambient one — relevant
    when the reducer is built at V0.5 (**D-039**).

### D-031 — V0.1 carries `min_independent_evidence` only; `evidence_requirements` is not in the genome

- **Status:** Accepted · **Date:** 2026-09-16 · **Decided by:** human owner
- **Source:** handoff §5, §6, §17, §30; precedent from D-041
- **Context:** `evidence_requirements` is **named three times and exemplified zero times** — §5 lists
  "Evidence requirements" among the user's mission inputs, §6 lists it as a Task Genome field, §17
  lists it among the dimensions strategy quality is weighed against. **§6's own example omits it**,
  as does §5's example mission. Meanwhile §30's `Minimum independent evidence: 3` is the **only
  concrete evidence-requirement content anywhere in the handoff**, and it is numeric and
  contract-side.

  Three readings were analysed: (A) the two are duplicates, so under D-013 the genome field does not
  exist; (B) they are complementary, the genome holding a descriptive requirement and the contract a
  threshold; (C) the genome field should not exist in V0.1 at all.

- **Decision: option C**, scoped to V0.1:
  - `ReliabilityContract` **includes** `min_independent_evidence`.
  - `TaskGenome` **does not include** `evidence_requirements`.
  - **No replacement representation is defined** for `evidence_requirements`.

- **Rationale:** Nothing in V0.1 produces, consumes or checks evidence — verification is V0.4, RAG
  and the evidence judge are V0.8. **D-041 already set this precedent**, excluding evidence fields
  from `MissionState` for exactly this reason.

  A is the **more likely eventual answer** — the §5/§30 structural parallel ("Required confidence" ↔
  "Minimum quality", "Evidence requirements" ↔ "Minimum independent evidence") and the absence of any
  non-numeric example both point that way. C was preferred because it reaches the same V0.1 outcome
  **without making a positive claim about the field's nature from inference**. Adding the field later
  is additive, so waiting costs nothing.

  B was rejected on the standing rule: the handoff shows no descriptive evidence content anywhere, so
  typing the field would mean inventing a representation.

- **Consequences:**
  - `TaskGenome` is now blocked only on **D-068**; `ReliabilityContract` only on **D-065** and
    **D-069**.
  - The substantive question is **not resolved**, only retargeted — recorded as **D-070** and
    deferred to V0.4/V0.8.
  - §30's clause bundles a qualitative property ("independent") with a quantity ("3"). That seam is
    noted and left alone; it is part of what D-070 must eventually address.

### D-068 — `TaskGenome` is mission-owned and does not carry `mission_id`

- **Status:** Accepted · **Date:** 2026-09-16 · **Decided by:** human owner
- **Source:** handoff §2, §5, §21, §22, §41, §46, §54, §73, §83; constrained by D-010a, D-013, D-045
- **Context:** Two sub-questions were bundled and had to be separated. **(a)** Is the genome
  mission-owned or an independently reusable descriptor? **(b)** If mission-owned, does it carry
  `mission_id`?

  On (a), everything describing genome *creation* is per-mission: §5's "EIDOS converts **this** into
  a structured Task Genome", §41's replay timeline entry `00:02 task genome created`, §73's
  `Mission created -> Task Genome generated -> ...`, and the loop in §2, §46 and §83. The only reuse
  signal is strategy memory.

  **The decisive detail is that §21 stores `task_class` *and* `task_genome characteristics` as two
  separate entries.** If the genome itself were the similarity key, `task_class` would be redundant.
  And the second entry is not `task_genome` but `task_genome **characteristics**` — strategy memory
  stores **features derived from** the genome, not the genome object. §22 confirms it from the other
  side by keying learning on `task type`, a coarse classifier.

- **Decision:** `TaskGenome` is **mission-owned**, and **does not carry `mission_id`**. Ownership is
  expressed through **containment** by the mission / `MissionState`.

- **Rationale (owner's):** this avoids two sources for the same ownership relationship and removes an
  unnecessary consistency check from V0.1.

  Supporting analysis: under **D-010a**, `MissionState` already **contains** `task_genome`, so the
  ownership relationship exists structurally without a back-reference. Adding `mission_id` would put
  one value in two places, making "a genome for mission X inside a state for mission Y" a
  **representable inconsistency** — the shape of duplication **D-013** rejected for constraints and
  §9/§10 reject for state.

  The reusable-descriptor reading was rejected on the handoff's own terms: §54's identifier list
  contains no genome id, every creation reference is per-mission, §21's "characteristics" removes the
  motive, and **D-045** makes the genome reference a mission-specific `ReliabilityContract` — a
  reusable genome carrying a mission-specific contract would be incoherent.

- **Consequences:**
  - **This changes the approved consolidated V0.1 specification**, which listed `mission_id` on
    `TaskGenome` with a warning marker. That entry was a proposal, not a decision, and is now removed.
  - `TaskGenome` is **unblocked**. Its V0.1 fields are: `tenant_id`, `goal`, `required_capabilities`,
    `information_dependencies`, `risk_level`, `autonomy_level`, `allowed_actions`,
    `reliability_contract`.
  - `MissionState` is unblocked by consequence, since its only remaining dependency was `TaskGenome`.
  - **D-071** records the future question of detached or reusable genome representations.
  - Untouched: **which** characteristics strategy memory derives from a genome is a V1.0 question the
    handoff leaves open and which is deliberately not logged here, being outside V0.1.

### D-065 — All six budget fields are optional; omission falls back to the system ceiling

- **Status:** Accepted · **Date:** 2026-09-17 · **Decided by:** human owner
- **Source:** handoff §5, §14, §30, §32, §53; governed by D-009 and D-042
- **Context:** D-042 fixed the six-field budget group without settling whether each must be supplied.
  The six divide sharply by where the handoff mentions them. `max_execution_time` appears in §5's
  user input ("Maximum latency"), §30's contract example, §53's API and §14/§32. `max_tokens` appears
  in §5 ("Resource/token budget"), §30 and §32. The other four — `max_retries`, `max_replans`,
  `max_agent_calls`, `max_tool_calls` — appear at **exactly two places in the whole document**,
  §14's plan-limit list and §32's execution hard-limit list, and **nowhere user-facing**.

  The decisive observation is simpler than that asymmetry: **§30's own example contract omits four of
  the six budgets.** The handoff presents that contract as valid, so omission is legal, which
  eliminates "all six required" without needing any inference.

- **Decision:** all six budget fields — `max_retries`, `max_replans`, `max_agent_calls`,
  `max_tool_calls`, `max_execution_time`, `max_tokens` — are **optional**.
  - When a budget is **omitted**, the applicable **system ceiling** is used.
  - When a budget is **supplied**, the mission may **tighten** the system ceiling but **may not
    exceed it**, per **D-009**.
  - **No numerical defaults are introduced in V0.1.**

- **Rationale:** One uniform rule, consistent with §30's worked example, with §5 (the user states
  two of the six) and with §53 (the API carries none). Under D-009 the fallback is already defined
  structurally — `effective = min(system, contract)` with the contract operand absent leaves the
  system ceiling — so no new mechanism is introduced.

  A split making the two user-facing budgets required was considered and rejected: that asymmetry
  rests on *where the handoff happens to mention* each field, which is weaker evidence than a worked
  example, and it would mandate fields the handoff never mandates — a second departure from
  permissive wording after **D-045**.

  D-045's rationale is not weakened. The contract is required so that acceptance criteria always
  exist, and that weight is carried by `min_quality`, `max_risk_level` and
  `min_independent_evidence`, not by the budgets. A contract stating no budgets is still a
  meaningful contract.

- **Consequences:**
  - The six budget fields are declarable. `ReliabilityContract` now awaits only **D-069** and
    **D-073**.
  - The fallback is **structural, not numeric**: system ceilings have no values until V0.2
    (**D-046**), so V0.1 records the rule and V0.2 supplies the numbers.
  - **Accepted cost:** "omitted" and "explicitly at the ceiling" produce the same effective limit and
    become indistinguishable. Recorded as **D-072**, which notes this argues for retaining the
    requested value alongside the effective one rather than for making fields required.
  - Four questions deliberately left Open: **D-072**, **D-043** (declared vs actual limits),
    **D-044** (`max_tokens` in the validation/execution limit model), **D-073** (optionality of the
    non-budget contract fields, explicitly **not** resolved here).

### D-069 — The high-risk approval clause is not a ReliabilityContract field

- **Status:** Accepted · **Date:** 2026-09-17 · **Decided by:** human owner
- **Source:** handoff §5, §13, §28, §29, §30; invariant 14
- **Context:** §30's example contract ends with `High-risk actions: Require human approval`. **Every
  other clause in that example is a value** — a threshold or a budget; this one is a **rule** stated
  as prose, with no number, no threshold, and no defined subject ("high-risk" is undefined against
  **D-056**'s `low | medium | high`, which is *task* risk, not action risk). **D-042** flagged it as
  a rule rather than a number when fixing the budget group.

  The larger problem is multiplicity: **four mechanisms in the handoff touch approval** — §30's
  clause and §29's Level 3, both mission-wide; §13's `HUMAN_APPROVAL` step kind, per-step; and §28's
  tool policy, per-call. **D-061** already records the collision between the two middle ones. Two
  mission-wide mechanisms expressing one idea is the duplication **D-013** rejected for constraints
  and §9/§10 reject for state — and unlike D-030's assessed/tolerated risk pair, these are not a
  comparison pair.

- **Decision: option B.** `High-risk actions: Require human approval` is **not a
  `ReliabilityContract` field in V0.1.**

  Approval is treated as a **governance / policy concern**, handled through the existing autonomy and
  approval mechanisms — especially §29's `autonomy_level` — with per-step `HUMAN_APPROVAL` and
  per-tool policy remaining **separate mechanisms**.

  **No approval-threshold field is created in `ReliabilityContract`.**

- **Rationale:** §29 already carries mission-wide approval through `autonomy_level`, which **D-014**
  made a real typed field, so this removes a duplicate rather than dropping a capability. And the
  contract-field alternative cannot be built honestly: "high-risk actions" requires an **action-risk**
  notion that **D-051** deliberately left untyped and **D-057** leaves undetermined, so the field
  would have a type but nothing to compare against — a placeholder in all but name.

  **Cost, stated plainly:** this is a **second departure from §30's example**, after **D-045** read
  its "can have" as non-permissive. §30 shows the clause inside a contract and this decision says it
  does not belong there.

- **Consequences:**
  - `ReliabilityContract` carries no approval field. It now awaits only **D-073**.
  - Enforcement lives where invariant 14 requires it — in code, in the V1.2 policy engine — rather
    than as per-mission data.
  - Three questions left Open: **D-074** (is §30's wording exactly `autonomy_level >= 3`, given §30
    is scoped to *actions* and §29 to the *mission*), **D-061** (mission-wide autonomy vs the
    per-step `HUMAN_APPROVAL` kind), **D-057** (how action risk is determined at all).
  - If **D-074** concludes the two are *not* equivalent, this decision dropped a capability rather
    than a duplicate and would need revisiting. That is the risk this decision carries.

### D-067 — V0.1 `MissionEvent` is the envelope only; no payload field

- **Status:** Accepted · **Date:** 2026-09-17 · **Decided by:** human owner
- **Source:** handoff §10, §33, §73; CLAUDE.md §8; precedent from D-016, D-031, D-041, D-052
- **Context:** §33 names thirteen event types whose payloads plainly differ, and **describes none of
  them**. §10 gives an event's field set — `event_id`, `a2a_task_id`, `sequence/version`,
  `timestamp` — and **does not list a payload at all**. CLAUDE.md §8 forbids untyped dicts crossing a
  module boundary, so a generic container is not an available answer.

  Four options were analysed: (A) a discriminated union with a payload class per type, defined now;
  (B) a typed base extended per milestone; (C) a constrained generic container; (D) no payload field
  in V0.1.

- **Decision: option D.** For V0.1, `MissionEvent` contains only the settled envelope:

  ```text
  event_id   tenant_id   mission_id   sequence   occurred_at   recorded_at   type
  ```

  **No `payload` field is included in the V0.1 contract.**

  The eventual payload design is deferred to the milestones that actually produce events. **The
  intended future direction is a typed, discriminated payload representation keyed by event type**,
  not an untyped mapping.

- **Rationale:** The precedent chain decides it. Four times already in this round something was
  excluded because nothing in V0.1 could produce it — the quality-estimate type (**D-016**),
  `evidence_requirements` (**D-031**), evidence and result fields in MissionState (**D-041**), and
  the `PLANNING`/`EXECUTING` statuses (**D-052**). This is the strongest instance: not only can V0.1
  not produce a payload, **V0.1 emits no events at all**. Defining thirteen payload shapes for types
  spanning V0.3 through V0.8 would be thirteen inventions with no test able to exercise them.

  It is also the only option consistent with §10, which enumerates an event's fields without
  including a payload.

  Option A remains the right **target**; recording the direction without building it mirrors how
  D-016 recorded the estimate type's obligation without discharging it.

- **Consequences:**
  - `MissionEvent` is **unblocked** and fully typed for V0.1. Only **D-073** now blocks any contract.
  - **Accepted cost:** `MissionEvent` is a pure envelope in V0.1 and will look incomplete to a reader.
    The envelope is precisely what **D-011** settled and what the reducer will key on, so it is not
    empty of purpose — but the appearance was weighed and accepted rather than overlooked.
  - Three questions left Open: **D-037** (whether internal and external events share one shape),
    **D-075** (per-type payload definitions), **D-076** (what payloads must carry for faithful replay
    under invariant 15).
  - **D-076 carries the real risk.** Deferring payloads defers the point at which "an event that is
    not recorded is not replayable" becomes testable. That obligation comes from D-010a and
    invariant 15; D-067 postpones the reckoning rather than creating it.

### D-073 — The three non-budget ReliabilityContract fields are required

- **Status:** Accepted · **Date:** 2026-09-17 · **Decided by:** human owner
- **Source:** handoff §4, §5, §30, §53; governed by D-045, and decided against the same evidentiary
  standard as D-065
- **Context:** D-065 settled optionality for the six budget fields only. The contract's other clauses
  had never been asked about. §30's example carries all three — `Minimum quality: 90%`,
  `Maximum risk: Medium`, `Minimum independent evidence: 3` — and §5 has the user state all three.
  §53's API carries `minimum_confidence` and `risk_tolerance` but **not** an evidence count. (Whether
  §53's `minimum_confidence` *is* `min_quality` is **D-064**, still Open, so §53 is weak evidence for
  that field.)

- **Decision:** `min_quality`, `max_risk_level` and `min_independent_evidence` are **required** in
  V0.1. The six budget fields **remain optional** per **D-065**, using the system ceiling when
  omitted.

  **No optionality for any other field is inferred from this decision.**

- **Rationale:** This is the answer consistent with how **D-065** was decided, not in tension with it.
  D-065 turned on a worked example **demonstrating omission** — §30 omits four of the six budgets.
  Here §30's example **includes all three** non-budget clauses and no demonstration of omission
  exists anywhere, so the same standard yields the opposite result.

  It also keeps **D-045** coherent. D-045 made the contract required so acceptance criteria always
  exist; optional criteria inside a required contract would hollow that out one level down. These
  three are precisely the fields carrying that weight — D-065's rationale said explicitly that the
  budgets do not. Structurally, budgets fall back to system ceilings; **these three have no
  equivalent fallback**, because there is no system-wide "minimum quality" or tolerated risk.

  A split making `min_independent_evidence` optional was considered and rejected: it rests on where
  the handoff happens to mention things, which is the reasoning D-065 declined.

- **Consequences:**
  - `ReliabilityContract` is **fully specified and writable** — the first of the seven to reach that
    state.
  - **Accepted cost:** `min_independent_evidence` is mandatory from V0.1 while **nothing checks it
    until V0.8**. The precedent chain (D-031, D-041, D-067) would normally argue for exclusion, but
    **D-031 already decided the field is carried**, so only optionality remained. It is a value the
    user supplies per §5, not one the system must compute.
  - The broader gap this analysis exposed — optionality never decided for five other models — is
    recorded as **D-077**.

---

## Open — require the human owner

These are ambiguities, contradictions and gaps found in the handoff during the bootstrap read. None
has been resolved. Work that depends on one of them is blocked until the owner decides.

Count: 43. Highest-impact first is **D-015** (how verification confidence is computed), then
**D-007** (capability vocabulary) and **D-012** (predicate language) for V0.2.

**All architectural V0.1 decisions are settled.** What remains is **representation**, and it is not
cosmetic: **no contract is currently constructible without an invention.** The blockers are
**D-077** (field optionality, five models) and **D-078**–**D-083** (units, `tenant_id` required vs
defaulted, `capability`, `AgentTask.status`, `MissionState` collection shapes and `Plan.version`,
timestamp representation). None touches an invariant.

**Standing rule for all Open items:** no placeholder enum, type, sentinel or inferred value may be
invented to make code compile. An Open item blocks the field it touches; it does not license a
guess. Where a type cannot be written without an answer, the field waits.

**All five decisions blocking V0.1 were resolved on 2026-09-16** and moved to Accepted: **D-013**,
**D-019**, **D-011**, **D-010a**, **D-009**. Each exposed sub-questions that the owner deliberately
kept Open rather than resolving by implication — D-030 and D-031 from D-013; D-032 through D-034
from D-019; D-035 through D-038 from D-011; D-010b and D-039 through D-041 from D-010a; D-042
through D-046 from D-009. Three further V0.1 scoping decisions followed: **D-033**, **D-047**,
**D-048**.

Open items still touching V0.1: **D-014**, **D-016**, **D-031**, **D-042**, **D-045** — each
affecting one field, one flag or one type — plus **D-056** (the task-risk value set), which **does
block** the two fields it types. D-014 and D-016
predate the blocking-decision round and were not part of it. **D-053** and **D-054** are minor and
affect representation rather than structure. **D-055** does not block V0.1.

**D-049 and D-050 are resolved**, which unblocks `PlanStep` and fixes the canonical `PlanStepKind`
set. Both are recorded as **refinements** of D-004 and D-047; neither of those has been modified.

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

### D-060 — Is Level 3 an ordinal point, or a gate cutting across the scale?

- **Status:** Open · **Source:** handoff §29 · **Split out of D-014, left Open by the owner**
- **Finding:** §29's five levels are not obviously one ordered dimension. Levels 0, 1, 2 and 4
  describe **what the system may do** — recommend, read, reverse, execute — and are monotonic in
  permissiveness. **Level 3, "Human approval required", describes a *process*, not a capability
  class.** It sits between 2 and 4 in permissiveness only under the unstated reading "may do
  irreversible things, but only with approval". §29's own examples reinforce the tension:
  `Modify configuration → human approval` maps an **action** to a **gate**, not to a level.
- **Why it matters:** invariant 14 requires governance to be deterministic and enforced in code. If
  `autonomy_level` is genuinely ordinal, enforcement is a comparison; if level 3 is a gate that cuts
  across the others, enforcement is a branch and the type is not simply ordinal.
- **Effect while Open:** none on V0.1 — the value set is fixed by D-014 and nothing enforces it until
  V1.2. Material when the policy engine is built.
- **Needs:** Owner to state whether the scale is ordinal throughout, and if not, how level 3
  composes with the others.

### D-061 — Relationship between mission-wide `autonomy_level` and the `HUMAN_APPROVAL` step kind

- **Status:** Open · **Source:** handoff §13 vs §29 · **Split out of D-014, left Open by the owner**
- **Finding:** Approval is expressible twice. §29's **Level 3** is a mission-wide autonomy setting
  meaning human approval is required; §13's **`HUMAN_APPROVAL`** is a per-step `PlanStepKind`. The
  handoff never states how they relate — whether level 3 causes approval steps to be inserted during
  planning, whether an explicit approval step is independent of the mission's level, or whether one
  subsumes the other.
- **Why it matters:** two mechanisms expressing one concept is the pattern this project has rejected
  twice already — **D-013** for constraints and §9/§10 for state. If both remain, their precedence
  must be explicit rather than emergent.
- **Effect while Open:** none on V0.1 — neither is enforced. Material at V0.3 if `HUMAN_APPROVAL` is
  compiled (§50 omits it from the V0.3 mapping list), and at V1.2 for the policy engine.
- **Needs:** Owner decision. Interacts with **D-055**, which asks whether `HUMAN_APPROVAL` is a work
  step at all.

### D-062 — Naming and semantics of the §40 Autonomy Budget / Autonomy Debt concept

- **Status:** Open · **Source:** handoff §40 · **Split out of D-014, left Open by the owner**
- **Finding:** §40 describes an accumulating autonomy/risk score which, when it crosses a policy
  threshold, requires human approval. This is a **different concept from §29's autonomy levels** but
  shares the word "autonomy", which is what made D-014 necessary. §40 itself states the concept
  "should remain experimental until its semantics are properly designed".
- **Effect while Open:** none. Nothing implements it. The requirement is that it **must be given a
  name distinct from `autonomy_level`** before it is ever implemented, so the collision cannot
  recur in code.
- **Needs:** A distinct name and, separately, its semantics. `RiskBudget` was floated earlier in
  discussion but **was never adopted** and is recorded here only so the suggestion is not mistaken
  for a decision. Note this is also entangled with **D-051**: §40's action-risk scale was declined as
  the task-risk vocabulary, so whatever this concept accumulates needs its own defined scale too.

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

### D-063 — The concrete type or structure of a quality estimate

- **Status:** Open · **Source:** handoff §19; invariant 17 · **Split out of D-016, left Open by the owner**
- **Finding:** D-016 settles that `ReliabilityContract.min_quality` is a plain scalar **requirement**.
  It deliberately does not introduce the type used for values the system **produces**. §19 requires
  those to represent uncertainty — "instead of `quality = 0.93`, potentially use
  `quality estimate = 0.90–0.95`, or a confidence interval" — and invariant 17 requires estimates to
  be labelled as estimates with prediction error recorded separately from outcomes.
- **Why it is deferred rather than defined:** nothing in V0.1 produces an estimate. There is no
  verification, no planner, no telemetry. Introducing the type now would create an **unreachable
  type**, which is the same reasoning that excluded `PLANNING` and `EXECUTING` in D-052.
- **Effect while Open:** none on V0.1. **Needed before V0.4**, when verification produces the first
  estimate, and before V0.9/V1.0, when telemetry and the planner produce theirs.
- **Needs:** A concrete representation — interval, distribution, or value-plus-method — and a
  decision on where prediction error is recorded. Distinct from **D-015**, which asks how proxies
  are *combined*; D-063 asks what the *result* looks like.

### D-064 — Are §31/§47 `confidence` and §30 `quality` the same quantity?

- **Status:** Open · **Source:** handoff §30, §31, §47 · **Split out of D-016, left Open by the owner**
- **Finding:** §30's Reliability Contract clause is `Minimum quality: 90%`. §31's verification
  compares `confidence = 0.88` against `required = 0.90`. §47's required output format reads
  `Evidence confidence: 0.88 / Required: 0.90 / STATUS: Insufficient evidence`. The handoff uses
  **"quality" and "confidence" for what appears to be one comparison** and never reconciles them.
- **Why it matters:** if they are one quantity, `min_quality` is the threshold verification checks
  against and the naming should be unified. If they are two — say, a quality figure over the whole
  mission and an evidence-confidence figure over a particular conclusion — then the contract needs
  **two** thresholds, and §47's output is checking the second against a clause §30 states for the
  first.
- **Effect while Open:** none on V0.1 — there is no verification. Material at V0.4, and it shapes
  **D-042**'s contract field list if a second threshold turns out to be required.
- **Needs:** Owner to state whether they are one quantity. Adjacent to **D-015** but distinct: D-015
  asks how the figure is computed, D-064 asks how many figures there are.

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

### D-057 — How the two risk values are determined

- **Status:** Open · **Source:** not specified by the handoff · **Scope boundary stated explicitly by the owner in D-030**
- **Finding:** D-030 establishes that assessed task risk and tolerated risk are distinct quantities,
  and states explicitly that it **does not define how either value is calculated**. The handoff does
  not supply that either. §5 has the user state "Risk tolerance" as a mission input, which maps
  cleanly onto `ReliabilityContract.max_risk_level`. But §6's `risk_level` sits in the **derived**
  Task Genome, and nothing says who assigns it — the user, the planner, a deterministic rule over
  `allowed_actions`, or something else.
- **Why it matters:** if assessed risk is produced by a model, it is a model-asserted judgement
  driving a governance decision, which is the pattern §18 warns against and which **D-015** already
  flags for verification confidence. If it is a deterministic rule, it needs a defined input. The
  two answers have materially different consequences for invariant 14, which requires governance to
  be deterministic and enforced in code rather than by prompt.
- **Effect while Open:** none on V0.1 — the field exists under D-030 regardless of its provenance.
  Material when policy validation is built (§14 stage 5, V0.2) and for governance at V1.2.
- **Needs:** Owner to decide the origin of `TaskGenome.risk_level`. Related to **D-056** (its value
  set) and **D-015** (the general question of model-asserted values driving decisions).

### D-070 — Is `evidence_requirements` a duplicate, or a distinct descriptive requirement?

- **Status:** Open · **Source:** handoff §5, §6, §17, §30 · **Split out of D-031, deferred by the owner**
- **Finding:** D-031 removes `evidence_requirements` from the V0.1 `TaskGenome` without deciding what
  it is. The substantive question survives: is §6's field the same concern as §30's
  `Minimum independent evidence` — in which case D-013 already places it in the contract and the
  genome never needs it — or a genuinely distinct **descriptive** requirement, such as "must cite the
  architecture documentation", which would be task identity and belong in the genome?

  The evidence available is thin in a specific way: the field is **named three times (§5, §6, §17)
  and exemplified zero times**. The only concrete evidence-requirement content anywhere in the
  handoff is §30's numeric clause. A §5/§30 structural parallel — "Required confidence" ↔ "Minimum
  quality", "Evidence requirements" ↔ "Minimum independent evidence" — suggests the duplicate
  reading, but the handoff never states that mapping.
- **If it is distinct:** its **representation** is also unspecified. Nothing in the handoff shows
  descriptive evidence content, so defining a shape now would require invention. **No replacement
  representation may be defined** until this is answered.
- **Effect while Open:** none on V0.1 by decision (D-031).
- **Needs:** Deferred to the milestone where verification (V0.4) and the evidence judge (V0.8)
  exist, so the requirement can be defined against real behaviour rather than against a field list.

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

### D-072 — Should "omitted" and "explicitly at the ceiling" be distinguishable?

- **Status:** Open · **Source:** implied by D-065 · **Split out of D-065, left Open by the owner**
- **Finding:** Under D-065 an omitted budget falls back to the system ceiling. A contract that omits
  `max_tokens` and one that explicitly requests exactly the ceiling therefore produce the **same
  effective limit** and become indistinguishable once the fallback is applied.
- **Why it may matter:** §19 requires prediction error to be tracked separately from outcomes, and
  invariant 17 requires estimates to be labelled as such — both of which compare against what was
  *requested*. §41's Mission Center and Strategy View show the user what they asked for. If the
  requested value is not retained distinctly from the effective one, neither can tell "the user
  chose the maximum" from "the user said nothing".
- **Effect while Open:** none on V0.1 — the field is optional either way. Material at V0.9 telemetry
  and V1.3 frontend.
- **Needs:** Owner to decide whether the requested value must be retained alongside the effective
  one. Note this argues for **storing both**, not for making fields required.

### D-077 — Field optionality for the five contracts where it has never been decided

- **Status:** Open · **Source:** not addressed by the handoff · **Identified during the D-073 analysis; logged at the owner's instruction**
- **Finding:** Optionality has only ever been decided for three things: `AgentTask` (**D-048** —
  `agent_id` and `status` required, four A2A fields optional), the `ReliabilityContract` budgets
  (**D-065** — all six optional), the non-budget contract fields (**D-073** — all three required),
  and individually `TaskGenome.tenant_id` (**D-019**/**D-033**) and
  `TaskGenome.reliability_contract` (**D-045**).

  **Never asked** for:
  - `TaskGenome` — `goal`, `required_capabilities`, `information_dependencies`, `risk_level`,
    `autonomy_level`, `allowed_actions`
  - `Plan` — `plan_id`, `mission_id`, `version`, `parent_plan_id`, `replan_reason`, `steps`
  - `PlanStep` — `step_id`, `kind`, `capability`, `depends_on`
  - `MissionEvent` — every envelope field
  - `MissionState` — every field

- **Why it blocks:** every field must be either required or carry a default. Until this is settled
  these five models cannot be written without **inventing** an answer per field, which the standing
  rule forbids.
- **Note on two fields in particular:** `Plan.parent_plan_id` and `Plan.replan_reason` are absent by
  nature on a v1 plan and present on replans (§15), so they are the clearest candidates for optional
  — but that is an observation, not a decision, and it is not being taken here.
- **Effect while Open:** blocks `TaskGenome`, `Plan`, `PlanStep`, `MissionEvent` and `MissionState`.
- **Needs:** Per-field required/optional for those five models. **Do not infer any of it from
  D-048, D-065 or D-073**, whose scopes are explicitly limited to their own models.

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

### D-066 — Is the ReliabilityContract always user-supplied, or may EIDOS synthesise one?

- **Status:** Open · **Source:** handoff §5, §30, §53 · **Split out of D-045, left Open by the owner**
- **Finding:** D-045 makes the contract **required on `TaskGenome`**. It does not say where the
  contract comes from. §5 has the user state constraints directly, which reads as user-supplied.
  §53's conceptual API carries three constraints, fewer than the contract holds, which suggests
  something fills the remainder. A synthesised default contract was considered during D-045 and is
  **currently unbuildable**, because synthesis requires numbers and **D-046** defers all numerical
  values to V0.2.
- **Effect while Open:** none on the V0.1 contract model — the reference is required either way.
  Material when mission creation is built, and dependent on D-046.
- **Needs:** Owner to decide whether contracts are always explicit, or whether EIDOS may synthesise
  or complete one. Adopting synthesis later would not contradict D-045.

### D-055 — Are `VERIFY` and `HUMAN_APPROVAL` work steps rather than control-flow steps?

- **Status:** Open · **Source:** handoff §13 vs §6, §7, §16, §43 · **Split out of D-049, left Open by the owner**
- **Finding:** D-049 establishes two categories: capability-bearing **work** steps and
  **control-flow** steps. Two of §13's eight named primitives sit ambiguously across that line.

  - **`VERIFY`** — §7's registry lists a Verification Agent with `evidence_validation` and
    `contradiction_detection`; §16's candidate strategies and §43's flagship demo both draw
    Verification as an agent node; §6's `required_capabilities` example includes `verification`.
    VERIFY may therefore be a **work step with `capability: verification`**, not a control primitive.
  - **`HUMAN_APPROVAL`** — §7 lists **"Human reviewer"** among the providers a capability may be
    bound to. HUMAN_APPROVAL may therefore be a **work step whose provider is a human** rather than
    a model.

- **Why it matters:** it determines the size of the control-flow kind set. If both are work steps,
  the canonical control set reduces to `ROUTE`, `RETRY`, `REPLAN`, `TERMINATE`. Deciding it **after**
  `PlanStep` is written turns an additive change into a rework, which is why it is recorded now.
- **Effect while Open:** does **not** block V0.1. Under D-049 both remain control-flow kinds, which
  is the conservative position — moving a kind from control to work later is additive for the work
  category. **No reclassification may be made silently while writing the contract.**
- **Needs:** Owner to decide whether either or both are work steps, and if HUMAN_APPROVAL is a work
  step, what capability it requests.

### D-058 — Should `paused` later become a more specific name?

- **Status:** Open · **Source:** handoff §32 · **Split out of D-052, left Open by the owner**
- **Finding:** §32 renders the state as `MISSION PAUSED` with "Maximum recovery budget exceeded" and
  "Human review required" as separate reason lines. D-052 adopts `paused` as the enum value and
  carries the explanation in `status_reason`. If future work introduces other reasons for suspending
  a mission — a `HUMAN_APPROVAL` step awaiting a decision (§13), or a policy hold (§29) — a single
  `paused` value may need to become several, or may correctly remain one value distinguished by
  reason.
- **Effect while Open:** none on V0.1. A rename or split is an enum change at whatever milestone
  introduces the second reason for pausing.
- **Needs:** Revisit when `HUMAN_APPROVAL` is implemented (V0.3 per §50's mapping, or later) or when
  the policy engine lands at V1.2.

### D-059 — Is "could not satisfy the reliability contract" `failed` with a reason, or a distinct terminal state?

- **Status:** Open · **Source:** handoff §30, §47; invariant 13 · **Split out of D-052, left Open by the owner**
- **Finding:** §30 requires EIDOS to be able to say "Mission could not satisfy the requested
  reliability contract", and §47 requires that outcome to be preferred over a confident guess.
  Invariant 13 makes it a first-class result. But the handoff gives it **no event name in §33** and
  **no status value in §53**, so it cannot be resolved from the text.

  Either it is `failed` with a distinguishing `status_reason`, or it is a fifth terminal state.
- **Why it matters:** invariant 13 requires the outcome to be distinguishable from a crash, a
  timeout or a budget exhaustion. If it collapses into `failed`, that distinction lives entirely in
  `status_reason`, which means anything reasoning about it — telemetry (§33), the UI (§41), strategy
  memory (§21) — must parse a reason rather than read a state.
- **Effect while Open:** none on V0.1 — no verification exists to produce the outcome. Material at
  V0.4 when verification lands, and at V1.2 for governance.
- **Needs:** Owner decision, ideally before verification is built at V0.4.

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

### D-075 — Payload type definitions per event type

- **Status:** Open · **Source:** handoff §33 (types named, payloads never described) · **Split out of D-067, deferred by the owner**
- **Finding:** D-067 removes the payload field from the V0.1 `MissionEvent`. The thirteen event types
  §33 names plainly carry different content — `PLAN_REJECTED` a rejection reason, `MCP_TOOL_CALLED` a
  tool and arguments, `VERIFICATION_FAILED` what failed, `MISSION_COMPLETED` an outcome — and **the
  handoff describes none of them**.
- **Intended direction, recorded but not built:** a **typed, discriminated payload representation
  keyed by event type**, not an untyped mapping. CLAUDE.md §8 forbids untyped dicts crossing a module
  boundary, so a generic container is not an available fallback.
- **Effect while Open:** none on V0.1 — no payload field exists and V0.1 emits no events.
- **Needs:** Per-type payload shapes, defined at the milestone that first emits each type. The types
  span V0.3 through V0.8, so this resolves incrementally rather than in one decision.

### D-076 — Event-log completeness: what payloads must carry for faithful replay

- **Status:** Open · **Source:** handoff §73; invariant 15; D-010a · **Split out of D-067, deferred by the owner**
- **Finding:** **D-010a** makes MissionState a materialized view over the event log, which shifts the
  completeness burden onto the log: *an event that is not recorded is not replayable*. §73 requires
  replay to consume recorded events **without re-running agents**. Together these impose a real
  constraint on payload **content** — payloads must carry whatever the reducer needs to reconstruct
  state — but that constraint cannot be discharged until **D-039** defines the reducer.
- **Why it is separate from D-075:** D-075 asks what shape a payload has; D-076 asks what it must
  *contain* for invariant 15 to hold. A well-typed payload that omits something the reducer needs
  would satisfy D-075 and still break replay.
- **Effect while Open:** none on V0.1. Deferring payloads also defers the point at which invariant
  15's completeness obligation becomes **testable** — the obligation is not created here, but the
  reckoning is postponed.
- **Needs:** Settle alongside **D-039** (reducer signature) at V0.5, and verify at the milestone
  where replay is first exercised.

### D-071 — Will detached or reusable genome representations ever be needed?

- **Status:** Open · **Source:** handoff §21, §22 · **Split out of D-068, deferred by the owner**
- **Finding:** D-068 makes `TaskGenome` mission-owned with ownership expressed by containment. If a
  genome is ever stored **detached** from its `MissionState` — for strategy memory (§21), telemetry
  (§33), or a vector collection (§25) — it will not say which mission it belonged to, and something
  will have to attach that at write time or carry it in the storage layer.

  This is the same accepted cost recorded in **D-033** for `tenant_id` being root-only, and it lands
  in the same place: V1.0 strategy memory.
- **Why it is not urgent:** §21 stores `task_class` and `task_genome **characteristics**` — derived
  features, not the genome object — so the detached case may never arise.
- **Effect while Open:** none on V0.1.
- **Needs:** Revisit at V1.0 when strategy memory is built. Adding a back-reference then would be
  additive.

### D-074 — Is §30's approval wording exactly `autonomy_level >= 3`?

- **Status:** Open · **Source:** handoff §29 vs §30 · **Split out of D-069, left Open by the owner**
- **Finding:** D-069 removes `High-risk actions: Require human approval` from the contract and routes
  approval through §29's `autonomy_level`. That presumes the two express the same thing, but the
  mapping has not been stated. §30's wording is scoped to "**high-risk actions**"; §29's Level 3 is
  scoped to the **whole mission**. So §30's clause may be *narrower* — approval for some actions
  rather than for everything — in which case `autonomy_level >= 3` does not reproduce it exactly.
- **Why it matters:** if the two are not equivalent, D-069 dropped a capability rather than a
  duplicate. Resolving it requires an action-risk notion, which **D-051** deliberately left untyped
  and **D-057** leaves undetermined.
- **Effect while Open:** none on V0.1 — no approval mechanism is implemented and no contract field
  exists either way.
- **Needs:** Owner to state whether the two are equivalent. Adjacent to **D-061**, which asks how
  mission-wide autonomy relates to the per-step `HUMAN_APPROVAL` kind; D-074 adds §30's wording to
  that same family rather than opening an unrelated question.

### D-078 — Units for the time and token budgets

- **Status:** Open · **Source:** handoff §6 vs §30 vs §53 · **Identified during the D-073 analysis; logged at the owner's instruction**
- **Finding:** The handoff expresses latency in **three different units**: `"latency_budget_ms":
  600000` (§6), `"maximum_latency_seconds": 600` (§53's request), `Maximum latency: 8 minutes` (§30),
  and `"latency_ms": 372000` in §53's result. Nothing states a canonical unit. `max_tokens` has no
  unit ambiguity but shares the same field-naming question — whether the unit is carried in the name
  (`max_execution_time_ms`) or left implicit.
- **Why it blocks:** a numeric field whose unit is undecided is ambiguous at every call site, and
  **D-046**'s eventual values would be meaningless without it. §67 forbids presenting numbers whose
  meaning is not established.
- **Affects:** `ReliabilityContract.max_execution_time` and `max_tokens`; the corresponding
  `MissionState` budget counters (**D-042**).
- **Needs:** A canonical unit for duration, and whether units appear in field names.

### D-079 — Is `tenant_id` required-to-supply, or defaulted?

- **Status:** Open · **Source:** **D-019**'s own wording · **Identified during the D-073 analysis; logged at the owner's instruction**
- **Finding:** D-019 states that `tenant_id` is "present and **required** on V0.1 root models" and
  that it "carries a single fixed **default** value". In contract terms those two statements
  conflict: **a field with a default does not need to be supplied**, so it is not required in the
  constructor sense. The intent was most likely "always has a value, never null" — but which
  mechanism delivers that was never decided.
- **Why it blocks:** the five root models cannot declare the field without choosing. It also
  determines whether **D-032** (the literal default value) is needed at all — if the field must be
  supplied by the caller, there is no default constant to choose.
- **Affects:** `TaskGenome`, `ReliabilityContract`, `Plan`, `MissionState`, `MissionEvent` (**D-033**).
- **Needs:** Owner to state whether callers must supply `tenant_id` or whether the model defaults it.
  Note that D-019's binding caveat holds either way: **the field carries no security meaning.**

### D-080 — Representation of `capability`

- **Status:** Open · **Source:** handoff §6, §7, §13; **D-049** · **Identified during the D-073 analysis; logged at the owner's instruction**
- **Finding:** **D-049** established that work steps carry a capability and control steps do not, and
  **D-007** leaves the vocabulary and matching semantics open. **The field's representation has never
  been decided.** Candidates include a plain string, a distinct per-kind identifier type in the style
  of **D-053**, or a closed enumeration once D-007 settles the vocabulary.

  The consolidated V0.1 specification described it as "an opaque identifier". **That was an
  assumption by Claude Code, not a decision**, and is recorded here so it is not mistaken for one.
- **Why it blocks:** `PlanStep.capability` and `TaskGenome.required_capabilities` cannot be declared
  without it.
- **Affects:** `PlanStep`, `TaskGenome`.
- **Needs:** A representation. It can be settled independently of **D-007**, since the vocabulary and
  the carrier are separate questions.

### D-081 — Representation of `AgentTask.status`

- **Status:** Open · **Source:** handoff §8; **D-048**, **D-036** · **Identified during the D-073 analysis; logged at the owner's instruction**
- **Finding:** **D-048** includes `status` in the V0.1 `AgentTask` and leaves its **semantics** open
  under **D-036**, with the binding rule that **nothing may branch on its value**. It says nothing
  about the **type**. A free-form string is a choice rather than a neutral default, and any closed
  enumeration would pre-empt D-036 by fixing the state set.
- **Why it blocks:** `AgentTask` cannot be declared without it — the only field of that model still
  undetermined.
- **Affects:** `AgentTask`.
- **Needs:** A representation that does **not** imply a state set, since D-036 owns that.

### D-082 — `MissionState` collection shapes and `Plan.version`

- **Status:** Open · **Source:** handoff §8, §15, §32; **D-010a**, **D-042** · **Identified during the D-073 analysis; logged at the owner's instruction**
- **Finding:** **D-010a** names the field set in prose — "plan versions and lineage", "remote
  `AgentTask` records", "budget consumption counters" — without specifying their shapes:
  - whether plans are an **ordered append-only sequence** and whether ordering is by version;
  - how `agent_tasks` is **keyed** (by `agent_id`, by `a2a_task_id`, or by a separate task id) —
    noting §8 gives `AgentTask` no id of its own;
  - the **types** of the six budget counters, which is entangled with **D-078**.

  Related and equally undetermined: **`Plan.version`** — an integer starting at 1, monotonic per
  mission, per lineage, or something else. §15 shows `Plan v1 -> Plan v2` without stating the rule.
- **Why it blocks:** `MissionState` and `Plan` cannot be declared without these.
- **Affects:** `MissionState`, `Plan`.
- **Needs:** Concrete shapes. The `agent_tasks` key is the sharpest, since §8's `AgentTask` has no
  identifier the handoff designates as primary.

### D-083 — Timestamp representation

- **Status:** Open · **Source:** handoff §10, §54; **D-054** · **Identified during the D-073 analysis; logged at the owner's instruction**
- **Finding:** **D-054** settled *where* timestamps come from — explicit required inputs, never the
  wall clock. It did not settle **what they are**: whether timezone-aware instants are required,
  whether naive values are rejected, and what resolution is assumed.
- **Why it blocks:** every model carrying a timestamp. For `MissionEvent` specifically it is not
  cosmetic — `occurred_at` comes from a **producer's** clock and `recorded_at` from EIDOS ingestion
  (**D-011**), and comparing or ordering those across processes at V0.6 requires an unambiguous
  representation.
- **Affects:** `MissionEvent`, `MissionState`, and any other model with a timestamp.
- **Needs:** A representation, and a rule for naive values. Recommend deciding alongside **D-078**,
  since both concern how time is expressed.

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
