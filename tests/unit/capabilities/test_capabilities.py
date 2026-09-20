"""The V0.4 capability vocabulary, registry and binding (decisions.md D-132, D-133, D-134, D-144; invariant 11)."""

import random
from uuid import UUID

import pytest
from pydantic import ValidationError

from eidos.capabilities import (
    ARCHITECTURE,
    COST,
    RESEARCH,
    SECURITY,
    V04_CAPABILITIES,
    VERIFICATION,
    AgentDescriptor,
    BindFailureCode,
    BindReport,
    BindViolation,
    CapabilityRegistry,
    NodeBinding,
    bind_plan,
)
from eidos.contracts import AgentId, CapabilityId, PlanId, StepId
from eidos.validation import validate_plan

from eidos_factories import make_mission_state, make_reliability_contract, make_task_genome
from eidos_validation_factories import make_system_limits

RESEARCH_AGENT = AgentId(UUID(int=101))
ANALYSIS_AGENT = AgentId(UUID(int=102))


def registry(*agents: AgentDescriptor) -> CapabilityRegistry:
    return CapabilityRegistry(agents=agents)


def v04_registry() -> CapabilityRegistry:
    """The mapping D-144 rules: Research serves research; Analysis serves architecture, security and cost."""
    return registry(
        AgentDescriptor(agent_id=RESEARCH_AGENT, version="1", capabilities=(RESEARCH,)),
        AgentDescriptor(agent_id=ANALYSIS_AGENT, version="1", capabilities=(ARCHITECTURE, SECURITY, COST)),
    )


def capability_of(name: str) -> CapabilityId:
    return CapabilityId(name)


# --- the vocabulary (D-132, D-144) -----------------------------------------------------------------------------------


def test_the_v04_vocabulary_is_exactly_the_five_lowercase_ids():
    assert set(V04_CAPABILITIES) == {"architecture", "security", "cost", "research", "verification"}
    assert len(V04_CAPABILITIES) == 5
    assert all(name == name.lower() and name == name.strip() for name in V04_CAPABILITIES)


def test_the_named_constants_are_the_ruled_strings():
    assert (ARCHITECTURE, SECURITY, COST, RESEARCH, VERIFICATION) == (
        "architecture", "security", "cost", "research", "verification",
    )


# --- the descriptor and the registry (D-134) -------------------------------------------------------------------------


def test_a_descriptor_is_an_id_a_version_and_capabilities_and_nothing_else():
    assert list(AgentDescriptor.model_fields) == ["agent_id", "version", "capabilities"]


@pytest.mark.parametrize("bad", [dict(version=""), dict(capabilities=()), dict(capabilities=(RESEARCH, RESEARCH))])
def test_an_invalid_descriptor_is_rejected(bad):
    fields = dict(agent_id=RESEARCH_AGENT, version="1", capabilities=(RESEARCH,))
    fields.update(bad)
    with pytest.raises(ValidationError):
        AgentDescriptor(**fields)


def test_extra_metadata_is_not_accepted_yet():
    with pytest.raises(ValidationError):
        AgentDescriptor(agent_id=RESEARCH_AGENT, version="1", capabilities=(RESEARCH,), historical_latency=1.0)


def test_the_registry_resolves_by_exact_string():
    r = v04_registry()
    assert r.resolve(RESEARCH) == RESEARCH_AGENT
    assert [r.resolve(c) for c in (ARCHITECTURE, SECURITY, COST)] == [ANALYSIS_AGENT] * 3


@pytest.mark.parametrize("near", ["Research", "RESEARCH", " research", "research ", "researcher", "research_agent", "", "security_analysis", "res", "cos", "secur", "arch"])
def test_a_near_miss_is_unresolved_never_the_nearest_match(near):
    assert v04_registry().resolve(capability_of(near)) is None


def test_verification_is_in_the_vocabulary_but_no_work_agent_serves_it():
    assert VERIFICATION in V04_CAPABILITIES
    assert v04_registry().resolve(VERIFICATION) is None


def test_the_same_agent_id_twice_is_refused():
    a = AgentDescriptor(agent_id=RESEARCH_AGENT, version="1", capabilities=(RESEARCH,))
    b = AgentDescriptor(agent_id=RESEARCH_AGENT, version="2", capabilities=(SECURITY,))
    with pytest.raises(ValidationError, match="registered twice"):
        registry(a, b)


def test_one_capability_served_by_two_agents_is_refused_so_a_resolution_is_never_a_choice():
    a = AgentDescriptor(agent_id=RESEARCH_AGENT, version="1", capabilities=(RESEARCH,))
    b = AgentDescriptor(agent_id=ANALYSIS_AGENT, version="1", capabilities=(RESEARCH, COST))
    with pytest.raises(ValidationError, match="two agents"):
        registry(a, b)


@pytest.mark.parametrize("outside", ["billing", "Research", "technical_analysis", ""])
def test_a_capability_outside_the_v04_vocabulary_cannot_be_served(outside):
    with pytest.raises(ValidationError, match="not in the V0.4 vocabulary"):
        registry(AgentDescriptor(agent_id=RESEARCH_AGENT, version="1", capabilities=(capability_of(outside),)))


def test_an_empty_registry_is_valid_and_resolves_nothing():
    assert registry().resolve(RESEARCH) is None


def test_resolution_does_not_depend_on_the_order_agents_are_listed_in():
    descriptors = [
        AgentDescriptor(agent_id=AgentId(UUID(int=200 + n)), version="1", capabilities=(c,))
        for n, c in enumerate(V04_CAPABILITIES)
    ]
    expected = {c: registry(*descriptors).resolve(c) for c in V04_CAPABILITIES}
    rng = random.Random(4)
    for _ in range(20):
        shuffled = descriptors[:]
        rng.shuffle(shuffled)
        assert {c: registry(*shuffled).resolve(c) for c in V04_CAPABILITIES} == expected


def test_the_registry_is_immutable():
    r = v04_registry()
    with pytest.raises(ValidationError):
        r.agents = ()
    with pytest.raises(ValidationError):
        r.agents[0].version = "9"


# --- binding (D-134, invariant 11) -----------------------------------------------------------------------------------


def compiled_with(spec, capabilities=None, verify=()):
    """Compile ``spec``; ``capabilities`` maps a step name to the capability its work step requests."""
    from eidos.compiler import compile_plan
    from eidos.contracts import PlanStepKind
    from eidos_compiler_factories import forged_accepted_report
    from eidos_factories import make_agent_step, make_control_step, make_plan

    steps = []
    for name, deps in spec.items():
        depends_on = tuple(StepId(d) for d in deps.split())
        if name in verify:
            steps.append(make_control_step(step_id=StepId(name), depends_on=depends_on, kind=PlanStepKind.VERIFY))
        else:
            steps.append(make_agent_step(step_id=StepId(name), depends_on=depends_on,
                                         capability=CapabilityId((capabilities or {}).get(name, "research"))))
    plan = make_plan(steps=tuple(steps))
    report = compile_plan(plan, forged_accepted_report(plan))
    assert report.succeeded, report.violations
    return report.compiled


def test_every_work_node_is_bound_to_the_agent_that_serves_its_capability():
    compiled = compiled_with({"gather": "", "analyse": "gather", "check": "analyse"},
                             {"gather": "research", "analyse": "cost"}, verify=("check",))
    report = bind_plan(compiled, v04_registry())

    assert report.succeeded and report.violations == ()
    assert report.plan_id == compiled.plan_id
    assert [(b.step_id, b.capability, b.agent_id) for b in report.bindings] == [
        ("gather", "research", RESEARCH_AGENT),
        ("analyse", "cost", ANALYSIS_AGENT),
    ]
    assert report.agent_for(StepId("analyse")) == ANALYSIS_AGENT


def test_a_verify_node_is_bound_by_kind_so_it_is_never_in_the_binding_and_never_a_violation():
    compiled = compiled_with({"check": ""}, verify=("check",))
    report = bind_plan(compiled, registry())  # not one agent registered at all

    assert report.succeeded and report.bindings == ()
    assert report.agent_for(StepId("check")) is None


def test_an_unbound_capability_is_a_typed_report_naming_every_unbound_step_in_plan_order():
    compiled = compiled_with(
        {"a": "", "b": "a", "c": "b", "d": "c"},
        {"a": "research", "b": "billing", "c": "verification", "d": "Research"},
    )
    report = bind_plan(compiled, v04_registry())

    assert not report.succeeded
    assert report.bindings == ()  # nothing is half-bound
    assert [(v.step_id, v.capability, v.code) for v in report.violations] == [
        ("b", "billing", BindFailureCode.UNBOUND_CAPABILITY),
        ("c", "verification", BindFailureCode.UNBOUND_CAPABILITY),
        ("d", "Research", BindFailureCode.UNBOUND_CAPABILITY),
    ]
    assert all("no registered agent serves" in v.message for v in report.violations)


def test_a_step_requesting_verification_is_unbound_even_though_the_word_is_in_the_vocabulary():
    compiled = compiled_with({"a": ""}, {"a": "verification"})
    assert [v.capability for v in bind_plan(compiled, v04_registry()).violations] == ["verification"]


def test_a_plan_with_no_work_nodes_binds_trivially():
    from eidos.compiler import compile_plan
    from eidos_compiler_factories import forged_accepted_report
    from eidos_factories import make_plan

    plan = make_plan(steps=())
    compiled = compile_plan(plan, forged_accepted_report(plan)).compiled
    assert bind_plan(compiled, registry()).succeeded


def test_binding_is_deterministic_and_leaves_the_compiled_plan_untouched():
    compiled = compiled_with({"a": "", "b": "a"}, {"a": "research", "b": "security"})
    before = compiled.model_dump_json()
    first = bind_plan(compiled, v04_registry())
    assert bind_plan(compiled, v04_registry()) == first
    assert bind_plan(compiled, v04_registry()).model_dump_json() == first.model_dump_json()
    assert compiled.model_dump_json() == before


def test_a_report_with_violations_that_also_binds_something_is_unconstructible():
    binding = NodeBinding(step_id=StepId("a"), capability=RESEARCH, agent_id=RESEARCH_AGENT)
    violation = BindViolation(code=BindFailureCode.UNBOUND_CAPABILITY, message="x", step_id=StepId("b"), capability=COST)
    with pytest.raises(ValidationError):
        BindReport(plan_id=PlanId(UUID(int=1)), bindings=(binding,), violations=(violation,))


def test_the_binding_names_agents_only_by_id_and_the_plan_never_does():
    # Invariant 11: a compiled work node carries a capability, never an agent.
    from eidos.compiler import WorkNode

    assert "agent_id" not in WorkNode.model_fields and "agent" not in WorkNode.model_fields


# --- V0.2 does not know which agents exist (D-102, D-134) -------------------------------------------------------------


def test_validation_accepts_a_capability_no_agent_serves_and_only_binding_refuses_it():
    contract = make_reliability_contract()
    genome = make_task_genome(contract=contract, required_capabilities=(CapabilityId("billing"),))
    state = make_mission_state(tenant_id=contract.tenant_id, reliability_contract=contract, task_genome=genome)
    compiled = compiled_with({"a": ""}, {"a": "billing"})
    from eidos_factories import make_agent_step, make_plan

    plan = make_plan(tenant_id=state.tenant_id, mission_id=state.mission_id,
                     steps=(make_agent_step("a", capability=CapabilityId("billing")),))

    assert validate_plan(plan, state, make_system_limits()).accepted  # V0.2 checks only the mission's own list
    assert not bind_plan(compiled, v04_registry()).succeeded  # binding is where availability is decided
