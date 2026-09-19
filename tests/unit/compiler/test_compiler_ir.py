"""The compiled form (decisions.md D-112, D-114, D-115, D-117, D-124).

The compiled representation validates itself: an inconsistent one cannot be
built by hand any more than by the compiler.
"""

from uuid import UUID

import pytest
from pydantic import ValidationError

from eidos.compiler import (
    SUPPORTED_STEP_KINDS,
    CompiledPlan,
    VerifyNode,
    WorkNode,
)
from eidos.contracts import (
    AgentStep,
    CapabilityId,
    ControlStep,
    MissionId,
    PlanId,
    PlanStepKind,
    StepId,
    TenantId,
)

from eidos_factories import make_agent_step, make_control_step

TENANT = TenantId(UUID(int=1))
MISSION = MissionId(UUID(int=2))
PLAN = PlanId(UUID(int=3))

UNSUPPORTED_KINDS = [k for k in PlanStepKind if k not in SUPPORTED_STEP_KINDS]


# --- builders -------------------------------------------------------------------


def work(step_id: str, position: int, level: int, preds: tuple = (), capability: str = "research"):
    return WorkNode(
        step_id=StepId(step_id),
        position=position,
        level=level,
        predecessors=tuple(StepId(p) for p in preds),
        capability=CapabilityId(capability),
    )


def verify(step_id: str, position: int, level: int, preds: tuple = ()):
    return VerifyNode(
        step_id=StepId(step_id),
        position=position,
        level=level,
        predecessors=tuple(StepId(p) for p in preds),
    )


def compiled(nodes: tuple, **overrides) -> CompiledPlan:
    fields = dict(
        tenant_id=TENANT, mission_id=MISSION, plan_id=PLAN, plan_version=1, nodes=tuple(nodes)
    )
    fields.update(overrides)
    return CompiledPlan(**fields)


def diamond() -> CompiledPlan:
    return compiled(
        (
            work("a", 0, 1),
            work("b", 1, 2, ("a",)),
            work("c", 2, 2, ("a",)),
            verify("d", 3, 3, ("b", "c")),
        )
    )


# --- what the representation is -------------------------------------------------


def test_the_supported_kinds_are_exactly_agent_and_verify():
    assert SUPPORTED_STEP_KINDS == (PlanStepKind.AGENT, PlanStepKind.VERIFY)


def test_an_empty_compiled_plan_is_legal():
    # D-106 is about validation, but the compiled form has no reason to differ.
    assert compiled(()).nodes == ()


def test_a_single_root_node_is_level_one_position_zero():
    plan = compiled((work("a", 0, 1),))
    (node,) = plan.nodes
    assert (node.position, node.level, node.predecessors) == (0, 1, ())


def test_a_diamond_is_valid():
    plan = diamond()
    assert [n.level for n in plan.nodes] == [1, 2, 2, 3]
    assert plan.nodes[3].predecessors == ("b", "c")


def test_nodes_may_be_in_any_plan_order_not_only_topological_order():
    # Nodes keep Plan.steps order, so a dependent may precede its dependency.
    plan = compiled((work("b", 0, 2, ("a",)), work("a", 1, 1)))
    assert [n.step_id for n in plan.nodes] == ["b", "a"]


def test_the_compiled_plan_carries_exactly_these_fields():
    # Encodes the "must not carry" list: no LangGraph objects, agent or model
    # bindings, budgets, retry or timeout fields, conditions, edge objects,
    # parent-plan lineage, or MissionState.
    assert list(CompiledPlan.model_fields) == [
        "tenant_id",
        "mission_id",
        "plan_id",
        "plan_version",
        "nodes",
    ]


def test_node_classes_carry_exactly_these_fields():
    assert list(WorkNode.model_fields) == [
        "step_id",
        "position",
        "level",
        "predecessors",
        "kind",
        "capability",
    ]
    assert list(VerifyNode.model_fields) == ["step_id", "position", "level", "predecessors", "kind"]


def test_kind_defaults_to_the_nodes_own_kind():
    assert work("a", 0, 1).kind is PlanStepKind.AGENT
    assert verify("a", 0, 1).kind is PlanStepKind.VERIFY


# --- self-validation: ids, positions, predecessors, levels -----------------------


def test_duplicate_node_ids_are_rejected():
    with pytest.raises(ValidationError, match="duplicate step_id 'a'"):
        compiled((work("a", 0, 1), work("a", 1, 1)))


@pytest.mark.parametrize(
    "nodes",
    [
        (work("a", 1, 1),),  # first node claims position 1
        (work("a", 0, 1), work("b", 0, 1)),  # positions repeat
        (work("a", 1, 1), work("b", 0, 1)),  # positions swapped
        (work("a", 0, 1), work("b", 2, 1)),  # a gap
    ],
)
def test_position_must_equal_the_nodes_actual_index(nodes):
    with pytest.raises(ValidationError, match="has position .*but it is at index"):
        compiled(nodes)


def test_a_predecessor_that_does_not_resolve_is_rejected():
    with pytest.raises(ValidationError, match="predecessor 'ghost', which is not a node"):
        compiled((work("a", 0, 2, ("ghost",)),))


def test_a_repeated_predecessor_is_rejected():
    with pytest.raises(ValidationError, match="lists predecessor 'a' more than once"):
        compiled((work("a", 0, 1), work("b", 1, 2, ("a", "a"))))


def test_a_node_cannot_be_its_own_predecessor():
    with pytest.raises(ValidationError, match="strictly lower level"):
        compiled((work("a", 0, 1, ("a",)),))


def test_a_predecessor_at_the_same_level_is_rejected():
    with pytest.raises(ValidationError, match="strictly lower level"):
        compiled((work("a", 0, 1), work("b", 1, 1, ("a",))))


def test_a_predecessor_at_a_higher_level_is_rejected():
    with pytest.raises(ValidationError, match="strictly lower level"):
        compiled((work("a", 0, 3), work("b", 1, 2, ("a",))))


def test_a_join_below_its_highest_predecessor_is_rejected_as_not_strictly_lower():
    # a (1) -> b (2); c depends on a and b but claims level 2, the same as b.
    with pytest.raises(ValidationError, match="strictly lower level"):
        compiled((work("a", 0, 1), work("b", 1, 2, ("a",)), work("c", 2, 2, ("a", "b"))))


def test_a_root_must_be_level_one():
    with pytest.raises(ValidationError, match="expected 1 .*or 1 for a root"):
        compiled((work("a", 0, 2),))


def test_a_level_above_one_plus_the_highest_predecessor_is_rejected():
    with pytest.raises(ValidationError, match="has level 4, expected 3"):
        compiled((work("a", 0, 1), work("b", 1, 2, ("a",)), work("c", 2, 4, ("b",))))


def test_a_level_is_one_plus_the_highest_predecessor_not_the_first_or_last_listed():
    # d depends on a (level 1) and c (level 3), listed in both orders: level must be 4.
    nodes = (work("a", 0, 1), work("b", 1, 2, ("a",)), work("c", 2, 3, ("b",)))
    for preds in (("a", "c"), ("c", "a")):
        assert compiled(nodes + (work("d", 3, 4, preds),)).nodes[3].level == 4
        with pytest.raises(ValidationError, match="has level 5, expected 4"):
            compiled(nodes + (work("d", 3, 5, preds),))
        with pytest.raises(ValidationError, match="strictly lower level"):  # 2 is below c's level 3
            compiled(nodes + (work("d", 3, 2, preds),))


def test_the_first_failing_check_is_the_one_reported():
    # Duplicate ids are reported before position, and so on.
    with pytest.raises(ValidationError, match="duplicate step_id"):
        compiled((work("a", 5, 9), work("a", 6, 9)))


# --- unsupported representations cannot be constructed ---------------------------


@pytest.mark.parametrize("kind", UNSUPPORTED_KINDS)
def test_an_unsupported_kind_cannot_be_a_verify_node(kind):
    with pytest.raises(ValidationError):
        VerifyNode(step_id=StepId("x"), position=0, level=1, predecessors=(), kind=kind)


@pytest.mark.parametrize("kind", UNSUPPORTED_KINDS)
def test_an_unsupported_kind_cannot_be_a_work_node(kind):
    with pytest.raises(ValidationError):
        WorkNode(
            step_id=StepId("x"),
            position=0,
            level=1,
            predecessors=(),
            kind=kind,
            capability=CapabilityId("research"),
        )


def test_a_work_node_cannot_have_the_verify_kind_nor_a_verify_node_the_agent_kind():
    with pytest.raises(ValidationError):
        WorkNode(
            step_id=StepId("x"),
            position=0,
            level=1,
            predecessors=(),
            kind=PlanStepKind.VERIFY,
            capability=CapabilityId("r"),
        )
    with pytest.raises(ValidationError):
        VerifyNode(
            step_id=StepId("x"), position=0, level=1, predecessors=(), kind=PlanStepKind.AGENT
        )


def test_a_work_node_requires_a_capability_and_a_verify_node_rejects_one():
    with pytest.raises(ValidationError):
        WorkNode(step_id=StepId("x"), position=0, level=1, predecessors=())
    with pytest.raises(ValidationError):  # extra="forbid": a control node never carries one
        VerifyNode(
            step_id=StepId("x"),
            position=0,
            level=1,
            predecessors=(),
            capability=CapabilityId("research"),
        )


@pytest.mark.parametrize("kind", UNSUPPORTED_KINDS)
def test_a_node_of_an_unsupported_kind_is_rejected_from_json(kind):
    text = diamond().model_dump_json()
    tampered = text.replace('"kind":"VERIFY"', f'"kind":"{kind.value}"')
    assert tampered != text
    with pytest.raises(ValidationError):
        CompiledPlan.model_validate_json(tampered)


def test_a_node_with_no_kind_is_rejected_from_json():
    text = diamond().model_dump_json()
    with pytest.raises(ValidationError):
        CompiledPlan.model_validate_json(text.replace('"kind":"VERIFY"', '"kind":null'))


def test_plan_steps_are_not_compiled_nodes():
    # The compiled form has its own node classes; a Plan's steps are not accepted in their place.
    with pytest.raises(ValidationError):
        compiled((make_agent_step("a"),))
    with pytest.raises(ValidationError):
        compiled((make_control_step("v", kind=PlanStepKind.VERIFY),))
    assert not issubclass(WorkNode, AgentStep) and not issubclass(VerifyNode, ControlStep)


def test_a_bare_mapping_is_not_accepted_as_a_node():
    with pytest.raises(ValidationError):
        compiled(({"step_id": "a", "position": 0, "level": 1, "predecessors": ()},))


# --- extra fields, types and required fields -------------------------------------


@pytest.mark.parametrize(
    "field", ["retries", "max_retries", "timeout_ms", "condition", "predicate", "budget", "agent_id", "edges"]
)
def test_fields_the_compiled_form_must_not_carry_are_rejected(field):
    with pytest.raises(ValidationError):
        work_with_extra = WorkNode(
            step_id=StepId("a"),
            position=0,
            level=1,
            predecessors=(),
            capability=CapabilityId("r"),
            **{field: 1},
        )
    with pytest.raises(ValidationError):
        compiled((), **{field: 1})


def test_parent_plan_lineage_is_not_duplicated_into_the_compiled_form():
    for field in ("parent_plan_id", "replan_reason"):
        with pytest.raises(ValidationError):
            compiled((), **{field: None})


def test_mission_state_cannot_be_smuggled_in():
    with pytest.raises(ValidationError):
        compiled((), mission_state=None)


@pytest.mark.parametrize("field", ["tenant_id", "mission_id", "plan_id", "plan_version", "nodes"])
def test_every_compiled_plan_field_is_required(field):
    fields = dict(
        tenant_id=TENANT, mission_id=MISSION, plan_id=PLAN, plan_version=1, nodes=()
    )
    del fields[field]
    with pytest.raises(ValidationError):
        CompiledPlan(**fields)


@pytest.mark.parametrize("bad", [0, -1, "1", 1.0, True, None])
def test_plan_version_is_a_strict_positive_integer(bad):
    with pytest.raises(ValidationError):
        compiled((), plan_version=bad)


@pytest.mark.parametrize("field, bad", [("level", 0), ("level", "1"), ("level", True), ("position", -1), ("position", "0"), ("position", False)])
def test_position_and_level_are_strict_integers_in_range(field, bad):
    fields = dict(step_id=StepId("a"), position=0, level=1, predecessors=(), capability=CapabilityId("r"))
    fields[field] = bad
    with pytest.raises(ValidationError):
        WorkNode(**fields)


def test_identifiers_are_strictly_typed():
    with pytest.raises(ValidationError):
        compiled((), tenant_id="not-a-uuid")
    with pytest.raises(ValidationError):
        compiled((), plan_id=str(PLAN))  # a str is not a UUID under strict mode


# --- immutability ---------------------------------------------------------------


def test_the_compiled_plan_and_its_nodes_are_frozen():
    plan = diamond()
    with pytest.raises(ValidationError):
        plan.plan_version = 2
    with pytest.raises(ValidationError):
        plan.nodes[0].level = 5
    with pytest.raises(ValidationError):
        plan.nodes[3].predecessors = ()


def test_the_collections_are_immutable_tuples():
    plan = diamond()
    assert isinstance(plan.nodes, tuple) and isinstance(plan.nodes[3].predecessors, tuple)
    with pytest.raises(TypeError):
        plan.nodes[0] = plan.nodes[1]
    with pytest.raises(AttributeError):
        plan.nodes.append(plan.nodes[0])
    with pytest.raises(AttributeError):
        plan.nodes[3].predecessors.append("a")


def test_a_list_supplied_for_a_collection_is_not_kept_as_a_mutable_list():
    # Strict mode rejects a list where a tuple is required; nothing mutable is ever stored.
    with pytest.raises(ValidationError):
        CompiledPlan(
            tenant_id=TENANT,
            mission_id=MISSION,
            plan_id=PLAN,
            plan_version=1,
            nodes=[work("a", 0, 1)],  # the `compiled` helper would convert this to a tuple
        )
    with pytest.raises(ValidationError):
        WorkNode(step_id=StepId("a"), position=0, level=1, predecessors=[], capability=CapabilityId("r"))


def test_model_copy_makes_a_new_object_and_leaves_the_original_untouched():
    plan = diamond()
    before = plan.model_dump_json()
    other = plan.model_copy(update={"plan_version": 9})
    assert other.plan_version == 9 and plan.plan_version == 1
    assert plan.model_dump_json() == before


def test_equal_compiled_plans_are_equal_and_hash_equally():
    a, b = diamond(), diamond()
    assert a == b and a is not b
    assert hash(a) == hash(b)
    assert a != compiled(a.nodes, plan_version=2)


# --- serialization ---------------------------------------------------------------


def test_json_round_trips_to_an_equal_compiled_plan():
    plan = diamond()
    assert CompiledPlan.model_validate_json(plan.model_dump_json()) == plan


def test_json_output_is_stable_and_field_ordered():
    text = diamond().model_dump_json()
    assert text == diamond().model_dump_json()
    assert text.startswith('{"tenant_id":')
    assert text.index('"plan_version"') < text.index('"nodes"')


def test_a_tampered_json_is_re_validated_not_trusted():
    # Rehydrating goes through the same self-validation as construction.
    text = diamond().model_dump_json()
    with pytest.raises(ValidationError, match="expected"):
        CompiledPlan.model_validate_json(text.replace('"level":3', '"level":9'))
    with pytest.raises(ValidationError, match="not a node of this compiled plan"):
        CompiledPlan.model_validate_json(text.replace('"predecessors":["b","c"]', '"predecessors":["b","zz"]'))
