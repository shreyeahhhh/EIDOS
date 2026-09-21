"""The V0.5 mission cases: every way a recorded baseline pass can end, runnable on either executor (decisions.md D-152 to D-160).

Each case names a mission, the scripted model's answers, and what the admission guard does; ``run_case`` records it on the executor given, over
a fixed clock and sequential ids, so a case gives the same log every time. The scenarios and the hash-seed story both build on these, so the two
cannot drift apart. Nothing here reaches a real model; every number a case produces is a fixed test value, never a measurement.

This module imports the LangGraph executor, so only the scenarios use it (the unit tests stay independent of the backend).
"""

from collections.abc import Callable
from dataclasses import dataclass

from eidos.agents import ModelFailure, ModelFailureKind
from eidos.backends.langgraph import LangGraphExecutor
from eidos.contracts import MissionState, Plan, PlanStepKind
from eidos.runtime import SequentialExecutor
from eidos.state import MissionFailureCause

from eidos_backend_factories import locked_admit_all, locked_halt_when
from eidos_mission_factories import make_mission, make_mission_plan
from eidos_recording_factories import FixedClock, SequentialIds, baseline_mission, record, respond_with_facts

EXECUTORS = (SequentialExecutor, LangGraphExecutor)
EXECUTOR_IDS = ("reference", "langgraph")

CAPABILITY_OF = {"gather": "research", "analyse": "cost"}


@dataclass(frozen=True)
class Case:
    name: str
    mission: Callable[[], tuple[MissionState, Plan]]
    respond: Callable | None = None
    halt_at: str | None = None  # the step the admission guard holds, if any
    # what the whole chain must come to
    status: str = "completed"
    cause: MissionFailureCause | None = None
    verified: bool | None = None
    run_outcome: str | None = "finished"
    node_statuses: tuple[str, ...] = ()  # in plan order; empty when the plan was refused (no node settles)
    reason: str = ""  # what the state's status reason must start with
    # the folded counters: fixed test values (each node takes 1,000 ms on the fixed clock; each answered model call reports 100 + 200 tokens)
    agent_calls: int = 0
    tokens: int = 0
    time_ms: int = 0


def _unverified():
    state = make_mission(capabilities=("research", "cost"))
    return state, make_mission_plan(state, {"gather": "", "analyse": "gather"}, capability_of=CAPABILITY_OF)


def _refused(name: str):
    def build():
        state = make_mission(capabilities=("research", "billing"))
        plans = {
            "validation": make_mission_plan(state, {"a": "b", "b": "a"}, capability_of={"a": "research", "b": "research"}),
            "compilation": make_mission_plan(state, {"a": "", "r": "a"}, controls={"r": PlanStepKind.ROUTE}, capability_of={"a": "research"}),
            "binding": make_mission_plan(state, {"a": ""}, capability_of={"a": "billing"}),
        }
        return state, plans[name]

    return build


def _failure(kind: ModelFailureKind):
    return respond_with_facts(research=ModelFailure(kind=kind, message="the model did not answer"))


CASES = (
    Case("verified", baseline_mission, verified=True, reason="finished and verified", node_statuses=("succeeded", "succeeded", "succeeded"), agent_calls=2, tokens=600, time_ms=3000),
    Case("unverified", _unverified, verified=False, reason="finished without a successful VERIFY", node_statuses=("succeeded", "succeeded"), agent_calls=2, tokens=600, time_ms=2000),
    Case(
        "verification_failed", baseline_mission, respond=respond_with_facts(analysis="Cites a [[ghost]] source."),
        status="failed", cause=MissionFailureCause.VERIFICATION_FAILED, run_outcome="failed", reason="verification_failed: ",
        node_statuses=("succeeded", "succeeded", "verification_failed"), agent_calls=2, tokens=600, time_ms=3000,
    ),
    Case(
        "model_timeout", baseline_mission, respond=_failure(ModelFailureKind.TIMEOUT),
        status="failed", cause=MissionFailureCause.EXECUTION_FAILED, run_outcome="failed", node_statuses=("failed", "skipped", "skipped"),
        reason="execution_failed: ",
        agent_calls=1, tokens=0, time_ms=1000,  # a failed call reports no tokens, and none are invented
    ),
    Case(
        "model_empty_response", baseline_mission, respond=_failure(ModelFailureKind.EMPTY_RESPONSE),
        status="failed", cause=MissionFailureCause.NO_RESULT, run_outcome="failed", node_statuses=("no_result", "skipped", "skipped"),
        reason="no_result: ",
        agent_calls=1, tokens=0, time_ms=1000,
    ),
    Case("plan_refused_at_validation", _refused("validation"), status="failed", cause=MissionFailureCause.PLAN_REJECTED, run_outcome=None,
         reason="plan_rejected: the plan was refused at the validation gate"),
    Case("plan_refused_at_compilation", _refused("compilation"), status="failed", cause=MissionFailureCause.PLAN_REJECTED, run_outcome=None,
         reason="plan_rejected: the plan was refused at the compilation gate"),
    Case("plan_refused_at_binding", _refused("binding"), status="failed", cause=MissionFailureCause.PLAN_REJECTED, run_outcome=None,
         reason="plan_rejected: the plan was refused at the binding gate"),
    Case(
        "admission_halt", baseline_mission, halt_at="analyse", status="paused", run_outcome="halted", reason="held for review",
        node_statuses=("succeeded", "not_reached", "not_reached"), agent_calls=1, tokens=300, time_ms=1000,
    ),
)
CASE_IDS = tuple(case.name for case in CASES)


def guard_for(case: Case):
    return locked_halt_when(lambda request: request.step_id == case.halt_at, "held for review") if case.halt_at else locked_admit_all()


def run_case(case: Case, executor, *, prior=None, rig=None, log=None, ids=None):
    """Record ``case`` on ``executor``. Returns the ``RecordedRun`` and the rig it ran over (to resume on)."""
    state, plan = case.mission()
    return record(
        state, plan, rig=rig, respond=case.respond, guard=guard_for(case), prior=prior, executor=executor,
        clock=FixedClock(), ids=ids or SequentialIds(), log=log,
    )
