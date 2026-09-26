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
| Replay from recorded events | Invariant 15 — the mission timeline reconstructs with **no agent invoked** (§73) | V0.5 (built) |
| Evidence lineage | Invariant 16 — conclusion walks back to source and retrieval query (§74) | V0.8 (built at V1.3, `test_rag_mission.py`) |

## Rules

- A scenario test asserts on the recorded history, not only the final answer. "It returned
  something" is not a passing condition (invariant 12). **No event history exists until V0.5**
  (D-123: V0.3 emits no `MissionEvent`; invariant 15 is not exercised), so V0.3 scenarios assert on the
  `RunResult` — every node's status and reason, and the dispatch order — and on what the ports were asked.
  Since V0.5 events exist (`eidos.state`, `eidos.recording`), and the V0.5 scenarios assert on them.
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
`drive_baseline` (`tests/support/eidos_v04_factories.py`) asserts the two reports are byte-identical. No real model is involved; the real-model baseline is an opt-in integration test, not a scenario
(`tests/integration/providers/test_ollama_real.py`), and its recorded results are in progress.md.

| File | Scenarios | Invariants and decisions exercised |
|---|---|---|
| `test_v04_baseline.py` | The baseline finishes verified from supplied documents; a PASS names what was NOT_EVALUATED and never claims contract satisfaction; well-formed output that cites a source that does not exist fails verification; too few sources, no citations and a failed verification gating what follows; a model outage, an empty answer and a raising adapter are contained; nothing supplied means nothing to research; an unbound capability stops at binding, an invalid plan at validation and an unsupported kind at compilation, each before any agent is called; halt then resume without asking the research model again; a replan needs fresh step ids, and reuse is refused before any model call and never overwritten (D-147), while same-plan resume is unaffected; the recorded limitation that an analysis step cannot follow a `VERIFY` step (D-148); a different research implementation and an unrelated domain need no core change | 3, 5, 9, 10, 11, 12, 14; D-131 to D-140, D-144 to D-146 |
| `test_v04_determinism.py` | A whole V0.4 mission (verified, failed verification, unbound, halt and resume) serializes to identical bytes under different `PYTHONHASHSEED`s | CLAUDE.md §8 (deterministic components) |

**Not exercised by the V0.3 and V0.4 scenarios, by scope:** replay (invariant 15; the V0.5 scenarios below do), evidence lineage (invariant 16, V0.8), the reliability
contract being unmet (invariant 13 as a mission outcome, V1.2), and real budgets and policy (V1.2). The halt scenarios use a
guard the test wrote; no budget is enforced by the runtime.

### V0.5 scenarios (built)

The recorder (`eidos.recording`) runs the real V0.4 agents over a **scripted** model with a fixed clock and sequential ids, and every case is run on **both** executors
(`tests/support/eidos_v05_cases.py` holds the cases, so the scenarios and the hash-seed story cannot drift apart). The cases: the verified baseline, an unverified finish, a failed verification,
a model timeout, an empty response, a plan refused at each of the three gates, and an admission halt. No real model is involved, and every number here is a fixed test value, not a measurement.

| File | Scenarios | Invariants and decisions exercised |
|---|---|---|
| `test_v05_recording_backends.py` | The reference and LangGraph executors give a byte-identical serialized log for a linear plan, a failed verification and an admission halt, and the same *set* of events (contiguous sequence) for parallel branches; the recorded report equals an unrecorded run's; the execution record is the same on both | 1, 2, 8, 15; D-152, D-158, D-159, D-160 |
| `test_v05_chain.py` | For every case on both executors: the log is the whole story (nothing refused, nothing contradicted, one terminal event, contiguous sequence); it folds to the expected status, cause, verified flag and counters; it serializes and replays to the live state; a checkpoint at every sequence plus the tail equals the full replay; the `ExecutionRecord` is the same live and replayed; a refused plan records no node; a paused mission is resumed by a new pass over its successes; a fresh interpreter replays the text without loading an agent, provider, backend, baseline runner, capability registry or recorder; the whole story is byte-identical under different `PYTHONHASHSEED`s | 1, 2, 8, 12, 15; D-152 to D-160, CLAUDE.md §8 |

**Not exercised by the V0.5 scenarios, by scope:** evidence lineage (invariant 16: no evidence, source or retrieval query is recorded until V0.8), estimates and prediction error (invariant 17), a real model (recording it is an opt-in test the owner has not asked for), a mission driver, a replan loop, `AgentTask` mirroring and A2A events, and any budget
enforced against the counters.

### V1.3 scenarios (built)

The retrieval-augmented mission and the frozen retrieval benchmark (D-208 to D-228). The mission scenario runs the real knowledge gate, ledger, recording wrappers, verification and replay over a scripted model and either the semantic retriever behind the real process boundary (the real worker program over a stub model) or the exact lexical retriever; no number in it is a measurement. The benchmarks pin what was measured on the frozen fixture and judge nothing.

| File | Scenarios | Invariants and decisions exercised |
|---|---|---|
| `test_rag_mission.py` | Mission, Research, the knowledge gate, a retriever, the evidence ledger, a cited result, Analysis and the existing verification, recorded and replayed: completion, the retrieval recorded as the port answered it, no evidence text in the log, every citation traced from the log alone to the retrieved chunk, byte-for-byte determinism, replay with a process, a socket, the retriever, the gate and the worker made impossible and in a fresh interpreter with the retrieval stack and every model library unimportable; the failure paths (each retrieval failure, an empty or wrong answer, a raising port, a worker that is gone, a citation nobody retrieved); a duplicate query served from storage; and two named known-limitation tests (D-228.1, D-228.2) | Invariants 1, 12, 15, 16; D-217, D-218, D-225, D-226, D-228 |
| `test_rag_mission_real_model.py` (`-m real_model`) | The same mission with the real pinned model behind the process boundary on the frozen fixture for one development query; asserts the path and judges nothing about retrieval | D-226, D-227, D-228 |
| `test_retrieval_benchmark_lexical.py` | The frozen fixture and the lexical baseline, pinned | D-208, D-213, D-225 |
| `test_retrieval_benchmark_semantic.py` (`-m real_model`) | The semantic measurement on the same frozen fixture, pinned; declares no winner | D-208, D-213, D-226, D-227 |

**Not exercised by the V1.3 scenarios, by scope:** a query ceiling and any knowledge budget (invariant 7, deferred, D-228.4), a verdict that counts independent sources (invariant 13, a known limitation, D-228.1), and the recording of a port that raises (D-228.3).
