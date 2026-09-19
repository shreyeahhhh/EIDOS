"""The V0.2 pipeline end to end (decisions.md D-103, D-106, D-107, D-110; invariants 5, 13)."""

import inspect
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest

import eidos.validation as validation
from eidos.contracts import (
    CapabilityId,
    MissionId,
    PlanId,
    PlanStepKind,
    StepId,
    TenantId,
)
from eidos.validation import (
    StageStatus,
    ValidationStage,
    ViolationCode,
    validate_plan,
    validate_plan_json,
)

from eidos_factories import (
    make_agent_step,
    make_control_step,
    make_plan,
    make_reliability_contract,
    make_mission_state,
    make_task_genome,
)
from eidos_validation_factories import make_system_limits

STAGES = list(ValidationStage)


def state_and_plan(*, steps=None, contract=None, required=None, **plan_overrides):
    """A mission state and a plan that belongs to it. Defaults: one 'research' agent step."""
    contract = contract or make_reliability_contract()
    genome_overrides = {} if required is None else dict(required_capabilities=required)
    tenant_id = contract.tenant_id
    genome = make_task_genome(contract=contract, **genome_overrides)
    state = make_mission_state(
        tenant_id=tenant_id,
        reliability_contract=contract,
        task_genome=genome,
    )
    fields = dict(tenant_id=state.tenant_id, mission_id=state.mission_id)
    if steps is not None:
        fields["steps"] = steps
    fields.update(plan_overrides)
    return state, make_plan(**fields)


def statuses(report) -> dict:
    return {r.stage: r.status for r in report.stages}


def codes(report) -> list:
    return [v.code for v in report.violations]


# --- the happy path --------------------------------------------------------


def test_a_valid_plan_is_accepted_with_every_stage_evaluated():
    state, plan = state_and_plan()
    report = validate_plan(plan, state, make_system_limits())
    assert report.accepted and report.fully_evaluated
    assert report.plan_id == plan.plan_id
    assert report.violations == ()
    assert [r.stage for r in report.stages] == STAGES
    assert statuses(report) == {
        ValidationStage.SCHEMA: StageStatus.PASSED,
        ValidationStage.DEPENDENCY: StageStatus.PASSED,
        ValidationStage.CYCLE: StageStatus.PASSED,
        ValidationStage.CAPABILITY: StageStatus.PASSED,
        ValidationStage.POLICY: StageStatus.NOT_APPLICABLE,
        ValidationStage.RESOURCE: StageStatus.PASSED,
        ValidationStage.COMPLEXITY: StageStatus.PASSED,
    }


def test_the_json_entry_point_agrees_with_the_typed_entry_point():
    state, plan = state_and_plan()
    limits = make_system_limits()
    assert validate_plan_json(plan.model_dump_json(), state, limits) == validate_plan(plan, state, limits)


def test_policy_is_not_applicable_never_passed_in_every_kind_of_report():
    state, plan = state_and_plan()
    limits = make_system_limits()
    reports = [
        validate_plan(plan, state, limits),
        validate_plan_json("not json", state, limits),
        validate_plan_json('{"steps": 5}', state, limits),
    ]
    for report in reports:
        assert statuses(report)[ValidationStage.POLICY] is StageStatus.NOT_APPLICABLE


def test_an_empty_plan_passes_every_stage_that_can_run():
    state, plan = state_and_plan(steps=())
    limits = make_system_limits(max_nodes=0, max_depth=0, max_parallel_branches=0, max_agent_calls=0)
    for report in (
        validate_plan(plan, state, limits),
        validate_plan_json(plan.model_dump_json(), state, limits),
    ):
        assert report.accepted and report.fully_evaluated
        assert report.violations == ()


def test_control_steps_of_every_kind_pass_with_no_predicate_checks():
    # D-047: V0.1 carries no condition payload, so ROUTE/RETRY/etc. are only
    # structural nodes here.
    kinds = [k for k in PlanStepKind if k is not PlanStepKind.AGENT]
    steps = tuple(make_control_step(step_id=StepId(k.value), kind=k) for k in kinds)
    state, plan = state_and_plan(steps=steps, required=())
    assert validate_plan(plan, state, make_system_limits()).accepted


def test_a_realistic_branching_plan_is_accepted():
    steps = (
        make_agent_step(step_id=StepId("research")),
        make_agent_step(step_id=StepId("analysis"), depends_on=(StepId("research"),)),
        make_control_step(step_id=StepId("verify"), depends_on=(StepId("analysis"),)),
        make_control_step(
            step_id=StepId("route"), depends_on=(StepId("verify"),), kind=PlanStepKind.ROUTE
        ),
    )
    state, plan = state_and_plan(steps=steps)
    assert validate_plan(plan, state, make_system_limits()).accepted


# --- every stage failing at once ------------------------------------------


def test_all_failing_stages_are_reported_together_in_pipeline_order():
    steps = (
        make_agent_step(step_id=StepId("a"), depends_on=(StepId("b"),), capability=CapabilityId("bad")),
        make_agent_step(step_id=StepId("b"), depends_on=(StepId("a"),), capability=CapabilityId("bad")),
        make_agent_step(step_id=StepId("c")),
    )
    contract = make_reliability_contract(max_tokens=10**9)
    state, plan = state_and_plan(steps=steps, contract=contract)
    limits = make_system_limits(max_agent_calls=2, max_nodes=2)
    report = validate_plan(plan, state, limits)

    assert not report.accepted
    assert statuses(report) == {
        ValidationStage.SCHEMA: StageStatus.PASSED,
        ValidationStage.DEPENDENCY: StageStatus.PASSED,
        ValidationStage.CYCLE: StageStatus.FAILED,
        ValidationStage.CAPABILITY: StageStatus.FAILED,
        ValidationStage.POLICY: StageStatus.NOT_APPLICABLE,
        ValidationStage.RESOURCE: StageStatus.FAILED,
        ValidationStage.COMPLEXITY: StageStatus.FAILED,
    }
    assert codes(report) == [
        ViolationCode.CYCLE_DETECTED,
        ViolationCode.CAPABILITY_NOT_REQUIRED,
        ViolationCode.CAPABILITY_NOT_REQUIRED,
        ViolationCode.CONTRACT_EXCEEDS_CEILING,
        ViolationCode.AGENT_CALLS_EXCEEDED,
        ViolationCode.MAX_NODES_EXCEEDED,
    ]
    # violations are in stage order
    stage_positions = [STAGES.index(v.stage) for v in report.violations]
    assert stage_positions == sorted(stage_positions)


# --- context binding -------------------------------------------------------


def test_a_plan_of_another_mission_is_rejected_and_state_stages_are_skipped():
    state, plan = state_and_plan(steps=(make_agent_step(capability=CapabilityId("not_required")),))
    foreign = plan.model_copy(update={"mission_id": MissionId(uuid4())})
    report = validate_plan(foreign, state, make_system_limits())

    assert statuses(report) == {
        ValidationStage.SCHEMA: StageStatus.FAILED,
        ValidationStage.DEPENDENCY: StageStatus.PASSED,
        ValidationStage.CYCLE: StageStatus.PASSED,
        ValidationStage.CAPABILITY: StageStatus.SKIPPED,
        ValidationStage.POLICY: StageStatus.NOT_APPLICABLE,
        ValidationStage.RESOURCE: StageStatus.SKIPPED,
        ValidationStage.COMPLEXITY: StageStatus.PASSED,
    }
    # The wrong mission's genome was never consulted: no capability verdict at all.
    assert codes(report) == [ViolationCode.PLAN_MISSION_MISMATCH]
    assert not report.accepted and not report.fully_evaluated
    assert "does not belong to this mission" in report.result_for(ValidationStage.CAPABILITY).detail


def test_a_plan_of_another_tenant_is_rejected():
    state, plan = state_and_plan()
    foreign = plan.model_copy(update={"tenant_id": TenantId(uuid4())})
    report = validate_plan(foreign, state, make_system_limits())
    assert codes(report) == [ViolationCode.PLAN_TENANT_MISMATCH]
    assert statuses(report)[ValidationStage.CAPABILITY] is StageStatus.SKIPPED
    assert statuses(report)[ValidationStage.RESOURCE] is StageStatus.SKIPPED


def test_structural_stages_still_run_on_a_plan_of_another_mission():
    steps = (make_agent_step(step_id=StepId("s"), depends_on=(StepId("s"),)),)
    state, plan = state_and_plan(steps=steps)
    foreign = plan.model_copy(update={"mission_id": MissionId(uuid4())})
    report = validate_plan(foreign, state, make_system_limits())
    assert ViolationCode.CYCLE_DETECTED in codes(report)
    assert ViolationCode.PLAN_MISSION_MISMATCH in codes(report)


# --- the contract and the ceilings ----------------------------------------


def test_the_states_own_contract_is_checked_even_for_an_empty_plan():
    contract = make_reliability_contract(max_tokens=make_system_limits().max_tokens + 1)
    state, plan = state_and_plan(steps=(), contract=contract, required=())
    report = validate_plan(plan, state, make_system_limits())
    assert codes(report) == [ViolationCode.CONTRACT_EXCEEDS_CEILING]
    assert report.violations[0].limit_name.value == "max_tokens"


def test_the_states_required_capabilities_are_what_the_plan_is_checked_against():
    state, plan = state_and_plan(
        steps=(make_agent_step(capability=CapabilityId("analysis")),),
        required=(CapabilityId("analysis"),),
    )
    assert validate_plan(plan, state, make_system_limits()).accepted


# --- construction bypass: the dependency stage re-checks -------------------


def test_a_plan_with_duplicate_ids_built_without_validation_is_rejected_not_crashed():
    state, plan = state_and_plan()
    broken = plan.model_copy(
        update={"steps": (make_agent_step(step_id=StepId("d")), make_agent_step(step_id=StepId("d")))}
    )
    report = validate_plan(broken, state, make_system_limits())
    assert codes(report) == [ViolationCode.DUPLICATE_STEP_ID]
    assert statuses(report)[ValidationStage.CYCLE] is StageStatus.SKIPPED
    assert statuses(report)[ValidationStage.COMPLEXITY] is StageStatus.SKIPPED
    assert "undefined" in report.result_for(ValidationStage.CYCLE).detail
    assert statuses(report)[ValidationStage.CAPABILITY] is StageStatus.PASSED
    assert not report.accepted


def test_a_plan_with_a_dangling_dependency_built_without_validation_does_not_raise():
    state, plan = state_and_plan()
    broken = plan.model_copy(
        update={"steps": (make_agent_step(step_id=StepId("a"), depends_on=(StepId("ghost"),)),)}
    )
    report = validate_plan(broken, state, make_system_limits())
    assert codes(report) == [ViolationCode.UNKNOWN_DEPENDENCY]
    assert not report.accepted


# --- JSON ingress: attribution of construction failures --------------------


SHARED_STATE, SHARED_PLAN = state_and_plan()  # frozen, so safe to share across tests


def plan_document(**overrides) -> dict:
    """A valid plan document (for SHARED_STATE) as parsed JSON, for mutation into invalid ones."""
    document = json.loads(SHARED_PLAN.model_dump_json())
    document.update(overrides)
    return document


def run_json(document_or_text, state=None, limits=None):
    state = state or SHARED_STATE
    text = document_or_text if isinstance(document_or_text, str) else json.dumps(document_or_text)
    return validate_plan_json(text, state, limits or make_system_limits())


def assert_unbuilt(report, *, failed_stage):
    """Every stage after the failure is SKIPPED; POLICY stays NOT_APPLICABLE; no plan_id."""
    assert report.plan_id is None
    assert not report.accepted and not report.fully_evaluated
    assert statuses(report)[failed_stage] is StageStatus.FAILED
    for stage in (ValidationStage.CYCLE, ValidationStage.CAPABILITY, ValidationStage.RESOURCE, ValidationStage.COMPLEXITY):
        assert statuses(report)[stage] is StageStatus.SKIPPED
        assert "could not be constructed" in report.result_for(stage).detail
    assert statuses(report)[ValidationStage.POLICY] is StageStatus.NOT_APPLICABLE


@pytest.mark.parametrize("text", ["", "not json", "{", '{"steps": [', "nul", "{'single': 'quotes'}"])
def test_text_that_is_not_json_is_malformed_json(text):
    report = run_json(text)
    assert codes(report) == [ViolationCode.MALFORMED_JSON]
    assert_unbuilt(report, failed_stage=ValidationStage.SCHEMA)
    assert statuses(report)[ValidationStage.DEPENDENCY] is StageStatus.SKIPPED


@pytest.mark.parametrize("text", ["[]", "null", "123", '"a string"', "true"])
def test_valid_json_that_is_not_an_object_is_a_schema_violation_not_malformed(text):
    report = run_json(text)
    assert codes(report) == [ViolationCode.SCHEMA_VIOLATION]
    assert_unbuilt(report, failed_stage=ValidationStage.SCHEMA)


def test_a_missing_required_field_names_the_field():
    document = plan_document()
    del document["plan_id"]
    report = run_json(document)
    assert codes(report) == [ViolationCode.SCHEMA_VIOLATION]
    assert report.violations[0].message.startswith("plan_id:")
    assert_unbuilt(report, failed_stage=ValidationStage.SCHEMA)


def test_several_schema_errors_are_each_reported_in_document_order():
    report = run_json({"steps": 5})
    assert codes(report) == [ViolationCode.SCHEMA_VIOLATION] * 4
    assert [v.message.split(":")[0] for v in report.violations] == [
        "plan_id",
        "mission_id",
        "version",
        "steps",
    ]


def test_an_unknown_top_level_field_is_a_schema_violation():
    report = run_json(plan_document(surprise=1))
    assert codes(report) == [ViolationCode.SCHEMA_VIOLATION]
    assert report.violations[0].message.startswith("surprise:")


def test_version_zero_is_a_schema_violation():
    report = run_json(plan_document(version=0))
    assert codes(report) == [ViolationCode.SCHEMA_VIOLATION]
    assert report.violations[0].message.startswith("version:")


def test_a_json_string_for_an_integer_is_rejected_under_strict_mode():
    report = run_json(plan_document(version="1"))
    assert codes(report) == [ViolationCode.SCHEMA_VIOLATION]


@pytest.mark.parametrize("kind", ["SEQUENTIAL", "PARALLEL", "sequential", "parallel", "unknown", ""])
def test_sequential_and_parallel_are_not_step_kinds(kind):
    # D-050: ordering and parallelism are edges, not kinds.
    step = {"step_id": "s1", "depends_on": [], "kind": kind}
    report = run_json(plan_document(steps=[step]))
    assert codes(report) == [ViolationCode.SCHEMA_VIOLATION]
    assert report.violations[0].message.startswith("steps.0:")
    assert_unbuilt(report, failed_stage=ValidationStage.SCHEMA)


def test_a_control_step_carrying_a_capability_is_a_schema_violation():
    # D-049: unrepresentable, so rejected at the schema stage.
    step = {"step_id": "v", "depends_on": [], "kind": "VERIFY", "capability": "research"}
    report = run_json(plan_document(steps=[step]))
    assert codes(report) == [ViolationCode.SCHEMA_VIOLATION]
    assert report.violations[0].message.startswith("steps.0.VERIFY.capability:")


def test_an_agent_step_without_a_capability_is_a_schema_violation():
    step = {"step_id": "s1", "depends_on": [], "kind": "agent"}
    report = run_json(plan_document(steps=[step]))
    assert codes(report) == [ViolationCode.SCHEMA_VIOLATION]
    assert report.violations[0].message.startswith("steps.0.agent.capability:")


def test_a_step_missing_its_depends_on_is_a_schema_violation():
    step = {"step_id": "s1", "kind": "agent", "capability": "research"}
    assert codes(run_json(plan_document(steps=[step]))) == [ViolationCode.SCHEMA_VIOLATION]


def test_duplicate_step_ids_in_json_are_a_dependency_failure_not_a_schema_failure():
    steps = [
        {"step_id": "d", "depends_on": [], "kind": "agent", "capability": "research"},
        {"step_id": "d", "depends_on": [], "kind": "VERIFY"},
    ]
    report = run_json(plan_document(steps=steps))
    assert codes(report) == [ViolationCode.DUPLICATE_STEP_ID]
    assert report.violations[0].step_ids == ("d",)
    assert statuses(report)[ValidationStage.SCHEMA] is StageStatus.PASSED
    assert statuses(report)[ValidationStage.DEPENDENCY] is StageStatus.FAILED
    assert report.plan_id is None
    assert not report.accepted


def test_an_unknown_dependency_in_json_is_a_dependency_failure():
    steps = [{"step_id": "a", "depends_on": ["ghost"], "kind": "agent", "capability": "research"}]
    report = run_json(plan_document(steps=steps))
    assert codes(report) == [ViolationCode.UNKNOWN_DEPENDENCY]
    assert report.violations[0].step_ids == ("a",)
    assert "'ghost'" in report.violations[0].message
    assert statuses(report)[ValidationStage.SCHEMA] is StageStatus.PASSED


def test_attribution_does_not_depend_on_message_text():
    # The typed exceptions (D-107), not string matching, drive the split: the
    # same failure class is attributed identically whatever the ids are called.
    for name in ("d", "step with spaces", "D-092", "unknown step_id"):
        steps = [
            {"step_id": name, "depends_on": [], "kind": "agent", "capability": "research"},
            {"step_id": name, "depends_on": [], "kind": "VERIFY"},
        ]
        assert codes(run_json(plan_document(steps=steps))) == [ViolationCode.DUPLICATE_STEP_ID]
        steps = [{"step_id": "a", "depends_on": [name], "kind": "agent", "capability": "research"}]
        assert codes(run_json(plan_document(steps=steps))) == [ViolationCode.UNKNOWN_DEPENDENCY]


def test_the_v01_accepted_self_dependency_document_is_rejected_by_the_cycle_stage():
    steps = [{"step_id": "s1", "depends_on": ["s1"], "kind": "agent", "capability": "research"}]
    report = run_json(plan_document(steps=steps))
    assert codes(report) == [ViolationCode.CYCLE_DETECTED]
    assert statuses(report)[ValidationStage.SCHEMA] is StageStatus.PASSED
    assert statuses(report)[ValidationStage.DEPENDENCY] is StageStatus.PASSED
    assert statuses(report)[ValidationStage.COMPLEXITY] is StageStatus.SKIPPED
    assert not report.accepted


def test_a_document_for_another_mission_is_caught_on_the_json_path_too():
    state, _ = state_and_plan()
    report = run_json(plan_document(), state=state)  # a different state's plan
    assert ViolationCode.PLAN_MISSION_MISMATCH in codes(report)
    assert not report.accepted


# --- never raises ----------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "",
        " ",
        "\x00",
        "{" * 5000,
        "[" * 5000,
        '{"steps": ' + "[" * 3000 + "]" * 3000 + "}",
        "☃",
        '{"plan_id": null, "steps": null}',
        '{"steps": [null]}',
        '{"steps": [[]]}',
        '{"steps": [{"kind": "agent"}]}',
        "9" * 10_000,
        '{"version": 1e999}',
    ],
)
def test_invalid_documents_return_a_rejecting_report_instead_of_raising(text):
    report = run_json(text)
    assert report.accepted is False
    assert [r.stage for r in report.stages] == STAGES


# --- explicit limits, no ambient config (D-103) ----------------------------


def test_limits_are_a_required_argument_of_both_entry_points():
    for entry in (validate_plan, validate_plan_json):
        parameters = inspect.signature(entry).parameters
        assert list(parameters) == [list(parameters)[0], "state", "limits"]
        assert all(p.default is inspect.Parameter.empty for p in parameters.values())
        with pytest.raises(TypeError):
            entry(*(None,) * 2)  # limits omitted


def test_the_public_surface_does_not_export_a_default_limits_object():
    for name in dir(validation):
        assert not isinstance(getattr(validation, name), validation.SystemLimits)


# --- determinism -----------------------------------------------------------


def test_repeated_runs_give_equal_reports_and_identical_json():
    steps = (
        make_agent_step(step_id=StepId("z"), depends_on=(StepId("y"),), capability=CapabilityId("bad")),
        make_agent_step(step_id=StepId("y"), depends_on=(StepId("z"),)),
        make_agent_step(step_id=StepId("m")),
    )
    state, plan = state_and_plan(steps=steps)
    limits = make_system_limits(max_nodes=2)
    reports = [validate_plan(plan, state, limits) for _ in range(5)]
    assert all(r == reports[0] for r in reports)
    assert len({r.model_dump_json() for r in reports}) == 1
    assert len({validate_plan_json(plan.model_dump_json(), state, limits).model_dump_json() for _ in range(3)}) == 1


def test_validation_does_not_mutate_its_inputs():
    state, plan = state_and_plan()
    limits = make_system_limits()
    before = (plan.model_dump_json(), state.model_dump_json(), limits.model_dump_json())
    validate_plan(plan, state, limits)
    assert before == (plan.model_dump_json(), state.model_dump_json(), limits.model_dump_json())


def test_reports_are_identical_across_hash_seeds():
    # String hashing is randomized per process; a report may not depend on it.
    script = (
        "import sys\n"
        "sys.path[:0] = ['src', 'tests/support']\n"
        "from uuid import UUID\n"
        "from eidos.contracts import *\n"
        "from eidos.validation import validate_plan\n"
        "from eidos_factories import *\n"
        "from eidos_validation_factories import make_system_limits\n"
        "names = ['step_%d' % i for i in range(30)]\n"
        "steps = tuple(make_agent_step(step_id=StepId(n), depends_on=tuple(StepId(m) for m in names[:i] if (i + len(m)) % 3 == 0), "
        "capability=CapabilityId('c%d' % (i % 4))) for i, n in enumerate(names))\n"
        "steps = (make_agent_step(step_id=StepId('step_0'), depends_on=(StepId('step_29'),)),) + steps[1:]\n"
        "contract = make_reliability_contract()\n"
        "genome = make_task_genome(contract=contract, required_capabilities=(CapabilityId('c0'), CapabilityId('c1')))\n"
        "state = make_mission_state(tenant_id=contract.tenant_id, reliability_contract=contract, task_genome=genome)\n"
        "plan = make_plan(tenant_id=state.tenant_id, mission_id=state.mission_id, "
        "plan_id=PlanId(UUID(int=7)), steps=steps)\n"
        "print(validate_plan(plan, state, make_system_limits(max_nodes=20, max_agent_calls=25)).model_dump_json())\n"
    )
    root = Path(__file__).resolve().parents[3]
    outputs = set()
    for seed in ("0", "1", "4242", "random"):
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            cwd=root,
            env=dict(os.environ, PYTHONHASHSEED=seed),
        )
        assert result.returncode == 0, result.stderr
        outputs.add(result.stdout)
    assert len(outputs) == 1
    report = json.loads(outputs.pop())
    assert report["plan_id"] == str(UUID(int=7))  # the run really did exercise a full report
    assert any(stage["violations"] for stage in report["stages"])
