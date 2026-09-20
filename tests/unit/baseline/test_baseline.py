"""The single-pass runner and the work dispatcher (decisions.md D-131, D-133, D-134, D-140)."""

import inspect
from uuid import UUID

import pytest

from eidos.agents import InMemoryArtifactStore, VerificationAgent
from eidos.baseline import BaselineReport, BaselineStage, WorkDispatcher, run_baseline
from eidos.capabilities import bind_plan
from eidos.contracts import AgentId, PlanStepKind, StepId
from eidos.runtime import SequentialExecutor, WorkResult, WorkStatus

from eidos_agents_factories import compiled_with, node_of
from eidos_mission_factories import make_mission, make_mission_plan
from eidos_runtime_factories import admit_all, context_for, halt_when
from eidos_v04_registry import ANALYSIS_AGENT_ID, RESEARCH_AGENT_ID, make_registry
from eidos_validation_factories import make_system_limits


class SpyAgent:
    def __init__(self, result=None):
        self.result = result or WorkResult.produced("artifact:spy")
        self.seen = []

    def run(self, context, node):
        self.seen.append(node.step_id)
        return self.result


def run(state, plan, *, agents=None, factory=None, registry=None, guard=None):
    store = InMemoryArtifactStore()
    return run_baseline(
        state=state,
        plan=plan,
        limits=make_system_limits(),
        registry=registry or make_registry(),
        agents=agents if agents is not None else {RESEARCH_AGENT_ID: SpyAgent(), ANALYSIS_AGENT_ID: SpyAgent()},
        verifier=VerificationAgent(store=store),
        admission_guard=guard or admit_all(),
        executor_factory=factory or SequentialExecutor,
    )


def mission():
    return make_mission(capabilities=("research", "cost"))


def plan_for(state, spec=None, **kwargs):
    return make_mission_plan(state, spec or {"gather": "", "analyse": "gather"},
                             capability_of={"gather": "research", "analyse": "cost"}, **kwargs)


# --- the dispatcher ----------------------------------------------------------------------------------------------------------


def dispatcher_for(compiled, agents):
    return WorkDispatcher(binding=bind_plan(compiled, make_registry()), agents=agents)


def test_the_dispatcher_hands_each_work_node_to_the_agent_its_capability_is_bound_to():
    compiled = compiled_with({"a": "", "b": "a"}, {"a": "research", "b": "security"})
    research, analysis = SpyAgent(), SpyAgent()
    dispatcher = dispatcher_for(compiled, {RESEARCH_AGENT_ID: research, ANALYSIS_AGENT_ID: analysis})
    context = context_for(compiled)

    dispatcher.execute(context, node_of(compiled, StepId("a")))
    dispatcher.execute(context, node_of(compiled, StepId("b")))

    assert (research.seen, analysis.seen) == (["a"], ["b"])


def test_a_node_with_no_binding_is_a_failed_work_result_and_no_agent_is_called():
    compiled = compiled_with({"a": ""}, {"a": "research"})
    agent = SpyAgent()
    dispatcher = WorkDispatcher(binding=bind_plan(compiled_with({"x": ""}, {"x": "cost"}), make_registry()),
                                agents={RESEARCH_AGENT_ID: agent, ANALYSIS_AGENT_ID: agent})
    result = dispatcher.execute(context_for(compiled), node_of(compiled, StepId("a")))
    assert result.status is WorkStatus.FAILED and "no agent is bound" in result.reason
    assert agent.seen == []


def test_a_bound_agent_that_was_not_supplied_is_a_failed_work_result():
    compiled = compiled_with({"a": ""}, {"a": "research"})
    result = dispatcher_for(compiled, {}).execute(context_for(compiled), node_of(compiled, StepId("a")))
    assert result.status is WorkStatus.FAILED and "was not supplied" in result.reason


def test_the_dispatcher_returns_what_the_agent_returned_unchanged():
    compiled = compiled_with({"a": ""}, {"a": "research"})
    failure = WorkResult.no_result("nothing to research")
    dispatcher = dispatcher_for(compiled, {RESEARCH_AGENT_ID: SpyAgent(failure)})
    assert dispatcher.execute(context_for(compiled), node_of(compiled, StepId("a"))) == failure


# --- the runner stops at the first gate that refuses ---------------------------------------------------------------------------


def test_a_plan_that_passes_every_gate_reaches_execution():
    state = mission()
    report = run(state, plan_for(state))
    assert report.stopped_at is None and report.run is not None and report.dispatched_anything


@pytest.mark.parametrize(
    "spec, controls, capability_of, stage",
    [
        ({"a": "b", "b": "a"}, None, {"a": "research", "b": "research"}, BaselineStage.VALIDATION),
        ({"a": "", "r": "a"}, {"r": PlanStepKind.ROUTE}, {"a": "research"}, BaselineStage.COMPILATION),
        ({"a": ""}, None, {"a": "billing"}, BaselineStage.BINDING),
    ],
    ids=["a cycle", "an unsupported step kind", "an unbound capability"],
)
def test_the_first_refusing_gate_ends_the_pass_and_no_agent_is_called(spec, controls, capability_of, stage):
    state = make_mission(capabilities=("research", "billing"))
    agent = SpyAgent()
    plan = make_mission_plan(state, spec, controls=controls, capability_of=capability_of)

    report = run(state, plan, agents={RESEARCH_AGENT_ID: agent, ANALYSIS_AGENT_ID: agent})

    assert report.stopped_at is stage
    assert report.run is None and agent.seen == []
    stages = [report.compilation, report.binding]
    assert [s is not None for s in stages] == {
        BaselineStage.VALIDATION: [False, False],
        BaselineStage.COMPILATION: [True, False],
        BaselineStage.BINDING: [True, True],
    }[stage]


def test_a_bad_plan_never_raises_out_of_the_runner():
    state = mission()
    for spec in ({"a": "b", "b": "a"}, {"a": "a"}):
        run(state, make_mission_plan(state, spec, capability_of={"a": "research", "b": "research"}))


def test_the_executor_factory_is_called_once_with_exactly_the_three_ports():
    state = mission()
    calls = []

    def factory(**ports):
        calls.append(sorted(ports))
        return SequentialExecutor(**ports)

    run(state, plan_for(state), factory=factory)
    assert calls == [["admission_guard", "verifier", "work_executor"]]


def test_the_factory_is_never_called_when_a_gate_refuses():
    state = mission()
    calls = []
    run(state, plan_for(state, {"a": "b", "b": "a"}), factory=lambda **ports: calls.append(ports))
    assert calls == []


def test_the_mission_state_is_only_read():
    state = mission()
    before = state.model_dump_json()
    run(state, plan_for(state))
    assert state.model_dump_json() == before


def test_an_admission_guard_is_required_and_has_no_default():
    parameter = inspect.signature(run_baseline).parameters["admission_guard"]
    assert parameter.default is inspect.Parameter.empty
    assert inspect.signature(run_baseline).parameters["verifier"].default is inspect.Parameter.empty
    assert inspect.signature(run_baseline).parameters["registry"].default is inspect.Parameter.empty


def test_a_halting_guard_pauses_the_run_the_runner_does_not_decide_that():
    from eidos.runtime import RunOutcome

    state = mission()
    report = run(state, plan_for(state), guard=halt_when(lambda request: True, "held"))
    assert report.run.outcome is RunOutcome.HALTED


# --- the report's own consistency ---------------------------------------------------------------------------------------------


def full_report():
    state = mission()
    return run(state, plan_for(state))


def test_a_report_with_a_missing_stage_is_unconstructible():
    r = full_report()
    with pytest.raises(ValueError, match="compilation is missing"):
        BaselineReport(plan_id=r.plan_id, validation=r.validation)
    with pytest.raises(ValueError, match="binding is missing"):
        BaselineReport(plan_id=r.plan_id, validation=r.validation, compilation=r.compilation)
    with pytest.raises(ValueError, match="no run"):
        BaselineReport(plan_id=r.plan_id, validation=r.validation, compilation=r.compilation, binding=r.binding)


def test_a_report_with_a_stage_that_could_not_have_run_is_unconstructible():
    state = make_mission(capabilities=("research",))
    refused = run(state, make_mission_plan(state, {"a": "b", "b": "a"}, capability_of={"a": "research", "b": "research"}))
    ok = full_report()
    with pytest.raises(ValueError, match="compilation ran"):
        BaselineReport(plan_id=refused.plan_id, validation=refused.validation, compilation=ok.compilation)
    unbound_state = make_mission(capabilities=("billing",))
    unbound = run(unbound_state, make_mission_plan(unbound_state, {"a": ""}, capability_of={"a": "billing"}))
    with pytest.raises(ValueError, match="a run exists"):
        BaselineReport(plan_id=unbound.plan_id, validation=unbound.validation, compilation=unbound.compilation,
                       binding=unbound.binding, run=ok.run)


def test_the_report_is_frozen_and_serializes():
    r = full_report()
    with pytest.raises(ValueError):
        r.run = None
    assert BaselineReport.model_validate_json(r.model_dump_json()) == r
    assert AgentId(UUID(int=1)) is not None
