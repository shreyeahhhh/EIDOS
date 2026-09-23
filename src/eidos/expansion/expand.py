"""``expand_strategy`` — the deterministic Strategy-to-Plan expansion boundary (decisions.md D-194, D-195; V0.9
Step 2).

**One capability occurrence, one ``AgentStep``.** ``StrategyStage.capabilities`` is a tuple, not a set (V0.7): a
capability named twice in one stage is two occurrences, and expansion never deduplicates them — each becomes its
own ``AgentStep``, exactly mirroring how ``eidos.planning.selector.structural_cost`` already counts *occurrences*,
never distinct names.

**Stage boundaries are dependency edges — D-179's own words, applied literally.** D-179 already defines what a
stage means: *"stage i+1 depends on the whole of stage i."* Stage 0's steps are roots (``depends_on=()``); every
later stage's steps each depend on **every** step generated from the immediately preceding stage (full fan-out,
not a chain within the stage) — capabilities within one stage never depend on each other.

**``FINAL`` depends on exactly the final stage, never transitively on an earlier one** (D-195). The real, already
-shipped V0.4 baseline plan already does this (``check`` depends only on ``analyse``, never on ``gather`` too),
and it matches how ``eidos.agents.verification`` actually reads a ``VerifyNode``: it verifies "the artifacts the
VERIFY node's predecessors produced" — ``depends_on`` is the verifier's own evidence boundary, not a redundant
ordering hint. Evidence from an earlier stage stays reachable through citation-following (D-146), not through a
direct edge. ``NONE`` produces no ``VERIFY`` step. Empty stages produce an empty ``Plan`` regardless of
``verification`` — there is no "final stage" for a ``VERIFY`` step to depend on, so none is emitted.

**Identity.** ``step_id`` is string-backed and exempt from D-053's UUID default (D-092: planner-authored, unique
within one Plan) — so it is a pure, deterministic derivation from ``(stage_index, position_in_stage, capability)``,
needing no injected source at all; two distinct occurrences can never collide, because their ``(stage_index,
position_in_stage)`` pair is already unique across the whole Plan. ``plan_id`` is UUID-backed with no exemption
(D-053 default), so it is drawn from an injected ``PlanIdSource`` — never generated internally — exactly mirroring
``eidos.planning.pipeline.StrategyIdSource`` one layer down and ``eidos.recording.ports.IdSource`` before that.
``tenant_id``/``mission_id`` are copied from the ``Strategy`` unchanged. The produced ``Plan`` is always fresh:
``version=1``, ``parent_plan_id=None``, ``replan_reason=None`` — replanning lineage through strategy selection is
not sketched here.

**What this module does not do.** It does not re-run the feasibility gate one layer down — admissibility was
already decided before a ``Strategy`` was selected (D-180, D-183). It does not run, duplicate or approximate
any V0.2 validation rule: the produced ``Plan`` is an ordinary value, handed to the existing, unmodified
``eidos.validation``/``eidos.compiler`` pipeline exactly as any hand-authored Plan would be (D-178). It does not
resolve D-129 (how a work node receives its predecessors' outputs stays Open); the edges below are built to be
correct under the mechanism that already, actually works today (D-137's artifact-store fetch), not to settle that
question.
"""

from typing import Protocol

from eidos.contracts import (
    AgentStep,
    CapabilityId,
    ControlStep,
    Plan,
    PlanId,
    PlanStep,
    PlanStepKind,
    StepId,
)
from eidos.planning import Strategy, VerificationPosture


class PlanIdSource(Protocol):
    """Draws one ``PlanId`` per expansion call. Injected, never drawn inside this deterministic core (D-194;
    mirrors ``eidos.planning.pipeline.StrategyIdSource`` one layer down) — a caller supplies one."""

    def next_plan_id(self) -> PlanId: ...


def _agent_step_id(stage_index: int, position: int, capability: CapabilityId) -> StepId:
    return StepId(f"stage{stage_index}_{position}_{capability}")


def expand_strategy(strategy: Strategy, *, ids: PlanIdSource) -> Plan:
    """Expand ``strategy`` into a fresh, unvalidated ``Plan`` (D-194, D-195). Pure and deterministic given
    ``ids``: no I/O, no clock, no randomness, no model call, no live agent lookup, no feasibility re-check."""
    steps: list[PlanStep] = []
    previous_stage_ids: tuple[StepId, ...] = ()

    for stage_index, stage in enumerate(strategy.stages):
        stage_ids: list[StepId] = []
        for position, capability in enumerate(stage.capabilities):
            step_id = _agent_step_id(stage_index, position, capability)
            steps.append(AgentStep(step_id=step_id, depends_on=previous_stage_ids, capability=capability))
            stage_ids.append(step_id)
        previous_stage_ids = tuple(stage_ids)

    if strategy.stages and strategy.verification is VerificationPosture.FINAL:
        steps.append(
            ControlStep(step_id=StepId("verify"), depends_on=previous_stage_ids, kind=PlanStepKind.VERIFY)
        )

    return Plan(
        tenant_id=strategy.tenant_id,
        plan_id=ids.next_plan_id(),
        mission_id=strategy.mission_id,
        version=1,
        parent_plan_id=None,
        replan_reason=None,
        steps=tuple(steps),
    )
