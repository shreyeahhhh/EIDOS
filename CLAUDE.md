# CLAUDE.md — EIDOS

Permanent rules for this repository. These do not change as the project advances.
Status lives in progress.md. Decisions and open questions live in decisions.md.

## 0. Authority
- `EIDOS_CLAUDE_CODE_HANDOFF.md` is the canonical product and architecture specification.
  Never modify it.
- `docs/` is the derived engineering knowledge base. It translates the handoff into
  implementation-level contracts and rules. Docs must not contradict the handoff.
- If the handoff and docs conflict, stop and report the conflict to the human owner.
  Do not decide which source wins.
- If code and docs conflict, stop and report. Do not silently "fix" either side.
- The human owner is the architect: product decisions, architecture, contracts, research questions,
  tradeoffs, scope and acceptance criteria are theirs. Claude Code does implementation, tests,
  debugging, refactoring, documentation, experiments and review.
- Propose; do not decide. Never redesign architecture, contracts, invariants or scope unilaterally.

## 1. Session start
Read in order: CLAUDE.md -> progress.md -> decisions.md -> the docs/ files relevant to the task.

## 2. Architecture invariants — never violate
1.  MissionState is the only authoritative global state. Nothing else is global truth.
2.  Only the state reducer mutates MissionState. Agents never mutate it. Remote agent state stays
    remote and is mirrored into EIDOS solely as AgentTask records.
3.  The LLM emits a bounded Plan DSL document and nothing else. It never emits executable code,
    Python, or LangGraph graph construction — under any circumstance.
4.  The canonical internal representation of a plan is an ID-addressed DAG: every step has an
    explicit id, and every dependency is an explicit edge. Validation and compilation operate only
    on that form. Any nested or tree-shaped surface syntax is optional sugar and must be normalized
    into the DAG before validation.
5.  No plan executes unvalidated. Order: schema -> dependencies -> cycles -> capabilities -> policy
    -> resources -> complexity limits -> compile.
6.  Plans are immutable and versioned. A live graph is never mutated in place. Replanning produces
    plan vN+1 with recorded lineage and a recorded reason.
7.  Execution is bounded: max_nodes, max_depth, max_parallel_branches, max_retries, max_replans,
    max_agent_calls, max_tool_calls, max_execution_time. Exhaustion pauses the mission for human
    review. It never loops, never silently truncates, never retries forever.
8.  Events are idempotent. Duplicates are ignored; late or out-of-order events are accepted or
    rejected deterministically against the lifecycle. Every event carries identity, ordering and
    timestamp fields.
9.  The runtime is model-independent. No model, vendor or SDK name appears in contracts, planning,
    validation, compiler, runtime or state. Models sit behind a capability interface.
10. The runtime is domain-agnostic. No domain workflow is hardcoded into it.
11. Plans request capabilities, not named agents. Capability-to-agent binding happens at selection
    time.
12. Verification is separate from completion. "An agent returned output" is never success.
13. The reliability contract is enforced. If it cannot be met, EIDOS reports that it cannot be met.
    Never manufacture confidence in order to produce an answer.
14. Governance is deterministic. "Can perform" and "is allowed to perform" are separate checks,
    enforced in code, never by prompt.
15. Every meaningful execution step emits a structured event, and a completed mission is replayable
    from recorded events without re-running agents.
16. Conclusions are traceable: conclusion -> evidence -> source -> retrieval query -> agent -> tool
    -> verification.
17. Estimates are labelled as estimates, carry uncertainty, and prediction error is recorded
    separately from outcomes.
18. Identifiers (tenant_id, mission_id, execution_id, plan_id, agent_id, event_id, timestamp) exist
    in data models from the start. Authentication and multi-tenancy are implemented later.

Any change touching an invariant requires explicit human approval and an entry in decisions.md.

## 3. Scope control
- Build core-outward, never bottom-up.
- One component, one change, one acceptance condition. Never "build EIDOS".
- Do not add a technology, dependency, service, protocol, agent or tool before the milestone that
  needs it.
- Do not create a package, module or directory before the milestone that fills it. Future
  architecture is documented, not scaffolded.
- Do not exceed three logical agents (Research, Analysis, Verification) without approval.
- Do not exceed the 2-3 approved MCP tools without approval.
- Do not generate an unbounded number of candidate strategies. Two or three.
- Prefer deletion and simplification over new files, layers and frameworks.

## 4. Workflow for every change
EXPLORE -> PLAN -> IMPLEMENT -> TEST -> VERIFY -> COMMIT
- Explore and plan without modifying files. State affected invariants, files, tests, failure modes.
- Implement only the approved plan. No unrelated refactors.
- Run focused tests, then the full suite.
- Update progress.md, decisions.md and docs/ before committing.

## 5. Definition of done
Implementation exists + tests exist + tests pass + integration works + invariants hold + failure
cases covered + documentation matches reality + a git checkpoint exists. Nothing less is done.

## 6. Testing
- tests/unit — schemas, validators, reducers, scoring, policy
- tests/integration — runtime, storage, external components
- tests/protocol — A2A/MCP lifecycle, idempotency, timeouts, failure events
- tests/scenarios — full missions, replanning, verification failure, budget exhaustion, policy
  violation
- Write failure-path tests, not only happy paths.
- Never weaken a test, delete a failing test, skip it, or suppress an error to get green.
  Report the failure instead.
- Tests are the objective verifier. "Implemented successfully" is not evidence.

## 7. Honesty and ambiguity
- Never resolve an architectural ambiguity, contradiction or gap silently. Record it in decisions.md
  as Open and raise it with the human owner. This applies even when a default looks obvious, and
  even when the gap is small. A silent default is a violation, not a shortcut.
- No fabricated numbers. Every metric in any document, README or report comes from an actual
  recorded run.
- Never present a placeholder, an estimate, or a model-asserted score as a measurement.
- Report blockers, partial work and skipped scope explicitly.

## 8. Code
- Python, src layout, package `eidos`. Pydantic v2 for all contracts.
- Contracts are typed, validated and versioned. No untyped dicts cross a module boundary.
- Core layers (contracts, validation, compiler, runtime, state) must not import agent, provider,
  protocol or storage implementations.
- Deterministic components (validator, compiler, reducer, policy) stay deterministic: no I/O,
  no network, no LLM calls, no hidden global state, no wall-clock dependence in logic.

## 9. Context hygiene
When context becomes hard to manage: update progress.md and decisions.md, ensure tests pass, commit,
then start a fresh session. Project state must survive a context change.

## 10. Subagents
Use for independent exploration, research, test review and parallel investigation. Subagents must
not redefine EIDOS architecture. The main session integrates their findings.

## 11. Before any change, answer
What problem does this solve? Which document defines it? Which invariant does it affect? What is the
smallest implementation? What tests prove it? What failure cases exist? Can it be demonstrated with
a real execution trace?

Optimize for correctness, clarity, boundedness, observability, measurability, reliability and
architectural coherence — never for number of files, frameworks, agents or features.
