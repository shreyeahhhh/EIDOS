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

---

## Open — require the human owner

These are ambiguities, contradictions and gaps found in the handoff during the bootstrap read. None
has been resolved. Work that depends on one of them is blocked until the owner decides.

Count: 45. Highest-impact first is **D-015** (how verification confidence is computed), then
**D-007** (capability vocabulary) and **D-012** (predicate language) for V0.2.

**All type-level V0.1 blockers are cleared.** What remains for V0.1 is field-level: **D-031**,
**D-065**, **D-067**, **D-068**, **D-069**, plus the cross-cutting **D-053** and **D-054**.

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

### D-065 — Is each ReliabilityContract budget field required or optional?

- **Status:** Open · **Source:** not stated by the handoff · **Split out of D-042, left Open by the owner**
- **Finding:** D-042 fixes the six-field budget group. Whether each field must be supplied is
  unstated. §30's example contract carries only two of the six, which suggests a contract may
  legitimately omit budgets — but §30 is an example, so it evidences nothing about obligation. §53's
  conceptual API is a further hint in the same direction: the user states three constraints there
  (`minimum_confidence`, `maximum_latency_seconds`, `risk_tolerance`) and **no budgets at all**,
  implying most budget values would be system-derived rather than user-stated.
- **Why it is distinct from D-045:** an **optional field on a present contract** and an **absent
  contract** are different situations with potentially different fallbacks. D-045 asks what happens
  with no contract; D-065 asks what happens with a contract that omits a field.
- **Effect while Open:** partially blocks V0.1 — the six field names are settled, their optionality
  is not.
- **Needs:** Per-field required/optional, and the fallback when a field is omitted. Under D-009 the
  natural fallback is the system ceiling, but that has not been decided and must not be assumed.

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

### D-067 — How is `MissionEvent.payload` typed?

- **Status:** Open · **Source:** handoff §10, §33 · **Surfaced in the V0.1 contract specification; logged at the owner's instruction**
- **Finding:** §33 names thirteen event types whose payloads plainly differ — `PLAN_REJECTED` carries
  a rejection reason, `MCP_TOOL_CALLED` carries a tool invocation, `MISSION_COMPLETED` carries an
  outcome. The handoff never describes a payload structure for any of them. CLAUDE.md §8 forbids
  untyped mappings crossing a module boundary, so "a dict" is not available as an answer.
  Candidate representations include a discriminated union keyed on `type`, a per-type event class
  hierarchy, or some other explicitly defined structure — **none of which is stated by the handoff,
  and none of which is being chosen here.**
- **Effect while Open:** blocks the payload field of `MissionEvent`. The rest of the model — event
  identity, ordering, timestamps, type — is settled by **D-011**.
- **Needs:** An explicit representation decision. Interacts with **D-037** (whether internal and
  external events share one shape) and with **D-052**/**D-059**, since some payloads carry status
  reasons.

### D-068 — Is `TaskGenome` mission-owned, or independently reusable?

- **Status:** Open · **Source:** handoff §6 vs §21, §22 · **Surfaced in the V0.1 contract specification; logged at the owner's instruction**
- **Finding:** §6 describes the Task Genome as the structured form of one mission's intent, which
  reads as mission-owned and would carry `mission_id`. But §21 stores "task_genome characteristics"
  in strategy memory and §22 ranks strategies for "a future **similar** task" — which reads as the
  genome, or features derived from it, being **reused across missions** as a similarity key. A
  genome carrying `mission_id` is by construction unique per mission and cannot itself be the
  similarity key.

  This tension is what made **D-013** decide as it did: the genome was kept free of constraint
  thresholds precisely so it would remain a clean similarity key. D-068 asks the next question —
  whether the genome *is* that key, or whether §21's "characteristics" are separately derived
  features and the genome remains mission-owned.
- **Effect while Open:** determines whether `TaskGenome` carries `mission_id`.
- **Needs:** Owner decision. Material for V1.0 strategy memory as well as for the V0.1 field list.

### D-069 — Is §30's high-risk approval clause a contract field or a policy rule?

- **Status:** Open · **Source:** handoff §28, §29, §30 · **Surfaced in the V0.1 contract specification; logged at the owner's instruction**
- **Finding:** §30's example contract ends with `High-risk actions: Require human approval`. Every
  other clause in that example is a **value** — a threshold or a budget. This one is a **rule**, and
  **D-042** flagged it as such when fixing the budget group. It could be a contract field (for
  instance an approval threshold expressed against the task-risk vocabulary), or it could be a
  later deterministic policy rule belonging to the V1.2 policy engine rather than to the contract's
  surface.
- **Why it matters:** invariant 14 requires governance to be deterministic and enforced in code.
  Whether the rule is data carried per-mission or logic carried by the policy engine changes where
  that enforcement lives — and interacts with **D-061**, since mission-wide `autonomy_level` level 3
  already expresses "human approval required".
- **Effect while Open:** determines whether `ReliabilityContract` carries an approval-related field
  at all.
- **Needs:** Owner decision. Note that three mechanisms currently touch approval — this clause,
  §29's level 3, and the `HUMAN_APPROVAL` step kind — which is the same multiplicity problem
  **D-061** already records.

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
