"""Helpers for backend tests: run the reference executor and the LangGraph backend side by side.

The LangGraph backend runs a level's nodes concurrently on worker threads, so the recording doubles used
against it must record *atomically*, and a test must compare what was recorded as a set of facts, never as
an ordered log — the order of concurrent calls is exactly the scheduling detail D-117 says is not part of
correctness. What must match the reference exactly is the ``RunResult`` (or ``RunRejection``), byte for byte.
"""

import threading

from eidos.backends.langgraph import LangGraphExecutor
from eidos.runtime import AdmissionDecision, SequentialExecutor, VerificationResult, WorkResult

from eidos_runtime_factories import (
    RecordingGuard,
    ScriptedVerifier,
    ScriptedWork,
    artifact_of,
    context_for,
)


class LockedWork(ScriptedWork):
    """A scripted work executor that records under a lock (same scripting rules as ``ScriptedWork``)."""

    def __init__(self, script=None):
        super().__init__(script)
        self._lock = threading.Lock()

    def execute(self, context, node):
        with self._lock:
            self.calls.append(node.step_id)
            self.contexts.append(context)
            self.nodes.append(node)
        entry = self.script.get(node.step_id)
        if entry is None:
            return WorkResult.produced(artifact_of(node.step_id))
        if isinstance(entry, BaseException):
            raise entry
        if callable(entry):
            return entry(context, node)
        return entry


class LockedVerifier(ScriptedVerifier):
    """Records each verification as one atomic ``(step_id, predecessors)`` fact."""

    def __init__(self, script=None):
        super().__init__(script)
        self._lock = threading.Lock()
        self.records: list[tuple] = []

    def verify(self, context, node, predecessors):
        with self._lock:
            self.records.append((node.step_id, predecessors))
            self.calls.append(node.step_id)
            self.contexts.append(context)
        entry = self.script.get(node.step_id)
        if entry is None:
            return VerificationResult.passed("verified")
        if isinstance(entry, BaseException):
            raise entry
        if callable(entry):
            return entry(context, node, predecessors)
        return entry


class LockedGuard(RecordingGuard):
    def __init__(self, decide=None):
        super().__init__(decide)
        self._lock = threading.Lock()

    def admit(self, request):
        with self._lock:
            self.requests.append(request)
        return self.decide(request)


def locked_admit_all() -> LockedGuard:
    return LockedGuard()


def locked_halt_when(predicate, reason: str = "budget exhausted") -> LockedGuard:
    return LockedGuard(
        lambda request: AdmissionDecision.halt(reason) if predicate(request) else AdmissionDecision.admit()
    )


def conform(compiled, *, work_script=None, verifier_script=None, guard=None, prior=None, context=None):
    """Run both executors on identical inputs and assert they agree exactly.

    ``work_script``, ``verifier_script`` and ``guard`` are *factories*, so each executor gets fresh
    doubles with its own recording. Returns ``(reference_result, backend_result, doubles)``.
    """
    context = context or context_for(compiled)
    runs = []
    for executor_class in (SequentialExecutor, LangGraphExecutor):
        work = LockedWork(work_script() if work_script else None)
        verifier = LockedVerifier(verifier_script() if verifier_script else None)
        the_guard = guard() if guard else locked_admit_all()
        result = executor_class(work_executor=work, verifier=verifier, admission_guard=the_guard).run(
            compiled, context, prior
        )
        runs.append((result, work, verifier, the_guard))
    (reference, ref_work, ref_verifier, ref_guard), (backend, lg_work, lg_verifier, lg_guard) = runs

    assert type(backend) is type(reference)
    assert backend == reference
    assert backend.model_dump_json() == reference.model_dump_json()
    # What each port was asked, as facts — never as an ordered log.
    assert sorted(lg_work.calls) == sorted(ref_work.calls)
    assert len(lg_verifier.records) == len(ref_verifier.records)
    assert dict(lg_verifier.records) == dict(ref_verifier.records)
    if hasattr(ref_guard, "asked"):  # the raising and junk guards record nothing
        assert sorted(lg_guard.asked()) == sorted(ref_guard.asked())
    assert all(c == context for c in lg_work.contexts + lg_verifier.contexts)
    return reference, backend, runs
