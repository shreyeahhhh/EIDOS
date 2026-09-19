"""compile_plan (decisions.md D-112, D-114, D-115, D-117, D-124): evidence, structure, kinds, determinism."""

import inspect
import json
import os
import random
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from eidos.compiler import (
    SUPPORTED_STEP_KINDS,
    CompileFailureCode,
    CompileReport,
    CompiledPlan,
    VerifyNode,
    WorkNode,
    compile_plan,
)
from eidos.contracts import CapabilityId, PlanStepKind, StepId
from eidos.validation import ValidationStage, validate_plan_json

from eidos_compiler_factories import (
    fixed_plan_id,
    forged_accepted_report,
    forged_report,
    plan_of,
    validated_report,
)
from eidos_factories import (
    make_agent_step,
    make_control_step,
    make_mission_state,
    make_plan,
    make_reliability_contract,
    make_task_genome,
)
from eidos_validation_factories import make_system_limits

UNSUPPORTED_KINDS = [k for k in PlanStepKind if k not in SUPPORTED_STEP_KINDS]
Code = CompileFailureCode


def ok(plan) -> CompileReport:
    """Compile with hand-built accepted evidence, so the plan's own content is what is tested."""
    return compile_plan(plan, forged_accepted_report(plan))


def compiled_of(plan) -> CompiledPlan:
    report = ok(plan)
    assert report.succeeded, [v.message for v in report.violations]
    return report.compiled


def codes(report) -> list:
    return [v.code for v in report.violations]


def bypass(plan, steps):
    """A Plan whose steps skipped construction-time validation (model_copy does not validate)."""
    return plan.model_copy(update={"steps": tuple(steps)})


def levels(compiled) -> dict:
    return {n.step_id: n.level for n in compiled.nodes}


def preds(compiled) -> dict:
    return {n.step_id: n.predecessors for n in compiled.nodes}


def verify_step(step_id: str, depends_on: tuple = ()):
    return make_control_step(
        step_id=StepId(step_id),
        depends_on=tuple(StepId(d) for d in depends_on),
        kind=PlanStepKind.VERIFY,
    )


# --- what compiles ----------------------------------------------------------------


def test_one_agent_step_compiles_to_one_work_node():
    plan = plan_of({"a": ""})
    report = ok(plan)
    assert report.succeeded and report.violations == ()
    (node,) = report.compiled.nodes
    assert isinstance(node, WorkNode)
    assert (node.step_id, node.position, node.level, node.predecessors) == ("a", 0, 1, ())
    assert node.capability == "research"


def test_one_verify_step_compiles_to_one_verify_node_without_a_capability():
    plan = make_plan(steps=(verify_step("v"),))
    (node,) = compiled_of(plan).nodes
    assert isinstance(node, VerifyNode)
    assert (node.position, node.level, node.predecessors) == (0, 1, ())
    assert not hasattr(node, "capability")


def test_the_compiled_form_carries_the_plans_identity_and_version_only():
    plan = plan_of({"a": ""}, version=3)
    compiled = compiled_of(plan)
    assert compiled.tenant_id == plan.tenant_id
    assert compiled.mission_id == plan.mission_id
    assert compiled.plan_id == plan.plan_id
    assert compiled.plan_version == 3
    assert ok(plan).plan_id == plan.plan_id


def test_a_chain_has_levels_one_to_n_and_each_predecessor_is_the_previous_step():
    plan = plan_of({"a": "", "b": "a", "c": "b", "d": "c", "e": "d"})
    compiled = compiled_of(plan)
    assert levels(compiled) == {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}
    assert preds(compiled) == {"a": (), "b": ("a",), "c": ("b",), "d": ("c",), "e": ("d",)}


def test_a_diamond():
    compiled = compiled_of(plan_of({"a": "", "b": "a", "c": "a", "d": "b c"}))
    assert levels(compiled) == {"a": 1, "b": 2, "c": 2, "d": 3}
    assert preds(compiled)["d"] == ("b", "c")


def test_fan_out_and_fan_in():
    compiled = compiled_of(
        plan_of({"root": "", "x": "root", "y": "root", "z": "root", "join": "x y z"})
    )
    assert levels(compiled) == {"root": 1, "x": 2, "y": 2, "z": 2, "join": 3}
    assert preds(compiled)["join"] == ("x", "y", "z")


def test_disconnected_components_have_independent_levels_and_several_roots():
    compiled = compiled_of(plan_of({"a": "", "b": "a", "c": "b", "x": "", "y": "x", "lone": ""}))
    assert levels(compiled) == {"a": 1, "b": 2, "c": 3, "x": 1, "y": 2, "lone": 1}
    assert [n.step_id for n in compiled.nodes if not n.predecessors] == ["a", "x", "lone"]


def test_an_empty_plan_compiles_to_an_empty_compiled_plan():
    plan = make_plan(steps=())
    report = ok(plan)
    assert report.succeeded and report.compiled.nodes == ()
    assert report.compiled.plan_id == plan.plan_id


def test_a_mixed_agent_and_verify_plan():
    plan = make_plan(
        steps=(
            make_agent_step(step_id=StepId("research")),
            verify_step("check", ("research",)),
            make_agent_step(step_id=StepId("summarise"), depends_on=(StepId("check"),)),
        )
    )
    compiled = compiled_of(plan)
    assert [type(n) for n in compiled.nodes] == [WorkNode, VerifyNode, WorkNode]
    assert levels(compiled) == {"research": 1, "check": 2, "summarise": 3}


def test_position_is_the_steps_index_even_when_plan_order_is_not_topological():
    plan = plan_of({"c": "b", "b": "a", "a": ""})  # dependents listed before their dependencies
    compiled = compiled_of(plan)
    assert [(n.step_id, n.position) for n in compiled.nodes] == [("c", 0), ("b", 1), ("a", 2)]
    assert levels(compiled) == {"a": 1, "b": 2, "c": 3}


def test_level_follows_the_longest_chain_not_the_shortest_route():
    # c depends on a directly and through b: still level 3.
    compiled = compiled_of(plan_of({"a": "", "b": "a", "c": "a b"}))
    assert levels(compiled)["c"] == 3


def test_a_join_of_a_shallow_and_a_deep_predecessor_sits_above_the_deep_one():
    compiled = compiled_of(plan_of({"a": "", "b": "a", "c": "b", "d": "a c"}))
    assert levels(compiled)["d"] == 4


def test_predecessors_keep_the_order_of_depends_on():
    compiled = compiled_of(plan_of({"a": "", "b": "", "c": "b a"}))
    assert preds(compiled)["c"] == ("b", "a")


def test_a_repeated_depends_on_entry_is_one_predecessor():
    compiled = compiled_of(plan_of({"a": "", "b": "a a a"}))
    assert preds(compiled)["b"] == ("a",)


def test_a_capability_is_carried_verbatim_never_normalised():
    plan = make_plan(steps=(make_agent_step(step_id=StepId("a"), capability=CapabilityId(" Research ")),))
    assert compiled_of(plan).nodes[0].capability == " Research "


def test_compiling_against_a_real_v02_report_matches_compiling_against_a_forged_one():
    plan = make_plan(
        steps=(make_agent_step(step_id=StepId("a")), verify_step("v", ("a",)))
    )
    real = validated_report(plan)
    assert real.accepted, [v.message for v in real.violations]
    assert compile_plan(plan, real) == ok(plan)
    assert compile_plan(plan, real).succeeded


def test_a_very_long_chain_compiles_without_hitting_the_recursion_limit():
    n = 5_000
    assert sys.getrecursionlimit() < n
    spec = {"s0": ""}
    for i in range(1, n):
        spec[f"s{i}"] = f"s{i - 1}"
    compiled = compiled_of(plan_of(spec))
    assert compiled.nodes[-1].level == n and len(compiled.nodes) == n


# --- compile is not validation ---------------------------------------------------------


def test_compile_plan_takes_exactly_a_plan_and_a_validation_report():
    # No state, no limits: it has neither the mission nor the ceilings to re-run V0.2.
    assert list(inspect.signature(compile_plan).parameters) == ["plan", "validation_report"]


def test_capabilities_are_not_re_checked_by_the_compiler():
    # Whether a capability is required by the mission is V0.2's stage, not compile's.
    plan = make_plan(steps=(make_agent_step(step_id=StepId("a"), capability=CapabilityId("anything at all")),))
    assert ok(plan).succeeded


def test_resource_and_complexity_limits_are_not_re_checked_by_the_compiler():
    # 60 agent steps exceed the V0.2 fixture ceiling of 50 nodes, but that is V0.2's verdict.
    plan = plan_of({f"s{i}": "" for i in range(60)})
    assert ok(plan).succeeded


def test_a_not_applicable_policy_stage_does_not_stop_compilation():
    plan = plan_of({"a": ""})
    report = forged_accepted_report(plan)
    assert report.result_for(ValidationStage.POLICY).status.value == "not_applicable"
    assert compile_plan(plan, report).succeeded


# --- evidence ---------------------------------------------------------------------------


def test_an_absent_validation_report_is_rejected():
    plan = plan_of({"a": ""})
    report = compile_plan(plan, None)
    assert not report.succeeded and report.compiled is None
    assert codes(report) == [Code.MISSING_VALIDATION]
    assert "requires an accepted validation report" in report.violations[0].message


@pytest.mark.parametrize("not_a_report", ["accepted", {"accepted": True}, 1, object()])
def test_something_that_is_not_a_validation_report_counts_as_absent(not_a_report):
    assert codes(compile_plan(plan_of({"a": ""}), not_a_report)) == [Code.MISSING_VALIDATION]


def test_a_plan_is_not_accepted_in_place_of_its_report():
    plan = plan_of({"a": ""})
    assert codes(compile_plan(plan, plan)) == [Code.MISSING_VALIDATION]


def test_an_unaccepted_report_for_this_plan_is_rejected_when_a_stage_failed():
    plan = plan_of({"a": ""})
    report = compile_plan(plan, forged_report(plan.plan_id, failed_cycle=True))
    assert codes(report) == [Code.VALIDATION_NOT_ACCEPTED]
    assert report.compiled is None


def test_an_unaccepted_report_for_this_plan_is_rejected_when_a_stage_was_skipped():
    plan = plan_of({"a": ""})
    report = compile_plan(plan, forged_report(plan.plan_id, skipped=ValidationStage.RESOURCE))
    assert codes(report) == [Code.VALIDATION_NOT_ACCEPTED]


def test_a_report_for_another_plan_is_rejected_even_if_accepted():
    plan, other = plan_of({"a": ""}), plan_of({"a": ""})
    report = compile_plan(plan, forged_accepted_report(other))
    assert codes(report) == [Code.VALIDATION_PLAN_MISMATCH]
    assert str(other.plan_id) in report.violations[0].message
    assert report.compiled is None


def test_a_real_v02_report_for_another_plan_is_rejected():
    plan, other = plan_of({"a": ""}), plan_of({"a": ""})
    real_for_other = validated_report(other)
    assert real_for_other.accepted
    assert codes(compile_plan(plan, real_for_other)) == [Code.VALIDATION_PLAN_MISMATCH]


def test_an_accepted_report_that_names_no_plan_is_rejected():
    plan = plan_of({"a": ""})
    report = compile_plan(plan, forged_report(None))
    assert codes(report) == [Code.VALIDATION_PLAN_MISMATCH]
    assert "no plan" in report.violations[0].message


def test_an_unparseable_document_report_is_both_unaccepted_and_for_no_plan():
    # What V0.2 returns for text that never became a Plan: rejected, with no plan_id.
    plan = plan_of({"a": ""})
    state = _state_for(plan)
    failure = validate_plan_json("not json", state, _limits())
    assert failure.plan_id is None and not failure.accepted
    assert codes(compile_plan(plan, failure)) == [Code.VALIDATION_NOT_ACCEPTED, Code.VALIDATION_PLAN_MISMATCH]


def test_evidence_failures_do_not_stop_the_structural_checks():
    plan = plan_of({"a": "b", "b": "a"})
    report = compile_plan(plan, forged_accepted_report(plan_of({"z": ""})))
    assert codes(report) == [Code.VALIDATION_PLAN_MISMATCH, Code.DEPENDENCY_CYCLE]


def test_evidence_failure_never_produces_a_compiled_plan_even_for_a_perfect_plan():
    plan = plan_of({"a": "", "b": "a"})
    for bad in (None, forged_report(plan.plan_id, failed_cycle=True), forged_accepted_report(plan_of({"q": ""}))):
        assert compile_plan(plan, bad).compiled is None


# --- accepted evidence that lies: the compiler re-checks structure ----------------------


def test_the_v01_accepted_self_dependency_plan_is_rejected_despite_an_accepted_report():
    plan = plan_of({"s1": "s1"})  # V0.1 constructs this; V0.2 would reject it
    report = ok(plan)
    assert codes(report) == [Code.DEPENDENCY_CYCLE]
    assert report.violations[0].step_ids == ("s1",)


def test_a_two_step_cycle_is_rejected_and_names_both_steps_in_plan_order():
    report = ok(plan_of({"b": "a", "a": "b"}))
    assert codes(report) == [Code.DEPENDENCY_CYCLE]
    assert report.violations[0].step_ids == ("b", "a")


def test_a_three_step_cycle_is_rejected():
    assert codes(ok(plan_of({"a": "c", "b": "a", "c": "b"}))) == [Code.DEPENDENCY_CYCLE]


def test_steps_downstream_of_a_cycle_are_named_but_steps_upstream_are_not():
    report = ok(plan_of({"feeder": "", "a": "feeder b", "b": "a", "tail": "a", "end": "tail"}))
    (violation,) = report.violations
    assert violation.step_ids == ("a", "b", "tail", "end")
    assert "on, or downstream of, a dependency cycle" in violation.message


def test_disjoint_cycles_are_reported_together_in_plan_order():
    report = ok(plan_of({"a": "b", "b": "a", "fine": "", "c": "d", "d": "c"}))
    (violation,) = report.violations
    assert violation.step_ids == ("a", "b", "c", "d")


def test_a_duplicate_step_id_in_a_constructed_plan_is_rejected_once():
    base = plan_of({"a": ""})
    plan = bypass(
        base,
        (make_agent_step(step_id=StepId("d")), make_agent_step(step_id=StepId("d")), verify_step("d")),
    )
    report = ok(plan)
    assert codes(report) == [Code.DUPLICATE_STEP_ID]
    assert report.violations[0].step_ids == ("d",)


def test_a_dangling_dependency_in_a_constructed_plan_is_rejected():
    base = plan_of({"a": ""})
    plan = bypass(base, (make_agent_step(step_id=StepId("a"), depends_on=(StepId("ghost"),)),))
    report = ok(plan)
    assert codes(report) == [Code.UNKNOWN_DEPENDENCY]
    assert report.violations[0].step_ids == ("a",)
    assert "'ghost'" in report.violations[0].message


def test_each_distinct_unknown_dependency_is_reported_once_in_plan_then_depends_on_order():
    base = plan_of({"a": ""})
    plan = bypass(
        base,
        (
            make_agent_step(step_id=StepId("a"), depends_on=(StepId("x"), StepId("x"), StepId("y"))),
            make_agent_step(step_id=StepId("b"), depends_on=(StepId("z"),)),
        ),
    )
    report = ok(plan)
    assert [(v.step_ids, v.message.split()[-1]) for v in report.violations] == [
        (("a",), "'x'"),
        (("a",), "'y'"),
        (("b",), "'z'"),
    ]


def test_the_cycle_check_is_not_attempted_on_an_undefined_graph():
    base = plan_of({"a": ""})
    plan = bypass(
        base,
        (
            make_agent_step(step_id=StepId("a"), depends_on=(StepId("b"),)),
            make_agent_step(step_id=StepId("b"), depends_on=(StepId("a"), StepId("ghost"))),
        ),
    )
    assert codes(ok(plan)) == [Code.UNKNOWN_DEPENDENCY]  # the a<->b cycle is not reported


def test_violations_come_in_evidence_structure_kind_order():
    base = plan_of({"a": ""})
    plan = bypass(
        base,
        (
            make_agent_step(step_id=StepId("d")),
            make_agent_step(step_id=StepId("d")),
            make_agent_step(step_id=StepId("e"), depends_on=(StepId("ghost"),)),
            make_control_step(step_id=StepId("r"), kind=PlanStepKind.ROUTE),
        ),
    )
    report = compile_plan(plan, None)
    assert codes(report) == [
        Code.MISSING_VALIDATION,
        Code.DUPLICATE_STEP_ID,
        Code.UNKNOWN_DEPENDENCY,
        Code.UNSUPPORTED_STEP_KIND,
    ]


def test_a_real_v02_rejection_of_a_cyclic_plan_is_also_rejected_by_the_compiler():
    plan = plan_of({"a": "b", "b": "a"})
    real = validated_report(plan)
    assert not real.accepted
    assert Code.VALIDATION_NOT_ACCEPTED in codes(compile_plan(plan, real))
    assert Code.DEPENDENCY_CYCLE in codes(compile_plan(plan, real))


# --- unsupported kinds --------------------------------------------------------------------


@pytest.mark.parametrize("kind", UNSUPPORTED_KINDS)
def test_every_unsupported_kind_is_rejected_after_v02_accepted_it(kind):
    plan = make_plan(steps=(make_control_step(step_id=StepId("s"), kind=kind),))
    real = validated_report(plan)
    assert real.accepted, "V0.2 accepts every kind by design (D-047)"

    report = compile_plan(plan, real)
    assert not report.succeeded and report.compiled is None
    (violation,) = report.violations
    assert violation.code is Code.UNSUPPORTED_STEP_KIND
    assert violation.step_kind is kind
    assert violation.step_ids == ("s",)
    assert "D-112" in violation.message and repr(kind.value) in violation.message


def test_route_is_accepted_by_v02_but_rejected_by_the_compiler():
    plan = make_plan(
        steps=(
            make_agent_step(step_id=StepId("research")),
            make_control_step(step_id=StepId("route"), depends_on=(StepId("research"),), kind=PlanStepKind.ROUTE),
            make_agent_step(step_id=StepId("act"), depends_on=(StepId("route"),)),
        )
    )
    real = validated_report(plan)
    assert real.accepted and real.violations == ()  # V0.2 has nothing to say about ROUTE (D-047)

    report = compile_plan(plan, real)
    assert codes(report) == [Code.UNSUPPORTED_STEP_KIND]
    assert report.violations[0].step_ids == ("route",)
    assert report.compiled is None  # nothing partial: not even the two supported steps


def test_the_supported_kinds_are_not_reported_as_unsupported():
    plan = make_plan(steps=(make_agent_step(step_id=StepId("a")), verify_step("v", ("a",))))
    assert ok(plan).succeeded


def test_each_unsupported_step_is_reported_in_plan_order_and_nothing_is_dropped():
    plan = make_plan(
        steps=(
            make_control_step(step_id=StepId("t"), kind=PlanStepKind.TERMINATE),
            make_agent_step(step_id=StepId("a")),
            make_control_step(step_id=StepId("h"), kind=PlanStepKind.HUMAN_APPROVAL),
            verify_step("v"),
            make_control_step(step_id=StepId("r"), kind=PlanStepKind.RETRY),
        )
    )
    report = ok(plan)
    assert [(v.step_ids[0], v.step_kind) for v in report.violations] == [
        ("t", PlanStepKind.TERMINATE),
        ("h", PlanStepKind.HUMAN_APPROVAL),
        ("r", PlanStepKind.RETRY),
    ]
    assert report.compiled is None


def test_an_unsupported_kind_is_not_repaired_dropped_or_transformed():
    plan = make_plan(steps=(make_agent_step(step_id=StepId("a")), make_control_step(step_id=StepId("r"), kind=PlanStepKind.ROUTE)))
    before = plan.model_dump_json()
    report = ok(plan)
    assert plan.model_dump_json() == before
    assert report.compiled is None


@pytest.mark.parametrize(
    "kind, cited",
    [
        (PlanStepKind.ROUTE, "D-012"),
        (PlanStepKind.REPLAN, "D-012"),
        (PlanStepKind.TERMINATE, "D-012"),
        (PlanStepKind.RETRY, "D-125"),
        (PlanStepKind.HUMAN_APPROVAL, "D-055"),
    ],
)
def test_the_rejection_names_the_open_decision_that_blocks_the_kind(kind, cited):
    plan = make_plan(steps=(make_control_step(step_id=StepId("s"), kind=kind),))
    assert cited in ok(plan).violations[0].message


# --- malformed steps: kind and shape disagree (only reachable by bypassing construction) --


def test_an_agent_step_relabelled_verify_is_rejected_not_silently_stripped_of_its_capability():
    base = plan_of({"a": ""})
    relabelled = base.steps[0].model_copy(update={"kind": PlanStepKind.VERIFY})
    report = ok(bypass(base, (relabelled,)))
    assert codes(report) == [Code.MALFORMED_STEP]
    assert report.compiled is None


def test_a_control_step_relabelled_agent_is_rejected():
    base = plan_of({"a": ""})
    relabelled = verify_step("v").model_copy(update={"kind": PlanStepKind.AGENT})
    assert codes(ok(bypass(base, (relabelled,)))) == [Code.MALFORMED_STEP]


def test_an_agent_step_without_a_capability_is_rejected():
    base = plan_of({"a": ""})
    capless = base.steps[0].model_copy(update={"capability": None})
    assert codes(ok(bypass(base, (capless,)))) == [Code.MALFORMED_STEP]


def test_a_control_step_of_a_kind_outside_the_enumeration_is_malformed_not_unsupported():
    base = plan_of({"a": ""})
    alien = verify_step("v").model_copy(update={"kind": "SEQUENTIAL"})  # D-050: not a kind
    assert codes(ok(bypass(base, (alien,)))) == [Code.MALFORMED_STEP]


# --- never raises for an invalid plan/report combination ------------------------------------


def test_every_invalid_combination_returns_a_report_instead_of_raising():
    base = plan_of({"a": ""})
    cyclic = plan_of({"a": "a"})
    dangling = bypass(base, (make_agent_step(step_id=StepId("a"), depends_on=(StepId("z"),)),))
    unsupported = make_plan(steps=(make_control_step(step_id=StepId("r"), kind=PlanStepKind.ROUTE),))
    for plan in (base, cyclic, dangling, unsupported, make_plan(steps=())):
        for evidence in (None, "x", forged_accepted_report(plan), forged_accepted_report(base),
                         forged_report(plan.plan_id, failed_cycle=True), forged_report(None)):
            result = compile_plan(plan, evidence)
            assert isinstance(result, CompileReport)
            assert result.succeeded == (result.violations == ())


# --- determinism ---------------------------------------------------------------------------------


def test_repeated_compilation_gives_equal_reports_and_identical_json():
    plan = plan_of({"a": "", "b": "a", "c": "a", "d": "b c"})
    reports = [ok(plan) for _ in range(5)]
    assert all(r == reports[0] for r in reports)
    assert len({r.model_dump_json() for r in reports}) == 1
    assert len({r.compiled.model_dump_json() for r in reports}) == 1


def test_equal_plans_that_are_distinct_objects_compile_identically():
    plan = plan_of({"a": "", "b": "a"})
    twin = type(plan).model_validate_json(plan.model_dump_json())
    assert twin == plan and twin is not plan
    assert ok(plan) == ok(twin)


def test_a_failing_compilation_is_deterministic_too():
    plan = bypass(
        plan_of({"a": ""}),
        (
            make_agent_step(step_id=StepId("d")),
            make_agent_step(step_id=StepId("d")),
            make_agent_step(step_id=StepId("x"), depends_on=(StepId("ghost"),)),
            make_control_step(step_id=StepId("r"), kind=PlanStepKind.ROUTE),
        ),
    )
    reports = [compile_plan(plan, None) for _ in range(4)]
    assert len({r.model_dump_json() for r in reports}) == 1


def _expected_levels(spec: dict) -> dict:
    """Longest chain in nodes, by an independent memoised walk."""
    memo: dict = {}

    def level(name):
        if name not in memo:
            memo[name] = 1 + max((level(d) for d in spec[name]), default=0)
        return memo[name]

    return {name: level(name) for name in spec}


def _random_dag(rng: random.Random, n: int, p: float) -> dict:
    names = [f"n{i}" for i in range(n)]
    spec = {name: tuple(names[j] for j in range(i) if rng.random() < p) for i, name in enumerate(names)}
    order = names[:]
    rng.shuffle(order)  # plan order need not be topological
    return {name: spec[name] for name in order}


@pytest.mark.parametrize("seed", range(40))
def test_levels_and_predecessors_match_an_independent_computation_on_random_dags(seed):
    rng = random.Random(seed)
    spec = _random_dag(rng, rng.randint(1, 12), rng.choice([0.1, 0.3, 0.6, 0.9]))
    plan = plan_of({name: " ".join(deps) for name, deps in spec.items()})
    compiled = compiled_of(plan)
    assert levels(compiled) == _expected_levels(spec)
    assert preds(compiled) == {name: deps for name, deps in spec.items()}
    assert [n.step_id for n in compiled.nodes] == list(spec)  # plan order preserved
    assert [n.position for n in compiled.nodes] == list(range(len(spec)))


@pytest.mark.parametrize("seed", range(10))
def test_reordering_the_steps_changes_positions_but_never_levels_or_predecessors(seed):
    rng = random.Random(500 + seed)
    spec = _random_dag(rng, 10, 0.4)
    reordered = dict(rng.sample(list(spec.items()), len(spec)))
    a = compiled_of(plan_of({k: " ".join(v) for k, v in spec.items()}))
    b = compiled_of(plan_of({k: " ".join(v) for k, v in reordered.items()}))
    assert levels(a) == levels(b) and preds(a) == preds(b)
    assert [n.step_id for n in b.nodes] == list(reordered)


def test_output_is_identical_across_hash_seeds():
    # String hashing is randomized per process; nothing observable may depend on it.
    script = (
        "import sys\n"
        "sys.path[:0] = ['src', 'tests/support']\n"
        "from eidos.compiler import compile_plan\n"
        "from eidos.contracts import *\n"
        "from eidos_compiler_factories import fixed_plan_id, forged_accepted_report\n"
        "from eidos_factories import *\n"
        "from uuid import UUID\n"
        "names = ['step_%d' % i for i in range(40)]\n"
        "steps = []\n"
        "for i, n in enumerate(names):\n"
        "    deps = tuple(StepId(m) for m in names[:i] if (i * 7 + len(m) * 3 + int(m[5:])) % 5 == 0)\n"
        "    steps.append(make_agent_step(step_id=StepId(n), depends_on=deps) if i % 4 else "
        "make_control_step(step_id=StepId(n), depends_on=deps, kind=PlanStepKind.VERIFY))\n"
        "steps.reverse()\n"
        "ids = dict(tenant_id=TenantId(UUID(int=1)), mission_id=MissionId(UUID(int=2)), plan_id=fixed_plan_id(3))\n"
        "good = make_plan(steps=tuple(steps), **ids)\n"
        "bad = good.model_copy(update={'steps': tuple(steps) + (make_control_step(step_id=StepId('r'), kind=PlanStepKind.ROUTE),"
        " make_agent_step(step_id=StepId('x'), depends_on=(StepId('x'),)))})\n"
        "print(compile_plan(good, forged_accepted_report(good)).model_dump_json())\n"
        "print(compile_plan(bad, forged_accepted_report(bad)).model_dump_json())\n"
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
    good_json, bad_json = outputs.pop().strip().splitlines()
    assert json.loads(good_json)["compiled"] is not None  # a real compiled plan was compared
    assert json.loads(bad_json)["compiled"] is None and json.loads(bad_json)["violations"]


# --- plan and compiled-form immutability ---------------------------------------------------------


def test_compiling_leaves_the_plan_untouched():
    plan = plan_of({"a": "", "b": "a"}, version=2)
    before = (plan.model_dump_json(), plan.steps)
    ok(plan)
    assert (plan.model_dump_json(), plan.steps) == before
    assert plan.steps is before[1]


def test_the_compiled_form_is_frozen_and_its_collections_are_tuples():
    compiled = compiled_of(plan_of({"a": "", "b": "a"}))
    with pytest.raises(ValidationError):
        compiled.plan_version = 9
    with pytest.raises(ValidationError):
        compiled.nodes[0].level = 9
    assert isinstance(compiled.nodes, tuple) and isinstance(compiled.nodes[1].predecessors, tuple)


def test_the_compiled_form_does_not_alias_the_plans_collections():
    plan = plan_of({"a": "", "b": "a"})
    compiled = compiled_of(plan)
    assert compiled.nodes is not plan.steps
    assert compiled.nodes[1].predecessors is not plan.steps[1].depends_on


def test_version_one_and_version_two_compile_to_independent_compiled_plans():
    v1 = plan_of({"a": "", "b": "a"}, version=1)
    v2 = plan_of(
        {"a": "", "c": "a", "d": "a", "e": "c d"},
        version=2,
        tenant_id=v1.tenant_id,
        mission_id=v1.mission_id,
        parent_plan_id=v1.plan_id,
        replan_reason="insufficient evidence",
    )
    first_v1 = compiled_of(v1)
    snapshot = first_v1.model_dump_json()

    compiled_v2 = compiled_of(v2)
    again_v1 = compiled_of(v1)

    assert first_v1.plan_version == 1 and compiled_v2.plan_version == 2
    assert first_v1.plan_id == v1.plan_id and compiled_v2.plan_id == v2.plan_id
    assert first_v1.plan_id != compiled_v2.plan_id
    assert [n.step_id for n in first_v1.nodes] == ["a", "b"]
    assert [n.step_id for n in compiled_v2.nodes] == ["a", "c", "d", "e"]
    assert first_v1.model_dump_json() == snapshot == again_v1.model_dump_json()  # v2 changed nothing
    assert first_v1 == again_v1
    assert first_v1.mission_id == compiled_v2.mission_id  # same mission, different versions


def test_lineage_stays_in_the_plan_and_is_not_copied_into_the_compiled_form():
    v1 = plan_of({"a": ""})
    v2 = plan_of({"a": ""}, version=2, parent_plan_id=v1.plan_id, replan_reason="because")
    text = compiled_of(v2).model_dump_json()
    assert "parent_plan_id" not in text and "replan_reason" not in text and "because" not in text
    assert str(v1.plan_id) not in text


def test_a_report_for_version_one_is_not_evidence_for_version_two():
    v1 = plan_of({"a": ""}, version=1)
    v2 = plan_of({"a": ""}, version=2, tenant_id=v1.tenant_id, mission_id=v1.mission_id, parent_plan_id=v1.plan_id, replan_reason="x")
    assert codes(compile_plan(v2, forged_accepted_report(v1))) == [Code.VALIDATION_PLAN_MISMATCH]


# --- a mission built around a plan, for the one test that needs V0.2's own failure report ---


def _state_for(plan):
    contract = make_reliability_contract(tenant_id=plan.tenant_id)
    genome = make_task_genome(contract=contract, required_capabilities=(CapabilityId("research"),))
    return make_mission_state(
        tenant_id=plan.tenant_id,
        mission_id=plan.mission_id,
        reliability_contract=contract,
        task_genome=genome,
    )


def _limits():
    return make_system_limits()
