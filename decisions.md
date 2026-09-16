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

---

## Open — require the human owner

These are ambiguities, contradictions and gaps found in the handoff during the bootstrap read. None
has been resolved. Work that depends on one of them is blocked until the owner decides.

Count: 22. Highest-impact first is **D-015** (how verification confidence is computed), then
**D-010**, **D-013**, **D-011** and **D-009**.

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

### D-009 — Execution bound values and where bounds originate

- **Status:** Open · **Source:** handoff §14, §30, §32
- **Finding:** Every budget dimension is named — `max_nodes`, `max_depth`,
  `max_parallel_branches`, `max_retries`, `max_replans`, `max_agent_calls`, `max_tool_calls`,
  `max_execution_time` — but **no default values are given**, and the handoff does not say whether
  bounds come from static policy configuration, from the per-mission ReliabilityContract, from the
  Task Genome, or from a combination.
- **Needs:** Source of authority for each bound, and starting values. Blocks resource validation and
  complexity-limit validation (§14).

### D-010 — MissionState field set, reducer signature, checkpoint semantics

- **Status:** Open · **Source:** handoff §9, §10, §11, §33
- **Finding:** §9/§10 fix *ownership* (MissionState is sole authority; only the reducer writes it)
  and §33 names the event types, but the state shape is never enumerated, the reducer signature is
  never given, and checkpoint granularity/trigger is never specified.
- **Needs:** The field set, the reducer contract, and what a checkpoint contains. Blocks V0.1
  MissionState and V0.5 entirely.

### D-011 — Event ordering key and idempotency key

- **Status:** Open · **Source:** handoff §10
- **Finding:** §10 requires every external event to carry "sequence/version" and mandates idempotent
  processing, but does not define the ordering domain: a per-mission monotonic counter, a per-
  AgentTask counter, a per-producer counter, or a version vector. Nor does it define what
  constitutes the idempotency key (`event_id` alone, or `(a2a_task_id, sequence)`).
- **Needs:** Precise definition. Two different choices give two different duplicate/late-event
  semantics. Blocks the reducer and all protocol tests for duplicate, late and out-of-order events.

### D-012 — Predicate language for conditional primitives

- **Status:** Open · **Source:** handoff §13
- **Finding:** `ROUTE`, `RETRY`, `REPLAN` and `TERMINATE` are all conditional, and routing must be
  deterministic (§11, §29), but **no expression or predicate language is specified** for any of
  them. Without one, either the condition is opaque (breaking determinism and validation) or an
  expression language is invented.
- **Needs:** How a condition is expressed, what it may read from MissionState, and how it is
  validated. Blocks the compiler and the ROUTE primitive.

### D-013 — TaskGenome and ReliabilityContract overlap

- **Status:** Open · **Source:** handoff §6 vs §30
- **Finding:** `quality_threshold`, `latency_budget`, `resource_budget` and `autonomy_level` appear
  in the Task Genome (§6). Minimum quality, maximum latency, maximum tokens, maximum risk, minimum
  independent evidence and approval requirements appear in the Reliability Contract (§30). These
  overlap substantially and the relationship is never stated.
- **Needs:** Is the ReliabilityContract derived from the TaskGenome, a separate user input, or an
  authoritative override? Which wins on conflict? Blocks both V0.1 contracts.

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

### D-019 — Whether `tenant_id` appears in V0.1 models

- **Status:** Open · **Source:** handoff §54
- **Finding:** §54 says data models "should conceptually include" `tenant_id`, `mission_id`,
  `execution_id`, `agent_id`, `timestamp`, while also warning the MVP must not become an
  authentication project. Whether V0.1 contracts carry `tenant_id` as a real field now is not
  stated. Invariant 18 reads as yes, but that reading has not been confirmed.
- **Needs:** Confirmation. Cheap to include now, expensive to retrofit later.

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
