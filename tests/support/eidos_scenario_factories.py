"""Helpers for V0.3 scenario tests: drive a whole mission through the whole path.

A scenario is not a component test. It takes a real ``MissionState`` and follows a plan through every
V0.3 authority in order — V0.2 validation, the compiler, a frozen execution context, and *both* executors —
and asserts on the recorded ``RunResult``. V0.3 writes no events (D-123), so the ``RunResult`` and what the
ports were asked are the whole record of a run.

``drive`` runs the reference executor and the LangGraph backend on identical inputs and asserts they agree
byte for byte (``conform``), so every scenario is a conformance check as well as a behaviour check; the
scenario then asserts what the run *should* have been, written out by hand, never derived from the run.

Nothing here is a mock agent of the product: the work executor, verifier and guard a scenario passes in are
scripted test doubles keyed by step id. Identifiers are fixed, so a scenario is deterministic.
"""

from dataclasses import dataclass

from eidos.compiler import CompiledPlan, CompileReport, compile_plan
from eidos.contracts import MissionState, Plan
from eidos.runtime import ExecutionContext, RunRejection, RunResult, context_from_state
from eidos.validation import PlanValidationReport, SystemLimits, validate_plan

from eidos_backend_factories import LockedGuard, LockedVerifier, LockedWork, conform, locked_admit_all
from eidos_mission_factories import CAPABILITIES, make_mission, make_mission_plan  # noqa: F401  (re-exported for the scenarios)
from eidos_validation_factories import make_system_limits

@dataclass(frozen=True, slots=True, kw_only=True)
class Attempt:
    """What happened when one plan was driven through validate -> compile -> execute.

    ``result`` is ``None`` when the plan never reached execution (it was not validated, or not compilable);
    otherwise it is the ``RunResult`` or ``RunRejection`` both executors returned, which ``drive`` has
    already asserted are identical. ``work``, ``verifier`` and ``guard`` are the reference executor's
    doubles (fresh and untouched when nothing ran) — what the ports were asked.
    """

    plan: Plan
    report: PlanValidationReport
    compile_report: CompileReport
    compiled: CompiledPlan | None
    context: ExecutionContext | None
    result: RunResult | RunRejection | None
    work: LockedWork
    verifier: LockedVerifier
    guard: LockedGuard

    @property
    def ran(self) -> bool:
        return self.result is not None


def drive(
    state: MissionState,
    plan: Plan,
    *,
    limits: SystemLimits | None = None,
    report: PlanValidationReport | None = None,
    context: ExecutionContext | None = None,
    prior=None,
    work=None,
    verifier=None,
    guard=None,
) -> Attempt:
    """Validate ``plan`` against ``state``, compile it, and — only if both allow — run it on both executors.

    ``work``, ``verifier`` and ``guard`` are *factories* returning fresh doubles (each executor gets its own).
    ``report`` overrides the validation evidence handed to the compiler (a scenario about the wrong evidence);
    ``context`` and ``prior`` override what the run is given.
    """
    report = report if report is not None else validate_plan(plan, state, limits or make_system_limits())
    compile_report = compile_plan(plan, report)
    if not compile_report.succeeded:
        return Attempt(
            plan=plan,
            report=report,
            compile_report=compile_report,
            compiled=None,
            context=None,
            result=None,
            work=LockedWork(),
            verifier=LockedVerifier(),
            guard=locked_admit_all(),
        )
    compiled = compile_report.compiled
    context = context if context is not None else context_from_state(state, compiled)
    reference, _, runs = conform(
        compiled, work_script=work, verifier_script=verifier, guard=guard, prior=prior, context=context
    )
    _, reference_work, reference_verifier, reference_guard = runs[0]
    return Attempt(
        plan=plan,
        report=report,
        compile_report=compile_report,
        compiled=compiled,
        context=context,
        result=reference,
        work=reference_work,
        verifier=reference_verifier,
        guard=reference_guard,
    )
