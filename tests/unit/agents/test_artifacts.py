"""The V0.4 artifact model and in-memory store (decisions.md D-137, D-145)."""

import threading
from uuid import UUID

import pytest
from pydantic import ValidationError

from eidos.agents import Artifact, ArtifactConflict, InMemoryArtifactStore
from eidos.contracts import ArtifactRef, ExecutionId, StepId

E1 = ExecutionId(UUID(int=1))
E2 = ExecutionId(UUID(int=2))


def artifact(ref="doc:a", content="text", **overrides) -> Artifact:
    fields = dict(ref=ArtifactRef(ref), content_type="text/markdown", content=content)
    fields.update(overrides)
    return Artifact(**fields)


# --- the model: four fields and nothing else (D-145) ------------------------------------------------------------------


def test_an_artifact_has_exactly_four_fields():
    assert list(Artifact.model_fields) == ["ref", "content_type", "content", "source_refs"]


def test_source_refs_default_to_none_and_the_other_three_are_required():
    assert artifact().source_refs == ()
    for missing in ("ref", "content_type", "content"):
        fields = dict(ref="a", content_type="text/plain", content="x")
        del fields[missing]
        with pytest.raises(ValidationError):
            Artifact(**fields)


@pytest.mark.parametrize("bad", [dict(ref=""), dict(content_type=""), dict(ref=None), dict(content=None), dict(content=5)])
def test_a_blank_or_mistyped_field_is_rejected(bad):
    with pytest.raises(ValidationError):
        artifact(**bad)


def test_an_empty_content_is_a_valid_artifact_so_that_verification_can_judge_it():
    assert artifact(content="").content == ""


@pytest.mark.parametrize(
    "sources",
    [("x", "x"), ("doc:a",), ("",)],
    ids=["a source listed twice", "an artifact citing itself", "a blank source"],
)
def test_source_references_are_distinct_non_blank_and_never_self_references(sources):
    with pytest.raises(ValidationError):
        artifact(ref="doc:a", source_refs=tuple(ArtifactRef(s) for s in sources))


def test_extra_fields_are_rejected_and_the_artifact_is_frozen():
    with pytest.raises(ValidationError):
        artifact(author="model")
    with pytest.raises(ValidationError):
        artifact().content = "changed"


def test_an_artifact_round_trips_through_json_unchanged():
    original = artifact(source_refs=(ArtifactRef("doc:b"), ArtifactRef("doc:c")))
    assert Artifact.model_validate_json(original.model_dump_json()) == original


# --- supplied artifacts: addressed by ref, namespaced by execution (D-145) ------------------------------------------------


def test_a_supplied_artifact_is_addressed_by_its_ref():
    store = InMemoryArtifactStore()
    doc = artifact("doc:a")
    store.put_supplied(E1, doc)
    assert store.get(E1, ArtifactRef("doc:a")) == doc


def test_supplied_artifacts_come_back_ordered_by_ref_whatever_order_they_went_in():
    store = InMemoryArtifactStore()
    for ref in ("doc:c", "doc:a", "doc:b"):
        store.put_supplied(E1, artifact(ref))
    assert [a.ref for a in store.supplied(E1)] == ["doc:a", "doc:b", "doc:c"]


def test_nothing_is_shared_between_executions():
    store = InMemoryArtifactStore()
    store.put_supplied(E1, artifact("doc:a"))
    assert store.get(E2, ArtifactRef("doc:a")) is None
    assert store.supplied(E2) == ()
    store.put_supplied(E2, artifact("doc:a", content="the other execution's"))  # the same ref, another namespace
    assert store.get(E1, ArtifactRef("doc:a")).content == "text"
    assert store.get(E2, ArtifactRef("doc:a")).content == "the other execution's"


def test_the_same_ref_cannot_be_supplied_twice_in_one_execution():
    store = InMemoryArtifactStore()
    store.put_supplied(E1, artifact("doc:a", content="first"))
    with pytest.raises(ArtifactConflict):
        store.put_supplied(E1, artifact("doc:a", content="second"))
    assert store.get(E1, ArtifactRef("doc:a")).content == "first"  # never overwritten
    assert len(store.supplied(E1)) == 1


def test_an_absent_artifact_is_none_never_a_guess():
    store = InMemoryArtifactStore()
    assert store.get(E1, ArtifactRef("nope")) is None
    assert store.get_step_artifact(E1, StepId("nope")) is None
    assert store.supplied(E1) == ()


# --- a step's one primary artifact (D-137) ------------------------------------------------------------------------------


def test_a_steps_primary_artifact_is_held_under_execution_and_step():
    store = InMemoryArtifactStore()
    out = artifact("artifact:gather", content="findings")
    store.put_step_artifact(E1, StepId("gather"), out)
    assert store.get_step_artifact(E1, StepId("gather")) == out
    assert store.get(E1, ArtifactRef("artifact:gather")) == out  # and it is addressable by ref, for citations
    assert store.get_step_artifact(E2, StepId("gather")) is None


def test_a_step_has_one_primary_artifact_and_a_second_is_refused():
    store = InMemoryArtifactStore()
    store.put_step_artifact(E1, StepId("s"), artifact("artifact:one"))
    with pytest.raises(ArtifactConflict, match="primary artifact"):
        store.put_step_artifact(E1, StepId("s"), artifact("artifact:two"))
    assert store.get(E1, ArtifactRef("artifact:two")) is None  # the refused write left nothing behind


def test_a_produced_artifact_cannot_take_a_ref_that_is_already_supplied_or_produced():
    store = InMemoryArtifactStore()
    store.put_supplied(E1, artifact("doc:a"))
    with pytest.raises(ArtifactConflict, match="already taken"):
        store.put_step_artifact(E1, StepId("s"), artifact("doc:a"))
    assert store.get_step_artifact(E1, StepId("s")) is None  # not half-written
    store.put_step_artifact(E1, StepId("s"), artifact("artifact:s"))
    with pytest.raises(ArtifactConflict):
        store.put_supplied(E1, artifact("artifact:s"))


def test_a_produced_artifact_is_not_a_supplied_document():
    store = InMemoryArtifactStore()
    store.put_supplied(E1, artifact("doc:a"))
    store.put_step_artifact(E1, StepId("s"), artifact("artifact:s"))
    assert [a.ref for a in store.supplied(E1)] == ["doc:a"]
    # ...and a supplied document is not any step's primary artifact, whatever its ref looks like.
    assert store.get_step_artifact(E1, StepId("doc:a")) is None
    assert store.get_step_artifact(E1, StepId("s")).ref == "artifact:s"


# --- thread safety: a level's nodes run on worker threads ---------------------------------------------------------------------


def run_threads(target, count):
    threads = [threading.Thread(target=target, args=(n,)) for n in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


def test_concurrent_writers_of_distinct_artifacts_all_land():
    store = InMemoryArtifactStore()
    run_threads(lambda n: store.put_step_artifact(E1, StepId(f"s{n}"), artifact(f"artifact:s{n}", content=str(n))), 200)
    for n in range(200):
        assert store.get_step_artifact(E1, StepId(f"s{n}")).content == str(n)


def test_concurrent_writers_of_the_same_ref_produce_exactly_one_winner():
    store = InMemoryArtifactStore()
    outcomes = []
    lock = threading.Lock()

    def write(n):
        try:
            store.put_supplied(E1, artifact("doc:contended", content=f"writer {n}"))
            result = "won"
        except ArtifactConflict:
            result = "lost"
        with lock:
            outcomes.append(result)

    run_threads(write, 64)
    assert sorted(outcomes) == ["lost"] * 63 + ["won"]
    assert len(store.supplied(E1)) == 1


def test_concurrent_readers_never_see_a_partial_write():
    store = InMemoryArtifactStore()
    seen = []
    lock = threading.Lock()

    def work(n):
        if n % 2 == 0:
            store.put_step_artifact(E1, StepId(f"s{n}"), artifact(f"artifact:s{n}", content="complete"))
        else:
            found = store.get_step_artifact(E1, StepId(f"s{n - 1}"))
            with lock:
                seen.append(found)

    run_threads(work, 200)
    assert all(found is None or found.content == "complete" for found in seen)
