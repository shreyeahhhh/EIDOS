"""The write-through model: a durable event log and artifact store for one run (decisions.md D-230; invariants 1, 2, 8 and 15; V1.4-B).

The in-memory log is the runtime authority and the database is behind it, never ahead of it. What is held: only an applied event is written, in order, guarded by the expected sequence; a store
fault never raises into the runtime and is retried in order; the bounded final flush ends in a definite yes or no; a commit whose answer was lost is recognised; a second writer is a permanent
failure; and artifacts are written before the events that follow them.
"""

import pytest

from eidos.agents import Artifact, ArtifactConflict
from eidos.contracts import ArtifactRef, StepId
from eidos.service import ArtifactWrite, DurableEventLog, InMemoryStorage, RunPersistence, SequenceConflict, StorageError, WriteThroughArtifactStore
from eidos.state import EventProposal, replay

from eidos_service_fixture import TENANT_A
from eidos_storage_helpers import NOW, events_for, make_record


class Recording:
    """An ``EventStore`` that forwards to a real one, counts and records what it was asked, and fails as told."""

    def __init__(self, inner, *, fail=0, fail_with=None, land_then_fail=0):
        self.inner, self.fail, self.fail_with, self.land_then_fail = inner, fail, fail_with or StorageError("unreachable"), land_then_fail
        self.commits, self.batches = 0, []

    def commit(self, **kwargs):
        self.commits += 1
        self.batches.append((tuple(w.artifact.ref for w in kwargs["artifacts"]), tuple(r.event.sequence for r in kwargs["events"])))
        if self.fail:
            self.fail -= 1
            raise self.fail_with
        result = self.inner.commit(**kwargs)
        if self.land_then_fail:
            self.land_then_fail -= 1
            raise StorageError("the answer was lost")  # the write landed; the caller never heard
        return result

    def read(self, *args, **kwargs):
        return self.inner.read(*args, **kwargs)


def setup(**store_kwargs):
    storage = InMemoryStorage()
    storage.add_tenant(TENANT_A)
    record = make_record()
    storage.create(record, ())
    events = Recording(storage, **store_kwargs)
    sleeps = []
    persistence = RunPersistence(
        events=events, tenant_id=record.tenant_id, mission_id=record.mission_id, execution_id=record.execution_id, attempts=3, backoff_seconds=0.5, sleep=sleeps.append
    )
    return storage, record, events, persistence, DurableEventLog(persistence), sleeps


def proposals(record, count=3):
    return [
        EventProposal(event_id=r.event.event_id, tenant_id=r.event.tenant_id, mission_id=r.event.mission_id, occurred_at=NOW, recorded_at=NOW, payload=r.payload)
        for r in events_for(record, count)
    ]


def durable(storage, record):
    return storage.read(record.tenant_id, record.mission_id)


def test_every_applied_event_is_written_through_and_the_durable_log_replays_to_the_runtime_state():
    storage, record, events, persistence, log, _ = setup()
    for proposal in proposals(record):
        assert log.accept(proposal).applied
    assert durable(storage, record) == log.records and len(log.records) == 3
    assert replay(durable(storage, record)).state == log.state  # the fold of what is durable is what the runtime folded
    assert (events.commits, persistence.durable_last_sequence, persistence.pending, persistence.degraded) == (3, 3, 0, False)
    assert storage.get(record.tenant_id, record.mission_id).last_sequence == 3


def test_an_event_the_reducer_refuses_is_never_persisted():
    storage, record, events, persistence, log, _ = setup()
    first = proposals(record)[0]
    assert log.accept(first).applied
    duplicate = log.accept(first)  # the same event id again: the intake ignores it
    assert not duplicate.applied
    assert len(durable(storage, record)) == 1 and events.commits == 1


def test_a_store_fault_never_raises_into_the_runtime_and_the_outbox_is_retried_in_order_by_the_next_accept():
    storage, record, events, persistence, log, _ = setup(fail=2)
    first, second, third = proposals(record)
    assert log.accept(first).applied and persistence.degraded and durable(storage, record) == ()  # the write failed; the run carried on
    assert log.accept(second).applied and persistence.degraded and durable(storage, record) == ()
    assert persistence.last_error == "StorageError: unreachable" and persistence.pending == 2
    assert log.accept(third).applied and not persistence.degraded
    assert durable(storage, record) == log.records  # all three, once, in order, in one commit
    assert events.batches[-1] == ((), (1, 2, 3))


def test_the_final_flush_is_bounded_and_ends_in_a_definite_answer():
    storage, record, events, persistence, log, sleeps = setup(fail=99)
    log.accept(proposals(record)[0])
    assert persistence.finish() is False and persistence.degraded and persistence.pending == 1
    assert events.commits == 1 + 3 and sleeps == [0.5, 1.0]  # the accept's try, then three attempts with a growing pause between them; never more
    assert durable(storage, record) == ()


def test_the_final_flush_succeeds_as_soon_as_the_store_answers():
    storage, record, events, persistence, log, sleeps = setup(fail=2)
    log.accept(proposals(record)[0])
    assert persistence.finish() is True and sleeps == [0.5] and persistence.pending == 0
    assert durable(storage, record) == log.records


def test_a_commit_that_landed_although_its_answer_was_lost_is_recognised_and_not_written_twice():
    storage, record, events, persistence, log, _ = setup(land_then_fail=1)
    log.accept(proposals(record)[0])
    assert persistence.degraded  # the caller heard an error
    assert persistence.finish() is True and persistence.failure is None
    assert durable(storage, record) == log.records and len(durable(storage, record)) == 1
    assert persistence.durable_last_sequence == 1


def test_another_writer_of_the_mission_is_a_permanent_failure_and_nothing_more_is_written():
    storage, record, events, persistence, log, _ = setup()
    other = events_for(record)  # a different writer already committed the first event, under another event id
    storage.commit(tenant_id=record.tenant_id, mission_id=record.mission_id, execution_id=record.execution_id, expected_last_sequence=0, artifacts=(), events=other[:1])
    log.accept(proposals(record)[0])
    assert persistence.failure and persistence.failure.startswith("sequence_conflict")
    before = events.commits
    log.accept(proposals(record)[1])  # the run goes on in memory, but it does not touch the store again
    assert persistence.finish() is False and events.commits == before
    assert durable(storage, record) == other[:1]  # the other writer's log is untouched


def test_an_artifact_is_written_before_the_event_that_follows_it_and_together_when_the_store_was_down():
    storage, record, events, persistence, log, _ = setup()
    store = WriteThroughArtifactStore(persistence)
    store.put_step_artifact(record.execution_id, StepId("s1"), Artifact(ref=ArtifactRef("artifact:s1"), content_type="text/plain", content="answer"))
    log.accept(proposals(record)[0])
    assert events.batches == [((ArtifactRef("artifact:s1"),), ()), ((), (1,))]  # the artifact first, then the event that settles its node
    assert storage.artifacts_for(record.tenant_id).get_step_artifact(record.execution_id, StepId("s1")).content == "answer"

    storage2, record2, events2, persistence2, log2, _ = setup(fail=1)
    store2 = WriteThroughArtifactStore(persistence2)
    store2.put_supplied(record2.execution_id, Artifact(ref=ArtifactRef("evidence:a"), content_type="text/plain", content="chunk"))
    log2.accept(proposals(record2)[0])  # the artifact's write failed; the event's flush carries both, in one commit
    assert events2.batches[-1] == ((ArtifactRef("evidence:a"),), (1,)) and durable(storage2, record2) == log2.records


def test_the_artifact_store_reads_from_memory_refuses_a_second_write_before_queueing_and_preload_writes_nothing():
    storage, record, events, persistence, log, _ = setup()
    store = WriteThroughArtifactStore(persistence)
    doc = Artifact(ref=ArtifactRef("doc:1"), content_type="text/plain", content="supplied")
    store.preload(record.execution_id, (doc,))
    assert store.get(record.execution_id, ArtifactRef("doc:1")) == doc and store.supplied(record.execution_id) == (doc,)
    assert events.commits == 0  # already durable: not written again
    new = Artifact(ref=ArtifactRef("evidence:x"), content_type="text/plain", content="c")
    store.put_supplied(record.execution_id, new)
    with pytest.raises(ArtifactConflict):
        store.put_supplied(record.execution_id, new)  # write-once, refused by memory before anything is queued
    assert events.commits == 1 and persistence.pending == 0
    assert store.get_step_artifact(record.execution_id, StepId("none")) is None


def test_an_artifact_conflict_in_the_store_is_permanent():
    storage, record, events, persistence, log, _ = setup()
    storage.create(make_record(), ())  # unrelated
    other = Artifact(ref=ArtifactRef("doc:1"), content_type="text/plain", content="stored elsewhere")
    storage._artifact_store(record.tenant_id, record.execution_id).put_supplied(record.execution_id, other)  # someone already stored this reference here
    persistence.add_artifact(ArtifactWrite(artifact=Artifact(ref=ArtifactRef("doc:1"), content_type="text/plain", content="mine"), kind="supplied"))
    assert persistence.failure and persistence.failure.startswith("artifact_conflict") and persistence.finish() is False


def test_a_persistence_that_never_had_an_attempt_to_make_is_refused():
    storage, record, *_ = setup()
    with pytest.raises(ValueError):
        RunPersistence(events=storage, tenant_id=record.tenant_id, mission_id=record.mission_id, execution_id=record.execution_id, attempts=0)


def test_a_sequence_conflict_that_is_not_a_landed_commit_is_told_apart_from_one_that_is():
    class Conflicting:
        def commit(self, **kwargs):
            raise SequenceConflict("nope")

        def read(self, *args, **kwargs):
            return ()

    storage, record, *_ = setup()
    persistence = RunPersistence(events=Conflicting(), tenant_id=record.tenant_id, mission_id=record.mission_id, execution_id=record.execution_id)
    persistence.add_event(events_for(record)[0])
    assert persistence.failure and persistence.finish() is False
