"""The repository contract, held by the in-memory and the PostgreSQL implementations alike (decisions.md D-230, D-233; V1.4-B).

One set of tests, two implementations: the default suite runs it on the in-memory storage, and ``-m postgres`` (with ``EIDOS_TEST_DATABASE_URL``) runs the same tests on PostgreSQL. What is held: tenant
scoping on every call (a row of another tenant is never returned and never touched), compare-and-set transitions, an append that must continue the log exactly and is atomic with its artifacts,
write-once and idempotent artifacts, and the deterministic order of the supplied documents.
"""

from uuid import UUID

import pytest

from eidos.agents import ArtifactConflict
from eidos.contracts import ArtifactRef, StepId, TenantId
from eidos.service import ArtifactWrite, DuplicateIdempotencyKey, InMemoryStorage, Role, RunStatus, SequenceConflict
from eidos.state import replay

from eidos_service_fixture import ALICE, BOB, CAROL, DAVE, TENANT_A, TENANT_B
from eidos_storage_helpers import NOW, artifact, commit, events_for, make_record



@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.postgres)])
def storage(request):
    if request.param == "memory":
        yield InMemoryStorage()
        return
    import eidos_postgres_fixture as pg

    url = pg.reset_schema()
    opened = pg.open_storage(url)
    yield opened
    opened.close()


@pytest.fixture
def seeded(storage):
    storage.add_tenant(TENANT_A, "a")
    storage.add_tenant(TENANT_B, "b")
    storage.add_member(TENANT_A, ALICE, Role.OWNER)
    storage.add_member(TENANT_B, BOB, Role.MEMBER)
    storage.add_member(TENANT_A, CAROL, Role.MEMBER)
    storage.add_member(TENANT_B, CAROL, Role.MEMBER)
    return storage.repositories()


# --- tenancy ----------------------------------------------------------------------------------------------------------------------------


def test_memberships_are_the_tenants_a_user_belongs_to_with_their_role(seeded):
    (alice,) = seeded.tenancy.memberships_of(ALICE)
    assert (alice.tenant_id, alice.role.value) == (TENANT_A, "owner")
    assert [m.tenant_id for m in seeded.tenancy.memberships_of(CAROL)] == sorted([TENANT_A, TENANT_B], key=str)
    assert seeded.tenancy.memberships_of(DAVE) == ()


def test_the_nil_tenant_is_reserved_and_can_never_be_a_real_tenant(storage):
    with pytest.raises(Exception):
        storage.add_tenant(TenantId(UUID(int=0)), "nil")


# --- missions ---------------------------------------------------------------------------------------------------------------------------


def test_a_mission_is_stored_with_its_documents_and_is_visible_only_to_its_own_tenant(seeded):
    record = make_record()
    seeded.missions.create(record, (artifact("doc:2", "two"), artifact("doc:1", "one")))
    assert seeded.missions.get(TENANT_A, record.mission_id) == record
    assert seeded.missions.get(TENANT_B, record.mission_id) is None  # another tenant's mission is not there
    assert [str(a.ref) for a in seeded.artifacts(TENANT_A).supplied(record.execution_id)] == ["doc:1", "doc:2"]
    assert seeded.artifacts(TENANT_B).supplied(record.execution_id) == ()
    assert seeded.artifacts(TENANT_B).get(record.execution_id, ArtifactRef("doc:1")) is None


def test_an_idempotency_key_is_unique_within_a_tenant_and_free_across_tenants(seeded):
    first = make_record(key="k1")
    seeded.missions.create(first, ())
    with pytest.raises(DuplicateIdempotencyKey):
        seeded.missions.create(make_record(key="k1"), ())
    seeded.missions.create(make_record(TENANT_B, key="k1"), ())  # the same key in another tenant is another key
    seeded.missions.create(make_record(key=None), ())
    seeded.missions.create(make_record(key=None), ())  # a mission without a key never conflicts
    assert seeded.missions.find_by_idempotency_key(TENANT_A, "k1") == first
    assert seeded.missions.find_by_idempotency_key(TENANT_B, "k1").tenant_id == TENANT_B
    assert seeded.missions.find_by_idempotency_key(TENANT_A, "other") is None


def test_a_transition_is_a_compare_and_set_scoped_to_its_tenant(seeded):
    record = make_record()
    seeded.missions.create(record, ())

    def move(tenant, expected, new):
        return seeded.missions.transition(tenant, record.mission_id, expected=expected, new=new, reason="why", at=NOW)

    assert move(TENANT_A, (RunStatus.RUNNING,), RunStatus.FINISHED) is False  # not in the expected state
    assert move(TENANT_B, (RunStatus.CREATED,), RunStatus.QUEUED) is False  # another tenant's mission is not touched
    assert seeded.missions.get(TENANT_A, record.mission_id).run_status is RunStatus.CREATED
    assert move(TENANT_A, (RunStatus.CREATED, RunStatus.QUEUED), RunStatus.QUEUED) is True
    moved = seeded.missions.get(TENANT_A, record.mission_id)
    assert (moved.run_status, moved.run_status_reason) == (RunStatus.QUEUED, "why")
    assert move(TENANT_A, (RunStatus.CREATED,), RunStatus.QUEUED) is False  # a second start finds it already moved


def test_active_runs_are_counted_per_tenant_and_startup_recovery_interrupts_every_active_run_only(seeded):
    ids = {}
    for name, tenant, status in (
        ("q", TENANT_A, RunStatus.QUEUED), ("r", TENANT_A, RunStatus.RUNNING), ("c", TENANT_A, RunStatus.CREATED), ("f", TENANT_A, RunStatus.FINISHED), ("b", TENANT_B, RunStatus.RUNNING)
    ):
        record = make_record(tenant)
        seeded.missions.create(record, ())
        if status is not RunStatus.CREATED:
            assert seeded.missions.transition(tenant, record.mission_id, expected=(RunStatus.CREATED,), new=status, reason=None, at=NOW)
        ids[name] = (tenant, record.mission_id)
    assert seeded.missions.count_active(TENANT_A) == 2 and seeded.missions.count_active(TENANT_B) == 1
    assert seeded.missions.interrupt_active(reason="restart", at=NOW) == 3
    assert [seeded.missions.get(*ids[n]).run_status for n in "qrbcf"] == [RunStatus.INTERRUPTED] * 3 + [RunStatus.CREATED, RunStatus.FINISHED]
    assert seeded.missions.get(*ids["q"]).run_status_reason == "restart" and seeded.missions.count_active(TENANT_A) == 0
    assert all(len(seeded.events.read(*ids[n])) == 0 for n in "qrb")  # recovery writes no event


# --- events -----------------------------------------------------------------------------------------------------------------------------


def test_an_append_continues_the_log_and_reads_come_back_in_sequence_order_and_paged(seeded):
    record = make_record()
    seeded.missions.create(record, ())
    records = events_for(record)
    assert commit(seeded, record, records[:2]) == 2
    assert commit(seeded, record, records[2:], expected=2) == 3
    assert seeded.missions.get(TENANT_A, record.mission_id).last_sequence == 3
    assert seeded.events.read(TENANT_A, record.mission_id) == records
    assert seeded.events.read(TENANT_A, record.mission_id, after=1) == records[1:]
    assert seeded.events.read(TENANT_A, record.mission_id, after=1, limit=1) == records[1:2]
    assert seeded.events.read(TENANT_A, record.mission_id, after=3) == ()


def test_events_are_stored_as_the_records_the_reducer_applied_and_replay_to_the_same_state(seeded):
    record = make_record()
    seeded.missions.create(record, ())
    records = events_for(record)
    commit(seeded, record, records)
    stored = seeded.events.read(TENANT_A, record.mission_id)
    assert stored == records and replay(stored).state == replay(records).state


def test_an_append_that_does_not_continue_the_log_exactly_is_refused_and_writes_nothing(seeded):
    record = make_record()
    seeded.missions.create(record, ())
    records = events_for(record)
    commit(seeded, record, records[:1])
    for expected, batch in ((0, records[:1]), (2, records[1:2]), (1, records[2:3]), (1, records[2:3] + records[1:2])):  # stale, ahead, a gap, out of order
        with pytest.raises(SequenceConflict):
            commit(seeded, record, batch, expected=expected, artifacts=(ArtifactWrite(artifact("evidence:a"), "supplied"),))
    assert seeded.events.read(TENANT_A, record.mission_id) == records[:1]
    assert seeded.artifacts(TENANT_A).get(record.execution_id, ArtifactRef("evidence:a")) is None  # the artifacts of a refused append are not stored: it is atomic
    assert seeded.missions.get(TENANT_A, record.mission_id).last_sequence == 1


def test_two_writers_of_one_mission_cannot_both_append_the_same_sequence(seeded):
    record = make_record()
    seeded.missions.create(record, ())
    records = events_for(record)
    commit(seeded, record, records[:2])
    with pytest.raises(SequenceConflict):  # a second writer that still believes the log ends at 1
        commit(seeded, record, records[1:2], expected=1)
    assert commit(seeded, record, records[2:], expected=2) == 3


def test_an_append_for_another_tenants_mission_is_refused_and_touches_nothing(seeded):
    record = make_record()
    seeded.missions.create(record, ())
    foreign = make_record(TENANT_B, mission_id=record.mission_id)  # the same mission id, claimed under another tenant
    with pytest.raises(SequenceConflict):
        seeded.events.commit(
            tenant_id=TENANT_B, mission_id=record.mission_id, execution_id=record.execution_id, expected_last_sequence=0, artifacts=(), events=events_for(foreign)
        )
    assert seeded.events.read(TENANT_A, record.mission_id) == () and seeded.events.read(TENANT_B, record.mission_id) == ()


def test_reading_events_is_scoped_to_the_tenant(seeded):
    record = make_record()
    seeded.missions.create(record, ())
    commit(seeded, record, events_for(record))
    assert len(seeded.events.read(TENANT_A, record.mission_id)) == 3 and seeded.events.read(TENANT_B, record.mission_id) == ()


# --- artifacts --------------------------------------------------------------------------------------------------------------------------


def test_artifacts_are_written_with_the_events_and_a_repeat_of_a_commit_is_idempotent(seeded):
    record = make_record()
    seeded.missions.create(record, ())
    records = events_for(record)
    step = artifact("artifact:s1", "answer", "doc:1")
    writes = (ArtifactWrite(artifact("evidence:a", "chunk"), "supplied"), ArtifactWrite(step, "step", StepId("s1")))
    commit(seeded, record, records[:1], artifacts=writes)
    store = seeded.artifacts(TENANT_A)
    assert store.get(record.execution_id, ArtifactRef("evidence:a")) == artifact("evidence:a", "chunk")
    assert store.get_step_artifact(record.execution_id, StepId("s1")) == step and store.get(record.execution_id, ArtifactRef("artifact:s1")) == step
    commit(seeded, record, records[1:], expected=1, artifacts=writes)  # the same artifacts again with the next events: nothing changes, nothing conflicts
    assert [str(a.ref) for a in store.supplied(record.execution_id)] == ["evidence:a"]


def test_an_artifact_reference_is_write_once_and_a_conflicting_commit_writes_nothing(seeded):
    record = make_record()
    seeded.missions.create(record, (artifact("doc:1", "original"),))
    records = events_for(record)
    with pytest.raises(ArtifactConflict):
        commit(seeded, record, records[:1], artifacts=(ArtifactWrite(artifact("doc:1", "different"), "supplied"),))
    assert seeded.events.read(TENANT_A, record.mission_id) == () and seeded.missions.get(TENANT_A, record.mission_id).last_sequence == 0
    assert seeded.artifacts(TENANT_A).get(record.execution_id, ArtifactRef("doc:1")).content == "original"


def test_a_step_has_one_primary_artifact_and_a_second_is_refused(seeded):
    record = make_record()
    seeded.missions.create(record, ())
    store = seeded.artifacts(TENANT_A)
    store.put_step_artifact(record.execution_id, StepId("s1"), artifact("artifact:s1", "one"))
    with pytest.raises(ArtifactConflict):
        store.put_step_artifact(record.execution_id, StepId("s1"), artifact("artifact:other", "two"))
    with pytest.raises(ArtifactConflict):
        store.put_supplied(record.execution_id, artifact("artifact:s1", "again"))
    assert seeded.artifacts(TENANT_B).get_step_artifact(record.execution_id, StepId("s1")) is None


def test_supplied_documents_come_back_in_code_point_order_whatever_the_database_collation(seeded):
    record = make_record()
    refs = ["b", "B", "a", "A1", "a1", "Z", "_x", "doc:10", "doc:2"]
    seeded.missions.create(record, tuple(artifact(ref, ref) for ref in refs))
    assert [str(a.ref) for a in seeded.artifacts(TENANT_A).supplied(record.execution_id)] == sorted(refs)
