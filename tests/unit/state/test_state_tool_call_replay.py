"""Tool-call facts through replay, the JSONL form, telemetry and experience, and hash-seed determinism (decisions.md D-203, D-160; V1.2 Step 3).

A recorded tool interaction must replay to the same state and the same facts from the log alone, with no tool and no tool machinery involved; a log
written before the field existed must replay identically; the existing telemetry and experience fields must carry the counter with no new contract;
and everything must serialise to the same bytes whatever the interpreter's hash seed.
"""

import functools
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from eidos.state import (
    ExecutionRecord,
    dump_jsonl,
    execution_record,
    load_jsonl,
    replay,
    replay_jsonl,
)
from eidos.memory import ExecutionExperience, evaluate_experience
from eidos.telemetry import TelemetryRecord, project

from eidos_planning_factories import make_strategy
from eidos_state_factories import T0, baseline_state_and_plan, LogBuilder, verify_result, verified_baseline, work_result
from eidos_tool_fact_factories import denied_call, failed_call, result_call, served_call, settle_with_tools

ROOT = Path(__file__).resolve().parents[3]


def tool_using_log() -> LogBuilder:
    """A finished, verified mission in which the two work nodes make five tool calls between them: three invocations, a served duplicate, a denial."""
    state, plan = baseline_state_and_plan()
    log = LogBuilder(state, plan)
    log.created(), log.generated(), log.compiled()
    log.started("gather")
    settle_with_tools(log, work_result("gather"), (result_call(number=1, documents=2), failed_call(number=2), served_call(number=1, documents=2)))
    log.started("analyse")
    settle_with_tools(log, work_result("analyse"), (result_call(number=3, documents=0, result_bytes=0), denied_call()))
    log.started("check")
    log.settled(verify_result("check"))
    log.completed(verified=True)
    return log


# --- replay reproduces the facts and the counter from the log alone ---------------------------------------------------------------


def test_replay_reproduces_the_counter_and_every_step_fact_from_the_recorded_log_alone():
    log = tool_using_log()
    replayed = replay(log.records)
    assert replayed.state is not None and replayed.state.tool_calls_used == 3
    record = execution_record(log.records)
    assert record.tool_calls_used == 3
    gather, analyse, check = record.steps
    assert [c.outcome.value for c in gather.tool_calls] == ["result", "timeout", "served_stored"]
    assert [c.outcome.value for c in analyse.tool_calls] == ["result", "denied"]
    assert check.tool_calls == ()


def test_the_jsonl_form_round_trips_every_recorded_fact_exactly():
    log = tool_using_log()
    text = dump_jsonl(log.records)
    loaded = load_jsonl(text)
    assert loaded.rejection is None and loaded.records == tuple(log.records)
    assert dump_jsonl(loaded.records) == text
    assert replay_jsonl(text).state == replay(log.records).state
    assert execution_record(loaded.records) == execution_record(log.records)


def test_the_served_duplicate_stays_distinguishable_from_the_invocation_it_repeats():
    record = execution_record(tool_using_log().records)
    first, _, duplicate = record.steps[0].tool_calls
    assert (first.args_digest, first.result_refs) == (duplicate.args_digest, duplicate.result_refs)  # the same request, the same stored answer
    assert first.invoked and not duplicate.invoked  # but one reached a tool and one did not
    assert first.elapsed_ms is not None and duplicate.elapsed_ms is None


def test_a_log_written_before_the_field_existed_replays_to_the_identical_state_and_record():
    log = verified_baseline()
    text = dump_jsonl(log.records)
    assert text.count('"tool_calls":[]') == 3  # every NODE_SETTLED of the baseline writes the new field, empty
    old_text = text.replace(',"tool_calls":[]', "")
    assert '"tool_calls"' not in old_text
    assert replay_jsonl(old_text).state == replay_jsonl(text).state == replay(log.records).state
    assert execution_record(load_jsonl(old_text).records) == execution_record(log.records)


REPLAY_WITHOUT_TOOLS = r"""
import json, sys
sys.path.insert(0, 'src')
from eidos.state import replay_jsonl, load_jsonl, execution_record

text = sys.stdin.read()
replayed = replay_jsonl(text)
record = execution_record(load_jsonl(text).records)
loaded = sorted(m for m in sys.modules if m.startswith(('eidos.agents', 'eidos.policy', 'eidos.mcp', 'eidos.recording', 'eidos.capabilities', 'eidos.providers', 'eidos.a2a')))
print(json.dumps({
    "used": replayed.state.tool_calls_used,
    "steps": [[c.outcome.value for c in step.tool_calls] for step in record.steps],
    "loaded": loaded,
}))
"""


def test_replay_needs_no_tool_no_policy_no_transport_and_no_agent_only_the_log():
    text = dump_jsonl(tool_using_log().records)
    completed = subprocess.run([sys.executable, "-c", REPLAY_WITHOUT_TOOLS], input=text, capture_output=True, text=True, cwd=ROOT)
    assert completed.returncode == 0, completed.stderr
    answer = json.loads(completed.stdout.strip().splitlines()[-1])
    assert answer["used"] == 3
    assert answer["steps"] == [["result", "timeout", "served_stored"], ["result", "denied"], []]
    assert answer["loaded"] == []  # nothing that could invoke a tool was so much as imported


# --- telemetry and experience: the existing fields carry the counter, and nothing was added ----------------------------------------


def test_telemetry_carries_the_counter_through_its_existing_field():
    log = tool_using_log()
    telemetry = project(log.records)
    assert isinstance(telemetry, TelemetryRecord) and telemetry.tool_calls_used == 3
    scoped = project(log.records, plan_id=log.plan.plan_id)
    assert scoped.tool_calls_used == 3  # D-204 item 2: the whole-mission total, however scoped


def test_experience_copies_the_counter_through_its_existing_field():
    log = tool_using_log()
    experience = evaluate_experience(make_strategy(), log.state.task_genome, project(log.records), recorded_at=T0)
    assert isinstance(experience, ExecutionExperience) and experience.tool_calls_used == 3


def test_telemetry_and_experience_gained_no_tool_field_the_integration_is_additive():
    for model in (TelemetryRecord, ExecutionExperience, ExecutionRecord):
        assert [name for name in model.model_fields if "tool" in name] == ["tool_calls_used"], model.__name__


def test_a_tool_free_mission_reports_zero_through_every_layer():
    log = verified_baseline()
    assert execution_record(log.records).tool_calls_used == project(log.records).tool_calls_used == 0
    assert evaluate_experience(make_strategy(), log.state.task_genome, project(log.records), recorded_at=T0).tool_calls_used == 0


# --- determinism ----------------------------------------------------------------------------------------------------------------

STORY = r"""
import hashlib, sys
sys.path[:0] = ['src', 'tests/support']
from eidos.state import dump_jsonl, execution_record, replay
from eidos.telemetry import project
from eidos_state_factories import LogBuilder, baseline_state_and_plan, verify_result, work_result
from eidos_tool_fact_factories import denied_call, failed_call, result_call, served_call, settle_with_tools
from eidos.state import ToolCallOutcome

state, plan = baseline_state_and_plan()
log = LogBuilder(state, plan)
log.created(), log.generated(), log.compiled()
log.started("gather")
settle_with_tools(log, work_result("gather"), (result_call(number=1, documents=3), failed_call(ToolCallOutcome.UNAVAILABLE, number=2, elapsed_ms=None), served_call(number=1, documents=3)))
log.started("analyse")
settle_with_tools(log, work_result("analyse"), (denied_call(), result_call(number=3, documents=0, result_bytes=0)))
log.started("check")
log.settled(verify_result("check"))
log.completed(verified=True)

digest = hashlib.sha256()
digest.update(dump_jsonl(log.records).encode())
digest.update(replay(log.records).state.model_dump_json().encode())
digest.update(execution_record(log.records).model_dump_json().encode())
digest.update(project(log.records).model_dump_json().encode())
print(digest.hexdigest())
"""


@functools.cache
def story_digest(hash_seed: str) -> str:
    completed = subprocess.run(
        [sys.executable, "-c", STORY], capture_output=True, text=True, cwd=ROOT, env=dict(os.environ, PYTHONHASHSEED=hash_seed),
    )
    assert completed.returncode == 0, completed.stderr
    digest = completed.stdout.strip().splitlines()[-1]
    assert len(digest) == hashlib.sha256().digest_size * 2
    return digest


@pytest.mark.parametrize("other_seed", ["1", "42", "112233", "2718281828"])
def test_the_recorded_facts_the_state_and_every_projection_serialise_to_the_same_bytes_under_any_hash_seed(other_seed):
    assert story_digest(other_seed) == story_digest("0")
