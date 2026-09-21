"""The runner's optional observer (decisions.md D-160 item 8; V0.5 Step 5a).

The observer is observational only: it is told when a plan arrives and when each gate settles, it is handed frozen values and never the
``MissionState``, and nothing it does — raising included — can change the pass or its report.
"""

import inspect

import pytest
from pydantic import ValidationError

from eidos.agents import InMemoryArtifactStore, VerificationAgent
from eidos.baseline import BaselineObserver, BaselineStage, run_baseline
from eidos.capabilities import BindReport
from eidos.compiler import CompileReport
from eidos.contracts import MissionState, PlanStepKind
from eidos.runtime import SequentialExecutor, WorkResult
from eidos.validation import PlanValidationReport

from eidos_mission_factories import make_mission, make_mission_plan
from eidos_runtime_factories import admit_all
from eidos_v04_registry import ANALYSIS_AGENT_ID, RESEARCH_AGENT_ID, make_registry
from eidos_validation_factories import make_system_limits


class SpyAgent:
    def __init__(self, trace):
        self.trace = trace

    def run(self, context, node):
        self.trace.append(("agent", node.step_id))
        return WorkResult.produced(f"artifact:{node.step_id}")


class Recording:
    """Notes what it is told, in order, into a shared trace."""

    def __init__(self, trace):
        self.trace, self.plans, self.gates = trace, [], []

    def plan_received(self, plan):
        self.plans.append(plan)
        self.trace.append(("plan", plan.plan_id))

    def gate_settled(self, stage, report):
        self.gates.append((stage, report))
        self.trace.append(("gate", stage))


class Raising:
    def __init__(self, on=("plan_received", "gate_settled"), error=RuntimeError("the observer broke")):
        self.on, self.error, self.calls = on, error, 0

    def plan_received(self, plan):
        self.calls += 1
        if "plan_received" in self.on:
            raise self.error

    def gate_settled(self, stage, report):
        self.calls += 1
        if "gate_settled" in self.on:
            raise self.error


class Mutating:
    """Tries every way it can think of to change what it was handed; each attempt must fail, and none may matter."""

    def __init__(self):
        self.attempts, self.refused = 0, 0

    def _try(self, action):
        self.attempts += 1
        try:
            action()
        except (ValidationError, TypeError, AttributeError):
            self.refused += 1

    def plan_received(self, plan):
        self._try(lambda: setattr(plan, "version", 99))
        self._try(lambda: plan.steps.append(None))

    def gate_settled(self, stage, report):
        self._try(lambda: setattr(report, "plan_id", None))


def mission():
    return make_mission(capabilities=("research", "cost", "billing"))


PLANS = {
    "accepted": lambda s: make_mission_plan(s, {"a": "", "b": "a", "check": "b"}, verify=("check",), capability_of={"a": "research", "b": "cost"}),
    "cycle": lambda s: make_mission_plan(s, {"a": "b", "b": "a"}, capability_of={"a": "research", "b": "research"}),
    "unsupported kind": lambda s: make_mission_plan(s, {"a": "", "r": "a"}, controls={"r": PlanStepKind.ROUTE}, capability_of={"a": "research"}),
    "unbound capability": lambda s: make_mission_plan(s, {"a": ""}, capability_of={"a": "billing"}),
}
EXPECTED_GATES = {
    "accepted": [BaselineStage.VALIDATION, BaselineStage.COMPILATION, BaselineStage.BINDING],
    "cycle": [BaselineStage.VALIDATION],
    "unsupported kind": [BaselineStage.VALIDATION, BaselineStage.COMPILATION],
    "unbound capability": [BaselineStage.VALIDATION, BaselineStage.COMPILATION, BaselineStage.BINDING],
}


def run(state, plan, observer=None, trace=None):
    trace = [] if trace is None else trace
    agent = SpyAgent(trace)
    return run_baseline(
        state=state, plan=plan, limits=make_system_limits(), registry=make_registry(),
        agents={RESEARCH_AGENT_ID: agent, ANALYSIS_AGENT_ID: agent},
        verifier=VerificationAgent(store=InMemoryArtifactStore()), admission_guard=admit_all(),
        executor_factory=SequentialExecutor, observer=observer,
    )


# --- what the observer is told -----------------------------------------------------------------------------------------------------


def test_the_observer_is_told_of_the_plan_and_then_of_each_gate_up_to_the_one_that_refused():
    for name, build in PLANS.items():
        state = mission()
        plan = build(state)
        observer = Recording([])
        run(state, plan, observer)
        assert observer.plans == [plan], name
        assert [stage for stage, _ in observer.gates] == EXPECTED_GATES[name], name


def test_each_gate_report_the_observer_sees_is_the_one_the_pass_reports():
    state = mission()
    plan = PLANS["accepted"](state)
    observer = Recording([])
    report = run(state, plan, observer)
    seen = dict(observer.gates)
    assert seen[BaselineStage.VALIDATION] == report.validation and isinstance(seen[BaselineStage.VALIDATION], PlanValidationReport)
    assert seen[BaselineStage.COMPILATION] == report.compilation and isinstance(seen[BaselineStage.COMPILATION], CompileReport)
    assert seen[BaselineStage.BINDING] == report.binding and isinstance(seen[BaselineStage.BINDING], BindReport)


def test_the_observer_is_told_of_the_plan_first_and_of_every_gate_before_any_agent_runs():
    state = mission()
    trace = []
    run(state, PLANS["accepted"](state), Recording(trace), trace)
    kinds = [entry[0] for entry in trace]
    assert kinds[0] == "plan" and kinds[1:4] == ["gate", "gate", "gate"]
    assert kinds.index("agent") > 3  # the agents run only once every gate has settled and been reported


def test_a_gate_that_refuses_is_reported_and_then_nothing_runs():
    state = mission()
    trace = []
    run(state, PLANS["unbound capability"](state), Recording(trace), trace)
    assert [entry[0] for entry in trace] == ["plan", "gate", "gate", "gate"]  # no "agent" entry: nothing was dispatched


def test_the_observer_is_never_handed_the_mission_state():
    state = mission()
    seen = []

    class Watcher:
        def plan_received(self, plan):
            seen.append(plan)

        def gate_settled(self, stage, report):
            seen.extend((stage, report))

    run(state, PLANS["accepted"](state), Watcher())
    assert seen and not any(isinstance(item, MissionState) for item in seen)
    assert list(inspect.signature(BaselineObserver.plan_received).parameters) == ["self", "plan"]
    assert list(inspect.signature(BaselineObserver.gate_settled).parameters) == ["self", "stage", "report"]


def test_the_observer_defaults_to_none_and_is_optional():
    parameter = inspect.signature(run_baseline).parameters["observer"]
    assert parameter.default is None
    state = mission()
    assert run(state, PLANS["accepted"](state)).run is not None  # no observer: the pass is as it always was


# --- it can change nothing ---------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", list(PLANS), ids=list(PLANS))
def test_the_report_is_identical_with_no_observer_a_recording_one_and_a_faulting_one(name):
    state = mission()
    plan = PLANS[name](state)
    baseline = run(state, plan).model_dump_json()
    assert run(state, plan, Recording([])).model_dump_json() == baseline
    for faulty in (Raising(), Raising(on=("plan_received",)), Raising(on=("gate_settled",))):
        assert run(state, plan, faulty).model_dump_json() == baseline
        assert faulty.calls > 0  # it really was called and really did raise


def test_a_faulting_observer_does_not_stop_the_agents_from_running():
    state = mission()
    trace = []
    report = run(state, PLANS["accepted"](state), Raising(), trace)
    assert [entry[1] for entry in trace if entry[0] == "agent"] == ["a", "b"]
    assert report.run is not None and report.run.dispatched


def test_an_observer_that_tries_to_change_what_it_was_handed_cannot_and_the_report_is_unchanged():
    state = mission()
    plan = PLANS["accepted"](state)
    baseline = run(state, plan).model_dump_json()
    mutator = Mutating()
    assert run(state, plan, mutator).model_dump_json() == baseline
    assert mutator.attempts > 0 and mutator.refused == mutator.attempts  # every attempt failed


def test_the_mission_state_is_read_and_never_written_with_an_observer_present():
    state = mission()
    before = state.model_dump_json()
    run(state, PLANS["accepted"](state), Recording([]))
    assert state.model_dump_json() == before


def test_only_an_ordinary_fault_is_contained_an_interrupt_still_stops_the_run():
    state = mission()
    with pytest.raises(KeyboardInterrupt):
        run(state, PLANS["accepted"](state), Raising(error=KeyboardInterrupt()))
