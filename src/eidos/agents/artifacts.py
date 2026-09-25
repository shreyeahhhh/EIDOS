"""The V0.4 artifact model and the in-memory artifact store (decisions.md D-137, D-145).

An artifact has four fields — ``ref``, ``content_type``, ``content`` and ``source_refs`` (D-145). At V0.4 they are primarily text or
Markdown plus references to the artifacts they draw on. ``ArtifactRef`` itself stays opaque (D-098): the runtime never sees an
artifact's content, so this model lives here, with the store, and not in ``eidos.contracts``.

The store is how a work node reads its predecessors' outputs and the supplied documents without changing the
``WorkExecutor`` signature (D-137). Everything in it is **namespaced by execution**:

- **supplied** artifacts are the documents the caller placed before a run and the documents a tool retrieved during it (the tool gate stores each
  one as a supplied artifact, V1.2, D-207), and are addressed by their ``ArtifactRef``;
- a work step's **primary** artifact (exactly one per step) is held under ``(execution_id, step_id)``;
- every artifact, supplied or produced, is also addressable by its ``ref``, which is unique within an execution.

It is in memory only (D-005): nothing is persisted, and persistence stays with D-017. It is thread-safe, because a level's
nodes run on worker threads. Writing is refused, never overwritten: a second artifact for the same ref, or a second primary
artifact for a step, raises ``ArtifactConflict``. Reading what is absent returns ``None``, never a guess.
"""

import threading
from typing import Protocol

from pydantic import Field, model_validator

from eidos.contracts import ArtifactRef, EidosModel, ExecutionId, StepId


class Artifact(EidosModel):
    ref: ArtifactRef = Field(min_length=1)
    content_type: str = Field(min_length=1)
    content: str
    source_refs: tuple[ArtifactRef, ...] = ()

    @model_validator(mode="after")
    def _check_source_refs(self) -> "Artifact":
        if any(not source for source in self.source_refs):
            raise ValueError("a source reference is never blank")
        if len(set(self.source_refs)) != len(self.source_refs):
            raise ValueError("an artifact lists each source at most once")
        if self.ref in self.source_refs:
            raise ValueError("an artifact cannot cite itself")
        return self


class ArtifactConflict(ValueError):
    """A write that would overwrite: the ref is taken, or the step already has its primary artifact."""


class ArtifactStore(Protocol):
    """Where artifacts live during an execution. Thread-safe; every method is scoped by ``execution_id``."""

    def put_supplied(self, execution_id: ExecutionId, artifact: Artifact) -> None: ...

    def put_step_artifact(self, execution_id: ExecutionId, step_id: StepId, artifact: Artifact) -> None: ...

    def get(self, execution_id: ExecutionId, ref: ArtifactRef) -> Artifact | None: ...

    def get_step_artifact(self, execution_id: ExecutionId, step_id: StepId) -> Artifact | None: ...

    def supplied(self, execution_id: ExecutionId) -> tuple[Artifact, ...]: ...


class InMemoryArtifactStore:
    """The V0.4 store: dictionaries behind one lock. Nothing is shared between executions."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_ref: dict[tuple[ExecutionId, ArtifactRef], Artifact] = {}
        self._step_ref: dict[tuple[ExecutionId, StepId], ArtifactRef] = {}
        self._supplied_refs: dict[ExecutionId, list[ArtifactRef]] = {}

    def put_supplied(self, execution_id: ExecutionId, artifact: Artifact) -> None:
        with self._lock:
            self._insert(execution_id, artifact)
            self._supplied_refs.setdefault(execution_id, []).append(artifact.ref)

    def put_step_artifact(self, execution_id: ExecutionId, step_id: StepId, artifact: Artifact) -> None:
        with self._lock:
            if (execution_id, step_id) in self._step_ref:
                raise ArtifactConflict(f"step {str(step_id)!r} already has its primary artifact")
            self._insert(execution_id, artifact)
            self._step_ref[(execution_id, step_id)] = artifact.ref

    def get(self, execution_id: ExecutionId, ref: ArtifactRef) -> Artifact | None:
        with self._lock:
            return self._by_ref.get((execution_id, ref))

    def get_step_artifact(self, execution_id: ExecutionId, step_id: StepId) -> Artifact | None:
        with self._lock:
            ref = self._step_ref.get((execution_id, step_id))
            return None if ref is None else self._by_ref[(execution_id, ref)]

    def supplied(self, execution_id: ExecutionId) -> tuple[Artifact, ...]:
        """Every supplied artifact of this execution, ordered by ``ref`` so the order never depends on insertion."""
        with self._lock:
            refs = sorted(self._supplied_refs.get(execution_id, ()))
            return tuple(self._by_ref[(execution_id, ref)] for ref in refs)

    def _insert(self, execution_id: ExecutionId, artifact: Artifact) -> None:
        key = (execution_id, artifact.ref)
        if key in self._by_ref:
            raise ArtifactConflict(f"ref {str(artifact.ref)!r} is already taken in this execution")
        self._by_ref[key] = artifact
