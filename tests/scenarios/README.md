# tests/scenarios

**Layer definition (handoff §62):** full missions, replanning, verification failures, budget
exhaustion, policy violations.

Scenario tests run a whole mission and assert on its outcome and its recorded history. They are the
tests that prove the *product* behaves as specified, not just that the parts work.

## What belongs here

| Scenario | Asserts | Milestone |
|---|---|---|
| Baseline mission completes end-to-end | The §49 MVP chain: task → genome → candidates → validation → execution → evaluation → history | V0.4 |
| Verification fails, replan, retrieve more, verify again | Invariant 12; plan v2 with recorded lineage and reason (§15, §43) | V0.4+ |
| Reliability contract cannot be met | Invariant 13 — reports "cannot satisfy", does **not** return a confident-looking answer (§30, §47) | V1.2 |
| Retry budget exhausted | Invariant 7 — `MISSION PAUSED`, human review required (§32) | V1.2 |
| Replan budget exhausted | Invariant 7 | V1.2 |
| Token budget exhausted | Invariant 7 | V1.2 |
| Tool budget exhausted | Invariant 7 | V1.2 |
| Policy violation | Invariant 14 — deterministic refusal, not a prompt-level refusal (§29) | V1.2 |
| Bad retrieval / conflicting evidence | §63; evidence rejected rather than used | V0.8 |
| Replay from recorded events | Invariant 15 — the mission timeline reconstructs with **no agent invoked** (§73) | V0.5 |
| Evidence lineage | Invariant 16 — conclusion walks back to source and retrieval query (§74) | V0.8 |

## Rules

- A scenario test asserts on the recorded history, not only the final answer. "It returned
  something" is not a passing condition (invariant 12). **No event history exists until V0.5**
  (D-123: V0.3 emits no `MissionEvent`; invariant 15 is not exercised), so V0.3 scenarios assert on the
  `RunResult` — every node's status and reason, and the dispatch order — and on what the ports were asked.
  Once events exist, scenarios assert on them.
- No fabricated fixtures presented as measurements. A scenario may use fixed inputs; it may not
  bake in a quality score and call it measured (CLAUDE.md §7).

## V0.3 scenarios (built)

These drive a real `MissionState` through V0.2 validation, the compiler, a frozen execution context and **both**
executors (`tests/support/eidos_scenario_factories.py`: `drive` asserts the LangGraph backend returns exactly what
the reference executor does). Work, verification and admission are scripted test doubles — there are no product
mock agents — so they prove the pipeline and the meaning of a run, not any agent's quality. They need the
`langgraph` extra (part of `dev`) and fail loudly without it.

| File | Scenarios | Invariants and decisions exercised |
|---|---|---|
| `test_v03_baseline_mission.py` | A mission from state to a finished, verified run; the ports are asked only what the plan requires; the mission state is read and never written; a finished run with no `VERIFY` is unverified; the empty plan; wide plans; repeatability | 1, 2, 5, 12; D-106, D-113, D-117, D-123 |
| `test_v03_verification_and_replanning.py` | A failed, inconclusive or crashed verification fails the run; no usable result; a crashing agent is contained; a replan is a new, separately validated plan with lineage, and nothing carries over from the old run | 6, 12; D-085, D-118, D-119, D-120, D-121 |
| `test_v03_halt_and_resume.py` | An exhausted budget halts and pauses (never loops, never truncates); halt outranks failure; a broken guard fails closed; resume over succeeded outcomes matches an uninterrupted run; no automatic retry | 7, 14; D-119, D-120, D-122 |
| `test_v03_plan_gates.py` | Invalid plans, rule-breaking plans, non-DSL documents and unsupported step kinds are stopped before any executor is reached; a forged acceptance does not compile a broken plan | 3, 5, 13; D-112, D-114 |
| `test_v03_determinism.py` | A whole story (fail, replan, halt, resume) serializes to identical bytes under different `PYTHONHASHSEED`s | CLAUDE.md §8 (deterministic components) |

### V0.4 scenarios (built)

Real Research, Analysis and Verification agents over a **scripted** model, run through `eidos.baseline.run_baseline` on both executors;
`drive_baseline` (`tests/support/eidos_v04_factories.py`) asserts the two reports are byte-identical. No real model is involved.

| File | Scenarios | Invariants and decisions exercised |
|---|---|---|
| `test_v04_baseline.py` | The baseline finishes verified from supplied documents; a PASS names what was NOT_EVALUATED and never claims contract satisfaction; well-formed output that cites a source that does not exist fails verification; too few sources, no citations and a failed verification gating what follows; a model outage, an empty answer and a raising adapter are contained; nothing supplied means nothing to research; an unbound capability stops at binding, an invalid plan at validation and an unsupported kind at compilation, each before any agent is called; halt then resume without asking the research model again; a replan needs fresh step ids and reuse is refused, not overwritten; a different research implementation and an unrelated domain need no core change | 3, 5, 9, 10, 11, 12, 14; D-131 to D-140, D-144 to D-146 |
| `test_v04_determinism.py` | A whole V0.4 mission (verified, failed verification, unbound, halt and resume) serializes to identical bytes under different `PYTHONHASHSEED`s | CLAUDE.md §8 (deterministic components) |

**Not exercised by these, by scope:** replay (invariant 15, V0.5), evidence lineage (invariant 16, V0.8), the reliability
contract being unmet (invariant 13 as a mission outcome, V1.2), and real budgets and policy (V1.2). The halt scenarios use a
guard the test wrote; no budget is enforced by the runtime.
