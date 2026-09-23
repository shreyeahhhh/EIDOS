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

### D-028 — Agentic RAG and Qdrant deferred to V0.8

- **Status:** Deferred · **Source:** handoff §24, §25, §26, §50
- Documented in `docs/09_rag_architecture.md`. §25 notes the collection schema "should be designed
  later". No Qdrant, embedding model, reranker, dependency or package exists.
- **Annotated 2026-09-22 (D-184):** V0.8 is now the Strategy Selector (V0.7 Step 1's own naming); RAG no longer
  has a reserved milestone number. It stays Deferred, unassigned, until a concrete requirement or benchmark needs it.

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
