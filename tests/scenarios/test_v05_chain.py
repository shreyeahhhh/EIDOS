"""Scenarios: the whole V0.5 chain, for every way a recorded baseline pass can end (decisions.md D-152 to D-160).

Execution -> events -> log -> serialized JSONL -> replay -> ``MissionState`` and ``ExecutionRecord``, on **both** executors, over the real V0.4
agents and a scripted model (no real model, and no number here is a measurement). Each case is the verified baseline, an unverified finish, a
failed verification, two model failures, a plan refused at each of the three gates, and an admission halt. For every one the scenario asserts what
the mission came to, and that the same events fold, serialize, replay, checkpoint and project consistently; that the log is the whole story (nothing
refused, nothing contradicted); and that a fresh interpreter replays the serialized log without loading an agent, a provider or a backend.
"""

import functools
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from eidos.contracts import MissionEventType, MissionStatus, PlanStepKind
from eidos.runtime import PriorOutcomes
from eidos.state import (
    Checkpoint,
    ExecutionRecord,
    checkpoint_at,
    dump_jsonl,
    execution_record,
    load_jsonl,
    records_after,
    replay,
    replay_jsonl,
    resume,
)

from eidos_recording_factories import unrecorded
from eidos_v05_cases import CASE_IDS, CASES, EXECUTOR_IDS, EXECUTORS, Case, guard_for, run_case

ROOT = Path(__file__).resolve().parents[2]
TERMINAL = {MissionEventType.MISSION_COMPLETED, MissionEventType.MISSION_FAILED, MissionEventType.MISSION_PAUSED}


def everywhere():
    return pytest.mark.parametrize("executor", EXECUTORS, ids=EXECUTOR_IDS), pytest.mark.parametrize("case", CASES, ids=CASE_IDS)


def apply(test):
    for mark in everywhere():
        test = mark(test)
    return test


@apply
def test_the_recorded_log_is_the_whole_story_and_folds_to_the_outcome_the_case_should_have(case: Case, executor):
    run, _ = run_case(case, executor)
    assert run.refused == () and run.discrepancies == ()  # nothing was refused and nothing was contradicted
    log = run.log
    assert [r.event.sequence for r in log.records] == list(range(1, len(log) + 1))  # contiguous from 1
    assert len({r.event.event_id for r in log.records}) == len(log)
    types = [r.event.type for r in log.records]
    assert types[0] is MissionEventType.MISSION_CREATED and types[-1] in TERMINAL and sum(t in TERMINAL for t in types) == 1  # one terminal event, and last
    assert log.state.status is MissionStatus(case.status) and log.state.status_reason.startswith(case.reason)


@apply
def test_the_serialized_log_replays_to_the_live_state_and_the_recorded_pass_is_the_pass_nothing_recorded(case: Case, executor):
    run, rig = run_case(case, executor)
    text = run.log.to_jsonl()
    assert text == dump_jsonl(run.log.records) and text.endswith("\n") and "\r" not in text
    replayed = replay_jsonl(text)
    assert replayed.rejection is None and replayed.state == run.log.state == replay(run.log.records).state
    state, plan = case.mission()
    plain = unrecorded(state, plan, respond=case.respond, guard=guard_for(case), executor=executor)
    assert run.report.model_dump_json() == plain.model_dump_json()  # recording changed nothing about the pass


@apply
def test_a_checkpoint_at_every_sequence_plus_the_tail_equals_the_full_replay(case: Case, executor):
    run, _ = run_case(case, executor)
    records, full = run.log.records, run.log.state
    for sequence in range(1, len(records) + 1):
        checkpoint = checkpoint_at(records, sequence)
        assert isinstance(checkpoint, Checkpoint) and checkpoint.last_sequence == sequence
        assert resume(checkpoint, records_after(records, checkpoint)).state == full
    middle = checkpoint_at(records, max(1, len(records) // 2))
    assert Checkpoint.model_validate_json(middle.model_dump_json()) == middle  # a checkpoint is a value: it survives serialization


@apply
def test_the_execution_record_says_what_the_case_came_to_and_is_the_same_live_and_replayed(case: Case, executor):
    run, _ = run_case(case, executor)
    live = execution_record(run.log.records)
    assert isinstance(live, ExecutionRecord)
    loaded = load_jsonl(run.log.to_jsonl())
    assert loaded.rejection is None and execution_record(loaded.records) == live
    assert (live.mission_status.value, live.failure_cause, live.verified) == (case.status, case.cause, case.verified)
    assert (live.run_outcome.value if live.run_outcome else None) == case.run_outcome
    assert tuple(s.result.status.value for s in live.steps if s.result) == case.node_statuses
    assert live.event_count == len(run.log)
    assert all((s.agent_id is not None) == (s.kind is PlanStepKind.AGENT and s.started) for s in live.steps)  # each agent step that started names its agent; nothing else does
    assert (live.agent_calls_used, live.tokens_used, live.execution_time_used_ms) == (case.agent_calls, case.tokens, case.time_ms)
    state = run.log.state
    assert (state.agent_calls_used, state.tokens_used, state.execution_time_used_ms) == (case.agent_calls, case.tokens, case.time_ms)
    assert (state.tool_calls_used, state.retries_used, state.replans_used) == (0, 0, 0)  # nothing produces these at V0.5


def test_a_refused_plan_records_no_node_and_no_run_and_says_which_gate_refused_it():
    for name, gate in (("plan_refused_at_validation", "validation"), ("plan_refused_at_compilation", "compilation"), ("plan_refused_at_binding", "binding")):
        case = next(c for c in CASES if c.name == name)
        for executor in EXECUTORS:
            run, rig = run_case(case, executor)
            record = execution_record(run.log.records)
            assert record.plan_rejected_at.value == gate and record.plan_rejection_reasons
            assert all(not step.started and step.result is None for step in record.steps)
            assert rig.scripted.requests == []  # nothing reached the model


def test_a_paused_mission_is_resumed_by_a_new_pass_over_the_first_passes_successes_and_each_log_stands_alone():
    case = next(c for c in CASES if c.name == "admission_halt")
    resumed_case = Case(name="resumed", mission=case.mission, verified=True, node_statuses=("succeeded", "succeeded", "succeeded"))
    for executor in EXECUTORS:
        first, rig = run_case(case, executor)
        second, _ = run_case(resumed_case, executor, prior=PriorOutcomes.succeeded_from(first.report.run), rig=rig)
        assert first.log.state.status is MissionStatus.PAUSED  # paused is terminal in V0.5: the pause is not reopened
        carried = execution_record(second.log.records)
        gather = next(s for s in carried.steps if s.step_id == "gather")
        assert (gather.dispatched, gather.started, gather.duration_ms, gather.model_calls) == (False, False, None, ())  # carried over, not run again
        assert (carried.mission_status, carried.verified, carried.agent_calls_used) == (MissionStatus.COMPLETED, True, 1)
        assert replay_jsonl(second.log.to_jsonl()).state == second.log.state and replay_jsonl(first.log.to_jsonl()).state == first.log.state


# --- a completed mission replays without re-running anything -----------------------------------------------------------------


REPLAY_ALONE = r"""
import hashlib, sys
sys.path[:0] = ['src']
from eidos.state import execution_record, load_jsonl, replay_jsonl
text = sys.stdin.read()
replayed = replay_jsonl(text)
assert replayed.rejection is None, replayed.rejection
record = execution_record(load_jsonl(text).records)
# Anything that executes work. The pure core layers the state package is built on (the contracts, the runtime's types, the compiler and the
# validator) are loaded and are not in this list: they run nothing.
loaded = sorted(m for m in sys.modules if m.startswith(('eidos.agents', 'eidos.providers', 'eidos.backends', 'eidos.baseline', 'eidos.recording',
                                                          'eidos.capabilities'))
                or m.split('.')[0] in ('langgraph', 'langchain', 'requests', 'httpx'))
print(hashlib.sha256(replayed.state.model_dump_json().encode()).hexdigest(), hashlib.sha256(record.model_dump_json().encode()).hexdigest())
print(loaded)
"""


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_a_fresh_interpreter_replays_the_serialized_log_without_loading_an_agent_a_provider_or_a_backend(case: Case):
    run, _ = run_case(case, EXECUTORS[1])
    completed = subprocess.run([sys.executable, "-c", REPLAY_ALONE], input=run.log.to_jsonl(), capture_output=True, text=True, cwd=ROOT)
    assert completed.returncode == 0, completed.stderr
    digests, loaded = completed.stdout.strip().split("\n")
    state_digest = hashlib.sha256(run.log.state.model_dump_json().encode()).hexdigest()
    record_digest = hashlib.sha256(execution_record(run.log.records).model_dump_json().encode()).hexdigest()
    assert digests == f"{state_digest} {record_digest}"  # the same state and the same record, rebuilt from the text alone
    assert loaded == "[]"  # replay loaded no agent, provider, backend, baseline runner, capability registry or recorder: it re-ran nothing (invariant 15)


# --- determinism across interpreters ----------------------------------------------------------------------------------------------------

STORY = r"""
import hashlib, sys
sys.path[:0] = ['src', 'tests/support']
from eidos_v05_cases import CASES, EXECUTORS, run_case
from eidos.state import execution_record

digest = hashlib.sha256()
for case in CASES:
    for executor in EXECUTORS:
        run, _ = run_case(case, executor)
        digest.update(run.log.to_jsonl().encode())
        digest.update(run.log.state.model_dump_json().encode())
        digest.update(execution_record(run.log.records).model_dump_json().encode())
print(digest.hexdigest())
"""


@functools.cache
def story_digest(hash_seed: str) -> str:
    completed = subprocess.run(
        [sys.executable, "-c", STORY], capture_output=True, text=True, cwd=ROOT, env={**os.environ, "PYTHONHASHSEED": hash_seed}
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def test_every_case_on_both_executors_gives_the_same_log_state_and_record_under_different_hash_seeds():
    digests = {seed: story_digest(seed) for seed in ("0", "1", "2", "12345")}
    assert len(set(digests.values())) == 1 and len(next(iter(digests.values()))) == 64
