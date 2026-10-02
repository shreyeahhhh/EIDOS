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
- **Extended by D-116 (2026-09-19):** LangGraph is declared as an optional extra, also in `dev`, at V0.3 —
  the milestone this entry anticipated. This entry is not reopened.

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
  `TERMINATE`. Conditional payloads and predicate semantics are deferred under **D-012**, to the
  milestone that actually needs them.

- **Rationale:** An opaque placeholder field would be an untyped value crossing a module boundary,
  which CLAUDE.md §8 forbids, and would invite something to start depending on its shape before the
  shape is decided. Defining structure without semantics keeps V0.1 fully typed and leaves D-012 a
  clean decision rather than a migration.

- **Consequences:**
  - The `PlanStep` contract is complete and typed for V0.1 with no placeholder fields.
  - **D-012 remains Open** and is unaffected. This decision scopes V0.1; it does not choose a
    predicate language.
  - Conditional payloads will be added to `PlanStep` at whichever milestone needs them, as an
    additive contract change rather than a reinterpretation of an existing field. **Corrected
    2026-09-18: that milestone is V0.3 (the compiler), not V0.2** — see D-012's own entry. Neither
    D-047 nor D-004 is modified by this correction; it fixes a forward-looking claim this entry made
    about a different decision's timing, not this decision's own scope.
  - A V0.1 plan containing a conditional kind is structurally valid but semantically incomplete.
    Nothing in V0.1 or V0.2 executes plans, so this is inert — but it must not silently become
    executable at V0.3 without D-012.

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
    which must set values against those definitions. *(Path length is counted in **nodes**, not
    edges — recorded in D-104, 2026-09-19.)*
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

- **Later note — V1.2 tool admission (added 2026-09-25 at the V1.2 close-out; nothing above is edited).** The omitted-budget fallback in this decision does **not** govern the V1.2
  tool-admission boundary. **D-205 (item 1, ruled by the owner on 2026-09-25) supersedes D-065 for that boundary:** `max_tool_calls=None` produces `BUDGET_UNRESOLVED`; it does not fall
  back to `SystemLimits.max_tool_calls`; there is no implicit unlimited, default or zero behaviour; and the per-`(execution_id, plan_id)` budget semantics are preserved. The supersession
  is scoped to that one boundary: this note decides nothing about any other budget field or consumer, and D-065 stays as accepted, historically intact.

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
- **V0.5 (2026-09-21):** the V0.1 `MissionEvent` stays an envelope with no payload field. **D-153** pairs it with a typed payload in an `EventRecord` (`eidos.state`) instead of adding a field to the
  contract.


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

### D-077 — Field presence for the five contracts: the required/optional split

- **Status:** Accepted · **Date:** 2026-09-18 · **Decided by:** human owner
- **Source:** handoff §6, §10, §15, §32, §33, §73; applies the evidentiary standard of D-065 and D-073
- **Context:** Field presence had been decided only for `AgentTask` (D-048) and `ReliabilityContract`
  (D-065, D-073). Five models remained. The standard applied is the one D-065 and D-073 used — **does
  a worked example in the handoff demonstrate omission?** — plus a second the handoff supplies
  directly: **does it show a state in which the field cannot yet exist?**

- **Decision — accepted for the present/absent split only:**

  | Model | Required | Optional |
  |---|---|---|
  | `TaskGenome` | `goal`, `required_capabilities`, `risk_level`, `autonomy_level`, `allowed_actions` (plus `tenant_id` per D-019 and `reliability_contract` per D-045) | `information_dependencies` |
  | `Plan` | `tenant_id`, `plan_id`, `mission_id`, `version`, `steps` | `parent_plan_id`, `replan_reason` |
  | `PlanStep` | `step_id`, `kind`, `depends_on` (`capability` governed by D-049) | — |
  | `MissionEvent` | `event_id`, `tenant_id`, `mission_id`, `sequence`, `recorded_at`, `type` | — |
  | `MissionState` | `tenant_id`, `mission_id`, `created_at`, `updated_at`, `state_version`, `status` | `status_reason`, `active_plan_id` |

  Clarifications stated by the owner:
  - **An optional field may be absent.**
  - **A required collection field may still legally be empty.** Absence and emptiness are separate
    questions, and **emptiness is not resolved by D-077**.
  - **`depends_on` is a required field whose value may be an empty collection for a DAG root.**

- **Basis per field group:**
  - `TaskGenome.information_dependencies` is optional because **§6's own example omits it** — the same
    demonstration-of-omission standard as D-065. Every other genome field is present in that example.
  - `Plan.parent_plan_id` and `Plan.replan_reason` are optional because §15 is explicit that `Plan v1`
    precedes any replan — a v1 plan has no parent and no reason **by construction**.
  - `MissionEvent`'s envelope is required because §10 says **every** event carries its field set.
  - `MissionState.status_reason` is optional because §32 shows a reason on `paused` and a completed
    mission has none; `active_plan_id` because §73 shows a mission existing before any plan is
    selected.
  - `PlanStep.capability` is **not** decided here — **D-049** governs it structurally (required on work
    steps, absent from control steps).

- **Explicitly not decided by D-077**, each logged separately:
  - `MissionState.task_genome` — **D-084**
  - `MissionState.execution_id` — **D-085**
  - `MissionEvent.occurred_at` — **D-086**, aligned with D-037
  - collection emptiness — **D-087**

  *All four were subsequently resolved on 2026-09-18.*

  Also **not assigned** by the D-077 proposal: the presence of `MissionState.plans`,
  `MissionState.agent_tasks` and the budget counters. These were discussed only in connection with
  emptiness and were never given a present/absent verdict, so **none is inferred here.**

### D-088 — `Plan.mission_id` stays required

- **Status:** Accepted · **Date:** 2026-09-18 · **Decided by:** human owner
- **Source:** D-077; deliberate asymmetry with D-068
- **Context:** D-068 removed `mission_id` from `TaskGenome` because MissionState *contains* the genome,
  so a back-reference would duplicate the value and make a mismatch representable. MissionState also
  contains `plans` (D-010a), so the same argument applies to `Plan.mission_id`, which D-077 had marked
  required. The two decisions reasoned in opposite directions.
- **Decision:** `Plan.mission_id` **remains required**.
- **Rationale (owner's):** a Plan is a **mission-specific versioned artifact** and should be
  **self-identifying when considered outside MissionState**. **This does not change D-068** —
  `TaskGenome` still does not carry `mission_id`.
- **Consequences:** a deliberate asymmetry, now recorded rather than accidental. The consistency
  obligation D-068 avoided **does exist for `Plan`**: a plan whose `mission_id` differs from its
  containing MissionState's is representable, so that equality will need checking wherever plans are
  placed into a state.

### D-089 — `TaskGenome` references its ReliabilityContract by identifier

- **Status:** Accepted · **Date:** 2026-09-18 · **Decided by:** human owner
- **Source:** D-013 ("references"), D-045
- **Context:** D-013 said the genome "references" the contract without saying by value or by id.
- **Decision:** `TaskGenome` references the contract **by contract identifier**, not by embedding or
  copying the contract object. The identifier uses a **distinct `ReliabilityContractId` type**.
- **Consequences:**
  - `ReliabilityContractId` is an EIDOS-assigned identifier, so **D-053**'s UUID-backed rule applies.
  - `ReliabilityContract.contract_id` is **required as a direct consequence** — a contract referenced
    by id must carry that id. Recorded as consequence, not as a separate decision.
  - ⚠️ **The contract object no longer has a home in MissionState.** D-010a's field set contains the
    genome but not the contract; under by-value containment the contract rode inside the genome, and
    this decision removes that path. Recorded as **D-100**.

### D-090 — `MissionEventType` is exactly the thirteen event types named in §33

- **Status:** Accepted · **Date:** 2026-09-18 · **Decided by:** human owner
- **Source:** handoff §33
- **Decision:** V0.1 defines **exactly** the thirteen event types explicitly named in §33:
  `MISSION_CREATED`, `PLAN_GENERATED`, `PLAN_REJECTED`, `PLAN_COMPILED`, `A2A_TASK_STARTED`,
  `A2A_TASK_COMPLETED`, `MCP_TOOL_CALLED`, `RAG_SEARCH`, `EVIDENCE_REJECTED`, `VERIFICATION_FAILED`,
  `REPLAN_TRIGGERED`, `MISSION_COMPLETED`, `MISSION_FAILED`. **No inferred event types are added.**
  Future types may be added in later milestones.
- **Consequences:**
  - The consolidated specification's "§33's thirteen, extensible" was an assumption by Claude Code;
    this replaces it with a decision.
  - Several of these types cannot occur in V0.1 (A2A, MCP and RAG subsystems do not exist). This
    differs from **D-052**, which excluded unreachable *mission states*; the owner chose to define the
    full §33 vocabulary for the event log regardless. Recorded so the difference is visible.
- **Superseded in part by D-154 (2026-09-21):** `MissionEventType` gains `NODE_STARTED`, `NODE_SETTLED` and `MISSION_PAUSED` and has **sixteen** members. The thirteen §33 types are unchanged.


### D-091 — MissionState collections and counters

- **Status:** Accepted · **Date:** 2026-09-18 · **Decided by:** human owner
- **Source:** D-010a, D-042, D-077; narrows D-082 and D-087
- **Decision:**
  - `plans`, `agent_tasks` and **all six budget-consumption counters** are **required** fields.
  - The collections **may legally be empty**.
  - The collections are **immutable**.
  - The counters are **non-negative integers**.
  - The execution-time counter uses **the same unit later chosen for `max_execution_time`** (D-078).
- **Consequences:**
  - Assigns the presence D-077 never gave these fields.
  - **Narrows D-087:** emptiness is settled for `MissionState.plans` and `agent_tasks`.
  - **Narrows D-082:** counter types and collection presence/immutability are settled; `Plan.version`
    and `agent_tasks` keying remain Open under D-082.

### D-092 — `StepId`: an opaque string unique within a plan version

- **Status:** Accepted · **Date:** 2026-09-18 · **Decided by:** human owner
- **Source:** D-004 (left the step-id namespace open); an explicit exception to D-053
- **Decision:** `step_id` uses a **distinct opaque `StepId` string**, **unique within a plan version**.
  **D-053's UUID-backed identifier rule does not apply to `StepId`.** LLM-generated ids such as
  `research_1` are valid identifiers.
- **Rationale:** the planner emits step ids inside the Plan DSL (invariant 3), and `depends_on`
  references them. Forcing UUIDs onto identifiers an LLM authors would make the DSL hard to produce and
  to read without any gain in collision safety, since uniqueness is only required within one version.
- **Consequences:** resolves the step-id namespace question D-004 left open, which had never been given
  its own number.

### D-093 — `Plan.steps` is an immutable ordered collection

- **Status:** Accepted · **Date:** 2026-09-18 · **Decided by:** human owner
- **Source:** D-004, D-077
- **Decision:** `Plan.steps` is an **immutable ordered collection of `PlanStep`**. It is **not** a map
  keyed by `step_id`. **`step_id` uniqueness is validated separately.**
- **Consequences:** uniqueness is a validation property rather than a structural one, which is
  consistent with §14 placing checks in a validation pipeline. Emptiness of `steps` remains under D-087.

### D-094 — `allowed_actions` are opaque immutable string identifiers

- **Status:** Accepted · **Date:** 2026-09-18 · **Decided by:** human owner
- **Source:** handoff §6
- **Decision:** V0.1 represents `allowed_actions` as **opaque immutable string identifiers**. **No
  action vocabulary or enumeration is invented.**
- **Consequences:** matches §6's example (`read_documents`, `read_repository`, `query_monitoring`).
  Whether actions eventually form a controlled vocabulary is left open alongside D-007's analogous
  question for capabilities. Emptiness remains under D-087.

### D-095 — A2A identifiers are externally assigned opaque strings

- **Status:** Accepted · **Date:** 2026-09-18 · **Decided by:** human owner
- **Source:** handoff §8; an explicit exception to D-053
- **Decision:** `a2a_task_id` and `a2a_context_id` are **externally assigned opaque strings** and are
  **not required to be UUIDs generated by EIDOS**. **D-053's UUID rule does not apply to externally
  assigned protocol identifiers.**
- **Rationale:** these are assigned by the remote A2A system; EIDOS mirrors them (invariant 2) and has
  no authority over their format, which **D-023** will determine.

### D-096 — `AgentTask.last_event` is an optional `EventId` reference

- **Status:** Accepted · **Date:** 2026-09-18 · **Decided by:** human owner
- **Source:** handoff §8; D-048
- **Decision:** `last_event` is **`EventId | None`**. **A `MissionEvent` is not embedded.**
- **Consequences:** a reference rather than a copy, so the event log remains the single record of the
  event. `latest_artifact` is **not** decided here — see **D-098**.

### D-097 — Event sequence starts at 1; `state_version` tracks the latest applied sequence

- **Status:** Accepted · **Date:** 2026-09-18 · **Decided by:** human owner
- **Source:** D-011, D-010a
- **Decision:**
  - The mission event `sequence` **begins at 1**.
  - `state_version` is a **non-negative integer representing the latest applied mission sequence**.
  - Exact reducer and checkpoint semantics remain **deferred to V0.5** (D-039, D-010b).
- **Consequences:** a MissionState with no applied event has `state_version = 0`; after the first
  event it equals 1. Whether a MissionState can exist before `MISSION_CREATED` is applied is part of
  **D-084**, not this decision. *(D-084 has since established that MissionState is created with its
  genome.)*
- **V0.5 (2026-09-21):** the reducer semantics deferred here are decided by **D-155** (a contiguous sequence and an outcome-returning reducer) and the checkpoint semantics by **D-157**.


### D-078 — Budget units: integer milliseconds and integer token counts

- **Status:** Accepted · **Date:** 2026-09-18 · **Decided by:** human owner
- **Source:** handoff §6 (`latency_budget_ms`), §30 (minutes), §53 (seconds)
- **Decision:**
  - `max_execution_time` is **integer milliseconds** internally.
  - The corresponding MissionState execution-time counter is **milliseconds**.
  - `max_tokens` is a **non-negative integer token count**.
  - Conversion between minutes, seconds and milliseconds for the API or UI is **outside the contract
    model**.
- **Consequences:** the three units the handoff uses for latency are reconciled at the boundary rather
  than in the contract. Milliseconds matches §6's `latency_budget_ms` and §53's `latency_ms` result.

### D-079 — `tenant_id` is always present; the single-tenant context supplies it

- **Status:** Accepted · **Date:** 2026-09-18 · **Decided by:** human owner
- **Source:** D-019's own wording ("required" and "carries a default")
- **Decision:**
  - `tenant_id` is **always present and non-null** on root models.
  - V0.1 is single-tenant, so a **fixed default `TenantId` is supplied by the single-tenant context**.
  - The default **carries no security meaning**.
  - "Required" means **every constructed root model has a `tenant_id` value**; it does **not** require
    every caller to supply the same value by hand.
- **Consequences:** resolves the conflict within D-019. **D-032** (the literal default value) is no
  longer a contract-model question — the value belongs to the single-tenant context, not to any model.
  D-019's binding caveat is restated: no authentication, authorization or isolation meaning.

### D-080 — `CapabilityId` and `ActionId` are distinct opaque identifier types

- **Status:** Accepted · **Date:** 2026-09-18 · **Decided by:** human owner
- **Source:** handoff §6, §7, §13; D-049, D-094
- **Decision:**
  - `CapabilityId` is an **opaque identifier type**, used by `TaskGenome.required_capabilities` and by
    work-step `PlanStep.capability`.
  - `ActionId` is a **separate opaque identifier type**, used by `allowed_actions`.
  - **No capability vocabulary and no action vocabulary is defined yet** (D-007 stays Open).
- **Consequences:**
  - Both are **string-backed and exempt from D-053's UUID rule.** Recorded as a consequence rather than a
    new decision: §13's own example writes `"capability": "research"`, §6 lists capabilities and actions
    as plain names, **D-094** already made `allowed_actions` opaque strings, and the planner emits
    capabilities inside the Plan DSL — so a UUID-backed `CapabilityId` would make the handoff's own
    examples unrepresentable. This follows **D-092**'s treatment of `StepId`.
  - Refines D-094: `allowed_actions` is now a collection of `ActionId`.

### D-081 — `AgentTask.status` is an opaque string in V0.1

- **Status:** Accepted · **Date:** 2026-09-18 · **Decided by:** human owner
- **Source:** handoff §8; D-036, D-048
- **Decision:** `AgentTask.status` is an **opaque string** in V0.1. **No code may branch on its value
  until D-036 defines the lifecycle.**
- **Consequences:** does not pre-empt D-036's state set, which a closed enumeration would have done.

### D-082 — Collection shapes, `Plan.version`, and counters

- **Status:** Accepted · **Date:** 2026-09-18 · **Decided by:** human owner
- **Source:** handoff §8, §15; D-010a, D-042, D-091, D-093
- **Decision:**
  - `Plan.version` is a **positive integer starting at 1**, **increasing monotonically within a mission**.
  - `Plan.steps` is an **immutable ordered collection**.
  - `MissionState.plans` is an **immutable ordered collection**.
  - `MissionState.agent_tasks` is an **immutable collection**.
  - The six budget counters are **non-negative integers**.
  - **Empty collections are legal in V0.1.**
  - **No storage-specific collection semantics** are added.
- **Consequences:** `agent_tasks` is a collection rather than a keyed map, which retires the keying
  question this item originally raised. Version monotonicity is scoped by mission, consistent with
  **D-088** keeping `Plan.mission_id`.

### D-083 — Timestamps are timezone-aware UTC; naive values are rejected

- **Status:** Accepted · **Date:** 2026-09-18 · **Decided by:** human owner
- **Source:** D-011, D-054
- **Decision:** all timestamps are **explicit timezone-aware UTC datetime values**. **Naive timestamps
  are rejected.** No contract constructs its own current timestamp (restating **D-054**).
- **Consequences:** `occurred_at` (producer clock) and `recorded_at` (EIDOS ingestion) are comparable
  across processes at V0.6 without ambiguity.

### D-087 — Empty collections are legal in V0.1

- **Status:** Accepted · **Date:** 2026-09-18 · **Decided by:** human owner
- **Source:** the explicit statement "Empty collections are legal in V0.1" in the owner's **D-082**
  decision
- **Decision:** every required collection field may legally be empty in V0.1 — including
  `TaskGenome.required_capabilities`, `TaskGenome.allowed_actions` and `Plan.steps`, which were the
  parts of this item still open after D-091.
- **Why recorded here:** D-082's statement answers this item exactly. Leaving D-087 marked Open would
  have contradicted an accepted rule. **No validation rules are invented in V0.1**, per this item's
  original constraint; whether an empty collection is *meaningful* is left to later validation.

### D-098 — `AgentTask.latest_artifact` is `ArtifactRef | None`

- **Status:** Accepted · **Date:** 2026-09-18 · **Decided by:** human owner
- **Source:** handoff §8, §50; D-048
- **Decision:** `latest_artifact` is **`ArtifactRef | None`**, where `ArtifactRef` is an **opaque
  identifier/reference**. **No full `Artifact` model is created yet.**
- **Consequences:** resolves the representability tension recorded earlier — the field now has a type.
  `ArtifactRef` is **string-backed and exempt from D-053**, recorded as a consequence: artifacts are
  produced by remote A2A agents, so this follows **D-095**'s treatment of externally assigned protocol
  identifiers.
- **V0.4 (2026-09-20):** **D-145** introduces a **minimal** artifact model (`ref`, `content_type`, `content`, `source_refs`) in `eidos.agents`.
  `ArtifactRef` stays opaque and the runtime never sees content; the full model this entry deferred is still not created.


### D-099 — `information_dependencies` is an immutable collection of opaque strings

- **Status:** Accepted · **Date:** 2026-09-18 · **Decided by:** human owner
- **Source:** handoff §6 (field named, never exemplified); D-077
- **Decision:** `information_dependencies` is an **immutable collection of opaque identifiers/strings**
  in V0.1. **No richer dependency semantics are invented.** The field remains optional per **D-077**.
- **Consequences:** resolves the representability tension recorded earlier.

### D-100 — MissionState holds the authoritative ReliabilityContract

- **Status:** Accepted · **Date:** 2026-09-18 · **Decided by:** human owner
- **Source:** D-010a, D-089; invariant 1
- **Context:** **D-089** made `TaskGenome` reference its contract by id, which left the contract object
  with no container: D-010a's MissionState field set never held it, and under by-value containment it
  had travelled inside the genome.
- **Decision:** add the authoritative **`reliability_contract: ReliabilityContract`** to MissionState.
  `TaskGenome` retains **only `reliability_contract_id`**. The full contract is **not** duplicated inside
  `TaskGenome`.
- **Rationale (owner's):** MissionState contains the contract because it is the **authoritative global
  mission state** and must be able to answer the mission's **acceptance constraints synchronously**.
- **Consequences:**
  - Amends D-010a's field set by one field. Satisfies invariant 1: the contract lives inside the one
    authoritative state rather than beside it.
  - MissionState can now reach both the budget **counters** (D-091) and the **limits** they are measured
    against, so D-009's `min(system, contract)` rule is computable from state.
  - The contract id now appears twice — as `TaskGenome.reliability_contract_id` and as
    `MissionState.reliability_contract.contract_id` — so a mismatch is **representable** and must be
    checked, as with **D-088**'s `Plan.mission_id`.
  - Lifecycle interaction noted, not decided: the contract is required on MissionState, while whether
    MissionState may exist before its genome was **D-084** (since resolved: it is created with its genome),
    and whether the contract may be synthesised
    is **D-066**.

### D-101 — The work-step kind is `agent`

- **Status:** Accepted · **Date:** 2026-09-18 · **Decided by:** human owner
- **Source:** handoff §13's own example (`"type": "agent"`); completes D-049; D-050, D-077
- **Decision:**
  - The capability-bearing work-step kind is named **`agent`**.
  - **`PlanStep.kind = "agent"`** is the V0.1 work-step variant, and it **requires `capability`**.
  - Control-step kinds **do not carry `capability`**.
- **Consequences:**
  - Completes **D-049**, which created the work-step category without naming it.
  - The canonical V0.1 kind set is `agent`, `ROUTE`, `VERIFY`, `RETRY`, `REPLAN`, `HUMAN_APPROVAL`,
    `TERMINATE` — with `VERIFY`/`HUMAN_APPROVAL` classification still under **D-055**, where both remain
    control-flow kinds.
  - Observation, not an open question: the resulting value set is mixed-case — `agent` follows §13's
    lowercase example, the control kinds follow §13's uppercase list. The handoff itself mixes the two
    within §13.

### D-084 — MissionState is created with its TaskGenome

- **Status:** Accepted · **Date:** 2026-09-18 · **Decided by:** human owner
- **Source:** handoff §33, §41, §73; D-010a, D-077, D-090
- **Decision:** `MissionState.task_genome` is **required and non-null** in V0.1. **A mission is created
  with its authoritative TaskGenome.** `MissionStatus.created` does **not** imply the genome is absent.
- **Consistency with the event model — confirmed, and it supports this decision:** **D-090** defines
  exactly the thirteen §33 event types, and **none of them introduces a genome**. There is no event after
  `MISSION_CREATED` that could add one, so under D-010a's fold the genome *must* be established at
  creation. §73's "Task Genome generated" and §41's `00:02 task genome created` are **replay-narrative
  steps, not §33 event types**.
- **Consequences:**
  - Resolves the tension D-077 surfaced between §73's sequence and D-010a's fold.
  - Under **D-067**, `MISSION_CREATED` carries no payload in V0.1, so when the V0.5 reducer rebuilds
    MissionState from the log the genome must come from somewhere in it. That is **D-076**'s existing
    obligation (payload completeness for replay), not a new question. In V0.1, MissionState is
    constructed directly.
  - Together with **D-100**, a MissionState now always carries both its genome and its contract.

### D-085 — One immutable execution identity per mission in V0.1

- **Status:** Accepted · **Date:** 2026-09-18 · **Decided by:** human owner
- **Source:** handoff §15, §32, §54; D-077, D-082, D-088
- **Decision:**
  - `MissionState.execution_id` is **required and immutable** in V0.1.
  - V0.1 has **exactly one execution identity per mission**.
  - **Replanning creates a new plan version, not a new execution.**
  - **Pause/resume retains the same `execution_id`.**
  - Multiple executions or reruns of a mission are **deferred to a later version**.
- **Consequences:**
  - `execution_id` is `ExecutionId`, EIDOS-assigned and UUID-backed per **D-053**.
  - In V0.1 `execution_id` and `mission_id` are one-to-one, so `execution_id` carries no additional
    information yet. It exists from the start per invariant 18, so that reruns can be added later without
    a contract change.
  - Consistent with **D-082**/**D-088**: plan versions increase within a mission, and a replan stays within
    one execution.

### D-086 — `MissionEvent.occurred_at` is required

- **Status:** Accepted · **Date:** 2026-09-18 · **Decided by:** human owner
- **Source:** handoff §10; D-011, D-054, D-083
- **Decision:**
  - `MissionEvent.occurred_at` is **required**. It represents the event's **domain occurrence time**.
  - For **externally produced** events, the **producer's occurrence timestamp is preserved**.
  - For **EIDOS-internal** events with no separate producer clock, **`occurred_at = recorded_at`**, set at
    recording/acceptance.
  - Both timestamps remain explicit **timezone-aware UTC** datetimes (**D-083**).
  - **The reducer must not invent timestamps.**
- **Consistency with D-054 — confirmed:** the contract never reads the clock. The acceptance step supplies
  `recorded_at` explicitly and, for internal events, copies it into `occurred_at`. That clock read belongs
  to the acceptance step, which D-054 anticipated: "whatever supplies the time becomes an explicit
  dependency."
- **Consequences:**
  - The internal/external rule is applied **at acceptance**; **no contract-level validation rule** is
    introduced.
  - Consistent with a **shared** event shape (one field, one rule for internal events), but **does not
    decide D-037**, which remains open for V0.6.

### D-102 — V0.2 capability validation is mission-scoped, not registry-scoped

- **Status:** Accepted · **Date:** 2026-09-18 · **Decided by:** human owner
- **Source:** handoff §6, §7; docs/03's split of `capabilities/` into "V0.2 / V0.4"; follows D-080
- **Context:** D-007 leaves two things unresolved: the matching rule, and whether a canonical,
  cross-mission capability list exists and who owns it. Neither is answerable from the handoff.
  EXPLORE established that capability-to-agent **availability** is unambiguously V0.4 (docs/03's
  package table), and that the only genuinely open fork was *what does "capability validation" mean
  at V0.2, when no registry exists to check against?* Three options were logged (well-formedness
  only; omit the stage; block fully on D-007) — none of them is what was chosen.
- **Decision:**
  1. V0.2 capability validation is **mission-scoped, not registry-scoped**.
  2. Validate that every capability-bearing `agent` `PlanStep` has a valid `CapabilityId`, **and**
     that the requested capability is present in `TaskGenome.required_capabilities`.
  3. **No global or static capability vocabulary is required.**
  4. **No check of whether a live agent currently provides the capability.**
  5. Capability-to-agent availability and binding remain a **later, V0.4** concern.
- **Rationale:** this sidesteps D-007's vocabulary-ownership question for V0.2 rather than answering
  it — the "list" a step's capability is checked against is the **mission's own declared
  `required_capabilities`**, decided per-mission by whoever writes the `TaskGenome`, not a
  system-wide vocabulary. Nothing beyond the V0.1 contracts is needed: both fields already exist,
  both are `CapabilityId`, and the comparison is a plain set-membership check. This was not one of
  the three options originally logged under this item — it is a fourth, narrower scoping that needs
  neither a registry nor a vocabulary.
- **Consequences:**
  - Membership is **exact-string** (`step.capability in genome.required_capabilities`). Anything
    hierarchical or similarity-based would invent matching machinery beyond what was asked; exact
    membership is the only reading that invents nothing, consistent with how D-080 already made
    `CapabilityId` a plain opaque string.
  - **D-007's substantive question is untouched.** This decision answers what V0.2 checks, not what
    the (eventual, cross-mission) capability vocabulary is. D-007 remains Open, and now blocks only
    V0.4 (the agent registry) rather than V0.2.
  - The check spans **two** V0.1 contracts (`Plan`/`PlanStep` and `TaskGenome`) at once, so it is a
    cross-object check in the same family as MissionState's A7 validators, not a Plan-only one. Where
    exactly it runs (on a `(Plan, TaskGenome)` pair, or once both sit inside a `MissionState`) is an
    implementation question for whoever writes the V0.2 validator, not decided here.

### D-103 — Production `SystemLimits` carries no built-in numeric defaults

- **Status:** Accepted · **Date:** 2026-09-18 · **Decided by:** human owner
- **Source:** D-046, D-009 rider 5; handoff §67; CLAUDE.md §7
- **Context:** D-046 asked whether the two handoff-example numbers (`latency_budget_ms: 600000`,
  `Maximum tokens: 10,000`) should seed provisional V0.2 values. EXPLORE established that the
  validation **mechanism** (the comparison logic; `effective = min(system, contract)`; reject-not-
  clamp) is pure logic, buildable and testable without any real ceiling existing, and that the two
  handoff numbers carry no authority as defaults — both are stated as illustrative examples, never
  as defaults, and D-009 rider 5 already says any other value "would be invention presented as
  engineering."
- **Decision:**
  1. **The numeric examples in the handoff are not production defaults.**
  2. V0.2 validation mechanisms must **accept explicitly supplied system-limit values** — no ambient
     or implicit configuration.
  3. **Production `SystemLimits` has no built-in numeric defaults.** Every field is required at
     construction.
  4. **Tests may use explicitly labelled fixture values.**
  5. **The handoff's illustrative numbers are not copied into shipped defaults.**
  6. **Actual provisional values remain governed by D-046** and must be explicitly provided or
     configured when needed.
- **Confirmed not in contradiction with D-046 or D-009:** D-009 rider 5 permissively says bound
  values "can be defined" at V0.2 — it does not require it. This decision takes the stricter,
  more conservative path (ship with zero built-in defaults) rather than the permitted-but-not-
  mandated one, which strengthens rather than weakens §67/CLAUDE.md §7's anti-fabrication rule.
  D-046's own scope — the actual numbers for all seven bound dimensions — is **entirely unchanged**.
- **Consequences:**
  - V0.2's resource-validation and graph-complexity-limits mechanisms are fully buildable and
    testable now, against test-only injected values, without D-046 resolving.
  - **D-046's own "Needs" text is narrowed by this decision** — it called for "provisional values at
    V0.2 ... explicitly marked arbitrary until measured"; this decision goes further and requires
    **no built-in default at all**, provisional or otherwise. Annotated on D-046's own entry.
  - A caller that does not explicitly supply `SystemLimits` values simply cannot construct one — this
    is a deliberate consequence, not an oversight to fix later.

### D-104 — `max_depth` counts nodes: a single-node plan has depth 1

- **Status:** Accepted · **Date:** 2026-09-19 · **Decided by:** human owner
- **Source:** V0.2 EXPLORE finding G1; refines D-050; handoff §14
- **Context:** D-050 defines `max_depth` as the **longest path** of the plan DAG but does not say
  whether a path's length is counted in nodes or in edges. The two differ by exactly one for every
  non-empty plan, and the difference changes which plans a given `max_depth` accepts or rejects.
  Left unstated, an implementation would pick one silently.
- **Decision:**
  1. `max_depth` is the number of **nodes** on the longest dependency path.
  2. A single-node plan has depth **1**. An empty plan has depth **0** (see D-106).
  3. A plan is within the limit when `depth <= max_depth`; `depth == max_depth` passes and
     `depth == max_depth + 1` is rejected.
- **Rationale:** "depth" as a budget on how many sequential steps a plan may chain is naturally a
  count of steps. Counting nodes also makes `max_depth` and `max_nodes` directly comparable — a
  strictly sequential plan of N steps has both `depth == N` and `node count == N` — and makes the
  smallest legal non-empty plan depth 1 rather than 0.
- **Consequences:**
  - D-050's definition is unchanged; this only fixes its unit. D-050 carries a pointer here.
  - **D-046** (actual numbers) must set `max_depth` values in nodes.
  - Implemented in `eidos.validation` (V0.2) as `longest chain in nodes`.

### D-105 — V0.2 checks only declared `max_agent_calls`; other budgets are contract-vs-ceiling only

- **Status:** Accepted · **Date:** 2026-09-19 · **Decided by:** human owner
- **Source:** V0.2 EXPLORE finding G2; D-009, D-042, D-043, D-065, D-103; handoff §14
- **Context:** The six mission budgets in `ReliabilityContract` (D-042) are `max_retries`,
  `max_replans`, `max_agent_calls`, `max_tool_calls`, `max_execution_time` and `max_tokens`. A static
  plan can reveal how many agent steps it *declares*, but nothing in it reveals how many retries,
  replans, tool calls, milliseconds or tokens its execution will consume. Treating a declared count
  as a prediction of actual consumption is the ambiguity **D-043** already tracks for V0.3.
- **Decision:**
  1. The **only** budget V0.2 checks against plan *structure* is **declared `max_agent_calls`**: the
     number of `agent`-kind steps in the plan must not exceed the effective limit,
     `min(system ceiling, contract value)`, where an omitted contract value (D-065) means the system
     ceiling alone.
  2. Retries, replans, tool calls, execution time and tokens are **not inferred from plan
     structure**. In V0.2 they are checked **only** as **contract-vs-system-ceiling**: the
     contract's value, if present, must not exceed the system ceiling. Violations **reject**; the
     value is never clamped (D-009).
  3. Violation messages for the agent-call check say **"declared"** so they are not mistaken for a
     statement about actual invocations.
- **Rationale:** it is the largest check that is fully determined by the plan alone, and it
  introduces no runtime semantics. Everything beyond it would be guesswork presented as validation.
- **Consequences:**
  - Reconciling declared counts with actual execution counters remains **D-043 (V0.3, Open)**. This
    decision does not resolve it and does not pre-empt it.
  - No runtime retry / replan / tool-call / time / token accounting is introduced.

### D-106 — Empty plans are legal in V0.2

- **Status:** Accepted · **Date:** 2026-09-19 · **Decided by:** human owner
- **Source:** V0.2 EXPLORE finding G3; V0.1 `Plan` contract (D-092/D-093)
- **Context:** The V0.1 `Plan` contract accepts `steps=()`. Whether the V0.2 pipeline should
  additionally *reject* an empty plan (nothing to execute) was not stated anywhere.
- **Decision:** an empty plan **passes** V0.2 validation. Every stage handles it as a vacuous pass:
  no cycles, no agent steps to bind to a capability, `node count = 0`, `depth = 0`, `width = 0`.
- **Rationale:** rejecting it would add a rule nothing in the specification or the contracts asks
  for. Whether an empty plan is *useful* is a planning or runtime concern, not a validity one.
- **Consequences:** if the human owner later wants empty plans rejected, that is a new, explicit rule
  and a new decision.

### D-107 — Plan ingress is JSON text; V0.1 gains two typed `ValueError` subclasses

- **Status:** Accepted · **Date:** 2026-09-19 · **Decided by:** human owner
- **Source:** V0.2 EXPLORE design choice A; invariants 3, 4, 5; `eidos.contracts.plan`
- **Context:** the LLM emits a Plan DSL **document** (invariant 3), so the untrusted ingress to the
  validator is **JSON text**, parsed with `Plan.model_validate_json`. The `Plan` contract already
  enforces duplicate-`step_id` and unknown-`depends_on` failures inside two model validators, both
  raising a bare `ValueError`. Pydantic wraps those, so a caller cannot tell a dependency failure
  from any other value error except by matching message strings — which is fragile.
- **Decision:**
  1. The untrusted ingress to V0.2 validation is **JSON text**, exposed as
     `validate_plan_json(text, state, limits)`. A second entry point,
     `validate_plan(plan, state, limits)`, accepts an already-constructed `Plan`.
  2. Two small, typed `ValueError` subclasses are added to `eidos.contracts.plan`, one for
     duplicate-`step_id` and one for unknown-dependency failures. The existing checks raise them
     instead of bare `ValueError`.
  3. **Existing behaviour and message text are preserved exactly.** They are still `ValueError`s,
     still raised from the same validators under the same conditions.
- **Rationale:** a typed failure is the smallest change that makes the failure classes
  distinguishable without parsing messages. Subclassing `ValueError` keeps every existing
  `pytest.raises(ValueError)` and pydantic's error wrapping working unchanged.
- **Consequences:**
  - The V0.1 `test_self_dependency_is_not_rejected_in_v01` remains valid: V0.1 still does not reject
    cycles. The V0.2 cycle stage does.
  - Both exception types are V0.1-layer additions; the V0.1 155-test baseline must stay green.

### D-108 — `EidosModel` is exported from `eidos.contracts`

- **Status:** Accepted · **Date:** 2026-09-19 · **Decided by:** human owner
- **Source:** V0.2 EXPLORE design choice B; CLAUDE.md §8
- **Context:** V0.2's report and limit models are Pydantic contracts and should carry the same
  strict, frozen, `extra="forbid"` configuration as every V0.1 contract (CLAUDE.md §8: typed,
  validated). `EidosModel` lives in the private `eidos.contracts._base` and is not part of the
  package's public surface, so `eidos.validation` would otherwise reach into a private module.
- **Decision:** export `EidosModel` from `eidos.contracts` (added to `__all__`). This is a purely
  additive API change.
- **Consequences:** `eidos.validation` depends only on `eidos.contracts`'s public surface.
  `eidos.contracts` still depends on nothing else inside `eidos`.

### D-109 — Shared test factories live in a uniquely named shared module

- **Status:** Accepted · **Date:** 2026-09-19 · **Decided by:** human owner
- **Source:** V0.2 EXPLORE design choice C; CLAUDE.md §6
- **Context:** V0.1's factories live in `tests/unit/contracts/conftest.py` and are imported with
  `from conftest import ...`. That resolves only while exactly one non-package `conftest.py`
  directory is on the import path. V0.2 adds a second test directory needing the same factories;
  with two, resolution depends on collection order (verified: the reverse order fails at
  collection).
- **Decision:** move the shared factories into one **uniquely named** shared test module and
  configure pytest (`pythonpath`) so tests import it directly, independent of `conftest.py`
  resolution. Done as its **own commit**, with the **155-test V0.1 baseline unchanged**.
- **Consequences:** test-infrastructure only. No test is weakened, deleted or skipped; no runtime
  dependency is added; `conftest.py` files remain free to hold fixtures.

### D-110 — The POLICY stage exists in the V0.2 pipeline and reports `NOT_APPLICABLE`

- **Status:** Accepted · **Date:** 2026-09-19 · **Decided by:** human owner
- **Source:** V0.2 EXPLORE design choice D; invariants 5 and 14; D-060, D-061, D-074
- **Context:** invariant 5 fixes the validation order (`schema -> dependencies -> cycles ->
  capabilities -> policy -> resources -> complexity limits -> compile`), and invariant 14 says
  governance is deterministic and enforced in code. But what a policy check would *evaluate* — the
  autonomy-level semantics — is blocked on **D-060/D-061/D-074** (Open). Inventing policy rules, or
  a mechanism for injecting them, to fill the stage would be a silent decision.
- **Decision:** the POLICY stage is present in the pipeline, in its invariant-5 position, and
  reports **`NOT_APPLICABLE`**. No policy semantics are invented and **no policy-injection
  mechanism** is built.
- **Rationale:** it keeps the pipeline's shape and ordering faithful to invariant 5 without
  fabricating governance that the owner has not decided.
- **Consequences:**
  - `NOT_APPLICABLE` is an honest, distinct outcome — not `PASSED`. A report must not present the
    policy stage as having approved the plan.
  - The stage is filled only by a later decision that resolves the autonomy questions.

### D-112 — V0.3 compiles only `agent` and `VERIFY`

- **Status:** Accepted · **Date:** 2026-09-19 · **Decided by:** human owner
- **Source:** handoff §13, §50; D-012, D-047, D-049, D-050; V0.3 exploration (A1)
- **Context:** §50's V0.3 mapping lists `SEQUENTIAL`, `PARALLEL`, `ROUTE`, `VERIFY`, `RETRY` and
  `REPLAN`, and omits `HUMAN_APPROVAL` and `TERMINATE`. `SEQUENTIAL` and `PARALLEL` are not kinds
  (D-050): they are edges. `ROUTE`, `RETRY`, `REPLAN` and `TERMINATE` are conditional, and D-012 (the
  predicate language) is Open. D-047 says a V0.1 plan containing a conditional kind is structurally
  valid but "must not silently become executable at V0.3 without D-012". V0.2 accepts such plans by
  design, so the compile boundary is where they must be stopped.
- **Decision:**
  1. The V0.3 compiler compiles exactly two step kinds: **`agent`** and **`VERIFY`**.
  2. It **rejects at compile time**: **`ROUTE`**, **`RETRY`**, **`REPLAN`**, **`TERMINATE`** and
     **`HUMAN_APPROVAL`**. A rejected kind yields a typed compile failure — no node is emitted, no
     placeholder behaviour exists, and a plan containing one is never partially compiled.
  3. **D-012 remains Open.** None of the five kinds gains executable semantics in V0.3.
  4. These kinds **must never silently become executable.** Supporting any of them later requires its
     own decision and an additive change.
- **Rationale:** rejection is the honest behaviour for a kind whose semantics do not exist. A
  placeholder node would be behaviour nobody decided, and would become accidental architecture.
- **Consequences:**
  - This **narrows §50's V0.3 mapping list**. A plan V0.2 accepted can be compile-rejected; that is
    expected, not a validation defect. V0.2 is unchanged.
  - The compiled form need represent only the two supported kinds. Its exact shape is an
    implementation matter.
  - D-055 is **not** answered by this entry — see D-124.
  - Semantics for the five kinds are deferred (D-127).

### D-113 — MissionState never enters LangGraph state; V0.3 writes nothing to MissionState

- **Status:** Accepted · **Date:** 2026-09-19 · **Decided by:** human owner · **Resolves D-040**
- **Source:** handoff §9, §11; invariants 1 and 2; D-010a, D-040; V0.3 exploration (A2)
- **Context:** §9 makes MissionState the only authoritative global state; §11 makes LangGraph the
  execution runtime with its own execution state. D-010a set the principle (per-node runtime state does
  not enter MissionState merely because LangGraph holds it) and deferred the concrete division to V0.3.
- **Decision:**
  1. **MissionState never enters LangGraph state.**
  2. LangGraph state contains **only** `outcomes`: a mapping from `step_id` to node outcome.
  3. A run receives a **frozen `ExecutionContext`** containing **only the required immutable run
     snapshot**. It is not part of LangGraph state and is never mutated. Its exact field set is an
     implementation matter, minimal by rule: a snapshot, not a view onto live state.
  4. **V0.3 writes nothing to MissionState** — not status, counters, plans, the active plan or agent
     tasks. Only the reducer mutates MissionState (invariant 2), and it arrives in V0.5.
  5. Results leave the run **by value**. How they reach MissionState is the reducer's concern, not V0.3's.
- **Rationale:** it keeps LangGraph subordinate — a scratch space for one run, not a second source of
  truth — which is the only reading under which invariant 1 and §11 are both true.
- **Consequences:**
  - **D-040 is resolved** and moved to Accepted. D-010b, D-039 and D-017 stay Open.
  - LangGraph's own checkpointing and interrupts are not used at V0.3 (D-127).
  - Because MissionState is not in the run, nothing about the run is authoritative until the reducer
    accepts it.
- **V0.4 (2026-09-20):** **D-139** adds the frozen `ReliabilityContract` to `ExecutionContext`. The principle here is unchanged:
  MissionState never enters runtime or backend state, and the context is a frozen, minimal, immutable snapshot.


### D-040 — The exact MissionState / LangGraph execution-state boundary

- **Status:** Accepted · **Date:** 2026-09-19 · **Decided by:** human owner · **Resolved by D-113**
  (originally Open, split out of D-010a and left Open by the owner)
- **Source:** handoff §9 vs §11
- **Original finding:** §9 asserts MissionState is the *only* authoritative global state; §11 assigns
  LangGraph management of *execution state*; §9's own diagram shows the reducer writing into
  "LangGraph checkpoint/state". Two state stores demonstrably exist. D-010a sets the **principle** —
  detailed per-node runtime execution state does not enter authoritative MissionState merely because
  LangGraph holds such state — but the specific split was left as inherited work at V0.3, when a
  runtime exists.
- **Resolution:** **D-113.** MissionState never enters LangGraph state; LangGraph state holds only
  `outcomes`; the run receives a frozen `ExecutionContext`; V0.3 writes nothing to MissionState.
- **Not resolved by this:** checkpoint contents, granularity and trigger (**D-010b**), the reducer
  signature (**D-039**) and persistence (**D-017**) all stay Open. V0.3 uses no LangGraph
  checkpointing or interrupts (D-127).

### D-114 — Compiler input is `(Plan, accepted PlanValidationReport)`; validation and compilation stay separate authorities

- **Status:** Accepted · **Date:** 2026-09-19 · **Decided by:** human owner
- **Source:** handoff §14; invariant 5; D-102, D-103, D-105, D-110; V0.3 exploration (A3)
- **Decision:**
  1. The compiler's input is a **`Plan` together with an accepted `PlanValidationReport`** (one whose
     `accepted` is true). Anything else is a typed compile failure.
  2. The compiler **defensively re-checks the structural properties it depends on** rather than
     trusting the report.
  3. **Validation and compilation remain separate authorities.** The compiler does not re-run or
     replace V0.2's stages (capabilities, resources, complexity, policy); V0.2 does not know what the
     compiler supports.
  4. Compile failures are a **separate typed family** from validation violations. A plan can be
     validation-accepted and compile-rejected (D-112).
- **Rationale:** a `PlanValidationReport` binds to a plan only by `plan_id`, not by content, so it is
  evidence rather than proof. The compiler's soundness depends on unique step ids, resolved
  dependencies and acyclicity; checking them is cheap, and a wrong assumption would fail at run time.
  Re-implementing the semantic stages instead would create two authorities that can drift apart.
- **Consequences:**
  - V0.1 and V0.2 are **not modified.**
  - The exact list of re-checked properties and the compile-failure codes are implementation matters.

### D-115 — Package boundary: `eidos.compiler`, `eidos.runtime`, `eidos.backends.langgraph`

- **Status:** Accepted · **Date:** 2026-09-19 · **Decided by:** human owner
- **Source:** invariant 9; handoff §11, §36, §50; docs/03 §11; CLAUDE.md §8; V0.3 exploration (A4)
- **Context:** docs/03's package map named `eidos.runtime` as "LangGraph execution of compiled plans",
  while invariant 9 (CLAUDE.md) says no model, vendor or SDK name appears in `contracts`, `planning`,
  `validation`, `compiler`, `runtime` or `state`.
- **Decision:**
  1. V0.3 adds three packages: **`eidos.compiler`**, **`eidos.runtime`**, **`eidos.backends.langgraph`**.
  2. **`eidos.compiler` and `eidos.runtime` — and every other core layer — must not import LangGraph.**
  3. **Only `eidos.backends.langgraph` may import LangGraph.**
  4. `eidos.runtime` is the backend-neutral execution layer; the backend package depends on it, never
     the reverse.
  5. **docs/03's package mapping is amended accordingly** (`eidos.runtime` is no longer described as
     LangGraph execution; `eidos.backends.langgraph` is added).
- **Rationale:** LangGraph is an execution backend, not the architectural authority (§11, §12). With
  the name confined to one adapter package, invariant 9 holds on its literal reading, so this decision
  does not have to choose what "SDK" means in that invariant.
- **Consequences:**
  - The packages are created when the V0.3 slices that fill them begin (CLAUDE.md §3), not now.
  - A static guard must enforce that only the backend package imports LangGraph.
  - **Not decided here:** whether `eidos.runtime` also ships a sequential reference executor. It was
    proposed in the V0.3 exploration but is not part of A1–A12; to be confirmed before the runtime
    slice.
- **Reference executor — resolved by D-128 (2026-09-19):** `eidos.runtime` ships a sequential reference executor, as the
  semantic oracle and conformance target for the LangGraph backend. The "not decided here" note above no
  longer applies.

### D-116 — LangGraph is an optional dependency extra, also included in `dev`

- **Status:** Accepted · **Date:** 2026-09-19 · **Decided by:** human owner
- **Source:** D-003; handoff §50, §76; V0.3 exploration (A5)
- **Decision:** LangGraph is declared as an **optional dependency extra** and is **also included in
  `dev`**. It is not a base dependency. **Core installation and core tests remain usable without
  importing LangGraph.**
- **Consequences:**
  - This is the milestone that **D-003** said would justify declaring it ("nothing else is declared
    until a milestone requires it"); D-003 is annotated, not reopened.
  - **No dependency is changed by this entry.** `pyproject.toml` changes in the slice that introduces
    the adapter. The extra's name and any version constraint are settled then, against what is actually
    installed.
  - LangGraph's transitive dependencies were reported by a secondary source and are unverified until
    it is installed.
- **Settled at V0.3 Step 4 (2026-09-20):** the extra is named `langgraph` and pins `langgraph>=1.2.11,<2` — the
  version the spike and conformance tests were verified against; `dev` includes it as `eidos[langgraph]`. The
  base `dependencies` still hold only `pydantic>=2`. Installed: LangGraph 1.2.11 (`Requires-Python >=3.10`,
  exercised on Python 3.12.10 only), with six direct requirements and a dependency closure of 38 distributions (measured with
  `importlib.metadata`; 32 beyond `langgraph` and the `pydantic` family EIDOS already needs), including
  `langchain-core`, `langsmith`, `httpx` and `websockets`. Consequences are recorded as **D-130** (ambient
  tracing) and in `progress.md`; this entry is not reopened.

### D-117 — V0.3 execution semantics: level-synchronous waves

- **Status:** Accepted · **Date:** 2026-09-19 · **Decided by:** human owner
- **Source:** handoff §11, §14, §32; D-050, D-104; V0.3 exploration (A6)
- **Context:** LangGraph runs parallel nodes in super-steps and its own documentation says updates
  from a parallel super-step "may not be ordered consistently". If EIDOS left the scheduling model to
  the backend, which nodes run before a halt would depend on the backend — for example `A→B` beside an
  independent `C` runs `A, B` under one-at-a-time scheduling but `A, C` under super-steps.
- **Decision:**
  1. Execution is **level-synchronous ("waves")**.
  2. A node's **level is the length of its longest predecessor chain, counted in nodes** (as D-104
     counts depth): a node with no predecessors is at level 1.
  3. **Within a level, nodes execute in ascending plan position.**
  4. A node is **ready** when **all its predecessors are settled**.
  5. A node **executes only when every predecessor is `SUCCEEDED`**. Otherwise it becomes
     **`SKIPPED` without dispatch**.
  6. **Independent branches continue after a failure.** Only descendants of a non-`SUCCEEDED` node are
     skipped.
  7. **A halt takes effect after the current level.**
  8. **No timing or concurrency assumption is part of correctness.**
- **Rationale:** with these rules the outcome of a run is a function of the node results alone, so a
  backend may run a level's nodes concurrently or one by one without changing the result. Continuing
  independent branches (rather than fail-fast) is what makes the set of executed nodes independent of
  timing.
- **Consequences:**
  - Level and plan position are properties of the compiled form and the run, not of LangGraph.
  - A backend must preserve the level barrier; it may not dispatch a node before its level.
  - Wasted work on independent branches after a failure is bounded by plan size, which V0.2 bounds.
  - How a halt is requested (the admission hook) is D-122; its request shape is pinned at implementation.

### D-118 — Node statuses and run outcomes

- **Status:** Accepted · **Date:** 2026-09-19 · **Decided by:** human owner
- **Source:** invariant 12; D-117; V0.3 exploration (A7)
- **Decision:**
  1. **Node statuses** are exactly: `SUCCEEDED`, `FAILED`, `NO_RESULT`, `VERIFICATION_FAILED`,
     `VERIFICATION_INCONCLUSIVE`, `SKIPPED`, `NOT_REACHED`.
  2. **Run outcomes** are exactly: `FINISHED`, `FAILED`, `HALTED`.
  3. **`FINISHED` is not itself equivalent to verified success.** Verification is separate (D-121).
  4. **`HALTED` takes precedence** over the other outcomes.
- **Intended meaning (pinned by tests at implementation):** `FAILED` — the node's execution failed;
  `NO_RESULT` — the node ran and produced no usable result; `SKIPPED` — settled without dispatch
  because a predecessor was not `SUCCEEDED` (D-117); `NOT_REACHED` — never settled because the run
  halted, so it can run in a later run (D-120). Run-level: `FINISHED` — not halted and every node
  `SUCCEEDED`; `FAILED` — not halted and not every node `SUCCEEDED`; `HALTED` — the run halted.
- **Consequences:**
  - An empty plan (legal, D-106) finishes vacuously; that behaviour is pinned at implementation.
  - "Usable" means the execution port reported a produced result. Whether the result is *good* is
    verification's question, not execution's (invariant 12).
  - How run outcomes map to `MissionStatus`, including D-059, is not decided here.

### D-119 — No automatic retry and no in-run replan in V0.3

- **Status:** Accepted · **Date:** 2026-09-19 · **Decided by:** human owner
- **Source:** handoff §15, §32; invariants 6 and 7; D-043, D-082; V0.3 exploration (A8)
- **Decision:**
  1. **V0.3 performs no automatic retry** and **no in-run replan.**
  2. **A retry is not a second invocation of the same node in the same run.** Within one run every
     node is dispatched at most once.
  3. **A replan is a caller-supplied new `Plan`**, which is **separately validated, compiled and
     executed.** The runtime never patches, replaces or re-plans a live plan (invariant 6).
- **Rationale:** retry needs a failure classification (§32's "classify" is unspecified), accounting that
  only the reducer can record (V0.5), and reconciliation of D-043. A run in which each node is
  dispatched at most once is bounded by construction, by the limits V0.2 already enforces.
- **Consequences:**
  - Plan lineage is carried by the existing V0.1 fields (`version`, `parent_plan_id`, `replan_reason`);
    no contract changes.
  - Version monotonicity and lineage validation across a mission's plans remain the V0.5 reducer's
    concern (D-082).
  - **D-043 stays Open** and is dormant at V0.3: no runtime counting is performed (D-127).
  - The relationship between plan-level `RETRY` and a future runtime retry policy is **D-125 (Open).**

### D-120 — Resume mechanism: prior `SUCCEEDED` outcomes

- **Status:** Accepted · **Date:** 2026-09-19 · **Decided by:** human owner
- **Source:** handoff §32; D-010b, D-017, D-085, D-113; V0.3 exploration (A9)
- **Decision:**
  1. **A later run may receive prior `SUCCEEDED` outcomes.**
  2. **Settled `SUCCEEDED` nodes are not redispatched.**
  3. **Invalid prior state produces a typed `RunRejection`.** It is never silently adapted — not
     dropped, reordered, repaired or partly honoured.
- **Rationale:** pause and resume must be possible without designing A2A or persistence early. Resume
  as re-running over recorded outcomes needs no LangGraph checkpointer or interrupt (D-010b and D-017
  are Open), and avoids the documented behaviour of LangGraph resumption re-running a node from its
  beginning, which would re-invoke agents.
- **Consequences:**
  - A resumed run belongs to the same execution (D-085).
  - What counts as invalid prior state (for example an outcome for an unknown step, or a `SUCCEEDED`
    outcome whose predecessor is not `SUCCEEDED`) is pinned by tests at implementation.
  - Whether and how a re-dispatch in a later run is *accounted* (`retries_used`) is **not decided here**;
    runtime accounting is deferred (D-127).
  - Nothing is persisted at V0.3; the source of prior outcomes is the caller.

### D-121 — Verification interface: `PASS | FAIL | INCONCLUSIVE` plus a reason

- **Status:** Accepted · **Date:** 2026-09-19 · **Decided by:** human owner
- **Source:** handoff §18, §19, §31; invariants 12 and 13; D-015; V0.3 exploration (A10)
- **Decision:**
  1. The `Verifier` returns **`PASS`**, **`FAIL`** or **`INCONCLUSIVE`**, **plus a reason.**
  2. **No scalar quality or confidence score is introduced.**
  3. A `VERIFY` node maps the verdict to its status: **`PASS` → `SUCCEEDED`**, **`FAIL` →
     `VERIFICATION_FAILED`**, **`INCONCLUSIVE` → `VERIFICATION_INCONCLUSIVE`.**
  4. **Verification remains separate from execution completion.**
- **Rationale:** it lets V0.3 carry a verification result without choosing how one is computed. `INCONCLUSIVE`
  exists so that "cannot establish success" is never forced into pass or fail (invariant 13).
- **Consequences:**
  - **D-015 stays Open.** This fixes only the result shape that crosses the port; it chooses neither a
    confidence function nor a pass/fail rule set for how a verifier decides.
  - `INCONCLUSIVE` is never treated as a pass.
  - Nothing here decides how verification results become mission status or a final result (D-059,
    D-041 stay Open).
  - A scalar or evidence field could be added later as an additive change.

### D-122 — V0.3 execution ports are synchronous; the AdmissionGuard is explicit and required; D-018 stays narrow

- **Status:** Accepted · **Date:** 2026-09-19 · **Decided by:** human owner
- **Source:** D-018, D-103; handoff §36, §50; invariant 7; V0.3 exploration (A11)
- **Decision:**
  1. **V0.3's execution ports are synchronous.** Future async and A2A interfaces stay deferred.
  2. **`AdmissionGuard` is an explicit, required input** to a run. There is **no ambient configuration
     and no default**, in the spirit of D-103.
  3. **D-018 is scoped narrowly to the execution-side port interface** — the interface through which the
     runtime asks for work to be performed, a verification to be judged and a halt to be admitted or
     refused. The model-provider abstraction boundary is **untouched**, and D-018 stays Open.
- **Rationale:** V0.3 uses mock agents (§50), so a synchronous port is the smallest thing that works.
  Requiring the guard means a bounded-execution hook cannot be omitted by accident.
- **Consequences:**
  - The `AdmissionGuard` is the hook through which a halt is requested (D-117). Its request shape and
    purity requirements are pinned at implementation.
  - No production guard ships: budget, time and token accounting are deferred (D-127); V0.3 tests
    supply their own guards.
  - The execution ports are owned by `eidos.runtime` (D-115); implementations depend on them, never the
    reverse.
- **V0.4 (2026-09-20):** D-018 is now **resolved by D-135**, which places the model-provider boundary in `eidos.agents` and the
  adapters in `eidos.providers`. This entry's execution-side scope is unchanged.


### D-123 — V0.3 emits no `MissionEvent` and mutates no `MissionState`; invariant 15 is not exercised

- **Status:** Accepted · **Date:** 2026-09-19 · **Decided by:** human owner
- **Source:** invariants 2 and 15; handoff §33, §73; D-011, D-067, D-075, D-076, D-090; V0.3 exploration (A12)
- **Context:** invariant 15 requires every meaningful execution step to emit a structured event so a
  completed mission is replayable without re-running agents. The current event vocabulary cannot
  represent a local node's lifecycle: D-090 fixed exactly thirteen types, the only ones describing task
  execution are the two `A2A_TASK_*` types (remote tasks), and `MissionEvent` has no payload (D-067).
- **Decision:**
  1. **V0.3 emits no `MissionEvent` and mutates no `MissionState`.**
  2. **Invariant 15 is explicitly not exercised in V0.3**, because the current event vocabulary cannot
     represent local node lifecycle events.
- **Consequences:**
  - No V0.3 test verifies replayability from events, and no V0.3 document may claim it.
  - A run result is **not** an event log. "An event that is not recorded is not replayable" (docs/06)
    remains an obligation on later milestones.
  - The gap itself is recorded as **D-126 (Open).**
- **V0.5 (2026-09-21):** the runtime still emits no `MissionEvent` and writes no `MissionState`, so this entry stays accurate for it. V0.5 produces events through recording adapters outside the
  runtime (D-158); a run result is still not an event log.


### D-124 — V0.3 treatment of `VERIFY` and `HUMAN_APPROVAL` (a V0.3 implementation decision; D-055 stays Open)

- **Status:** Accepted · **Date:** 2026-09-19 · **Decided by:** human owner
- **Source:** D-049, D-055, D-112; V0.3 exploration
- **Decision:** for **V0.3 only**:
  1. **`VERIFY` is treated as a control step** and compiles to a **`VerifyNode`**.
  2. **`HUMAN_APPROVAL` is unsupported in V0.3** and is rejected at compile time (D-112).
- **This does not answer D-055.** Whether `VERIFY` and `HUMAN_APPROVAL` are work steps rather than
  control-flow steps, and what capability a human-approval step would request, **remain Open** for
  future evolution. This entry records how V0.3 is implemented, not how the kinds are classified.
- **Consequences:**
  - This is consistent with the conservative position D-049 already takes (both remain control-flow
    kinds meanwhile).
  - If D-055 is later resolved differently, `VERIFY`'s compile mapping must be revisited. That cost is
    accepted.
  - **D-058 and D-061 are unaffected:** no `HUMAN_APPROVAL` step compiles and no pause-by-approval
    exists at V0.3.

### D-128 — The sequential reference executor is part of V0.3

- **Status:** Accepted · **Date:** 2026-09-19 · **Decided by:** human owner
- **Source:** D-115 ("not decided here"), D-117, D-118; V0.3 Step 3 instruction
- **Context:** D-115 fixed the package boundary but recorded that whether `eidos.runtime` also ships a
  sequential reference executor was **not decided** — it had been proposed in the V0.3 exploration and was
  not part of A1–A12, and was "to be confirmed before the runtime slice."
- **Decision:**
  1. **`eidos.runtime` ships a sequential reference executor.**
  2. Its purpose is to **define EIDOS's backend-neutral execution semantics**, to be a **deterministic
     reference and oracle**, to be **independently testable without LangGraph**, and to be the
     **conformance target** for `eidos.backends.langgraph`.
  3. It is **not the final production concurrency backend**, and it **must not become coupled to
     LangGraph**.
- **Rationale:** D-117 and D-118 say what a run means; without an executable statement of them, a backend
  could only be tested against itself. A small dependency-free executor turns those decisions into something
  a second implementation can be compared with.
- **Consequences:**
  - **D-115's open note is resolved** and annotated.
  - For the same compiled plan, context, prior outcomes and deterministic ports, the LangGraph backend must
    produce the same `RunResult` (or `RunRejection`) as the reference executor. A disagreement is a defect in
    the backend, unless D-117 or D-118 are amended by a new decision.
  - The reference executor imports no LangGraph and no backend package; only tests bring the two together.
  - The run preconditions (context and prior-state checks) live in their own module so that every backend
    applies exactly the same ones.

### D-130 — LangGraph tracing stays off in V0.3; there is no opt-in

- **Status:** Accepted · **Date:** 2026-09-20 · **Decided by:** human owner
- **Source:** V0.3 Step 4 spike (S10); D-103, D-113, D-122, D-123; handoff §33, §76
- **Context:** LangGraph depends on LangSmith. With `LANGSMITH_TRACING` or `LANGCHAIN_TRACING_V2` set in the
  **environment**, an unmodified LangGraph run POSTs every node's inputs and outputs to
  `api.smith.langchain.com` (spike S10 observes the attempt). For EIDOS those inputs and outputs are a
  mission's outcomes, artifacts and failure reasons. The variables are **ambient configuration**, exactly what
  D-103 and D-122 refuse for limits and the guard, and the handoff names OpenTelemetry for observability (§76),
  never LangSmith. Nothing in the handoff decided whether a run's data may leave the process, or through what.
- **Decision:**
  1. **LangSmith / LangChain tracing stays OFF in V0.3.**
  2. **There is no opt-in** in V0.3: no flag, parameter, environment variable or configuration switches it on.
- **Implemented as:** `eidos.backends.langgraph` runs every invocation inside `tracing_context(enabled=False)`,
  which switches tracing off in LangGraph's worker threads too. Tests run with the tracing variables set before
  the process starts and the network refused, and prove **no attempt is made**
  (`tests/integration/langgraph`); a static guard requires the call and permits `langsmith` to be imported for
  that purpose only.
- **Consequences:**
  - The Step 4 implementation is the decision as written; no code change follows from accepting it.
  - **Not decided here:** any later export of run data. Telemetry proper is V0.9 (§50, §33), and an exporter,
    if one is ever wanted, is a separate decision that names what may leave the process and where it goes.
    The guard and tests above are what such a decision would have to amend.
### D-131 — V0.4 scope: the baseline chain and the single-pass runner

- **Status:** Accepted · **Date:** 2026-09-20 · **Decided by:** human owner
- **Source:** handoff §49, §50 (V0.4), §68; D-119, D-127, CLAUDE.md §3; V0.4 exploration (Q1, Q2)
- **Context:** §50 says only "Add Research, Analysis, Verification. Make the baseline workflow work end-to-end."
  "Baseline workflow" appears nowhere else in the handoff. §49's chain (task, genome, candidate strategies,
  validation, execution, evaluation, history) contains stages that belong to later milestones, and D-127 leaves
  the planner and the driver loop unassigned.
- **Decision:**
  1. **V0.4's baseline workflow is a fixed, hand-authored plan — Research, then Analysis, then a `VERIFY`
     node — over a supplied `TaskGenome`, driven once, single-pass:** validate (V0.2), compile, execute on the
     LangGraph backend, with the three agents and a real local model behind the model seam (D-135), and the typed
     run result reported.
  2. **The plan is supplied to the runner; nothing generates plans.** No planner, no candidate strategies, no
     LLM-emitted Plan DSL (invariant 3 is untouched) and no system-driven replan: a replan remains a caller-supplied
     new plan (D-119).
  3. **Out of V0.4:** planner and candidate strategies, evaluation, execution history and events (V0.5), A2A (V0.6),
     MCP (V0.7), RAG (V0.8).
  4. **The runner is one small module:** one pass, **no CLI and no API** (§53's API is later). Its name and placement
     are settled when it is created and recorded in `docs/03_architecture.md`.
  5. **Exactly three logical agents** — Research, Analysis, Verification — per CLAUDE.md §3.
- **Rationale:** it is the smallest chain that exercises every V0.1 to V0.3 authority with real agents, and it is what
  §68's "fixed multi-agent" version describes. Generating plans needs a planner, which is a fourth LLM role, and
  D-127 has not assigned it.
- **Consequences:**
  - D-127's "a planner and the mission driver loop" row is **split**: the single-pass runner is in V0.4; the planner and
    a replanning loop stay unassigned. **D-020 stays Open.**
  - The baseline plan's per-step capabilities depend on **D-141** (since resolved by D-144).
  - The runner requires an explicit `AdmissionGuard` (D-140).

### D-132 — V0.4 capability vocabulary: the five capabilities of handoff §43 (V0.4 only)

- **Status:** Accepted · **Date:** 2026-09-20 · **Decided by:** human owner · **Resolves D-006**
- **Source:** handoff §6, §7, §16, §43; D-006, D-007, D-080, D-102; V0.4 exploration (Q3)
- **Decision:**
  1. **For V0.4 only, five capability IDs exist**, exactly as listed under "Required capabilities" in §43:
     **`Architecture`, `Security`, `Cost`, `Research`, `Verification`.**
  2. **Matching stays exact-string** (D-102, D-080).
  3. **This is scoped to V0.4 and is not a global vocabulary. D-007 stays Open:** nothing here decides hierarchy,
     similarity, ownership or a canonical cross-mission list.
  4. **D-006 is resolved for V0.4:** the capability set is five, not three; the agent set stays three logical
     agents (D-131).
- **Consequences:**
  - **V0.2 is unchanged.** Its capability stage still checks that a step's capability is in the mission's own
    `required_capabilities` (D-102).
  - §43 lists these five under "Required capabilities", while its strategy diagram uses Research, Security,
    Architecture, Analysis and Verification — Analysis in place of Cost. The ruling follows the "Required
    capabilities" list. How the diagram's Analysis step is expressed is **D-141** (since resolved by D-144).
  - Which agent serves which capability, the spelling of the names beyond "as printed", and what `Verification`
    binds to are **D-141** (since resolved by D-144).
- **Spelling settled (2026-09-20):** **D-144** fixes the V0.4 spellings as lowercase — `architecture`, `security`, `cost`, `research`,
  `verification` — superseding the capitalised forms above **for spelling only**. The set is unchanged and D-007 stays Open.


### D-133 — `VERIFY` is bound to the `Verifier` port by node kind, not by capability

- **Status:** Accepted · **Date:** 2026-09-20 · **Decided by:** human owner · **D-055 stays Open**
- **Source:** handoff §7, §31; D-049, D-055, D-121, D-124; V0.4 exploration (Q4)
- **Decision:**
  1. A `VERIFY` node is executed through the **`Verifier` port** (D-121, D-124) and is **bound by node kind, not by
     capability.**
  2. `VERIFY` carries no capability (D-049, D-124 unchanged).
  3. **This does not answer D-055.** It records how V0.4 binds `VERIFY`, not whether `VERIFY` is a work step.
- **Consequences:**
  - The Verification Agent implements the `Verifier` port (D-138). Invariant 11 holds for work steps (capabilities)
    and, for `VERIFY`, binding happens by kind when the run is constructed.
  - If D-055 is later resolved differently, this binding is revisited, at the cost D-124 already accepted.
  - What the `Verification` capability ID (D-132) binds to, if an `agent` step requested it, is **D-141** (since resolved by D-144).

### D-134 — Capability registry, binding and unbound capabilities (V0.4)

- **Status:** Accepted · **Date:** 2026-09-20 · **Decided by:** human owner
- **Source:** handoff §7; D-053, D-080, D-102, D-114; invariant 11; V0.4 exploration (Q5)
- **Decision:**
  1. **`eidos.capabilities`** holds the V0.4 capability set (D-132) and a **registry that resolves a capability to an
     agent**, deterministically and by exact string.
  2. **An agent descriptor carries `agent_id`, a version and its capabilities — nothing else.** `agent_id` is
     a fixed, UUID-backed value supplied at registration (D-053): no randomness. The rest of §7's metadata
     (supported inputs and outputs, permissions, tools, historical latency, success and verification rate,
     availability) is **not built**: the statistics belong to telemetry (V0.9), the rest to V0.6, V0.7 and V1.2.
  3. **An unbound capability is a typed pre-run rejection**, produced when the run is bound and before anything is
     dispatched. **V0.2 validation is unchanged:** it does not know which agents exist (D-102).
- **Consequences:**
  - A plan can be validation-accepted and compile-accepted and still be refused at binding. Binding is a third
    authority with its own typed failure family, separate from `ViolationCode` and `CompileFailureCode`, for the
    reason D-114 gives for separating validation and compilation. Its shape is pinned at implementation.
  - The registry is deterministic and does no I/O.

### D-135 — The model seam: `eidos.agents` owns `ModelPort`, providers implement it (resolves D-018)

- **Status:** Accepted · **Date:** 2026-09-20 · **Decided by:** human owner · **Resolves D-018**
- **Source:** handoff §36, §51, §77; invariant 9; D-018, D-103, D-122; V0.4 exploration (Q6)
- **Decision:**
  1. **`eidos.agents` owns a synchronous `ModelPort` protocol** and its typed request, response and failure types.
     Only agents call it; only a provider adapter implements it.
  2. **Every provider adapter lives in `eidos.providers`**, the only place a vendor, model or SDK name may appear.
  3. **Configuration is explicit; there are no silent defaults.** The model identifier, the generation parameters
     (temperature, seed, maximum output tokens) and the timeout are **required inputs** (D-103's spirit). Nothing is
     ambient.
  4. **Provider outages, timeouts and malformed responses become typed failures.** They are never raised out of a
     run and never read as success.
  5. **Facts a provider measures** (token counts, elapsed time) are returned as measured facts and labelled as such
     (invariant 17). They are never model-asserted.
- **Consequences:**
  - **D-018 is resolved** and moved to Accepted. D-122's narrow, execution-side scope is unchanged.
  - Field-level shape is pinned at implementation.
  - **Ports must be thread-safe:** the LangGraph backend runs a level's nodes on worker threads, and a single local GPU
    may serialise concurrent calls. The synchronous port has no runtime time budget (D-127), so the client-side
    timeout is the only bound on a hung call; its value is the caller's (D-046 stays Open).
  - Static guards extend: `eidos.agents` and `eidos.capabilities` stay vendor-free; only `eidos.providers` may name a
    vendor; core layers import none of these (CLAUDE.md §8). Invariant 9 is verified by substituting one
    implementation for another without touching core layers (docs/12).
  - Model outputs must be capturable so V0.5 can record them for replay (D-076); nothing is recorded at V0.4.

### D-136 — The local model provider: dependency, environment and test gating

- **Status:** Accepted · **Date:** 2026-09-20 · **Decided by:** human owner
- **Source:** handoff §51, §76, §77; CLAUDE.md §3, §6, §7; D-116, D-135; V0.4 exploration (Q7, Q8, Q9)
- **Decision:**
  1. **No new dependency.** The provider adapter uses the standard library's HTTP client. No vendor SDK and no new
     extra at V0.4.
  2. **The runtime environment is the owner's action.** Installing the local model runtime and choosing and pulling a
     model are done by the owner, never by Claude Code. The model used is recorded when it is first used.
  3. **Test gating.** The default suite uses a scripted fake model and stays offline and deterministic (a fake at the
     port, and a local fake HTTP server for the adapter). **Real-model tests are an explicit opt-in** — a marker
     excluded from the default run — and are **never a silent skip** (CLAUDE.md §6). Any latency, throughput or
     quality figure comes only from an actual recorded run (CLAUDE.md §7).
- **Recorded fact (measured during the V0.4 exploration, on the owner's machine):** no local model runtime is installed;
  the GPU has 4 GB of memory and the machine 15.7 GB of RAM. Nothing about model speed or quality has been measured.
- **First use (2026-09-21, owner-run):** the model is `qwen3:4b` on Ollama 0.34.2. The owner ran the two opt-in tests once; the exact printed result and
  the runtime's own description of the model are recorded in progress.md ("The first real baseline run"). The baseline mission ended `FAILED`; see D-149 (the diagnosis) and D-150 (what next).
- **Consequences:** a dependency needed later is a new decision and an optional extra (D-116). The opt-in marker's
  mechanics are pinned at implementation and registered in `pyproject.toml`.

### D-137 — Artifacts and data flow at V0.4 (D-129 answered for V0.4; it stays Open)

- **Status:** Accepted · **Date:** 2026-09-20 · **Decided by:** human owner · **D-129 stays Open**
- **Source:** handoff §8, §13; D-005, D-017, D-098, D-122, D-129; V0.4 exploration (Q10, Q11)
- **Decision:**
  1. **An in-memory artifact store.** An artifact is held under **`(execution_id, step_id)`**, and V0.4 has **one
     primary artifact per work step.**
  2. **`ArtifactRef` stays an opaque reference** (D-098). A work result names it; the runtime never interprets it.
  3. **A work node reads its predecessors' outputs, and a verifier reads what it verifies, by fetching from the store.**
     **The `WorkExecutor` signature is not changed** (D-122), and neither is the `Verifier` signature.
  4. **Research works from supplied input or document artifacts** placed in the store by the caller. No file access, no
     tools and no retrieval: MCP is V0.7 and RAG is V0.8.
  5. **Storage is in memory only** (D-005). Nothing is persisted; persistence stays with D-017.
- **Not decided here:** what an artifact contains, how a supplied document is keyed, and how a step learns what it is for.
  Those are **D-142** (since resolved by D-145). No full artifact model exists (D-098 stands).
- **Consequences:**
  - **D-129 is answered for V0.4 and stays Open:** "what an artifact is" and the general data-flow question (for example
    for remote agents at V0.6) remain.
  - The store is the consumer's, not the runtime's: it lives with the agents, so the runtime never imports it (CLAUDE.md §8).
  - The store must be thread-safe: a level's nodes run on worker threads.
- **Settled (2026-09-20):** what an artifact contains, how supplied documents are keyed and the absence of a per-step input field are
  answered by **D-145**. D-129 stays Open.
- **Settled (2026-09-20):** artifact identity is unchanged across plan versions, and a work step in one execution must use a fresh step ID; an
  existing artifact for the step is refused before any model call (**D-147**).



### D-138 — V0.4 verification is a deterministic rule set; no model gives a verdict

- **Status:** Accepted · **Date:** 2026-09-20 · **Decided by:** human owner · **D-015 stays Open**
- **Source:** handoff §18, §19, §31, §47; invariants 12 and 13; D-015, D-121, D-133; V0.4 exploration (Q12)
- **Decision:**
  1. **The V0.4 Verification Agent implements the `Verifier` port (D-121, D-133) as a deterministic rule set.** No model
     is consulted for a verdict.
  2. **Verdicts are `PASS`, `FAIL` or `INCONCLUSIVE` with a reason** (D-121). No scalar.
  3. **The rule categories are** schema correctness of the artifacts, citation coverage, and a minimum number of
     distinct sources. Each rule's exact definition is pinned at implementation, against the content shape D-142 will
     settle.
  4. **A check that cannot be performed yields `INCONCLUSIVE`, never `PASS`** (invariant 13).
  5. A model may produce Research and Analysis content; it never judges it.
- **Consequences:**
  - **D-015 stays Open.** This answers it for V0.4 only. A scalar confidence and §31's threshold-driven replan are V1.2.
    **D-063 and D-064 stay Open and dormant:** no scalar exists to type or compare.
  - The `min_independent_evidence` clause of the reliability contract is a count and can be evaluated (D-139 supplies the
    contract). `min_quality` has no measure at V0.4: **D-143** (since resolved by D-146).
- **Settled (2026-09-20):** which clauses the rule set evaluates, and that `min_quality` is `NOT_EVALUATED`, are **D-146**.


### D-139 — `ExecutionContext` carries the frozen `ReliabilityContract`

- **Status:** Accepted · **Date:** 2026-09-20 · **Decided by:** human owner · **D-041 stays Open**
- **Source:** handoff §30, §31; D-041, D-089, D-100, D-113; V0.4 exploration (Q13)
- **Decision:**
  1. **From V0.4, `ExecutionContext` includes the mission's frozen `ReliabilityContract`** (an additive field), read once
     from MissionState by `context_from_state`.
  2. **No universal output or answer field is introduced, and D-041 is not reopened.**
  3. MissionState still never enters runtime or backend state (D-113): the context remains a frozen, minimal snapshot.
- **Consequences:**
  - This **amends an implementation-level detail of V0.3 Step 3**: the `ExecutionContext` docstring says the context
    deliberately excludes the contract. That exclusion was not a decision; **D-113's principle stands** (only the required
    immutable run snapshot).
  - The tests that pin the context's six fields change **because the approved specification changes**, not to get green.
    Consistency rules (the contract's tenant and identifier must match the tenant and the genome's reference, as
    MissionState's own validators require) are pinned at implementation.
  - The LangGraph adapter closes over the context, so no adapter change is expected; conformance tests will prove it.

### D-140 — V0.4 agents are read-only; the `AdmissionGuard` stays explicit

- **Status:** Accepted · **Date:** 2026-09-20 · **Decided by:** human owner · **D-043 and D-046 stay Open**
- **Source:** handoff §29, §32; D-043, D-046, D-060, D-061, D-074, D-110, D-122, D-127; V0.4 exploration (Q14, Q15)
- **Decision:**
  1. **V0.4 agents are read-only, with no tools and no side effects.** They read supplied artifacts and call the model
     seam; they take no action. Under that constraint, the question D-127 left for the owner — whether real agents may
     execute before a policy exists — is **answered for V0.4**: they may, because none can act. **Policy semantics
     stay deferred** (D-060, D-061, D-074, D-110 are untouched).
  2. **The `AdmissionGuard` remains an explicit, caller-supplied input** (D-122). **No production guard and no default
     ships**, and the runner requires one.
  3. **D-043 and D-046 stay Open.** No runtime accounting is introduced (D-127).
- **Consequences:**
  - If a later milestone gives an agent a tool or an action, this decision no longer covers it, and policy must be decided
    first (MCP at V0.7, policy at V1.2).
  - A minimal agent-call-count guard remains an option for the owner. It is not built.
- **Annotated 2026-09-24 (D-203):** the consequence above (a tool needs policy decided first) is met for read-only tools by D-203's minimal deterministic tool-admission policy, and only for the Research agent. D-060, D-061, D-074 and D-110 stay Open; the plan-validation POLICY stage stays `NOT_APPLICABLE`.

### D-006 — Which capabilities exist in the MVP agent set

- **Status:** Accepted · **Date:** 2026-09-20 · **Decided by:** human owner · **Resolved by D-132**
  (originally Open)
- **Source:** handoff §49 vs §16, §43
- **Original finding:** §49 says start with exactly three logical agents — Research, Analysis, Verification —
  and "do not build 10+". But the flagship demo (§43) and the candidate strategies (§16) both use
  five: Research, Security, Architecture, Analysis, Verification.
- **Original need:** Which capability set exists at V0.4? If three, the §43 demo cannot be run as written.
- **Resolution:** **D-132.** Five capabilities exist at V0.4 — the five listed under "Required capabilities" in §43 — while the agent set stays three logical agents (D-131). This is a V0.4-only answer.
- **Not resolved by this:** **D-007** (the cross-mission vocabulary) stays Open. Which agent serves which capability, and
  the spelling of the five names, are **D-141** (since resolved by D-144).

### D-018 — Where the model-provider abstraction boundary lives

- **Status:** Accepted · **Date:** 2026-09-20 · **Decided by:** human owner · **Resolved by D-135**
  (originally Open)
- **Source:** handoff §36 vs §51
- **Original finding:** §36 forbids model dependence anywhere in EIDOS; §51 names Ollama plus a local open
  model as the concrete LLM. The handoff shows a "Model/Agent Interface" in a diagram but does not
  say which module owns it, what its interface is, or which layers may import it.
- **Original need:** The owning module and its interface. Invariant 9 forbids vendor names in contracts,
  planning, validation, compiler, runtime and state — so the boundary must be defined before any
  code calls a model.
- **Scoped narrowly at V0.3 (2026-09-19, D-122):** only the *execution-side* port interface — how the runtime asks
  for work to be performed and a verification to be judged — is defined at V0.3, and it is owned by
  `eidos.runtime`. The model-provider abstraction boundary this entry asks about is untouched and
  remains Open.
- **Resolution:** **D-135.** `eidos.agents` owns a synchronous `ModelPort` and its typed request, response and failure
  types; every provider adapter lives in `eidos.providers`, the only place a vendor, model or SDK name may appear;
  model, generation parameters and timeout are explicit and never defaulted.

### D-144 — V0.4 canonical capability IDs, and which agent serves which (resolves D-141)

- **Status:** Accepted · **Date:** 2026-09-20 · **Decided by:** human owner · **Resolves D-141**
- **Source:** handoff §6, §7, §43; D-006, D-007, D-132, D-133, D-134
- **Decision:**
  1. **The V0.4 canonical capability IDs are exactly `architecture`, `security`, `cost`, `research`, `verification`** (lowercase).
     This settles the spelling D-132 left to D-141: D-132's capitalised forms are superseded **for spelling only**; the set of
     five is unchanged.
  2. **Scoped to V0.4. D-007 stays Open:** nothing global, hierarchical, similarity-based or cross-mission is decided.
  3. **The Research Agent serves `research`. The Analysis Agent serves `architecture`, `security` and `cost`.**
  4. **The Verification Agent is not capability-bound.** It is reached through the `Verifier` port by `VERIFY` node kind (D-133).
- **Consequences:**
  - `verification` is a member of the V0.4 vocabulary (a genome label) that **no work agent serves**. An `agent` step that requested
    it is an unbound capability and is refused before dispatch (D-134).
  - The baseline plan is supplied (D-131), so which of the Analysis Agent's three capabilities its analysis step requests is the plan
    author's choice, not the runner's.
  - **V0.2 is unchanged:** it still checks membership in the mission's own `required_capabilities` (D-102), not the vocabulary.

### D-145 — The V0.4 artifact model, supplied documents and access (resolves D-142)

- **Status:** Accepted · **Date:** 2026-09-20 · **Decided by:** human owner · **Resolves D-142**
- **Source:** D-047, D-098, D-099, D-129, D-137
- **Decision:**
  1. **A minimal typed artifact model** with four fields: **`ref`, `content_type`, `content`, `source_refs`.**
  2. **V0.4 artifacts are primarily text or Markdown plus source references.**
  3. **Supplied documents are stored and addressed by `ArtifactRef`, namespaced by execution.**
  4. **No per-step input field is added** (D-047 stands; `PlanStep` is unchanged).
  5. **Research and Analysis reach mission-level and supplied artifacts through the in-memory artifact store**, so the `WorkExecutor`
     signature is preserved (D-137).
- **Consequences:**
  - This introduces the minimal model D-098 deferred; **`ArtifactRef` itself stays opaque** and the runtime never sees an artifact's
    content. The model lives with the store, in `eidos.agents` (D-137), not in `eidos.contracts`.
  - An agent's task derives from the mission goal, its capability, its predecessors' artifacts and the supplied artifacts
    — nothing else.
  - **D-129 stays Open:** the general data-flow question (for example for remote agents at V0.6) is untouched.
  - Field constraints and the store's exact interface are pinned at implementation.

### D-146 — Which reliability-contract clauses V0.4 evaluates; `min_quality` is NOT_EVALUATED (resolves D-143)

- **Status:** Accepted · **Date:** 2026-09-20 · **Decided by:** human owner · **Resolves D-143**
- **Source:** handoff §30, §47; invariants 12 and 13; D-057, D-059, D-063, D-064, D-121, D-138, D-139
- **Decision:**
  1. **V0.4 evaluates only `ReliabilityContract` clauses that have an explicitly defined deterministic measurement.**
  2. **Evaluable:** schema validity, citation and source coverage, and a minimum number of distinct sources.
  3. **`min_quality` is explicitly `NOT_EVALUATED`.** No quality metric is invented.
  4. **Contract satisfaction is never silently claimed.** A `PASS` means the **supported V0.4 verification rules passed**, not that
     every `ReliabilityContract` clause was evaluated.
- **Consequences:**
  - By rule 1, any other clause without a defined measurement is also `NOT_EVALUATED`: `max_risk_level` (how a run's risk is
    determined is D-057, Open). The six budget clauses are runtime accounting, deferred (D-127), and are not verification clauses.
  - Every verdict's reason names the clauses that were `NOT_EVALUATED`. The `Verifier` port carries only a verdict and a reason
    (D-121), so this is stated in the reason; the verification agent keeps a typed per-clause record from which the reason is rendered.
    No runtime type changes.
  - `RunResult.verified` keeps its meaning: never a claim that the mission or its contract succeeded.
  - **D-059 stays Open** (no status is invented for "contract not satisfied"); **D-063 and D-064 stay Open and dormant.**
- **Annotated 2026-09-25 (D-209):** the meaning of "distinct sources" is extended additively for V1.3 knowledge evidence (independence by declared source identity, with declared `derived_from`). The V0.4
  verifier's behaviour, and its behaviour with no resolver, are unchanged; how existing supplied and tool documents are keyed once a resolver exists is D-210 (ruled 2026-09-25, built at V1.3 Step 3, readings D-224).

### D-141 — The five V0.4 capabilities: spelling, the agents that serve them, and what `Verification` binds to

- **Status:** Accepted · **Date:** 2026-09-20 · **Decided by:** human owner · **Resolved by D-144**
  (originally Open)
- **Source:** handoff §6, §7, §16, §43; D-006, D-132, D-133, D-134; raised while recording the V0.4 rulings
- **Original finding:**
  - **(a) Spelling.** §43 prints the five names as display labels — capitalised single words. §6's example for the same
    mission writes `architecture_analysis`, `security_analysis`, `cost_analysis`, `research` and `verification`; the
    examples and tests elsewhere in this repository use lowercase. D-132 records the names **exactly as printed in §43**.
    Matching is exact-string, so the spelling decides every genome, plan and registration.
  - **(b) Which agent serves what.** There are five capabilities and three logical agents (D-131). §7 gives the Analysis
    Agent `technical_analysis` and `cost_analysis` and describes a separate Security Agent; the handoff does not say which of
    the three agents serves `Architecture`, `Security` and `Cost`.
  - **(c) The analysis step.** The baseline plan is Research, then Analysis, then `VERIFY` (D-131), but "Analysis" is not one of
    the five, and an `agent` step must request a capability.
  - **(d) `Verification`.** It is a capability ID, yet `VERIFY` is bound by node kind (D-133). An `agent` step that requested
    `Verification` would have no work agent registered for it: an unbound capability (D-134).
- **Effect while Open:** none until the registry and the baseline plan are built (V0.4 Step 4).
- **Original need:** (a) confirm the literal spelling or give another form; (b) the capability-to-agent mapping — *proposal:* the
  Research Agent serves `Research`, the Analysis Agent serves `Architecture`, `Security` and `Cost`, and the Verification
  Agent serves the `Verifier` port only; (c) which of the Analysis Agent's capabilities the baseline plan's analysis step
  requests; (d) whether `Verification` stays in the vocabulary as a genome-only label that no work agent serves, or is dropped.
- **Resolution:** **D-144.** The spelling is lowercase, the mapping is settled, and `verification` is a vocabulary member that no work agent serves.

### D-142 — V0.4 artifact content, supplied documents and per-step input

- **Status:** Accepted · **Date:** 2026-09-20 · **Decided by:** human owner · **Resolved by D-145**
  (originally Open)
- **Source:** D-047, D-098, D-099, D-129, D-137, D-138
- **Original finding:** D-137 fixes where artifacts live, not what they contain.
  - **(a) Content.** The deterministic verifier (D-138) needs schema-checkable structure — claims and the sources they cite —
    and D-098 says no artifact model exists. A minimal typed shape is unavoidable, and defining one is a contract decision.
  - **(b) Supplied documents.** A supplied document is not produced by a step, so `(execution_id, step_id)` does not key it.
    `information_dependencies` are opaque strings (D-099); reading them as store keys would be invention.
  - **(c) Per-step input.** `PlanStep` carries no instruction or input (D-047). An agent's task can only be derived from the
    mission goal, its capability and its predecessors' artifacts.
- **Effect while Open:** blocks the artifact-store slice and the agents (V0.4 Steps 5 and 6) only.
- **Original need:** (a) the minimal content shape for Research and Analysis artifacts; (b) how supplied input artifacts are named and
  keyed; (c) confirmation that V0.4 adds no per-step input field — *recommended*; a field would be an additive contract
  change later (D-047).
- **Resolution:** **D-145.** A minimal typed artifact model; supplied documents addressed by `ArtifactRef`, namespaced by execution; no per-step input field.

### D-143 — Reliability-contract clauses the V0.4 verifier cannot evaluate

- **Status:** Accepted · **Date:** 2026-09-20 · **Decided by:** human owner · **Resolved by D-146**
  (originally Open)
- **Source:** handoff §30, §47; invariant 13; D-057, D-059, D-063, D-064, D-073, D-138, D-139
- **Original finding:** D-139 gives the verifier the frozen `ReliabilityContract`. `min_independent_evidence` is a count and can be
  checked deterministically. **`min_quality`** is a required contract field (D-073) with no measure at V0.4: there is no
  scalar (D-138), and D-063 and D-064 are Open. **`max_risk_level`** has no defined check either, because how a run's risk is
  determined is D-057 (Open). If the verifier read any unevaluable clause as `INCONCLUSIVE`, **no mission could ever
  `PASS`**. If it ignored them, a `PASS` could be read as "the contract is satisfied", which invariant 13 forbids
  manufacturing. (`RunResult.verified` already states that it is never a claim of mission success.)
- **Effect while Open:** blocks the verifier slice (V0.4 Step 6) only.
- **Original need:** the rule. *Recommended:* the verdict is judged only on the clauses that can be evaluated; its reason names every
  clause **not evaluated** and why; a `verified` run is never reported as contract-satisfied; D-059 (whether an unmet contract is
  a status) stays Open. *Alternative:* `INCONCLUSIVE` whenever any clause is unevaluated — safe, but nothing then passes.
- **Resolution:** **D-146.** Only clauses with an explicitly defined deterministic measurement are evaluated; `min_quality` is explicitly NOT_EVALUATED.


### D-147 — Artifact identity across plan versions: fresh step ids, and a guard before any model call

- **Status:** Accepted · **Date:** 2026-09-20 · **Decided by:** human owner · **Resolved by the owner's ruling** (originally Open)
- **Source:** D-085, D-119, D-120, D-137, D-145; found writing the V0.4 replan scenario
- **Original finding:** D-137 holds a work step's one primary artifact under `(execution_id, step_id)`. A replan is a new plan version run in the **same**
  execution (D-085, D-119), and a replan naturally reuses step ids (version 2 is often version 1 plus a step). The V0.4 store is write-once, so a
  version-2 step with the id of a version-1 step is **refused** (`FAILED`, "could not be recorded") rather than overwritten. Prior outcomes cannot
  bridge the gap: they belong to one plan (D-120).
- **Decision (option a):**
  1. **Within one execution, a newly executed work step must use a fresh step ID across plan versions.** A step ID that an earlier-executed work step of
     the same execution already used may not be used again.
  2. **Artifact identity is unchanged:** `(execution_id, step_id)` and `artifact:<step_id>`. **No plan-scoped artifact keys or refs are introduced in V0.4.**
  3. **The guard.** Before an agent makes any model call, it checks whether the artifact for that execution and step already exists. If it does, the new
     execution of that step is **refused with a typed failure and no model call is made.**
  4. **Same-plan resume is preserved (D-120).** A step with a prior `SUCCEEDED` outcome is not dispatched, so it is never refused. A step that failed or
     produced nothing wrote no artifact, so it may run again.
- **Consequences:**
  - The typed failure is a `FAILED` work result with a stable, documented reason; the `WorkExecutor` signature is unchanged (D-122, D-137).
  - The guard covers both halves of the identity: the step's artifact under `(execution_id, step_id)` and the reference `artifact:<step_id>` being taken
    (for example by a supplied document). The write-once store stays as the backstop for a race between the check and the write.
  - **V0.2 does not enforce the rule** (it validates one plan and cannot see an execution's history). It is enforced at execution time by this guard; a
    reducer that knows a mission's plan lineage could enforce it earlier at V0.5 (D-076 stays Open). That, and how artifact identity should carry
    lineage for replay and evidence (invariant 16), is **not decided here.**
  - Options (b) (plan-scoped keys, which would also need plan-scoped refs) and (c) (a fresh store per plan version) are not adopted. (c) remains available
    to any caller today.
  - The one-artifact-per-step rule (D-137) and same-plan resume are unaffected.

### D-148 — V0.4 implementation details (accepted as written)

- **Status:** Accepted · **Date:** 2026-09-20 · **Decided by:** human owner · **Accepted as written** (originally Open)
- **Source:** D-131 to D-147; recorded at the end of V0.4 Step 8 — none touches an invariant
- **Decision:** the ten details below are accepted exactly as written.
- **The details:**
  1. **Registry.** Refuses a repeated `agent_id`, a capability served by two agents, and a capability outside the V0.4 five. `verification` is not
     barred from registration (no agent registers it); an `agent` step requesting it is unbound. Registry resolution is by exact string and never nearest match.
  2. **Binding.** One violation per unbound step, every one reported in plan order; a failed report binds nothing. `VERIFY` nodes never appear in it.
  3. **Artifact.** `content` may be empty (verification judges it); `source_refs` are distinct, non-blank and never a self-reference; a produced
     artifact's `ref` is `artifact:<step_id>` and its `content_type` is `text/markdown`; the supported types are `text/markdown` and `text/plain`.
  4. **Store.** Write-once per `ref` and per step; `supplied()` returns artifacts ordered by `ref`; an absent read is `None`; nothing is shared across
     executions; a refused write leaves nothing behind.
  5. **Citations.** An agent asks the model to cite `[[ref]]` and records **what the model cited** as `source_refs`, including references that do not exist
     (verification then fails them) and dropping only a citation of the output itself.
  6. **Work agents.** Research with nothing supplied returns `NO_RESULT` and never asks a model. Analysis reads its predecessors' artifacts, then the supplied
     documents; a predecessor with no artifact is a `FAILED` result, so an analysis step's predecessors are work steps at V0.4. Each capability has a fixed,
     generic instruction. Model failures map `TIMEOUT` and `UNAVAILABLE` to `FAILED` and `MALFORMED_RESPONSE` and `EMPTY_RESPONSE` to `NO_RESULT`.
  7. **Verifier.** Three rules (`schema_validity`, `citation_coverage`, `minimum_distinct_sources`), each `SATISFIED`, `VIOLATED` or `UNPERFORMABLE`; any
     violation is `FAIL`, else any unperformable rule is `INCONCLUSIVE`, else `PASS`. "Distinct sources" are the distinct **supplied** documents reached by
     following citations through produced artifacts. The clauses named `NOT_EVALUATED` are `min_quality` and `max_risk_level`; the budget clauses are not
     listed. A `VERIFY` with no artifact among its predecessors is `INCONCLUSIVE`.
  8. **Runner.** `eidos.baseline` takes an executor factory, never imports a backend or provider, and does not own the artifact store: the caller supplies
     documents under the mission's `execution_id`. `BaselineReport` is consistent by construction and names the first gate that refused.
  9. **Provider.** The base URL is explicit and `http` or `https` only. The timeout is passed to each socket operation, so it is the only bound on a call and
     not a guarantee of total elapsed time. An error status and a dropped connection are `UNAVAILABLE`; malformed HTTP or JSON is `MALFORMED_RESPONSE`.
  10. **Tests.** Real-model tests are deselected by `-m 'not real_model'` in `addopts` and fail, never skip, when selected without their configuration.
- **A V0.4 limitation recorded, not redesigned (item 6).** A plan in which an analysis step follows a `VERIFY` step cannot run at V0.4: the analysis
  agent looks for its predecessor's artifact, a `VERIFY` node produces none, and the step fails with "predecessor '<id>' has no artifact to analyse". An
  analysis step's predecessors are work steps. Nothing was changed to work around this, and a plan of that shape is a **later decision** if it is wanted.
- **Consequences:** items 3 (`artifact:<step_id>`) and 4 (write-once, refused writes) stand as accepted and are what D-147's rule rests on.

### D-149 — The first real run's failure: diagnosed with one raw-response call (option 1)

- **Status:** Accepted · **Date:** 2026-09-21 · **Decided by:** human owner · **Resolved by the owner's ruling** (originally Open; option 1 chosen)
- **Source:** D-135, D-136, D-148 (items 6 and 9); the first real baseline run (owner-run, V0.4 Step 8)
- **Original finding (measured, one run):** with `qwen3:4b` through the local runtime (temperature 0.0, seed 7, `max_output_tokens` 512, timeout 120 s), a direct
  completion of "Reply with the single word: ready." returned a 5-character response while the runtime reported **154 output tokens**; and in the baseline
  run the Research step's one model call returned **no text** (`empty_response`), so the step was `NO_RESULT`, the Analysis and `VERIFY` steps were
  `SKIPPED`, and the mission ended `FAILED` with `verified` false. The runtime lists a `thinking` capability for this model and the adapter reads only the `response`
  field; the candidate explanation was that reasoning used the output budget. That was a hypothesis until the diagnostic below.
- **Ruling (option 1):** diagnose first. One real-model run of the same baseline test, with a **test-only** change that prints the raw response of the baseline's own
  call. The provider, the agents, the verifier, the model settings and production behaviour are not changed, and the temporary code is removed afterwards.
- **What was done (2026-09-21):** Claude Code ran the baseline test once, at the owner's direction, with the same model and settings as the recorded run, at the runtime's
  default local address `http://127.0.0.1:11434` (the address of the owner's own run was not printed, so that is an assumption about it; the runtime answered there). A
  temporary tap on the HTTP layer inside the test recorded the request and the raw response body of the call the provider made. It was reverted afterwards: the working tree
  equals its committed state. The raw response is kept outside the repository. The full result is in progress.md ("The D-149 diagnostic").
- **Result (one run):** the request was the Research agent's own: its system instruction and a prompt of the mission goal, the three supplied documents and the task line
  (160 prompt tokens). The response was HTTP 200, 6,081 bytes, with **`response` empty**, **`thinking` 2,581 characters (406 words) of reasoning that ends mid-sentence**,
  `done` true, **`done_reason` `length`** and **`eval_count` 512, equal to `num_predict`**. The runtime reported `total_duration` 30.256 s, of which `load_duration` 7.678 s,
  `prompt_eval_duration` 0.316 s and `eval_duration` 22.249 s. EIDOS read it as before: `gather` `no_result` ("the model call failed (empty_response): the model returned no
  text"), `analyse` and `check` skipped, outcome `failed`, `verified` false.
- **Cause, established for this call:** the runtime returns this model's reasoning in a separate `thinking` field and counts it against `num_predict`. The whole 512-token
  budget was spent reasoning, generation stopped at the limit before any answer text, and the `response` field the adapter reads was empty. The adapter's `empty_response`
  was accurate about that field and silent about why; `thinking` and `done_reason` are in the body, and the adapter discards both.
- **Not observed:** the raw body of the trivial "ready" call (its 154 output tokens for a 5-character answer are consistent with the same mechanism, which is an inference and
  not an observation); what a larger budget, or reasoning switched off, would return; whether the reasoning would have finished and the answer been usable and verifiable.
- **Consequences:** no production code, model setting or test expectation changed. Option 1 decided only to diagnose; **what to do about the finding was D-150** (since resolved).

### D-150 — What to do when a reasoning model spends its whole output budget before answering (follows D-149)

- **Status:** Accepted · **Date:** 2026-09-21 · **Decided by:** human owner · **Resolved by the owner's ruling** (originally Open; the options were tried in order)
- **Source:** D-135, D-136, D-148, D-149 (the diagnostic's result)
- **Decision:** option **(a′) adopted**, option **(c) adopted**, option **(b) not adopted**, option **(d) not adopted**. Concretely:
  1. **(a′)** The committed opt-in real-model test carries `max_output_tokens` **4,096** and a **240 s** timeout — the timeout as a committed constant beside the generation
     parameters, no longer an environment variable — with `qwen3:4b`, temperature 0.0, seed 7, the endpoint, the mission and all other behaviour unchanged. Option (a) alone
     (2,048 tokens, 120 s) had been tried first and was not sufficient.
  2. **(c)** The adapter's failure message for an empty answer that stopped at the output limit says so. The failure kind, D-135's set, the ModelPort, the agents, the verifier and
     the runtime are unchanged.
  3. **(b)** The model seam does not express reasoning: `GenerationParameters`, `ModelSettings` and D-135 are unchanged.
  4. **(d)** The model choice is unchanged.
  5. **Not decided here:** what to do with a non-empty answer that stopped at the output limit. That is **D-151 (Open)**.
- **The committed test, run once (2026-09-21):** after the adoption was committed, the baseline node of the committed opt-in test was run once from a clean tree (no tap, retry, re-run
  or side call; `qwen3:4b`, temperature 0.0, seed 7, 4,096 tokens, 240 s). Outcome **`finished`**, `verified` **true**; `gather`, `analyse` and `check` all `succeeded`, so `VERIFY` was
  dispatched and the verifier returned PASS, with the same reason recorded below. Research: 753 characters, 977 output tokens, 59.531 s. Analysis: 842 characters, 2,582 output
  tokens, 172.203 s (72% of the timeout). The response lengths and token counts equal the earlier (a′) run's; only the timings differ. pytest: 1 passed in 232.93 s. Detail in
  progress.md ("The committed real-model run").
- **Finding:** D-149's diagnostic established that, with `qwen3:4b` and `max_output_tokens` 512, the runtime spent the whole budget on the model's reasoning, stopped at the
  limit (`done_reason` `length`) and returned an empty `response`. The provider then reported `empty_response`, so a length cutoff and a model that genuinely said nothing are
  indistinguishable in a typed failure, and the reasoning and the stop reason are discarded. The seam (`ModelSettings`, `GenerationParameters`, D-135) has no notion of
  reasoning, and a `ModelFailure` carries no measured facts, so a failed call's token counts and latency are lost too.
- **Not known when logged:** whether a larger budget, or reasoning turned off, yields an answer the agents can use and the verifier can judge. None of it had been tested then; a
  larger budget has since been (option a′). Reasoning turned off, and another model, remain untested.
- **Effect:** the adapter's failure message names an output-limit cutoff (option c) and the committed opt-in test's configuration changed (option a′). No other code, prompt, setting
  or contract changed. At 512 output tokens the baseline with this model had failed at its first step and at 2,048 at its second; at 4,096 tokens with a 240 s timeout it finished
  verified. The history below records what each attempt showed, as it was.
- **Options considered** (the outcome is in bold at the end of each):
  (a) **configuration only** — raise `max_output_tokens` in the opt-in test (the value is fixed there, explicitly, per D-135) and run it once more; no production change —
  tried once (below), not sufficient on its own; **superseded by (a′)**;
  (a′) **configuration only, both limits** — raise the timeout (then an environment setting of the opt-in test) as well as the budget — tried once (below): the baseline finished, verified; **adopted**;
  (b) **let the seam express reasoning** — a request setting that tells the runtime whether to reason, sent by the adapter; a change to D-135's contract and to the adapter; **not adopted**;
  (c) **make the adapter report a length cutoff distinctly** — read `done_reason` (and possibly `thinking`) so the failure names its cause; a change to the adapter and, if
  it adds a failure kind, to D-135's closed set — implemented as a message-only change with no new kind (below); **adopted**;
  (d) **another model**, one that does not reason by default — **not adopted**.
  These combine (for example (c) with (a)). Under every option the agents and the verifier are **not** changed to make a model pass.
- **Owner ruling (2026-09-21): option (a) first, one run only.** For one opt-in run, `max_output_tokens` went from 512 to **2,048** — chosen so that a worst-case generation would
  fit inside the unchanged 120 s timeout, from the 23.0 tokens/s measured under D-149; that estimate proved optimistic (below). Model, temperature, seed, timeout, endpoint and
  mission were unchanged, and the ModelPort, the provider, the agent prompts, the verifier, the artifact model and store, the runtime and the model choice were not touched.
  The temporary edit (that limit and a test-only tap on the HTTP layer) was reverted; the working tree equals its committed state.
- **Result of option (a)** — one baseline attempt, two model calls, as the mission dispatches them; full detail in progress.md ("The D-150 option (a) run"):
  - **Research succeeded:** `response` 753 characters citing `doc:1`, `doc:2` and `doc:3`; `thinking` 4,226 characters; `done_reason` `stop`; `eval_count` 977 of 2,048; 52.661 s
    (load 6.191 s). The agent stored it as `artifact:gather` with those three `source_refs`. This is the first real model output to reach the store.
  - **Analysis failed the same way:** `response` empty; `thinking` 10,790 characters (1,709 words); `done_reason` `length`; `eval_count` 2,048 of 2,048; 111.010 s, 93% of the
    120 s timeout. The recorded reasoning drafted the same analysis four times and was cut off part-way through the fourth. The step was `no_result`.
  - `check` (`VERIFY`) was skipped. The mission ended `failed`, `verified` false. **The verifier did not run: there is no PASS, FAIL or INCONCLUSIVE.**
  - Runtime-reported generation rates: 21.2 tokens/s (Research) and 18.5 tokens/s (Analysis). At 18.5 tokens/s the 120 s timeout allows about 2,200 generated tokens on this
    machine, so with the timeout unchanged there is almost no room above 2,048: a larger budget needs a larger timeout too (option a′). One run: not a benchmark.
  - Not observed: whether Analysis finishes with a larger budget and timeout; reasoning switched off; another model.
- **Also found, by reading the code (not observed in any run):** the adapter returns a `ModelResponse` whenever `response` has text, whatever `done_reason` says, so an answer cut
  off part-way would be passed on as a normal answer and the verifier would not be told. Option (c) does not address this; it is now **D-151 (Open)**.
- **Owner ruling (2026-09-21): option (c) implemented, as its own step, before any further real-model run.** The smallest provider-local change, in `OllamaModel._interpret`: an
  empty `response` whose `done_reason` is exactly the string `"length"` is still an `EMPTY_RESPONSE`, but its message now says that generation stopped at the output limit ("the
  model returned no text: generation stopped at the output limit (done_reason 'length') before any answer text"). An empty `response` with `"stop"`, with no `done_reason`, or
  with a `done_reason` that is not exactly `"length"` keeps the message "the model returned no text". A non-empty `response` is unchanged whatever `done_reason` says, so the gap
  noted above stays open. **No new failure kind:** D-135's set, the ModelPort, the agents' mapping to `NO_RESULT`, the verifier, the runtime, the prompts and the settings are
  unchanged. Five tests (16 cases) were added to the adapter tests and 12 of 12 mutations were caught; nothing was run against a real model in that step.
- **Owner ruling (2026-09-21): option (a′), one baseline attempt, after option (c).** For that one opt-in run only: `max_output_tokens` 4,096 and a 240 s timeout; `qwen3:4b`,
  temperature 0.0, seed 7, the same endpoint and mission; no retry, no re-run, no side calls; the adapter as changed by option (c). Nothing else was changed, and the temporary edit
  (the limit and a test-only tap on the HTTP layer) was reverted; **the committed opt-in test then still set `max_output_tokens` 512** (changed by the adoption above).
- **Result of option (a′)** — two model calls, as the mission dispatches them; detail in progress.md ("The D-150 option (a′) run"):
  - **Research:** `response` 753 characters, `thinking` 4,226 characters, `done_reason` `stop`, `eval_count` 977 of 4,096, 53.049 s; `succeeded`, `artifact:gather`. **Identical, byte for
    byte in `response` and `thinking`, to the same call in the 2,048-token run.**
  - **Analysis:** `response` 842 characters, `thinking` 12,588 characters, `done_reason` `stop`, `eval_count` 2,582 of 4,096, 154.208 s (64% of the 240 s timeout); `succeeded`,
    `artifact:analyse`. **The 2,048-token run's cut-off reasoning is an exact prefix of this run's reasoning:** the model followed the same path and needed 534 more tokens than it had
    been given, so the budget was the only difference.
  - **`VERIFY` was dispatched and the verifier returned PASS** (the node's status is `succeeded`): "schema_validity satisfied (1 artifact(s) well-formed); citation_coverage satisfied
    (every artifact cites sources that exist); minimum_distinct_sources satisfied (3 distinct supplied source(s) reached, 3 required). NOT_EVALUATED: min_quality, max_risk_level (no
    defined deterministic measurement). This verdict covers the V0.4 verification rules only; it is not a claim that the reliability contract is satisfied."
  - Final `RunResult`: outcome **`finished`**, `verified` **true**. pytest: 1 passed in 208.50 s.
  - **What the PASS is not:** it checks that the artifacts are well-formed, that every cited reference exists and that three distinct supplied documents are reached. It does not
    check that a cited document supports the claim it is cited for, and no quality is measured (D-146).
  - Not observed: repeatability beyond the Research call above (one attempt); other models; reasoning switched off; a budget between 2,048 and 4,096; the opt-in test as committed (which then still set 512 tokens; see the committed run above).

### D-152 — V0.5 scope: the event log, the reducer, checkpoint and replay, recording adapters and a thin derived record

- **Status:** Accepted · **Date:** 2026-09-21 · **Decided by:** human owner
- **Source:** handoff §9, §10, §33, §34, §50, §73; invariants 1, 2, 8, 15; D-010a, D-011, D-097, D-123, D-127; the V0.5 exploration, which found that the handoff's V0.5 line and the
  telemetry-to-memory chain the owner described place telemetry, memory and learning at different milestones
- **Decision:** V0.5 is **MissionEvent / MissionState / StateReducer + the event log + checkpoint and replay + recording adapters + a thin, read-only `ExecutionRecord`.**
  1. **In V0.5:** typed event payloads (D-153); the local-execution event vocabulary (D-154); a pure reducer (D-155); the run-outcome mapping and the counters (D-156); an append-only in-memory
     event log with a strict JSONL round trip, a checkpoint value and replay (D-157); recording adapters that turn a V0.4 run into events without changing the runtime (D-158); and the derived
     `ExecutionRecord` (D-159).
  2. **The ladder does not move.** Telemetry breadth (A2A, RAG, cache, policy and human-intervention measures, aggregation, OpenTelemetry) stays at V0.9; historical strategy memory and ranking at
     V1.0; adaptive learning at V1.1. `ExecutionRecord` is the only addition to the handoff's V0.5 line, and it is derived, so it is not a second source of truth.
  3. **Where this sits in §34's loop** (telemetry → evaluation → performance memory → strategy selection): V0.5 builds the first link only — a faithful, replayable record of what an execution did
     and measured. It scores nothing, remembers nothing across missions and selects nothing.
  4. **Nothing is scaffolded early.** The new packages are `eidos.state` (pure) and `eidos.recording` (adapters), each created by the step that fills it (CLAUDE.md §3).
  5. Everything V0.5 excludes is recorded in **D-161**.
- **Consequences:** the event log is the authoritative history (D-157); the derived record is the raw material a later milestone may use, and V0.5 makes no claim about how it will be used.

### D-153 — Typed payloads through `EventRecord`; the V0.1 envelope is unchanged

- **Status:** Accepted · **Date:** 2026-09-21 · **Decided by:** human owner
- **Source:** D-067, D-075, D-076, D-090, D-154; CLAUDE.md §8; the V0.5 exploration
- **Decision:**
  1. **`MissionEvent` (V0.1) is unchanged:** the envelope only, with no payload field. D-067 stays true of the contract, and `test_no_payload_field_exists` stays true.
  2. **`EventRecord`**, defined in `eidos.state`, pairs one `MissionEvent` with **one typed payload** from a discriminated union keyed by the envelope's `type`. A record whose payload kind does not
     match its envelope's type is rejected at construction.
  3. **Payload classes exist only for the types V0.5 emits** (D-154, D-160). A type with no payload class (`A2A_TASK_STARTED`, `A2A_TASK_COMPLETED`, `MCP_TOOL_CALLED`, `RAG_SEARCH`,
     `EVIDENCE_REJECTED`, `REPLAN_TRIGGERED`, and `VERIFICATION_FAILED`, D-160 item 2) cannot form an `EventRecord` in V0.5 and is refused at intake. No placeholder payloads are invented.
  4. **A payload carries only what the reducer and the `ExecutionRecord` need.** Artifacts appear as an `ArtifactRef`, never as content.
  5. **Layering:** payload types live in `eidos.state`, which may import the core layers (contracts, runtime) and never agents, providers, capabilities or baseline. The recorded model-call outcome is
     therefore an enum owned by `eidos.state` and mirrored from the agents' failure kinds by the recording adapter, with a guard test that the two value sets match.
- **Consequences:** the concrete payload fields are recorded in **D-160** (approved). **D-075** is answered for the emitted types only; **D-076** is discharged for them but
  stays Open (see the annotations on both).

### D-154 — The local-execution event vocabulary: `NODE_STARTED`, `NODE_SETTLED`, `MISSION_PAUSED` (resolves D-126; supersedes D-090's "exactly thirteen")

- **Status:** Accepted · **Date:** 2026-09-21 · **Decided by:** human owner
- **Source:** handoff §33; invariants 2 and 15; D-052, D-090, D-118, D-123, D-126; the V0.5 exploration
- **Decision:** `MissionEventType` gains exactly **three** members, so it has **sixteen**. The thirteen §33 types are unchanged, including the ones V0.5 does not emit.
  1. **`NODE_STARTED`** — a compiled node was dispatched: a port was invoked for it.
  2. **`NODE_SETTLED`** — a compiled node reached a settled state, carrying the typed `NodeStatus` (D-118: all seven, including `skipped` and `not_reached`, which have no `NODE_STARTED`). In a
     completed pass every compiled node has exactly one `NODE_SETTLED`.
  3. **`MISSION_PAUSED`** — a run halted at an admission guard, so the mission becomes `paused` (D-052). Until now `paused` was a status with no event that could cause it.
  4. **Local nodes are not `AgentTask`s,** and the `A2A_TASK_*` types are not reused for them: remote state stays remote (invariant 2), and D-036 is unaffected.
  5. **This is the only change to the V0.1 contracts:** an enum extension. `MissionEvent`, `MissionState` and `MissionStatus` are unchanged.
  6. **Tests that pin the old set change because the specification changed, not to get green:** `test_mission_event_type_is_exactly_the_thirteen_33_types` now expects the sixteen, and the test that
     rejects an unknown type keeps rejecting one. Nothing is weakened, deleted or skipped.
- **Decided in D-160 (item 2):** `VERIFICATION_FAILED` is not emitted in V0.5; the type is retained for future use.
- **Consequences:** D-126 is resolved; D-090 is superseded in part; D-123 stays accurate about the runtime (D-158).

### D-155 — The reducer contract (resolves D-039)

- **Status:** Accepted · **Date:** 2026-09-21 · **Decided by:** human owner
- **Source:** handoff §9, §10; invariants 1, 2 and 8; D-010a, D-011, D-052, D-097; docs/06
- **Decision:**
  1. **A pure function.** The reducer lives in `eidos.state` and does no I/O, no network, no LLM call, reads no clock and holds no hidden state. A timestamp on the state comes from the applied event
     (`updated_at` is the applied event's `recorded_at`). **Only the reducer writes `MissionState`** (invariants 1 and 2); nothing else, at any layer, constructs or updates one.
  2. **It returns the new state and an outcome.** Expected traffic is an outcome, never an exception: *applied*, *duplicate* (ignored), *out of order* (rejected), *stale or late* (rejected), *after a
     terminal state* (rejected) and *invalid for the current state* (rejected), each with a reason. A non-applied outcome leaves the state **byte-identical**.
  3. **Sequence.** An event applies only if its `sequence` is `state_version + 1`; the sequence begins at 1 and `state_version` is the latest applied sequence (D-097).
  4. **Idempotency.** `event_id` is the idempotency key (D-011). A repeated `event_id` is ignored, not re-applied. The set of applied ids is derived from the log with full retention in memory —
     **D-038 is answered for V0.5 only**; bounding and persisting it stay Open with D-017.
  5. **Terminal states.** `completed` and `failed` reject every later event. The treatment of `paused` and the reducer's effect per event type are in D-160.
- **Consequences:** D-039 is resolved. The determinism requirement is now observable — an outcome can be counted and asserted — which was the reason D-039 asked for an outcome.
- **Note (2026-09-21):** the reducer holds no per-node state, so it cannot refuse a repeated `NODE_STARTED` or `NODE_SETTLED` for a step; the intake and a fold from scratch refuse it, and the reducer's six outcomes are
  unchanged (**D-162** item 1).

### D-156 — Run outcome to mission status, and the counters (D-043, D-059 and D-015 stay Open)

- **Status:** Accepted · **Date:** 2026-09-21 · **Decided by:** human owner
- **Source:** D-052, D-091, D-118, D-119, D-121, D-131, D-146; invariants 7, 12 and 13; the V0.5 exploration
- **Decision:**
  1. **One recorded pass is the mission's execution at V0.5.** There is no planner, no replan and no retry (D-119, D-131), so the single pass's end is the mission's end. A later milestone that adds
     recovery must revisit this mapping.
  2. **Completion and verification stay separate** (invariants 12 and 13; D-118, D-121). A terminal event records the outcome and a typed `verified` fact; nothing collapses "the run finished" into
     "the mission succeeded". The exact mapping is D-160, item 5.
  3. **A failure carries a typed cause and a reason.** V0.5 adds **no** fifth status and **no** event for "could not satisfy the reliability contract": a verifier FAIL or INCONCLUSIVE is recorded as
     such, and V0.5 makes no claim about contract satisfaction (D-146). **D-059 stays Open**; a typed cause keeps either later answer non-breaking.
  4. **Counters (D-091) are folded by the reducer from recorded facts, never estimated:**
     - `agent_calls_used` counts dispatched work nodes (a dispatched node is one agent call; `VERIFY` dispatches are not agent calls);
     - `tokens_used` counts the prompt and output tokens the **provider reported** for the node's model calls. A call whose tokens were not reported is counted separately in the payload, so the
       counter is a visible **lower bound**;
     - `execution_time_used_ms` follows the rule in D-160, item 6;
     - `retries_used`, `replans_used` and `tool_calls_used` stay 0, because nothing produces them.
  5. **Counters are recorded, not enforced.** No limit is checked at V0.5 (invariant 7's enforcement stays deferred, D-127). **D-043, D-044 and D-046 stay Open.**
  6. **D-015 stays Open:** only a verdict and a reason are recorded; there is no scalar and no confidence.

### D-157 — The event log, checkpoint and replay (resolves D-010b for V0.5; D-017 and D-038 stay Open)

- **Status:** Accepted · **Date:** 2026-09-21 · **Decided by:** human owner
- **Source:** handoff §9, §11, §73; invariants 1, 8 and 15; D-010a, D-010b, D-017, D-038, D-113; docs/06
- **Decision:**
  1. **The event log is authoritative.** `MissionState` is only its materialized view (a fold), and `ExecutionRecord` is purely derived (D-159). A checkpoint or snapshot is an optimisation and never a
     source of truth.
  2. **The log** is append-only and per mission. An **intake** step orders events: it assigns the sequence at acceptance (D-011) and ignores a repeated `event_id`. Producers propose events and hold
     no `MissionState`.
  3. **Storage in V0.5 is in memory plus a strict JSONL round trip** — one `EventRecord` per line, deterministic field order, UTC timestamps, and a parsed log equal to the original. **No SQLite, no file
     store and no durable persistence is built** (the owner's ruling); **D-017 stays Open** for persistence, its schema and its interface.
  4. **A checkpoint is a value:** the mission state and the last applied sequence. It is taken only when the caller asks, never automatically. Resuming restores it and applies the events after its
     sequence; the tested invariant is that **a checkpoint plus the tail equals a full replay**. It is not a LangGraph checkpointer: MissionState never enters LangGraph state (D-113), and LangGraph
     checkpointing and interrupts are not part of V0.5 (D-127); resume of an execution stays by prior `SUCCEEDED` outcomes (D-120).
  5. **Replay** consumes recorded events only and re-runs no agent (invariant 15). It reconstructs the mission state, the node outcomes and the measured facts. It imports no agent, provider or model.
     **Artifact content is not in the log** (`ArtifactRef` only), so replay does not reconstruct artifact text: D-129 and D-017 stay Open.
  6. **A replayable log** is contiguous from sequence 1, belongs to one mission and tenant, and begins with `MISSION_CREATED`. Anything else is a typed rejection, never a partial replay.
- **Consequences:** D-010b is resolved for V0.5. History survives a restart only if the caller saves the serialized log; strategy memory will need a durable store before V1.0, which is D-017's decision
  and not V0.5's.
- **Note (2026-09-21):** the intake also refuses a repeated `NODE_STARTED` or `NODE_SETTLED` for the same step of a plan, and a fold from scratch refuses a log that has one (**D-162** item 1).

### D-158 — Recording adapters and measured facts (D-151 stays Open; `MeasuredFacts` is not modified)

- **Status:** Accepted · **Date:** 2026-09-21 · **Decided by:** human owner
- **Source:** D-113, D-122, D-123, D-135, D-137, D-148, D-150, D-151; invariants 1, 2, 9, 15 and 17; CLAUDE.md §7 and §8; the V0.5 exploration
- **Decision:**
  1. **Events are produced by recording adapters** in `eidos.recording`, outside the runtime. They wrap the existing injection points — the agents, the verifier and the model port — and propose
     events to the log. The plan-stage events (the plan and the result of each gate) come from the optional, observational `observer` hook on `run_baseline` (D-160 item 8). **A halt by the admission
     guard is not observed at the guard:** it is read from the run's result after the run and recorded as `MISSION_PAUSED`, in D-160 item 1's order, so the guard is not wrapped. *(Amended 2026-09-21 by
     D-163: the original wording listed the admission guard among the wrapped points.)* **The runtime, the executors, the compiler, the agents, the verifier and the D-122 and D-137 signatures are unchanged**, and the runtime itself emits no
     event, so D-123 stays accurate for it.
  2. **Adapters hold no `MissionState` and cannot write it.** They propose; the intake orders; only the reducer writes state (invariants 1 and 2).
  3. **The clock and the id source are injected.** Deterministic components read neither, and the adapters are not deterministic components.
  4. **Facts only.** A value is either what the provider reported (`MeasuredFacts`: prompt tokens, output tokens, elapsed seconds) or what the recorder observed with its injected clock; `None` stays
     `None`. Nothing is guessed, and nothing a model asserted is recorded as a measurement. A failed call has no provider facts (D-150) and is recorded as such. Latencies are labelled by source and
     never combined.
  5. **`MeasuredFacts` is not modified** (the owner's ruling), so the log records **no stop reason.** **D-151 stays Open.** The consequence is recorded so it is visible: history cannot tell a
     non-empty answer cut off at the output limit from a complete one.
  6. **Concurrent nodes.** LangGraph runs a level's nodes on worker threads, so two live runs of a plan with parallel nodes may log those nodes in either order (acceptance order). Replay of a recorded
     log is deterministic, and backend conformance is asserted for the linear baseline.
  7. **A correction to the exploration.** The `Verifier` port returns a verdict and a reason only. Per-rule outcomes exist inside the verifying agent's report, not at the port, so the log records the
     verdict and the reason text; it does **not** claim typed per-rule outcomes (D-148 item 7 already carries `NOT_EVALUATED` as prose).
- **Consequences:** V0.5 changes one V0.4 module, and only additively: `run_baseline` gains an optional, observational `observer` parameter (D-160, item 8). Nothing else in V0.3 or V0.4 changes.
- **Amended (2026-09-21, D-163):** item 1 now states the recording and observer boundary as built. The original wording listed the admission guard among the wrapped points; nothing else in this decision changed.

### D-159 — `ExecutionRecord`: a thin, read-only, derived record

- **Status:** Accepted · **Date:** 2026-09-21 · **Decided by:** human owner
- **Source:** handoff §21, §33, §34; invariants 1, 12, 13, 16 and 17; D-015, D-063, D-064, D-146; the V0.5 exploration
- **Decision:** `ExecutionRecord(log)` is a **pure, read-only projection** of a mission's event log. It is recomputable at any time, never stored as truth and never written to `MissionState`.
  1. **Contents (facts only):** identity (tenant, mission, execution, plan ids and versions); the plan's structure as recorded (ordered steps, kinds, capabilities, bound agent ids); each node's
     typed status, artifact reference, reason and recorded duration; the model-call facts; the `VERIFY` verdict and reason; the run outcome; the terminal mission status and typed cause; the folded
     counters; and the log's own bounds (event count, first and last timestamps).
  2. **Excluded:** any quality, confidence, score, rate or `strategy_signature`. `min_quality` and `max_risk_level` remain `NOT_EVALUATED` (D-146). No aggregation across missions.
  3. **It is not strategy memory** (V1.0) **and not the telemetry platform** (V0.9): it describes one execution.
- **Consequences:** D-015, D-063 and D-064 are untouched. What "evaluation" means beyond recording the verifier's verdict is a later milestone's decision.
- **Note (2026-09-21):** as built, `ExecutionRecord` is the function `execution_record(records)`; a log that repeats a step's start or settlement is a typed rejection, never a record; see **D-162** items 1 and 10.

### D-160 — V0.5 implementation details (approved with eight rulings)

- **Status:** Accepted · **Date:** 2026-09-21 · **Decided by:** human owner · **Approved with eight rulings** (originally Open)
- **Source:** D-152 to D-159; recorded at the end of V0.5 Step 1 — none touches an invariant
- **Finding:** the approved rulings fix the shape of V0.5 but leave concrete details that implementation would otherwise have to choose. They are recorded here, as D-148 was for V0.4, so that none is
  chosen silently. **The owner has confirmed them, with the rulings below.**
- **The details, as proposed:**
  1. **Event order for the baseline mission.** `MISSION_CREATED`; `PLAN_GENERATED`; then either `PLAN_REJECTED` (a refused gate) or `PLAN_COMPILED`; then, for each dispatched node, `NODE_STARTED`
     followed by `NODE_SETTLED`, in level order and, within a level, in acceptance order; nodes that were never dispatched (`skipped`, `not_reached`) have a `NODE_SETTLED` only, emitted after the run in
     plan order; and finally exactly one of `MISSION_COMPLETED`, `MISSION_FAILED` or `MISSION_PAUSED`.
  2. **`VERIFICATION_FAILED` is not emitted in V0.5** (the type stays defined, retained for future use). `NODE_SETTLED` carries the typed verdict, so emitting it would record one fact twice;
     emitting it for `INCONCLUSIVE` would misname it; and a mission-level recovery trigger belongs to the milestone that adds recovery. **Approved by the owner.**
  3. **Payload fields**, all frozen and strict, for the emitted types:
     - `MISSION_CREATED`: `task_genome`, `reliability_contract`, `execution_id`.
     - `PLAN_GENERATED`: `plan`. `PLAN_REJECTED`: `plan_id`, `stage` (validation, compilation or binding), `reasons` (a tuple of code and message). `PLAN_COMPILED`: `plan_id`, `plan_version`.
     - `NODE_STARTED`: `plan_id`, `step_id`, `kind`, `capability` and `agent_id` (absent for `VERIFY`).
     - `NODE_SETTLED`: `plan_id`, `step_id`, `kind`, `status` (`NodeStatus`), `artifact` or `reason`, `duration_ms` (absent when not dispatched), `model_calls` (a tuple of outcome, prompt tokens, output
       tokens and elapsed seconds, each absent if unreported), and for `VERIFY` the verdict and its reason. **No stop reason** (D-158).
     - `MISSION_PAUSED`: `plan_id`, `step_id`, `level`, `reason`. `MISSION_COMPLETED`: `plan_id`, `verified`. `MISSION_FAILED`: `plan_id` (absent if no plan was accepted), a typed `cause`, `reason`.
  4. **Reducer effects.** `MISSION_CREATED` creates the state (status `created`, counters 0). `PLAN_GENERATED` appends the plan (the `MissionState` validators check uniqueness and lineage; a violation is
     "invalid for the current state"). `PLAN_COMPILED` sets `active_plan_id`, and the plan must exist. `NODE_STARTED` changes only `state_version` and `updated_at` (per-node state never enters
     `MissionState`, D-010a). `NODE_SETTLED` folds the counters. The three terminal and pause events set `status` and `status_reason`.
  5. **Terminal mapping (D-156).** A finished, verified run is `MISSION_COMPLETED` with `verified` true; a finished run without a successful `VERIFY` is `MISSION_COMPLETED` with `verified` false; a
     failed run is `MISSION_FAILED` with a typed cause taken from the node statuses; a halted run is `MISSION_PAUSED`; a refused plan is `PLAN_REJECTED` then `MISSION_FAILED` with cause `plan_rejected`.
  6. **`execution_time_used_ms` is accumulated accounted node execution time, not wall-clock duration.** Each dispatched node's duration is recorded in its `NODE_SETTLED` payload as an **observed
     fact** (integer milliseconds, from the recorder's injected monotonic clock). The reducer adds the recorded `duration_ms` of each settled node; a node with no recorded duration adds nothing — it
     is never estimated, and no wall-clock metric is invented when one is unavailable. Nodes in one level add up, so the counter can exceed elapsed wall-clock time. What a limit should bound is D-043
     and D-046 (Open).
  7. **Duplicates and ordering.** The intake ignores a repeated `event_id` and assigns the next sequence; the reducer enforces contiguity and lifecycle and returns the outcome. Both outcomes reach
     the caller. The recorder supplies the `event_id` from an injected id source. **The deterministic, EIDOS-assigned sequence is the only ordering:** no semantic ordering is inferred from
     timestamps — in particular not for nodes that run in parallel, whose acceptance order can differ between live runs.
  8. **Plan-stage timestamps.** `run_baseline` gains an optional `observer` parameter, default `None`, so the validate, compile and bind stages are recorded with real times. **It is observational
     only:** it receives frozen values, cannot mutate state, and its faults never change the result — a run with an observer, with a faulting observer and with none returns an identical
     `BaselineReport`. This is the only change to a V0.3 or V0.4 module.
  9. **`paused` is terminal in V0.5.** No resume event exists, so a paused log ends there and the reducer rejects later events. Resume is deferred (D-161).
  10. **JSONL.** One `EventRecord` per line, produced by the strict JSON serialization, with the sequence as the only ordering.
  11. **Model-call attribution.** A recording model port attributes each call to the node being dispatched in the same thread; no agent changes are needed. The state-owned outcome enum mirrors the
      agents' failure kinds plus `response`, with a guard test.
  12. **Packages.** `eidos.state` holds the records, reducer, intake and log, checkpoint, replay and `ExecutionRecord`; `eidos.recording` holds the clock and id ports, the wrappers and the run recorder.
- **The owner's rulings (2026-09-21):**
  1. `VERIFICATION_FAILED` is not emitted in V0.5; `NODE_SETTLED` carries the verification verdict, and the event type is retained for future use.
  2. The optional `observer=None` hook in `run_baseline` is approved, for recording real plan-stage timestamps. It is observational only and must not mutate state or affect execution.
  3. Ordering is the deterministic, EIDOS-assigned sequence. No semantic ordering is inferred from wall-clock timestamps, especially for parallel nodes.
  4. `paused` stays terminal in V0.5; resume is deferred. *(Amended 2026-09-22 by D-176: `paused` caused by an admission-guard halt stays terminal exactly as here; `paused` caused by an
     A2A-awaiting pause is the one exception — it is resumable on the same log. No fifth `MissionStatus` was added.)*
  5. A finished run without a successful `VERIFY` is `MISSION_COMPLETED` with `verified` false; a refused plan is `PLAN_REJECTED` followed by `MISSION_FAILED`.
  6. `execution_time_used_ms` is not defined as wall-clock duration: node durations are recorded as observed facts, the counter is accumulated accounted node execution time, and no wall-clock metric
     is invented when one is unavailable.
  7. D-151 stays Open and `MeasuredFacts` is not modified.
  8. Proceed with the implementation sequence, with no further exploration unless a genuine contradiction with an Accepted decision is found.
- **Effect:** none on existing code until the steps that implement it.
- **Amended (2026-09-22, D-176):** ruling 4 is amended narrowly. An admission-guard `paused` mission stays fully terminal, byte-for-byte as shipped. A `paused` mission caused by an A2A-awaiting pause (D-169) is resumable — the reducer accepts a subsequent event for that cause on the same log. Nothing else in D-160 changed.

### D-162 — Repeated node events are refused at the intake; the V0.5 implementation details are confirmed

- **Status:** Accepted · **Date:** 2026-09-21 · **Decided by:** human owner · **Item 1 approved (option a); items 2 to 6 and 8 to 10 kept; item 7 moved to D-163, since resolved** (originally Open)
- **Source:** V0.5 Steps 2 to 7 (D-153 to D-160); invariants 8, 15 and 16; D-010a, D-113, D-155, D-157; CLAUDE.md §7 (a gap is recorded and raised, never resolved silently)
- **Finding (item 1):** the reducer cannot refuse a repeated `NODE_STARTED` or `NODE_SETTLED` for the same step. **Probe (2026-09-21):** a recorded verified baseline folds to `agent_calls_used == 2`; offering
  `gather`'s `NODE_SETTLED` a second time, with a new `event_id` and the next sequence, before the terminal event, was **applied** and `agent_calls_used` became **3** (its tokens and duration were folded
  again). A repeated `event_id` was already refused (D-011); only a repeat under a **new** identity got through. `MissionState` keeps no per-node state (D-010a, D-113), so the reducer had nothing to see it with.
  Nothing produced such a repeat at V0.5; it becomes reachable with a second producer, a resume or a replan loop.
- **The owner's ruling (2026-09-21):** the event intake must reject a repeated `NODE_STARTED` or `NODE_SETTLED` for the same execution step. **No per-node state is added to `MissionState`.** Items 2 to 10 are kept as
  built unless one contradicts an Accepted decision; each was checked against D-135, D-155, D-156, D-157, D-158, D-159 and D-160, and **item 7 does contradict the wording of D-158 item 1**, so it is not kept
  and was recorded as **D-163**, which the owner then resolved by amending D-158 item 1. Keeping D-151 Open was restated.

1. **The guard, as built.**
   - **The key is (event type, plan, step).** "The same execution step" is read as the same step *of the same plan*: a step id used again in another plan version is another step, so a replanned mission can run
     and verify again (D-147 governs how work step ids are chosen across versions). What is refused is a second event of the *same type* for a step; only the first is ever recorded. *This reading of "same
     execution step" is an implementation choice, recorded here so the owner can correct it.*
   - **A seventh outcome, `REPEATED_STEP_EVENT`,** is added to the outcome enum. **The reducer never returns it** and its six outcomes (D-155 item 2) are unchanged; the intake and a fold from scratch do.
   - **Where:** the intake asks the reducer first and then checks the repeat, so the reducer's own outcomes (a duplicate `event_id`, an event after a terminal state, one that does not fit) take precedence. A
     refused proposal is not appended, folds nothing, remembers nothing and consumes no sequence; the recorder surfaces it in `refused`.
   - **A fold from scratch enforces the same rule:** replay, `EventLog.restore`, the JSONL replay and the projection refuse a log that repeats a step's start or settlement, as a typed `not_applicable`
     rejection naming the sequence and the outcome. So a log the intake wrote always replays, and the live intake and a replay refuse the same record of the same log (tested).
   - **The memory is the log's own,** a set of keys kept by the log and by the fold. It is not in `MissionState`, in a checkpoint or in the reducer.
   - **A limit, stated:** `resume(checkpoint, tail)` sees nothing before the checkpoint, because a checkpoint is a value (D-157 item 4), so a repeat of an event from before it is not seen there. This is the
     same limit as the applied `event_id` set (D-038). For a log that replays, which is what a checkpoint is taken from, `checkpoint + tail == full replay` holds at every sequence (tested).
   - **`ExecutionRecord.repeated_step_events` was removed:** it counted repeats while the reducer could not refuse them, and a replayed log now has none.
   - **Not refused, because the ruling covers repeats only:** a `NODE_STARTED` after the same step's `NODE_SETTLED` (D-164, Open). A `NODE_SETTLED` with no `NODE_STARTED` is legitimate and stays accepted: a
     node that was skipped, not reached, or whose port raised is settled without a start.
2. **The payload discriminator is `event_type`.** `NODE_STARTED` and `NODE_SETTLED` carry a step `kind`, so `kind` could not also name the payload; `Literal[MissionEventType.X]` discriminates in a strict JSON
   round trip.
3. **`NODE_SETTLED` embeds the runtime's own `NodeResult` and states `dispatched` explicitly.** `eidos.state` therefore imports `eidos.runtime`, which the core-layer rule already allows. `dispatched` is what
   tells a skipped or not-reached node from one a port ran for; it is not inferred. (D-160 item 3 lists the same fields; they are nested, not flattened.)
4. **Live settlement, with reconciliation.** A node is settled the moment its work returns, so the log reads started then settled, node by node. The `NodeResult` recorded live restates the three-line mapping
   the executor applies to a port's result; after the run the recorder compares it with the run's own `NodeResult` and reports any disagreement (`RecordedRun.discrepancies`) instead of hiding it. A test
   runs the real executor over every work status and verdict and compares the two mappings, so a change to either fails it.
5. **A port that raises is settled after the run.** The wrapper lets the exception pass unchanged and records nothing live; the executor's own `FAILED` result is recorded after the run, together with the
   duration and the model calls observed before the raise. A model call that itself raises is not recorded as a call: D-135 item 4 makes provider failures typed results that are never raised, so a raise is
   a port fault, and the log holds no fact for it.
6. **`PLAN_REJECTED` changes only `state_version` and `updated_at`.** The refused plan stays in `plans` and `active_plan_id` stays absent; the rejection's stage and reasons live in the event.
7. *(Moved to **D-163**, resolved: D-158 item 1 was amended to say the admission guard is not wrapped.)*
8. **`EventProposal` reuses `UtcDateTime` from `eidos.contracts._validators`,** the same validator the envelope uses, so a naive or non-UTC time is refused the same way.
9. **The mission's `status_reason` is written by the reducer:** `finished and verified`; `finished without a successful VERIFY (verified is false)`; `<cause>: <reason>` for a failure; the halt's reason for a
   pause. `MISSION_FAILED` carries a cause and a reason and no `step_id` (D-160 item 3 gives it none).
10. **`ExecutionRecord` (D-159) as built.** It is a function, `execution_record(records)`, that returns a record or the replay's typed rejection, an equivalent form of D-159's `ExecutionRecord(log)`; it
    replays first, so a log the reducer would refuse, or one that repeats a step event, never yields a record. The plan it describes is the active plan, else the last generated. `run_outcome` is derived from the terminal
    event and is absent when the plan or the run was refused before anything ran. `responses_missing_token_counts` counts responses that reported no prompt or no output token count, so the folded token counter's lower
    bound is visible; a failed call carries no provider facts by design (D-150) and is not counted there. `first_occurred_at` and `last_occurred_at` are those of the first and last record by sequence, never a
    minimum or a maximum.

- **Effect:** `eidos.state.step_events` (the key and the check), the intake and the fold as described, and the tests in `test_state_step_events.py`, with the reducer, projection, recording and scenario tests adjusted.
  D-155 item 2's six outcomes and D-157's contract are unchanged except that the intake also refuses a repeated step event. `MissionState`, `MeasuredFacts`, the V0.1 envelope and the runtime are untouched.
- **Not touched:** D-151 stays Open; no per-node state was added anywhere.

---

### D-163 — D-158 item 1 amended: the recorder does not wrap the admission guard

- **Status:** Accepted · **Date:** 2026-09-21 · **Decided by:** human owner · **Resolves the conflict found while checking D-162 against the Accepted decisions** (originally Open)
- **Source:** D-158 item 1, D-160 items 1 and 8, D-162 (its former item 7)
- **The conflict, as recorded:** D-158 item 1 listed the admission guard among the injection points the recording adapters wrap ("the agents, the verifier, the admission guard and the model port"), while
  D-160 item 1 fixes the event order, in which `MISSION_PAUSED` is **last**, after a `NODE_SETTLED` for every node that was not reached. A guard wrapper sees each admission decision as it is made, so the
  only event it could propose at a halt is `MISSION_PAUSED`, **before** the settlements of the not-reached nodes, which exist only when the run ends; and the only other thing it could record, each
  admission, has no event type in the vocabulary (D-154 added three types, none for admission).
- **The owner's ruling (2026-09-21):** amend D-158's wording to match the implemented recording and observer boundary. **The recorder is not redesigned and no code changed.**
- **The boundary, as amended in D-158 item 1 and as built:**
  - the recording adapters **wrap the agents, the verifier and the model port**, and propose events to the log;
  - the plan-stage events (the plan, and the result of each gate) come from the optional, observational **`observer` hook on `run_baseline`** (D-160 item 8);
  - **the admission guard is not wrapped or observed:** a halt is read from the run's result (`RunResult.halt`) after the run and recorded as `MISSION_PAUSED` after the not-reached nodes are settled, which is
    D-160 item 1's order. The halt's step, level and reason are in the event; the admission-halt case is tested on both executors.
- **Effect:** documentation only. D-158 item 1 now says what was built; D-160 item 1's order stands; D-155, D-157, D-159 and D-162 are unaffected. Nothing in `eidos.recording`, `eidos.baseline` or the runtime
  changed.

---

### D-023 — A2A implementation: SDK, version, transport

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner · **Resolved by D-171** (originally Open) · **Source:** handoff §8, §51, §76
- **Finding:** A2A (Agent2Agent) is named as the agent protocol and §8 specifies the conceptual
  mapping (`agent_id`, `a2a_task_id`, `a2a_context_id`, `status`, `latest_artifact`, `last_event`),
  but no SDK, protocol version or transport is named.
- **Needs:** A choice before V0.6. Related to D-011, since the wire format determines what ordering
  guarantees are actually available.
- **Resolution (V0.6, 2026-09-22):** resolved by **D-171.** A hand-rolled client over `httpx` and the existing `pydantic` dependency speaks the published A2A v1.0 JSON-RPC wire format directly; no `a2a-sdk`
  dependency is added. The EIDOS surface is exactly `message/send`, `tasks/get` and receiving one webhook shape, with protocol conformance tests required.

### D-035 — Do A2A events carry a producer-assigned per-`a2a_task_id` sequence?

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner · **Resolved by D-172, negatively** (originally Open) · **Source:** handoff §10 · **Split out of D-011, left Open by the owner**
- **Finding:** D-011 adopts the layered model in principle but scopes V0.1 to identity plus an
  EIDOS-assigned mission sequence. Whether remote events additionally carry a producer-assigned
  per-task sequence — layer 3 of the model — is deferred. A producer-assigned value is only
  trustworthy for detecting ordering within that producer's own stream, which is the sole use it
  would have.
- **Effect while Open:** none on V0.1. Blocks V0.6 lateness detection for remote tasks.
- **Needs:** Owner decision at V0.6, informed by **D-023** (the A2A wire format determines what
  ordering guarantees are actually available to carry).
- **Resolution (V0.6, 2026-09-22):** resolved by **D-172**, in the negative. Verified directly against the published A2A specification: no producer-assigned sequence field exists on the webhook delivery path
  at all — the spec defines no ordering, retry or deduplication guarantee there. Lateness and duplication are instead detected by `event_id` (D-011, unchanged) plus a legal-transition guard over the
  `AgentTask` lifecycle (D-166), the same structural pattern D-162 already proved for local node events.

### D-036 — The `AgentTask` lifecycle state machine

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner · **Resolved by D-166** (originally Open) · **Source:** handoff §10 vs §8 · **Split out of D-011, left Open by the owner**
- **Finding:** §10 mandates that late and out-of-order events be "validated against lifecycle" and
  accepted or rejected **deterministically**. §8 gives `AgentTask` a `status` field but **never
  enumerates the states or the legal transitions**. Without that state machine, "validate against
  lifecycle" has no defined content and "deterministically" cannot be satisfied.
- **Effect while Open:** none on V0.1, which has no remote tasks. **Blocks V0.6 protocol tests for
  late event, out-of-order event, agent restart and partial artifact** (§50, §63) — those tests
  cannot be written against an unspecified lifecycle without encoding the decision silently.
- **Needs:** The state set and the legal transition table, including which states are terminal and
  what an event arriving for a terminal task does.
- **Resolution (V0.6, 2026-09-22):** resolved by **D-166.** `AgentTask.status` is the real ten-value wire `TaskState` set (nine states verified against the published A2A specification, plus EIDOS-observed
  `TIMED_OUT`), never collapsed early; a separate, explicit mapping to `NodeStatus` is where EIDOS's own decision about each state lives. The legal-transition table this finding anticipated turns out
  narrower once built: V0.6 records only a task's first acknowledgment and its terminal outcome (D-174), so **D-172**'s guard needs only "at most one `STARTED`, at most one `COMPLETED`, per `a2a_task_id`" —
  the same shape D-162 already built for local node events, not a full nine-state transition validator.

### D-037 — One common event shape, or separate internal and external shapes?

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner · **Resolved by the shape already built for V0.5** (originally Open) · **Source:** handoff §10 vs §33 · **Split out of D-011, left Open by the owner**
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
- **Resolution (V0.6, 2026-09-22):** resolved by the shape D-153/D-154 already built for V0.5, now confirmed sufficient for V0.6 without change — a **third** option beyond this entry's original two.
  `MissionEvent`'s envelope is fully shared across every event type and carries no protocol-specific field at all; `a2a_task_id` and every other A2A-specific field live only inside the `A2A_TASK_STARTED`/
  `A2A_TASK_COMPLETED` payloads (D-174), never on the envelope. One wholly generic envelope, plus payloads that vary per type and carry nothing the envelope doesn't need.

### D-126 — `MissionEvent` vocabulary for local node lifecycle events

- **Status:** Accepted · **Date:** 2026-09-21 · **Decided by:** human owner · **Resolved by D-154** (originally Open) · **Source:** handoff §33; invariant 15; D-067, D-075, D-076, D-090, D-123; raised in V0.3 exploration
- **Finding:** §33 says every meaningful execution event should be structured, and invariant 15 makes
  replay from recorded events a requirement. D-090 fixed the vocabulary at exactly the thirteen §33
  types. None of them represents a **local** node — a work step run by a locally hosted agent, or a
  `VERIFY` step — being started, completed, failed, skipped or not reached. The `A2A_TASK_*` types
  describe remote tasks; `VERIFICATION_FAILED` exists but there is no type for a verification that
  passed or was inconclusive; and `MissionEvent` has no payload (D-067; D-075 and D-076 Open), so the
  existing types cannot carry the distinction either.
- **Effect while Open:** V0.3 emits no events (D-123) and invariant 15 is not exercised. Any later claim
  that local execution is replayable is blocked until this is decided.
- **Needs:** whether to add event types, to carry lifecycle in typed payloads (D-075), or something
  else. Any change to the thirteen types supersedes D-090's "exactly thirteen" and needs its own
  decision. Material at V0.5 (reducer, replay) or wherever local node events are first recorded.
- **Resolution (V0.5, 2026-09-21):** resolved by **D-154.** `MissionEventType` gains `NODE_STARTED`, `NODE_SETTLED` and `MISSION_PAUSED` (sixteen types); D-090's "exactly thirteen" is superseded in
  part; local nodes are not `AgentTask`s.

### D-039 — The reducer signature

- **Status:** Accepted · **Date:** 2026-09-21 · **Decided by:** human owner · **Resolved by D-155** (originally Open) · **Source:** handoff §9, §10 · **Split out of D-010a, left Open by the owner**
- **Finding:** §10 requires duplicates to be ignored and late or out-of-order events to be accepted
  or rejected **deterministically**. A signature of `(state, event) -> state` makes a rejection
  indistinguishable from a no-op, leaving §33's telemetry nothing to count and making the
  determinism requirement untestable. A signature returning state **plus an outcome** makes it
  observable. Raising on duplicate or late events was considered and is a poor fit: §10 treats both
  as expected traffic rather than errors, and exceptions would be awkward to drive from a replay
  loop.
- **Effect while Open:** none on V0.1 — the reducer is V0.5 work; V0.1 needs only the contract.
- **Needs:** Decide at V0.5, alongside the reducer itself.
- **Resolution (V0.5, 2026-09-21):** decided by **D-155.** The reducer returns the new state **and an outcome**; expected traffic — duplicates, late and out-of-order events — is an outcome, never
  an exception.

### D-010b — Checkpoint semantics

- **Status:** Accepted · **Date:** 2026-09-21 · **Decided by:** human owner · **Resolved by D-157** (originally Open) · **Source:** handoff §9, §11 · **Split out of D-010; deliberately not resolved**
- **Finding:** §11 lists checkpoints among LangGraph's responsibilities and §9's diagram terminates
  at "LangGraph checkpoint/state", but checkpoint **granularity**, **trigger** and **contents** are
  never specified. D-010a settles the MissionState field set; it does not settle what a checkpoint
  is.
- **Effect while Open:** none on V0.1. Blocks V0.5.
- **Needs:** What a checkpoint contains, when one is taken, and whether resuming from a checkpoint
  replays events forward from it or restores a snapshot directly. Entangled with **D-017**.
- **Resolution (V0.5, 2026-09-21):** decided for V0.5 by **D-157.** A checkpoint is a value — the mission state and the last applied sequence — taken only when the caller asks and never
  automatically. Resuming restores it and applies the events after its sequence, and the tested invariant is that a checkpoint plus the tail equals a full replay. It is not a LangGraph
  checkpointer, and where a checkpoint is stored stays with **D-017 (Open)**.

---

### D-165 — Non-blocking execution shape for a remote work node

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner
- **Source:** D-118, D-122; invariants 2, 9 and 10; the V0.6 exploration
- **Decision:**
  1. **`WorkStatus` gains `SUBMITTED`.** A work node's port has dispatched the work and does not yet know the outcome. It carries **no artifact and no reason field beyond a short, generic description** ("dispatched; outcome pending") — the same shape discipline `FAILED`/`NO_RESULT` already have, and **nothing protocol-specific**: `eidos.runtime` stays vendor- and protocol-free (invariant 9), so `WorkResult.SUBMITTED` carries no `a2a_task_id` and no correlation handle of any kind. Which remote task a submitted node belongs to is answered one layer up, in `eidos.state`, which already names `a2a_task_id` at the contract level (`AgentTask`, D-048) and is where `A2A_TASK_STARTED`'s payload carries it (D-174).
  2. **`NodeStatus` gains `AWAITING`.** A node the run dispatched but whose outcome is not yet known. Not `NOT_REACHED` (which means never dispatched because the run halted) and not any of the other six.
  3. **`RunOutcome` gains `AWAITING`**, taking precedence over `FINISHED`/`FAILED` the same way `HALTED` already does (D-118 rule 4).
  4. **`RunResult` gains `awaiting: tuple[AwaitingInfo, ...]`** (default empty), **not a single optional value.** Unlike a `HALT` — which the executor's own design makes single-node (the run stops at the first one, D-117) — more than one node in the same level can independently return `SUBMITTED` (if more than one compiled node requests the remote-backed capability), so every outstanding node must be named, not just the first. `AwaitingInfo` is `(step_id: StepId, level: int, reason: str)`, mirroring `HaltInfo`'s shape but deliberately carrying **no protocol-specific field** for the same layering reason as rule 1.
  5. **The submission call itself stays synchronous**, exactly as D-122 already requires of every port: `WorkAgent.run()` makes one ordinary blocking call (in A2A's case, one HTTP round trip that returns a server-assigned task id **synchronously** — verified against the published spec, not assumed), then returns `SUBMITTED` immediately. It is only **completion** that becomes asynchronous. D-122's "ports are synchronous" is not violated: every port call still returns before the run needs it to.
- **Consequences:** `RunResult`'s consistency validator gains one more branch (an `AWAITING`-status result is accounted for in `awaiting`, exactly as a `NOT_REACHED` one is accounted for in `halt`'s absence check). Nothing about a purely local mission changes: `SUBMITTED`/`AWAITING` are reachable only when a port actually returns them, and no V0.4 agent does.
- **Affects:** D-118 (exactly seven `NodeStatus` / exactly three `RunOutcome`, both extended by one), D-122 (unchanged in kind — still synchronous ports, still exactly one call per dispatch).

### D-166 — `AgentTask.status` preserves the real A2A `TaskState` vocabulary; a separate typed mapping to `NodeStatus` (resolves D-036)

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner
- **Source:** D-036, D-081; the A2A Protocol Specification v1.0 (a2a-protocol.org), verified 2026-09-22; invariant 12 ("verification is separate from completion" — the parallel principle applied here: *recording* the remote's state is separate from *what EIDOS does about it*)
- **Decision:**
  1. **`AgentTask.status` is the closed, ten-value set:** the real wire `TaskState` — `SUBMITTED, WORKING, INPUT_REQUIRED, AUTH_REQUIRED, COMPLETED, FAILED, CANCELED, REJECTED, UNSPECIFIED` — **plus one EIDOS-observed value, `TIMED_OUT`**, which no wire message ever carries; it is what the adapter itself concludes when no terminal report arrives within its own configured deadline (D-173 item 2). This **resolves D-036** and **D-081** (the opaque string is replaced by this enumeration) without inventing a smaller vocabulary: the remote's exact reported state is preserved, never collapsed early, matching the project's existing habit of carrying a verifier's or a model's exact wording through unmodified (D-146's `NOT_EVALUATED` clauses, D-150's failure messages).
  2. **A separate, explicit, tested mapping from this ten-value set to the seven-plus-`AWAITING` `NodeStatus` set** (D-165) is the only place EIDOS's own decision about "what this means for the node" lives — the same two-tier pattern already used twice in this codebase: `ModelFailureKind → WorkResult.status` (in `eidos.agents.base.ask_model`) and `VerificationVerdict → NodeStatus` (`_VERDICT_STATUS` in `eidos.recording.adapters`). Proposed mapping, to be pinned by tests at implementation exactly as D-118's own "intended meaning" was:
     - `COMPLETED` → `SUCCEEDED` if a usable artifact was produced, else `NO_RESULT` (a completed task with no result is possible under the protocol — "returns either a task... or a direct response message" — and is not a failure);
     - `FAILED`, `CANCELED`, `REJECTED`, `TIMED_OUT` → `FAILED`, each preserving the exact wire state name in `NodeResult.reason` so nothing is lost;
     - `INPUT_REQUIRED`, `AUTH_REQUIRED` → `FAILED`, with a reason stating plainly that the V0.6 boundary does not support an interactive/authenticated remote task — a scope limit, stated honestly, never silently ignored (this is not the Research Agent's expected behaviour, D-140, but the mapping must exist for whatever the remote genuinely reports);
     - `SUBMITTED`, `WORKING`, `UNSPECIFIED` → no terminal mapping; the node stays `AWAITING` (these never produce an `A2A_TASK_COMPLETED` event at all — see D-174).
  3. **No new `MissionFailureCause` member.** A remote-caused `FAILED` node folds into the existing `EXECUTION_FAILED` cause, exactly as a local port fault does — the existing catch-all already fits.
- **Consequences:** `AgentTask` becomes fully typed with no branch-on-opaque-string anywhere (discharging D-081's stated reason for keeping `status` opaque). Nothing about the *reachable* states changes if the remote never reports `INPUT_REQUIRED`/`AUTH_REQUIRED`/`CANCELED`/`REJECTED` — the mapping exists for correctness, not because V0.6 expects to exercise every branch.
- **Affects:** resolves **D-036**; discharges **D-081**'s deferral; extends the two-tier mapping pattern already established by D-135/D-121.

### D-167 — One continuous `EventLog` across the asynchronous pause/resume boundary

- **Status:** Accepted, subject to D-176 · **Date:** 2026-09-22 · **Decided by:** human owner
- **Source:** invariant 15; D-120, D-157; the V0.6 exploration, checked directly against the shipped `eidos.state`/`eidos.recording` code
- **Decision:** a mission that pauses `AWAITING` a remote task and later resumes stays **one log**, not two. Confirmed against the actual code that this needs **no new plumbing**: `record_baseline(..., log=...)` already accepts an existing `EventLog`, and `Recorder` already takes one in its constructor with no other state that must survive between calls. The caller (D-170) keeps `RecordedRun.log` after a pass returns `AWAITING`, and when the remote task settles: (1) builds a short-lived `Recorder` around that same log and calls `.record(A2ATaskCompletedPayload(...))` directly, then (2) builds `PriorOutcomes` including the newly-known result and calls `record_baseline(..., log=the_same_log, prior=...)` again, which naturally produces the post-hoc `NODE_SETTLED` and, if nothing else is outstanding, the mission's real terminal event — entirely through machinery that already exists.
- **What this needs, precisely (the only things that change):** (a) `run.py`'s `_finish()` gains one new branch, parallel to its existing `HALTED`/`FINISHED`/`FAILED` branches, for `RunOutcome.AWAITING` → `MissionPausedPayload` carrying `awaiting` (D-169); (b) the reducer's terminal check must stop refusing *every* event once `status == PAUSED` — **this is D-176**, and D-167 cannot be finalized in code before D-176 is. `checkpoint_at`, `resume`, `records_after`, the JSONL round trip and `execution_record` need **no change at all** — they are already generic over an arbitrarily long-lived, arbitrarily-many-events log.
- **Consequences:** invariant 15 is satisfied for the *whole* mission, including the paused stretch, not just per attempt — a fuller reading than V0.5's admission-halt case needed, since that pause is (by design, D-160 ruling 4, unamended for that cause) never reopened.
- **Affects:** D-120 (unchanged — still the resume mechanism), D-157 (unchanged — still one log, still a value-checkpoint), **D-176** (the precondition).

### D-168 — `AgentTask` gains `plan_id`, `step_id` and `started_at`

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner
- **Source:** D-048; the V0.6 exploration
- **Decision:** three fields are added to `AgentTask`, all optional, all additive:
  - **`plan_id: PlanId | None`, `step_id: StepId | None`** — correlate the mirrored remote task to the plan node it serves. Without them nothing ties an `AgentTask` entry to a compiled node at all.
  - **`started_at: UtcDateTime | None`** — the `occurred_at` of the `A2A_TASK_STARTED` event that created this entry, carried forward so that when `A2A_TASK_COMPLETED` later replaces it (D-176's new reducer operation), the reducer can compute elapsed wall-clock duration by subtracting two envelope timestamps it already has — **no new duration field on the payload, and no monotonic-clock subtraction across a possible process restart** (D-173 item 2's instruction, satisfied exactly).
  - **Checked against D-048, D-033, D-082, D-095, D-096, D-098 — no contradiction found.** D-048 explicitly anticipated additive fields ("kept minimal and future-compatible for V0.6"); D-033 (no `tenant_id`) is untouched; D-082 fixes `agent_tasks`'s *type* (an immutable tuple) not the rule that transforms it (see D-176); D-095/D-096/D-098 are untouched by this addition.
- **Consequences:** every existing `AgentTask` construction (there are none yet outside tests, since V0.1–V0.5 never populate this field) is unaffected; the three new fields default to absent.
- **Affects:** D-048 (extended, not redefined).

### D-169 — `MissionStatus.PAUSED` is reused for "awaiting a remote task"; `MissionPausedPayload` names which kind

- **Status:** Accepted, subject to D-176 · **Date:** 2026-09-22 · **Decided by:** human owner
- **Source:** D-052; D-160 items 3 and 10 (`MISSION_PAUSED`'s existing `HaltInfo` shape); the V0.6 exploration
- **Decision:** no fifth `MissionStatus` is added (D-052's "no additional in-progress states invented" stands untouched). `MissionPausedPayload` carries **exactly one of two** shapes, matching the codebase's existing "exactly one of two" idiom (`ReplayResult`, `LoadResult`):
  - `halt: HaltInfo` — an admission-guard pause, unchanged from V0.5 in every respect: still terminal (D-160 ruling 4, unamended for this cause), still one node (the executor's own halt-is-single-node design).
  - `awaiting: tuple[AwaitingInfo, ...]` (non-empty) — an A2A-awaiting pause (D-165's `AwaitingInfo`), possibly naming more than one outstanding node, and **the one exception to `paused`-is-terminal** (D-176).
  `status_reason` continues to carry the human-readable explanation, exactly as D-052 already anticipated.
- **Consequences:** `HaltInfo` itself is untouched — reused exactly as V0.5 shipped it, never generalized or overloaded to also describe an A2A wait, which would have blurred two genuinely different kinds of pause.
- **Affects:** D-052 (reused, not extended), D-160 (item 3's payload shape gains the second variant; item 9/ruling 4 amended narrowly by **D-176**).

### D-170 — Caller-orchestrated resume; no built-in mission driver in V0.6

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner
- **Source:** D-119, D-020, D-127, D-161 ("a planner and the mission driver loop... not assigned to a milestone"); the V0.6 exploration
- **Decision:** V0.6 builds no component that watches for a remote task's completion and re-invokes the runtime on its own. Confirmed workable directly from the shipped D-120 resume mechanism (§ D-167): the whole "wait, then continue" story is exactly two ordinary calls a caller makes — append one event, then call `record_baseline` again — needing no new persistent process, thread or loop inside EIDOS. Building such a loop would be pulling forward part of the still-unassigned mission driver (D-119/D-020), which nothing in V0.6's scope requires.
- **Consequences:** the A2A adapter (`eidos.a2a`) provides the pieces (a client, a webhook receiver, the payload construction) but never itself decides *when* to resume a mission — that is the calling application's responsibility, exactly as it already is for every existing use of `record_baseline`.
- **Affects:** none of D-119/D-020/D-127 is resolved or narrowed; they stay exactly as unassigned as before.

### D-171 — A2A transport: a hand-rolled client over `httpx`, not `a2a-sdk`; protocol version A2A v1.0 (resolves D-023)

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner
- **Source:** D-023, D-136 (the precedent against a new vendor dependency where the wire protocol is speakable directly); researched directly against the published A2A Protocol Specification (a2a-protocol.org, v1.0 current stable, Linux Foundation-hosted) and the `a2a-sdk` package's actual `pyproject.toml` (github.com/a2aproject/a2a-python), 2026-09-22
- **Decision:**
  1. **No new SDK dependency.** `eidos.a2a` speaks the published JSON-RPC 2.0 wire format directly, using `httpx` (one new, narrow dependency) and the `pydantic` EIDOS already requires. `a2a-sdk`'s core install alone pulls in `protobuf`, `google-api-core`, `googleapis-common-protos`, `json-rpc` and `culsans` beyond `httpx`/`pydantic` — verified from its actual dependency list — for a surface EIDOS only needs a thin, exact slice of (submission, an optional poll, receiving one webhook shape). This follows D-136's precedent rather than repeating it verbatim: A2A's JSON-RPC-plus-task-lifecycle-plus-webhook-config surface is genuinely more complex than Ollama's completion endpoint, so EIDOS **owns getting the schema right** and re-verifying it if the protocol version moves — an explicit, accepted cost, not an oversight.
  2. **The EIDOS A2A surface stays exactly:** `message/send` (submission — the only call that must return the task id synchronously, per the spec), `tasks/get` (polling, only if a webhook is unavailable or as a reconciliation check), receiving one HTTP POST at a configured webhook URL, and the typed `Task`/`TaskStatus` payload shapes the spec defines. Nothing else — no streaming (SSE), no `tasks/cancel`, no push-notification-config management beyond registering the one webhook EIDOS needs.
  3. **Protocol version: A2A v1.0**, the current stable spec, targeted directly (not the compatibility-mode 0.3 shim `a2a-sdk` offers, which EIDOS has no reason to need since it isn't using that SDK).
  4. **Protocol conformance tests are required**, validating EIDOS's hand-rolled request/response construction and parsing against the published schema — independent of and in addition to the D-166/D-172 lifecycle tests in `tests/protocol/`. **EIDOS invents no protocol detail**: every field name, every state name and every rule cited in D-165–D-176 traces to the verified spec text, not to an assumption.
- **Consequences:** `eidos.a2a`'s dependency footprint is `httpx` alone, beyond what EIDOS already requires. The risk this accepts (owning schema correctness, re-verifying on a protocol version bump) is explicit and recorded, not hidden.
- **Affects:** resolves **D-023** in full (SDK, version and transport all pinned); **D-136** cited as precedent, not extended (Ollama's provider is untouched).

### D-172 — No producer-assigned sequence (resolves D-035); idempotency and lateness are `event_id` plus a legal-transition guard

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner
- **Source:** D-011, D-035; the A2A Protocol Specification, verified 2026-09-22; D-162 (`step_events.py`) as the direct structural precedent
- **Decision:**
  1. **No producer-assigned per-task sequence is adopted, because none exists to adopt.** Verified directly against the spec: a push-notification (webhook) delivery carries no event/delivery id distinct from `taskId`, and the specification explicitly defines no ordering, retry or deduplication guarantee for that path (only the SSE streaming path — not used here, D-171 item 2 — has a MUST-preserve-order guarantee). **D-035 is resolved in the negative.**
  2. **Two layers, both already-established patterns, neither new in kind:**
     - **Identity (D-011, unchanged):** the adapter's own `event_id` (from the same injected `IdSource` V0.5 already has) is the idempotency key for the *EIDOS-side proposal*, exactly as for every other event.
     - **Legal-transition guard (new, but the same shape as D-162's, keyed differently):** because V0.6 records **only** a task's first acknowledgment and its terminal outcome (D-174 — no intermediate `WORKING` notification is ever proposed as an event, since `MissionState` has nothing new to fold from "still working"), the guard reduces to exactly what D-162 already proved: **one `A2A_TASK_STARTED` creates the `AgentTask` entry for an `a2a_task_id` that must not already exist; at most one `A2A_TASK_COMPLETED` settles it, and a second one for the same `a2a_task_id` — whether identical or not — is refused**, the same intake-level, fold-from-scratch-replays-the-same-way pattern D-162 already built and tested. This is **narrower** than the full nine-state transition table I first proposed: EIDOS never needs to validate `WORKING`/`SUBMITTED`-to-`WORKING` transitions at all, because it never records them.
- **Consequences:** `eidos.state` gains one sibling to `step_events.py` (an `agent_task_events.py`-shaped guard, keyed by `a2a_task_id`, exactly two operations: refuse-a-second-`STARTED`, refuse-a-second-`COMPLETED`), not a general state-machine validator.
- **Affects:** resolves **D-035** (negatively — nothing is adopted); D-011 unchanged; direct structural reuse of **D-162**.

### D-173 — Three separate timeout concepts, none a new `SystemLimits` dimension

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner
- **Source:** D-042, D-046; D-160 item 6; the V0.6 exploration; verified against the A2A spec (which defines no timeout/deadline/TTL concept at all)
- **Decision:** kept strictly separate, at three different layers:
  1. **Transport/network timeout** — lives entirely inside the `eidos.a2a` HTTP client's own configuration. Never a domain contract field, exactly as `OllamaModel`'s HTTP timeout isn't one.
  2. **A2A task waiting deadline** — "how long EIDOS's adapter will wait for a terminal report before declaring `TIMED_OUT`" (D-166). Lives in `eidos.a2a`'s own adapter-level configuration, **not** `SystemLimits` or `ReliabilityContract` — D-042 already closed the mission-level budget group at exactly six dimensions, and this stays outside core domain contracts entirely, per the owner's own stated constraint.
  3. **EIDOS mission execution budget** (`SystemLimits.max_execution_time`, `MissionState.execution_time_used_ms`) — unchanged in meaning. D-160 item 6's existing rule already means an `AWAITING` node contributes nothing while outstanding (it has no recorded duration yet); once it settles, its contribution is computed from **`occurred_at` timestamps** between its `A2A_TASK_STARTED` and `A2A_TASK_COMPLETED` events (D-168's `started_at` field makes this a plain subtraction the reducer can do), **not** the recorder's monotonic clock, which cannot be safely compared across a possible process restart between submission and completion.
- **Consequences:** no seventh `SystemLimits` dimension; D-042/D-046 untouched. A remote node's `duration_ms`-equivalent contribution is measured differently in kind (wall-clock, cross-process-safe) from a local node's (monotonic, single-process) — a real, disclosed difference, not a silent inconsistency.
- **Affects:** extends D-160 item 6's rule to a second measurement method for the one case it's needed; D-042, D-046 untouched.

### D-174 — Exactly two A2A event types; completion carries a typed outcome, never split further

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner
- **Source:** D-090, D-154, D-160 item 2 (the precedent for not splitting an outcome into separate event types); the V0.6 exploration
- **Decision:** exactly the two `MissionEventType` members V0.1 already reserved (D-090) are used — **no new member is added**:
  - **`A2A_TASK_STARTED`** — `plan_id`, `step_id`, `agent_id`, `a2a_task_id`, `a2a_context_id`. Proposed once, at submission, alongside the existing `NODE_STARTED`.
  - **`A2A_TASK_COMPLETED`** — `plan_id`, `step_id`, `a2a_task_id`, a typed `outcome: AgentTaskStatus` (the ten-value set from D-166), `artifact: ArtifactRef | None`, `reason: str`. Proposed once, whenever the task reaches a terminal outcome (including EIDOS-observed `TIMED_OUT`) — mirroring exactly how the real protocol itself reports outcome as one field's value, never a different message per outcome, and matching `NODE_SETTLED`'s own precedent (one type, a typed payload) rather than inventing `A2A_TASK_FAILED`/`A2A_TASK_TIMED_OUT`/`A2A_TASK_CANCELED`.
  - **An intermediate `WORKING` (or a repeated `SUBMITTED`) notification is never proposed as an event.** `MissionState` has nothing to fold from "still not done" that it doesn't already know from the node being `AWAITING`, so the adapter observes it and does nothing with it.
- **Consequences:** the D-172 guard stays exactly two-operation-simple (§D-172); no `EmittedPayload` member beyond these two is added for A2A.
- **Affects:** none — the vocabulary slots were already reserved by D-090; only their payload classes are new.

### D-175 — Research Agent is the single A2A boundary for V0.6

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner
- **Source:** §50's own example; `docs/07_a2a_contract.md` §4 ("one boundary, not three")
- **Decision:** the Research Agent (and only it) moves behind the A2A boundary in V0.6. The Analysis and Verification agents stay exactly as they are — local, synchronous `WorkAgent`/`Verifier` implementations, unchanged.
- **Consequences:** `docs/07_a2a_contract.md`'s open question on this point is closed.
- **Affects:** none — purely a scope statement.

### D-176 — D-160 ruling 4 amended: `PAUSED` stays terminal for an admission-guard halt; an A2A-awaiting `PAUSED` is resumable on the same log; a new reducer operation, "find by correlation key and replace," is named for `agent_tasks`

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner
- **Source:** D-160 ruling 4 ("`paused` stays terminal in V0.5; resume is deferred"); the reducer's `_TERMINAL` check (`eidos.state.reducer`); D-167, D-169; the V0.6 exploration, which found this contradiction directly against the shipped code and stopped rather than resolving it silently
- **The contradiction found (and reported, not resolved, at the time):** D-167 (one continuous log across an async pause) and D-169 (reuse `PAUSED` for that pause) together require the reducer to accept further events after `status == PAUSED` for that one cause — but D-160 ruling 4, as shipped, and the reducer's `_TERMINAL = (COMPLETED, FAILED, PAUSED)` check, refuse **every** event once `status == PAUSED`, unconditionally, for **any** cause.
- **The owner's ruling (2026-09-22):** amend D-160 ruling 4 **narrowly**. `PAUSED` caused by an admission-guard halt (`MissionPausedPayload.halt` present) **stays terminal, exactly as V0.5 shipped it** — resume-after-human-review-halt is still genuinely undecided policy and nothing here changes that. `PAUSED` caused by an A2A-awaiting pause (`MissionPausedPayload.awaiting` present, D-169) is **resumable**: the reducer accepts a subsequent `A2A_TASK_COMPLETED` (and whatever it triggers) on the **same** log. **No fifth `MissionStatus` is added. The V0.5 state machine is not redesigned** — this is the one, cause-keyed exception, not a new mechanism, following the same amendment style already used once this project for D-158 (amended by D-163): the original ruling's text is kept, and this amendment is recorded beside it rather than silently rewritten.
- **The new reducer operation, named explicitly:** folding `agent_tasks` needs a **third** pattern, distinct from the two the reducer already has (*append-only*, for `plans`; *first-wins, refuse the repeat*, for node settlement via D-162). `AgentTask` genuinely changes over its own lifetime — the same record moves `SUBMITTED → ... → COMPLETED` — so the rule is: **find the existing `AgentTask` entry whose `a2a_task_id` matches the incoming event's, and produce a new tuple with that one entry replaced** (`A2A_TASK_STARTED` instead *appends* a new entry, since no matching `a2a_task_id` can already exist — D-172's own guard already refuses a second `STARTED` for one). `MissionState.agent_tasks` **remains an immutable tuple** (D-082, untouched — its *type* was never in question); only the rule that transforms it from one state to the next is new. This is not a contradiction of D-082, and is recorded here precisely so it is visible before it is written, not discovered mid-implementation.
- **Consequences:** the admission-halt case is **byte-for-byte unchanged** — same tests, same behaviour, same "the pause is not reopened" guarantee V0.5 shipped and pushed. Only a *new* cause of `PAUSED`, which did not exist before this decision, gets different treatment.
- **Affects:** amends **D-160** ruling 4 (narrowly, in the same style D-163 already used on D-158); **D-052** is untouched (still exactly four `MissionStatus` values); **D-082** is untouched (still an immutable tuple; only the fold rule is new); resolves the tension between **D-167** and **D-169**, which are now both final.

### D-177 — A2A completion makes a paused mission resumable; it does not itself resume it. Resumption is a distinct, explicit `EventLog` operation that reads the log's own history, not a `MissionState` field

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner
- **Source:** D-176, D-167, D-170; `eidos.state.reducer`/`eidos.state.log`/`eidos.state.replay` (V0.6 Step 4, already committed at `7f69e87`); the V0.6 Step 5 report, which found this gap directly against the shipped code and stopped rather than resolving it silently
- **The gap found (and reported, not resolved, at the time):** D-176 lets a `paused` mission accept exactly one `A2A_TASK_COMPLETED`, and that event folds only `agent_tasks`, never `status` — so `MissionState.status` stays `paused` after it, unconditionally, by design. But nothing in the shipped design then let a caller record *any further* event (the newly-unblocked nodes' `NODE_STARTED`/`NODE_SETTLED`, the eventual terminal event) on the same log: the reducer's terminal check refused them exactly as it refuses anything after any other terminal status. D-167 had explicitly described the opposite — recording pass 2's events "naturally produces the post-hoc `NODE_SETTLED` and ... the mission's real terminal event — entirely through machinery that already exists" — but that machinery did not exist.
- **Why `MissionState` alone cannot fix this:** the only way to tell a genuinely resumable awaiting-pause apart from a permanently terminal admission-guard halt, later in the mission's life, is to know *which* pause most recently happened — and `MissionState` deliberately carries no such field (D-176 named only the `agent_tasks` fold as new, and this ruling does not reopen that). A fix keyed only on `MissionState.agent_tasks` (e.g. "resume once nothing is outstanding") was checked and found to be **wrong**: it cannot distinguish an admission-halt-paused mission that happens to *also* have an independently outstanding A2A task (D-176's own worked case) from a genuinely resolved awaiting pause — both look identical in `agent_tasks` once the outstanding task concludes, and the former must never become resumable. Only the event **log's own history** — which `MissionState` is deliberately not — can tell them apart.
- **The owner's ruling (2026-09-22):** resumption is a **new, narrow, explicit operation**, not a change to `MissionState`, `MissionStatus`, `reduce()`, `accept()`, or D-176's `A2A_TASK_COMPLETED` handling, all of which are unchanged:
  1. **`EventLog.accept_resumed(proposal)`** (sibling to `accept`, same `IntakeResult` shape) is the caller's explicit resume. It requires `MissionState.status == PAUSED`; finds the mission's actual most recent `MISSION_PAUSED` record in the log's own history (`most_recent_pause`); refuses outright, unconditionally, if that pause's cause was `.halt` (D-176's terminality, never reopened, regardless of any A2A activity before or after); otherwise requires every step its `.awaiting` named to now show a concluded `AgentTask` (`resumable_pause`, via the same `node_status_for` mapping the reducer's own fold already uses). Only then does it fold the proposal, through the same D-162/D-172 repeat-guard bookkeeping `accept` itself uses.
  2. **`reduce_resumed(state, record, applied)`** (sibling to `reduce`, sharing every check with it but one, via a shared internal `_reduce`) is the only thing `accept_resumed` folds through: it differs from `reduce` in exactly one respect — a `paused` mission is not refused *for that reason alone*. `completed`/`failed` remain refused, unconditionally, exactly as `reduce` refuses them; duplicate, identity, sequence and the event's own fit are the identical checks, not forked.
  3. **`MissionState.status` stays `paused` through the whole resumed round** — it changes only when an ordinary `MISSION_COMPLETED`/`MISSION_FAILED`/`MISSION_PAUSED` event next sets it, exactly as it always has. No fifth `MissionStatus` (e.g. `RESUMABLE`) is added, and none is needed: `status` never has to distinguish "paused, still waiting" from "paused, now resumable" — `most_recent_pause` plus `resumable_pause`, evaluated fresh from the log's own history at the moment of the call, already do.
  4. **Nothing is automatic.** `accept_resumed` is never called by anything inside `eidos.state`; a caller invokes it exactly when it chooses to, the same caller-orchestrated discipline D-170 already established for the whole "wait, then continue" story. `A2A_TASK_COMPLETED` itself never triggers it.
  5. **`replay`'s own fold (`_fold`) needed the identical rule**, found as a direct, necessary consequence while implementing this (not a reopening of D-157): a log a live caller correctly extended past a `accept_resumed` call must still replay from scratch to the same state, so `_fold` now tracks the same `most_recent_pause`/`resumable_pause` logic incrementally as it folds and switches to `reduce_resumed` under the identical condition `accept_resumed` uses — one rule, shared, not two. `checkpoint_at`/`resume` (D-157's own, unrelated "resume") inherit the same known limitation `seen`/`task_seen` (D-162/D-172) already carry: a checkpoint taken strictly inside an unresolved pause cannot fold a tail across a later `accept_resumed` call, since `resume` is never given the records before its checkpoint. To check a log end to end, replay it — unchanged advice (D-157 item 4).
- **Consequences:** the admission-halt case stays exactly as terminal as D-176 shipped it, in every test, including the one this ruling was checked against (a halt-paused mission with an independently outstanding, later-concluding A2A task: the completion is still accepted by unmodified D-176 machinery, but `accept_resumed` still refuses, because the log's history says the pause was a halt). A genuinely new admission-guard halt recorded *during* a resumed round is picked up by the next `most_recent_pause` call and makes the mission terminal again, correctly, with no extra state.
- **Affects:** narrows nothing in D-165–D-176 (all unchanged); extends D-167 (the continuous log now actually supports the flow it described) and D-170 (the caller-orchestrated resume now has a concrete, named operation). `eidos.a2a`'s own `test_a2a_scenario.py` (V0.6 Step 5), which found and pinned this gap as unresolved, now completes the full scenario it always meant to prove.

### D-178 — Strategy is a distinct object from Plan (resolves D-020)

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner · **Resolves D-020**
- **Source:** handoff §2, §13, §16, §17; `docs/03_architecture.md` §7; V0.7 Step 1 exploration
- **The question D-020 left open:** whether "Strategy" and "Plan" are the same object, or a Plan plus binding decisions the §13 DSL does not encode — left unresolved since the bootstrap read because nothing needed it decided until V0.7.
- **Decision:** they are **two distinct objects**. A `Strategy` describes execution *shape* — an abstract, capability-level description of how a mission intends to execute — and never contains a `StepId`, a dependency edge, or an agent binding. A `Plan` remains exactly what V0.1–V0.6 already built: the concrete, ID-addressed, validated DAG. A strategy may **eventually** (V0.8+, not built by this decision) expand into one or more concrete `Plan`s; a `Plan` is never itself treated as a `Strategy` and neither subsumes the other's schema.
- **Why not one object:** collapsing them would mean either bloating `Plan` with fields no validator/compiler stage reads (real concrete plans would carry unused strategy-only fields) or bloating `Strategy` with step ids and edges it does not yet have and should not invent before a strategy is selected — duplicating exactly the schema item A's own design work was told not to duplicate.
- **Consequences:** `eidos.planning` is a new core layer producing its own type, `Strategy`, the same way `eidos.compiler` produces `CompiledPlan` rather than putting it in `eidos.contracts` — precedent, not invention. Whatever later expands a selected `Strategy` into a `Plan` must still pass that `Plan` through the unmodified V0.2 validation and V0.3 compiler pipeline; a `Strategy` grants no validation or compilation shortcut, ever.
- **Affects:** D-179 (what a `Strategy` may express), D-182 (its identity). Does not reopen D-004, D-047, D-050, D-053, D-092, D-101 or any other Plan/PlanStep decision.

### D-179 — V0.7 Strategy structural dimensions, and what is explicitly excluded

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner
- **Source:** handoff §17 (the full "strategy factors" list); invariants 9 and 11; D-012, D-102, D-125, D-133; V0.7 Step 1 exploration
- **Decision:** a `Strategy` expresses only the dimensions the system can actually act on today:
  1. **Execution topology / decomposition style / parallelism** — one structural field: a sequential tuple of stages, each stage a non-empty set of capabilities that run in parallel within it (stage *i+1* depends on the whole of stage *i*). Linear chains, parallel-converge and staged shapes (the §16 Plan A/B/C examples) are all expressible as this one shape; no separate "topology kind" or "parallelism" field is added — both are read off the stage shape, never stored twice.
  2. **Verification posture** — a two-member enum, `NONE`/`FINAL`, reflecting that exactly one deterministic `Verifier` exists (D-133) and is invoked once, at the end, in every baseline built so far. Not a richer "verification approach": there is nothing yet to choose between.
  3. **Capability allocation** — which capabilities appear in the strategy, and how many times.
- **Explicitly excluded, and why each is excluded now rather than omitted by oversight:**
  - **Agent selection** — invariant 11 ("plans request capabilities, not named agents") applies to `Strategy` exactly as it applies to `Plan`; a `Strategy` never carries an `AgentId`.
  - **Model selection** — invariant 9 (no model/vendor name in contracts, planning, validation, compiler, runtime or state).
  - **Tool selection / retrieval strategy** — no MCP, no RAG exist in the codebase yet.
  - **Retry / replan / recovery posture** — D-012 (no predicate language) and D-125 (plan-level `RETRY` vs. runtime retry policy) are both still Open, and the compiler rejects `RETRY`/`REPLAN` steps outright today (D-114); there is nothing for a Strategy-level field to describe that could ever compile.
  - **Context allocation** — not expressible in any built primitive; not invented here.
- **Consequences:** the §17 "potential strategy factors" list is **not** V0.7's contract — it is the long-run aspiration; V0.7 takes only the slice the rest of the system can already support. Adding an excluded dimension later requires its own decision, once the primitive it depends on exists (D-012/D-125 resolving, MCP/RAG landing, etc.) — this entry does not pre-approve any of them.
- **Affects:** D-178 (the object this bounds), D-180 (what feasibility over these dimensions can check).

### D-180 — Strategy feasibility filtering reuses `SystemLimits`/`ReliabilityContract`; no new numeric ceiling

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner
- **Source:** `eidos.validation.stages` (`check_capabilities`, `check_complexity`, `check_resources`); D-009, D-046, D-102, D-110; V0.7 Step 1 exploration
- **Decision:** feasibility filtering over a `Strategy` (deferred to a later V0.7 step, not built by this decision) is a narrower, structural analogue of exactly three of V0.2's seven stages — CAPABILITY, COMPLEXITY and RESOURCE — reusing the **same** `SystemLimits` and `ReliabilityContract` values a `Plan` is already checked against, never a value invented for `Strategy` alone. SCHEMA/DEPENDENCY/CYCLE do not apply (a `Strategy` has no step ids or edges to be malformed, duplicated, or cyclic); POLICY stays `NOT_APPLICABLE` for the identical reason D-110 already gives.
- **Consequences:** `eidos.planning` becomes a **core layer**, joining `eidos.contracts`, `eidos.validation`, `eidos.compiler`, `eidos.runtime` and `eidos.state` — it may import `eidos.validation.limits.SystemLimits` (a new core-to-core edge, not previously drawn) and `eidos.contracts.ReliabilityContract`. It imports nothing from `eidos.agents`, `eidos.providers`, `eidos.capabilities`, `eidos.backends`, `eidos.a2a` or `eidos.recording` — determinism (invariant: no I/O, no clock, no hidden state) is preserved exactly as it is for `eidos.validation`/`eidos.compiler` today.
- **Affects:** the feasibility-checking step itself is **not implemented by this decision** — it only fixes what it may reuse and what layer it lives in, ahead of the step that builds it.

### D-181 — `max_candidates` is an explicit generation-time parameter, not a `SystemLimits` field

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner
- **Source:** CLAUDE.md §3 ("Do not generate an unbounded number of candidate strategies. Two or three."); handoff §16; D-046, D-103; `eidos.validation.limits.SystemLimits`'s own docstring ("ceilings a plan and a reliability contract are checked against"); V0.7 Step 1 exploration
- **Decision:** the ceiling on how many candidate strategies a generation round may return is **CLAUDE.md's own "two or three"** — not reopened, not re-decided here. Where the number is supplied is: a required parameter to the (not-yet-built) generation entrypoint, with **no default**, matching D-103's "no ambient configuration" discipline. It is **not** added to `SystemLimits`, because `SystemLimits` bounds a plan's shape and a mission's resource budgets — a candidate *count* at generation time is a different kind of quantity, checked before any `Plan` exists at all.
- **Consequences:** no new field is added to any existing contract by this decision. A (not-yet-built) reference generator must never pad its output to reach a target count — it emits only structurally distinct shapes and the parameter only ever truncates, never pads. The **exact** value used at any call site (2 or 3) is left to the caller, consistent with D-046's own "actual values pinned at implementation, never invented" discipline.
- **Affects:** nothing existing changes; this only fixes where a not-yet-built parameter will live.

### D-182 — `StrategyId` is a plain, UUID-backed identity; no version, no signature

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner
- **Source:** D-053 (identifier conventions), D-021 (Strategy signature / "Strategy Genome," Open, explicitly deferred); V0.7 Step 1 exploration
- **Decision:** `Strategy` carries one new identifier, `StrategyId`, UUID-backed by D-053's default (no exemption applies — it is neither planner-authored DSL text, an opaque external-system id, nor produced by a remote agent, the four reasons the existing exemptions exist). It carries **no version** (strategies are not replanned/amended in place the way `Plan` is — a fresh generation round produces fresh ids for a fresh, unrelated candidate set) and **no signature or "genome" encoding**.
- **Consequences:** **D-021 stays Open and untouched** — a bare `strategy_id` is not an answer to what a `strategy_signature` encodes or how strategies are compared for similarity; it only gives a future `STRATEGY_SELECTED`-type event (V0.8+, not built) something to reference. Strategy Memory (V1.0) is not built by this decision and needs no further contract change to eventually key outcomes by `strategy_id`.
- **Affects:** D-178 (the object this identifies). Does not resolve D-021.

### D-183 — Strategy candidate ordering: feasibility gates candidates before selection; full Plan validation runs once, only on the selected strategy's expanded Plan

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner
- **Source:** handoff §2, §83 (`... Candidate Strategy Generation → Plan Validation → Strategy Selection → Execution ...`) vs. this session's own V0.7 Step 1 target flow (`... Candidate Strategy Generation → Feasibility filtering → bounded candidate set → [V0.8 Selection] → Plan validation → execution`); V0.7 Steps 1 and 4
- **The tension found (and reported, not resolved, at Step 1):** the handoff's own fundamental-loop diagrams place PLAN VALIDATION between candidate generation and strategy selection, which reads as every candidate being expanded into a concrete `Plan` and run through the full V0.2 pipeline before anything is selected. The flow given for V0.7 itself placed "Plan validation" *after* selection, implying only the one selected strategy is ever expanded and validated. V0.7 did not need this resolved (Steps 2–4 stop at "bounded feasible candidate set," before either point), but V0.8 (Strategy Selection) would.
- **Decision:** `Generate candidates → deterministic Strategy Feasibility (D-180, eidos.planning.feasibility, V0.7 Step 4) → Strategy Selection (V0.8, not built) → Strategy-to-Plan expansion (V0.8+, not built) → the existing, unmodified full Plan Validation pipeline (eidos.validation) → compilation (eidos.compiler).` Only strategies `check_feasibility` finds feasible may enter selection. **Full V0.2 Plan validation is never run against every candidate** — only once, against the concrete `Plan` the *selected* strategy expands into.
- **Consequences:** confirms the reading V0.7 Steps 2–4 were already built against (feasibility is a narrower, strategy-level gate, not a stand-in for full Plan validation, D-180); no code changes to `eidos.planning` or `eidos.validation` follow from this ruling — it fixes the *order* a future V0.8 selector must respect, not anything already built. The handoff's own diagrams are not amended; this decision states which reading governs implementation, per CLAUDE.md §0's "if the handoff and this document conflict, stop and report" — reported at Step 1, now ruled on.
- **Affects:** V0.8's own design (Strategy Selection must call `check_feasibility`-filtered candidates, never re-run full Plan validation per candidate). Does not reopen D-178–D-182 or any V0.2/V0.3 decision.

### D-184 — MCP and RAG are deferred, unassigned extensions outside the V0.7–V1.0 strategy-intelligence sequence

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner
- **Source:** `docs/03_architecture.md`, `progress.md`'s "Intentionally not built yet" table (originally: `mcp/` at V0.7, `rag/` at V0.8, per D-027/D-028); V0.7 Step 1's own redefinition of V0.7 as Strategy & Candidate Generation
- **The gap found (and reported, not resolved, at Step 1):** the owner redefined V0.7 as Strategy & Candidate Generation and named V0.8 (Selector), V0.9 (benchmark) and V1.0 (Strategy Memory) explicitly — but said nothing about where MCP (previously "V0.7") and RAG (previously "V0.8") now land, an omission flagged rather than silently resolved by shifting every later milestone down by one.
- **Decision:** MCP and RAG are **not** slotted anywhere in the V0.7–V1.0 strategy-intelligence sequence (Strategy contracts → candidate generation → feasibility → selection → benchmark → memory). Neither is assigned a milestone number now. Each gets one **only when a concrete EIDOS requirement or benchmark actually needs it** — not pre-reserved, not guessed at.
- **Consequences:** `progress.md`'s "Intentionally not built yet" table rows for `mcp/`/`rag/` are updated from "V0.7 unclear"/"V0.8 unclear" to explicitly deferred-and-unassigned, per this ruling. D-027/D-028 (the original decisions putting MCP/RAG at V0.7/V0.8) are superseded by this renumbering, not reopened in substance — nothing about MCP's or RAG's own eventual design is decided here.
- **Affects:** the milestone ladder in `progress.md` only. No source code, contract or test is affected.
- **Annotated 2026-09-24 (D-203):** MCP now has its milestone, V1.2, because a concrete requirement exists (the Research agent returns `NO_RESULT` when no documents are supplied). RAG is unaffected and stays deferred and unassigned.
- **Annotated 2026-09-25 (D-208):** RAG now has its milestone, V1.3 (the knowledge/evidence layer only), because a concrete requirement exists: retrieved evidence enters the supplied set and the verifier's
  distinct-source count cannot tell one source from several (D-207 reading 1). The agentic loop, reranking, Qdrant and web acquisition stay deferred and unassigned.

### D-185 — Candidate generation and feasibility are not MissionEvent lifecycle events in V0.7

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner
- **Source:** invariant 15 ("every meaningful execution step emits a structured event"); `eidos.contracts.enums.MissionEventType`; V0.7 Step 1's own default position ("I'd default to no... but haven't assumed it")
- **The question found (and reported, not resolved, at Step 1):** whether a generated `Strategy`, or the fact that a candidate-generation round happened at all, should be recorded as a `MissionEvent` (e.g. a future `CANDIDATES_GENERATED`/`STRATEGY_SELECTED`-shaped type), or whether it stays entirely outside `eidos.state` until a strategy is actually selected and expanded into a `Plan`.
- **Decision:** **No.** Candidate generation and feasibility filtering are not `MissionEvent` lifecycle events in V0.7. `MissionEventType` gains no member for either. A `Strategy` is not (yet) a `MissionState` field and is not recorded by `eidos.state` in any form.
- **Consequences:** matches D-165-style scope discipline — event vocabulary is added only at the milestone that needs it, never speculatively. Strategy-related event vocabulary (for replay, evaluation or Strategy Memory, V1.0) **may be introduced later**, when one of those milestones actually needs it — this decision does not pre-approve any specific future shape, only confirms none is needed now.
- **Affects:** `eidos.state` is untouched by V0.7 in every step. Does not reopen D-090, D-154 or any other `MissionEventType` decision.

### D-186 — A selected Strategy is always one of the supplied feasible candidates; a Selector never emits a new Strategy or Plan DSL

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner
- **Source:** the Jev-inspired bounded-decision-space principle (V0.7 Step 1, D-179/D-183's own application of it); invariant 14 ("governance is deterministic... never by prompt"); `eidos.agents.model.ModelPort` (D-135) — text-in, text-out only, confirmed by inspection
- **The finding this rests on:** `ModelPort.complete()` returns text, never a structured value — a model can never return a `Strategy` object directly, only name one. This is the mechanical reason the constraint below is enforceable in code, not merely policy.
- **Decision:** a `Selector` may choose **only** from the candidate set it is given. It returns a `StrategyId` — never a `Strategy` value, never Plan DSL, never a newly constructed strategy of any kind. The actual admission of that choice (proving the id names a real member of the candidate set) is performed by a separate, deterministic orchestration boundary (D-187), never trusted from the selector itself.
- **Consequences:** this is the V0.8-level restatement of the same discipline `eidos.planning`'s own candidate generator already applies at the layer below it (a `CandidateGenerator` cannot name a capability outside `TaskGenome.required_capabilities`, D-178 onward) — governance never depends on the selector, deterministic or model-assisted, behaving correctly.
- **Affects:** D-187 (the contract this constrains). Does not reopen D-178 through D-185.

### D-187 — The Selector contract and its orchestration boundary

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner
- **Source:** `CandidateGenerator`/`generate_candidate_strategies`'s own two-layer split (D-178 onward); `ModelResult`'s total-function shape (D-135); `docs/03_architecture.md`'s pre-existing package table ("candidate strategy generation, strategy selection" under `eidos.planning`)
- **Decision:**
  1. **`Selector.select(candidates, task_genome) -> SelectorChoice`**, where `SelectorChoice = SelectedCandidate | SelectorFailure` — mirrors `ModelResult`'s own total, never-raising shape.
  2. **`select_strategy(selector, candidates, task_genome) -> SelectionResult`** is the deterministic orchestration boundary, mirroring `generate_candidate_strategies`'s own role: zero candidates → `NO_FEASIBLE_CANDIDATES`, the selector is never called; exactly one candidate → selected directly, the selector is never called; otherwise the selector is invoked and its claim is checked against the actual candidate tuple by `strategy_id` — a match returns the exact existing `Strategy` object (never reconstructed); no match is `INVALID_CANDIDATE_RETURNED`, never substituted; a `SelectorFailure` is `SELECTOR_FAILED`, the message preserved, never retried, never silently falling back.
  3. **`check_feasibility` is not re-run inside this boundary.** Every candidate offered to a `Selector` is, by construction, already the feasibility-filtered output of `generate_candidate_strategies` (V0.7 Step 4); the membership check here is an identity check, not a second admissibility pass.
  4. **Lives in `eidos.planning`** (no new package) — the core `Selector` Protocol and one deterministic reference implementation only. A future model-assisted `Selector` (needing `eidos.agents.ModelPort`) is a separate adapter *outside* this core layer, not built now.
- **Consequences:** `eidos.planning` needs no new dependency for this — `Selector`/`select_strategy` take no `SystemLimits`/`ReliabilityContract` at all, since admissibility was already fully decided by feasibility filtering before a candidate ever reaches selection.
- **Affects:** D-186 (the constraint this contract enforces), D-188 (the one reference implementation this step ships).

### D-188 — The reference DeterministicSelector's tie-break is structural, never a scalar score

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner
- **Source:** invariant 13/17 discipline ("never manufacture confidence," "no fabricated numbers") applied to strategy comparison; handoff §18's own cold-start sequence ("rules and heuristics" before any measured signal exists)
- **Decision:** `DeterministicSelector` orders candidates by `structural_cost(strategy) = (total capability occurrences, stage count)` — a **tuple**, compared lexicographically, never weighted or combined into a single number. Tie-break order: fewest total capability occurrences first, then fewest stages, then the candidate set's own generation order (via `min()`'s own stability — the first minimal element in iteration order wins, so no separate tie-break code exists). No scalar quality score is introduced at this step or implied for later.
- **Consequences:** this is deliberately the first, plainest rung of handoff §18's own progressive cold-start sequence ("rules and heuristics → small pilot → measure actual signals...") — not a placeholder for a future weighted score, a considered choice to avoid fabricating a quality judgment this milestone has no measured basis for.
- **Affects:** `eidos.planning.selector`'s own reference implementation only. Does not constrain a future model-assisted `Selector`'s own internal reasoning, only that it must still resolve to a `StrategyId` a real candidate carries (D-186).

### D-189 — SelectionResult is a typed, replay-ready value only; no SelectionId, no MissionEvent, no Strategy Memory

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner
- **Source:** D-185's own identical deferral for candidate generation; invariant 15 (replayability)
- **Decision:** `SelectionResult` (`outcome`, `selected`, `reason`) is a complete, frozen, JSON-round-trippable value — nothing more. It is **not** a `MissionEvent`, **not** a `MissionState` field, and carries **no identity of its own** (no `SelectionId`). Nothing records a selection anywhere yet.
- **Consequences:** exactly mirrors D-185's own reasoning: the contract is shaped to be recordable later (a future event, not built) without needing to exist as one now. A completed mission still replays deterministically once a selection is eventually recorded as a fact — the *selection mechanism* need not be deterministic itself (a future model-assisted one likely won't be), the same way a model call inside an agent already isn't, without breaking mission replay.
- **Affects:** nothing in `eidos.state` is touched. Does not reopen D-185.

### D-190 — Minimum model context for selection: goal plus each candidate's stages, verification and rationale — nothing else

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner
- **Source:** V0.8 Step 4 exploration; `ModelPort`'s text-in/text-out shape (D-135); D-179's own capability-allocation/verification-posture/topology dimensions
- **Decision:** a model-assisted `Selector` (not built by this decision) may see exactly: `TaskGenome.goal`, and each candidate's `stages`, `verification` and `rationale`. It must **not** see `required_capabilities` (redundant — already fully visible as the union of what the candidates' own stages show), `risk_level`/`autonomy_level` (no bounded, deterministic instruction exists yet for how these should influence a choice — handing them over would only invite free-form judgment), `structural_cost` (would let the model simply recompute what `DeterministicSelector` already does for free, giving model-assistance no differentiated value and anchoring toward "smaller number is better," which is not necessarily goal-fit), or the raw `StrategyId` (D-191).
- **Consequences:** context is not added merely because it is available; each exclusion has a stated, specific reason, not a blanket minimalism gesture. A future decision may add a field once a bounded, deterministic instruction for using it exists — this decision does not pre-approve any specific future addition.
- **Affects:** the not-yet-built model-assisted `Selector`'s own request-construction logic. Does not reopen D-186 or D-187.

### D-191 — Compact position-derived labels, never raw StrategyId, shown to the model; deterministic JSON candidate serialization

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner
- **Source:** V0.8 Step 4 exploration; `base.render_artifacts`'s own `[[ref]]` labelling precedent; D-053 (StrategyId is UUID-backed, none of D-053's four exemption reasons apply to a model-facing label)
- **Decision:** candidates are presented to the model under compact labels — `CANDIDATE_1`, `CANDIDATE_2`, ... — derived **strictly from candidate-tuple position**, never drawn from randomness or an injected id source (there is nothing to inject: the label *is* the index). The label↔`StrategyId` map is built fresh per call, from the `candidates` tuple itself, and is never exposed to the model. Candidate *data* (`stages`, `verification`, `rationale`) is serialized as JSON with fixed field order and fixed candidate order — safe and unambiguous regardless of arbitrary content in a `rationale` string, unlike a bespoke delimited-text format would be.
- **Consequences:** the authoritative identity remains `StrategyId` throughout; the label is a presentation-layer detail resolved back to it immediately after parsing (D-192), never trusted or propagated past that point. A 36-character UUID is never something the model has to reproduce exactly — the closed, short label vocabulary is both safer against transcription error and structurally impossible to satisfy with an out-of-set answer.
- **Affects:** the not-yet-built model-assisted `Selector`'s own serialization logic only. `Strategy`/`StrategyId` themselves are unchanged.

### D-192 — Model output contract: exactly one bracketed candidate label, reusing the existing citation-token convention; no new failure vocabulary

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner
- **Source:** V0.8 Step 4 exploration; `eidos.agents.base`'s existing `_CITATION`/`cited_refs` regex-extraction precedent; D-187 (`Selector`'s existing contract), D-135 (`ModelFailureKind`)
- **Decision:**
  1. The model is instructed to respond with exactly one candidate label wrapped in double brackets (e.g. `[[CANDIDATE_2]]``) and nothing else — no rationale, no score, no confidence, no "best strategy" narrative.
  2. Parsing extracts every **distinct** bracketed token from the response, mirroring the existing citation-extraction pattern exactly (tolerant of surrounding prose, de-duplicating repeated identical tokens to one). Only a bracketed token is ever authoritative; nothing outside brackets is read for meaning under any circumstance.
  3. Exactly one distinct, resolvable label → a candidate is proposed. Zero labels, two or more *distinct* labels, or a label outside the given `CANDIDATE_1..N` set are **all** `SelectorFailureKind.MALFORMED_CHOICE` — never a guessed tie-break, never a best-effort substitution.
  4. Underlying `ModelFailure` kinds map onto the **existing**, unchanged three-member `SelectorFailureKind` (D-187): `TIMEOUT`→`TIMEOUT`, `UNAVAILABLE`→`UNAVAILABLE`, `MALFORMED_RESPONSE`→`MALFORMED_CHOICE`, `EMPTY_RESPONSE`→`MALFORMED_CHOICE`. **No new failure kind is introduced** — checked, not assumed: every real `ModelFailure`/parsing-failure case maps cleanly onto the three members Step 2 already approved.
- **Consequences:** this is the actual prompt-injection boundary, and it is structural, not linguistic — even a fully successful attempt to influence the model's wording can, at worst, bias *which* already-feasible candidate gets named; it cannot escape the closed label vocabulary, because the parser structurally extracts nothing else. Prompt wording that frames goal/candidate text as data, not instructions, is a best-effort, non-load-bearing addition on top of this, never the boundary itself.
- **Affects:** the not-yet-built model-assisted `Selector`'s own output handling. Does not add a member to `SelectorFailureKind` or change `select_strategy`'s own membership check, which remains the unconditional backstop regardless of how a choice was produced.

### D-193 — ModelAssistedSelector is an independent Selector implementation; no automatic fallback to DeterministicSelector

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner
- **Source:** V0.8 Step 4 exploration; D-170 (no automatic mission driver, A2A resume); D-187 (the shared `select_strategy` orchestration boundary)
- **Decision:** a model-assisted `Selector` is an independent, alternative implementation of the same `Selector` Protocol (D-187) — not a fallback, not a wrapper, not a verification pass over `DeterministicSelector`. Both implementations are validated by the identical, unchanged `select_strategy` boundary. **No automatic fallback exists or is planned**: a `SelectorFailure` from a model-assisted selector is returned to the caller as `SELECTOR_FAILED`, exactly as any other selector failure already is — never silently retried, never silently resolved by switching to `DeterministicSelector`.
- **Consequences:** the caller — never the selection boundary itself — decides what happens after `SELECTOR_FAILED` (retry, switch selectors, halt for review). A future *opt-in* composition (e.g. a wrapper `Selector` that tries one implementation then another) would itself be an ordinary `Selector` implementation the existing Protocol already supports — not proposed or built now.
- **Affects:** the not-yet-built model-assisted `Selector`'s own failure handling. Does not change `select_strategy`, `SelectionResult`, or `SelectionOutcome`.

### D-194 — Strategy-to-Plan expansion lives in a new sibling core layer, `eidos.expansion`

- **Status:** Accepted · **Date:** 2026-09-23 · **Decided by:** human owner
- **Source:** D-178 ("whatever later expands a selected Strategy into a Plan must still pass that Plan through the unmodified V0.2 validation and V0.3 compiler pipeline"); D-180's own precedent (`eidos.planning` becomes a core layer with a named, narrow set of approved dependencies); `tests/unit/planning/test_planning_guards.py`'s existing `FORBIDDEN_CONCEPT_IMPORTS` guard, which already forbids `eidos.planning` from ever importing `StepId` (enforcing D-179's own exclusion of step ids and edges from `Strategy`); V0.8 Step 7 exploration.
- **Decision:** the mechanism that expands a selected `Strategy` into a concrete `Plan` lives in a **new sibling core layer, `eidos.expansion`** — not inside `eidos.planning` (structurally impossible without violating the existing guard above, which is not weakened by this decision) and not inside `eidos.contracts`, `eidos.validation` or `eidos.compiler`. It joins the existing core-layer set (`eidos.contracts`, `eidos.validation`, `eidos.compiler`, `eidos.runtime`, `eidos.state`, `eidos.planning`) with the same discipline: deterministic, no I/O, no clock, no randomness, no model/vendor/tool name. It may depend only on `eidos.contracts` (`Plan`, `PlanStep`/`AgentStep`/`ControlStep`, `PlanId`, `StepId`) and `eidos.planning` (`Strategy`, `StrategyStage`, `VerificationPosture`) — never `eidos.validation`, `eidos.compiler`, `eidos.runtime`, `eidos.agents`, `eidos.providers`, `eidos.backends`, `eidos.a2a`, `eidos.recording` or `eidos.selectors`.
- **Consequences:** its output is an ordinary `Plan` — no new entry point into V0.2 validation or V0.3 compilation is created; both remain exactly as they are, per D-178's own promise that a `Strategy` grants no shortcut. `eidos.expansion` does not call `eidos.planning.feasibility.check_feasibility` (already decided admissibility, D-180/D-183) and does not duplicate any V0.2 validation rule.
- **Affects:** establishes the package boundary and its approved dependency edges ahead of V0.8 Step 8, which implements it. Does not reopen D-178, D-179, D-180 or D-183. *(D-196: this work is filed under V0.8 Steps 7–8, not "V0.9" — see D-196.)*

### D-195 — `VerificationPosture.FINAL` expands to exactly one VERIFY step depending exactly on the final stage's own step ids

- **Status:** Accepted · **Date:** 2026-09-23 · **Decided by:** human owner
- **Source:** the real, already-shipped V0.4 baseline plan precedent (`{"gather": "", "analyse": "gather", "check": "analyse"}` — the `VERIFY` step depends only on the immediately preceding step, never transitively on an earlier one); `eidos.agents.verification`'s own documented behavior ("over the artifacts the VERIFY node's predecessors produced" — a `VerifyNode`'s `predecessors`, i.e. its `depends_on` edges, are the actual boundary of what gets verified, not a redundant ordering hint); D-146 (`minimum_distinct_sources` follows citations transitively through the artifact graph, not through Plan dependency edges, so evidence from an earlier stage remains reachable without a direct edge); V0.8 Step 7 exploration.
- **Decision:** when a `Strategy.verification` is `FINAL`, expansion appends **exactly one** `VERIFY` `ControlStep` to the produced `Plan`, whose `depends_on` is **exactly** the complete set of `PlanStep` ids generated from the strategy's **final** stage — never every agent step in the Plan, and never a subset of the final stage. `VerificationPosture.NONE` produces no `VERIFY` step at all (unchanged from D-179's own definition of the field).
- **Consequences:** verification's own direct scope is the final stage's output only; an earlier stage's evidence remains reachable only through citation-following (D-146), exactly mirroring the existing V0.4 precedent. This does not resolve D-129 (how a work node receives its predecessors' outputs stays Open) — the edges this decision fixes are for the `VERIFY` control step only, which already has a settled, documented data-flow (`eidos.agents.verification`), not for `AgentStep`-to-`AgentStep` edges.
- **Affects:** `eidos.expansion`'s own expansion rule for the `VERIFY` step. Does not change `PlanStepKind`, `VerifyNode`, `VerificationAgent`, or any V0.2/V0.3 contract. Does not close D-129. *(D-196: this work is filed under V0.8 Steps 7–8, not "V0.9" — see D-196.)*

## Open — require the human owner

These are ambiguities, contradictions and gaps found in the handoff during the bootstrap read. None
has been resolved. Work that depends on one of them is blocked until the owner decides.

Count: 40. Highest-impact first is **D-015** (how verification confidence is computed), then
**D-007** (now V0.4-only, not V0.2 — see D-102) and **D-046** (bound values, mechanism unaffected —
see D-103) for later V0.2 work. **D-012** (predicate language) was corrected 2026-09-18 to no longer
be listed as a V0.2 item — it blocks the V0.3 compiler. **D-102** and **D-103**, logged the same day,
were **resolved the same day**: V0.2 capability validation is mission-scoped against
`TaskGenome.required_capabilities` (no registry, no global vocabulary needed), and production
`SystemLimits` ships with no built-in numeric defaults. **D-043** was investigated and corrected the
same day: it is a V0.3 (runtime reconciliation) concern, not a V0.2 blocker.

**All seven V0.1 contracts are fully specified and constructible** as of 2026-09-18. **No Open item
blocks V0.1 contract construction.** The remaining Open items concern later milestones, or touch V0.1
without blocking it (see `progress.md`).

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
- **V0.4 (2026-09-20):** **D-132** fixes a V0.4-only, exact-string set of five capabilities (the §43 "Required capabilities").
  **D-007 stays Open:** nothing global, hierarchical, similarity-based or cross-mission is decided. Spelling and the
  agents behind each capability are **D-141** (since resolved by D-144).


### D-008 — Lint and type-checking tooling not adopted

- **Status:** Open · **Source:** handoff §76 (does not name any linter or type checker)
- **Finding:** A linter and a type checker would normally be adopted at bootstrap, but the handoff's
  technology stack does not name one. Adopting `ruff`/`mypy` unasked would be an unapproved
  decision.
- **Action taken:** Neither is declared in `pyproject.toml`. `.gitignore` already ignores their
  caches so adding them later is frictionless.
- **Needs:** Owner to decide whether to adopt, and which.

### D-041 — Evidence and final mission-result fields in MissionState

- **Status:** Open · **Source:** handoff §30, §31, §74 · **Split out of D-010a, left Open by the owner**
- **Finding:** D-010a's field set deliberately excludes evidence and the final mission result.
  Evidence arrives with Agentic RAG at V0.8 and evidence lineage (§74, invariant 16); the mission
  result and its contract-satisfaction verdict (§30, invariant 13) arrive with verification at V0.4.
  Excluded by scope discipline, not by oversight.
- **Effect while Open:** none on V0.1.
- **Needs:** Decide at V0.4 (result) and V0.8 (evidence), each as its own milestone question.
- **V0.4 (2026-09-20):** not reopened. **D-139** adds the frozen `ReliabilityContract` to `ExecutionContext` and explicitly
  introduces **no universal output or answer field.**


### D-012 — Predicate language for conditional primitives

- **Status:** Open · **Source:** handoff §13
- **Finding:** `ROUTE`, `RETRY`, `REPLAN` and `TERMINATE` are all conditional, and routing must be
  deterministic (§11, §29), but **no expression or predicate language is specified** for any of
  them. Without one, either the condition is opaque (breaking determinism and validation) or an
  expression language is invented.
- **Needs:** How a condition is expressed, what it may read from MissionState, and how it is
  validated. **Blocks the compiler (V0.3)** — nothing in the V0.2 validation pipeline (§14's eight
  stages: schema, dependency, cycle, capability, policy, resource, graph-complexity validation) reads
  or checks a step's condition, since none exists to check.
- **V0.1 scope settled by D-047, which does not resolve this item.** V0.1 defines plan *structure*
  only — kinds, step IDs, capability, edges, DAG — and carries **no conditional payload at all**,
  rather than an opaque placeholder. D-012 is a clean **V0.3** decision (the compiler is the first
  thing that needs to interpret a condition), not a migration away from a guessed shape.
- **Corrected 2026-09-18:** this entry, `docs/05_plan_dsl.md` and `progress.md` previously disagreed
  on whether D-012 blocks V0.2 or V0.3 — one sentence here called it "a clean V0.2 decision" while
  the line above it already said "blocks the compiler." That was documentation drift, not a decision;
  it is fixed to consistently read V0.3 in all three places.
- **V0.3 note (2026-09-19):** V0.3 does **not** resolve this item. Instead of compiling the four conditional kinds
  it **rejects** them at compile time (**D-112**), so "blocks the compiler" now means "blocks compiling
  `ROUTE`, `RETRY`, `REPLAN` and `TERMINATE`". Deferred explicitly (**D-127**).

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
- **V0.3 note (2026-09-19):** not material at V0.3 after all. `HUMAN_APPROVAL` is compile-rejected (D-112), so the
  question of how it relates to the mission-wide autonomy level does not arise yet. Stays Open.

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
- **V0.4 (2026-09-20):** **D-138** decides that V0.4 verification is a **deterministic rule set with no model verdict** and no
  scalar. That answers this entry for V0.4 only. **D-015 stays Open** for a scalar confidence and §31's threshold-driven
  replan (V1.2). **D-063 and D-064 stay Open and dormant.** Clauses of the contract the verifier cannot evaluate: **D-143** (since resolved by D-146).
- **V0.5 (2026-09-21):** not resolved. The `ExecutionRecord` stores the verifier's verdict and reason only — no scalar and no confidence (D-159).



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
- **V0.5 (2026-09-21):** **D-157** answers the *authority* question for V0.5 — the **event log is authoritative** and a snapshot is an optimisation — and keeps V0.5 to an in-memory log
  with a strict JSONL round trip. **No durable store (no SQLite, no file store) is built; D-017 stays Open** for persistence, its schema and its interface.
- **Answered for V1.4 (2026-09-26, D-230):** what is stored (the events and the artifacts), which is authoritative (the events, D-157) and the interface (the service Protocols and the existing `ArtifactStore`) are answered by D-230, accepted by the owner on 2026-09-27 and built in V1.4-B. **Still Open:** snapshots and checkpoints as stored values, strategy memory and any other store.


### D-020 — "Strategy" and "Plan" are used interchangeably

- **Status:** Accepted · **Date:** 2026-09-22 · **Decided by:** human owner · **Resolved by D-178**
  (originally Open)
- **Source:** handoff §13, §16, §17, §38, §53
- **Finding:** §16 generates "candidate strategies" labelled Plan A/B/C; §13 defines a Plan DSL;
  §53's API response carries `strategy_id`; §17 lists strategy factors (model selection, retrieval
  strategy, context allocation) that are *not* expressible in the §13 plan primitives.
- **Original need:** Are a Strategy and a Plan the same object, or is a Strategy a Plan plus binding
  decisions (agent, model, retrieval, context) that the DSL does not encode? This determines whether
  one contract or two is needed, and what a `strategy_signature` (D-021) actually signs.
- **Resolution:** **D-178.** Two distinct objects. A `Strategy` describes execution shape only
  (capability stages, verification posture) and never carries a `StepId`, a dependency edge or an
  agent binding; a `Plan` is unchanged. A selected strategy may later (V0.8+) expand into a `Plan`,
  which still passes through the unmodified V0.2/V0.3 pipeline.
- **Not resolved by this:** **D-021** (what a `strategy_signature`/"Strategy Genome" encodes) stays
  Open — `StrategyId` (D-182) is plain identity, not a signature.

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
- **V1.4 (2026-09-26, D-229):** the frontend is the handoff's V1.3 label, and this project's V1.3 is RAG. Frontend is unassigned and not started, and this stays Open until it starts.

### D-024 — Placement of the FAISS vs Qdrant experiment

- **Status:** Open · **Source:** handoff §26
- **Finding:** §26 proposes a FAISS-vs-Qdrant comparison *and* says not to introduce both into the
  core runtime without a clear research reason, with Qdrant as the default. The natural reading is
  that the experiment lives outside the core runtime, but that is a reading, not a statement.
- **Needs:** Confirmation that the comparison is an out-of-runtime experiment rather than a runtime
  abstraction with two backends.
- **Annotated 2026-09-25 (D-208, D-220):** V1.3 uses an in-process exact cosine index over a pinned snapshot; neither FAISS nor Qdrant is part of it. D-024 stays Open.

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
- **Annotated 2026-09-25 (D-216, D-217):** answered for the V1.3 initial implementation only. Retrieval is bounded by per-knowledge-base configuration (`top_k`, a maximum result count and a maximum
  returned size), there is no new global retrieval budget, and there is no reformulation loop (one deterministic query per acceptance path, no LLM query planning). D-029 stays Open for the
  agentic reformulation loop and any `max_rag_rounds`.

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
- **Answered for the V1.4 API (2026-09-26, D-232):** `risk_level` is as stated by the caller in the `MissionSpec` and is not assessed by the server; the server applies ceilings on `autonomy_level` and `allowed_actions`, not on the stated risk.

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

- **Status:** Accepted (2026-09-26, the owner's V1.4 direction, recorded in D-233) · **Source:** handoff §54 (silent) · **Split out of D-019, left Open by the owner**
- **Finding:** D-019 establishes that `tenant_id` is required and carries a single fixed default.
  §54 provides no value, and the choice is not neutral: a value that reads as a sentinel behaves
  differently under a future migration than one that reads as a real tenant, and a value that looks
  like an identifier invites being parsed as one.
- **Effect while Open:** does not block the model definitions — only the constant.
- **Needs:** Owner to choose the value, and to state whether it is a reserved sentinel that real
  tenants may never take.
- **Ruled (owner, 2026-09-26, D-233):** the literal stays the nil UUID, and it is a reserved sentinel that a real tenant may never take: the nil/default tenant is for non-real and test contexts. The comment in `eidos.contracts.identifiers` ("CHANGE THIS when D-032 is resolved") is updated when V1.4 code is written; nothing else changes. **Done (V1.4-B, 2026-09-27):** the comment is updated (a comment only; the value is unchanged), the `tenants` table refuses the nil tenant with a check constraint and the in-memory storage refuses it too.

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
- **V0.5 (2026-09-21):** answered for V0.5 only — the applied-`event_id` set is derived from the in-memory log with full retention (D-155, D-157). Bounding and persisting it stay Open with D-017.
- **Answered for V1.4 (2026-09-26, D-230):** the applied-event-id set is derived from the persisted log with full retention; it is not stored separately.


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
- **Effect while Open:** none on V0.1, and **none on V0.2's declared-step-count check either** —
  corrected 2026-09-18. Investigated during V0.2 scoping: V0.2's resource-validation and
  graph-complexity-limits stages operate on a *static* Plan, before anything executes, so they can
  only ever count **declared** steps — there is no runtime yet to count actual invocations against.
  V0.2 can therefore implement "declared step count for kind X <= max_X" as a complete, well-defined
  check with zero ambiguity, **provided it is documented as counting declared steps only** and does
  not claim to bound total actual execution calls. The genuine ambiguity this item names — whether a
  contract field bounds the same number at validation time and at execution time — only becomes a
  live problem once the **V0.3 runtime** (and later the V0.5 reducer incrementing MissionState's
  budget counters, D-091) exists and needs reconciling against the V0.2 check. **Material at V0.3,
  not V0.2.**
- **Needs:** Either two distinctly named limits, or one limit with a stated counting rule that both
  enforcement points share. Not required to build V0.2's own declared-count check.
- **V0.3 note (2026-09-19):** V0.3 performs **no runtime counting** (D-127) and dispatches each node at most once per
  run (D-119), so this item stays dormant at V0.3. It is **not** resolved and remains Open.
- **V0.5 (2026-09-21):** the reducer now folds the MissionState counters (D-156), counting **actual** recorded facts (agent dispatches, provider-reported tokens, recorded node durations); nothing is
  enforced against a limit. **D-043 stays Open:** which number a limit bounds, and its reconciliation with V0.2's declared-step check, are undecided.


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
- **Answered for the V1.4 API (2026-09-26, D-232):** the contract is user-supplied in the `MissionSpec` and validated; EIDOS does not synthesise one.

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
- **V0.3 implementation note (2026-09-19, D-124):** for V0.3 only, `VERIFY` is treated as a control step compiling to a
  `VerifyNode`, and `HUMAN_APPROVAL` is unsupported (compile-rejected). This does **not** answer this
  item; the broader classification remains Open.
- **V0.4 (2026-09-20):** **D-133** binds a `VERIFY` node to the `Verifier` port by node kind, not by capability. That records
  how V0.4 binds `VERIFY`; **D-055 stays Open.**


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
- **V0.3 note (2026-09-19):** unaffected. `HUMAN_APPROVAL` is not compiled at V0.3 (D-112, D-124), so it is not
  implemented there; this item stays Open.

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
- **V0.5 (2026-09-21):** not resolved. `MISSION_FAILED` carries a typed cause and a reason, and no new status or event is added for "could not satisfy the reliability contract" (D-156). A verifier
  FAIL or INCONCLUSIVE is recorded as such and V0.5 makes no claim about contract satisfaction (D-146). A typed cause keeps either later answer non-breaking.


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
- **Narrowed by D-103 (2026-09-18):** production `SystemLimits` ships with **no built-in default at
  all**, provisional or otherwise — stricter than this item's original "provisional values at V0.2."
  D-103 governs the mechanism's posture toward absent values; the actual numbers for all seven bound
  dimensions remain entirely this item's question, unresolved.
- **V1.4 (2026-09-26, D-232, D-234):** the values stay Open. The service supplies `SystemLimits` from a **provisional** configuration, and the API safety ceilings are provisional too: neither is tuned, measured or presented as tuned.

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
- **V0.5 (2026-09-21):** answered for the types V0.5 emits by **D-153** (typed payloads in an `EventRecord`, the V0.1 envelope unchanged; the concrete fields are D-160). **Stays Open** for the types
  V0.5 does not emit (`A2A_TASK_*`, `MCP_TOOL_CALLED`, `RAG_SEARCH`, `EVIDENCE_REJECTED`, `REPLAN_TRIGGERED` and `VERIFICATION_FAILED`, D-160 item 2).


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
- **V0.5 (2026-09-21):** discharged for the emitted types — the payloads carry what the reducer and the `ExecutionRecord` need, and replay reconstructs the state from the log alone (D-153, D-157) —
  **but stays Open**: artifact content is not in the log (refs only), no stop reason is recorded (D-151, D-158), and the obligation continues for every later event type.
- **V1.4 (2026-09-26, D-230):** the log still holds an `ArtifactRef` only; artifact content is durable in the `artifacts` table behind the existing `ArtifactStore`. The obligation for later event types continues.


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


### D-111 — V0.2 implementation details the approved design left unspecified

- **Status:** Open · **Source:** V0.2 implementation (2026-09-19); CLAUDE.md §7 (no silent defaults)
- **Finding:** The approved V0.2 design fixed the stage list, the result model, the limits and the
  rulings D-104..D-110. While implementing it, eight small behaviours were **not** specified. Each
  had to be written one way or another, so each was written the most conservative way and is
  recorded here for the human owner to confirm or change. **None is a claim that the choice is
  right; all are cheap to reverse and none weakens an invariant.**
  1. **Identity mismatch is reported under the SCHEMA stage.** A plan whose `mission_id` or
     `tenant_id` differs from the `MissionState` it is validated against gets
     `PLAN_MISSION_MISMATCH` / `PLAN_TENANT_MISMATCH` under SCHEMA, because invariant 5's stage order
     has no earlier or better-fitting home. CAPABILITY and RESOURCE (the two stages that read the
     state) are then SKIPPED; the structural stages still run.
  2. **`accepted` is stricter than "no stage FAILED".** A report is accepted only if every stage is
     `PASSED` or `NOT_APPLICABLE`; a `SKIPPED` stage is never accepted (invariants 5, 13).
  3. **The DEPENDENCY stage re-checks a constructed `Plan`.** `Plan` enforces uniqueness and
     reference resolution at construction, but `model_copy(update=...)` / `model_construct` bypass
     that. `validate_plan` re-verifies both so a `PASSED` reflects a check that ran on this plan and
     the graph stages never receive an undefined graph; if it fails, CYCLE and COMPLEXITY are SKIPPED.
  4. **COMPLEXITY skip semantics.** A cyclic plan within `max_nodes` is `SKIPPED` (depth and width
     are undefined), never `PASSED`. A plan over `max_nodes` is rejected **without computing the
     width**, whose cost is up to quadratic in the step count; `max_depth` (linear) is still checked.
  5. **`SystemLimits` numeric range.** Every field is an integer `>= 0` with no upper bound and no
     default; `0` is a legal limit, not "unset".
  6. **Violation ordering.** Stage order; within a stage, `plan.steps` order (cycles by earliest
     member), the fixed six-budget order for contract-versus-ceiling, and mission-before-tenant for
     identity. The order is asserted byte-identical across process hash seeds.
  7. **Two exception types exported from `eidos.contracts`.** D-108 authorised exporting
     `EidosModel`; `DuplicateStepIdError` and `UnknownDependencyError` (D-107) were exported
     alongside it so `eidos.validation` need not import a submodule path.
  8. **The report carries `plan_id` only** (`None` when the document could not be parsed) — no
     `tenant_id` or `mission_id`. The report is derived output, not persisted state; invariant 18's
     identifier rule was read as applying to state and event records.
- **Effect while Open:** none blocking. Items 1, 3 and 4 change which stage or status a situation
  is reported under. Item 2 fixes that a report with a `SKIPPED` stage is never accepted — a state
  that, in a normal run, only ever arises alongside a `FAILED` stage. Items 5–8 are representation.
- **Needs:** the owner to confirm each item or replace it; any replacement is a new Accepted entry.

### D-125 — Relationship between plan-level `RETRY` and future runtime retry policy

- **Status:** Open · **Source:** handoff §13, §17, §32; D-012, D-043, D-119; raised in V0.3 exploration
- **Finding:** retry appears in the handoff in two roles that are never related. §13 lists **`RETRY`
  as a Plan DSL step kind**. §32 describes a **runtime recovery behaviour** — "agent failure → classify
  → retry if appropriate → fallback capability → replan if necessary" — bounded by `max_retries`, and
  §17 names "retry strategy" as a strategy factor. The handoff does not say whether a `RETRY` step *is*
  the mechanism for the runtime behaviour, a planner-expressed alternative to it, or an independent
  construct; nor what a `RETRY` step's edges mean (which step it retries, and when), since no predicate
  language exists (D-012). §32's "classify" is also unspecified. This is the two-mechanisms pattern
  already seen in D-061 and D-013.
- **Effect while Open:** none on V0.3. `RETRY` is rejected at compile (D-112) and V0.3 performs no
  automatic retry (D-119).
- **Needs:** the owner to state how the plan-level step and any runtime policy relate; what a retry
  counts against (`max_retries`, and D-043's declared-versus-actual counting); and whether failure
  classification is part of the runtime or the plan.

### D-129 — How a work node receives its predecessors' outputs

- **Status:** Open · **Source:** handoff §13, §16, §43; D-098, D-121, D-122; raised implementing V0.3 Step 3
- **Finding:** the V0.3 work port is specified as `execute(context, node)` (D-122): a work node is told
  *what to do* (its requested capability) and *for which mission*, but **not what its predecessors
  produced**. The verifier port is different — a `VERIFY` node is given its predecessors' results. So in
  V0.3 an edge into a work node carries **ordering only**: a downstream work node cannot consume an upstream
  node's artifact. §16 and §43 draw analysis consuming research, which is the point of a dependency. Any
  answer needs an output representation, and D-098 defines none: `ArtifactRef` is an opaque reference and
  "no Artifact model is created".
- **Effect while Open:** none on V0.3, which uses scripted test doubles only and executes no real work. It
  becomes material when real agents exist (V0.4).
- **Needs:** whether predecessors' results are passed to a work node (as the verifier's are), fetched by the
  work implementation through a reference, or something else; and what an artifact is. Changing the port
  signature is a change to D-122, so it needs the owner.
- **V0.4 (2026-09-20):** **D-137** answers this for V0.4: predecessors' outputs are fetched from an in-memory artifact store
  under `(execution_id, step_id)`, one primary artifact per work step, and **the `WorkExecutor` signature is unchanged.** **D-129
  stays Open:** what an artifact contains (**D-142**, since resolved by D-145) and the general data-flow question remain.
- **V0.5 (2026-09-21):** not resolved. The log records an `ArtifactRef` only, never content, so replay reconstructs state, outcomes and facts, not artifact text (D-157); the `WorkExecutor`
  signature is unchanged.



### D-151 — Handling non-empty model responses terminated by `done_reason=length`

- **Status:** Open · **Date:** 2026-09-21 · **Source:** D-135, D-137, D-138, D-146, D-148 (items 5, 7 and 9), D-150; found by reading the code while working on D-150 option (c); invariants 12 and 13
- **Question:** what should EIDOS do when the runtime returns text but reports that generation stopped at the output limit (`done_reason` `length`) — an answer cut off part-way?
- **Current behaviour (V0.4), recorded as it is:**
  - `OllamaModel._interpret` returns a `ModelResponse` whenever `response` has non-blank text, **whatever `done_reason` says**. `done_reason` is read only in the empty-response branch
    (D-150 option c).
  - `ModelResponse` and `MeasuredFacts` (D-135) carry the text, the token counts and the elapsed time. They have **no field for why generation stopped**, so nothing downstream can
    know that the text was cut off.
  - The agents store the text as the step's one artifact (D-137) and record what it cited as `source_refs` (D-148 item 5). The verifier's three rules (D-146) — schema validity, that
    every cited reference exists, and three distinct supplied sources — **do not detect truncation**: a truncated but well-formed artifact that cites existing sources can `PASS`.
  - **Not observed in any run.** Every non-empty response whose raw body was captured (three: Research at 2,048 and at 4,096 tokens, and Analysis at 4,096) had `done_reason` `stop`. The
    only `length` responses captured (D-149, D-150 option a) were empty. The committed opt-in test does not print `done_reason`.
- **Why it is deferred, not solved in V0.4:**
  1. **No existing contract requires it.** D-135 lists four failure kinds (timeout, unavailable, malformed, empty) and its typed result has no stop reason; D-138 and D-146 define exactly
     three verifier rules and say the verdict covers those rules only; invariants 12 and 13 forbid manufacturing confidence but do not specify this case.
  2. **Every way of handling it changes an accepted contract:** a new failure kind, or a stop-reason field, changes D-135 (and, if the agents record it, D-137); a verifier rule changes
     D-138 and D-146; treating it as a failure changes what `NO_RESULT` and `FAILED` mean for a work step (D-148 item 6).
  3. **It has not been observed**, and the committed configuration (4,096 tokens) makes a cutoff on the baseline mission less likely — the longest recorded call used 2,582 tokens — though not impossible.
  4. **The owner ruled (2026-09-21)** that it is not redesigned or solved in V0.4 unless an existing contract explicitly requires it; none does.
- **Effect while Open:** an answer that is cut off part-way and still has text would be stored as a normal artifact and could pass verification unmarked. No mitigation specific to it is in
  place.
- **Needs:** the owner's choice, none adopted, when the model seam is next changed or replay needs model outputs recorded (V0.5, D-076):
  (a) treat a non-empty `length` response as a failure — a new kind, or an existing one (a D-135 change);
  (b) carry the stop reason in `ModelResponse` or `MeasuredFacts` and let the agents record it with the artifact, leaving the verifier alone (a D-135 and D-137 change);
  (c) carry it and add a deterministic verifier rule that returns `INCONCLUSIVE` for a truncated artifact (a D-138 and D-146 change);
  (d) leave it as it is and document it.
- **V0.5 (2026-09-21):** stays Open by the owner's ruling. `MeasuredFacts` is **not** modified to improve replay, so the log records no stop reason, and history cannot tell a non-empty answer cut
  off at the output limit from a complete one (D-158). Recorded so the blind spot is visible.

---


### D-164 — A `NODE_STARTED` recorded after the same step's `NODE_SETTLED`

- **Status:** Open · **Date:** 2026-09-21 · **Source:** D-162 item 1; invariant 8 ("late or out-of-order events are accepted or rejected deterministically against the lifecycle")
- **Question:** D-162's guard refuses a *repeat* of a step's start or settlement. It does not refuse a `NODE_STARTED` that arrives after the same step's `NODE_SETTLED`, which is not a repeat but is out of
  lifecycle order: a node cannot start after it has settled.
- **Current behaviour (V0.5), recorded as it is:** the intake and a replay **accept** it. It folds nothing (a start changes only `state_version` and `updated_at`), so no counter can be corrupted by it.
  The recorder never produces it, and the recording tests assert the order started, then settled. If it were recorded, the projection would show the step as started although its settlement came first: a wrong
  chronology, not a wrong count.
- **Why it is not decided:** the owner's ruling covered repeats only. A `NODE_SETTLED` with no `NODE_STARTED` must stay legal (skipped, not reached, or a raised port), so the rule is one-way and needs a
  ruling.
- **Needs:** the owner's choice, none adopted: (a) refuse a start after the same step's settlement, with the same outcome or a new one, in the intake and the fold, as the repeat is; (b) leave it.

---

## Deferred — specified, deliberately not implemented

### D-026 — A2A boundary deferred to V0.6

- **Status:** Deferred · **Source:** handoff §8, §10, §50
- The A2A boundary contract is documented in `docs/07_a2a_contract.md` from what the handoff
  specifies. §50 places it at V0.6, after MissionState and the event reducer are reliable (§50
  V0.5: "Before adding A2A, state handling must already be reliable"). No A2A code, dependency or
  package exists.
- **V0.6 (2026-09-22):** the protocol/contract design is decided — **D-165 to D-176** — resolving **D-023, D-035, D-036, D-037** along the way. **No code exists yet**; this entry stays Deferred until
  implementation begins.

### D-027 — MCP tool boundary deferred to V0.7

- **Status:** Deferred · **Source:** handoff §27, §28, §50
- Documented in `docs/08_mcp_contract.md`. §27 caps the initial tool set at 2–3 (`search_documents`,
  `retrieve_evidence`) and warns against 20 tools in V1. No MCP code, dependency or package exists.
- **Annotated 2026-09-22 (D-184):** V0.7 was redefined as Strategy & Candidate Generation; MCP no longer has a
  reserved milestone number. It stays Deferred, unassigned, until a concrete requirement or benchmark needs it.
- **Annotated 2026-09-24 (D-203):** superseded in part: MCP is assigned to V1.2 (one pinned read-only tool, a minimal stdio client). The status line above is left as it was recorded.

### D-028 — Agentic RAG and Qdrant deferred to V0.8

- **Status:** Deferred · **Source:** handoff §24, §25, §26, §50
- Documented in `docs/09_rag_architecture.md`. §25 notes the collection schema "should be designed
  later". No Qdrant, embedding model, reranker, dependency or package exists.
- **Annotated 2026-09-22 (D-184):** V0.8 is now the Strategy Selector (V0.7 Step 1's own naming); RAG no longer
  has a reserved milestone number. It stays Deferred, unassigned, until a concrete requirement or benchmark needs it.
- **Annotated 2026-09-25 (D-208):** RAG now has a milestone, V1.3, as the knowledge/evidence layer only: a staged subset of what this entry deferred. Qdrant, reranking, the evidence judge and
  the agentic loop stay deferred and unassigned.

### D-127 — V0.3 explicit deferrals

- **Status:** Deferred · **Date:** 2026-09-19 · **Source:** V0.3 exploration and approvals (D-112 to D-126)
- Recorded so that nothing below can become part of V0.3 by accident. **Items that are Open decisions
  stay Open; deferral is not resolution.**

  | Deferred item | Governing entry | Not before |
  |---|---|---|
  | The predicate language for conditional primitives | **D-012 (stays Open)** | a decision before any conditional kind is supported |
  | Semantics of `ROUTE`, `RETRY`, `REPLAN`, `TERMINATE`, `HUMAN_APPROVAL` — all compile-rejected | D-112, D-012, D-055, D-058, D-061, D-125 | its own decision |
  | Automatic retries | D-119, D-125 | not assigned to a milestone |
  | A planner and the mission driver loop (plan → validate → compile → execute → verify → replan) | D-119, D-020 | not assigned to a milestone |
  | The MissionState reducer and the event log | D-123, D-126, D-039, D-076 | V0.5 |
  | LangGraph checkpointing and interrupts | D-113, D-120, D-010b, D-017 | V0.5 |
  | Runtime budget, time and token accounting, including reconciling declared with actual counts | D-122, D-043, D-046 | not assigned to a milestone |
  | The capability registry and capability-to-agent binding | D-007, D-018 (narrow, D-122) | V0.4 |
  | Async execution ports and A2A interfaces | D-122, D-026 | when a milestone needs them (V0.6) |
  | MCP and RAG | D-027, D-028 | V0.7, V0.8 |
  | Policy semantics | D-060, D-061, D-074, D-110 | V1.2 |

- **Recorded for visibility, not decided:** V0.2's POLICY stage reports `NOT_APPLICABLE` (D-110), so a
  plan that V0.3 compiles has had no policy evaluation. At V0.3 only mock agents execute, so nothing
  ungoverned has any effect. Whether real agents may execute before a policy exists is a V0.4 question
  for the owner.
- **V0.4 (2026-09-20):** the single-pass runner is now in V0.4 (**D-131**); the planner and a replanning loop stay unassigned. The
  capability registry and binding are scheduled for V0.4 (**D-134**). The question recorded above — whether real agents may
  execute before a policy exists — is **answered for V0.4 by D-140** (they are read-only and cannot act); policy semantics
  stay deferred.
- **V0.5 (2026-09-21):** the reducer and the event log are scheduled for V0.5 (**D-152** to **D-159**). **LangGraph checkpointing and interrupts are not part of V0.5:** a V0.5 checkpoint is a value,
  not a LangGraph checkpointer (D-157), and resume stays by prior `SUCCEEDED` outcomes (D-120). Runtime budget accounting stays unassigned: V0.5 records counters but enforces nothing (D-156).


### D-161 — V0.5 explicit deferrals

- **Status:** Deferred · **Date:** 2026-09-21 · **Source:** the V0.5 exploration and the owner's rulings (D-152 to D-160)
- Recorded so that nothing below can become part of V0.5 by accident. **Items that are Open decisions stay Open; deferral is not resolution.**

  | Deferred item | Governing entry | Not before |
  |---|---|---|
  | Durable persistence: SQLite, a file store, PostgreSQL, and where a checkpoint is stored | **D-017 (stays Open)** | an owner decision |
  | A stop reason in `MeasuredFacts`, and any policy for a non-empty answer cut off at the output limit | **D-151 (stays Open)** | when the model seam is next changed |
  | A2A events, the `AgentTask` lifecycle and producer-assigned sequences | D-026, D-035, D-036, D-037 | V0.6 |
  | MCP and RAG events | D-027, D-028 | V0.7, V0.8 |
  | The telemetry platform: OpenTelemetry, dashboards, aggregation, and the A2A, RAG, cache, policy-violation and human-intervention measures | handoff §33, §50 | V0.9 |
  | Quality, confidence, estimates and prediction error | **D-015, D-063, D-064 (stay Open)** | later milestones |
  | A distinct "contract not satisfied" status or event | **D-059 (stays Open)** | an owner decision |
  | Historical strategy memory, ranking, the selector, pilots, exploration and adaptive learning | handoff §21, §22, §50 | V1.0, V1.1 |
  | A planner, a replan or retry loop, and a mission driver | D-119, D-125, D-127 | not assigned |
  | Resume of a paused mission, and a resume event | D-085, D-120 | not assigned |
  | Cross-mission storage, indexing and aggregation | — | V1.0 |
  | Artifact persistence and the general question of how a node receives its predecessors' outputs | **D-129, D-017 (stay Open)** | not assigned |
  | LangGraph checkpointing and interrupts | D-113, D-120, D-127 | not assigned |
  | Enforcement of any budget or limit against the counters | D-043, D-044, D-046 | V1.2 |
  | Reinforcement learning, DSPy optimisation, a vector database and an AI planner | handoff §22, §24 | outside V0.5 |

### D-196 — "V0.9" stays Telemetry; the benchmark stays unassigned; Strategy-to-Plan expansion is filed as V0.8 Steps 7–8

- **Status:** Accepted · **Date:** 2026-09-23 · **Decided by:** human owner
- **Source:** D-161's own deferral table (2026-09-21: "the telemetry platform... | V0.9"); `progress.md`'s
  milestone ladder (pre-existing row: "**V0.9** Telemetry... Not started"); `docs/03_architecture.md`'s own
  package table (`eidos.telemetry | ... | V0.9`); D-184's own V0.7 Step 1 "gap found (and reported, not
  resolved, at Step 1)" — the owner named "V0.8 (Selector), V0.9 (benchmark) and V1.0 (Strategy Memory)
  explicitly" but D-184's own ruling addressed only where MCP/RAG land, never whether V0.9 stops meaning
  Telemetry; D-183's own pre-existing phrasing, twice, "Strategy-to-Plan expansion (V0.8+, not built)"; this
  session's own most recent instruction, which named the work just implemented "V0.9 Step 1"/"V0.9 Step 2."
- **The finding this rests on:** "V0.9" was on record with three meanings — (1) **Telemetry**, the original,
  by far the most numerous and longest-standing (14+ references across `progress.md`, `decisions.md` and
  `docs/03_architecture.md`, dating to the project's earliest days); (2) **a controlled benchmark**, named once
  by the owner at V0.7 Step 1 (quoted in D-184's own "gap found" text) and never formally reconciled against
  (1) — an old, still-Open half of a question D-184 itself raised and left dangling; (3) **Strategy-to-Plan
  Expansion**, introduced this session by promoting an instruction header ("V0.9 Step 1/2") to a milestone
  label without checking it against (1) or (2) first. D-183's own pre-existing text already described this
  same work as "V0.8+, not built" — never "V0.9" — which is the strongest existing evidence for where it
  actually belongs.
- **Decision:**
  1. **V0.9 remains Telemetry**, unchanged. Nothing has ever formally superseded it; D-184's own ruling was
     explicitly scoped to MCP/RAG placement only.
  2. **The future controlled benchmark is not assigned a milestone number.** It is deferred, exactly as D-184
     already treats MCP and RAG — described by name only, numbered later, only when a concrete requirement
     fixes its actual slot.
  3. **Strategy-to-Plan expansion — the design step and the implementation step already completed this
     session — is renamed from "V0.9 Step 1/2" to `V0.8 Step 7` (design) and `V0.8 Step 8` (implementation)**,
     folded into V0.8 Strategy Selection's own step sequence rather than given a new top-level number. This
     matches D-183's own literal, pre-existing "V0.8+" phrasing exactly and requires reinterpreting nothing
     else.
- **Consequences:** no historical decision becomes false. The 14+ pre-existing "V0.9 = Telemetry" references
  (`progress.md`, `decisions.md`, `docs/03_architecture.md`) are accurate and untouched. D-184's own text is
  untouched — this decision closes the other half of the exact gap D-184 itself found and reported, without
  reopening D-184's own MCP/RAG ruling. D-194 and D-195's architectural content is **unchanged** — only their
  own "Source"/"Affects" cross-references were corrected from "V0.9 Step 1/2" to "V0.8 Step 7/8." D-129 stays
  Open, not closed, exactly as D-195 already states. No source code, test, or git commit history is touched —
  this is a documentation-and-decision-record correction only.
- **Affects:** `progress.md`'s milestone ladder and session log, `README.md`, `docs/03_architecture.md`.
  Resolves the V0.9-numbering half of the gap D-184 found and left open at V0.7 Step 1 (mirrors D-178's
  "resolves D-020" precedent). Does not reopen D-178 through D-195.

### D-197 — The first controlled benchmark's harness lives under `tests/`, not `src/eidos`; no new top-level directory

- **Status:** Accepted · **Date:** 2026-09-23 · **Decided by:** human owner (delegated the location call to inspection)
- **Source:** the owner's own final-approval instruction for "the first controlled EIDOS benchmark" ("Inspect the
  repository and determine the narrowest existing location/convention for experimental benchmark code. Do not
  assume the location from the design document... The benchmark must remain outside `src/eidos`"); CLAUDE.md §3
  ("do not create a package, module or directory before the milestone that fills it"); `progress.md`'s own
  "Intentionally not built yet" table, which already reserves `evaluation/` for **V1.1** specifically
- **The question, inspected before any file was written:** the benchmark itself is explicitly unassigned a
  milestone number (D-196), and `evaluation/` is explicitly reserved for a *different*, later milestone (V1.1,
  "evaluation harness, experiments") — so neither `src/eidos/evaluation` nor any other new package could be
  created for it without contradicting an already-Accepted decision. The repository has no `scripts/`,
  `tools/`, `benchmarks/` or `experiments/` directory of any kind (checked directly: the only top-level
  directories are `.claude`, `docs`, `src`, `tests`), so there was no existing non-`tests` convention to reuse.
- **Decision:** the benchmark's reusable machinery (`eidos_benchmark_harness.py`) lives in `tests/support/` —
  pythonpath'd, never itself collected, exactly like every other `eidos_*_factories.py` module already there.
  Its actual assertions and case tables live in `tests/scenarios/test_benchmark_execution_control.py` —
  `tests/scenarios/` is already scoped by CLAUDE.md §6 to "full missions, replanning, verification failure,
  budget exhaustion, policy violation," which the benchmark's own five task classes match almost verbatim, and
  it is already a collected `testpaths` entry in `pyproject.toml`. No new top-level directory is created; no
  `pyproject.toml` change is needed.
- **Consequences:** the benchmark composes only already-shipped `eidos` code (`eidos.agents`, `eidos.baseline`,
  `eidos.recording`, `eidos.planning`, `eidos.expansion`, `eidos.validation`, `eidos.telemetry`) — no core
  contract, `MissionEvent`, or `src/eidos` package is added or changed by this decision or by the benchmark it
  authorizes the location for. If a later milestone (most plausibly V1.1's own `evaluation/`) needs this
  machinery promoted into `src/eidos`, that is that milestone's own decision, not implied by this one.
- **Affects:** where this session's benchmark files were placed only. Does not reopen D-184 or D-196, and does
  not reserve or rename anything in `progress.md`'s "Intentionally not built yet" table.

### D-198 — V1.0 Execution Experience / Strategy Memory architecture (approved with a decision revision, 2026-09-23)

- **Status:** Accepted · **Date:** 2026-09-23 · **Decided by:** human owner, in two rounds — an initial architecture
  approval ("approved in direction, do not implement yet") followed by a detailed decision revision resolving nine
  named open items before any code was written
- **Source:** the V1.0 design-proposal inspection turn (no code); `docs/03_architecture.md`'s own pre-existing
  `eidos.memory | Strategy and execution memory | V1.0` package-table row; D-015/D-016/D-017/D-020/D-021/D-063/D-064
  (all confirmed still Open — no quality/confidence/persistence/signature mechanism exists anywhere to build on);
  `tests/unit/selectors/test_selectors_guards.py`'s own pre-existing, by-name prohibition on `"StrategyMemory"`
- **The research question:** "can measured execution experience from previous missions improve future strategy
  selection?" — answered by a new architecture layer, never by making EIDOS merely *appear* adaptive (ruling 12).

**Decision, in full:**

1. **`ExecutionExperience`** (`eidos.memory.experience`, pure) is the smallest immutable, factual record of one
   completed mission: identity, `strategy_id` + structural shape (`strategy_stage_shapes`, `strategy_verification`
   — no signature, D-021 stays untouched), task characteristics (`task_required_capabilities`, `task_risk_level`,
   `task_autonomy_level` — the only fields ever used for relevance), and every cost/outcome fact `TelemetryRecord`
   already carries, copied verbatim. No quality score, no confidence score, no strategy signature, no embeddings,
   no artifact text, no subjective judgment of any kind. `evaluate_experience(strategy, task_genome, telemetry, *,
   recorded_at)` is a pure function — `recorded_at` is caller-supplied, never read from a clock inside it.
2. **Strategy↔execution linkage lives only inside `ExecutionExperience`**, made once by whichever caller already
   holds both objects in scope at the moment a mission concludes. **No `strategy_id` is added to `Plan`,
   `MissionState`, `TelemetryRecord`, `ExecutionRecord`, or any `MissionEvent`** — inspection found this genuinely
   unavoidable to be untrue; the existing "external correlation suffices" reasoning (V0.9 Step 4) extends cleanly
   one layer further.
3. **Relevance** (`eidos.memory.relevance`, pure, V1.0 Step 2 — not yet built): a record is task-relevant to a new
   `TaskGenome` as **"same"** only if `required_capabilities` (as a set), `risk_level` and `autonomy_level` all
   match exactly; **"similar"** only if `risk_level`/`autonomy_level` still match exactly and the capability sets
   merely intersect (non-empty, non-total); **"irrelevant"** on any risk/autonomy mismatch, regardless of capability
   overlap, or on zero capability overlap. No cross-level transfer, ever. No embeddings, no semantic similarity.
   **No staleness/recency/decay rule in V1.0** — every relevant record is equally eligible regardless of age;
   recorded here explicitly as a deferred future limitation, not an oversight.
4. **Strategy relevance is separate from task relevance**: `StrategyId` is fresh every generation round (D-182), so
   a stored record is matched to a *current candidate* by structural shape (`strategy_stage_shapes`/
   `strategy_verification` equality), never by id.
5. **`eidos.memory` package boundary**: `experience.py` (pure, this step), `relevance.py` (pure, Step 2),
   `store.py` (Step 3 — the `ExperienceStore` Protocol and its one real JSONL implementation, the *only* file in
   the package ever permitted file I/O, mirroring `eidos.recording.ports.py`'s own established "Protocol and real
   implementation co-located" precedent). Depends only on `eidos.contracts`, `eidos.planning`, `eidos.runtime`,
   `eidos.state`, `eidos.telemetry` — the identical dependency shape `eidos.telemetry` itself already has, one
   layer further. **Not placed in `eidos.recording`**: that package wraps *live* injection points during one
   execution; `eidos.memory` constructs and queries a *derived, cross-mission* record strictly after execution — a
   different temporal/functional category, closer in kind to `eidos.telemetry`'s own "pure projection" role.
6. **`ExperienceInformedSelector`** (`eidos.selectors.experience_informed`, Step 4 — not yet built) is a fourth
   `Selector` implementation, alongside `DeterministicSelector`/`ModelAssistedSelector`. **No change to the
   `Selector` Protocol, `SelectorChoice`, or `select_strategy`'s own orchestration** — the new dependency
   (`eidos.memory`) and the actual relevance/history read happen inside `select()` itself, exactly where
   `ModelAssistedSelector.select()` already does its own I/O (a `ModelPort` call).
7. **Cold start**: `ExperienceInformedSelector(store, fallback=DeterministicSelector())`. No relevant experience for
   any candidate is **not** a `SelectorFailure` — it is the ordinary, common case, and collapses the algorithm to
   exactly `DeterministicSelector.select(candidates, task_genome)`, a provable equivalence (every candidate lands
   in the same tier, so only `structural_cost` differentiates them, bit-for-bit what `DeterministicSelector` already
   computes).
8. **The selection algorithm** — a lexicographic tuple comparison, never a scalar, mirroring D-188's own
   "`structural_cost` compared lexicographically, never weighted" discipline one layer up. Per candidate, using
   only its own structurally-matched, task-relevant `ExecutionExperience` records:
   - **Tier 0** — at least one record with `mission_status == COMPLETED and verified is True`. Broken, in order,
     by: (a) more verified successes (a plain count, never a rate); (b) fewer observed non-successes; (c) lower
     **sum** (never a mean — comparable only because (a)/(b) are already tied at that point) of
     `execution_time_used_ms` across its own verified-success records — cost/time used only this late, exactly as
     required.
   - **Tier 1** — no relevant record at all (genuinely untested). Ranked *above* Tier 2 deliberately: absence of
     evidence is neutral; observed failure is negative evidence and should count against a candidate more than
     having none. Falls straight to (d) below.
   - **Tier 2** — relevant records exist, none is a verified success. Broken only by fewer observed non-successes.
     **Deliberately not distinguishing by `failure_cause`** — ranking one failure type against another would need a
     subjective severity judgment with no basis in directly observed facts; considered and rejected.
   - **(d) Final, universal tie-break**: `structural_cost` (`eidos.planning.selector`, unmodified, reused directly)
     — applied within Tier 1 always, and wherever the above still ties.
   Preserves: candidate-set membership (chooses only from `candidates`), exact `StrategyId` identity (never
   reconstructs a `Strategy`), full determinism, no combined/composite score, no subjective failure-severity
   ranking. Not to be reinterpreted as a weighted-ranking model.
9. **Storage**: append-only JSONL (mirrors `EventLog`'s own D-157 precedent), local, zero new dependencies. The
   real adapter loads its file into an immutable tuple once; `append()` persists the new record **and** updates
   the in-memory tuple; `all()` returns the current cached tuple — the hot-path read is bounded and in-memory,
   never a per-call disk re-scan.
10. **Selector guards are deliberately revised, not deleted or weakened**:
    `tests/unit/selectors/test_selectors_guards.py`'s `ALLOWED_EIDOS` gains `"eidos.memory"`;
    `FORBIDDEN_CONCEPT_NAMES` drops `"StrategyMemory"` (with the module docstring's own explanatory sentence
    corrected to state why — V1.0 makes the original assumption genuinely false, mirroring the exact wording
    discipline D-196/V0.9 Step 3 already used for their own guard corrections);
    `test_the_package_has_the_expected_modules` gains `"experience_informed.py"`. A new
    `tests/unit/memory/test_memory_guards.py` mirrors `test_planning_guards.py`'s own discipline, scoped to
    whichever modules exist at each step.
11. **Benchmark 2** (Step 7, design only — not implemented): a genuine confound was found and avoided, not
    silently accepted — a *content*-based verification-failure design (one capability scripted to under-cite
    evidence) is structurally biased toward whichever topology gives `VERIFY` the broadest predecessor visibility
    (always the parallel shape, under D-195's own "`FINAL` depends on exactly the final stage" rule), which is
    *also* what `DeterministicSelector`'s own tie-break always prefers (fewest stages) — the two would coincide,
    leaving E1 nothing to demonstrably improve on. Revised to a **topology-driven** mechanism instead: a
    deterministic `AdmissionGuard` (`halt_when(lambda r: r.rank_in_level >= 1, ...)`, the existing test double
    already used in Benchmark 1's own constraint-violation case) halts any shape that dispatches more than one node
    per level. A two-capability `TaskGenome` yields exactly two candidates — linear (never halts, verifies
    successfully every time with uniformly sufficient citations) and parallel (always halts before `VERIFY`,
    non-success every time) — deliberately arranged so `DeterministicSelector`'s own bias and the reliably-failing
    shape coincide, so any behavioral shift by E1 is attributable only to memory. N = 5 sequential missions per
    task shape, across three independent two-capability pairs (research+cost, research+security, cost+security).
    D1 (`DeterministicSelector`, no memory), D2 (`ModelAssistedSelector`, no memory, scripted to the same parallel
    choice every time), E1 (`ExperienceInformedSelector`, memory accumulating within the sequence — mission 1
    falls back to `DeterministicSelector` identically to D1/D2, by ruling 7's own cold-start equivalence; from
    mission 2 onward, parallel's observed halt and linear's untested status should make E1 prefer linear). Reports
    a plain per-mission table only — never a combined score, a win rate, or a superiority claim (ruling 12).
- **Consequences:** `eidos.memory` is the milestone `docs/03_architecture.md`'s own package table already
  reserved for V1.0 — unlike D-197, no new decision is needed to justify the package's existence, only its
  internal shape (this entry). No existing contract changes. `Selector`/`SelectionResult`/`select_strategy` stay
  byte-for-byte as V0.8 left them.
- **Affects:** `eidos.memory` (new, this decision), `eidos.selectors` (Step 4, adds a module and revises two named
  guard checks), `tests/unit/memory/` (new). Does not reopen D-178 through D-197, D-015/D-016/D-017/D-021 (all
  stay Open, untouched), or any V0.1–V0.9 contract.
- **Implementation order** (each step its own inspect → implement → test → guard → mutation → report cycle, no
  step begun without the prior one's own explicit go-ahead): 1 `ExecutionExperience`/`evaluate_experience`; 2
  `relevant_experience`/`task_relevance`/`experience_for`; 3 `ExperienceStore`/the JSONL adapter; 4
  `ExperienceInformedSelector`; 5 guard revisions + dedicated memory guard tests; 6 an integration test proving the
  complete chain, `TaskGenome` → candidates → experience-aware selection → Strategy→Plan → execution → Telemetry →
  Experience → Memory → future selection; 7 Benchmark 2.

### D-199 — Within-mission replanning architecture (approved, 2026-09-24)

- **Status:** Accepted · **Date:** 2026-09-24 · **Decided by:** human owner, resolving a pre-implementation design
  turn's own four flagged open questions
- **Source:** a post-V1.0 capability-gap inspection (traced both executors' own failure outcomes, `MissionStatus`/
  `RunOutcome` semantics, `AdmissionGuard` behavior, verification/`ModelFailure` behavior, A2A `PAUSED`/resume
  (D-166 to D-177), `Plan` versioning/lineage, D-119, D-125, D-129, the reducer's own event vocabulary, and
  `ExperienceInformedSelector`), followed by a design turn resolving exactly the open questions it found
- **The gap, found by inspection, not assumed:** `Plan.version`/`parent_plan_id`/`replan_reason`,
  `SystemLimits.max_replans`/`ReliabilityContract.max_replans`, `replans_used` on `MissionState`/
  `ExecutionRecord`/`TelemetryRecord`/`ExecutionExperience`, `PlanStepKind.REPLAN` and
  `MissionEventType.REPLAN_TRIGGERED` have all existed since V0.1/V0.5/V0.9 — `replans_used` is permanently `0`
  everywhere (`reducer.py`'s own comment: "nothing produces them") and `REPLAN_TRIGGERED` is a bare enum member
  with no payload class and no reducer case. V1.0's own adaptive loop (Step 6/Benchmark 2, D-198) only ever
  adapts **across** separate, caller-orchestrated missions; nothing closes the loop **inside** one mission's own
  lifecycle — a mission that fails simply stops (`FAILED`/`PAUSED`), exactly as D-119/D-170 always documented.

**Decision, in full:**

1. **Replan eligibility** — a closed set, derived from the existing `MissionFailureCause`/`RunOutcome` taxonomy,
   no new failure category invented:
   - Eligible: `EXECUTION_FAILED`, `NO_RESULT`, `VERIFICATION_FAILED`, `VERIFICATION_INCONCLUSIVE` (all
     `RunOutcome.FAILED`), **and `RunOutcome.FINISHED` with `verified=False`** — completion is not success
     (invariant 12, D-156); an unsatisfied reliability outcome may trigger a bounded replan exactly as a genuine
     failure may.
   - Never eligible: `PLAN_REJECTED`, `RUN_REJECTED` (mission-level/pipeline defects a different candidate
     strategy cannot fix), and **`RunOutcome.HALTED`** (an admission-guard halt) — **stays terminal for that
     attempt, exactly as D-176 already shipped it; it must never automatically trigger a different strategy.**
     This decision does not reopen or narrow D-176 — it only decides that the *new* replan mechanism (§4 below)
     never engages for a halted attempt, the identical restriction every other caller already has.
   - `RunOutcome.AWAITING` (A2A) is untouched: this mechanism applies only to the synchronous, `record_baseline`
     -driven execution path; `accept_resumed`/`reduce_resumed` (D-177) remain the sole path past an A2A pause.
   - A successful, verified completion is, as always, terminal with no replan question to ask.
2. **Fallback strategy selection**: the bounded candidate set (`generate_candidate_strategies`, `max_candidates`
   -bounded) is generated **exactly once**, at mission start. Each replan re-invokes the **same, already-shipped
   `Selector`** the mission was configured with, over the same candidate tuple with every already-attempted
   `StrategyId` filtered out by identity (safe: these are the same in-mission objects, never a fresh id drawn
   across missions, D-182). No `Selector` Protocol change, no new selector implementation, no scalar score, no
   candidate regeneration (structurally pointless: `RuleBasedCandidateGenerator` is a pure function of the
   genome/limits, so a second call could only draw fresh, useless ids for the identical shapes, D-182). Exhaustion
   is the existing `SelectionOutcome.NO_FEASIBLE_CANDIDATES`, not a new outcome.
3. **Replan lineage**: `Plan.version` increments per attempt; `parent_plan_id` names the immediately preceding
   attempt's own `plan_id`; `replan_reason` is **deterministically derived from the failed attempt's own
   `MissionFailureCause`/reason** — never an LLM-generated or otherwise non-deterministic string.
   `replans_used` increments once per accepted replan (a decision to try again), never once per bare failure.
4. **Event/state semantics**: a `ReplanTriggeredPayload` (finally giving the already-declared
   `MissionEventType.REPLAN_TRIGGERED` a real shape) is recorded for an attempt that will be retried. It
   **never sets `MissionState.status`** — `MissionStatus` has only four values by design (D-052; no
   `EXECUTING` state), so a mission already sits in `CREATED` throughout its whole run, and `CREATED` is not in
   `_TERMINAL`. This is why **no new `accept_replanned`/`reduce_replanned` mechanism is needed**, unlike D-177's
   own A2A resume — the mission is never actually terminal until it genuinely is. Only the final attempt (success
   or genuine exhaustion) reaches the existing `_finish` translation and its existing three terminal payloads,
   completely unchanged. One continuous `EventLog` covers the whole mission, every attempt.
5. **Mission termination**: a replan success ends the mission `COMPLETED` on the winning plan, as today.
   Exhaustion (no untried candidate left, or `max_replans` reached first) ends the mission on the **last
   attempted strategy's own real, honest outcome** — never a synthetic "replans exhausted" cause. `max_replans`
   uses whatever the mission's own configured `SystemLimits`/`ReliabilityContract` bound already is; **no numeric
   default is introduced by this decision** (mirrors D-046's own still-Open "no numeric bound values decided"
   stance) — a mission with no configured bound has no replanning to do, by construction, not by a silently
   invented fallback.
6. **Memory interaction**: an `ExecutionExperience` is appended **after every completed attempt** — including a
   failed or `verified=False` one — **before** the next strategy is selected, so `ExperienceInformedSelector`
   (unmodified) can already see it on the very next `select_strategy` call within the same mission, exactly as it
   already sees cross-mission history today. `ExperienceStore`/`ExperienceInformedSelector`/`relevant_experience`/
   `experience_for` semantics are **unchanged** — this exercises the existing tiered algorithm one call earlier
   than usual, not a new algorithm.
- **The one genuinely necessary signature extension found**: `execution_record()`/`project()` currently project
  only "the active plan, or the last one" — insufficient to build a clean per-attempt `TelemetryRecord` for an
  already-abandoned plan version once a later one is active. Both gain one additive `plan_id: PlanId | None =
  None` keyword parameter; the default reproduces today's exact behavior for every existing caller.
- **Consequences**: no change to `Plan`/`MissionState`/`TaskGenome`/`ReliabilityContract`/`Strategy`/
  `AgentTask` as *data contracts* (only `expand_strategy`'s own construction of a `Plan` gains new optional
  parameters, §3); no change to the `Selector` Protocol or any of its three implementations; no change to
  `eidos.memory` (any file); no change to the V0.2 validation pipeline, the compiler, or either runtime executor;
  no change to `EventLog`, `reduce_resumed`/`accept_resumed` or A2A's own resume mechanism, and `reduce`'s behaviour for every existing
  event is unchanged; the reducer gains exactly one new `isinstance` case, for `ReplanTriggeredPayload` (V1.1 Step 3), and nothing else.
  *(Corrected by D-202: this line first said there was no change to `reduce`, which contradicted the reducer case this same decision
  specifies under Affects.)* `PLAN_REJECTED`/`RUN_REJECTED`/
  `HALTED`/`AWAITING` handling is read, never altered.
- **Milestone note** (mirrors D-196's own precedent of correcting a stale label against reality rather than
  silently ignoring it): the milestone ladder's pre-existing "V1.1 Adaptive Learning" row (`progress.md`)
  describes "historical ranking, exploration, empirical estimation, prediction-error tracking" — none of which
  is this work. This decision's own scope is filed as **V1.1 — Within-Mission Replanning**, and the ladder's own
  V1.1 description is corrected to match, exactly as D-196 corrected a stale V0.9 description rather than
  inventing a new number or silently building under a mismatched label. *(Clarified by D-202: the "V1.1 Adaptive Learning" row restated the
  handoff's own V1.1 list, so what this decision relabelled is a divergence from the handoff, not only from a `progress.md` placeholder.)*
- **Affects:** `eidos.expansion` (Step 1, additive `expand_strategy` parameters only), `eidos.state` (a new
  payload + one reducer case; `execution_record`'s new optional parameter), `eidos.telemetry` (`project`'s new
  optional parameter), a new narrow orchestration function (location proposed at implementation time, sibling to
  `eidos.baseline`, not a new package). Does not reopen D-119, D-125, D-129, D-176, D-177, or any V0.1–V1.0
  contract or decision; D-129 stays Open, untouched.
- **Implementation order** (each step its own inspect → implement → test → guard → mutation → report cycle, no
  step begun without the prior one's own explicit go-ahead): 1 `expand_strategy`'s additive lineage parameters;
  2 `execution_record`/`project`'s additive `plan_id` scoping parameter; 3 `ReplanTriggeredPayload` + its one reducer
  case; 4 the replan orchestration function; 5 the full test/mutation/documentation pass. *(Corrected by D-202: this
  line first listed steps 2 and 3 in the reverse order; they were built as shown here, commits `ec3993c` and `24ae94d`.)*


### D-200 — Fresh work-step ids across plan versions for a within-mission replan (Option 1 approved, 2026-09-24)

- **Status:** Accepted · **Date:** 2026-09-24 · **Decided by:** human owner · **Resolved by the owner's ruling** (originally Open; Option 1 chosen)
- **Source:** D-147, D-194, D-199; found running the real V1.1 Step 4 orchestrator against real V0.4 agents
- **Ruling (Option 1):** version-aware step ids for replanned plans, applied at the plan producer.
  1. **Plan version 1 preserves the D-194 id scheme exactly:** `stage{stage_index}_{position}_{capability}`, byte for byte
     as before V1.1. **D-194's original version-1 ids are unchanged**, so every existing version-1 plan, hash and benchmark
     digest is untouched.
  2. **Plan versions greater than 1 use a deterministic version-aware namespace:** `v{version}_stage{stage_index}_{position}_{capability}`.
     The stage/position/capability structure is preserved as a suffix; no randomness and no UUID is involved. Every work-step id
     of version N therefore differs from every work-step id of every other version (a version-1 id starts with `stage`, a
     version-N id with `v{N}_`, and `N` is digits-only so it is recovered uniquely from the first `_`).
  3. **The `verify` control step keeps its id.** It is not a work step: it stores no artifact, and the intake's repeated-step
     guard is keyed by (event type, plan, step) (D-162), so a `verify` step in another plan version is another step.
  4. **Nothing else changes.** The artifact store stays write-once and `artifact:<step_id>` / `(execution_id, step_id)` identity is
     unchanged (D-137, D-147). No fresh artifact store per attempt (D-147 option c) and no plan-scoped artifact keys (option b)
     are introduced. **D-147 is not weakened:** its guard still refuses a reused work-step id before any model call, and now
     a replan produced by `expand_strategy` never asks it to.
- **Rationale:** D-147 (option a) already places the obligation on whoever chooses step ids across versions. V1.1 Step 1 added
  `version` to `expand_strategy` but left the ids version-independent, so a replan's plan v2 collided with v1's stored artifacts.
  This is a necessary compatibility correction discovered at Step 4 integration, **not** a widening of the V1.1 milestone.
- **Affects:** `eidos.expansion.expand` only (`_agent_step_id` gains the version). Amends the D-194 id scheme for `version > 1` only. The
  V1.1 Step 1 test asserting a replanned plan's step ids equal a fresh plan's is superseded by this ruling and rewritten to assert what
  still holds (same shape, same capabilities, same dependency structure).


### D-201 — V1.1 Step 4: the cause of a replan after an unverified completion, and a mission with no selectable first strategy (both approved, 2026-09-24)

- **Status:** Accepted · **Date:** 2026-09-24 · **Decided by:** human owner · **Resolved by the owner's ruling** (originally Open; both provisional behaviours resolved)
- **Source:** D-199, D-200; found implementing `run_with_replanning` (V1.1 Step 4); CLAUDE.md §7 (a gap is recorded and raised, never resolved silently)
- **Item 1 — the cause recorded for a replan after a `FINISHED`, `verified=false` attempt: accepted as built.** `ReplanTriggeredPayload.cause` (V1.1 Step 3) is a
  `MissionFailureCause`, which has six members; none means "finished, but nothing verified it". The outcome is replan-eligible under D-199 ruling 2 but is
  reachable only when a candidate's `VerificationPosture` is `NONE`, which `RuleBasedCandidateGenerator` never produces for a non-empty genome (a custom
  `CandidateGenerator` can). **Ruling:** the closest existing member, `VERIFICATION_INCONCLUSIVE`, is used with the reason
  `finished without a successful VERIFY (verified is false)`, both in the recorded payload and in the next plan's `replan_reason`. **No seventh
  `MissionFailureCause` member is added, `cause` is not made optional, and no other failure taxonomy is introduced.** The abandoned attempt's own
  `ExecutionExperience` is unaffected: it records `COMPLETED`, `verified=false` and no `failure_cause`.
- **Item 2 — a mission with no selectable first strategy: a typed rejection, not an exception.** This is a pre-execution condition: no strategy was selected,
  no `Plan` was generated, no attempt ran, no event was recorded (not even `MISSION_CREATED`) and no `ExecutionExperience` was appended. **Ruling:**
  `run_with_replanning` returns `ReplanRun | ReplanRejection` — the same union-return convention as `ReplayRejection` and `ExperienceLoadRejection`
  — and raises nothing for this outcome. `ReplanRejection` carries a `ReplanRejectionCode` (one member, `NO_SELECTABLE_STRATEGY`), the existing
  `SelectionOutcome` saying why the first selection produced nothing (`NO_FEASIBLE_CANDIDATES`, `SELECTOR_FAILED` or `INVALID_CANDIDATE_RETURNED`, never
  `SELECTED`), and that selection's own reason. **It carries no `MissionFailureCause`, and none is invented for this case:** no mission ever failed, because
  none ever began. A refused selection *after* a first attempt is unchanged: the mission ends on that attempt's own real outcome (D-199).
- **Effect:** the rest of the accepted Step 4 behaviour is unchanged. `MissionFailureCause` keeps exactly its six members, pinned by a test.


### D-202 — V1.1 close-out: exhaustion semantics, cross-attempt budgets and the handoff milestone conflict (Accepted, 2026-09-24)

- **Status:** Accepted · **Date:** 2026-09-24 · **Decided by:** human owner · **Resolved by the owner's rulings** (raised by the V1.1 Step 5 close-out audit)
- **Source:** the V1.1 Step 5 audit of the five commits `e2e216f`, `ec3993c`, `24ae94d`, `312c25c`, `bf97922`; CLAUDE.md §0, §7 and invariants 6 and 7; the handoff's
  milestone list; D-043, D-127, D-156 item 5, D-199, D-200, D-201
- **Ruling 1 — invariant 7 and `max_replans` exhaustion (wording reconciled, no implementation change).** The bounded-replan invariant limits *additional
  attempts*; it does not prescribe `PAUSED` as the terminal state. Once no further replan is permitted (the effective `max_replans` is reached, or no untried
  candidate remains), the mission terminates according to the outcome of the final attempted plan: `COMPLETED` (with `verified` false where that is what the
  attempt produced), `FAILED` with that attempt's own cause, or `PAUSED` only if that attempt was itself halted or is awaiting a remote task (D-176, D-177).
  Replan exhaustion does not by itself require `MissionStatus.PAUSED`. This is the reading D-199 ruling 5 was already built on; it is stated here so it no longer
  sits in tension with invariant 7's sentence "Exhaustion pauses the mission for human review". CLAUDE.md and the handoff are not edited; the reading is recorded
  here and beside the invariant in `docs/12_architecture_invariants.md`.
- **Ruling 2 — cross-attempt budgets (no cumulative enforcement is added; runtime behaviour is unchanged).** What V1.1 actually guarantees: (a) every attempt is a full
  pass through the existing pipeline, so per-plan limits are enforced for each individual attempt (plan validation, including the declared-agent-step check against
  the effective `max_agent_calls`, and the complexity limits); (b) the number of attempts is bounded by the effective `max_replans` (`min(system ceiling, contract value)`,
  D-065), and by the number of candidates (`max_candidates`). What it does not guarantee: a mission-wide total across attempts. Observed in an audit probe run, not a
  committed test: with a contract `max_agent_calls` of 2 and a two-capability mission that replanned once, each plan declared 2 agent steps and the mission finished
  with `agent_calls_used` 4 and no halt. Cumulative mission-wide budget enforcement across replan attempts remains an open, deferred issue that belongs to the
  pre-existing design: D-043 (declared plan limits against actual counters, Open), D-127 (enforcement deferred) and D-156 item 5 (counters are recorded, not enforced).
  No new Open decision is created; those three are unchanged.
- **Ruling 3 — the handoff milestone conflict (recorded, not resolved by editing the handoff).** The handoff, which is not modified, defines V1.1 as *Adaptive Learning*
  (strategy memory, historical ranking, exploration, empirical estimation, prediction-error tracking) and V1.2 as *Reliability/Governance* (policy engine, autonomy
  levels, human approval, failure recovery, replan limits, execution budgets). D-199 filed the implemented scope as V1.1 Within-Mission Replanning and described the
  older label as a `progress.md` placeholder; that row was in fact the handoff's own V1.1 list. Ruling: the implemented V1.1 scope stays exactly as D-199 defines it
  (within-mission replanning/self-healing). The older handoff V1.1 label and its remaining items, including exploration, empirical estimation and prediction-error
  tracking, are **not part of the completed V1.1 implementation and remain deferred and unassigned until explicitly decided** (historical strategy memory and selection
  were delivered under V1.0, D-198, to the extent built there). V1.2 keeps its wider governance items: V1.1 implemented only the narrow, bounded within-mission replan
  and none of the policy engine, autonomy levels, human approval or execution-budget enforcement. `eidos.evaluation` is unassigned.
- **Documentation corrections made with this decision (documentation only):**
  1. Stale "not pushed"/"none pushed" claims in `README.md` and `progress.md` were corrected against git: `git reflog show origin/master` records pushes on 2026-09-22,
     2026-09-23 and 2026-09-24, and V0.6 to V1.0 are all ancestors of `origin/master` (`a2a53fc`); only V1.1 remains local.
  2. The `README.md` paragraph that said there is no planner, A2A or persistence was rewritten to match what exists.
  3. D-199's implementation-order line now has step 2 as `plan_id` scoping and step 3 as the payload and reducer case, as built.
  4. D-199's consequence text no longer says the reducer was unchanged; it says exactly one case was added.
  5. "V1.0 proved ..." and the three other Benchmark 2 "proving" claims (the README status paragraph, the `progress.md` status line and the V1.0 ladder row) now read as a
     controlled, scripted demonstration with no statistical validation.
  6. `docs/03_architecture.md` lists `record_attempt` and `terminal_payload_for` under `eidos.recording`.
  7. `docs/06_mission_state.md` documents the `REPLAN_TRIGGERED` payload.
  8. Milestone references that contradicted the recorded V1.1 scope were corrected where necessary: the `eidos.evaluation` rows in `docs/03_architecture.md` and
     `progress.md`, and one line each in `docs/09_rag_architecture.md` and `docs/11_evaluation.md`. Dated historical narrative in `progress.md` that names V1.1 as
     Adaptive Learning or as the evaluation package is left as the record it is.
- **Effect:** documentation and governance only. No source, test, contract or behaviour changes. D-043, D-127 and D-156 are unchanged, and no new Open decision is created.


### D-203 — V1.2 MCP / Tool Intelligence: scope, minimal tool policy and the vertical slice (approved, 2026-09-24)

- **Status:** Accepted · **Date:** 2026-09-24 · **Decided by:** human owner · **Resolved by the owner's rulings** (proposal: the V1.2 readiness pass, read-only, at `57180fc`)
- **Source:** handoff §27, §28, §29, §50, §63; D-027, D-028, D-094, D-101, D-110, D-127, D-132, D-135, D-140, D-160, D-171, D-184, D-202; CLAUDE.md §3, §6 and invariants 3, 9, 11, 12, 14, 15, 16
- **What the readiness pass found (by inspection, not assumed):** no tool exists: there is no `eidos.mcp`, no tool contract and no dependency. Inert hooks exist:
  `ReliabilityContract.max_tool_calls`, `MissionState.tool_calls_used` (never produced), `MissionEventType.MCP_TOOL_CALLED` (no payload), `TaskGenome.allowed_actions` (opaque strings,
  D-094, read by nothing) and `autonomy_level` (D-014). D-140 makes agents read-only with no tools and says a later tool needs policy decided first; D-127 and `docs/08` §7 placed
  policy semantics at V1.2; D-184 left MCP unassigned until a concrete requirement exists. The Research agent returns `NO_RESULT` whenever no documents are supplied. The MCP
  specification has also moved: when checked, the published latest revision was `2026-07-28` (no `initialize` handshake; per-request `_meta`; a `server/discover` method), while
  revisions up to `2025-11-25` use `initialize`. That reading came from a summarised fetch and is re-verified at Step 5.
- **Decision, in full:**
  1. **Milestone.** V1.2 is MCP / Tool Intelligence. The authoritative handoff is preserved: it defines V1.2 as *Reliability/Governance* (policy engine, autonomy levels, human approval,
     failure recovery, replan limits, execution budgets). Those handoff V1.2 governance items are **deferred and unassigned** until explicitly decided. The concrete trigger D-184 asked for is the
     Research agent's `NO_RESULT` when no documents are supplied.
  2. **Minimal deterministic policy, and nothing more:** a pinned tool allowlist; an exact match between the tool's `action_id` and `TaskGenome.allowed_actions`; `autonomy_level` >= 1
     (`SAFE_READ_ONLY`, handoff §29); read-only tools only; `max_tool_calls`; argument and schema validation; timeout and result-size bounds; deterministic, typed denial. **No general policy
     engine is built.** Server-declared tool annotations are never trusted: read-only comes from the allowlist.
  3. **MCP client.** A minimal, hand-rolled, standard-library client. MCP transport stays inside `eidos.mcp`. Before the wire protocol is implemented, the current published specification is
     re-verified and the one revision the reference server needs is implemented. No historical protocol compatibility is added unless an actual requirement appears (a server speaking another
     revision is refused with a typed failure, not adapted to). **No SDK dependency; `pyproject.toml` does not change.**
  4. **Event model.** No new MCP or tool event. Additive `tool_calls` facts on `NODE_SETTLED`, following the existing model-call recording pattern (D-160). Old logs replay unchanged.
  5. **Tool-call budget.** No cumulative mission-wide `max_tool_calls` enforcement; the V1.1 and D-043 ruling that cumulative cross-attempt budgets are deferred (D-202 ruling 2) is preserved.
     The frozen reading:
     - `max_tool_calls` is enforced per plan attempt, scoped by `(execution_id, plan_id)`;
     - each replan starts a fresh tool-call budget;
     - duplicate detection remains execution-wide, identified by `(execution_id, tool_id, args_digest)`;
     - a duplicate served from the stored artifact invokes no external tool and consumes no invocation budget;
     - cumulative mission-wide tool-call enforcement remains deferred under D-043.
  6. **Evidence.** Tool-retrieved documents may satisfy `min_independent_evidence` when they are independently identifiable and traceable to their tool call and source. **The verification rules
     do not change.** Provenance is preserved in the artifact reference and in the recorded tool-call fact.
  7. **Architecture.** Strategy is unchanged. The Plan DSL is unchanged. **There is no `TOOL` plan step.** Tool use happens inside the Research agent through a `ToolPort`. No new capability
     (D-132's five stay) and no fourth agent.
  8. **MVP.** Exactly one local, read-only, stdio MCP server exposing `search_documents`, with keyword matching only. Excluded: RAG, Qdrant, embeddings, OAuth, HTTP/SSE, resources, prompts, sampling,
     elicitation, write tools, tool-selection intelligence, learning, a human-approval flow, artifact persistence and multiple servers.
- **Readings carried from the approved design (not additional rulings):**
  - Tool policy is evaluated **at call time only**. The plan-validation POLICY stage stays `NOT_APPLICABLE` (D-110); a plan never names a tool.
  - Each retrieved document becomes its own artifact with its own reference, so distinct documents are distinct sources; the reference carries the tool id and provenance, and the recorded
    tool-call fact lists the references it produced.
  - Placement: the `ToolPort` seam and its typed request, result and failure in `eidos.agents` (as `ModelPort`, D-135); `ToolDescriptor` and `ToolRegistry` in `eidos.capabilities`; the pure
    admission function in a new `eidos.policy`; transport in a new `eidos.mcp`; a recording wrapper in `eidos.recording`. `tool_id` is a plain non-empty string, so `eidos.contracts` does not change.
  - A tool failure or a denial is a typed result, never an exception, and a tool call that succeeds is neither evidence sufficiency nor mission success (invariant 12).
- **What does not change (frozen):** V1.1 in full (`expand_strategy`, the `plan_id` scoping of `execution_record`/`project`, `ReplanTriggeredPayload` and its reducer case, `run_with_replanning`,
  `ReplanRejection`, D-199 to D-202) and every V0.1 to V1.0 decision. Also unchanged: Strategy, the Plan DSL and `PlanStepKind`, the capability vocabulary, the compiler and both executors, the
  validation pipeline, A2A, the selectors, `ExperienceStore`, `TelemetryRecord` and `ExecutionExperience`, and `MissionEventType` (`MCP_TOOL_CALLED` stays an unused vocabulary slot).
  `tool_calls_used` keeps the V1.1 semantics of a whole-mission running total; exact per-attempt tool counts come from the per-step facts.
- **What changes, additively only:** new `eidos.mcp`, `eidos.policy` and tool types in `eidos.capabilities` and `eidos.agents`; `ToolCallFacts` and `NodeSettledPayload.tool_calls` (default empty)
  in `eidos.state`; the reducer's `NODE_SETTLED` case also folds `tool_calls_used` from admitted invocations; `StepRecord.tool_calls`; the recorder's observation carries tool facts; the model-call
  tracker also collects tool facts so that `record_baseline` and `record_attempt` keep their signatures; the Research agent gains optional tool access. One V1.1-era private helper,
  `_record_settled_nodes`, passes the new field through. The module docstrings that say agents have "no tools (D-140)" are updated when the Research agent changes.
- **Implementation order:** 1 record this decision (documentation only); 2 tool contracts and deterministic admission (pure); 3 tool-call facts in state and replay; 4 Research → `ToolPort` →
  admission → recording, using a **scripted** `ToolPort`; 5 the real minimal MCP client, with protocol tests against a real subprocess; 6 the end-to-end vertical slice on the real subprocess path, and the close-out audit.
  MCP protocol tests go in `tests/protocol/`, which holds no tests yet (CLAUDE.md §6). Acceptance criteria are recorded in `progress.md`.
- **Still Open, unaffected:** D-060, D-061, D-074, D-110, D-043, D-127, D-156, D-017 and D-129. **D-204** records two gaps found while inspecting the affected contracts and is **Open and deferred**:
  V1.2 does not modify `run_with_replanning`, `record_attempt`, tracker propagation or any V1.1 execution-path signature. Tool-call facts (like model-call facts) are therefore captured through
  the baseline recording path (`record_baseline`) only; replanned executions do not capture them, and V1.2 makes no claim that they do.
- **Effect:** documentation only at this step. No source, test, contract or dependency changes.


### D-204 — Recording-tracker propagation under replanning, and `tool_calls_used` plan scoping (OPEN, deferred)

- **Status:** Partly ruled, partly Open (item 1 directed by the owner on 2026-09-26, specified and accepted in D-231 and implemented in V1.4-B; item 2 stays Open and deferred) · **Date:** 2026-09-24 · **Decided by:** human owner (kept Open and deferred in V1.2; item 1 directed for V1.4)
- **Source:** the V1.2 readiness inspection; D-199, D-160, V1.1 Step 2; CLAUDE.md §7 (a gap is recorded and raised, never resolved silently)
- **Ruling:** D-204 stays **Open and deferred**. **V1.2 does not modify `run_with_replanning`, `record_attempt`, tracker propagation, or any V1.1 execution-path signature.** It does not block
  V1.2 and is not to be fixed now.
- **Item 1 — the finding:** replanned executions currently do not propagate the recording tracker used by the baseline recording path, so model and tool call facts are not currently captured
  through that path. Evidence, a probe and not a committed test: with the model wrapped in a `RecordingModel` sharing the caller's tracker, `run_with_replanning` finished with
  `telemetry.model_call_count` 0 and 0 model calls on every settled node. `record_attempt` creates its own default tracker and `run_with_replanning` has no `tracker` parameter, so the
  caller's tracker is never the one the recorder reads. `record_baseline` accepts a tracker and is not affected. The V1.1 Step 4 note that model-call facts were "not exercised at this layer"
  understated this: wrapping the model would not have recorded them either.
- **Item 2 — `tool_calls_used` under plan scoping:** V1.1 Step 2 left `tool_calls_used` as the whole-mission total under `execution_record(plan_id=...)` because no per-node source existed. Once
  V1.2 records per-step tool facts it could be scoped per plan like `agent_calls_used`. V1.2 keeps the V1.1 semantics: it stays a whole-mission running total, and exact per-attempt tool counts
  come from the per-step facts.
- **Candidate resolutions, not to be taken in V1.2:** item 1, an additive optional `tracker` parameter on `run_with_replanning` passed to `record_attempt` (this changes a frozen V1.1 signature);
  item 2, scoping `tool_calls_used` per plan (this changes documented V1.1 behaviour). Each needs its own ruling.
- **Effect:** none on V1.2. The vertical slice runs through `record_baseline`, and tool-call facts are captured through that path only. V1.1 behaviour is unchanged.
- **V1.4 (2026-09-26, D-231):** the owner directed that the API's execution path is the full `run_with_replanning` and that **item 1 is resolved by an additive, optional tracker parameter**; D-231 specifies the exact change (one keyword-only `tracker` parameter forwarded to `record_attempt`, default unchanged). **Item 2** (`tool_calls_used` per plan) stays Open and deferred. **Item 1 resolved (V1.4-B, 2026-09-27):** implemented and tested (D-231): with a tracker, the model, retrieval and citation facts of every attempt of a replanned mission are recorded on the settled nodes.


### D-205 — V1.2 Step 2: readings taken where D-203 was silent (items 1, 2, 4, 6 and 11 ruled 2026-09-25; the rest OPEN)

- **Status:** Partly ruled, partly Open · **Date:** 2026-09-25 · **Raised by:** Claude Code while implementing V1.2 Step 2 (pure tool contracts and deterministic admission) · **Decided by:** the human
  owner, for items 1, 2, 4, 6 and 11 only (marked **Ruled**); items 3, 5, 7, 8, 9 and 10 are readings taken and **not yet confirmed**
- **Source:** D-203 rulings 2, 5, 7 and 8; D-009, D-046, D-065; handoff §14, §28, §32; `docs/08`; CLAUDE.md §7 and invariants 7, 12, 14; the contracts and package guards as inspected at `e3968c7`
- **Why recorded:** Step 2 implements every D-203 rule as ruled. D-203 fixed *what* admission enforces, not every detail of *how*, and a gap is recorded, never resolved silently (CLAUDE.md §7). Each
  reading below is the smallest implementation, is local to `eidos.capabilities`, `eidos.agents` and `eidos.policy`, and can be reversed without touching a V1.1 file, `eidos.contracts` or D-204.
  The owner's rulings of 2026-09-25 reopen nothing in D-203 and change no V1.1 contract; D-204 stays Open and deferred.
- **Items:**
  1. **An absent `max_tool_calls`. Ruled (owner, 2026-09-25).** `ReliabilityContract.max_tool_calls` is `int | None` (D-065: every budget is optional). `None` does **not** mean unlimited (invariant 7),
     does not silently become zero and is never replaced by an invented numeric default. Admission requires an explicit finite integer budget: `admit_tool_call` takes `int | None`, and `None` is
     unresolved configuration, denied deterministically with the typed, returned denial `BUDGET_UNRESOLVED`. A value that is set but is not a non-negative integer (a negative number, a `bool`, a float
     such as infinity) is a programming error and raises. The budget semantics are unchanged: scoped `(execution_id, plan_id)`, a fresh budget for each replan, duplicate detection execution-wide on
     `(execution_id, tool_id, args_digest)`, a served stored duplicate consuming no invocation budget, and cumulative mission-wide enforcement deferred under D-043. **Not changed, not decided:**
     `ReliabilityContract` and its `None` default; `SystemLimits.max_tool_calls` (a plan-validation ceiling in `eidos.validation`), which is not used as a fallback here; D-009 and D-046 (the value and its
     source of authority stay Open).
     **Owner addendum, V1.2 close-out (2026-09-25): D-205 supersedes D-065 for V1.2 tool admission.** For the V1.2 tool-admission contract, `max_tool_calls=None` produces `BUDGET_UNRESOLVED`;
     it must not fall back to `SystemLimits.max_tool_calls`; there is no implicit unlimited, default or zero behaviour; and the existing per-`(execution_id, plan_id)` budget semantics are preserved.
     D-065 is kept historically intact and now carries a cross-reference saying its omitted-budget fallback does not govern this boundary. The supersession is scoped to tool admission; it decides
     nothing about any other budget field or consumer, and D-009 and D-046 (the numeric value) stay Open.
  2. **Order of the rules, and the unset budget against duplicate detection. Ruled (owner, 2026-09-25).** D-203 lists the rules without an order. Fixed order: first the precondition of item 1
     (`BUDGET_UNRESOLVED`), then unknown tool, not read-only, action not allowed, autonomy below 1, invalid arguments, duplicate, budget; the first failing rule decides the denial. **The ruling:**
     `BUDGET_UNRESOLVED` takes precedence over duplicate detection. An admission request with `max_tool_calls=None` is rejected deterministically before any duplicate lookup, so a stored duplicate is
     not served when the current execution attempt has no explicit tool-call budget. This is a configuration and admission precondition, not a tool invocation and not a consumed budget. All existing
     semantics are preserved: an explicit finite budget only; the budget scoped `(execution_id, plan_id)`; a fresh budget for each replan; duplicate identity `(execution_id, tool_id, args_digest)`; a
     served duplicate consuming no invocation budget; and cumulative mission-wide tool-call enforcement still deferred (D-043). As implemented, the precondition is decided before every rule, the
     duplicate lookup included (the history is not even read); the ruling states the precedence over duplicate detection and calls the check a precondition, and does not separately address the four
     policy rules that precede the duplicate rule. Because the duplicate check follows every policy rule and precedes the budget rule, an explicit-budget request for an exact duplicate is served even when
     the attempt's budget is spent (ruling 5: it "consumes no invocation budget"), and a duplicate can never bypass a policy rule. No fallback from `SystemLimits.max_tool_calls` is introduced.
  3. **What counts against the budget, and what can serve a duplicate.** Every invocation that reached a tool counts against its plan attempt's budget, including one that ended in a failure
     (timeout, unavailable, error). Only an invocation whose result was stored can serve a later duplicate: ruling 5 serves "from the stored artifact" and a failure stores none, so a retry of a
     failed call is a fresh invocation and consumes budget. The history is an explicit input (`ToolInvocationRecord`); how Step 4's ledger builds it is Step 4's.
  4. **`read_only` on a descriptor. Ruled (owner, 2026-09-25).** It is EIDOS's own boolean declaration on the allowlist entry. Constructing or representing a descriptor whose entry says
     `read_only=False` is valid: neither the descriptor nor the registry rejects it. V1.2 admission denies such a tool deterministically with `NOT_READ_ONLY`. (The other reading, refusing construction, is
     not taken.)
  5. **Scope of the argument schema.** Flat, named arguments, each a string or an integer with mandatory `minimum`/`maximum` (a string's length in characters, an integer's value), required or
     optional, with no defaults. No enumerations, patterns, nested, array, boolean or floating-point arguments; an unknown argument is a violation and a `bool` is not an integer. Anything richer is
     a later, separate decision.
  6. **The concrete `search_documents` entry is not in `src`. Ruled (owner, 2026-09-25).** No production configuration value is invented beyond the approved V1.2 design, and the scope stays the single
     approved local read-only `search_documents` tool. The entry exists only in `tests/support/eidos_tool_factories.py` (`query`: string, 1 to 256 characters, required; `limit`: integer, 1 to 10,
     optional; timeout 5.0 s; `max_result_bytes` 4,096; a placeholder schema digest), as test values and **not as decisions** (the module says so). **Step 4 must establish the concrete production and
     test fixture location and explicitly document its timeout, its result-size bound and how its schema digest is treated.** `docs/08` said the schemas are "fixed at Step 2"; Step 2 fixed their
     *representation* only, because a domain tool is configuration (invariant 10).
     **Discharged in D-207 (2026-09-25):** the fixture's location (`tests/support`), its timeout (5.0 s), its result-size bound (4,096 bytes) and the treatment of its schema digest are documented in
     D-207 and `docs/08` §4c; no production value was invented.
  7. **Bounds are per entry.** A request carries its own timeout and result-size bound and has no default for either; both come from the allowlist entry through the `INVOKE` decision. Result size
     is checked after the call by `bound_result` (a `RESULT_TOO_LARGE` failure, never a truncation); enforcing the timeout belongs to the transport (Step 5). Admission itself does not deny on either
     bound.
  8. **Result shape and failure kinds.** A result is a tuple of `ToolDocument(document_id, content)` with distinct ids and no other field (no title, locator or score); its size is the UTF-8 bytes
     of the ids and contents. Failure kinds: `unavailable`, `timeout`, `tool_error`, `malformed_result`, `result_too_large`. D-203 ruling 6 needs each document to be identifiable and traceable to its
     source; if the reference server has to supply more (a source locator), Step 5 raises the additive change rather than assuming it.
  9. **Argument digest and identifiers.** `args_digest` is the SHA-256 (lowercase hex) of the arguments as compact, key-sorted, ASCII-escaped JSON, so `"1"` and `1` differ and an omitted
     optional argument differs from an explicit one (there are no defaults to normalise them). A `tool_id` is `<provider_id>/<tool_name>`, each part `[A-Za-z0-9_.-]{1,128}`; a request's and a
     record's `tool_id` stay plain non-empty strings (D-203: no `eidos.contracts` change), and an unmatched one, an empty one included, is denied `UNKNOWN_TOOL` and echoed verbatim.
  10. **Handoff §28 tool metadata not represented.** The descriptor carries a read-only declaration, an action, arguments, bounds and a schema pin. It carries no description, "allowed agents",
      risk level or cacheability (§28 says a tool should "eventually" carry them). D-203 froze a minimal policy and none of the four is read by it.
  11. **Layering for the admission seam. Ruled (owner, 2026-09-25).** The `eidos.agents` static guard (`tests/unit/agents/test_agents_guards.py`) is extended by exactly one layer, `eidos.policy`, to
      permit the intended `eidos.agents` → `eidos.policy` admission seam, and by nothing else: no transport, recorder, provider or backend is newly allowed. The extension is pinned (a test fails if the
      allowed set is anything other than the previous set plus `eidos.policy`), the seam is one-way (no `eidos.policy` module imports an agent), and the seam's own request and result types
      (`agents/tool.py`) stay free of `eidos.policy`. No dependency rule was broadly relaxed. No agent module imports `eidos.policy` yet; Step 4 will.
- **Effect:** the source Step 2 adds, including the ruling-1 change (`admit_tool_call(max_tool_calls: int | None)` and the `BUDGET_UNRESOLVED` denial) and the ruling-4 guard extension. No `eidos.contracts`,
  dependency, V1.1 or D-204-related change. The docstrings saying agents have "no tools (D-140)" are left for Step 4, when the Research agent changes (D-203). **Done in the V1.2 close-out commit (2026-09-25):** `agents/base.py`, `agents/artifacts.py` (its supplied-artifact wording) and the
  `docs/03_architecture.md` package row were corrected, wording only; Step 4 had not updated them.


### D-206 — V1.2 Step 3: readings taken for the tool-call facts and their recording seam (OPEN)

- **Status:** Open (readings taken, none blocking) · **Date:** 2026-09-25 · **Raised by:** Claude Code while implementing V1.2 Step 3 (tool-call facts and the recording seam); **not decided**
- **Source:** D-203 rulings 4 and 6; D-160 (the model-call pattern this mirrors); D-204 item 2; D-205 items 3, 8 and 9; the Step 3 brief (additive facts on `NODE_SETTLED`, a reducer-derived `tool_calls_used`, replay
  without a tool, recording, telemetry and experience additive); CLAUDE.md §7 and invariants 1, 2, 8, 15, 16
- **Why recorded:** D-203 froze *that* a tool call is an additive fact on `NODE_SETTLED` and that `tool_calls_used` folds from admitted invocations, not the exact shape of the fact. The existing contracts allowed the
  additive design without a new event type, so nothing blocked and none was added. Each reading below is the smallest implementation and can be changed without touching a V1.1 signature, `eidos.contracts` or D-204.
- **What Step 3 built:** `ToolCallFacts`, `ToolCallOutcome` and `ToolDenialReason` in `eidos.state`; `NodeSettledPayload.tool_calls` (default empty, dispatched work nodes only); the reducer's `tool_calls_used` fold;
  `StepRecord.tool_calls`; the tracker's tool collection (`ModelCallTracker.current_tool_calls`/`end_tool_calls`) and the recorder's `note_tool_calls`/`tool_calls` hand-off, passed through `RecordingAgent` and
  `_record_settled_nodes`. No tool is invoked, no MCP, no `TOOL` step, no capability, no fourth agent, no `eidos.contracts` change; `run_with_replanning`, `record_attempt`, `record_baseline` and tracker
  propagation are untouched (D-204 stays Open and deferred), and `TelemetryRecord` and `ExecutionExperience` are unchanged (they already carry `tool_calls_used`).
- **Readings:**
  1. **Fact shape.** `ToolCallFacts(tool_id, outcome, denial, args_digest, result_refs, result_bytes, elapsed_ms)`. The names are mine. `elapsed_ms` is whole milliseconds observed by the recorder's monotonic clock,
     as `NodeSettledPayload.duration_ms` is, not seconds reported by a provider as `ModelCallFacts.elapsed_seconds` is; a `ToolResult` carries no elapsed time to report. `tool_id` is the id the caller named,
     verbatim and unconstrained, so a call that named nothing valid is still recordable.
  2. **Outcome vocabulary.** Eight outcomes: `result`; the five invocation failures mirroring `ToolFailureKind`; `served_stored` (a duplicate answered from a stored result); `denied`, with a `denial` reason mirroring
     the seven `ToolDenialCode` values. `eidos.state` cannot import an agent or the policy layer, so both are mirrored by value and guard tests keep them in step (as `ModelCallOutcome` is, D-153 item 5): a new
     failure kind or denial code needs the state enum extended.
  3. **Denials and served duplicates are recorded as facts.** They cost nothing (below) but stay visible and typed. A denial carries no digest, because admission produces none for a refusal. A served duplicate
     carries the digest and the stored references of the call it repeats and no elapsed time, since nothing was invoked.
  4. **What `tool_calls_used` counts.** Every fact that reached a tool: `result` and the five failures. A served duplicate and a denial count for nothing. This follows the reading of D-205 item 3 (a failed invocation
     counts against the budget), which is still Open; if that is ruled otherwise, the fold changes in the one property that defines an invocation. It stays the whole-mission running total (D-204 item 2); the
     per-attempt count is read from the scoped steps' facts.
  5. **References, sizes and messages.** `result_refs` are the artifacts the answer became, one per document in the answer's order (D-203 reading); an empty tuple with a `result` is a real "nothing matched".
     `result_bytes` is carried only by a `result` or a `served_stored`; a failed invocation has no answer to reference or measure, and a `ToolFailure`'s message text is not recorded (the typed kind only), as a
     model failure's is not. Whether `result_refs` and `result_bytes` are always supplied for a `result` (rather than left `None`, meaning unmeasured) is left to Step 4.
  6. **Where the facts are collected.** The existing `ModelCallTracker` gained a parallel tool collection (its name is unchanged; renaming it is deferred) and the recorder gained `note_tool_calls`. A node's facts are
     handed over only when it made some, so a run without tools makes exactly the recorder calls it always made and no existing recorder signature changed.
  7. **Written form.** A newly written `NODE_SETTLED` always contains `"tool_calls": []`, so the serialised form of a new log differs from a pre-Step-3 log by that key; a pre-Step-3 log reads back unchanged.
  8. **Telemetry and experience.** No field was added to either. They carry the counter through `tool_calls_used`. Per-outcome aggregates (denials, served duplicates, elapsed time) are not added; they can be derived from
     `StepRecord.tool_calls` if a later step wants them.
  9. **Producing the facts is Step 4's.** Step 3 defines no mapping from an admission decision and a `ToolPort` outcome to a fact, so what measures `elapsed_ms` and `result_bytes`, and how a served duplicate's stored
     references are obtained, are Step 4's to establish (with the `RecordingToolPort`, D-203).
     **Discharged by D-207 reading 6 (2026-09-25):** the mapping is `tool_facts_of` and the `RecordingToolAccess` wrapper (over the gate, not a port, so a denial and a served duplicate are recorded too);
     `elapsed_ms` is the injected monotonic clock's reading across the gate call, for an invocation only; `result_bytes` is `ToolResult.size_bytes`; and a served duplicate's references are rebuilt from the
     stored artifacts. Readings 1 to 8 are unchanged and stay Open.
- **Effect:** additive only. No `eidos.contracts`, dependency, V1.1 or D-204-related change; old logs replay unchanged.


### D-207 — V1.2 Steps 4 and 5: the tool integration and the real MCP client; readings taken (OPEN)

- **Status:** Open (readings taken, none blocking) · **Date:** 2026-09-25 · **Raised by:** Claude Code while implementing V1.2 Steps 4 and 5 as one milestone (Phase A, a scripted `ToolPort`; then Phase B, the real
  MCP stdio client); **not decided**
- **Source:** D-203 rulings 2, 3, 5, 6, 7 and 8; D-204; D-205 (ruling 3 in particular); D-206; the published MCP specification, verified 2026-09-25 (below); CLAUDE.md §3, §7 and invariants 3, 9, 12, 14, 15, 16
- **Why recorded:** D-203 froze the design, not every detail of how the pieces meet. Nothing required a new architectural decision, so none was made; each reading below is the smallest implementation and can be
  changed without touching `eidos.contracts`, `eidos.state`, `eidos.policy`, a V1.1 signature or D-204.
- **What was built.** *Phase A:* in `eidos.agents`, `ToolAccess` (what an agent calls), `ToolGate` (admission first, the invocation ledger, duplicates served from stored artifacts, the port, normalisation and
  storage of results as one artifact per document), `ToolGateOutcome`, `ToolGateKind`, `tool_document_ref`/`parse_tool_document_ref`, and optional tool access for `ResearchAgent` (`tools`, `search_tool_id`); in
  `eidos.recording`, `tool_facts_of` and `RecordingToolAccess`. *Phase B:* `eidos.mcp` (`protocol.py`, `stdio.py`): `StdioMcpToolPort`, `McpServerLaunch`, `PROTOCOL_VERSION`, `schema_digest`,
  `normalise_call_result`. *Test support (the fixture):* `search_documents_corpus.py`, `mcp_search_documents_server.py`, `eidos_search_fixture.py`, `eidos_mcp_fixture.py`. Unchanged: `eidos.contracts`,
  `eidos.state`, `eidos.policy`, `pyproject.toml`, `run_with_replanning`, `record_attempt`, `record_baseline` and tracker propagation.
- **The flow, exactly.** `ResearchAgent.run` → `ToolAccess.call(context, tool_id, {"query": goal})` (in a recorded run, `RecordingToolAccess` → `ToolGate`) → `admit_tool_call` under the gate's lock, with the
  context's `allowed_actions`, autonomy level, `max_tool_calls`, execution and plan ids and the ledger → *denied:* returned typed, the port is never reached · *served:* rebuilt from the stored artifacts, nothing
  invoked and no budget used · *invoke:* the budget is reserved in the ledger, a `ToolRequest` carrying only the allowlist entry's timeout and size bound is built → `ToolPort.call` (`StdioMcpToolPort`, or the scripted
  port) → `ToolResult`/`ToolFailure` → size bound → each document stored as an artifact (`put_supplied`) → ledger marked stored → the outcome returns → the recording wrapper adds one `ToolCallFacts` for the call
  → Research reads the documents in the store, asks the model, records its artifact → verification (unchanged) → `NODE_SETTLED` carries the facts → the reducer folds `tool_calls_used`.
- **MCP revision and behaviour, verified against the published specification on 2026-09-25.** The versioning page marks **`2026-07-28`** the current revision; revisions up to `2025-11-25` use an `initialize`
  handshake. `2026-07-28` is stateless: every request carries `_meta` with `io.modelcontextprotocol/protocolVersion` and `io.modelcontextprotocol/clientCapabilities` (both required) and
  `io.modelcontextprotocol/clientInfo` (recommended); `server/discover` is mandatory for a server; results carry `resultType` (`complete`; an absent one is read as complete; an unrecognised one is invalid); stdio
  framing is one UTF-8 JSON-RPC message per line with no embedded newline and nothing but messages on stdout; a client abandons a request with `notifications/cancelled` `{requestId, reason}`; it shuts a server down
  by closing its input, waiting, then terminating; it restarts a server that exits unexpectedly; tools are `tools/list` (paged by `cursor`/`nextCursor`) and `tools/call` (`name`, `arguments`), with results in
  `content`/`structuredContent`/`isError`; protocol errors are JSON-RPC errors and tool execution errors are `isError`; tool annotations are untrusted. **Implemented: exactly this revision, over stdio, to a local
  trusted server.** Not implemented, by ruling: any earlier revision (a server of another revision is refused with a typed failure), HTTP, multi round-trip requests (`input_required` is treated as invalid),
  subscriptions, extensions, resources, prompts, sampling, elicitation, progress and caching. The specification pages consulted are listed in `docs/08_mcp_contract.md` §4d (added at the V1.2
  close-out, 2026-09-25).
- **The `search_documents` fixture (D-205 ruling 3, discharged).** *Location:* `tests/support/eidos_search_fixture.py` (allowlist entry, mission builder, scripted port), `search_documents_corpus.py` (corpus, keyword
  search, declared input schema), `mcp_search_documents_server.py` (the reference server) and `eidos_mcp_fixture.py` (its launch). *Tool id* `docs/search_documents`, capability `research`, action `read_documents`,
  `read_only` true by EIDOS's own declaration; arguments `query` (string, 1 to 256 characters, required) and `limit` (integer, 1 to 10, optional), no defaults. ***Timeout 5.0 seconds; result-size bound 4,096 bytes***
  (the UTF-8 size of the documents' ids and texts); ***schema digest*** `298b120661e86f97c4cb09438c7d5dd7f441314386b76d4b679cae6ccc9a8f9f`, the SHA-256 of the canonical JSON (sorted keys, no whitespace, ASCII-escaped)
  of the `inputSchema` the reference server declares, pinned on the entry, checked when the server is contacted and never read by admission; a test keeps the literal equal to the digest of the schema. The client's
  line cap is 65,536 bytes and the server's own default `limit` is 3, over a six-document corpus. These are test-fixture values, not production configuration.
- **Readings:**
  1. **Retrieved documents count as sources through the store's existing `put_supplied`.** D-203 ruling 6 says tool documents may satisfy `min_independent_evidence` and the verification rules do not change; the
     verifier counts distinct *supplied* documents, so a retrieved document is stored as a supplied one, under a reference that carries its provenance. No store or verifier change was needed. The consequence: a
     retrieved document appears among the supplied documents that every agent reads and that a later plan attempt of the same execution reads. The alternative, a separate retrieved-artifact notion that the verifier
     also counts, would change the verifier and the store's contract and was not taken.
     **Known V1.2 limitation (recorded at the V1.2 close-out, 2026-09-25; recorded, not resolved).** The verifier's independent source is a distinct reference: it counts the distinct supplied references
     an artifact cites, and a retrieved document's reference embeds the request digest. The same underlying document retrieved by two different queries would therefore be stored under two references and
     counted as two sources (shown by an audit probe over the real gate, store and verifier). This is **not reachable in the current V1.2 execution path**: Research makes one query per run (the mission
     goal, verbatim), so every plan attempt of an execution has the same digest and the same references, and the store is per execution. The same definition also means that a document a caller supplied
     and an identical document a tool retrieves count as two, as two identical caller-supplied documents already would. Nothing in `put_supplied`, the store or the verifier was changed. **What
     "independent" means for retrieved documents must be revisited, by the owner, before any multi-query retrieval or RAG is introduced** (or anything else that lets one execution issue more than one
     distinct query); how is not decided here.
     **Revisited by D-209 (2026-09-25):** the owner has ruled the independence semantics for V1.3 knowledge evidence. V1.2 behaviour is unchanged, and how existing V1.2 supplied and tool documents are keyed
     under a resolver is D-210 (ruled 2026-09-25, built at V1.3 Step 3, readings D-224).
  2. **The gate lives in `eidos.agents` and the Research agent holds a `ToolAccess`, not a `ToolPort`.** Admission sits between the agent and the port, inside the gate, which is the seam D-205 ruling 4 opened
     (`eidos.agents` → `eidos.policy`). The agent cannot tell a scripted port from a real one, and names no transport.
  3. **The ledger is in memory inside the gate, and the budget is reserved under its lock before the port is called**, so a call still in flight already counts and two nodes on worker threads cannot both spend the
     last unit. It is not persisted. One gate is shared by all the plan attempts of a mission, which is what makes duplicate detection execution-wide.
  4. **References and identifiers.** A document is stored as `tool:<tool_id>:<args_digest>:<document_id>`; its id must be a plain identifier (`[A-Za-z0-9_.-]{1,128}`) or the whole result is a typed
     `MALFORMED_RESULT`, so a reference can always be cited as `[[ref]]`. A reference already taken in the execution is also `MALFORMED_RESULT`, and nothing is written. Both count as invocations.
  5. **A port is total, and one that is not is contained.** A port that raises is a `TOOL_ERROR` failure and one that returns neither a result nor a failure is a `MALFORMED_RESULT`; both are charged (D-205 item 3).
  6. **Recording wraps the gate, not a `ToolPort`.** D-203 named a `RecordingToolPort`; a denial and a served duplicate never reach a port, so the recording wrapper is `RecordingToolAccess`, over `ToolAccess`. It
     takes the same tracker and clock as `record_baseline`. `elapsed_ms` is the injected monotonic clock's reading across the gate call, for an invocation only (it includes admission and storage, which are
     negligible beside an invocation); `result_bytes` is `ToolResult.size_bytes`. D-206 item 9 is discharged this way. Through `run_with_replanning` no tool-call fact is captured, exactly as no model-call fact is (D-204).
  7. **Research uses the tool whenever it is configured, once per run**, not only when nothing is supplied, so a later plan attempt asks again and is served the stored documents. The query is the mission goal,
     stripped, verbatim: no limit is invented, so a goal the allowlist entry will not accept as a query is a typed `INVALID_ARGUMENTS` denial, not a truncation. A denial, a failure or an empty result never stops a run
     that has documents (supplied, or retrieved earlier); with none, a denial, `MALFORMED_RESULT`, `RESULT_TOO_LARGE` and an empty result are `NO_RESULT`, and `UNAVAILABLE`, `TIMEOUT` and `TOOL_ERROR` are `FAILED`,
     mirroring how a model failure is read.
  8. **The client's process discipline.** One local server process, started on first use with exactly the environment the launch names (nothing inherited) and no shell, its standard error discarded; kept between
     calls (the protocol is stateless); started again if it has exited; killed on a timeout, a malformed message or a message over the cap. The call's timeout covers launch and discovery too, and on expiry the
     required cancellation notification is sent before the process is ended. A server refused at the start of a session (another revision, no tools capability, a missing pinned tool, a changed schema) is refused for
     the life of the port, and a new port is needed to retry. One call is in flight at a time. `max_message_bytes` is required, with no default. The bound on `tools/list` pages (5) and the shutdown grace (1 s) are
     technical bounds inside `eidos.mcp`, not policy.
  9. **The result convention for `search_documents` over MCP is this milestone's own.** MCP does not define a document search result, so the client requires `structuredContent.documents`, a list of `{id, text}`
     objects with distinct non-empty ids; unstructured content is never parsed for documents; `isError` is a `TOOL_ERROR`; a JSON-RPC error on a call is a `TOOL_ERROR`; anything else is `MALFORMED_RESULT`.
  10. **The schema pin.** The digest is defined in `eidos.mcp` (the schema is the MCP side's artefact): SHA-256 of the canonical JSON of the declared `inputSchema`. A missing pinned tool or a different digest is an
      `UNAVAILABLE` refusal.
  11. **`eidos.mcp` imports `eidos.agents`** for the port vocabulary only (a guard enforces the exact names), and importing the agents package brings the gate and the policy layer with it; the guards check the MCP
      package's own source, which names neither.
- **Still Open, unaffected:** D-205 items 3, 5, 7, 8, 9 and 10; D-206's readings 1 to 8 (its reading 9 is discharged by reading 6 above); D-043, D-046, D-015, D-059, D-060, D-061, D-074, D-017 and D-129. **Deferred, unaffected:** D-127. **Accepted,
  unaffected:** D-009, D-110 and D-156; an earlier version of this list called them Open, corrected at the V1.2 close-out (2026-09-25). What stays Open behind each is named above: the numeric values
  and cumulative enforcement behind D-009 (D-046, D-043), the autonomy semantics behind D-110 (D-060, D-061, D-074) and the three questions D-156 itself leaves Open (D-043, D-059, D-015). **D-204 stays Open and deferred:** V1.2 modified none of
  `run_with_replanning`, `record_attempt`, tracker propagation or any V1.1 signature.
- **Effect:** additive only. No `eidos.contracts`, `eidos.state`, `eidos.policy`, dependency or V1.1 change; `pyproject.toml` is unchanged and declares no MCP package.


### D-208 — V1.3 RAG / Knowledge Intelligence: scope, and a measured lexical-versus-semantic retrieval comparison (2026-09-25)

- **Status:** Accepted · **Date:** 2026-09-25 · **Decided by:** human owner — the V1.3 rulings D-208 to D-220, given after two read-only readiness reports (2026-09-25); D-210 was not ruled at that point and was ruled later the same day (see it)
- **Source:** the owner's V1.3 rulings and the accepted readiness report; handoff §24 to §26, §30, §31, §33, §50, §74; `docs/09`; D-184, D-203, D-207 reading 1; invariants 7 and 12 to 16
- **Why:** since V1.2 the Research agent can retrieve documents through a tool, but a retrieved document enters the supplied-artifact set and the verifier's "distinct sources" is a count of distinct reference strings,
  which embed the request digest (D-207 reading 1: a known V1.2 limitation, not reachable in the current one-query path). V1.3 introduces a controlled knowledge and evidence layer: how EIDOS ingests, indexes,
  retrieves, identifies, constrains and verifies external knowledge so that retrieved evidence can take part in execution without weakening provenance, determinism, verification or replay.
- **Decision:**
  1. V1.3 is the **knowledge/evidence layer only**: document ingestion, document and chunk identity, indexing, retrieval, source and provenance tracking, retrieval-query identity, evidence references,
     duplicate-source handling, bounded retrieval, evidence traceability into verification, and replay without querying the knowledge store. The initial system supports **local documents**.
  2. V1.3 uses **a measured lexical-versus-semantic retrieval comparison behind one `KnowledgePort`.** The retrieval implementation is **not chosen in advance.** The two candidates are (1) lexical retrieval and
     (2) Sentence Transformer semantic retrieval, run on the same fixture (D-213); the choice follows the measured results and is the owner's (implementation order, step 11).
  3. **Qdrant is not part of the first slice.** It may be introduced later only if measured scale, filtering, persistence, concurrency or latency requirements justify it (D-220).
  4. **Cross-encoder reranking is excluded** from the initial V1.3 implementation. It is a possible future stage only if a later measured result justifies it.
  5. **The V1.2 contracts are frozen and consumed, not redesigned:** MissionState authority and the reducer architecture; the event and replay model; the validated Plan DSL; strategy selection; replanning;
     `ToolPort`, `ToolGate` and tool admission; the MCP transport boundary and protocol; the Research agent's `ToolPort` abstraction; the existing tool-call facts; the existing verification architecture, unless a
     concrete V1.3 requirement proves an additive change necessary (D-209 is that requirement); `run_with_replanning`, `record_attempt` and tracker propagation; D-204; and the V1.2 tool budget semantics.
  6. **Excluded from the initial scope:** web crawling, autonomous web search and autonomous knowledge acquisition; multiple knowledge agents; LLM query planning and autonomous query decomposition; DSPy; Laya;
     cross-encoder reranking; production Qdrant; RAG chains and LangChain RAG; a new `PlanStepKind`, agent or event type; a frontend, FastAPI, Supabase, authentication and deployment. **Research agent
     integration does not begin until the retrieval comparison has been reviewed.**
  7. The **implementation order and the testing requirements** are the owner's and are recorded in `progress.md` ("V1.3 RAG / Knowledge Intelligence"). The first step is documentation and governance only.
- **Relation to the handoff (reported, not a conflict; the handoff is not modified):** §25 and §26 name Qdrant as the planned local vector database and the default, and §50's V0.8 list names Qdrant, local
  embeddings, retrieval, reranking and an evidence judge. V1.3 as ruled is a staged subset of that list: Qdrant is deferred to a later adapter behind the same port (D-024 stays Open), reranking and the evidence
  judge are deferred, and the agentic reformulation loop of §24 is not built. This is a scoping and sequencing ruling of the same kind as D-184 and D-203.
- **Milestone label (raised, D-222 point 1):** the owner named this milestone V1.3. The `progress.md` ladder, the handoff's milestone list and several decisions and documents use the label V1.3 for Frontend and
  V1.4 for Deployment. Nothing was renumbered; the older references keep meaning the handoff's Frontend milestone until the owner rules.
- **Effect:** documentation only at this step: no source, test, dependency or contract change.
- **Annotated 2026-09-25 (D-222 rulings):** Qdrant is not added to V1.3 core and remains the later MVP storage implementation behind `KnowledgePort`. This states the intended later adapter of item 3 and does not
  change it: nothing in V1.3 core uses Qdrant.

### D-209 — V1.3 evidence independence: the ruled counting rule (2026-09-25; clarified by D-221)

- **Status:** Accepted · **Date:** 2026-09-25 · **Decided by:** human owner (the ruling is recorded as given; D-221 confirmed and clarified it on 2026-09-25)
- **Source:** the owner's V1.3 rulings; the readiness report §6 (rules S1 to S5); D-145, D-146, D-207 reading 1; invariants 12, 13 and 16
- **Decision (the owner's ruling, "Rule: S4"):** independent-source counting uses **declared source identity**, **content-derived document identity** and **explicit `derived_from` relationships when declared.**
  Consequences, as ruled:
  - repeated retrieval of the same chunk = one source;
  - multiple chunks from one document = one source;
  - multiple documents under one declared source = one source;
  - identical content under different declared sources = separate sources;
  - known derived content can collapse through `derived_from`;
  - undeclared derivation cannot be inferred automatically.
  **No broad semantic plagiarism or derivation detection is attempted.** The resolver must be **deterministic and pure.**
- **What changes:** this rule changes the interpretation of the existing "distinct sources" semantics (D-145, D-146: the verifier counts distinct supplied references) and is recorded as an explicit **additive V1.3
  decision.** As ruled for Step 3, an absent resolver leaves the verifier's behaviour byte-identical. The V1.2 limitation of D-207 reading 1 is revisited by this ruling; nothing in V1.2 behaviour changes until Step 3,
  and how existing V1.2 supplied and tool documents are keyed once a resolver is present was not ruled then (D-210, ruled later on 2026-09-25 and built at Step 3, readings D-224).
- **Confirmation (D-221, ruled 2026-09-25):** the ruling's name and its enumerated consequences read differently against the readiness report's rules; the owner clarified them in D-221.
- **Clarified by D-221:** the enumerated consequences govern. Different declared sources stay distinct even for identical content; `derived_from` applies to documents, not sources, is explicit only and is non-transitive. The name "S4" is the owner's label; the readiness report's S4 (a mirror counts once) and S5 (a transitive source-level relation) are not adopted as defined.
- **Effect:** documentation only at this step.

### D-210 — V1.3: how existing V1.2 supplied and tool documents are keyed for independence (RULED 2026-09-25)

- **Status:** Accepted · **Date:** 2026-09-25 · **Raised by:** Claude Code while recording D-208 to D-220 (the rulings of that day gave none for D-210, which the readiness report listed as needed before Step 3) · **Decided by:** human owner, 2026-09-25 (it was Open when raised)
- **Source:** the readiness report §17; D-207 reading 1; D-209
- **Question:** once the verifier is given a resolver (Step 3), which independence key does a document that is not knowledge evidence have: a caller-supplied artifact, and a V1.2 tool document stored as
  `tool:<tool_id>:<args_digest>:<document_id>`? The readiness report listed (a) the SHA-256 of the artifact's text (provider-independent; identical caller and tool text would count once); (b) `(tool_id, provider
  document_id)` for a tool document and the reference itself for a caller document (provider-asserted identity); (c) unchanged, the reference string.
- **Not affected:** with no resolver the verifier is byte-identical (the owner's Step 3 requirement), so V1.2 behaviour is unchanged whatever is ruled.
- **Blocked (until the ruling below):** V1.3 Step 3 (the EvidenceLedger and its resolver). Nothing was implemented.
- **Ruling (owner, 2026-09-25):** existing V1.2 supplied and tool documents **must receive a deterministic knowledge identity from their existing artifact/reference identity plus normalised content.** V1.2
  behaviour is not changed and historical ids are not rewritten retroactively. The resolver **maps old evidence into the new knowledge identity without modifying historical records.**
- **What the ruling settles:** the readiness report's options (a), (b) and (c) above are not adopted as written. The identity is derived from what the artifact already is (its reference identity) together with its
  normalised content, and nothing already recorded is touched: a V1.2 artifact reference, a `tool_calls` fact, an artifact and the verifier's behaviour all stay exactly as they were.
- **Not settled by the ruling (D-224, the Step 3 readings, Open):** what the "existing artifact/reference identity" of a tool document is when its reference embeds the request digest
  (`tool:<tool_id>:<args_digest>:<document_id>`); how a source id is derived from it; and where the derived identity is held.

### D-211 — V1.3 source identity: `source_id` is mandatory (2026-09-25)

- **Status:** Accepted · **Date:** 2026-09-25 · **Decided by:** human owner
- **Source:** the owner's V1.3 rulings; D-209, D-212
- **Decision:** `source_id` is **mandatory** in V1.3 knowledge manifests. **No default source id is invented.** Every ingested document must belong to an explicitly declared source.
- **Consequences:** a manifest entry that names no source is refused at ingestion, never given a default; independence (D-209) therefore always rests on a declared identity. The manifest schema and the typed
  refusal are Step 2 work; the manifest's `derived_from` representation is part of D-221.

### D-212 — V1.3 identity model (2026-09-25)

- **Status:** Accepted · **Date:** 2026-09-25 · **Decided by:** human owner
- **Source:** the owner's V1.3 rulings; the readiness report §5 (this corrects its first version)
- **Decision:** the corrected model.
  - `source_id`: declared manifest identity;
  - `document_id`: SHA-256 of the normalised document text;
  - `chunk_id`: SHA-256 of a version tag, `source_id`, `document_id`, `chunking_scheme_id`, the chunk boundaries and the chunk-text digest;
  - `query_id`: SHA-256 of the canonical retrieval request;
  - `evidence_ref`: deterministic from `chunk_id`;
  - `snapshot_id`: deterministic from the sorted source/document manifest and the scheme identifiers.
  **No id may depend on query order, the plan, the execution, a random UUID or the wall clock.**
- **The correction:** the first readiness report's `chunk_id` omitted `source_id`, so a byte-identical mirror declared under a second source would have produced the same chunk ids as the original. With
  `source_id` in the chunk id, identical content under two sources has one `document_id` and two `chunk_id`s.
- **Details from the accepted readiness report (§5), not restated by the ruling:** normalisation is strict UTF-8 decoding, Unicode NFC, and CRLF and CR to LF, nothing else (the repository's own working copies
  mix CRLF and LF under `autocrlf`, so hashing raw bytes would give one document several ids); `evidence_ref` is `evidence:` followed by the first 16 hexadecimal digits of `chunk_id`, and ingestion refuses a
  prefix collision inside a snapshot (the canonical identity stays the full digest); identifiers are plain constrained strings, not new `eidos.contracts` types.
- **Effect:** documentation only at this step; the derivations are implemented and tested at Step 2.

### D-213 — V1.3 benchmark fixture (2026-09-25)

- **Status:** Accepted · **Date:** 2026-09-25 · **Decided by:** human owner
- **Source:** the owner's V1.3 rulings; the readiness report §14 and §15
- **Decision:** the proposed fictional-facility benchmark structure is approved: approximately 12 documents; approximately 6 sources; approximately 48 to 60 chunks; approximately 36 queries, of which approximately
  6 are dev queries and approximately 30 are frozen test queries; lexical-overlap cases; paraphrase cases; multi-source cases; distractor-bait cases; a byte-identical mirror under another source; and an
  undeclared paraphrased copy. **The cross-lingual stratum is not added to the first benchmark:** English only is sufficient for the initial V1.3 measurement.
- **Freeze rule:** the fixture and its gold labels are frozen before any retrieval result is observed, and nothing is tuned against the test set.
- **Metrics (the owner's Step 5 list):** Recall@1, Recall@3, Recall@5, MRR and source-coverage@k, plus latency, memory and reproducibility; the dependency cost of each method is recorded too. No measurement is
  fabricated, and no method is called better before actual fixture results exist.
- **Not restated by the ruling (D-222 point 7):** the gold-label rule for the mirror pair, whether decision margins are pre-registered, and the review protocol for the paraphrase queries.
- **Effect:** the fixture is authored at Step 5, not now.

### D-214 — V1.3 semantic environment: an isolated benchmark process on Python 3.13 (2026-09-25)

- **Status:** Accepted · **Date:** 2026-09-25 · **Decided by:** human owner
- **Source:** the owner's V1.3 rulings; the second readiness report (environment verified read-only, 2026-09-25)
- **Decision:** EIDOS's main Python version stays **3.12.** For the first Sentence Transformer benchmark: the existing **Python 3.13 environment** is used; semantic retrieval runs as an **isolated benchmark process**;
  `torch`, `sentence-transformers` and `transformers` are **not** added to EIDOS's `pyproject.toml`; no other model is installed or downloaded. The model is the locally cached
  `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, and **its exact cached revision and weight digest are pinned.** The semantic benchmark **fails loudly** if that isolated environment or model is
  unavailable. **This is a benchmark environment decision, not permission to make semantic retrieval a runtime dependency yet.**
- **Verified context (read-only; nothing installed or downloaded):** the model is in the default Hugging Face cache and loads offline from its local snapshot (384 dimensions, `max_seq_length` 128, 117,653,760
  parameters, licence apache-2.0). Two revisions are cached, `e8f8c211226b894fcb81acc59f3b34ba3efd5f42` (the one `refs/main` names) and `86741b4e3f5cb7765a600d3a3d55a0f6a6cb443d`, with byte-identical weights
  (SHA-256 `eaa086f0ffee582aeb45b36e34cdd1fe2d6de2bef61f8a559a1bbc9bd955917b`) and tokenizer, differing only in `tokenizer_config.json`. The semantic stack (torch 2.9.0+cpu, sentence-transformers 5.1.1,
  transformers 4.57.1) exists only in Python 3.13.1; EIDOS's Python 3.12 has none of it. EIDOS's core packages import under 3.13 with `PYTHONPATH=src` alone (the test suite has not been run there).
- **Which revision is pinned is not stated by the ruling (D-222 point 2).**
- **The cross-encoder** `cross-encoder/ms-marco-MiniLM-L-6-v2` is also cached and loads offline; it is not used (D-208).

### D-215 — V1.3 chunking: the semantic model's 128-token window (2026-09-25)

- **Status:** Accepted · **Date:** 2026-09-25 · **Decided by:** human owner
- **Source:** the owner's V1.3 rulings; the second readiness report (a probe showed text past the window changes nothing in the embedding)
- **Decision:** chunk size must stay within the semantic model's **128-token window.** The target is approximately 85 English words or fewer, but **the authoritative check is the tokenizer's word-piece count.**
  The fixture and harness **mechanically verify the bound.** **No silent truncation.**
- **Consequences:** the semantic side refuses a chunk over the bound instead of truncating it (the exact typed failure is a Step 8 detail). The tokenizer exists only in the Python 3.13 benchmark environment, so the
  authoritative check runs there; the default suite can check only a non-authoritative proxy (D-222 point 3).

### D-216 — V1.3 retrieval bounds: per-knowledge-base configuration (2026-09-25)

- **Status:** Accepted · **Date:** 2026-09-25 · **Decided by:** human owner
- **Source:** the owner's V1.3 rulings; D-029, D-009, D-043; invariant 7
- **Decision:** per-knowledge-base configuration for the first V1.3 implementation. **No new global system-level retrieval budget yet.** Retrieval is bounded by `top_k`, a configured maximum result count and a
  configured maximum returned size (bytes or tokens, as appropriate). **Retrieval is never unbounded.**
- **Consequences:** this answers D-029 for the V1.3 initial implementation only; D-029 stays Open for any agentic loop and `max_rag_rounds`. The remaining details are D-222 point 5.

### D-217 — V1.3 query generation: the mission goal, one deterministic query (2026-09-25)

- **Status:** Accepted · **Date:** 2026-09-25 · **Decided by:** human owner
- **Source:** the owner's V1.3 rulings; D-099, D-207 reading 7
- **Decision:** the Research agent uses the human mission objective (goal) to form the retrieval query. **No LLM query planning. No autonomous multi-query decomposition. No new `information_dependencies`
  mechanism yet.** One deterministic query per initial acceptance path. Multi-query behaviour may be tested at the evidence layer, to prove the duplicate-source semantics, but it is not part of the initial agent
  planning architecture.
- **Consequences:** Research integration is not part of the steps before the retrieval comparison has been reviewed (D-208); how exactly the query is formed from the goal is D-222 point 6.

### D-218 — V1.3 recording: additive fields on the existing `NODE_SETTLED` facts (2026-09-25)

- **Status:** Accepted · **Date:** 2026-09-25 · **Decided by:** human owner
- **Source:** the owner's V1.3 rulings; D-076, D-153, D-206; invariants 8, 15 and 16
- **Decision:** additive fields on the existing `NODE_SETTLED` facts. Record `scheme_id`, `snapshot_id`, `query_id`, the outcome, the ordered hits (each with `chunk_id`, `document_id`, `source_id`, rank and content
  digest, and an optional score with its kind), the retrieval sizes and the elapsed time. Also record the **citation edges** as an additive tuple field. **No new RAG event yet.** The existing replay
  architecture remains authoritative.
- **Consequences:** `RAG_SEARCH` and `EVIDENCE_REJECTED` stay unused vocabulary, as `MCP_TOOL_CALLED` did in V1.2. Old logs replay unchanged and a newly written `NODE_SETTLED` gains the new empty fields, as
  D-206 reading 7 did for `tool_calls`. As with tool facts, retrieval facts are captured through `record_baseline` only: D-204 is unchanged. Replay must not require Sentence Transformers, Qdrant, BM25 or the
  knowledge store; the derived `evidence_audit` projection is Step 4.

### D-219 — V1.3 package: `eidos.knowledge` (2026-09-25)

- **Status:** Accepted · **Date:** 2026-09-25 · **Decided by:** human owner
- **Source:** the owner's V1.3 rulings; CLAUDE.md §3 and §8; D-175's and D-190's precedent for adapter packages
- **Decision:** the package is **`eidos.knowledge`**, not `eidos.rag`. Knowledge and retrieval contracts live in it. It must remain independent of Qdrant, Sentence Transformers, BM25 and any specific embedding model.
- **Contract set (the accepted readiness report, §18):** of the 20 contracts first proposed, the boundary contracts are `KnowledgeChunk`, `KnowledgeSnapshot`, `RetrievalRequest`, `RetrievedChunk`,
  `RetrievalResult`, `RetrievalFailure`, `KnowledgePort`, `EvidenceRecord`, the recorded `RetrievalFacts` (with a hit fact) and `SourceKeyResolver`. The identifiers are plain constrained strings, so
  `eidos.contracts` is not changed. `KnowledgeSource`, `RetrievalQuery` and `EvidenceReference` are deleted, and `KnowledgeDocument` is an ingestion-local input. A small knowledge-base descriptor, an admission
  result and denial, and an `Embedder` protocol (semantic side only) were found necessary.
- **Effect:** the package is created at Step 2, not now (CLAUDE.md §3). Where the retrieval implementations live, and the import-guard ruling the verifier and ledger will need, are D-222 point 4.

### D-220 — V1.3 vector storage: a pinned snapshot is authoritative; a derived exact index is not (2026-09-25)

- **Status:** Accepted · **Date:** 2026-09-25 · **Decided by:** human owner
- **Source:** the owner's V1.3 rulings; the second readiness report
- **Decision:** a **pinned knowledge snapshot is the authoritative knowledge state.** For semantic retrieval: snapshot, then a **derived vector index**, then **exact cosine search.** The vector index is rebuildable and
  is **not** part of replay authority. **No Qdrant. No ANN retrieval.** **No claim of cross-machine bit-identical embedding generation.**
- **Context (informal probe, 2026-09-25, eight fixed sentences on this machine, not a benchmark):** repeating an encode in one process gave identical vectors, while changing the torch thread count or the batch
  shape changed vector bits by at most about 3.1e-7 (max absolute difference) and did not change the toy ranking. This shows sensitivity to configuration; it says nothing about another machine.
- **Consequences:** deterministic parts are identifiers, normalisation, chunking, filtering, ordering and tie-breaking and the replay of recorded retrieval; embedding generation and floating-point similarity are
  potentially environment-dependent. Qdrant remains a possible later adapter behind the same port (D-208, D-024).
- **Annotated 2026-09-25 (D-222 rulings):** the owner states that Qdrant remains the later MVP storage implementation behind `KnowledgePort`, and is not added to V1.3 core.

### D-221 — V1.3: confirmation of the ruled independence rule (D-209) (RULED 2026-09-25)

- **Status:** Accepted · **Date:** 2026-09-25 · **Raised by:** Claude Code while recording D-209 · **Decided by:** human owner, 2026-09-25 (it was Open when raised)
- **Source:** D-209; the readiness report §6 (rules S1 to S5); CLAUDE.md §7
- **Why recorded:** the owner ruled "Rule: S4", but the ruling's own enumerated consequences do not match the S4 defined in the readiness report, and a gap is recorded and raised, never resolved silently. The report
  defined S3 as the distinct declared `source_id`; S4 as S3 plus collapsing documents of identical content across sources; and S5 as S4 plus declared `derived_from`. The ruling names S4 but lists as consequences
  that identical content under different declared sources counts as **separate** sources (S3's behaviour, not S4's) and that known derived content can collapse through `derived_from` (S5's relation). Read
  literally, the consequences describe **declared source identity plus declared `derived_from`, with no content-based collapse across sources**; read by its name, S4 would count a byte-identical mirror once.
- **Points to confirm:**
  1. Which is intended: the enumerated consequences (a mirror under another declared source counts as a separate source) or the name S4 (a mirror counts once)? This decides what the fixture's byte-identical
     mirror (D-213) does to the independent-source count.
  2. The role of "content-derived document identity" in counting. Under the enumerated consequences it identifies a document inside one source (so chunks of one document are one source) and would not merge
     documents across sources.
  3. `derived_from`: whether it is declared between sources or between documents; its direction; whether it is transitive; whether a cycle or an unknown target is a manifest error; and its manifest
     representation. The smallest reading, **offered and not applied,** is that declared `derived_from` edges connect sources, the connection is transitive, a cycle or an unknown target is a manifest error, and all
     sources in one connected group count once.
- **Blocked (until the ruling below):** V1.3 Step 2's independence resolver and manifest schema, and Step 3.
- **Ruling (owner, 2026-09-25):**
  1. **Different declared `source_id`s remain distinct independent sources even when their documents contain identical or byte-identical content.** Content identity never collapses them.
  2. **`derived_from` applies to documents, not sources.**
  3. **`derived_from` is an explicitly declared document-derivation relationship only.** EIDOS must not infer derivation from similarity, identical content, matching text or any other heuristic.
  4. **`derived_from` is non-transitive in V1.3:** only directly declared relationships are considered.
- **What this settles:** the enumerated consequences of D-209 govern. A byte-identical mirror under another declared source counts as a separate source unless its own entry declares `derived_from` the
  original. The readiness report's S4 (a mirror counts once) and S5 (a transitive source-level relation) are **not** adopted as defined, and the smallest reading offered above (source-level, transitive) is
  **not applied**, because the ruling excludes both properties.
- **Not settled by the ruling (D-223, the Step 2 readings, Open):** the exact function that counts independent sources under points 3 and 4; how a document is referenced as a derivation target; and what an unknown
  target, a self-derivation or a derivation cycle does.
- **D-210 stays Open.** The owner: it is a Step 3 resolver concern. No ruling was invented for it. *(Ruled by the owner later on 2026-09-25 with the Step 3 brief; see D-210.)*

### D-222 — V1.3 Step 1: points the rulings left open (PARTLY RULED 2026-09-25)

- **Status:** Partly ruled, partly Open · **Date:** 2026-09-25 · **Raised by:** Claude Code while recording D-208 to D-220 · **Decided by:** human owner, for points 2 and 3, and for point 4 (its home, then its import guard on 2026-09-25); points 5 and 6, and point 7 (a) by direction to resolve them from the accepted reports (readings in D-225); point 2 (2026-09-26: the exact recorded revision and digest) and point 7 (b) (2026-09-26: no numeric decision rule); points 1 and 7 (c), and the admission part of point 5, stay Open; point 8 is answered by readings in D-226
- **Source:** the rulings and the two readiness reports; CLAUDE.md §7
- **Points** (each is a gap or an unstated detail; none was resolved):
  1. **Milestone label.** The owner named this milestone V1.3. The `progress.md` ladder, the handoff's milestone list (§50) and D-022, D-072, `docs/02` and `docs/10` use V1.3 for Frontend and V1.4 for
     Deployment. Nothing was renumbered. Does Frontend keep the number V1.3 alongside this milestone, become unassigned (as D-184 did for MCP and RAG), or move? Blocks nothing.
  2. **Which cached revision is pinned (D-214).** Two revisions are cached with identical weights and tokenizer, differing only in `tokenizer_config.json`. The proposal, not applied, is `e8f8c211…` (what
     `refs/main` names and an unpinned load resolves) with the weights digest recorded in D-214. Blocks Step 8.
  3. **Where the word-piece bound is checked (D-215).** The tokenizer exists only in the Python 3.13 benchmark environment, so the authoritative check cannot run in the default 3.12 suite, which can check only
     a proxy (a word count). The pure chunker has no tokenizer, and its size unit (words, characters or sentences) is a Step 2 proposal. Blocks Step 5 and Step 8.
  4. **Where the retrieval implementations live, and the layering rulings (D-219).** `eidos.knowledge` must stay independent of BM25, Sentence Transformers, Qdrant and any embedding model, so
     `LexicalKnowledgePort` and `SemanticKnowledgePort` need a home outside it or a rule for what may sit inside it. The verifier and the ledger in `eidos.agents` will need to import `eidos.knowledge`, an
     extension of the agents import guard of the kind D-205 ruling 4 made for `eidos.policy`, which needs its own pinned ruling. Blocks Step 3 (the guard) and Step 6.
  5. **Retrieval bound details (D-216).** The maximum number of queries per execution or plan attempt; bytes or tokens; the denial vocabulary; whether an exhausted bound returns a typed denial, as tool admission
     does. Blocks Research integration.
  6. **The form of the query (D-217).** "Form the retrieval query from the goal": verbatim `goal.strip()`, as V1.2 does (D-207 reading 7), or transformed. Blocks Research integration.
  7. **Benchmark rules the rulings did not restate (D-213).** (a) Gold labels over content-equivalence groups, so a byte-identical mirror pair counts once in Recall (readiness report §14); (b) no numeric
     decision rule or margin is pre-registered, so the retrieval decision is the owner's at step 11 from the comparison report; (c) the review protocol for the paraphrase queries. Blocks Step 5.
  8. **The isolated benchmark process (D-214).** How semantic results leave the Python 3.13 process and how "fail loudly" is realised (a marker like `real_model`, D-136). A Step 8 proposal, not a question now.
- **Effect:** none on Step 1, which is documentation only.
- **Rulings on these points (owner, 2026-09-25) and what stays Open:**
  - **Point 1, the milestone label:** not addressed; **still Open.**
  - **Point 2, the pinned revision: ruled.** Use the verified cached model revision, and record the exact revision and digest rather than relying on a floating model name. *Reading taken, not confirmed:* "the verified
    cached revision" is the one proposed in point 2, `e8f8c211226b894fcb81acc59f3b34ba3efd5f42` (what `refs/main` names), with weights SHA-256 `eaa086f0ffee582aeb45b36e34cdd1fe2d6de2bef61f8a559a1bbc9bd955917b`; the
    other cached revision has identical weights and tokenizer and differs only in `tokenizer_config.json`. Applies at Step 8.
  - **Point 3, where the token bound is enforced: ruled.** Chunking and token-bound enforcement stay deterministic, and the enforcement sits in the semantic retrieval boundary, where the tokenizer is available.
    *Reading:* the pure chunker (Step 2) stays tokenizer-free and shared by every retriever, and the word-piece check and the refusal to truncate belong to the semantic side, in the Python 3.13 process. The chunker's
    size unit is a Step 2 reading (D-223).
  - **Point 4, where the retrieval ports live: ruled in part.** Retrieval ports stay under `eidos.knowledge`. **Still Open:** the import-guard ruling for `eidos.agents` importing `eidos.knowledge` (needed before
    Step 3), and the rule that keeps the package's core modules free of any engine or model while an adapter module may name one.
  - **Points 5, 6, 7 and 8** (retrieval bound details, the form of the query, the benchmark rules not restated, the isolated-process mechanics): not addressed; **still Open.**
- **Also stated by the owner (2026-09-25):** the main EIDOS runtime stays on Python 3.12; semantic embedding stays isolated to the already-verified Python 3.13 environment for V1.3; **Qdrant is not added to V1.3 core
  and remains the later MVP storage implementation behind `KnowledgePort`**; cross-encoder reranking is not introduced; the V1.2 contracts are not reopened.
- **Update (owner, 2026-09-25, with the Step 3 rulings): point 4's import-guard part is ruled.** **`eidos.agents` may depend on the knowledge boundary only through the defined `KnowledgePort` and the
  knowledge-facing contracts needed for retrieval. `eidos.knowledge` must never import `eidos.agents`, `eidos.policy`, MCP, LangGraph or infrastructure. The dependency direction stays one-way.** *Reading
  taken, not confirmed (D-224):* until `KnowledgePort` exists, the pinned boundary is the set of knowledge names the evidence ledger needs, imported from the package root only; a later step adds names to that
  set on purpose. Points 1, 5, 6, 7 and 8 stay Open.
- **Update (owner, 2026-09-25, with the Step 4 brief): points 5 and 6 are to be resolved before coding, from the readiness reports and the accepted decisions, with no further architecture invented; the combined benchmark listing names content-equivalence groups (point 7 a).** Resolved as readings in **D-225** (readings 1 to 4 and 10): the retrieval contract, the query form (the goal, canonicalised), `query_id`, the bounds (`top_k` and `max_result_bytes`, in bytes), and the gold labels over content-equivalence groups. **Still Open:** point 1; point 7 (b), no numeric decision rule, and (c), the owner's review of the paraphrase queries; point 8; and, for Step 7, the admission part of point 5 (queries per execution, the denial vocabulary).
- **Update (owner, 2026-09-26, with the Step 5 brief):** **point 2 is confirmed** (the exact previously verified cached revision and digest are used) and **point 7 (b) is ruled: no numeric pass/fail threshold or margin is
  imposed** before the comparison, and the owner decides at Step 6. Point 8 (the isolated benchmark process) is answered by readings 6 to 8 of **D-226**. Points 1 and 7 (c) stay Open.
- **Update (owner, 2026-09-26, with the Step 6 decision, D-227):** point 7 (c), the owner's review of the paraphrase queries, is answered: the ten test paraphrase queries were reviewed, no flaw invalidating the stratum was found, and they are accepted for this benchmark with the recorded caveats. Point 1 (the milestone label) and the admission part of point 5 stay Open.
- **Update (owner, 2026-09-26, with the D-228 rulings):** the admission part of point 5 (a ceiling on queries per execution or attempt, the denial vocabulary, a typed denial for an exhausted bound) is **deferred** and not built in V1.3 (D-228.4): it is revisited when a second distinct knowledge query can exist. The current Research path is bounded to one query per run by construction. Point 1 (the milestone label) stays Open.
- **Update (2026-09-26, D-229):** point 1 (the milestone label) is resolved: V1.3 is RAG, V1.4 is Product Backend, and the handoff's Frontend and Deployment are unassigned, not renumbered. Confirmed by the owner on 2026-09-27 (D-229 accepted).

### D-223 — V1.3 Step 2: readings taken where the rulings were silent (OPEN)

- **Status:** Open (readings taken, none blocking) · **Date:** 2026-09-25 · **Raised by:** Claude Code while implementing V1.3 Step 2 (the pure `eidos.knowledge` structures); **not decided**
- **Source:** D-208 to D-222 (D-209, D-211, D-212, D-215, D-219, D-220, D-221 and D-222 in particular); the accepted readiness reports; CLAUDE.md §7 and invariants 8, 10, 13 and 16
- **Why recorded:** the rulings fixed what independence, identity and chunking must satisfy, not every detail of how. Each reading below is the smallest implementation, lives in one function or constant, and can be
  changed without touching a V1.2 contract, `eidos.contracts` or D-204.
- **What Step 2 built:** `eidos.knowledge` — `identity.py`, `contracts.py`, `chunking.py`, `snapshot.py` and `independence.py`. Pure, standard library plus `pydantic` plus `eidos.contracts`; nothing imports it;
  `pyproject.toml` is unchanged.
- **Readings:**
  1. **The counting function (D-221 points 3 and 4).** A cited document is set aside if a document it directly declares as an origin is also cited; the independent sources are the distinct declared sources of
     the cited documents that remain. Different sources are never merged by content, and only declared, direct edges are read. *Alternatives not taken:* (a) counting a derived document as its origin's source, which
     mis-counts a chain cited through its middle; (b) the largest set of pairwise-unrelated cited documents, which is exponential in general and counts a fully cited chain A, B, C as two. The three differ only for
     chains whose middle document is cited alongside both ends. One short function (`independent_sources`).
  2. **How a derivation names its target.** A document is named by the source it is declared under and the SHA-256 of its normalised text (`DocumentRef`), so a byte-identical mirror can declare its original across
     sources. A friendlier manifest label is a loader concern for a later step.
  3. **What a declaration may not be.** A self-derivation, a target that is not in the corpus, and a cycle of any length are refused at ingestion (three typed refusals), and a snapshot refuses them too, because a
     cycle would set aside every cited document of it and count none. Not ruled.
  4. **Duplicates.** A document declared twice under one source, even written with other line endings or Unicode forms, is refused (`DUPLICATE_DOCUMENT`), not silently merged; the same content under two sources is
     not a duplicate (D-221 point 1). Repeated `derived_from` entries collapse to one.
  5. **The chunker (D-215, D-222 point 3).** The unit is the word: a maximal run of characters outside a fixed whitespace set (the ASCII controls and space, U+0085, U+00A0, U+1680, U+2000 to U+200A, U+2028, U+2029,
     U+202F, U+205F and U+3000), so no result depends on the interpreter's Unicode tables; zero-width characters, the soft hyphen and U+180E are not whitespace. Two or more line feeds between words end a
     paragraph. Paragraphs are packed greedily into chunks of at most `max_words` words; a longer paragraph is cut into consecutive windows of `max_words` words and never merged with a neighbour. A chunk is the trimmed
     span from its first word to its last, in code-point offsets into the normalised text, and chunks do not overlap. `max_words` has no default: the fixture (Step 5) states it, aiming under the semantic model's
     128-piece window, whose word-piece check stays in the semantic boundary. The scheme id is `paragraph-pack-v1/max_words=N`.
  6. **The snapshot id (D-212).** A digest of its version, the normalisation version, the chunking scheme id, the sorted `(source_id, document_id)` pairs and the sorted derivation edges. Derivations are included
     because they change independence outcomes; the retrieval scheme is not, because it describes an index over a snapshot and not the snapshot.
  7. **`evidence_ref`** is `evidence:` and the first 16 hexadecimal digits of the `chunk_id` (the accepted readiness report); ingestion refuses a collision (`EVIDENCE_REF_COLLISION`) and a snapshot refuses one too.
  8. **Identifier shapes.** `source_id` matches `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`; document, chunk and snapshot ids are 64 lowercase hexadecimal digits; a chunking scheme id matches
     `^[A-Za-z0-9][A-Za-z0-9._=/-]{0,127}$`. Plain constrained strings, so `eidos.contracts` is unchanged.
  9. **Refusals.** A corpus that cannot be ingested returns the first refusal in a fixed order (an empty corpus; then, per document in the order given, the source id, encodability, no words, a duplicate; then the
     derivations; then an evidence-reference collision) and never raises. Nine codes. Which refusal comes first can depend on the order the documents were given in; the snapshot never does.
  10. **What identity depends on.** NFC follows the Unicode database of the running interpreter. Measured 2026-09-25: Python 3.12.10 (EIDOS) has database 15.0.0 and Python 3.13.1 (the D-214 benchmark
      environment) has 15.1.0; NFC and NFD agreed on all 1,112,064 single code points and on 520,930 sampled base-plus-mark pairs (565 bases by 922 combining marks), and the test corpus gave the same snapshot id
      and digest in both. That is evidence, not a proof for every sequence, so the isolated benchmark process should still check that the snapshot id it works from equals the snapshot's own.
  11. **Text, not bytes.** The Step 2 entry point takes text. Strict UTF-8 decoding of files, and refusing invalid bytes, belongs to the loader, with the fixture (Step 5).
  12. **Deferred by design.** `query_id` and the retrieval contracts (`RetrievalRequest`, `RetrievedChunk`, `RetrievalResult`, `RetrievalFailure`, `KnowledgePort`), `EvidenceRecord` and `RetrievalFacts` have no
      consumer until Steps 3 to 6 and need D-222 points 5 and 6, so they are not built. **The readiness report's per-reference `SourceKeyResolver.key_of` cannot express the ruled rule** (whether a cited document
      counts depends on which other documents are cited), so Step 3's resolver is set-based (`independent_sources(cited)`); D-210 stayed Open at Step 2 and was ruled afterwards (built at Step 3, D-224).
- **Still Open, unaffected (as of Step 2; D-210 and D-222 point 4's import-guard part were ruled afterwards, on 2026-09-25):** D-210; D-222 points 1, 4 (its import-guard part), 5, 6, 7 and 8; D-204 to D-207.
- **Effect:** additive only. No `eidos.contracts`, `eidos.state`, `eidos.agents`, `eidos.policy`, dependency, V1.1 or V1.2 change; `pyproject.toml` is unchanged; nothing imports `eidos.knowledge`.

### D-224 — V1.3 Step 3: readings taken where the rulings were silent (PARTLY RULED 2026-09-25)

- **Status:** Partly ruled, partly Open · **Date:** 2026-09-25 · **Raised by:** Claude Code while implementing V1.3 Step 3 (the evidence ledger and the D-210 resolver); **readings 1 and 7 ruled by the human owner on 2026-09-25 (below); the others not decided**
- **Source:** D-208 to D-223 (D-209, D-210, D-212, D-219, D-221 and D-222 point 4 in particular); the accepted readiness reports (§4, the `EvidenceRecord` row of §18); CLAUDE.md §7 and invariants 8, 10, 12, 13 and 16
- **Why recorded:** the D-210 ruling fixed that a V1.2 document receives a deterministic knowledge identity from its existing artifact/reference identity plus its normalised content, and the import-guard ruling fixed
  the direction of the dependency. Neither said what the "existing reference identity" of a tool document is, how a source id is derived from a reference, or which knowledge names the boundary contains before a
  `KnowledgePort` exists. Each reading below is the smallest implementation and lives in one function or constant.
- **What Step 3 built:** in `eidos.knowledge`, `evidence.py` (pure): `EvidenceRecord`, `EvidenceRefusal`, `IndependenceResolution`, `evidence_from_snapshot`, `merge_evidence`, `resolve_independence`,
  `legacy_supplied_record` and `legacy_tool_record`; in `eidos.agents`, `evidence_ledger.py`: `EvidenceLedger` (in memory, one lock) and `resolve_supplied_evidence`. Nothing else imports the knowledge package, the
  verifier, the recorder, the artifact store, the tool gate and every existing contract are unchanged, and `pyproject.toml` is unchanged.
- **Readings:**
  1. **The identity of a tool document (D-210).** Its "existing reference identity" is the tool and the provider's own document id, `(tool_id, document_id)`; the request digest in
     `tool:<tool_id>:<args_digest>:<document_id>` is retrieval provenance and takes no part in the identity, so the same document reached by two queries is one source. *Alternative not taken:* the whole reference
     string, which keeps V1.2's keying and so keeps the D-207 reading 1 limitation (a repeated retrieval counts twice), which D-209 ("repeated retrieval of the same chunk = one source") exists to remove. A one-line
     change in the resolver (`legacy_tool_record` and its call). A caller-supplied document's identity is its reference string.
  2. **How a source id is derived.** `legacy-` and the first 32 hexadecimal digits of the SHA-256 of a canonical JSON object naming a version, the kind (`supplied` or `tool`) and the identity fields. A digest,
     because a reference may contain characters the source-id shape excludes; the kind tag keeps a caller reference that reads like a tool reference from sharing a source with the tool document it resembles when
     built through the pure functions. The result always matches the existing source-id shape (39 characters). **No reserved prefix is enforced:** a manifest may declare a source that starts with `legacy-`, because
     the Step 2 contracts are not reopened; a collision would need a deliberate 128-bit match.
  3. **One document, one chunk.** A V1.2 document becomes one chunk of its whole normalised text under the scheme id `legacy-artifact-v1` (offsets 0 to its length), identified by Step 2's `chunk_id_of` unchanged;
     its `document_id` is the digest of the normalised content, as ruled. A V1.2 record carries no snapshot. V1.2 had no way to declare a derivation, so V1.2 documents have none.
  4. **Which references are tool documents.** By the V1.2 convention: a reference `parse_tool_document_ref` reads is a tool document, anything else a caller document. A caller document deliberately named like a
     tool reference is therefore read as that tool document (a limitation, the same one V1.2 has), and the parser does not check that the digest is a digest; the resolver does not use it either.
  5. **What is refused.** A V1.2 document with no content is refused (`EMPTY_DOCUMENT`); a document of only whitespace is one chunk, as V1.2 counted it. A reference that is not a supplied artifact of the execution,
     such as a step's produced artifact, is refused (`NOT_SUPPLIED`). The ledger refuses a different chunk under a held evidence reference (`EVIDENCE_REF_COLLISION`, possible across snapshots of one execution because
     Step 2 only checks inside one) and the same chunk from a different snapshot (`SNAPSHOT_CONFLICT`); a refusal changes nothing. Refusals are returned, never raised; a malformed query id, a tampered record, records of
     different references handed to `merge_evidence`, and two different chunks under one reference in the resolver's input are contract violations and raise.
  6. **What a record holds.** `EvidenceRecord(chunk, chunking_scheme_id, snapshot_id, retrieved_by)`: the accepted readiness report's `EvidenceRecord(evidence_ref, chunk, retrieved_by)` with the scheme and the
     snapshot made explicit, so that a record re-derives its own chunk id and cannot claim an identity its parts do not have. `retrieved_by` holds sorted, distinct query ids (the D-212 `query_id`, whose derivation
     belongs to the retrieval contracts of a later step). **A V1.2 record carries no query provenance:** V1.2's `args_digest` digests the tool arguments, which is not the V1.3 `query_id`, and it stays in the
     artifact reference, untouched.
  7. **Merging the same evidence again.** One record per evidence reference: the same chunk retrieved again keeps that record and adds the query id to it (a union, order independent); recording the same chunk and
     query again changes nothing. One chunk from two snapshots in one execution is refused rather than merged (reading 5); the alternative is a record that names every snapshot it was retrieved from.
  8. **The ledger's scope and locking.** One object, keyed by `execution_id` as the artifact store is, in memory. One lock makes the read-merge-write of `record` atomic (the accepted design called the ledger
     thread-safe); a test slows the merge down to prove it. No other concurrency machinery.
  9. **Independence is resolved over a set.** `resolve_independence(cited, records, derived_from)` returns the cited references the ledger holds, those it does not (reported, never counted), the distinct
     documents and the independent sources, delegating to Step 2's `independent_sources` unchanged. `derived_from` is a required argument: leaving the declarations out would silently over-count independence.
  10. **The boundary.** Until a `KnowledgePort` exists, the dependency the import-guard ruling permits is one agents module, `evidence_ledger.py`, taking exactly nine names from the package root (`DocumentRef`,
      `EvidenceRecord`, `EvidenceRefusal`, `EvidenceRefusalCode`, `IndependenceResolution`, `legacy_supplied_record`, `legacy_tool_record`, `merge_evidence`, `resolve_independence`); a guard pins the module, the names
      and the root. A later step adds names on purpose. The agents guard's pinned set of allowed layers is extended deliberately (it now names `eidos.knowledge` beside `eidos.policy`).
  11. **What is not wired.** The verifier, the recorder, the Research agent and the artifact store are unchanged, so no verdict changes and there is still no verifier rule that reads the ledger. The earlier ladder
      described Step 3 as "the EvidenceLedger and the verifier resolver"; the ruling authorised the ledger and its resolvers only. How a model's `[[ref]]` citation reaches an evidence reference, and a
      resolver-backed verification rule, wait for the steps that record citation edges (Step 4) and integrate Research.
- **Still Open, unaffected:** D-222 points 1, 5, 6, 7 and 8 and the parts of D-222 not ruled; D-223; D-204 to D-207.
- **Effect:** additive only. No `eidos.contracts`, `eidos.state`, `eidos.policy`, verifier, recorder, dependency, V1.1 or V1.2 change; `pyproject.toml` is unchanged. The existing source files touched are the two
  package `__init__` files (exports); the existing tests touched are the two guard tests (revised deliberately, as they said they would be: the agents ratchet now pins two added layers, and "no other package imports
  the knowledge package yet" became "only the evidence ledger imports it, from the package root") and the knowledge test factories (helpers added).
- **Rulings (owner, 2026-09-25, with the Step 4 brief):** **reading 1 is ruled as read** (a tool document is identified by the tool and the provider's document id; the request digest is not part of the identity, so the same provider document reached through different queries is one knowledge document and source), and **reading 7 is ruled as read** (a single evidence reference or chunk is never merged across snapshots; the conflict is refused and no multi-snapshot record is made). Readings 2 to 6 and 8 to 11 stay Open. Recorded with D-225.
- **Update (owner, 2026-09-26, D-228.1):** reading 11's "resolver-backed verification rule" is **not part of V1.3**: the verification semantics are unchanged, no verdict reads the ledger, and the resolver stays available for a later verifier/evidence milestone.

### D-225 — V1.3 Step 4: retrieval contracts, replay, the lexical retriever and the frozen benchmark (rulings; the readings taken are OPEN)

- **Status:** Partly ruled, partly Open · **Date:** 2026-09-25 · **Decided by:** human owner (the rulings below, given with the Step 4 brief on 2026-09-25); the readings are Claude Code's, **not decided**
- **Source:** D-208 to D-224; the two accepted readiness reports (the `KnowledgePort` boundary, the typed contracts, the id table, the retrieval-result and replay designs, the determinism table, the benchmark design and
  the metrics, all of which this record takes as its source of truth); CLAUDE.md §7 and invariants 8, 12, 13, 15, 16 and 17
- **Owner rulings (2026-09-25):**
  1. **Tool-document identity (D-224 reading 1): ruled as read.** A tool document is identified by the tool/provider identity plus the provider's document id; the request digest is not part of the identity, so the
     same provider document retrieved through different queries resolves to the same knowledge document and source.
  2. **Evidence from different snapshots (D-224 reading 7): ruled as read.** A single evidence reference or chunk cannot be merged across snapshots; the conflict is refused, and no multi-snapshot record is made.
  3. **The milestone is reshaped.** The former Steps 4 and 5 are ONE milestone, **Step 4 = retrieval contracts + replay + deterministic lexical retrieval + the frozen benchmark**, with internal phases (A contracts and
     replay, B the lexical retriever, C the benchmark) and one local commit. The steps after it are **Step 5 semantic retrieval, Step 6 the lexical-versus-semantic comparison and the human decision, Step 7
     Research integration and the end-to-end scenario, Step 8 the V1.3 close-out.**
  4. **The remaining D-222 retrieval decisions (bounds, the form of the query, `query_id`) are to be resolved before coding, from the readiness reports and the accepted decisions, with no further architecture
     invented.** They are resolved below as readings (1 to 4); what the sources do not settle is left Open and named.
  5. **Scope.** The minimum retrieval contracts (`RetrievalRequest`, `RetrievedChunk`, `RetrievalResult`, `RetrievalFailure`, a deterministic `query_id`), retrieval facts, citation facts and the retrieval metadata
     replay needs; replay that uses only recorded facts and can never call a retriever, load a model or an embedding, reach Qdrant or a vector index, use the network or the file system, or recompute retrieval;
     a deterministic exact in-process lexical retriever behind `KnowledgePort`; the approved small benchmark, frozen before any result is observed, with the approved metrics, reported without calling any retriever
     better, best or sufficient. Not built: Qdrant, Sentence Transformers, a cross-encoder, embeddings, ANN, external search, a RAG framework, Research integration, any V1.2 execution or verifier change, a
     frontend, FastAPI, Supabase, Docker or deployment. The dependency direction stays agents to the knowledge boundary; `eidos.knowledge` never imports agents, policy, MCP, LangGraph or infrastructure.
- **Readings taken (Open, none blocking):**
  1. **The contract.** All are `EidosModel` types in `eidos.knowledge.retrieval`, identifiers plain constrained strings. `RetrievalRequest(kb_id, snapshot_id, scheme_id, text, top_k, max_result_bytes)`, no defaults: the
     caller pins the knowledge base, the snapshot and the retrieval scheme it means, and states both bounds. `RetrievedChunk(rank, chunk, score)`: `chunk` is the Step 2 `KnowledgeChunk`, `rank` an integer from 1,
     `score` present only if the scheme provides one. `RetrievalResult(query_id, kb_id, snapshot_id, scheme_id, score_kind, hits)`: the hits are ranked 1 to n in order, ordered by score descending and then `chunk_id`
     ascending when scored, each chunk at most once; `score_kind` names what a score is (a label, never a confidence) and is present exactly when the hits carry scores. `RetrievalFailure(kind, message)`, with
     four kinds: `UNAVAILABLE`, `REQUEST_MISMATCH` (the request names a knowledge base, snapshot or scheme the port does not serve), `RESULT_TOO_LARGE` (the hits' text exceeds `max_result_bytes`; never truncated) and
     `MALFORMED_RESULT` (a result that does not answer its request). `KnowledgePort.retrieve(request) -> RetrievalResult | RetrievalFailure`: synchronous, thread-safe, total (a failure is returned, never raised) and
     read-only. An empty result is a real result. A hit is not evidence and not an independent source. The readiness report's `RetrievalQuery`, `EvidenceReference` and `KnowledgeSource` stay deleted; the gate,
     `KnowledgeBaseDescriptor` and admission are Step 7.
  2. **The form of the query (D-222 point 6, D-217).** The query is the mission goal, unchanged, taken as V1.2 takes it (`goal.strip()`, D-207 reading 7) and not transformed; no rewriting, expansion or decomposition
     exists. Its canonical form is Unicode NFC, CRLF and CR read as LF, and the ends stripped of the fixed whitespace set of Step 2's chunker (so the result does not depend on the interpreter's Unicode tables; it
     differs from `str.strip()` only for the four control characters U+001C to U+001F). A `RetrievalRequest` accepts only text that is already canonical and non-empty, so one query has one identity. There is no
     maximum query length in the contract.
  3. **`query_id`.** The SHA-256 of the canonical JSON (sorted keys, ASCII escapes, compact separators) of `{"version": "query-v1", "kb_id", "snapshot_id", "scheme_id", "text", "top_k"}`: the accepted formula
     (`{kb_id, normalised text, top_k, scheme_id, snapshot_id}`) with a version tag, like every other id. It depends on nothing else: not the plan, the execution, the caller, the clock or the hash seed. **The
     byte bound is not part of it**: it is per-knowledge-base configuration (D-216), not query identity, so the same query under a changed bound keeps its id (the gate at Step 7 decides whether a stored answer
     may be served across a changed bound).
  4. **Bounds (D-216, D-222 point 5).** Retrieval is bounded by `top_k` (at least 1) and `max_result_bytes` (at least 1), both carried by the request and neither defaulted; bytes, not tokens, measured as the UTF-8
     size of the returned chunk texts, as tool results are (V1.2). A result over the byte bound is the typed failure `RESULT_TOO_LARGE`, never a truncation. The contract sets no ceiling on either number: a
     ceiling is per-knowledge-base configuration checked at admission (Step 7). **Not resolved here, and left Open for Step 7:** the maximum number of queries per execution or plan attempt, the denial vocabulary,
     and whether an exhausted bound returns a typed denial; they are gate and admission concerns, and the readiness reports name no vocabulary for them.
  5. **Ordering, ties and scores.** Every port orders hits by score descending and then `chunk_id` ascending, with integer ranks from 1; a scheme with no score orders by its own rule and says so in its scheme
     id. A score is a labelled measurement and is never read by verification (D-015, D-016, invariant 17).
  6. **The lexical scheme (D-208 item 2, readiness §12).** `lexical-bm25-v1/k1=1.2/b=0.75/tokens=word-v1`, in the standard library only: tokens are the runs of word characters of the NFC text, lower-cased (the
     interpreter's Unicode tables, the same class as NFC); no stop list, no stemming. Score is Okapi weighting with `idf = ln(1 + (N - df + 0.5) / (df + 0.5))` over the snapshot's chunks and each distinct query
     term once; `k1` and `b` are the customary values, fixed before any run and never tuned. **It is computed in exact decimal arithmetic**, whose logarithm is correctly rounded and so does not depend on the
     platform's math library (the readiness report's `log` and libm concern), and each score is rounded to 1e-9, so ties are real ties and are broken by `chunk_id`. A chunk that shares no term with the query is not
     a hit, so an empty result is possible. The index is built in memory from the pinned snapshot when the port is made; nothing is written and nothing persists. **Boundary reading (D-219, D-222 point 4, the rule
     it left Open):** the package keeps its core modules free of any engine or model name; the one module that implements a retriever, `lexical.py`, is standard library only and may name the scheme; the guards are
     revised to say exactly that, and any third-party engine, vector store, embedding or model name stays forbidden in every module.
  7. **Retrieval and citation facts (D-218).** Additive fields on `NODE_SETTLED`, no new event. `RetrievalFacts(kb_id, snapshot_id, scheme_id, query_id, top_k, outcome, score_kind, hits, result_bytes, elapsed_ms)`
     with `RetrievalHitFacts(rank, chunk_id, document_id, source_id, content_digest, score)`; the outcome is `result` or one of the four failure kinds (mirrored, and a guard keeps them in step); `denied` and
     `served_stored` join it when the gate exists. **No chunk text and no query text is recorded** (content stays out of the log, D-076; `query_id` identifies the query). The facts validate themselves: ranks 1 to
     n, each chunk once, at most `top_k` hits, scores present exactly when `score_kind` is, and the ordering rule, so a tampered fact is unconstructible. `citations` is the tuple of references a work artifact cited
     (its `source_refs`, verbatim, each once), a work node's only. Both fields are empty by default, so a log written before them replays identically. Captured only through `record_baseline`, as tool facts
     are (D-204 unchanged). The recording adapter maps a port's answer to facts, and an answer that does not answer its request is recorded as `malformed_result`, never dropped and never trusted.
  8. **Replay and the audit (D-218).** Replay folds the log exactly as before; the new facts ride in the events, so replay reproduces them from the log alone and imports nothing that could retrieve. `audit_evidence`
     in `eidos.state` is the derived projection over an `ExecutionRecord`: it resolves each recorded citation to the recorded hits that carry the same evidence reference (a rule mirrored from
     `eidos.knowledge` and kept equal by a test, as the tool-outcome enums are), and reports it as resolved, unresolved, ambiguous (one reference recorded for two chunks) or not knowledge evidence, with the
     query, snapshot, rank, chunk, document and source of every hit. It does not count independent sources: the derivations live in the snapshot, not in the log (`snapshot_id` pins them), so the count is composed
     by a caller that holds the snapshot, and the comparison with the verifier's recorded reason waits for the verifier wiring (Step 7).
  9. **The dependency graph.** `eidos.state` imports no knowledge (its facts mirror identifiers as constrained strings, as `ToolCallFacts` does). `eidos.recording` gains one edge, to `eidos.knowledge`, in one
     module, from the package root, for the retrieval adapter (`retrieval_facts_of`, `RecordingKnowledgePort`), and its guard is extended deliberately, as the agents guard was for the ledger. The recording seam
     wraps the `KnowledgePort` now; at Step 7, as for tools, the seam moves to the gate. `RecordingAgent` gains an optional artifact store for citations; without one it does exactly what it did.
  10. **The benchmark (D-213, readiness §14 and §15).** *Fixture:* a fictional tidal power station; 12 documents in 6 sources and 48 to 60 chunks (the exact number is recorded with the frozen digest),
      each paragraph one chunk of at most 60 words (the semantic model's word-piece check needs the tokenizer and runs at Step 5); a byte-identical mirror of one document under a second source; a second source that restates another's facts in other words,
      undeclared; three distractor documents that reuse the queries' vocabulary. *Queries:* 36 in English, 6 development (debugging only) and 30 frozen test queries: lexical-overlap 8, paraphrase 10,
      multi-source 6, distractor-bait 6 (the development six are spread across the strata). Each stratum is defined by construction and **checked mechanically**, never by observed performance: a lexical-overlap
      query shares at least two content tokens with every gold chunk, a paraphrase query none, a multi-source query has gold chunks in at least three sources, a distractor-bait query shares at least two content
      tokens with some non-gold chunk (content tokens: the fixture's own fixed stop list, independent of the retriever). *Gold labels* are over content-equivalence groups (chunks of identical text), so the mirror
      pair is one gold group; every chunk that states the fact is gold, the restating source's included. *Frozen:* the fixture, its gold labels and the metric definitions are digested and the digest pinned in a test
      before the first retrieval run; nothing is tuned against it, and the lexical parameters are the customary ones fixed above. *Metrics, as operationalised:* Recall@k (k = 1, 3, 5) and MRR over the ranking
      deduplicated by content-equivalence group, macro-averaged over queries and computed from the full ranking (the request's `top_k` is the corpus size for measurement; a test shows that a `top_k` of 5 returns
      exactly the first five); source-coverage@k is over the chunk ranking (the first k chunks, each carrying its declared source, so a mirror is two sources, D-221) and is a supplementary measure of this
      record's, not a substitute for the owner's. Reported overall and per stratum, the development and test sets separately, with per-query ranks; no significance test, and none of the strata has enough queries
      for a gap below about 0.2 to mean anything (readiness §15). Efficiency is measured from actual runs only: index build and query latency (warm median and p95, one cold run in a fresh interpreter), peak
      memory allocated by Python (`tracemalloc`, not process memory), the fixture's size on disk, the third-party modules loaded, and reproducibility across repeats, hash seeds and construction order.
  11. **Not decided, left to the owner (named, not invented):** any numeric decision rule or margin (D-222 point 7 b: none is pre-registered, and the report says nothing about which retriever is better or
      sufficient); the review of the paraphrase queries by the owner (point 7 c: the fixture is frozen as authored, and that review is still owed); whether measured latency or memory budgets matter (no budget is
      set). Not built: the semantic retriever, the comparison, Research integration.
- **Built (2026-09-25, V1.3 Step 4; one commit):**
  - `eidos.knowledge.retrieval`: `RetrievalRequest`, `RetrievedChunk`, `RetrievalResult`, `RetrievalFailure` and its four kinds, `KnowledgePort`, `canonical_query_text`, `query_id_of` and `result_problem`. `eidos.knowledge.lexical`:
    `LexicalKnowledgePort`, scheme `lexical-bm25-v1/k1=1.2/b=0.75/tokens=word-v1`, exact decimal arithmetic in the standard library alone, no dependency added.
  - `eidos.state`: `RetrievalOutcome`, `RetrievalHitFacts`, `RetrievalFacts`, the additive `NodeSettledPayload.retrievals` and `.citations`, the matching `StepRecord` fields, and `audit_evidence` (`evidence_audit.py`).
    `eidos.recording`: `retrieval_facts_of`, `RecordingKnowledgePort`, `RecordingCitations`, the tracker's retrieval and citation collections, and the recorder's hand-off and settlement wiring.
  - The frozen benchmark: `tests/support/eidos_retrieval_fixture.py` (corpus, queries, gold labels, digest), `eidos_retrieval_benchmark.py` (metrics, runner, cost harness) and the scenario `test_retrieval_benchmark_lexical.py`.
  - Unchanged: `eidos.contracts`, the reducer, the verifier, `eidos.agents` (`RecordingAgent`, `record_baseline` and `record_attempt` keep their signatures, pinned by tests), `eidos.policy`, `eidos.mcp`, every V1.2 contract,
    Steps 2 and 3, and `pyproject.toml`. Guards revised deliberately, as they said they would be: the knowledge guards now confine retrieval vocabulary to `retrieval.py` and `lexical.py`, allow `decimal` and the word
    `bm25` in `lexical.py` only and still forbid every embedding, vector, reranking and third-party engine name; the recording guard gains `eidos.knowledge` for one module and five names.
- **Readings found while building (Open, none blocking):**
  12. **Citations are captured by a wrapper, not a parameter.** `RecordingCitations` wraps a work agent and adds the references its artifact cited to the tracker; `RecordingAgent` hands them over exactly as it hands
      over tool calls and retrievals. An optional store parameter on `RecordingAgent` or `record_baseline` would have changed signatures an existing test pins (D-204). A citation is what the artifact's `source_refs` say,
      verbatim, whatever kind of reference it is.
  13. **The audit is not causal.** `audit_evidence` resolves a citation against every retrieval recorded in the same execution record, in any step, and does not require the retrieval to come first in plan order
      (steps are in plan order, not time order). It reports; it does not judge support (D-015) or count independent sources (reading 8).
  14. **Retrieval moves no mission counter.** Nothing in `MissionState` changes because a node retrieved (retrieval is bounded by the request, D-216, and not budgeted here); a recording wrapper that shares a clock
      with the recorder lengthens the accounted node time by the readings it takes, which is the only difference a test found.
  15. **What the measured ranking contains.** A lexical retriever returns only chunks that share a term with the query, so a gold group with no shared term has no rank: two of the 36 queries have one (M03 and MD1,
      below). `df` counts chunks, so a byte-identical mirror doubles the document frequency of its terms, which the scheme states rather than corrects.
  16. **`MALFORMED_RESULT` is recorded by the adapter.** A port's answer that does not answer its request (`result_problem`), or is neither a result nor a failure, is recorded as `malformed_result` with the request's
      identity and nothing else; the gate at Step 7 will make the same check before it serves an answer.
- **The fixture (frozen 2026-09-25T23:14:01+05:30, before the first retrieval run at 2026-09-25T23:17:23+05:30):** digest `93db0b1f14c7c444073f86c763e891f1ccab92e5259f62351305b374db57df6b`; snapshot `b76e15e080adadab784effc727ec8876145b0e2a2ba80b833dce4b043d58491c`. 12 documents in 6 sources (`ops`, `safety`, `maint`, `grid`, `archive`,
  `outreach`; one source holds four documents), 53 chunks (one paragraph each, 38 to 53 words), `archive` holds a byte-identical copy of the safety audit, `outreach` restates four maintenance paragraphs in other words and
  declares nothing, and three outreach documents are distractors. 36 English queries: 30 frozen test (lexical 8, paraphrase 10, multi-source 6, distractor bait 6) and 6 development (2, 2, 1, 1); every stratum definition is
  checked mechanically (57 tests) and no gold label was chosen from a retrieval result. Fixture tests were written and passed before the first run; nothing was tuned afterwards.
- **The measured lexical baseline (the first run, 2026-09-25T23:17:23+05:30, reproduced byte for byte by every later run; macro-averages over queries, from the full ranking; exact rationals are in the scenario test):**

| Queries | n | Recall@1 | Recall@3 | Recall@5 | MRR | Source-cov.@1 | @3 | @5 |
|---|---|---|---|---|---|---|---|---|
| **test, all 30** | 30 | 0.4386 | 0.4700 | 0.5186 | 0.6344 | 0.4056 | 0.5000 | 0.5500 |
| test: lexical overlap | 8 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.9375 | 1.0000 | 1.0000 |
| test: paraphrase | 10 | 0.0000 | 0.0000 | 0.1000 | 0.0782 | 0.0000 | 0.0000 | 0.1000 |
| test: multi-source | 6 | 0.1931 | 0.3500 | 0.4264 | 1.0000 | 0.2778 | 0.5000 | 0.5833 |
| test: distractor bait | 6 | 0.6667 | 0.6667 | 0.6667 | 0.7083 | 0.5000 | 0.6667 | 0.6667 |
| development, all 6 (debugging only) | 6 | 0.5333 | 0.5667 | 0.6000 | 0.6944 | 0.5417 | 0.5833 | 0.6250 |

  - Reading these numbers: each stratum has 6 to 10 queries, so a gap below about 0.2 in a macro-average is not distinguishable from noise (readiness §15), and Recall has a ceiling below 1 wherever a query has several gold groups
    (multi-source queries have 4 to 8). **No retriever is called better, best or sufficient on this evidence, no threshold or margin exists, and this is a baseline for Step 5's semantic run, not a result.** Two queries have a
    gold group the lexical retriever cannot return because it shares no term with the query: M03 (a restating paragraph says "brake disc", the query "braking discs") and MD1 (a paragraph says "record" and "file", the query
    "recorded" and "filed"); they are counted, not removed. The owner's review of the paraphrase queries (D-222 point 7 c) is still owed.
  - Cost, measured and never asserted: one machine, one day (Windows-11-10.0.26200-SP0, CPython 3.12.10, AMD64, Intel64 Family 6 Model 154 Stepping 3, GenuineIntel): building the index took a median of 3.19 ms (p95 3.54 ms over 30 builds); a full-ranking query took a median of 2.17 ms warm (p95 3.14 ms, maximum 6.61 ms over 1080 calls); in a fresh interpreter, five cold runs took 745 to 788 ms to import, 9.3 to 9.9 ms to build the snapshot, 2.2 to 2.6 ms to build the index and 3.2 to 3.6 ms to answer the first query; the peak memory Python allocated for the snapshot, the index and all 36 queries was 280,749 bytes (`tracemalloc`, not process memory); the corpus is 14,354 bytes of UTF-8 in 12 documents (53 chunks, 14,272 bytes of chunk text) and the index is in memory only (0 bytes on disk); the third-party modules a retrieval loads are annotated_types, pydantic, pydantic_core, typing_extensions, typing_inspection, all already required by the contracts, and no engine, model or network library.
  - Reproducibility: the report digest `f10840ecaf7642f1ffbb098e031ae165a2ae017f913577495766965214a822ff` is identical across repeats, under four hash seeds and for shuffled document order (and a lexical answer does not depend on the ambient decimal context: a unit test); a `top_k` of 5 returns exactly the first five of the
    full ranking for every query; a mirror pair is a real tie ordered by chunk id.
- **Tests and checks (2026-09-25):** 501 new tests in nine files (115 retrieval contracts, 68 lexical, 26 metrics, 57 fixture, 110 state facts, 21 audit,
  60 recording, 27 replay integration, 17 benchmark scenario) and 56 more guard cases; the full default suite 6,278 passed and 2 deselected (was 5,721) under
  `PYTHONHASHSEED=57721`; mutation on isolated copies (four workers; the repository fingerprint identical before and after every run): 224 of 235 caught by a real test failure on the first run; of the 11 survivors, 6 were real test gaps and were closed by new tests (re-run: caught), 3 were checks in my own code that proved redundant and were removed from the source rather than excused (one re-tested with its new anchor: caught), and 2 are equivalent by analysis (query terms taken in set order, which only reorders decimal additions at 40 digits under a rounding to 1e-9, and an enumeration from zero that is algebraically the same)
- **Still Open, unaffected:** D-222 points 1 (the milestone label), 7 (b and c) and 8 (the isolated-process mechanics) and, for Step 7, the admission vocabulary and the number of queries per execution; D-223; D-224
  readings 2 to 6 and 8 to 11; D-204 to D-207.
- **Effect:** additive. `eidos.contracts`, the reducer, the verifier, `eidos.agents`, `eidos.policy`, `eidos.mcp`, every V1.2 contract and `pyproject.toml` are unchanged; Steps 2 and 3 behave exactly as before. Existing source
  edited: the `__init__` exports of `eidos.knowledge`, `eidos.state` and `eidos.recording`, and additively `state/payloads.py`, `state/execution_record.py`, `recording/adapters.py`, `recording/recorder.py` and `recording/run.py`.
- **Update (owner, 2026-09-26, D-228.1, D-228.3 and D-228.4):** reading 8's comparison with the verifier waits for a later verifier/evidence milestone (the verifier was not wired at Step 7 and is not in V1.3); the `served_stored` and `denied` outcomes of reading 7 are not added in V1.3 (deferred with the query ceiling, D-228.4); reading 9's seam stays the single port-level `RecordingKnowledgePort` and D-228.3 adds no second recording seam (the wording "the seam moves to the gate" is read as in D-228 reading 8, not separately confirmed).

### D-226 — V1.3 Step 5: semantic retrieval behind `KnowledgePort` (owner rulings; the environment measured; the readings taken are OPEN)

- **Status:** Partly ruled, partly Open · **Date:** 2026-09-26 · **Decided by:** human owner (the rulings below, given with the Step 5 brief); the readings are Claude Code's, **not decided**
- **Built and measured:** 2026-09-26 (V1.3 Step 5, committed locally, not pushed); see "Built" and "Measured" below
- **Source:** D-208, D-213 to D-215, D-219, D-220, D-222, D-225; the two accepted readiness reports (§3, §8 to §10, §14, §15); CLAUDE.md §7 and invariants 9, 10, 13 and 15
- **Owner rulings (2026-09-26):**
  1. **No numeric pass/fail threshold** is imposed before the lexical-versus-semantic comparison (this rules D-222 point 7 (b): no decision rule or margin is pre-registered). The frozen benchmark measures both
     approaches; the owner reviews the results and decides which becomes the baseline. Nothing is to be declared better, best, sufficient or rejected on a pre-set number, and Step 5 produces only the semantic
     measurement and the comparable results, not the decision (that is Step 6).
  2. **Runtime environment.** The main EIDOS runtime stays on Python 3.12. Sentence Transformer retrieval runs in the already verified isolated Python 3.13.1 environment. No Python 3.13 ML dependency is added to the
     main environment and `pyproject.toml` is not modified to support semantic retrieval. The process boundary must be deterministic, bounded, replaceable and isolated. The model library never leaks into the core knowledge
     contracts.
  3. **Qdrant stays deferred** (later, an MVP storage implementation behind `KnowledgePort`). No cross-encoder. Steps 2 to 4 are not reopened unless a genuine contradiction is found.
  4. **The model** is the cached `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, at **the exact previously verified cached revision and digest the project recorded** (this confirms the reading of D-222 point 2:
     revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`, weights SHA-256 `eaa086f0ffee582aeb45b36e34cdd1fe2d6de2bef61f8a559a1bbc9bd955917b`). No model is downloaded, no package installed, no other model or the
     cross-encoder used, and no Hugging Face network access is made. Its 128 word-piece window is respected: the ruled chunk bound is enforced mechanically at the semantic boundary, **a chunk over it gets a typed,
     deterministic failure and is never silently truncated**.
  5. **Semantic retrieval requirements:** snapshot- and model-pinned; deterministic query normalisation and embedding invocation; exact cosine similarity, never ANN; deterministic score ordering with `chunk_id` ties; bounded
     `top_k` and result bytes; no network, no Qdrant, no external vector database. The embedding environment is treated honestly: a fixed execution configuration, the environment and model identity recorded, determinism
     tested across repeated runs, and **no claim of cross-machine bit identity unless demonstrated**.
  6. **The benchmark is the exact frozen Step 4 benchmark**, unmodified (corpus, gold labels, query text, groups, strata, digest), with the same metrics; semantic-specific facts are reported as well (embedding dimension,
     model revision and digest, model load time, embedding and retrieval latency, environment identity, token-piece rejection count). **No tuning against the test set:** any parameter tuned is tuned on the development queries
     only, recorded and frozen before the 30 test queries are evaluated, and nothing is tuned until the benchmark design requires it.
- **The environment, measured (2026-09-26, read-only: no package installed and no model downloaded; the network is refused before any library is imported; the cache held 65 files before and after):**
  the interpreter is `C:\Users\shrey\AppData\Local\Programs\Python\Python313\python.exe` (CPython 3.13.1, MSC v.1942 64 bit); the stack is in its system site-packages: torch 2.9.0+cpu (CPU only, 12 threads by default, no CUDA), sentence-transformers
  5.1.1, transformers 4.57.1, tokenizers 0.22.1, numpy 2.2.1. The model directory
  `~/.cache/huggingface/hub/models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2/snapshots/e8f8c211226b894fcb81acc59f3b34ba3efd5f42` (also what `refs/main` names) holds:
    `1_Pooling/config.json` 190 bytes, SHA-256 `4be450dde3b0273bb9787637cfbd28fe04a7ba6ab9d36ac48e92b11e350ffc23`
    `README.md` 3,888 bytes, SHA-256 `1e98ea05b0de579fcaad3d625b62ea55647142ed674d5f5ebf1440e4bbbb6f23`
    `config.json` 645 bytes, SHA-256 `6300193cb75e01cf80c96decef7187dfb33094d97cc1490b7ead6ff134476e4e`
    `config_sentence_transformers.json` 122 bytes, SHA-256 `b8c64b5cece00d8424b4896ea75b512b6008576088497609dfeb6bd63e6d36b8`
    `model.safetensors` 470,641,600 bytes, SHA-256 `eaa086f0ffee582aeb45b36e34cdd1fe2d6de2bef61f8a559a1bbc9bd955917b`
    `modules.json` 229 bytes, SHA-256 `8f4b264b80206c830bebbdcae377e137925650a433b689343a63bdc9b3145460`
    `sentence_bert_config.json` 53 bytes, SHA-256 `70f4448f31320443fe3557cacea5abf2dcc4915dda8c80646bec9f3bb0aa5a1f`
    `special_tokens_map.json` 239 bytes, SHA-256 `378eb3bf733eb16e65792d7e3fda5b8a4631387ca04d2015199c4d4f22ae554d`
    `tokenizer.json` 9,081,518 bytes, SHA-256 `2c3387be76557bd40970cec13153b3bbf80407865484b209e655e5e4729076b8`
    `tokenizer_config.json` 526 bytes, SHA-256 `5036ea374ffedd706e3bef33e2e0d6953cb868ef8a490e76e32ba0faa37a6b9b`
  Modules `Transformer` and `Pooling`, dimension 384, `max_seq_length` 128, tokenizer `PreTrainedTokenizerFast` with `<s>` and `</s>` as its special tokens. The first
  import of the stack took 35 s (a cold disk cache) and loading the model 0.78 s. **The fixture fits the window:** counting the two special tokens, the 53 chunks are
  53 to 82 word pieces and the 36 queries 11 to 36, none over 128. Repeating the encoding of five chunks with batch size 1 and one thread gave identical vectors.
- **Readings taken (Open, none blocking):**
  1. **Three modules, one boundary.** `eidos.knowledge.semantic` (pure): the `Embedder` protocol, the pinned model identity, `SemanticKnowledgePort`, exact cosine and the mapping of every embedder outcome to a typed retrieval
     outcome. `eidos.knowledge.semantic_process` (the one adapter that spawns a process): `IsolatedEmbedder`, a client of the worker. `eidos.knowledge.semantic_worker` (a program, not a module: nothing imports it): run by the
     3.13 interpreter, the only file that names the library, and it imports no `eidos` and no `pydantic`. The worker embeds and counts word pieces (only it has the tokenizer); the port, in the main runtime, computes cosine,
     ordering, ties, `top_k`, the byte bound and the mismatch checks, so the contract's logic is tested without any model.
  2. **The model identity is pinned by revision and digests, never by name.** The worker loads from the local snapshot directory, never from a name that could resolve `main`, refuses the network (the socket layer is made to
     fail before the library is imported, and the offline flags are set), recomputes the SHA-256 of every file of the directory and refuses (`identity_mismatch`) unless the weights digest equals the pinned one and the directory's
     own digest equals the recorded one. The environment (interpreter, library versions, threads, device, precision) is recorded and reported, not pinned: a different version is a different environment, honestly named.
  3. **A fixed execution configuration:** CPU, float32, one torch thread, batch size 1 (each text encoded alone), evaluation mode, no normalisation by the model (cosine is scale-free), no query prefix; chunk texts embedded
     in canonical chunk order. Nothing is tuned: these are fixed a priori and no parameter is tuned at all in this step.
  4. **Cosine and ranking.** `math.fsum` for the dot product and the squared norms, one division, no rounding of the score; hits ordered by score descending and then `chunk_id` ascending; every chunk is a candidate, so a query
     always returns `min(top_k, chunks)` hits (unlike the lexical retriever, which returns only chunks that share a term). `score_kind` is `semantic-cosine-v1`, and the scheme id names the model and its revision, the
     dimension and the piece bound, so a different model is a different scheme and a different `query_id`.
  5. **Over-window inputs are refused, never truncated.** A chunk over the window makes the index unbuildable: `SemanticKnowledgePort.open` returns a typed `RetrievalFailure` of kind `unavailable` naming the first such chunk
     (canonical order) and its count; a query over the window gets kind `request_mismatch`. **A gap, raised and not resolved:** Step 4's four failure kinds have no kind for "an input over the port's own window", so
     these two are readings that leave Step 4's contract and its mirror in `eidos.state` unchanged; the alternative is a dedicated additive kind and mirror, the owner's to decide.
  6. **The process boundary.** Line-delimited JSON over the worker's stdin and stdout (stdout reserved for the protocol; the library's own prints go to stderr); the interpreter runs isolated (`-I`) with a minimal explicit
     environment; every bound is explicit: a ready timeout (model load), a per-request timeout, a maximum of texts and of characters per request, a maximum reply size, an idle timeout and a total lifetime enforced inside the
     worker, and a kill on close or on any timeout. A crash, a timeout, a malformed or oversize reply, an identity mismatch, a missing model, a missing interpreter and a worker that refuses each become a typed embedder
     failure and then a typed retrieval failure; nothing escapes as an exception. The handshake returns the identity and the environment.
  7. **Replaceable and isolated.** The port depends on the `Embedder` protocol alone; a fake worker speaking the same protocol under the main interpreter lets the whole boundary be tested by default with no ML stack, and a
     different model is a different identity. The main environment imports none of the library (a subprocess test proves it), replay starts no worker (the semantic modules are not imported by replay and a test forbids the
     spawn), and the package `__init__` exports only the pure names, so importing `eidos.knowledge` loads no process code.
  8. **The tests that need the real model are an explicit opt-in** under `tests/integration/semantic/`, marked with the existing `real_model` marker (D-136; the mechanics D-222 point 8 left open), so `pyproject.toml` is not
     touched: they are deselected by default, selected with `-m real_model`, and fail loudly, never skip, when the 3.13 interpreter or the pinned snapshot is missing. They also run under Python 3.13.1.
  9. **What a semantic report adds** (measured from actual runs, never asserted): the dimension, the pinned revision and digests, the worker's start and model-load times, the time to embed the corpus and per query, warm and cold
     query latency through the boundary, the worker's peak working set, the environment identity, the token-piece rejection count, repeated-run identity, the smallest gap between adjacent scores (how much vector jitter the
     ranking could absorb) and, as a stated experiment, how a change of thread count or batch size moves vectors and scores on this machine. It is reported beside the lexical numbers and judges nothing.
- **Built (2026-09-26, Step 5), as read above; what building it settled and what it raised (all of it Open with the readings, none of it silent):**
  1. **Three modules and their tests.** `eidos.knowledge.semantic` (pure; the pinned `PINNED_MODEL`, `SemanticModelIdentity`, `semantic_scheme_id`, the `Embedder` protocol with `EmbeddedText` and the typed
     `EmbedderFailure`, exact `cosine_similarity` by `math.fsum` clamped to [-1, 1], and `SemanticKnowledgePort`, opened once over a snapshot); `eidos.knowledge.semantic_process` (`IsolatedEmbedder`, `WorkerLimits`,
     `WorkerEnvironment`, `WorkerReady`, `semantic_worker_command`, `hub_model_directory`); and `eidos/knowledge/semantic_worker.py`, a program that imports no `eidos` and no `pydantic`. The package root exports the
     pure names only (ten new ones); the process client and the worker are imported by nothing in `src` (a guard proves it). Nothing else changed: no Step 2 to 4 module, no `eidos.agents`, `eidos.state`,
     `eidos.recording`, verifier or V1.2 file, no `pyproject.toml`.
  2. **The identity is pinned once and checked twice.** `PINNED_MODEL` is the only place the revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`, the weights digest and the directory digest
     (`e99a362c5cdf060fe3dec4f42b61f3f847d80ce8881a8c716b3468bdf7ef03dc`, the SHA-256 over `"<path>\n<file sha256>\n"` for the ten files of the snapshot, paths relative with `/`, sorted as strings) are written. The
     client passes them to the worker as arguments; the worker recomputes both digests and the directory's name before it imports the library and ends with `identity_mismatch` on any difference, and the client compares
     the five things the worker measured (revision, both digests, dimension, window) with what it expected and stops the worker on any difference. The worker holds no copy of the identity. The dimension and the window
     are measured by the worker from the loaded model, not asserted.
  3. **The fixed execution configuration is read off the calls.** With a recording stand-in for the library the tests show: one torch thread; the model loaded from its local directory, on the CPU, offline, without remote
     code; put in evaluation mode (and reported as `evaluation_mode`, a field added to `WorkerEnvironment` while building, so it is measured and not assumed); each text tokenized with its special pieces and no truncation
     and encoded alone (batch size 1, no normalisation, no progress bar). The port batches at most sixteen texts per request over the boundary; the worker still encodes each one on its own, so a request's batch changes
     nothing the model sees. The sensitivity experiment below is why the model's own batch is one.
  4. **The process boundary, as built.** Line-delimited ASCII JSON; the interpreter is started as `python -I <script>` with the names of `INHERITED_ENVIRONMENT` only (what an interpreter needs to start, and no
     credential, no `PYTHON*` and no `HF_*` variable), so the caller's environment never reaches it; the worker sets the offline flags and one thread for the library, and refuses every outgoing connection (the socket layer
     fails before the library is imported; a stub worker that tries to connect to a listening local port is refused and the listener sees nothing). `WorkerLimits`, fixed a priori and not tuned: a start (interpreter, digests,
     import, model load) may take 300 s; a request 120 s; a worker that is not asked for 600 s ends by itself; its lifetime is 3600 s from its start; a request holds at
     most 64 texts of at most 20,000 characters; a reply is read with a limit of 4,194,304 bytes. Idle time and lifetime must exceed the start time, and none of them may be infinite
     or not a number (a validator; a lifetime that never ends is not a bound). A timeout, a crash (with its exit code and its last words), an oversize, malformed, short, long or out-of-step reply, a reply to another
     request, a worker's own error report and a wrong identity each stop the worker, kill it if it does not end, reap it and close its pipes (proved by recording every process a failing scenario started), and the embedder
     then answers `unavailable` and never restarts. A worker that refuses a request (too many texts, a text too long) is a refusal and stays up. A clean `close` ends the worker with exit code 0; one that ignores it is killed
     after two seconds.
  5. **How the six embedder failures map to Step 4's four retrieval failures** (Step 4's contract and its mirror in `eidos.state` are unchanged, and a test proves every embedder kind has a mapping):
     `unavailable`, `timeout`, `crashed` and `identity_mismatch` become `unavailable`; `malformed_reply` becomes `malformed_result`; `request_refused` becomes `request_mismatch`. A vector that is not of the model's
     dimension, not finite, of no usable length (outside 1e-100 to 1e100), a text within the window that came back without a vector, a text over the window that came back with one, and an answer that is not one embedded
     text for each text asked are `malformed_result`. **The gap raised in reading 5 is still open:** a chunk over the 128-piece window makes `open` return `unavailable` naming the first such chunk (canonical order),
     and a query over it is a `request_mismatch`; neither is truncated. A dedicated additive failure kind and its mirror in `eidos.state` remains the owner's alternative to decide.
  6. **The tests that need the real model** are `tests/integration/semantic/test_semantic_real_model.py` and `tests/scenarios/test_retrieval_benchmark_semantic.py`, marked `real_model` (no `pyproject.toml` change): deselected by
     default, selected with `-m real_model`, failing loudly and never skipping. The isolated interpreter is found as `EIDOS_SEMANTIC_PYTHON` or `py -3.13`, and the model directory as `EIDOS_SEMANTIC_MODEL_DIR` or the model
     library's local cache; both live only in `tests/support/eidos_semantic_benchmark.py`, and **no source file reads either**. Where production code finds them, and who owns the embedder's lifetime, is Open for Step 7.
  7. **Found by a test, not by reading.** The idle clock of a worker ran from the start of its process, so a worker that was slow to load could end before it was ready; it is now reset when the worker is ready, its
     limit must exceed the start time (the client validates that), and a test with a three-second load and a four-second idle time proves it. A test also caught a boolean posing as an integer id in a refusal.
     A benchmark helper that keyed embeddings by text collapsed the five mirrored chunks and miscounted the token pieces (min 15, 31 queries) in a first run; the count was corrected before anything was recorded from it
     (chunks 53 to 82 pieces, queries 11 to 36, all 89 texts counted).
  8. **An existing V1.2 guard had to be revised, for the owner to confirm.** `tests/unit/mcp/test_mcp_guards.py::test_the_mcp_package_is_the_only_place_that_starts_a_process` said that no file outside
     `eidos.mcp` may import `subprocess`. The ruled process boundary (ruling 2) needs a client that starts the worker, and the port and the worker cannot do it, so `eidos/knowledge/semantic_process.py` is now named in
     that guard as the one other place (`PROCESS_STARTERS`), and the test asserts the set of files that import `subprocess` outside `eidos.mcp` is exactly that one file, so a third place still fails it. The same
     file has its own, narrower guards in the knowledge guards (no model library, no socket, no clock, no state, no retrieval names). This is the only existing guard that was changed; the rest were extended, and
     the change is a narrowing of "only" to "exactly these two", not a removal. Whether a second process-starting place is acceptable is the owner's to confirm; if not, the adapter moves out of `src`.
  9. **Two assertions of mine were environment-dependent and were corrected when the tests were run under Python 3.13.1:** that importing `eidos.knowledge` loads no `subprocess` (Python 3.13's own libraries load
     it; the guard now asserts that no EIDOS process module is loaded, which is the claim) and that every EIDOS module imports with the model libraries blocked (the workflow and HTTP extras are not installed in 3.13,
     so a module that needs one is tolerated, and a blocked model library is still a failure).
- **Measured (2026-09-26; one machine, one day; the frozen fixture `93db0b1f14c7c444073f86c763e891f1ccab92e5259f62351305b374db57df6b`, unchanged; no parameter tuned; nothing judged):**
  - **Environment.** Main interpreter CPython 3.12.10 on Windows-11-10.0.26200-SP0 (Intel64 Family 6 Model 154 Stepping 3, GenuineIntel). The isolated interpreter `C:\Users\shrey\AppData\Local\Programs\Python\Python313\python.exe` is CPython
    3.13.1: torch 2.9.0+cpu, sentence-transformers 5.1.1, transformers 4.57.1, tokenizers 0.22.1, numpy 2.2.1; CPU, float32, one thread, evaluation mode. Model `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`, weights SHA-256
    `eaa086f0ffee582aeb45b36e34cdd1fe2d6de2bef61f8a559a1bbc9bd955917b`, directory SHA-256 `e99a362c5cdf060fe3dec4f42b61f3f847d80ce8881a8c716b3468bdf7ef03dc`; dimension 384, window 128 word pieces.
    Scheme id `semantic-cosine-v1/model=paraphrase-multilingual-MiniLM-L12-v2/rev=e8f8c211/dim=384/pieces=128`.
  - **Retrieval results (semantic; the same runner, metrics and gold labels as the lexical baseline).** Report digest `7dbab19fddd7f8a2c93751f5150214bf8d6cc9275e96ec33b68979a5996f2bf0` (the lexical report's is `f10840ecaf7642f1ffbb098e031ae165a2ae017f913577495766965214a822ff`). Test queries (30), macro-averaged
    and exact: Recall@1 149/225 = 0.6622, Recall@3 713/900 = 0.7922, Recall@5 749/900 = 0.8322, MRR 69/80 = 0.8625,
    source-coverage@1/3/5 109/180, 143/180, 151/180 = 0.6056, 0.7944, 0.8389; no query without a gold group in its ranking, and every query is
    ranked over all 53 chunks (every chunk is a candidate). Development queries (6, debugging only): Recall@1/3/5 7/10, 7/10, 11/15; MRR 61/72. Strata of the test queries (Recall@1, Recall@3, Recall@5, MRR):
    lexical overlap (8) 0.8750, 1.0000, 1.0000, 0.9375;
    paraphrase (10) 0.6500, 0.7500, 0.7500, 0.7750;
    multi-source (6) 0.1444, 0.3778, 0.5778, 0.7708;
    distractor bait (6) 0.9167, 1.0000, 1.0000, 1.0000.
    The lexical baseline it is set beside is unchanged (Step 4: Recall@1/3/5 0.4386, 0.4700, 0.5186; MRR 0.6344). **No retriever is called better, best, sufficient or rejected here; there is no threshold, margin or
    decision rule; the strata hold 6 to 10 queries each; the comparison and the decision are the owner's, at Step 6.**
  - **Semantic-specific facts.** The window: the 53 chunks are 53 to 82 word pieces and the 36 queries 11 to 36 (the two special pieces counted), so the token-piece rejection count on the fixture is
    0; on the real tokenizer a text of 400 words is 402 pieces and refused, a text of exactly 128 pieces (126 words) is embedded, and one of 129 is refused, none
    truncated. Worker start 30.4 s wall (library import 27.4 s of it, digest verification 0.60 s, model load 1.80 s); embedding the 53 chunks through the boundary
    8.39 s wall (8.33 s inside the worker, 157.2 ms a chunk). First query after the corpus 101.8 ms (of which 75.9 ms embedding, through the boundary). Warm full
    ranking over 53 chunks (180 samples): median 99.3 ms, p95 128.4 ms, max 158.4 ms; the embedding through the boundary median 72.9 ms (p95 101.7 ms),
    of which inside the worker median 71.4 ms; the port's own computation (cosine over 53 vectors, ordering, validation of the result) median 25.0 ms (p95 36.7 ms). The worker's peak
    working set 771 MB (728 MB after the model load), its peak page file 1331 MB; this process's Python allocations for the index and one pass of queries peaked at 830 kB. The model
    directory is 10 files, 479,729,010 bytes; the index is 20,352 numbers in memory and nothing on disk. The Hugging Face cache held 65 files before and 65 after: nothing was
    downloaded or written. **Two full harness runs are recorded and they differ:** the first, on an otherwise idle machine, gave a worker start of 11.0 s, corpus embedding 2.61 s, a first query of 32.2 ms and a warm median of 29.9 ms (p95 38.2 ms), peak working set 770 MB; the figures above are from the final run, made with the machine at about 42 percent load from other programs. Read the cost as an order of magnitude, not a measurement to two figures; the results, the ranks and the digests were identical in both. For scale, the lexical retriever's warm query median was about 2.2 ms and it loaded no third-party library (Step 4).
  - **Determinism, measured and no further.** In this environment the same 89 texts embedded twice in one worker, and once more in a second worker process, gave the same vectors bit for bit (0 and
    0 of 34,176 components differ), the same scores and the same ranking for every query, and the same report digest. The adjacent-score gaps of the 1872 adjacent pairs in the 36 full
    rankings: 180 are exact ties (the five mirrored chunks share a text, hence a vector, and are ordered by `chunk_id`), the smallest non-zero gap is 6.25e-06, 0 pairs are closer than 1e-6 and 21 closer than 1e-4.
    **Nothing is claimed for another machine, another library version or another CPU.**
  - **The thread and batch sensitivity experiment** (`tests/support/semantic_sensitivity_experiment.py`, run by hand in the isolated interpreter; the library's own default here is one thread because the worker's offline setup
    exports `OMP_NUM_THREADS=1`; this machine has 16 logical processors). Against the fixed configuration (1 thread, each text alone): repeating it, 89 of 89 texts bit-identical, 0 of 34,176 components differ, largest vector difference 0, largest score difference 0, 0 of 36 queries with a different chunk order, report digest identical; 1 thread and batches of 16, 7 of 89 texts bit-identical, 28,283 of 34,176 components differ, largest vector difference 3.4e-07, largest score difference 1.1e-07, 20 of 36 queries with a different chunk order, report digest identical;
    4 threads, 36 of 89 texts bit-identical, 18,372 of 34,176 components differ, largest vector difference 2.7e-07, largest score difference 1.2e-07, 0 of 36 queries with a different chunk order, report digest identical; 16 threads, 0 of 89 texts bit-identical, 30,683 of 34,176 components differ, largest vector difference 3e-07, largest score difference 1.5e-07, 0 of 36 queries with a different chunk order, report digest identical; 16 threads and batches of 16, 10 of 89 texts bit-identical, 27,245 of 34,176 components differ, largest vector difference 3.4e-07, largest score difference 1.5e-07, 20 of 36 queries with a different chunk order, report digest identical. So on this machine a change of thread count or batch shape moves vector bits
    by up to about 3.4e-7 and scores by up to about 1.5e-7, which is far below the smallest non-zero adjacent gap, and no configuration changed the report; a batch of 16 does change the chunk order of 20 queries, because
    the mirrored chunks land at different positions in a batch, get vectors that differ in the last bits and stop being exact ties: that, and only that, is why the model's batch is fixed at one.
  - **Tests and checks.** Default suite 6,704 passed and 31 deselected under `PYTHONHASHSEED=20260926` (was 6,278 at Step 4): 426 new tests (118 pure port, 77 worker,
    53 process client, 108 protocol against real worker processes, 11 integration: boundary and replay, 27 more guard cases). 29 `real_model` tests (worker start, identity,
    window, determinism, timeout, benchmark, cost) pass under Python 3.13.1 (29 passed) and passed under the main interpreter (27 in a first run, whose 28th test was my own mistake and was corrected into two, which then passed); the default semantic tests under 3.13.1: 642 passed, after two environment-dependent assertions of mine were corrected. The guards catch
    26 of 26 deliberate violations applied to an isolated copy (a model-library or process import in a pure module, a top-level library import in the worker, an `eidos` or `pydantic` import in the worker, the process client
    exported or imported, Qdrant or a cross-encoder named, a model dependency added to `pyproject.toml`, a module-level mutable, a wall-clock read, a retrieval or semantic name in the wrong module, a non-ASCII character, an
    unlisted module, a raise where a return is required). Mutation testing (an AST engine, isolated copies, only a failing assertion counts as a kill): the campaign was stopped at the owner's request and is NOT complete. First pass over the three new modules, 625 mutants: 595 were killed by a failing assertion; 9 more broke the module at import (killed at collection); 5 could not be classified by the harness's rule, because each crashed or hung the test run instead of failing an assertion (two negate the worker's `__main__` guard, one makes the worker's watchdog thread non-daemon, and two make the process client's `stop` skip its kill); 16 survived. Pure port (`semantic.py`, 138): 131 killed by assertion, 7 at import, 0 survivors. Worker program (259): 255 killed by assertion, 3 not classified, 1 survivor (the program name in its usage message), closed by a tightened test and re-verified killed. Process client (228): 209 killed by assertion, 4 not classified (two at import, two hangs), 15 survivors: 9 equivalent or unobservable (a validator's return value that pydantic ignores; an infinity check that the cross-field check already makes; a queue put after the pipe is closed; a falsy return; the read chunk size, two mutants; a constant that is only used where the platform lacks the attribute; a redundant `and` in `stop`, since simplified; and one timing-only race guard, the join of the stderr reader, which no test can make deterministic) and 6 closed by tests added afterwards, of which 2 were re-verified killed by a partial re-run and 4 were not re-run. Nothing else was re-run: the exact-message and non-ASCII tests that close the last four were written and pass, but were not proved against their mutants.
- **Still Open:** D-222 point 1 (the milestone label) and 7 (c) (the owner's review of the paraphrase queries); the admission part of D-222 point 5 (Step 7); D-223; D-224 readings 2 to 6 and 8 to 11; D-225 readings 12 to 16;
  D-204 to D-207. **D-222 point 7 (b) and point 8 are answered here** (ruling 1; readings 6 and 8). **Raised by Step 5, for the owner:** (a) the additive failure kind for "an input over the port's own window" (built as
  `unavailable` for a chunk and `request_mismatch` for a query; see Built 5); (b) where production code finds the isolated interpreter and the model directory, and who owns the embedder's lifetime (Step 7; Built 6);
  (c) the `WorkerLimits` defaults and the `INHERITED_ENVIRONMENT` names are fixed a priori and not tuned (Built 4), and are the owner's to change; (d) whether the worker's environment (interpreter, library versions, threads,
  precision) is to be recorded on a mission's log at Step 7, since only the scheme id (model, revision, dimension, window) is in a recorded retrieval fact today; (e) the index is derived, rebuilt at every `open` (about
  8.39 s after a 30.4 s worker start on this machine) and never persisted, per D-220; whether that is acceptable for a mission is a Step 6 and 7 question; (f) `trust_remote_code=False` and `local_files_only=True` are
  postures no test can observe on this complete, offline snapshot: they are read off the recorded calls only; (g) the revised V1.2 subprocess guard (Built 8). **Update (owner, 2026-09-26, with the Step 6 decision, D-227):** (a) is ruled: the Step 4 failure vocabulary stays and no new kind is introduced in Step 6; (g) is accepted exactly as narrowed (`eidos.mcp` and `semantic_process.py`), not to be broadened, the adapter not to be moved; (b), (d) and (e) are deferred to the later integration/production milestone and not implemented now; (c) and (f) remain Open.
- **Effect:** additive. Steps 2 to 4 (behaviour), `eidos.agents`, `eidos.state`, `eidos.recording`, the verifier, every V1.2 contract, the frozen fixture and benchmark and `pyproject.toml` are unchanged; the package root gained ten
  exports and the knowledge guards were revised deliberately (three retrieval modules, three semantic modules with narrower rules for the two that are not pure, and new guards for the boundary); the three semantic modules,
  their tests, the semantic measurement harness and the sensitivity experiment are new. Status of the readings: **still Open, none decided.**

### D-227 — V1.3 Step 6: lexical versus semantic comparison, and the human architecture decision (ACCEPTED 2026-09-26: the owner chose B, semantic retrieval; the lexical retriever stays behind the same port)

- **Status:** Accepted · **Date:** 2026-09-26 · **Decided by:** human owner (the decision below, given after the analysis). The analysis is Claude Code's and ranks nothing; the choice, the review of the paraphrase queries, the subprocess-guard acceptance and the deferrals are the owner's.
- **Source:** D-208, D-213 to D-215, D-220, D-222 (points 1 and 7), D-225, D-226 (ruling 1: no numeric pass/fail threshold, no automatic verdict); CLAUDE.md sections 0 and 7 and invariants 9, 13, 14 and 17.
- **Evidence used, and nothing else.** The lexical report of Step 4 (digest `f10840ecaf76...822ff`) and the semantic report of Step 5 (digest `7dbab19fddd7...2bf0`), both over the frozen fixture (digest
  `93db0b1f14c7c444073f86c763e891f1ccab92e5259f62351305b374db57df6b`, snapshot `b76e15e080ad...`, 53 chunks, 36 queries: 30 test and 6 development), and the cost and determinism measurements recorded in D-225 and D-226. The two saved
  reports were re-hashed and match the recorded digests. **Nothing was re-run, rebuilt, tuned or changed**: no fixture, gold label, query, chunking, model, parameter or code.
- **Measured fact 1: the results** (test queries, macro-averaged, each cell lexical / semantic; SC = source-coverage; exact fractions are in D-225 and D-226; no significance test exists and none is claimed):

| Test queries | n | R@1 | R@3 | R@5 | MRR | SC@1 | SC@3 | SC@5 |
|---|---|---|---|---|---|---|---|---|
| **all test queries** | 30 | 0.4386 / 0.6622 | 0.4700 / 0.7922 | 0.5186 / 0.8322 | 0.6344 / 0.8625 | 0.4056 / 0.6056 | 0.5000 / 0.7944 | 0.5500 / 0.8389 |
| lexical overlap | 8 | 1.0000 / 0.8750 | 1.0000 / 1.0000 | 1.0000 / 1.0000 | 1.0000 / 0.9375 | 0.9375 / 0.8125 | 1.0000 / 1.0000 | 1.0000 / 1.0000 |
| paraphrase | 10 | 0.0000 / 0.6500 | 0.0000 / 0.7500 | 0.1000 / 0.7500 | 0.0782 / 0.7750 | 0.0000 / 0.6000 | 0.0000 / 0.7500 | 0.1000 / 0.7500 |
| multi-source | 6 | 0.1931 / 0.1444 | 0.3500 / 0.3778 | 0.4264 / 0.5778 | 1.0000 / 0.7708 | 0.2778 / 0.1944 | 0.5000 / 0.3889 | 0.5833 / 0.6111 |
| distractor bait | 6 | 0.6667 / 0.9167 | 0.6667 / 1.0000 | 0.6667 / 1.0000 | 0.7083 / 1.0000 | 0.5000 / 0.7500 | 0.6667 / 1.0000 | 0.6667 / 1.0000 |

  The 6 development queries (debugging only) are in D-225 and D-226 and are not used here.
- **Measured fact 2: per query** (test queries; first-ranked gold group, lexical / semantic; a lower rank is earlier): L01 1 / 1; L02 1 / 1; L03 1 / 2; L04 1 / 1; L05 1 / 1; L06 1 / 1; L07 1 / 1; L08 1 / 1; P01 11 / 8; P02 23 / 1; P03 12 / 1; P04 47 / 1; P05 23 / 8; P06 5 / 1; P07 38 / 1; P08 17 / 2; P09 7 / 1; P10 14 / 1; M01 1 / 2; M02 1 / 1; M03 1 / 1; M04 1 / 1; M05 1 / 1; M06 1 / 8; B01 1 / 1; B02 1 / 1; B03 6 / 1; B04 12 / 1; B05 1 / 1; B06 1 / 1. Counting the 30 test queries: a gold group is ranked first by the lexical retriever
  for 18 and by the semantic retriever for 24; by both for 15, by the lexical only for 3 (L03, M01, M06), by the semantic only for 9 (P02, P03, P04, P06, P07, P09, P10, B03, B04) and by neither for 3 (P01, P05, P08: all paraphrase queries); the
  first gold group is ranked earlier by the lexical for 3 (L03, M01, M06), earlier by the semantic for 12 (10 paraphrase, 2 distractor bait) and at the same rank for 15. In the multi-source stratum the lexical
  retriever ranks a gold group first for all 6 queries and its per-query Recall@5 is higher for M01 (2/3 against 1/3) and M06 (3/8 against 0); the semantic one has the higher Recall@5 for M02, M03 (5/6 against 1/6) and M05 (1 against 1/4).
  For M06 ("Which documents describe the duty engineer's tasks?", 8 gold groups) the semantic retriever ranks the gold groups at 8, 9, 17, 18, 22, 29, 34 and 42. Its two clear wins outside the paraphrase stratum are the distractor-bait queries B03 and B04, where the lexical
  retriever's first gold group is at rank 6 and 12.
- **Measured fact 3: cost, dependencies and determinism** (one machine, Windows 11, AMD64, Intel64 Family 6 Model 154; the lexical figures are Step 4's, the semantic ones are two full harness runs that differ by about 3 times, the first on an idle machine and the final with the machine at about 42 percent load from
  other programs, so read every semantic cost as an order of magnitude):

| | Lexical (`lexical-bm25-v1`) | Semantic (`semantic-cosine-v1`, MiniLM, 384 dimensions) |
|---|---|---|
| Runs in | the main Python 3.12 process | a separate isolated Python 3.13.1 worker process, minimal environment, bounded, typed failures |
| Third-party dependencies | pydantic only (already required) | torch 2.9.0+cpu, sentence-transformers 5.1.1, transformers 4.57.1, tokenizers 0.22.1, numpy 2.2.1 in the isolated interpreter (about 0.8 GB of packages), not declared in `pyproject.toml`; a cached model of 479,729,010 bytes in 10 files |
| Start | interpreter and imports about 750 to 790 ms cold; the index builds in about 2 to 3 ms | worker start 11.0 s idle and 30.4 s under load (library import 9.5 s, digest verification 0.5 s, model load 0.8 s, idle run); embedding the 53 chunks 2.6 s idle |
| Warm query (full ranking of 53 chunks) | median 2.2 ms, p95 3.1 ms, max 6.6 ms | median 29.9 ms idle (p95 38.2) and 99.3 ms under load: about 14 to 46 times the lexical median |
| Memory | Python allocations peaked at 280,749 bytes | the worker's peak working set about 770 MB; this process's allocations about 830 kB |
| What a query returns | only chunks that share a term with the query; an empty result is possible and is a real result | every chunk, ranked: always a full ranking, never empty; a score is a cosine, not a confidence |
| Determinism measured | exact decimal arithmetic; the report was identical under four hash seeds and any document order (Step 4); independent of the platform's math library by construction; not measured across machines | the same 89 texts gave bit-identical vectors, scores and reports across repeated runs and two worker processes on this machine, with the execution configuration fixed (one thread, each text alone); other thread counts or batch shapes moved vector bits by up to about 3.4e-7 and no report; the smallest non-zero gap between adjacent scores is 6.2e-06; not measured across machines |

- **Interpretation (mine: an interpretation is not a decision rule, and none exists).**
  1. On this fixture the difference between the two is concentrated in the paraphrase stratum, where the lexical retriever ranks no gold group first (0 of 10; its first gold group is at ranks 5 to 47) and the semantic retriever ranks one first for 7 of 10; 10 of the 12 test queries where the
     semantic retriever is ahead are paraphrase queries. In the lexical-overlap stratum the two agree on 7 of 8 queries. In the multi-source and distractor strata the results are mixed and depend on the metric: the lexical retriever has the higher Recall@1 and MRR for multi-source and the semantic
     one the higher Recall@3 and Recall@5, and for distractor bait the semantic retriever is ahead on every metric shown. Each of these strata holds 6 to 8 queries, so one query moves a stratum's Recall@1 by up to 0.125 to 0.167.
  2. The two retrievers fail on different queries: for 27 of the 30 test queries at least one of them ranks a gold group first, and the 3 where neither does are all paraphrase queries. This is an observation about the queries, not a measurement of any combination of the two, and no
     combination was built or measured.
  3. The lexical retriever's visible failure is vocabulary mismatch (the paraphrase stratum, and the two distractor-bait queries B03 and B04 where other passages share the query's words). The semantic retriever's visible shortfalls are three queries: L03 (a lexical-overlap query for a
     vendor and a lead time, gold group at rank 2) and the multi-source queries M01 and M06, about a named role (the shift supervisor, the duty engineer), where it ranks a gold group second and eighth. A reading that this benchmark does not establish is that queries built on specific terms
     that many passages contain are where exact-term matching helps.
  4. The semantic retriever's costs are an order of magnitude or more above the lexical retriever's in start-up, latency, memory and dependencies, and it needs a second interpreter and a process boundary. That boundary is bounded and typed, but it required narrowing one V1.2 guard (only `eidos.mcp`
     may start a process) which the owner has since accepted (see the decision below; D-226 Built 8).
  5. Invariant 13 (never manufacture confidence) bears on the two behaviours in the table: a lexical retriever can say that nothing shares a term, and a semantic ranking never does. **The benchmark contains no query whose answer is absent from the corpus, so neither behaviour is measured.**
- **Unresolved questions (not answered by this benchmark).** (a) How each behaves on a query with no answer in the corpus. (b) Whether a hybrid or fallback rule would keep the lexical retriever's strengths and the semantic retriever's, and which rule: no rule was designed, and the 6 development queries are too few to
  tune one. (c) How a stemmed, stop-listed or otherwise tuned lexical retriever, or a different or larger embedding model, would compare: only one untuned lexical scheme and one small model were measured. (d) Whether the paraphrase stratum represents real paraphrase: its 10 queries and
  their gold labels were authored by Claude Code, and **the owner's review of them (D-222 point 7 (c)) was still owed when this analysis was written; it is answered below.** (e) Whether retrieval quality on this fixture predicts answer quality, verification outcome or evidence sufficiency downstream: nothing here measures those.
- **What this benchmark does NOT establish.** Universal superiority of either retriever; performance on a real or larger corpus, on other domains or languages (the fixture is English, fictional, 12 documents, 53 chunks of at most 60 words, 30 test queries); production latency, throughput or cost;
  cross-machine or cross-version bit identity (measured on one machine only); any statistical significance (no test was run, strata hold 6 to 10 queries); robustness to adversarial or malformed queries; retrieval of chunks longer than the model's 128-piece window; the behaviour of any other model,
  parameter setting, fusion rule or reranker; anything about Research integration, the verifier or the reliability contract.
- **The choices (unranked; the order is only A, B, C).**
  - **A. Lexical only.** *Evidence for:* the higher results in the lexical-overlap stratum (Recall@1/3/5 and MRR all 1.0; one query, L03, ranked first that the semantic ranks second) and the higher MRR in the multi-source stratum (1.0 against 0.7708); the lower cost (more than an order of magnitude on warm latency and on start-up), no third-party dependency
     beyond pydantic, in process; exact decimal arithmetic, so its scores do not depend on the platform's math library; an empty result when nothing matches. *Evidence against:* Recall@1 0.0 and Recall@5 0.1 in the paraphrase stratum, and lower Recall on the distractor-bait stratum (Recall@1 0.6667
     against 0.9167); overall Recall@1/3/5 and MRR below the semantic numbers. *Cost and complexity:* already built. *Determinism:* exact and platform independent by construction; measured invariant under hash seeds and document order; not measured across machines. *Dependencies:* none new. *Failure modes visible here:* a query in other words than the
     passage (P01 to P10; B03 and B04 where bait passages share the query's words).
  - **B. Semantic only.** *Evidence for:* higher overall Recall@1/3/5, MRR and source-coverage on the 30 test queries, concentrated in the paraphrase and distractor-bait strata (Recall@1 0.6500 in the paraphrase stratum). *Evidence against:* lower Recall@1 and MRR than the lexical
     in the multi-source stratum, one lexical-overlap query ranked second (L03), the M06 result (Recall@5 0), no measurement of an absent-answer query, and always a full ranking. *Cost and complexity:* built, but it needs the isolated 3.13 interpreter and model outside the declared dependencies, a process boundary, a subprocess-guard revision
     (accepted by the owner, see below), a production answer for where the interpreter and model live and who owns the embedder's lifetime (D-226, Step 7), and a decision on rebuilding the index at every open. *Determinism:* repeatable on this machine in a fixed configuration, sensitive to thread and batch settings at about 3e-7 in the
     vectors, unmeasured across machines. *Dependencies:* the heaviest. *Failure modes visible here:* L03, M01 and M06 (see interpretation 3), and a full ranking for every query.
  - **C. Hybrid or fallback** (any rule that uses both). *Evidence for:* the two retrievers rank a gold group first on different queries (27 of 30 covered by at least one; the 3 misses all paraphrase). *Evidence against:* nothing measured supports any particular rule: no fusion or fallback rule exists, none was measured, the
     development set is too small to choose one and the test set may not be used to tune. *Cost and complexity:* all of B's costs and dependencies plus a rule to design, justify and measure, on a fixture that would need to be extended for the purpose. *Determinism:* the lexical part is exact, the semantic part as in B, and the
     rule adds its own; the whole is only as reproducible as its least reproducible part. *Dependencies:* those of B. *Failure modes visible here:* none can be read from this benchmark, because no combination was measured; the failures of each part are listed above.
- **The 10 paraphrase test queries, for the owner's review under D-222 point 7 (c)** (P01 to P08 and P10 each have one gold passage in the frozen fixture; P09 has two, the passage and its restatement under a source that declares nothing; the passages are in `tests/support/eidos_retrieval_fixture.py`):
  - P01: Which paperwork must the person on watch fill in for each machine housing prior to bringing the plant back into service?
  - P02: During a severe weather closure, which comes earlier, sealing the sea wall openings or halting the power generators, and how long does each opening take?
  - P03: How much warning must the plant give the electricity network company ahead of returning a generator onto the wires after a stoppage?
  - P04: Which standby luminaires beside the steps by the water did not survive the long battery trial, and what was fitted afterwards?
  - P05: How long can a broached barrel of transmission lubricant stay in use before it is thrown away, and where are the barrels kept?
  - P06: Which outside worker walked into a machine chamber lacking authorisation and was led away, and whose sign-off is required to go in?
  - P07: After a severe weather alarm, where do employees who are not vital gather, and who tells the port authority to halt boat traffic?
  - P08: What limits how much electricity may be sent out before a second manager endorses the log after several machines are running?
  - P09: When are the stoppages for maintenance arranged to coincide with the gentlest current, and how early is the programme made public?
  - P10: What is the highest amount of power the site can send to the network, and how quickly must it stop sending when told to by the network company?
- **The questions put to the owner (answered below; the analysis above is unchanged).**
  1. **Choose the architecture:** A, B, C, or another option, and say which evidence carries the weight. Nothing here should be read as a recommendation.
  2. **Review the paraphrase queries** above and say whether they are acceptable as the paraphrase evidence, or what is to be changed (a change is a new frozen fixture and a new run, not an edit of this one).
  3. **If B or C:** confirm or reject the narrowed subprocess guard (D-226 Built 8); if C, say what "hybrid or fallback" is to mean (for example which retriever is asked first and what triggers the other, or a fusion of both rankings) and what measurement would be accepted for it, since no rule exists yet.
  4. **If A:** say whether the semantic modules, worker and harness stay in the repository as an unused, tested capability or are removed (they are built, tested and committed at Step 5).
- **The owner's decision (2026-09-26, given after the analysis; it supersedes nothing above and changes no number):**
  1. **Architecture: B.** Semantic retrieval is the selected V1.3 retrieval capability. The owner's stated reasons, all from the measurements recorded above: the semantic retriever has the higher overall Recall@1/3/5 and MRR on the
     30 test queries; its largest measured advantage is on the paraphrase queries; the lexical retriever remains substantially cheaper and lighter; and no hybrid rule has been measured, so none is introduced. **This is an MVP architecture
     decision, not a claim that semantic retrieval is universally better**, and the limits listed under "What this benchmark does NOT establish" stand.
  2. **The lexical retriever stays**, implemented and tested, behind the same `KnowledgePort`: the Step 4 code, its tests, its frozen baseline and the benchmark are kept and are not deleted or changed. **No hybrid or fallback policy is built** (choice C
     is not taken), and no reranker, ANN, Qdrant or cross-encoder is added.
  3. **Paraphrase queries P01 to P10: accepted** as the current paraphrase evidence for this benchmark, with the small-sample caveat and the caveats in the review below. None was edited and the benchmark was not re-run.
  4. **Subprocess guard: accepted**, exactly as narrowed at Step 5 (D-226 Built 8): `eidos.mcp` and `eidos/knowledge/semantic_process.py` are the only two places that may import `subprocess`, each for its own process boundary. The exception is not to be
     broadened, and the adapter is not to be moved merely to preserve the old guard.
  5. **Over-window failure kind: the Step 4 failure vocabulary stays for now** (a chunk over the window is `unavailable`, a query over it is `request_mismatch`). No new failure kind is introduced in V1.3 Step 6.
  6. **Deferred to the later integration/production milestone and not implemented now:** how production code finds the isolated interpreter and the model directory (and who owns the embedder's lifetime), whether and how the worker's environment
     is recorded on a mission's log, and whether the index is persisted.
  7. **Not started:** Step 7 (Research integration, the gate and admission), and any change to the retrieval architecture or to the benchmark.
- **Review of the paraphrase queries P01 to P10 (done at the owner's instruction, 2026-09-26: read-only, nothing edited, no retrieval, model or benchmark run). Result: no flaw that invalidates the stratum was found; accepted with the caveats below.**
  What was checked. (a) The stratum's defining rule holds for all 12 paraphrase queries (10 test, 2 development): none shares a content token with any of its gold chunks, by the fixture's own `content_tokens` rule, which its default-suite test also asserts.
  (b) Each gold passage states the answer to every part of its question (7 of the 10 test queries ask two things: P02, P04, P05, P06, P07, P09, P10). (c) The answer-bearing facts (for example "six minutes", "ninety days", "KR-IR-32", the one-third export limit
  until the counter-signature, "fourteen megawatts", "a month ahead") occur only in the labelled gold chunks, apart from the byte-identical mirror of P04's passage under `archive` (the same gold group) and the restatement under `outreach` that P09 labels as its second
  gold group. (d) The non-gold chunks that share a fact's words do not answer the question (P01: the grid call is logged on the reverse of Form KR-14; P03: the storm-shutdown estimate is updated every thirty minutes; P10: a turbine is stationary for two minutes before
  its hatch is sealed; the `outreach` notices that mention gates, permits, the lodge or the harbourmaster are about a car park, a barbecue and tours), so no unlabelled answer was found.
  **Caveats, not flaws.** Ten test queries is a small sample. All ten were authored by Claude Code together with the fixture. Some substitutions are deliberately unnatural ("machine housing", "sea wall openings", "luminaires"). And because the stratum is *defined* to have
  zero content-token overlap with its gold, the lexical retriever's failure there (Recall@1 0.0, Recall@5 0.1: its gold chunks can match only on words of the fixed stop list, which the lexical scheme does not remove) is largely a consequence of that rule. The stratum therefore shows
  how each retriever behaves under complete vocabulary substitution; it does **not** show the size of the advantage on ordinary paraphrased queries, which usually keep some words. It is accepted for what it measures.
- **Effect:** none on code, tests, fixtures, benchmark or dependencies: this entry is documentation only, and nothing was run, built or changed at Step 6. It selects the semantic retriever as the V1.3 retrieval capability for the MVP, retains the lexical retriever behind the
  same port, and defers the production questions listed above. It changes D-226's open items as recorded in D-226's update, and answers D-222 point 7 (c). **Step 7 has not started.**
- **V1.4 (2026-09-26, D-234):** not reopened. Semantic retrieval stays available behind `KnowledgePort`; its production wiring (interpreter and model paths, worker lifetime, worker-environment logging, index persistence) stays deferred, and V1.4 ships no knowledge base at all: the owner ruled on 2026-09-27 that knowledge stays optional, with no production knowledge-base choice in V1.4 (the static lexical knowledge base of the V1.4-A proposal is not built).

### D-228 — V1.3 Step 7: Research integration and one end-to-end RAG mission; the readings taken and the conflict found (PARTLY RULED 2026-09-26: the four issues decided)

- **Status:** Partly ruled, partly Open · **Date:** 2026-09-26 · **Raised by:** Claude Code, before coding Step 7 · **Decided by:** human owner, 2026-09-26, for the four issues D-228.1 to D-228.4 below (given after the Step 7 decision surface was presented). The ten readings below are Claude Code's, are the smallest implementation, live in one place, and are **not separately confirmed** (they stay Open, none blocking). The owner's Step 7 brief (below) is recorded as given.
- **Source:** the owner's Step 7 brief (2026-09-26); D-208 to D-227 (D-208 item 5 and D-209 for the frozen contracts and the additive verification change, D-216 and D-217 for the bounds and the query, D-218 and D-225 reading 9 for recording, D-222 point 5 for admission, D-224
  readings 10 and 11 for the boundary and what waits for Research, D-227 for the chosen retrieval); docs/03 (`ResearchAgent -> KnowledgeAccess / KnowledgeGate -> KnowledgePort`); CLAUDE.md sections 0, 3, 7 and invariants 1, 2, 3, 6, 9, 11 to 16.
- **The brief (2026-09-26):** integrate the existing `KnowledgePort`, retrieval, evidence and recording architecture into the Research execution path and demonstrate one bounded end-to-end mission: Mission, Research, `KnowledgePort`, semantic retrieval, `EvidenceLedger`, a cited research
  result, the existing verification, the mission result. Research depends on the port and the evidence-facing contracts, not on the semantic implementation; retrieved evidence enters the existing ledger with deterministic provenance; the citation and provenance contracts, the recorded retrieval
  facts and citations (as designed) and `MissionState` authority are preserved; replay audits the recorded facts without a worker, a model or a retrieval; failure paths are tested; the implementation is model independent. **Not in scope:** Qdrant, a hybrid or fallback, reranking, ANN, another
  agent, a redesign of strategy selection or of verification, production interpreter or model discovery, worker lifetime management, index persistence, mutation testing unless an existing criterion requires it, background polling, a push.
- **What is inspected and found (facts):** (1) `ResearchAgent` already takes an optional, admission-gated `ToolAccess` and works from `store.supplied(execution_id)`; a retrieved tool document becomes a supplied artifact under a citable reference and the verifier's rules run over the store. (2) `EvidenceLedger`
  and `EvidenceRecord` exist and are fed by nothing yet. (3) `RetrievalFacts`, `citations`, `RecordingKnowledgePort`, `RecordingCitations`, `audit_evidence` and replay exist and already resolve a citation `evidence:<16 hex>` to the recorded hits across every step of an execution. (4) The agents import guard
  allows exactly one module, `evidence_ledger.py`, to import `eidos.knowledge`, with a pinned name set, and says a later step adds names on purpose (D-224 reading 10). (5) The V1.2 verifier's `minimum_distinct_sources` counts distinct **supplied references**, and a stored chunk is one reference.
- **Readings taken (Open, none blocking):**
  1. **The seam.** A new agents module `knowledge_gate.py`: the protocol `KnowledgeAccess` (`retrieve(context, query) -> KnowledgeGateOutcome`, total: every outcome is returned, none raised) and its implementation `KnowledgeGate`, beside `ToolAccess` and `ToolGate` (docs/03). Research depends on `KnowledgeAccess` only,
     optionally, exactly as it does on `ToolAccess`: an agent built without it behaves as it always did. Only the gate and the ledger import `eidos.knowledge`, from its root, by name; no agents module names a retriever, an embedder, a model or a process, so the semantic (or lexical) port is injected where the mission
     is assembled.
  2. **`KnowledgeBaseDescriptor`** (the D-225 name): `kb_id`, the pinned `snapshot`, `scheme_id`, `top_k` and `max_result_bytes`. It is the per-knowledge-base configuration of D-216. The gate builds the `RetrievalRequest` from it, so an agent cannot state or raise a bound or name another snapshot or scheme.
  3. **The query** is the mission goal, `goal.strip()`, verbatim as V1.2 and D-225 reading 2 take it (canonicalised by `RetrievalRequest`); one query per Research run; an empty goal makes no retrieval, as in V1.2.
  4. **How retrieved evidence enters (deterministically).** Each hit becomes an `EvidenceRecord` (`evidence_from_snapshot`, so a chunk the snapshot does not hold is refused) recorded in the `EvidenceLedger` (the same chunk again keeps one record and adds the query id, D-209), **and** the chunk's text is stored once as a **supplied artifact
     under its evidence reference** (`evidence:<16 hex>`, `text/plain`), exactly as the V1.2 gate stores a tool document. The ledger is the authority for provenance and independence; the artifact is what the model reads and what a citation resolves to, so the existing citation and verification contracts
     work unchanged. The same evidence stored by two queries is one artifact (an identical text is reused; a different text under the reference is refused).
  5. **A duplicate query.** The same `query_id` again in one execution (a second Research step, or a replanned attempt) is answered from the stored answer: no port call, no ledger change, no artifact written. The `served_stored` retrieval outcome that D-225 reading 7 said would join the vocabulary is **not added**: the serving node records no retrieval
     fact of its own, and its citations still resolve to the hits the first node recorded (the audit works across the whole execution record). A failed retrieval is not stored, so a repeat asks the port again.
  6. **Admission: none beyond the descriptor.** The admission part of D-222 point 5 (a ceiling on queries per execution, a denial vocabulary, a typed denial for an exhausted bound) **stays Open and nothing is built for it**: with the goal as the only query and duplicates served, one execution makes at most one distinct retrieval, bounded by
     `top_k` and `max_result_bytes`. The `denied` outcome of D-225 reading 7 is not added. This needs revisiting the moment any agent forms a second distinct query.
  7. **How Research reads a failure.** As it reads a tool's: an `unavailable` retrieval means the work did not complete (`FAILED`); a mismatch, an oversize or malformed answer, and an empty answer mean it completed and produced nothing usable (`NO_RESULT`); either only when there is no document to work from. If documents exist (supplied, from a tool or from
     knowledge) it works from them.
  8. **Recording is unchanged.** The composition wraps the port in the existing `RecordingKnowledgePort` and Research's node in the existing `RecordingCitations`; the gate is the only caller of the wrapped port ("the seam moves to the gate", D-225 reading 9). `eidos.state`, `eidos.recording` and `MissionState` are not changed.
  9. **The guards are revised deliberately, not weakened:** the agents guard names two boundary modules, each with its own pinned set of names from the package root; the knowledge guard lists the gate beside the ledger as an importer.
  10. **The demonstration.** A mission (Research, then Analysis, then the existing verification) whose Research node retrieves through the gate. The default suite runs it over `SemanticKnowledgePort` with the real process boundary and a stub model (no model library) and over the lexical port (to show Research does not care which); one opt-in `real_model` run
     uses the real pinned model on the frozen fixture with a **development** query, never a test query. The model is a scripted `ModelPort`, as in every earlier scenario, so nothing in the path is model dependent.
- **The conflict found (decided as D-228.1, below):** **the existing verification over-counts independent evidence for retrieved knowledge.** Its `minimum_distinct_sources` counts distinct supplied references, and each stored chunk is one, so three chunks of one document, or a chunk and its byte-identical mirror, satisfy `min_independent_evidence = 3` while D-209 says they are fewer
  independent sources. D-209 and D-208 item 5 authorise an additive, optional, resolver-backed change to the verifier ("an absent resolver leaves the verifier's behaviour byte-identical"), and the earlier ladder named "the verifier wiring" in Step 7, but the brief says to use the existing verification and not to redesign it, so **nothing in the verifier is changed.** The independent-source count
  is computed beside the verdict from the ledger and the audit and reported by the scenario, and a test pins the over-count as a known, named limitation. **Decided by the owner (D-228.1, 2026-09-26):** the V1.2 count is accepted for retrieved knowledge as a V1.3 limitation; the resolver is kept available and is not wired into the verifier in V1.3. Until then a mission verified on retrieved chunks means the V1.2 rules passed, not that
  `min_independent_evidence` independent sources were reached.
- **Owner decisions (2026-09-26), recorded as given: D-228.1 to D-228.4.**
  - **D-228.1 Evidence independence.** Classification: known limitation. Choice: **A, leave it and accept it as a V1.3 limitation.** Do not modify verification semantics. Do not integrate `EvidenceLedger.resolve_independence()` into `VerificationAgent` in V1.3. Keep the resolver available for a later verifier/evidence milestone. No tests approved for change.
  - **D-228.2 Citation coverage.** Classification: known limitation. Choice: **A, leave it; `audit_evidence` remains the current traceability check.** Do not make `citation_coverage` transitive. Do not change VERIFY plan dependencies. Do not add evidence entailment/support judging. No tests approved for change.
  - **D-228.3 Port exception recording.** Classification: known limitation / broken-contract edge case. Choice: **A, leave it and document it.** Supported `KnowledgePort` implementations must return typed `RetrievalFailure` outcomes. Do not add port-level or gate-level exception recording in V1.3. Do not introduce a second recording seam. No tests approved for change.
  - **D-228.4 Query ceiling.** Classification: deferred. Choice: **A, leave Open until a second distinct query can actually exist.** Do not add `max_knowledge_queries` or another knowledge budget in V1.3. The current Research path is bounded to one query per run by construction. Revisit admission/query budgeting when multiple distinct knowledge queries become possible. No tests approved for change.
- **What the four decisions settle (Claude Code's reading, for the record):** (1) The V1.2 count stays the verifier's rule for retrieved chunks: a mission verified on retrieved chunks means the V1.2 rules passed, not that `min_independent_evidence` independent sources were reached (the verdict's own reason already says it is not a claim that the reliability contract is satisfied). The ledger, the D-209 resolver and `audit_evidence` stay available and unwired. `test_known_limitation_the_existing_verification_counts_stored_chunks...` stays as it is; it is the test a later verifier milestone would change on purpose. (2) `audit_evidence` is the traceability check; `test_known_limitation_a_citation_nobody_retrieved_in_the_research_artifact...` stays as it is. (3) The typed-failure rule is already the `KnowledgePort` contract ("total: a failure is returned, never raised", `eidos/knowledge/retrieval.py`); `docs/09` now says it. The recording seam stays the single port-level `RecordingKnowledgePort` of reading 8: the ruling adds none and does not separately confirm reading 8, and D-225 reading 9's wording ("the seam moves to the gate") stays a reading. (4) The admission part of D-222 point 5, and the `served_stored` and `denied` outcomes of D-225 reading 7, are deferred until a second distinct query can exist. No test was approved for change, and none was changed.
- **Still Open:** the ten readings above (taken, not separately confirmed); D-222 point 1 (the milestone label); D-223 to D-226 readings not ruled. **Deferred by D-228 (owner, 2026-09-26):** the admission part of D-222 point 5 and the `served_stored` and `denied` retrieval outcomes (D-228.4); wiring the D-209 resolver into the verification (D-228.1, for a later verifier/evidence milestone). **Deferred by the owner (D-227) and not touched:** production discovery of the interpreter and model, worker lifetime, worker-environment logging, index persistence.
- **Built (2026-09-26, Step 7):** `eidos.agents.knowledge_gate` (`KnowledgeBaseDescriptor`, `KnowledgeGateKind`, `KnowledgeGateOutcome`, `KnowledgeAccess`, `KnowledgeGate`); `ResearchAgent` takes an optional `knowledge: KnowledgeAccess | None`; the agents package exports the six names. The agents guard now pins
  two boundary modules by name (`evidence_ledger.py`, `knowledge_gate.py`) and asserts that Research imports nothing from `eidos.knowledge` and names no retriever, embedder, subprocess, worker or model library; the knowledge guard lists the gate beside the ledger and its ASCII list covers the new files.
  Tests: 43 for the gate (`tests/unit/agents/test_agents_knowledge_gate.py`), 20 for Research with knowledge (`test_agents_research_knowledge.py`), and the scenario `tests/scenarios/test_rag_mission.py` (36 tests: the mission tests run over the semantic retriever behind the real process boundary, the real worker
  program over a stub model, and over the lexical retriever; the failure paths; a duplicate query; determinism; replay with a process, a socket, the retriever, the gate and the worker made impossible, and in a fresh interpreter with the retrieval stack and every model library unimportable; and two named
  known-limitation tests). One opt-in `tests/scenarios/test_rag_mission_real_model.py` (`-m real_model`, three tests) ran once on 2026-09-26 in this environment and passed in about 17 seconds: the real pinned model on the frozen fixture with development query LD1 ("When is an Amber Watch declared?"); the gold chunk was the
  rank-1 hit on that one run, which is printed as an observation and never asserted, and is not a measurement of retrieval quality. Test support: `eidos_knowledge_gate_fixture.py`, `eidos_rag_rig.py` (the composition) and `eidos_replay_story.py` (the fresh-interpreter replay, moved out of the Step 5 replay test, which now imports it;
  its behaviour is unchanged and it now also compares the replayed state's digest). Three deliberate tampers of the gate (no ledger write, no duplicate serving, an answer trusted) were each caught by the scenario. Mutation testing was not run: no existing acceptance criterion requires it and the brief said not to start it.
- **Observations for the owner (raised, not decided; none blocks Step 7):** (1) **The verifier over-count is demonstrated, not only argued.** The lexical retriever answers the fixture goal with six chunks from four independent sources; a contract requiring five is passed by the existing verification
  ("6 distinct supplied source(s) reached, 5 required") and the mission completes verified, while the ledger and the D-209 resolver say four. Pinned by `test_known_limitation_the_existing_verification_counts_stored_chunks...`. (2) **`citation_coverage` is not transitive.** It checks what the artifacts it is handed cite, and it is handed the
  analysis; a citation nobody retrieved in the research artifact passes verification and is named only by `audit_evidence` (`unresolved`). Pinned by `test_known_limitation_a_citation_nobody_retrieved_in_the_research_artifact...`. The audit is where invariant 16 is checked; verification does not check it. (3) **A port that raises records no
  retrieval fact.** Both real retrievers return typed failures, so this concerns only a port that breaks its contract: the recording wrapper sits inside the gate and passes an exception through untouched (D-218), and the gate turns it into an `unavailable` outcome afterwards, so only the node's reason names it. Options: leave it, or have the gate
  note the failure. Not changed. (4) **No `served_stored` and no `denied` outcome, and no admission ceiling** (readings 5 and 6, unchanged): with the goal as the only query a mission makes at most one distinct retrieval, so this must be revisited before any agent forms a second distinct query. (5) **The default suite proves the path
  with a stub model**; only the opt-in run uses the real model, and it judges nothing about quality (that is the benchmark's, on the frozen test queries).
- **Observations, as decided (2026-09-26):** observation (1) is D-228.1, (2) is D-228.2, (3) is D-228.3 and (4) is D-228.4; observation (5) is not one of the four and stays an observation.
- **Close-out correction (Step 8, 2026-09-26): the gate was mutation tested.** The statement above that no existing criterion required mutation testing of the gate was an under-reading. The owner's V1.3 testing requirement makes mutation testing mandatory for the deterministic core components, on isolated copies, and Step 3 applied it to `eidos.agents.evidence_ledger`, a module of the same package; the gate is a module of that kind. One bounded pass was therefore run at Step 8 on an isolated copy (47 mutants of `knowledge_gate.py` and the Research knowledge path; the repository was not written: its fingerprint is identical before and after): **40 of 47 caught by a real test failure (pytest exit 1); 7 survived and are recorded, not chased.** Two are equivalent (the descriptor's `top_k` and `max_result_bytes` lower bounds, which `RetrievalRequest` enforces again when the descriptor validates itself). Two are defences reachable only through a concurrent writer to the same ledger or store, so no single-thread test can observe them (the second ledger refusal, which the first pass already makes unreachable, and the artifact-conflict handler, which the get-before-put already makes unreachable). One is the lock itself: the concurrent test asks with twelve threads, but a scripted port returns too fast to force an interleaving. **Two are real test gaps, recorded and not closed, because the owner asked for a documentation-only close-out (no test was added):** (a) a refused admission (an answer the store or the ledger refuses) is not shown to be left unstored, so that a repeat asks the port again (only a failed port answer is shown), and (b) all-or-nothing is not shown for a ledger refusal on a later hit of a multi-hit answer (a single refused hit is refused identically by the second pass). Each is one small test if the owner wants it.
- **Effect:** additive. New: `eidos.agents.knowledge_gate` and its tests. Changed: `ResearchAgent` (an optional field), the agents package exports, the agents guard and the knowledge guard (deliberately). Unchanged: `MissionState`, the reducer, `eidos.state`, `eidos.recording`, the verifier, the tool gate, strategy selection, replanning, every V1.1 and V1.2 contract, `pyproject.toml`, the benchmark and the retrievers. Test-only changes to two existing files: the agents guard and the knowledge guard (deliberate, reading 9), and the Step 5 replay test now imports the shared fresh-interpreter replay. Applied. The Step 8 close-out changed no source file, no test and no contract.
- **Correction and observation (V1.4-B, 2026-09-27):** reading 5 (a replan attempt's Research node records no retrieval fact of its own, because the gate serves the repeated query) is right, but its consequence for the audit was incomplete. The default `execution_record` holds the last plan's steps only, so `audit_evidence(execution_record(records))` marks that attempt's citations `unresolved`; the whole execution resolves them (`tests/integration/planning/test_v1_replanning_tracker.py` shows both). The product backend audits the whole execution (D-231, `eidos.service.views.whole_execution_record`); no core projection changed.

### D-229 — V1.4 Product Backend: the milestone, its scope, and the handoff's Frontend and Deployment labels (ACCEPTED 2026-09-27; IMPLEMENTED IN V1.4-B)

- **Status:** Accepted · **Date:** 2026-09-26 · **Raised by:** Claude Code, consolidating the V1.4 inspection into V1.4-A · **Decided by:** human owner, for the milestone's name, its scope and what it must preserve (the V1.4 briefs of 2026-09-26); the treatment of the handoff's labels, and with it D-222 point 1, was Claude Code's proposal and was confirmed by the owner on 2026-09-27 (the V1.4-B brief).
- **Source:** the owner's V1.4 briefs; handoff §50 (V1.3 Frontend, V1.4 Deployment), §51, §52, §53, §54, §76, §78; D-022, D-184, D-196, D-199, D-202, D-208, D-222 point 1; `docs/13_product_backend.md`.
- **Decision (owner):** the next milestone is **"V1.4 Product Backend"**: turn the validated EIDOS runtime into a usable backend service, Next.js (later) to FastAPI to the EIDOS runtime to Supabase PostgreSQL to authentication and lightweight tenancy, **without changing the core runtime architecture.** It must preserve: (1) `MissionState` is the authoritative runtime state; (2) the reducer is the only authority for mutating it; (3) database persistence is durable storage and never a replacement runtime authority; (4) the V1.1, V1.2 and V1.3 contracts; (5) model independence; (6) domain independence; (7) the execution, event and replay architecture. The API and the database adapt to EIDOS; EIDOS is not redesigned to fit them. **Not in this milestone:** a frontend, Qdrant, Docker, deployment, Kubernetes, scaling or load work, new agents, new retrieval strategies (hybrid, reranking), another orchestration framework, microservices, enterprise authentication. The five architecture decisions are D-230 to D-234, and the frozen contracts are in `docs/13_product_backend.md`.
- **The handoff (reported, not a conflict; the handoff is not modified):** §50 labels *V1.3 Frontend* and *V1.4 Deployment*; §51 and §76 say *SQLite initially, PostgreSQL later*; §53 gives a conceptual `POST /missions` whose sample result carries a `confidence`; §54 defers authentication and tenancy and says the MVP must not become an authentication project. The owner's milestone uses Supabase PostgreSQL first, with no SQLite, and lightweight authentication and tenancy now. This is a sequencing and scoping ruling of the same kind as D-184, D-203 and D-208. The sample `confidence` is not produced: verification computes no scalar (invariant 13; D-015, D-121, D-159).
- **Treatment of the handoff's labels (Claude Code's proposal, pending confirmation):** this project's milestone numbers are V1.3 = RAG (D-208) and V1.4 = Product Backend. The handoff's **Frontend** and **Deployment** are its labels for product capabilities, not numbers in this project's ladder: both become **unassigned and not started**, the treatment D-184 gave MCP and RAG and D-199 and D-202 gave the handoff's V1.1 and V1.2 items. Each is numbered only when the owner starts it, and nothing is renumbered. `progress.md`'s ladder reads "Frontend (the handoff's label V1.3)" and "Deployment (the handoff's label V1.4)"; the references in `docs/02`, `docs/10` and `docs/03` say the same; older dated entries are historical and are not rewritten. The handoff's "API + workers + DB" overlaps this milestone only in the API and the database: containers, a cloud environment and separate workers stay with Deployment. If the owner confirms this, **D-222 point 1 (the milestone label) is resolved**; D-022 (the frontend stack) stays Open, not before Frontend starts.
- **Confirmed (owner, 2026-09-27):** the treatment of the two labels.
- **Effect (V1.4-A):** documentation only. No source, test, dependency or contract change.
- **Accepted and implemented (V1.4-B, 2026-09-27):** the owner approved D-229 as proposed: V1.4 is the Product Backend, the handoff's Frontend and Deployment labels are unassigned and not renumbered, and D-222 point 1 is resolved. The owner also replaced the V1.4-A implementation order (V1.4-B to V1.4-E, `docs/13` section 11) with ONE substantial phase, V1.4-B, which built everything in D-230 to D-234 in a single commit: the additive `tracker` parameter, `eidos.service`, `eidos.persistence`, `eidos.api` and `eidos.providers.factory`, with their tests. Not built, by the owner's scope: a frontend (Next.js), Docker, Render, Kubernetes, a separate worker service, Qdrant, enterprise IAM, complex RBAC and any knowledge-base management.

### D-230 — V1.4 persistence: Supabase PostgreSQL, the event log as the durable authority, the schema and the write-through model (ACCEPTED 2026-09-27; IMPLEMENTED IN V1.4-B)

- **Status:** Accepted · **Date:** 2026-09-26 · **Raised by:** Claude Code (V1.4-A) · **Decided by:** human owner, for the direction below; the schema, the write-through model and the recovery rules were Claude Code's proposal and were accepted by the owner on 2026-09-27, including that the recorder's lock is held during the ordered write-through flush.
- **Source:** the owner's V1.4 briefs; D-005, D-017, D-038, D-076, D-085, D-129, D-137, D-145, D-155, D-157, D-160, D-201; invariants 1, 2, 6, 8 and 15; `docs/13` section 2.
- **Decision (owner):** Supabase PostgreSQL is the durable backend store, and SQLite is not introduced first. The **`EventLog` is the authoritative durable mission history**; `MissionState` is the runtime fold of events; `ExecutionRecord` and `audit_evidence` are projections; artifacts stay behind the existing `ArtifactStore` abstraction; persistence does not replace EIDOS runtime authority. The tables are `tenants`, `tenant_members`, `missions`, `mission_events` and `artifacts`, with any absolutely necessary additional table, and **no plans table** unless an existing invariant requires one.
- **Proposed (`docs/13` section 2, pending confirmation):** (1) The five tables, plus a `schema_migrations` table for the applier, in a schema `eidos`; the DDL is in `docs/13`. No plans table is needed: invariant 6 is met by the immutable, versioned plan in its `PLAN_GENERATED` payload. No table holds `MissionState`, `ExecutionRecord` or any status the reducer folds; `missions.last_sequence` is an append guard only and the log wins on any mismatch; projection columns wait for a list API. (2) Before `MISSION_CREATED` the mission does not exist for the log (D-201), so `missions.spec` holds the accepted `MissionSpec` without its documents (those are supplied artifacts); once events exist, the recorded payload is authoritative. (3) **Write-through:** a `DurableEventLog(EventLog)` overriding `accept` only, and a write-through wrapper of the run's in-memory artifact store; one ordered per-run outbox, flushed in one transaction with an optimistic `last_sequence` guard; fail-soft, so a flush failure never raises into the runtime; a final flush, and `run_status = error` if it cannot be made; nothing is persisted that the reducer refused; the durable prefix is always a valid replayable log. (4) The read path replays on read and writes nothing. (5) Startup marks `queued` and `running` runs `interrupted` and writes no event; one API process per database. (6) Plain versioned SQL migrations, no ORM, no session state (so any Supabase connection mode works, to be verified), and `supplied()` ordered `collate "C"` so the database collation cannot change what a model is shown. (7) The applied-event-id set (D-038) is derived from the log, with full retention.
- **Departure from the handoff:** §51 and §76 (SQLite initially, PostgreSQL later) become Supabase PostgreSQL first, by the owner's direction (D-229).
- **Answers for V1.4:** D-017 (what is stored: events and artifacts; which is authoritative: the events, D-157; the interface: the service Protocols and the existing `ArtifactStore`), D-038, and D-076 and D-129 (the log still holds an `ArtifactRef` only; the content is durable in `artifacts`). D-017's remainder (snapshots, strategy memory, other stores) stays Open.
- **Confirmed (owner, 2026-09-27):** the schema and the write-through model, including that the recorder's lock is held while a flush runs (database latency serialises node settlements; accepted for the MVP).
- **Effect (V1.4-A):** documentation only.
- **Implemented (V1.4-B, 2026-09-27):** `eidos.persistence` (`migrations/0001_init.sql`: six tables in schema `eidos`, row level security enabled on every table with no policy, every privilege on the schema revoked from `anon`, `authenticated` and `service_role` wherever those roles exist; `migrate.py`, the plain-SQL applier, run with `python -m eidos.persistence.migrate`, serialised by a transaction-level advisory lock; `postgres.py`, `PostgresStorage` and `PostgresArtifacts` over a psycopg 3 pool with `prepare_threshold=None`, a statement timeout and single compare-and-set statements) and `eidos.service.durable` (`RunPersistence`, the ordered outbox; `DurableEventLog(EventLog)`, which overrides `accept` and `accept_resumed` and calls the real intake first; `WriteThroughArtifactStore`). **Differences from the V1.4-A DDL, all additive or clarifying:** `missions.contract_id` (the contract id is assigned at creation and the run must rebuild the same contract); named constraints; composite keys `(mission_id, tenant_id)` and `(execution_id, tenant_id)` with composite foreign keys, so the schema itself refuses an event or an artifact that names another tenant's mission. **Semantics:** one atomic commit per flush guarded by the expected `last_sequence` (artifacts before the events after them); a commit whose answer was lost is recognised (the durable log already holds exactly the pending event ids and sequences) and not written twice; any other sequence conflict, and any artifact conflict, is a permanent failure of the run (`error`) and nothing more is written; the final flush is bounded (three attempts, a growing pause); a store fault never reaches the runtime. No table holds `MissionState`, `ExecutionRecord` or a folded status. **Verified** by one repository-contract suite run on the in-memory storage in the default suite and on a real PostgreSQL 16.2 with `-m postgres` (`EIDOS_TEST_DATABASE_URL`, a disposable database; an embedded local server, **not a Supabase project**), and by 15 PostgreSQL-only tests (the migrations, deny-all RLS and the API roles, the schema's own constraints, a whole mission, restart and recovery, two processes racing to start one mission). The concurrent-applier test found a real race in the applier's bootstrap (`create ... if not exists` is not safe against a concurrent creator); the bootstrap now takes the same advisory lock. The default suite needs no database and no credential.

### D-231 — V1.4 execution path: `run_with_replanning`, and the additive tracker that resolves D-204 item 1 (ACCEPTED 2026-09-27; IMPLEMENTED IN V1.4-B)

- **Status:** Accepted · **Date:** 2026-09-26 · **Raised by:** Claude Code (V1.4-A) · **Decided by:** human owner, for the direction and its requirements; the exact change below was Claude Code's specification and was accepted exactly by the owner on 2026-09-27.
- **Source:** the owner's V1.4 briefs; D-199, D-200, D-201, D-204, D-208 item 5, D-228; `eidos.replanning`, `eidos.recording`.
- **Decision (owner):** the real API execution path uses the **full `run_with_replanning` driver**. D-204 is resolved by an **additive tracker propagation**, preferably an optional tracker parameter into `run_with_replanning` and not a replacement of the path. Existing callers remain compatible; the default behaviour is unchanged; model, tool, retrieval and citation facts are captured when the tracker is supplied; replan attempts retain correct recording behaviour; V1.1 is not rewritten and its frozen semantics are not silently changed.
- **The exact change (Claude Code's specification):** one new **keyword-only, optional** parameter, `tracker: ModelCallTracker | None = None`, on `run_with_replanning`, forwarded unchanged as `record_attempt(..., tracker=tracker)`. That is the whole change (the code is in `docs/13` section 3); `ModelCallTracker` is already exported by `eidos.recording`, which `eidos.replanning` already imports. **Default `None` changes nothing:** `record_attempt` then builds its own fresh tracker exactly as it does now, so an existing caller's events, telemetry and experiences are identical. **With a tracker,** the caller wraps its model, tool access, knowledge port and agents with that same tracker, as for `record_baseline`, and every attempt's nodes settle with their facts. One tracker across attempts is correct (its collectors are thread-local and opened and closed per node), and `record_attempt` still creates a fresh `Recorder` per attempt. The only observable difference, and only when a tracker is supplied, is that `model_call_count`, `tokens_used` and `responses_missing_token_counts` in the telemetry and in `ExecutionExperience` are real instead of zero. **Not changed:** `record_attempt`, `record_baseline`, the recorder, the tracker, the reducer, the events, the flow of `run_with_replanning`, and **D-204 item 2** (`tool_calls_used` stays a whole-mission total; Open and deferred). As D-228 reading 5 says, a repeated query in a replan attempt is served by the `KnowledgeGate`, so that attempt's Research node records no retrieval fact of its own and its citations still resolve to the first attempt's hits in `audit_evidence`.
- **What it lifts:** D-208 item 5 listed `run_with_replanning`, `record_attempt` and tracker propagation as frozen for V1.3. V1.4 lifts that for this one parameter, by the owner's direction, and for nothing else.
- **Tests required with the change (V1.4-B):** every existing test passes unmodified; a run with no tracker records the log the existing replanning scenarios pin; with a tracker and a forced replan, the model, tool, retrieval and citation facts are on the settled nodes of every attempt and are not attributed across attempts; the change touches `replanning.py` only.
- **Confirmed (owner, 2026-09-27):** the specification.
- **Effect (V1.4-A):** documentation only. The change is V1.4-B.
- **Implemented (V1.4-B, 2026-09-27):** `run_with_replanning` gained one keyword-only parameter, `tracker: ModelCallTracker | None = None`, forwarded unchanged as `record_attempt(..., tracker=tracker)`; that is the whole core change (`src/eidos/replanning.py`: one import name, the parameter, the forwarded argument and a docstring paragraph). No caller was changed, and `record_attempt`, the recorder, the tracker and the reducer are untouched. The default records what every earlier caller got. **One existing test was updated on purpose and not weakened:** `tests/unit/recording/test_recording_tool_facts.py` pins the exact parameter list of `run_with_replanning`, and its pin now ends `log, tracker` (all keyword-only, both default `None`). Six new tests (`tests/integration/planning/test_v1_replanning_tracker.py`): with no tracker no model fact is recorded and the log has the shape it always had; a supplied tracker is the same object at every attempt (a spy on `record_attempt`); under a forced replan the model, retrieval and citation facts are on the settled nodes of both plans and belong to the attempt that made them. **Found by that test, reported and not decided:** the default `execution_record` is the LAST plan's steps only, and a retrieval fact lives on the node of the attempt that made it, so `audit_evidence(execution_record(records))` calls a replan attempt's citations `unresolved` although they were retrieved (D-228 reading 5 was right about the gate and incomplete about the audit). The service therefore audits a validated whole-execution record (`eidos.service.views.whole_execution_record`: every plan's steps in plan order, built through the record's own strict JSON form, never constructed around its validators). No core projection changed; whether `execution_record` should ever default to the whole execution is a core question left to the owner.

### D-232 — V1.4 MissionSpec: its mapping to `TaskGenome` and `ReliabilityContract`, and the provisional API safety ceilings (ACCEPTED 2026-09-27; IMPLEMENTED IN V1.4-B)

- **Status:** Accepted · **Date:** 2026-09-26 · **Raised by:** Claude Code (V1.4-A) · **Decided by:** human owner, for the direction; the mapping's details and the ceilings were Claude Code's proposal; the owner accepted the mapping, `supplied_documents`, server-assigned identity and ceilings that reject and never clamp on 2026-09-27. The numeric values stay PROVISIONAL configuration.
- **Source:** the owner's V1.4 briefs; invariants 3, 7, 13 and 14; D-009, D-015, D-016, D-045, D-046, D-057, D-065, D-066, D-073, D-103, D-127, D-145, D-146, D-156, D-201, D-205; `docs/04`; `docs/13` sections 4 and 9.
- **Decision (owner):** the API receives an **explicit structured `MissionSpec`**. The `TaskGenome` is **not derived from an LLM**: the backend validates the supplied structure and applies configured server ceilings, and the client supplies the bounded mission intent and constraints from which the runtime input is constructed. Invariant 3 is preserved: the LLM does not silently become the authority for mission-genome creation. The mapping is the minimum one, with no large new product schema.
- **Proposed (`docs/13` section 4, pending confirmation):** (1) `MissionSpec` uses the contracts' own field names, so the mapping is one to one: `goal`, `required_capabilities`, `information_dependencies`, `risk_level`, `autonomy_level`, `allowed_actions`, and a `reliability` object holding the `ReliabilityContract` fields (`min_quality`, `max_risk_level`, `min_independent_evidence`, and the six optional budgets, `max_execution_time` in milliseconds as in D-078); plus an optional, bounded `supplied_documents` list (D-145's supplied artifacts). (2) The server assigns `tenant_id` (from the authenticated context; a client-supplied one is refused), `mission_id`, `execution_id`, `contract_id`, the timestamps and the `MissionState` carrier (`CREATED`, no plans, counters 0) that `run_with_replanning` reads the genome, the contract and the ids from. (3) Validation order: body size, structure with unknown fields forbidden, the server ceilings, the existing contract validators, then persistence. Every ceiling **rejects; none clamps** (D-009). A budget that is absent stays absent (D-065, D-205); a present one above `SystemLimits`'s same field is rejected. (4) `min_quality` and `max_risk_level` are recorded and not evaluated (D-015, D-146); the API never reports a confidence. (5) The ceilings (body size, goal length, list lengths, `max_autonomy_level`, the `allowed_actions` allowlist, the document count and sizes, the run concurrency) are **provisional API safety ceilings, not tuned and not measured** (the D-046 precedent), listed in `docs/13` section 9 and labelled there; **they are not EIDOS budget enforcement** and nothing claims they are.
- **Answers for the API:** D-066 (the contract is user-supplied and validated, never synthesised), D-057 (`risk_level` is as stated by the caller, not assessed). D-046 (the values of `SystemLimits`) stays Open; V1.4 supplies a provisional configuration.
- **Confirmed (owner, 2026-09-27; the numeric values stay provisional):** `supplied_documents` in the spec (small, and it reuses D-145's supplied artifacts), and the provisional values.
- **Effect (V1.4-A):** documentation only.
- **Implemented (V1.4-B, 2026-09-27):** `eidos.service.spec` (`MissionSpec`, `ReliabilitySpec`, `SuppliedDocument`, `validate_spec`, `contract_and_genome`, `initial_state`, `spec_digest`) and `eidos.service.config`. The field names are the contracts' own and a test pins that the mapping is one to one (`MissionSpec` minus `reliability` and `supplied_documents` is `TaskGenome` minus `tenant_id` and `reliability_contract_id`; `ReliabilitySpec` is `ReliabilityContract` minus `tenant_id` and `contract_id`). The server assigns the tenant (from the authenticated context), the mission, execution and contract ids and the timestamps; a client-supplied tenant or any other unknown field is refused. Ceilings reject and never clamp, every problem is reported in one pass, and a contract budget above `SystemLimits` is rejected. A document reference must be one a model can cite (a letter or digit first, then letters, digits and `: . _ / -`, at most 128) and may not use a namespace the runtime writes (`artifact:`, `evidence:`, `tool:`); size is counted in UTF-8 bytes. The request digest (SHA-256) covers the documents, so an `Idempotency-Key` reused with different documents is a conflict. **The numeric ceilings, `SystemLimits` and the runner bounds are PROVISIONAL** (`eidos.service.config`, labelled there): not tuned, not measured, not derived from any run; D-046 and D-103 stay Open. The carrier `MissionState` handed to `run_with_replanning` is built by the reducer, by folding one `MISSION_CREATED` event through a throwaway `EventLog` (`initial_state`), because only the reducer may construct a `MissionState` (a repository guard); its `state_version` is therefore 1, and V1.4-A's `state_version=0` was wrong. The run's own log records its own `MISSION_CREATED`.

### D-233 — V1.4 authentication and multi-tenancy (ACCEPTED 2026-09-27; IMPLEMENTED IN V1.4-B; resolves D-032)

- **Status:** Accepted · **Date:** 2026-09-26 · **Raised by:** Claude Code (V1.4-A) · **Decided by:** human owner, for the direction, and for the reserved nil tenant (which settles D-032); the choice between application-only isolation and application isolation plus RLS was left to Claude Code within the owner's stated preference (the smallest production-safe design), and was accepted by the owner on 2026-09-27: application-enforced isolation plus deny-all RLS as defence in depth, with tenants and memberships provisioned out of band.
- **Source:** the owner's V1.4 briefs; handoff §54; D-019, D-032, D-033, D-079; invariant 18; `docs/13` section 5.
- **Decision (owner):** authentication uses a **Supabase-issued JWT**. FastAPI verifies the **signature, the expiry and the audience**, and the token's **subject is the user identity**. Tenancy is **explicit membership**. **Every repository operation is tenant-scoped.** **A resource belonging to another tenant returns 404.** The **nil/default tenant sentinel is reserved for non-real and test contexts.** Roles are **owner and member** only. No enterprise RBAC, SSO, rate limiting or complex policy engine.
- **D-032 is settled by that direction:** the literal stays the nil UUID, and it is a reserved sentinel that a real tenant may never take. The `tenants` table rejects it; the API neither accepts nor produces it; tests, in-memory and single-tenant contexts may use it. The placeholder comment in `eidos.contracts.identifiers` is updated when code is written (documentation only in this phase).
- **Chosen within the owner's preference (Claude Code, pending confirmation):** tenant isolation is **application-enforced**, and PostgreSQL row level security is used only as a safety net, **enabled on every table with no policies**, with the `eidos` schema not exposed through Supabase's Data API and no privilege granted to its API roles, so a leaked public key reaches nothing. Tenant-scoped RLS policies are **deferred**: they need per-request claims set in every transaction, which conflicts with the no-session-state rule of D-230, and the isolation is tested with contract tests over the in-memory and the PostgreSQL repositories. Tenant resolution: no membership is 403; an `X-Tenant-Id` that is not one of the user's tenants is 404; no header with one membership uses it, and with several is 422. Both roles have every V1 endpoint on their tenant's missions; the role is reserved for the membership management that is deferred. **Tenants and memberships are provisioned out of band** (a SQL script); there is no signup, tenant or membership endpoint in V1.4-A. Secrets come from the environment only.
- **Not verified in this phase (no network use):** Supabase's current JWT signing and key details, how its Data API exposes schemas, and its connection modes. Each is verified against the current documentation when the code is written.
- **Confirmed (owner, 2026-09-27):** application-enforced isolation with deny-all RLS, and out-of-band provisioning.
- **Effect (V1.4-A):** documentation only.
- **Implemented (V1.4-B, 2026-09-27):** `eidos.api.auth` (`JwtVerifier`, `JwksKeys`, `StaticKey`), `MissionService.resolve_context`, the `tenants` and `tenant_members` tables and `eidos.persistence`. **Verified:** the signature, the expiry (`exp` required) and the audience (`aud` required; `authenticated`, Supabase's value for a signed-in user, is the default); the subject must be a UUID and is the user; an issuer is checked only if one is configured. The algorithm list is fixed by configuration and never read from the token: the asymmetric mode (the project's JWKS endpoint, `https` only, cached at most ten minutes) allows RS256 and ES256, the legacy shared-secret mode allows HS256, and `none` is refused at construction; an unsigned token and an algorithm-confusion token are tested and refused. A JWKS endpoint that cannot be reached is a 503 `auth_unavailable`, not a 401, and every rejection is one indistinguishable 401. **Tenancy:** explicit membership; `X-Tenant-Id` when a user belongs to several tenants; a tenant the user is not a member of is a 404 whether or not it exists; every repository call takes the tenant; another tenant's mission is a 404 on every method, tested on the in-memory and the PostgreSQL repositories. The schema itself refuses an event or an artifact whose tenant differs from its mission's, refuses the nil tenant (a check constraint), and enables RLS on every table with no policy and no privilege for the API roles. Provisioning is out of band (`PostgresStorage.add_tenant` and `add_member` exist for tests). **D-032 is settled in code:** the nil UUID stays a reserved sentinel; the comment in `eidos.contracts.identifiers` is updated (a comment only; the value is unchanged). No RBAC engine, SSO, rate limiting or per-endpoint policy was built.

### D-244 — A Groq rate limit failed a mission step at once; the adapter now waits as long as Groq asks, boundedly, and retries (RESOLVED 2026-10-02)

- **Seen by the owner** (the first run that reached a live model): `the model call failed (unavailable): the provider answered HTTP status 429: Rate limit reached for model `openai/gpt-oss-120b` … on tokens per minute (TPM): Limit 8000, Used 5997, Requested 4073. Please…` — the model, key and URL were right; the free (`on_demand`) tier allows 8,000 tokens per minute and this mission's own earlier calls had used 5,997 of them. A rate limit is the provider saying "not yet" and saying how long, but `GroqModel` returned it as a failure immediately, a failed node makes EIDOS replan, and each replan made more calls into the same exhausted minute (the earlier 404 mission shows the shape: five refused calls, two replans, nothing completed).
- **Change (`eidos.providers.groq`, adapter only):** on HTTP 429 the adapter reads `Retry-After`, waits that many seconds and asks again — **at most 3 retries, no wait longer than 30 s (a longer `Retry-After` is reported at once rather than holding a step for minutes), and never past the call's own `timeout_seconds`** (that timeout is now one bound over every attempt and wait, not per socket operation). With no usable `Retry-After` the wait doubles from 2 s (2, 4, 8). The same request is repeated, nothing is changed; no other status is ever retried (401, 403, 404, 5xx are as before). If the limit does not lift the failure is the same `UNAVAILABLE` with Groq's own explanation (D-242) and "(after waiting and retrying N times)". `MeasuredFacts.elapsed_seconds` is the whole call including the pauses — what the caller actually waited, an observed fact. The wait is made by an injectable `sleep` (default `time.sleep`) so tests do not really wait; Ollama is unchanged (a local runtime has no such limit).
- **Verification:** `tests/integration/providers/test_groq_adapter.py` (a wait for the stated time then success; doubling with no header and with a non-numeric one; bounded retries with the provider's reason in the message; a too-long wait not made; a wait that does not fit the timeout ending the retries; a real wait of the stated length; no other status retried; the key never in the message). **7 deliberate breakages of the new handling, 7 caught** (one survived at first because the call timeout masked the 30 s cap, and the test was fixed, not the code).
- **Not verified:** the owner's real run after this change (no key used here). **What it cannot fix:** a free-tier account is slow by construction — a mission makes several model calls of a few thousand tokens each, so it spends most of its time waiting out the minute; and Groq counts *max output tokens* toward "Requested", so a large `EIDOS_MODEL_MAX_OUTPUT_TOKENS` makes every request ask for more of the minute than it uses. A fetched page larger than the tier's per-minute allowance can never fit, and the provider's message will say so. Production wants a paid tier or a smaller output budget; both are the owner's choice (`docs/14`).

### D-243 — The Groq model id suggested in the V1.6 notes had been retired (RESOLVED 2026-10-02; configuration guidance only)

- **Seen by the owner**, now that D-242 makes the reason visible: `the model call failed (unavailable): the provider answered HTTP status 404: The model `llama-3.3-70b-versatile` does not exist or you do not have access to it.` — so the URL and the key were right (a bad key is 401, a bad URL a different 404) and Groq itself would not serve that model. **Cause:** Groq's published deprecation list gives `llama-3.3-70b-versatile` a shutdown date of 2026-08-16 (recommended replacement `openai/gpt-oss-120b`); its models page, fetched in the same check, still listed it, which is most likely stale. The id was the example I wrote into `render.yaml`, the run instructions and D-239 from memory; nothing in the code assumes it (`EIDOS_MODEL_NAME` is required and has no default, D-135).
- **Change (documentation and a comment only):** `render.yaml` and `docs/14_deployment.md` now suggest `openai/gpt-oss-120b`, say models are retired on a schedule, how to list the ids an account can use, and how each refusal reads. No code, test or contract changed.
- **Not verified:** that `openai/gpt-oss-120b` works end to end with this adapter (no key was used here). It is a reasoning model, so the output-token budget may need to be generous, and Groq's per-minute token allowance may refuse a large fetched page; both are stated in `docs/14` as things to watch, not as facts. The owner's next mission, or the opt-in `-m groq` test, is the check.

### D-242 — A refused model call said only "HTTP status 404"; it now carries the provider's own explanation (RESOLVED 2026-10-02)

- **Seen by the owner:** after the D-240 fix a mission failed `execution_failed` with "the model call failed (unavailable): the provider answered HTTP status 404" (five model calls refused in 3.4 s, two replans, nothing completed). A 404 from a provider means very different things — a model name the account cannot use or that was deprecated, a wrong base URL, a model that was never pulled into Ollama — and the message could not say which. The owner's terminal showed the Ollama and the Groq settings blocks pasted into one window several times, so which provider, URL and model were really in force could not be told from outside either.
- **Fix:** `eidos.providers._http_error.http_failure_message` (shared by `OllamaModel` and `GroqModel`) reads at most 16 KB of the error body and, when it is JSON with an `error` message (`{"error": {"message": …}}` for Groq, `{"error": "…"}` for Ollama), appends it: `the provider answered HTTP status 404: <message>`. The message is whitespace-collapsed and cut to 200 characters; **the API key is replaced by `[redacted]` wherever it appears, before the cut**, so a cut cannot leave half of one; a body that is missing, unreadable, not JSON, too large or has no message gives exactly the plain status line as before. The failure kind, every other path and the existing tests' assertions (the status is in the message) are unchanged.
- **Established for real, keylessly:** with the right URL and a wrong key Groq now reports `HTTP status 401: Invalid API Key`; with the base URL missing `/openai/v1` it reports `HTTP status 404: Unknown request URL: POST /chat/completions. Please check the URL…` — the 404 the owner saw is very plausibly this (a base URL of `https://api.groq.com` or an Ollama URL left in place under the Groq provider). A wrong model name gives a different message and is now distinguishable. **Not verified:** which of these the owner's run actually had — the next failure will say.
- **Tests:** `tests/unit/providers/test_http_error.py` (the cases above, redaction, truncation, unreadable and oversize bodies, a bounded read), one case each in `test_groq_adapter.py` (including a server that echoes the key back) and `test_ollama_adapter.py`.

### D-241 — A pooled database connection that died while idle made the next request wait ~20 s and fail 503 (RESOLVED 2026-10-02)

- **Seen by the owner:** `POST /api/eidos/missions 503 in 19.9s`; the backend log read `discarding closed connection: <psycopg.Connection [BAD]>` then `POST /v1/missions … 503 Service Unavailable`. **Cause:** the pool (`psycopg_pool`, min 1) held a connection the remote end — Supabase, a NAT, or a laptop's network after sleep or a switch — had dropped while idle. It looks open until used; the first request then waits for the operating system to give up on the dead socket (about 20 s), the failure is a retriable `StorageError` and so a `503 storage_unavailable`, and the pool discards the connection (the "[BAD]" line), after which the next request works. The pool had no health check on checkout and no TCP keepalives.
- **Fix (`eidos.persistence.postgres.PostgresStorage.open`, connection settings only):** `check=ConnectionPool.check_connection` — the pool tests a connection as it hands it out and replaces a dead one before a request sees it (one cheap round trip per checkout: noticeable against a high-latency remote database, negligible next to it in production); TCP keepalives (`keepalives=1`, idle 30 s, interval 10 s, count 3) so an idle connection is kept alive through NATs and a dead one is noticed; and `tcp_user_timeout=10000` ms so a send to a dead peer cannot wait ~20 s. All are libpq client parameters (checked to be accepted by the Windows libpq as well as Linux's). No schema, port, contract or behaviour change; `prepare_threshold=None`, the statement and connect timeouts and the pool size are as they were.
- **Verification and its limit:** `tests/unit/persistence/test_postgres_pool.py` pins the pool's construction (no database needed). **The recovery from a genuinely dead connection was not reproduced here** — no database was available — it is `psycopg_pool`'s own `check` behaviour once enabled. The owner can confirm it by leaving the backend idle past the point it failed before and creating a mission.
- **Not changed, deliberately:** writes are not retried on a connection fault (a lost acknowledgement after a successful commit would repeat the write); a request that hits a database that is really down is still a 503. The ~2 s per request of a *local* backend against a *remote* database is round-trip latency, not this.

### D-240 — The Groq adapter named no User-Agent, so Groq's front door refused every real call with HTTP 403 (RESOLVED 2026-10-02)

- **Found by the owner's first real use of Groq** (a mission ended `execution_failed`: "the model call failed (unavailable): the provider answered HTTP status 403"). **A defect in D-235's adapter, mine:** `GroqModel` used `urllib` and set no `User-Agent`, so every request went out as `Python-urllib/3.x`. Groq sits behind Cloudflare, which answers that identity with `403 Error 1010: Access denied` *before the request reaches Groq*, whatever the key. D-235's scripted adapter tests could not show it and its opt-in real test (`-m groq`, needs a key) had never been run, so the adapter had never been exercised against the real service.
- **Established without any key:** the same unauthenticated request returns `403` / `error 1010` with the default identity and the normal `401 invalid_api_key` with any other; and after the fix the real adapter, given a deliberately wrong key, returns `unavailable … HTTP status 401` (it reached Groq) instead of `403`.
- **Fix:** `eidos.providers.groq.USER_AGENT = "EIDOS-model-adapter/1"`, sent on every call; `test_groq_adapter.py` now asserts the header is present and is not `Python-urllib`. Nothing else changed (no new dependency; the adapter still reads no environment).
- **Not verified:** a successful completion from Groq with a real key — no key was used here. The next step is the owner's own run with a valid key (the opt-in `-m groq` test or a mission). A `403` after this fix would mean something else (a model the account cannot use, a revoked key — Groq and GitHub revoke keys that appear in public places — or a region block).

### D-239 — A fetched page's reference carried a 64-hex request digest that a small model mis-copies, so a correctly grounded answer could fail verification (RESOLVED 2026-10-02, option (a), the owner's ruling)

- **Resolution (owner chose (a): "yes a"):** `eidos.agents.tool_gate.tool_document_ref` now puts only the **first 12 hex characters** of the request digest in a reference (`REFERENCE_DIGEST_CHARS = 12`): `tool:<tool_id>:<12 hex>:<document_id>`. Nothing else changed: `args_digest` stays the full SHA-256 in `ToolInvocationRecord`, `ToolAdmission`, the recorded `ToolCallFacts` and duplicate detection (`(execution_id, tool_id, args_digest)`); the reference's digest is the *start* of the recorded one, so a reference still names its call (`fact.args_digest.startswith(prefix)`). A clash is, as before, a typed `MALFORMED_RESULT` ("a document reference is already taken") that stores nothing and never overwrites. The verifier, the gate's order of operations, the policy, and every other V1.2 rule are untouched. **Tests that pinned the old format were updated to the new one on this ruling, not weakened:** `test_each_document_becomes_its_own_artifact_...` and `test_a_document_reference_round_trips_...` (`tests/unit/agents/test_agents_tool_gate.py`) now expect the 12-character form, and `test_end_to_end_evidence_is_traceable_...` (`tests/integration/tools/test_tool_path.py`) now asserts the reference's digest is a 12-character prefix of the recorded full digest and that exactly one recorded call carries that prefix (the same traceability, stated for a prefix). New: `test_a_reference_is_short_enough_to_copy_...` and `test_two_requests_whose_digests_start_alike_are_a_refused_call_never_a_wrong_source`. The old problem statement follows.
- **Status:** Resolved · **Raised by:** Claude Code, from the one real end-to-end run of D-238 · **Affects:** D-205/D-206 (the reference a retrieved document is stored under), `docs/08_mcp_contract.md` section 4, `eidos.agents.tool_gate.tool_document_ref`.
- **What happened (a real run, not a test):** the real fetcher read the owner's portfolio page, a real local model (`qwen3:4b` through Ollama, temperature 0, seed 7) wrote a grounded answer from it (name, title, location, education and CGPA all matched the page, each cited), and the real verifier then **failed** the mission: `citation_coverage` violated — one citation named a reference that does not exist. The reference is `tool:web/fetch:<64 hex characters>:<host>-<hash>`; the model reproduced it correctly in some citations and, in another, **dropped one hex character** (`…d4d610cbc…` written as `…d4d60cbc…`). The verifier did exactly its job (a citation to a source that is not there is not a pass — invariant 12); the mission ended `verification_failed`, honestly, with the page fetched and stored.
- **Cause:** V1.2 names a retrieved document by the tool, the **full SHA-256 of the call's arguments** and the document id so that a reference alone says where evidence came from. A model must copy the whole reference verbatim as `[[…]]`; 64 random hex characters is the part a small model gets wrong.
- **Not tested:** whether the production model (Groq, `llama-3.3-70b-versatile`) copies it reliably — no Groq key was used. Likely better; not guaranteed, and an intermittent verification failure on a correct answer is a poor product behaviour whichever model is behind it.
- **Options (not chosen — this edits an accepted V1.2 decision, so it is the owner's):** (a) **shorten the digest component of the reference to a prefix** (recommended: 12 hex characters, 48 bits). The reference is already scoped to one execution, an execution makes at most `max_tool_calls` (≤ 16) calls, and the gate already turns a taken reference into a typed failure rather than overwriting, so a collision is a refused call, never a wrong source. It changes `tool_document_ref` and the tests and docs that pin the format; `ToolInvocationRecord.args_digest` and duplicate detection keep the full digest. (b) Leave it and rely on larger models. (c) Cite by a short alias (`web:1`) that the gate maps to the real reference — more robust, but it touches how agents render and cite artifacts.
- **Not done:** no change to V1.2; the verifier, the gate and the reference format are exactly as they were.

### D-238 — A web-fetch tool: Research can read the public pages a goal names, behind the existing tool gate (ACCEPTED 2026-10-02; IMPLEMENTED)

- **Status:** Accepted · **Date:** 2026-10-02 · **Decided by:** the owner, explicitly: "the web fetch is needed, make it secure"; **no** rendered-page view, **no** quality or taste judgement (declined in the same message); no knowledge base or search API was asked for and none was built. · **Source:** the owner's request; V1.2 (D-203 to D-207: the tool seam, allowlist, admission, gate, recording); invariants 3, 12, 14, 16; CLAUDE.md section 3 (a tool is added only on the owner's approval; this is that approval, for one tool).
- **Decision.** One tool, `web/fetch`, a `ToolPort` adapter in a **new package `eidos.tools`** (not `eidos.providers`, whose guard says model adapters only; not MCP: it is a direct, in-process HTTPS client). It is reached by the **unchanged** V1.2 path: a pinned `ToolDescriptor` (read-only, action `web_fetch`, one string argument `query`, 45 s, 48 KB of result — provisional), `admit_tool_call` (the mission must list the action, have a `max_tool_calls` budget and autonomy ≥ 1), `ToolGate` (budget reserved before the call, duplicates served not re-fetched, each page stored as its own artifact `tool:web/fetch:<digest>:<host>-<hash>`), `RecordingToolAccess` (a `ToolCallFacts` on the node). `eidos.agents`, `eidos.contracts`, `eidos.runtime`, `eidos.recording`, `eidos.policy`, the API schema and every existing test are unchanged; `Composition` gained one optional `ToolProvision`, exactly as it has one for knowledge.
- **How a mission names a page (the one real design choice).** The Research agent already calls its tool once per run with the **goal text** as `query`. The adapter reads the `https` addresses **written in the goal** and fetches exactly those: none is a real empty answer (no network); more than three, or any one that fails, is a typed failure naming the address (all-or-nothing: no page is silently omitted); addresses found inside a fetched page are never followed. *Not chosen:* a new structured `urls` field or reuse of `information_dependencies` (it would change what Research does and add a contract field); a search API (not requested). The owner can still ask for a structured field later; nothing here prevents it.
- **Wiring.** The tool exists only where the deployer lists `web_fetch` in `EIDOS_ALLOWED_ACTIONS` (one existing knob; no new variable); a mission must also name it (the per-mission permission, shown in the form as "Let EIDOS read the web pages named in my goal", which sends the action and `max_tool_calls: 3`). `render.yaml` sets it.
- **Security (`eidos.tools.safe_https`; the whole point).** https and port 443 only, no credentials in the address; only real public host names (an IP in any spelling, a single-word name and local-only suffixes are refused); the name is resolved **once** and **every** address must be public (loopback, private, link-local, carrier-grade NAT, multicast, reserved, IPv4-mapped, 6to4, Teredo and the reserved low IPv6 block are refused; a NAT64 address is judged by the IPv4 address inside it); the socket is opened to the **checked address**, never the name, with TLS verified against the name (no re-lookup, so no DNS-rebinding window); redirects by hand, at most three, each fully revalidated; one deadline over DNS, connects and reads; the body capped at 512 KB and refused, not truncated; nothing decompressed (compressed answers refused); a non-text type is refused from its headers without downloading the body; GET only, no cookie, credential, caller header or proxy. Standard library only; reads no environment; guards in `tests/unit/tools/test_tools_guards.py` forbid an HTTP library, a high-level opener, proxies and disabling TLS verification. A refusal never echoes an address the name resolved to.
- **Found by running it for real, not by the scripted tests (both fixed, both now pinned):** (1) `http.client` closes its socket as soon as it has read the headers of a `Connection: close` answer, so a later `settimeout` failed on every real fetch; the read timeout is now set once before the response and the deadline is checked between reads (a call can overrun its deadline by at most one read timeout, 15 s). (2) This machine's network is DNS64: an IPv4-only host (including the owner's Render portfolio) resolves to `64:ff9b::` addresses, which the first version refused wholesale as non-public; they are now judged by the embedded IPv4 address (a private one inside the prefix is still refused).
- **One addition outside the tool, additive and honest.** `evidence_of` (the evidence view) now also returns the *text* of a cited fetched page, so a reader can see what was read (otherwise a fetched page appeared only as a bare reference). The audit is untouched: a fetched page is still `not_evidence` (it was not retrieved from a knowledge base — D-228's meaning stands); the panel labels it "Web page" and says so. No schema change (`EvidenceItem` already carries ref, type and content).
- **Verification.** `tests/unit/tools` (security matrix, pinning, redirects, bounds, DNS64, text extraction, the real gate's denials), `tests/unit/service/test_service_web_fetch.py` (a mission end to end on the real service: fetched, cited, verified, recorded; refused without the action, without a budget, below the autonomy level; a 404 and a private address never complete). **Mutation: 25 deliberate breakages of the protections, 25 caught** (two initially survived — a size failure retried on another address, a per-page rather than shared deadline — and the tests were strengthened, not the code). A real-network opt-in suite (`-m web_fetch`, never skipped, excluded from the default run): 11 passed against the real internet, including a real page, a public name that resolves to loopback (`localtest.me`, refused by the real resolver), an expired certificate (refused), a non-text type (refused) and the metadata address.
- **Real end-to-end runs** (in memory: the real fetcher against the owner's portfolio page, `qwen3:4b` through Ollama at temperature 0 and seed 7, the real verifier; no database, no secret). (1) A 300 s model timeout ended `execution_failed` (a 4B reasoning model on CPU is slow; nothing was invented). (2) The page was fetched, stored, recorded and cited and the answer was grounded in it, but the mission **failed verification** because one citation mis-copied the 64-hex digest in the reference — **D-239**. (3) After D-239 was resolved (a 12-hex reference), the same mission **completed and verified**: `mission_status=completed`, verdict `PASS` (`schema_validity`, `citation_coverage` — every cited source exists — and `minimum_distinct_sources` satisfied), the answer's every claim cited the one fetched page (`tool:web/fetch:449a47084cc8:portfolio-g9av.onrender.com-f83a`), one recorded tool call, 179 s. Read it as: the tool, the gate, the citations and the verifier work together on a real page and a real model. **A PASS means those three deterministic rules passed** — it measures no quality and does not say the summary is right (D-146); the claims I compared (name, title, location, education, CGPA) do match the page text. One mission, one model, one page: not a benchmark. A research+architecture mission was not retried.
- **Not verified / known limits.** Behaviour on Render (its egress and resolver) and with Groq's per-minute token allowance on a fetched page (the 48 KB bound is a provisional guess at keeping one page inside it); no per-user rate limit or quota (D-233) — outbound requests are bounded only by the per-tenant active-run cap and the queue; `robots.txt` is not honoured; no caching; JavaScript is not run, so a page that builds itself in the browser yields little text (and says so). Prompt injection: a page's text goes to a model as data; EIDOS never executes it and the model's output is text, but a model can still be steered by what it reads — the verifier checks citations, not truth.
- **Tests:** `tests/unit/tools` (207), `tests/unit/service/test_service_web_fetch.py` (9), `tests/unit/api/test_api_main.py`, frontend `web-access`, `create-mission-form` and `evidence-panel` tests.

### D-237 — Self-service sign-up: a user with no tenant is given a workspace of their own (ACCEPTED 2026-10-02; IMPLEMENTED, opt-in)

- **Status:** Accepted · **Date:** 2026-10-02 · **Decided by:** the owner, explicitly: "new account needs to get new workspace automatically, and the old user must be able to access their old workspace." · **Amends:** D-233's "tenants and memberships are provisioned out of band" and its `403 no_tenant_membership` for a signed-in user with no tenant — only where the deployer turns this on.
- **Decision.** `EIDOS_AUTO_PROVISION_WORKSPACES` (`true`/`1`/`yes`; absent or anything else is **off**, which is exactly the V1.4 behaviour) makes `MissionService.resolve_context` call a new `TenancyRepository.provision_personal_workspace(user_id, name)` when — and only when — a user has **zero** memberships. It creates a tenant named "Personal workspace" and an `owner` membership, then resolves as usual. A user who already has any tenant is never touched: their memberships, and so their old workspace and its missions, are exactly what they were; there is no migration and no data movement. Several tenants still means naming one in `X-Tenant-Id`.
- **Race-safe and idempotent by construction.** The new tenant's id is `uuid5(NAMESPACE_URL, "eidos:personal-workspace:" + user_id)` (`personal_workspace_id`), so the first page load's several simultaneous requests all name the same row; both inserts are `on conflict do nothing`. No lock, no advisory lock, no session state (D-230). Tested: 16 racing resolutions on 8 threads end with one tenant and one membership.
- **Why opt-in, and what it means.** Open sign-up plus automatic workspaces means anyone who can obtain a valid Supabase JWT gets a workspace and can start missions that spend the deployment's Groq quota. The existing bounds are the only limits: per-tenant active runs (`EIDOS_MAX_ACTIVE_RUNS_PER_TENANT`), the queue cap, the request-body and document ceilings. **No rate limit per user, no quota and no billing exist** (D-233 excluded rate limiting). The deployer should keep Supabase's **Confirm email** on (a session is then only issued after the address is confirmed) and watch Groq usage. Recorded as a known limit, not solved here.
- **Frontend (no backend contract change):** `/signup` (`supabase.auth.signUp`, ≥ 8 characters), `/auth/callback` (exchanges the confirmation `code` for a session, redirects only to a same-origin path), the same "check your email" message whether or not the address already exists (no account enumeration), and `/login`'s copy no longer says an administrator sets accounts up. Supabase must have email sign-ups enabled and `<site>/auth/callback` in its redirect-URL allow list — dashboard settings the owner makes; nothing here changes the project.
- **Not verified:** the `provision_personal_workspace` SQL against a real PostgreSQL (the default suite uses the in-memory storage; the contract test also runs under `-m postgres`, which needs a database this session does not have), and a real sign-up and confirmation email against the real Supabase project (no real account was created).
- **Tests:** `tests/unit/service/test_service_service.py` (5 new), `tests/integration/persistence/test_storage_contract.py` (1 new, both implementations), `tests/unit/api/test_api_main.py` (8 parametrised), frontend `auth-redirect`, `documents` and `create-mission-form` tests.

### D-236 — Two pre-existing V1.4-era guard tests now contradict V1.5's real, owner-directed frontend (RESOLVED 2026-09-28)

- **Status:** Resolved · **Date raised:** 2026-09-28 · **Date resolved:** 2026-09-28 · **Raised by:** Claude Code, while running the full default suite for unrelated V1.6 (Groq provider) verification. · **Decided by:** the owner, explicitly: fix both guards to stay faithful to the current architecture rather than leave them red or weaken them.
- **Source:** `tests/unit/service/test_service_guards.py`.
- **What was found:** two backend guard tests, written at V1.4-C (when `frontend/` genuinely did not exist), now fail against the repository's real, current, owner-directed state — not against anything V1.6 changed. Confirmed by `git stash`: both already failed identically on `d84219e` (V1.5-C's own HEAD, before any V1.6 work began).
  1. `test_nothing_deferred_was_built` asserts `not (ROOT / "frontend").exists()` — literally true at V1.4-C, and false since V1.5-A, on the owner's own explicit instruction to build a frontend.
  2. `test_no_environment_or_key_file_is_in_the_tree_and_the_ignore_file_keeps_it_that_way` flags `frontend/.env.local` (the real, gitignored, untracked local env file) and `frontend/.env.local.example` (a deliberately committed, secret-free template — `.gitignore` has carried a `!frontend/.env.local.example` exception since V1.5-A for exactly this file) as if they were the same class of risk as a real, leaked `.env`.
- **Why this is Open, not silently fixed:** CLAUDE.md section 7 forbids resolving a contradiction between test and reality silently in either direction. Weakening or deleting either assertion could plausibly hide a genuine future regression (a real `Dockerfile`/`docker-compose.yml` landing outside V1.6's own owner-directed Docker work, or a real leaked `.env`); leaving them failing means the full default suite has had 2 (of 7,325) known-red tests since V1.5-A landed, silently, because nothing in V1.5-A/B/C's own scope required running the *full* backend suite (only the frontend changed) — the gap was only surfaced now because V1.6/Groq touches `eidos.providers`, warranting a full run.
- **Not done:** no test file was changed. `.env.backend.local` (a real leftover credential scratch file from the V1.5-C QA pass, unrelated to either guard's design intent) *was* deleted as ordinary cleanup — that resolved a third, transient failure (a `PermissionError` on a locked `frontend/.next/dev/lock` file from a still-running dev server, also stopped) that was never a real secret-exposure finding.
- **Owner's call:** how these two guards should be updated for a repository that now legitimately has a frontend — e.g., `test_nothing_deferred_was_built` could drop `frontend` from its checked-directory list (the other five — `web`, `k8s`, `kubernetes`, `deploy`, `worker` — still correctly assert nothing was deferred-then-built) and gain an assertion that *only* the files V1.6's own Docker work adds exist, if any; the environment-file guard could exempt exactly `frontend/.env.local.example` by relative path rather than by bare filename. Both are narrow, mechanical fixes once the owner confirms the intended scope, but they are edits to a security-guard test, which is not this session's call to make unprompted.
- **Resolution — the actual root cause was neither guard's assertion, but its *source of files*.** Both scanned the raw filesystem (`ROOT.rglob("*")`), which cannot distinguish "real but gitignored" (`frontend/.env.local`, `frontend/.next/*`, `frontend/node_modules/*` — none ever a commit risk) from "actually committed or committable." Fixed by making both git-aware: a new `_committable_files()` (`tests/unit/service/test_service_guards.py`) runs `git ls-files --cached --others --exclude-standard -z` from `ROOT`, which is exactly the universe `git status`/`git add .` would show, and automatically honours every nested `.gitignore` — `frontend/.gitignore`'s own `node_modules`, `.next/`, and `.env*`/`!.env.local.example` rules apply with no EIDOS-side knowledge of the frontend's own tooling needed. This is a **strengthening**, not a weakening: it would catch a genuinely risky new file *before* `git add`, which the old raw walk also did, but now correctly stops flagging files that were never a commit risk in the first place.
  - `test_nothing_deferred_was_built`: `frontend` removed from the forbidden-directory list (the other five directories, and every top-level Docker/Render file, are unchanged and still enforced) — its docstring rewritten to state its real, ongoing job ("nothing got built before the owner decided it should be", checked against what is *currently* decided) rather than read as a frozen V1.4-B snapshot. A new `test_the_one_approved_exception_to_the_above_is_frontend_and_nothing_else_snuck_in_beside_it` pins the exception itself: `frontend/` must be the real thing (asserts `frontend/src/app/page.tsx` exists, not an empty placeholder), and no Docker/Render file may quietly ride in alongside it.
  - `test_no_environment_or_key_file_is_in_the_tree_and_the_ignore_file_keeps_it_that_way`: rewritten over `_committable_files()`; a new, narrow `_ALLOWED_ENV_FILES = {"frontend/.env.local.example"}` is the *only* exception, matched by exact relative path (not by bare filename, so a same-named file anywhere else would still correctly fail). A new `test_the_one_allowed_env_template_is_named_explicitly_tracked_and_itself_holds_no_secret` regression-tests the exception itself: the allow-list names exactly one file, that file is genuinely tracked by git (`git ls-files --error-unmatch`, not just present on disk), and — independently — its content holds no real secret shape.
  - `test_no_credential_key_token_or_password_url_is_committed` (the content-secrets scan) shares `_repository_files()`, now also built over `_committable_files()`; this incidentally fixed the `PermissionError` it hit on a locked `frontend/.next/dev/lock` file (a build artifact with no extension, previously in-scope by accident since its `""` suffix matched the allowed set) — the file was never a candidate for a secrets scan in the first place once ignored files are excluded. `_repository_files()`'s allowed-suffix set also gained `.example`, so the one allowed template is now itself covered by the content scan (it was not, before, since `.example` was not a recognised suffix) — closing a real, small pre-existing gap rather than just working around it.
  - `_SKIP_DIRECTORIES` was kept as a defensive second layer (every entry in it is independently confirmed already gitignored, so this is now a no-op in practice, not a load-bearing mechanism) rather than removed, to keep the change narrowly scoped to what D-236 actually required.
- **Validation:** the full default suite — 7,328 passed, 76 deselected, **0 failures** (up from 7,323 passed / 2 known-red before this fix, and from 6,163–6,164 in the two intermediate runs while `.env.backend.local` and a locked dev-server file were still present). No test was weakened, skipped or deleted; four tests were added, none removed. No file outside `tests/unit/service/test_service_guards.py` (plus this record) was touched.

### D-235 — Groq as a second model provider, alongside Ollama (ACCEPTED 2026-09-28; IMPLEMENTED)

- **Status:** Accepted · **Date:** 2026-09-28 · **Raised by:** the owner, while scoping V1.6 (Docker + deployment) — Render cannot reasonably host Ollama itself, and D-234's own V1.4-C note #7 had already flagged "only one model adapter exists; a hosted model provider is a deployment-time decision." · **Decided by:** the owner, in full: the exact target shape (a `ModelProvider` boundary, `OllamaProvider`/`GroqProvider`), the constraint list (16 numbered requirements), and the explicit exclusions (no dynamic selection, no provider learning or routing, no frontend model selector).
- **Source:** the owner's V1.6 brief; its Groq-specific revision; invariant 9 (models sit behind a capability interface); D-135 (the `ModelPort` seam); D-136 (standard library only, no vendor SDK).
- **Decision (owner):** add `GroqModel` beside the existing `OllamaModel`, both implementing the **already-sufficient** `eidos.agents.ModelPort` Protocol — no new abstraction was needed, because `ModelPort` was already the smallest clean provider boundary (D-135, V0.4). Ollama stays local-development's adapter, unchanged; Groq (`https://api.groq.com/openai/v1`, OpenAI-compatible chat completions) is production's, selected the same way Ollama always was: `EIDOS_MODEL_PROVIDER=groq`, with `GROQ_API_KEY` required only for that provider and read *only* by `eidos.api.main` (the composition root), never by `eidos.providers.groq` itself — matching how every other setting already reaches an adapter as an explicit constructor argument, never an ambient read (D-135).
- **What "the smallest clean implementation" turned out to mean:** nothing outside `eidos.providers` and `eidos.api.main` changed. `eidos.service.composition.Composition.prepare` already wraps *whichever* `ModelPort` it is given with `StorableModel` (NUL-safety) then `RecordingModel`/`ModelCallTracker` (the mechanism that turns a call into a recorded `ModelCallFacts` on `NODE_SETTLED`) — entirely by interface, with zero knowledge of which adapter is underneath. So requirements 11 and 12 (preserve tracking; record provider/model metadata through the existing mechanism) were already satisfied *by the existing architecture*, without a single line of `eidos.service` or `eidos.recording` touched. Groq's four failure modes (bad/expired key, unknown model, rate limit, malformed answer) map onto the same four `ModelFailureKind` values Ollama already uses — no new kind was added; a rate limit is `UNAVAILABLE` ("the provider... answered with an error"), exactly as the existing vocabulary already means it.
- **What changed:** `src/eidos/providers/groq.py` (new — the adapter, ~140 lines, stdlib `urllib` only, structured identically to `ollama.py`); `src/eidos/providers/factory.py` (`KNOWN_PROVIDERS` gains `"groq"`; `model_port` gains an optional `api_key` kwarg, ignored by `ollama`, required and validated for `groq`); `src/eidos/providers/__init__.py` (exports `GroqModel`); `src/eidos/api/main.py` (reads `GROQ_API_KEY` from its own environment argument, forwards it — the docstring gained one paragraph). No change to `eidos.agents`, `eidos.service`, `eidos.recording`, `eidos.state`, `eidos.api.app`, or any HTTP-exposed contract.
- **Tests:** `tests/integration/providers/test_groq_adapter.py` (mirrors `test_ollama_adapter.py`'s coverage over the same `FakeRuntime` harness: request shape, response parsing, every `ModelFailureKind`, thread safety, transport-error mapping, no-default-config); `tests/unit/providers/test_factory.py` (the provider-selection boundary itself — new); `tests/integration/providers/test_groq_real.py` (an explicit opt-in, gated on a real `GROQ_API_KEY`, registered as pytest marker `groq` and excluded from the default run exactly like `real_model`/`postgres` — never skips, fails loudly if selected without a key, per CLAUDE.md section 6); `tests/unit/api/test_api_main.py` gained Groq-specific configuration-refusal and never-echoes-the-key cases; `tests/unit/providers/test_providers_guards.py`'s ambient-environment/no-default-endpoint check was generalized from "just `ollama.py`" to every adapter module (so it now also covers `groq.py`), and gained a marker-registration check mirroring `real_model`'s. All existing Ollama tests pass unchanged (requirements 1–2). No new dependency and no new optional extra (`test_the_provider_added_no_dependency_and_no_extra` passes unchanged) — Groq speaks HTTP directly via `urllib`, the same choice `OllamaModel` already made (D-136).
- **Not done, on purpose:** no dynamic provider selection, learning or routing (owner's explicit exclusion); no frontend change of any kind (the frontend never touches model configuration); no backend API/contract change; no change to planning, execution or verification. **Not exercised:** the real Groq API (`test_groq_real.py` requires a real key the owner has not yet supplied in this session; it is designed to fail loudly, not silently pass, if ever selected without one).

- **Status:** Accepted · **Date:** 2026-09-26 · **Raised by:** Claude Code (V1.4-A) · **Decided by:** human owner, for the frozen direction, the API list, the runner, the `run_status` vocabulary and the knowledge and limits rules; the details below were Claude Code's proposal; on 2026-09-27 the owner accepted the eight endpoints exactly, the `Idempotency-Key` behaviour and the 409 and 503 semantics, and replaced the proposed static knowledge base with an optional one (no production knowledge-base choice in V1.4, D-227 not reopened, no Qdrant).
- **Source:** the owner's V1.4 briefs; invariants 1, 2, 7, 9, 10, 13, 14 and 15; D-052, D-085, D-127, D-135, D-156, D-160, D-201, D-227; `docs/13` sections 1 and 6 to 9.
- **Decision (owner):** the flow is HTTP and FastAPI, then an application and service layer, then the EIDOS runtime, then `EventLog`, `MissionState`, execution and evidence, then PostgreSQL persistence. **FastAPI does not mutate `MissionState`, and the database is not the runtime authority.** The API is exactly `POST /v1/missions`, `POST /v1/missions/{id}/start`, `GET /v1/missions/{id}`, `GET /v1/missions/{id}/execution`, `GET /v1/missions/{id}/events`, `GET /v1/missions/{id}/result`, `GET /v1/missions/{id}/evidence` and `GET /v1/healthz`; no list, cancel, replay or strategy-view endpoint yet. The runner is a **bounded in-process worker pool**, with one execution at a time per mission and no separate worker service. **`run_status` is API-level and separate from `MissionStatus`** (created, queued, running, finished, rejected, interrupted, error), **never enters `MissionState`**, and crash recovery may mark a run `interrupted` **without fabricating a `MISSION_FAILED` event**. **Knowledge:** no Qdrant; V1.3 semantic retrieval remains available through the existing `KnowledgePort`; V1.4 uses the simplest configuration that needs no production knowledge-base management; D-227 is not reopened. **Limits:** EIDOS budget enforcement is not redesigned; provisional server and API safety ceilings are defined separately from the `ReliabilityContract`, reject rather than clamp, are labelled provisional, and are not pretended to equal runtime budget enforcement.
- **Proposed (`docs/13`, pending confirmation):** (1) Three new packages and one dependency direction: `eidos.api` (FastAPI, the JWT library, error mapping; reads response types only), `eidos.service` (the application service, `RunManager`, the per-run composition, the repository Protocols and in-memory implementations; no FastAPI, JWT or driver), `eidos.persistence` (psycopg adapters; imports the service Protocols); the core imports none of them; guards in the pattern of the existing ones; new optional extras `api` and `postgres` (no dependency is added by this phase). A synchronous stack throughout, because the runtime is synchronous. (2) The transitions of `run_status`, all compare-and-set and by `RunManager` only: `created` to `queued` to `running`, then `finished`, `rejected` (`ReplanRejection`, nothing recorded, D-201) or `error`; `interrupted` at startup only. `finished` says the run ended, and what the mission came to is `mission_status` read from the folded log. `error` also covers a log that is not the whole story (`refused` or `discrepancies` not empty, D-160). (3) The API contracts and failure semantics of `docs/13` sections 7 and 8: an API failure and a mission failure never share a channel, so a failed or paused mission is a `200` that describes it and an API error is never an event; responses reuse `ExecutionRecord`, `EventRecord` and `EvidenceAudit`; the result is the verdict word for word and the artifacts of the plan's sink work steps, with no confidence and no score. (4) **Knowledge configuration:** at most one static knowledge base per deployment, a configured directory served by the in-process lexical retriever behind `KnowledgePort` and `KnowledgeGate`, shared read-only by every tenant (so it holds only what every tenant may read), and refused at startup if invalid; without one, missions work from supplied documents. Semantic wiring (interpreter and model paths, worker lifetime, environment logging, index persistence) stays deferred under D-227. No tool and no MCP server is wired. (5) The admission guard is a trivial always-admit guard that enforces no budget (D-127, D-156). There is no wall-clock cap, because a running thread cannot be preempted; each model and tool call keeps its own timeout and the plan's shape limits and `max_replans` bound the rest; cancel and a meaningful run timeout are deferred together. (6) The experience store is per mission and in memory, with the deterministic selector, so nothing is learned across missions and nothing leaks across tenants; a tenant-scoped store is a later decision. (7) The model comes from a factory in `eidos.providers` chosen by configuration, so no vendor name enters `eidos.service` or `eidos.api` (D-135).
- **Confirmed (owner, 2026-09-27), except where the Implemented note below says otherwise:** the API details (the definition of the result's artifacts, the `Idempotency-Key`, the 409 and 503 codes), the static knowledge base, the per-mission experience store, and the implementation order of `docs/13` section 11 (V1.4-B the tracker, V1.4-C the service and persistence, V1.4-D the API and authentication, V1.4-E the close-out), with the new optional dependencies approved at the step that needs each.
- **Effect (V1.4-A):** documentation only.
- **Implemented (V1.4-B, 2026-09-27):** the eight endpoints exactly (`eidos.api.app`; a test pins the route set and that list, cancel, replay, strategy-view, the interactive docs and every other path do not exist), the `Idempotency-Key` behaviour, the 409 and 503 semantics, the bounded in-process `RunManager` (`eidos.service.runner`: a thread pool; compare-and-set `run_status` transitions, so one run per mission holds across two processes too because the compare-and-set is in the database; startup recovery marking `queued` and `running` runs `interrupted` and writing no event; a bounded queue and a per-tenant limit; the checks of `start` are made in the order `not_startable`, `tenant_run_limit`, `busy`) and the failure semantics (a failed mission is a 200; an API failure is never an event; a run that could not be persisted is an `error` run and never a fabricated `MISSION_FAILED`). Route handlers are plain `def`; only the body reader, the exception handlers and the lifespan are `async`. **Changes to the V1.4-A proposal, by the owner:** (1) no static knowledge base and no loader: knowledge is optional, a deployer may hand `Composition` a `KnowledgeProvision` (a descriptor and a `KnowledgePort`), `eidos.api.main` configures none, and no production knowledge-base choice is made; (2) the implementation order of `docs/13` section 11 is replaced by the one phase, V1.4-B. **Choices made under the accepted architecture, not separately confirmed (`docs/13` section 12.2):** the per-mission in-memory experience store; the always-admit admission guard, labelled as enforcing no budget; the sequential reference executor only (the LangGraph executor is not wired); the whole-execution evidence view (D-231); fixed sentences for service faults and exception-type-only `run_status_reason` values with the detail logged server-side (a test found that an unsanitised storage message would have reached the caller and the `run_status_reason`); a 413 for a body over the limit whether or not it declares its length; the model provider chosen by configuration through `eidos.providers.factory.model_port` (only `ollama` exists); and a one-method structural `RetrievalPort` in `eidos.service.composition` in place of an import of `eidos.knowledge` (the knowledge guard admits three boundary modules only and is unchanged).
- **Raised for the owner (V1.4-B, 2026-09-27; raised, not decided; none blocks anything):** (1) **With no knowledge base the evidence view says nothing was retrieved.** `audit_evidence` calls a citation evidence only when a retrieval recorded it (D-209, D-228), so a citation of a supplied document is `not_evidence`, `GET .../evidence` returns those traces and no evidence text, and the verification still counts the cited sources. Whether the audit should treat a cited supplied document as evidence of its own kind is a core (D-209) question; nothing was changed. (2) **The default `execution_record` is the last plan's steps** (D-231); a core question, nothing changed. (3) **Provisional numbers stay provisional:** the API ceilings, `SystemLimits` (D-046, D-103), the runner bounds, the flush retry and the 10-second database timeouts. (4) **One API process per database:** multi-instance operation needs leases and heartbeats (deferred); startup recovery marks every active run interrupted and assumes no other process is running one. (5) **An idempotency key lives as long as its mission row** (no expiry). (6) **Nothing was run against a live Supabase project:** the JWT and connection facts come from Supabase's documentation as read on 2026-09-26 and the PostgreSQL tests ran on a disposable local PostgreSQL 16.2. (7) **Only one model adapter exists** (`ollama`); a hosted model provider is a deployment-time decision. (8) **D-204 item 2** (`tool_calls_used` per plan) stays Open and deferred.
- **V1.4-C acceptance audit (2026-09-27): a bounded hardening and close-out pass over the V1.4-B implementation. No decision status changes.** Six genuine implementation defects were found and fixed (all confined to `eidos.service` and `eidos.api`, no core file changed): a NUL character reaching PostgreSQL was an unhandled 500, and a model's answer holding one ended its run in error with a short prefix (fixed at the door and at the model port, `eidos.service.spec.UNSTORABLE` and `eidos.service.composition.StorableModel`); the framework's own 404 and 405 answered outside this API's one error shape (a new `method_not_allowed` code, section 8 updated); a transient storage fault exactly when a run started or ended was a single try (`RunManager`'s own transitions now retry with the flush's own bound); a shared HS256 secret below the 32-byte RFC 7518 minimum was accepted (now refused at startup); and two behaviours (a concurrent-create race decided by the database's unique constraint, and awkward-but-storable text round-tripping unchanged on real PostgreSQL) were confirmed correct under real concurrency and pinned by new tests. Everything else the audit checked was reconfirmed with no change: D-231's tracker propagation, the import boundaries (an independent AST audit at `e6bcb1a` and at this commit finds the same three package edges V1.4-B found, none from a core layer), tenant isolation and cross-tenant 404, idempotency, the write-through model and replay, restart and interrupted-run recovery under a real process kill, the bounded runner's one-execution-per-mission guarantee under real concurrency, the API-error/mission-failure separation, and no confidence or score in any answer; a repository-wide scan found no credential, key, token or connection string with a password. The eight limitations raised above (D-234's note, this entry) were each checked against the audit's findings and left exactly as documented: none had a concrete correctness or security failure, so none was changed, per the owner's brief. 22 new default tests and 9 new opt-in PostgreSQL tests (31 total); the full default suite passed under two hash seeds (7,255 passed, 74 deselected, up from 7,233 and 65 at V1.4-B); the full opt-in PostgreSQL suite (40 tests, up from 31) passed once against a disposable local PostgreSQL 16.2, never against a Supabase project. `docs/13` section 12.6 has the full account. Mutation testing not run: no acceptance criterion required it.
