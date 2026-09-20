"""Scenarios: nothing reaches execution unless it passed every gate (V0.3).

Invariant 5: no plan executes unvalidated. Invariant 3: what the planner emits is a bounded Plan DSL document
and nothing else — never code. A plan is untrusted text until V0.2 has accepted it, the compiler has accepted
that evidence, and only a ``CompiledPlan`` can be run: there is no path to execution that skips a gate.

Each scenario drives a plan that should be stopped and asserts *where* it stopped and *why*, and that no
executor and no port was ever reached.
"""

import json

import pytest
from pydantic import ValidationError

from eidos.compiler import CompileFailureCode, compile_plan
from eidos.contracts import Plan, PlanStepKind
from eidos.validation import StageStatus, ValidationStage, ViolationCode, validate_plan_json

from eidos_compiler_factories import forged_accepted_report
from eidos_factories import make_agent_step, make_plan
from eidos_scenario_factories import drive, make_mission, make_mission_plan
from eidos_validation_factories import make_system_limits


def assert_stopped_before_execution(attempt, *, violation_code=None):
    assert not attempt.report.accepted
    assert not attempt.compile_report.succeeded and attempt.compiled is None
    # The compiler refuses the evidence, and may add what it found in the plan itself.
    assert CompileFailureCode.VALIDATION_NOT_ACCEPTED in [v.code for v in attempt.compile_report.violations]
    assert attempt.context is None and attempt.result is None and not attempt.ran
    assert attempt.work.calls == [] and attempt.verifier.calls == [] and attempt.guard.requests == []
    if violation_code is not None:
        assert violation_code in [v.code for v in attempt.report.violations]


# --- V0.2 stops a plan that breaks a rule ----------------------------------------------------------------------------


def invalid_cases():
    state = make_mission()
    tight_contract = make_mission(max_agent_calls=2)
    three_agents = {"a": "", "b": "", "c": ""}
    return [
        pytest.param(
            state, make_mission_plan(state, {"a": "b", "b": "a"}), {}, ViolationCode.CYCLE_DETECTED, id="a cycle"
        ),
        pytest.param(
            state,
            make_mission_plan(state, {"a": ""}, capability_of={"a": "billing"}),
            {},
            ViolationCode.CAPABILITY_NOT_REQUIRED,
            id="a capability the mission never asked for",
        ),
        pytest.param(
            state,
            make_mission_plan(state, {"a": "", "b": "a", "c": "b", "d": "c"}),
            dict(max_nodes=3),
            ViolationCode.MAX_NODES_EXCEEDED,
            id="more nodes than max_nodes",
        ),
        pytest.param(
            state,
            make_mission_plan(state, {"a": "", "b": "a", "c": "b"}),
            dict(max_depth=2),
            ViolationCode.MAX_DEPTH_EXCEEDED,
            id="deeper than max_depth",
        ),
        pytest.param(
            state,
            make_mission_plan(state, three_agents),
            dict(max_parallel_branches=2),
            ViolationCode.MAX_PARALLEL_BRANCHES_EXCEEDED,
            id="wider than max_parallel_branches",
        ),
        pytest.param(
            tight_contract,
            make_mission_plan(tight_contract, three_agents),
            {},
            ViolationCode.AGENT_CALLS_EXCEEDED,
            id="more agent calls than the mission's own contract allows",
        ),
        pytest.param(
            state,
            make_mission_plan(make_mission(seed=2), {"a": ""}),
            {},
            ViolationCode.PLAN_MISSION_MISMATCH,
            id="a plan for another mission",
        ),
    ]


@pytest.mark.parametrize("state, plan, limit_overrides, code", invalid_cases())
def test_a_plan_that_breaks_a_rule_is_stopped_by_validation_and_nothing_runs(state, plan, limit_overrides, code):
    attempt = drive(state, plan, limits=make_system_limits(**limit_overrides))

    assert_stopped_before_execution(attempt, violation_code=code)


def test_a_plan_that_could_not_be_fully_checked_is_not_accepted():
    # Invariant 13: a stage that did not run is SKIPPED, never PASSED — and an unchecked plan never runs.
    state = make_mission()
    plan = make_mission_plan(state, {"a": "b", "b": "a"})  # a cycle leaves the graph stages unable to run

    attempt = drive(state, plan)

    assert attempt.report.result_for(ValidationStage.CYCLE).status is StageStatus.FAILED
    assert not attempt.report.fully_evaluated
    assert_stopped_before_execution(attempt)


# --- the planner's output is text, and only the Plan DSL is accepted (invariant 3) ------------------------------------


def valid_document(state):
    plan = make_mission_plan(state, {"gather": "", "check": "gather"}, verify=("check",))
    return plan, json.loads(plan.model_dump_json())


def test_a_plan_document_is_accepted_only_as_the_plan_it_says_it_is():
    state = make_mission()
    plan, document = valid_document(state)

    report = validate_plan_json(json.dumps(document), state, make_system_limits())

    assert report.accepted and report.plan_id == plan.plan_id
    assert drive(state, Plan.model_validate_json(json.dumps(document)), report=report).result.verified is True


@pytest.mark.parametrize(
    "corrupt, code",
    [
        pytest.param(lambda d: d["steps"][0].update(code="import os; os.system('x')"), ViolationCode.SCHEMA_VIOLATION,
                     id="a step smuggling in executable code"),
        pytest.param(lambda d: d["steps"][0].update(kind="python"), ViolationCode.SCHEMA_VIOLATION,
                     id="a step of a kind that does not exist"),
        pytest.param(lambda d: d.update(graph="StateGraph()"), ViolationCode.SCHEMA_VIOLATION,
                     id="a document carrying a graph construction"),
    ],
)
def test_a_document_that_is_more_than_the_plan_dsl_is_rejected_and_never_becomes_a_plan(corrupt, code):
    state = make_mission()
    _, document = valid_document(state)
    corrupt(document)

    report = validate_plan_json(json.dumps(document), state, make_system_limits())

    assert not report.accepted
    assert code in [v.code for v in report.violations]
    assert report.plan_id is None  # no plan was ever constructed from it
    assert not report.fully_evaluated
    with pytest.raises(ValidationError):  # and there is nothing for the compiler to be handed
        Plan.model_validate_json(json.dumps(document))


def test_text_that_is_not_json_is_rejected():
    state = make_mission()

    report = validate_plan_json("steps: [gather]  # not a plan", state, make_system_limits())

    assert not report.accepted
    assert [v.code for v in report.violations] == [ViolationCode.MALFORMED_JSON]


# --- V0.2 can accept a plan the compiler will not compile (D-112) ------------------------------------------------------


@pytest.mark.parametrize(
    "kind",
    [
        PlanStepKind.ROUTE,
        PlanStepKind.RETRY,
        PlanStepKind.REPLAN,
        PlanStepKind.TERMINATE,
        PlanStepKind.HUMAN_APPROVAL,
    ],
)
def test_a_valid_plan_with_a_step_kind_v03_does_not_execute_is_refused_at_compile_time(kind):
    # Rejected, never silently dropped or reinterpreted: an unsupported step is not something to run around.
    state = make_mission()
    plan = make_mission_plan(state, {"a": "", "x": "a", "b": "x"}, controls={"x": kind})

    attempt = drive(state, plan)

    assert attempt.report.accepted  # V0.2 has no quarrel with it
    assert not attempt.compile_report.succeeded and attempt.compiled is None
    assert [v.code for v in attempt.compile_report.violations] == [CompileFailureCode.UNSUPPORTED_STEP_KIND]
    assert attempt.compile_report.violations[0].step_ids == ("x",)
    assert not attempt.ran
    assert attempt.work.calls == [] and attempt.verifier.calls == [] and attempt.guard.requests == []


def test_a_forged_acceptance_does_not_get_a_broken_plan_compiled():
    # The compiler does not take V0.2's word for a plan's structure (D-114): it checks what it depends on.
    state = make_mission()
    plan = make_plan(
        tenant_id=state.tenant_id,
        mission_id=state.mission_id,
        steps=(make_agent_step("a", depends_on=("b",)), make_agent_step("b", depends_on=("a",))),
    )

    compiled = compile_plan(plan, forged_accepted_report(plan))

    assert not compiled.succeeded
    assert [v.code for v in compiled.violations] == [CompileFailureCode.DEPENDENCY_CYCLE]
