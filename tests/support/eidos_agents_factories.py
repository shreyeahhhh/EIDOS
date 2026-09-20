"""Factories and doubles for V0.4 agent tests.

``ScriptedModel`` is the fake at the model seam (D-136): the default suite never reaches a real model. It answers
as a test scripted, records every request atomically, and is thread-safe, because the LangGraph backend runs a
level's nodes on worker threads. Nothing here names a real model or provider.
"""

import threading
from uuid import UUID

from eidos.agents import Artifact, GenerationParameters, ModelRequest, ModelResponse, ModelSettings
from eidos.compiler import compile_plan
from eidos.contracts import ArtifactRef, CapabilityId, PlanStepKind, ReliabilityContractId, StepId

from eidos_compiler_factories import forged_accepted_report
from eidos_factories import (
    make_agent_step,
    make_control_step,
    make_plan,
    make_reliability_contract,
    make_task_genome,
)
from eidos_runtime_factories import context_for


def make_settings(**overrides) -> ModelSettings:
    fields = dict(
        model="test-model",
        parameters=GenerationParameters(temperature=0.0, seed=7, max_output_tokens=256),
        timeout_seconds=5.0,
    )
    fields.update(overrides)
    return ModelSettings(**fields)


class ScriptedModel:
    """A ``ModelPort`` that answers with ``respond(request)``.

    ``respond`` may return a ``ModelResponse`` or ``ModelFailure``, or raise (to test containment). By default it
    answers ``"scripted answer"``. Every request is recorded, under a lock.
    """

    def __init__(self, respond=None):
        self._respond = respond or (lambda request: ModelResponse(text="scripted answer"))
        self._lock = threading.Lock()
        self.requests: list[ModelRequest] = []

    def complete(self, request):
        with self._lock:
            self.requests.append(request)
        return self._respond(request)

    @property
    def calls(self) -> int:
        with self._lock:
            return len(self.requests)


# --- plans, contexts and artifacts for agent tests ------------------------------------------------------------------------


def compiled_with(spec, capabilities=None, verify=()):
    """Compile ``{"step": "dep1 dep2"}``; ``capabilities`` maps a work step to the capability it requests (default research)."""
    steps = []
    for name, deps in spec.items():
        depends_on = tuple(StepId(d) for d in deps.split())
        if name in verify:
            steps.append(make_control_step(step_id=StepId(name), depends_on=depends_on, kind=PlanStepKind.VERIFY))
        else:
            capability = CapabilityId((capabilities or {}).get(name, "research"))
            steps.append(make_agent_step(step_id=StepId(name), depends_on=depends_on, capability=capability))
    plan = make_plan(steps=tuple(steps))
    report = compile_plan(plan, forged_accepted_report(plan))
    assert report.succeeded, report.violations
    return report.compiled


def node_of(compiled, step_id):
    return next(node for node in compiled.nodes if node.step_id == step_id)


def context_requiring(compiled, min_independent_evidence, **contract_overrides):
    """A context whose contract asks for ``min_independent_evidence`` distinct sources."""
    contract = make_reliability_contract(
        tenant_id=compiled.tenant_id,
        contract_id=ReliabilityContractId(UUID(int=11)),
        min_independent_evidence=min_independent_evidence,
        **contract_overrides,
    )
    return context_for(compiled, task_genome=make_task_genome(contract=contract), reliability_contract=contract)


def doc(ref, content="Some supplied text.", *, content_type="text/markdown", sources=()) -> Artifact:
    return Artifact(ref=ArtifactRef(ref), content_type=content_type, content=content,
                    source_refs=tuple(ArtifactRef(s) for s in sources))
