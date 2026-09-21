"""Scenario: recording a baseline pass on both executors (decisions.md D-152, D-158, D-160; V0.5 Step 5b).

The recording adapters sit outside the runtime, so which executor runs the plan must not change what the log says. Over a fixed clock and
scripted models, the reference executor and the LangGraph executor must give the same serialized log for a linear plan, byte for byte, and
the same *set* of events for a plan with parallel branches, whose interleaving is the one thing a backend may change (D-158 item 6). Each log
must replay to the state the recorder's own log holds, and each recorded report must equal the report an unrecorded run gives.
"""

import pytest

from eidos.backends.langgraph import LangGraphExecutor
from eidos.runtime import SequentialExecutor
from eidos.state import replay, replay_jsonl

from eidos_backend_factories import locked_admit_all, locked_halt_when
from eidos_mission_factories import make_mission, make_mission_plan
from eidos_recording_factories import FixedClock, SequentialIds, baseline_mission, record, respond_with_facts, unrecorded

EXECUTORS = [SequentialExecutor, LangGraphExecutor]
IDS = ["reference", "langgraph"]


def recorded(state, plan, executor, *, guard=None, respond=None):
    guard = guard if guard is not None else (locked_admit_all() if executor is LangGraphExecutor else None)
    run, _ = record(state, plan, executor=executor, guard=guard, respond=respond, clock=FixedClock(), ids=SequentialIds())
    assert run.refused == () and run.discrepancies == ()  # the log is the whole story
    return run


def both(state, plan, **kwargs):
    reference, backend = (recorded(state, plan, executor, **kwargs) for executor in EXECUTORS)
    return reference, backend


def test_a_linear_plan_gives_a_byte_identical_log_on_both_executors():
    state, plan = baseline_mission()
    reference, backend = both(state, plan)
    assert backend.log.to_jsonl() == reference.log.to_jsonl()
    assert backend.report == reference.report
    assert backend.log.state == reference.log.state


@pytest.mark.parametrize("executor", EXECUTORS, ids=IDS)
def test_each_executors_log_replays_to_its_own_state_and_to_the_report_of_an_unrecorded_run(executor):
    state, plan = baseline_mission()
    run = recorded(state, plan, executor)
    guard = locked_admit_all() if executor is LangGraphExecutor else None
    assert run.report == unrecorded(state, plan, executor=executor, guard=guard)
    replayed = replay_jsonl(run.log.to_jsonl())
    assert replayed.rejection is None and replayed.state == run.log.state
    assert replayed.state == replay(run.log.records).state


def test_a_run_that_fails_verification_gives_the_same_log_on_both_executors():
    state, plan = baseline_mission()
    reference, backend = both(state, plan, respond=respond_with_facts(analysis="Cites a [[ghost]] source."))
    assert backend.log.to_jsonl() == reference.log.to_jsonl()
    assert reference.log.records[-1].payload.cause.value == "verification_failed"


def test_a_run_halted_by_the_admission_guard_gives_the_same_log_on_both_executors():
    state, plan = baseline_mission()
    reference = recorded(state, plan, SequentialExecutor, guard=locked_halt_when(lambda request: request.step_id == "analyse", "held"))
    backend = recorded(state, plan, LangGraphExecutor, guard=locked_halt_when(lambda request: request.step_id == "analyse", "held"))
    assert backend.log.to_jsonl() == reference.log.to_jsonl()
    assert reference.log.records[-1].payload.halt.reason == "held"


def test_parallel_branches_give_the_same_events_on_both_executors_whatever_their_interleaving():
    state = make_mission(capabilities=("research", "cost"))
    plan = make_mission_plan(state, {"one": "", "two": "", "three": ""}, capability_of={"one": "research", "two": "research", "three": "research"})
    reference, backend = both(state, plan)

    def payloads(run):
        return sorted(record_.payload.model_dump_json() for record_ in run.log.records)

    assert payloads(backend) == payloads(reference)
    assert backend.report == reference.report
    assert [r.event.sequence for r in backend.log.records] == list(range(1, len(backend.log.records) + 1))  # contiguous, whatever the order
    final, expected = backend.log.state, reference.log.state
    for name in ("status", "agent_calls_used", "tool_calls_used", "tokens_used", "execution_time_used_ms", "retries_used", "replans_used"):
        assert getattr(final, name) == getattr(expected, name), name
    assert replay_jsonl(backend.log.to_jsonl()).state == final
