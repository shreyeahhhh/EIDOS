"""The product backend's whole path, with the real runtime and a scripted model (decisions.md D-230 to D-234; invariants 1, 2, 8, 15 and 16; V1.4-B).

What is held: what a run makes durable is exactly what the runtime folded, so replaying the durable log gives the runtime's own final state; a second service over the same storage (a restart) answers
every read identically because it holds nothing but the log; the model, retrieval and citation facts of D-231 are in the durable events, replans included; a store that fails part-way leaves a
valid prefix and an ``error`` run and no fabricated failure; a tenant's runs and artifacts are their own even when they run together; and one mission is never run twice.
"""

import threading

from eidos.contracts import MissionEventType, MissionStatus
from eidos.replanning import ReplanRun, run_with_replanning
from eidos.service import InMemoryStorage, KnowledgeProvision, RunStatus, StorageError
from eidos.state import execution_record, replay

from eidos_replanning_factories import ScriptedCalls, always_fails
from eidos_search_fixture import cite_every_document
from eidos_service_fixture import TENANT_A, TENANT_B, make_rig, make_spec


def created(rig, who="alice", **spec):
    context = rig.context(who)
    return context, rig.service.create_mission(context, make_spec(**spec))[0].mission_id


def directly(rig, mission_id, tenant=TENANT_A):
    """One run driven by hand through the service's own composition: what the runner does, with the run itself in the caller's hand so its in-memory result can be compared."""
    record = rig.storage.get(tenant, mission_id)
    prepared = rig.composition.prepare(record, rig.storage.artifacts_for(tenant).supplied(record.execution_id))
    outcome = run_with_replanning(**prepared.run_arguments)
    assert isinstance(outcome, ReplanRun) and prepared.persistence.finish()
    return record, prepared, outcome


def shape(records):
    return [(r.event.type.value, getattr(getattr(r.payload, "result", None), "status", None) and r.payload.result.status.value) for r in records]


# --- what is durable is what the runtime folded --------------------------------------------------------------------------------------------


def test_the_durable_log_is_the_runtimes_log_and_replays_to_the_state_it_ended_with():
    rig = make_rig()
    _, mission_id = created(rig)
    record, prepared, outcome = directly(rig, mission_id)
    durable = rig.storage.read(TENANT_A, mission_id)
    assert durable == outcome.log.records and len(durable) > 6 and outcome.refused == () and outcome.discrepancies == ()
    replayed = replay(durable)
    assert replayed.rejection is None and replayed.state == outcome.log.state and replayed.state.status is MissionStatus.COMPLETED
    assert rig.storage.get(TENANT_A, mission_id).last_sequence == len(durable) == prepared.persistence.durable_last_sequence
    assert (prepared.persistence.pending, prepared.persistence.degraded, prepared.persistence.failure) == (0, False, None)


def test_every_artifact_the_run_made_is_durable_and_the_supplied_ones_were_stored_once_before_it():
    rig = make_rig()
    _, mission_id = created(rig)
    record, prepared, outcome = directly(rig, mission_id)
    stored = rig.storage.artifacts_for(TENANT_A)
    steps = [step for step in execution_record(rig.storage.read(TENANT_A, mission_id)).steps if step.result is not None and step.result.artifact is not None]
    assert steps
    for step in steps:
        made = stored.get(record.execution_id, step.result.artifact)
        assert made is not None and made == prepared.store.get(record.execution_id, step.result.artifact)
        assert stored.get_step_artifact(record.execution_id, step.step_id) == made
    assert [str(a.ref) for a in stored.supplied(record.execution_id)] == ["doc:1", "doc:2", "doc:3"]


def test_the_model_facts_of_the_tracker_are_in_the_durable_events_and_so_survive_a_restart():
    rig = make_rig()
    _, mission_id = created(rig)
    directly(rig, mission_id)
    steps = execution_record(rig.storage.read(TENANT_A, mission_id)).steps
    calls = [call for step in steps for call in step.model_calls]
    assert calls and all(call.prompt_tokens == 100 and call.output_tokens == 50 for call in calls)
    assert sum(len(step.citations) for step in steps) > 0
    restarted = make_rig(storage=rig.storage)  # a new process over the same database
    assert restarted.service.get_mission(restarted.context("alice"), mission_id).counters.tokens_used == 150 * len(calls)


def test_a_replanned_missions_durable_log_holds_both_plans_and_the_facts_of_the_second_attempt():
    rig = make_rig(respond=ScriptedCalls((cite_every_document, always_fails), then=cite_every_document))
    _, mission_id = created(rig)
    record, prepared, outcome = directly(rig, mission_id)
    durable = rig.storage.read(TENANT_A, mission_id)
    assert len(outcome.plans) == 2 and durable == outcome.log.records
    types = [r.event.type for r in durable]
    assert types.count(MissionEventType.PLAN_GENERATED) == 2 and MissionEventType.REPLAN_TRIGGERED in types
    second = execution_record(durable, plan_id=outcome.plans[1].plan_id)
    assert any(step.model_calls for step in second.steps)  # the tracker reaches the attempts a replan makes (D-231)


def test_a_second_service_over_the_same_storage_answers_every_read_identically():
    rig = make_rig()
    context, mission_id = created(rig)
    rig.run_to_the_end(context, mission_id)
    restarted = make_rig(storage=rig.storage)
    other = restarted.context("alice")
    for read in ("get_mission", "execution", "events", "result", "evidence"):
        assert getattr(restarted.service, read)(other, mission_id) == getattr(rig.service, read)(context, mission_id), read


def test_the_same_request_run_twice_records_the_same_shaped_log():
    rig = make_rig()
    context = rig.context("alice")
    first, second = (rig.service.create_mission(context, make_spec())[0].mission_id for _ in range(2))
    rig.run_to_the_end(context, first)
    rig.run_to_the_end(context, second)
    one, two = rig.storage.read(TENANT_A, first), rig.storage.read(TENANT_A, second)
    assert shape(one) == shape(two) and one[0].event.event_id != two[0].event.event_id  # the same story; the identities are the server's, freshly assigned


# --- knowledge is optional and shipped with no production choice ---------------------------------------------------------------------------------


def test_with_no_knowledge_provision_no_retrieval_is_recorded_and_with_one_it_is():
    from eidos.knowledge import LexicalKnowledgePort

    from eidos_knowledge_gate_fixture import GOAL, KB, SNAPSHOT, descriptor_for

    plain = make_rig()
    context, mission_id = created(plain)
    plain.run_to_the_end(context, mission_id)
    assert MissionEventType.RAG_SEARCH not in {r.event.type for r in plain.storage.read(TENANT_A, mission_id)}
    assert all(not step.retrievals for step in execution_record(plain.storage.read(TENANT_A, mission_id)).steps)

    provision = KnowledgeProvision(descriptor=descriptor_for(), port=LexicalKnowledgePort(SNAPSHOT, kb_id=KB))
    rag = make_rig(knowledge=provision)
    context, mission_id = created(rag, goal=GOAL, supplied_documents=())
    rag.run_to_the_end(context, mission_id)
    durable = rag.storage.read(TENANT_A, mission_id)
    assert any(step.retrievals for step in execution_record(durable).steps)
    view = rag.service.evidence(context, mission_id)
    assert view.evidence and rag.service.get_mission(context, mission_id).verified is True


# --- a store that fails part-way -----------------------------------------------------------------------------------------------------------------


class FailsAfter:
    """An ``EventStore`` that takes ``good`` commits and then refuses every one: the database went away part-way through a run."""

    def __init__(self, inner, good):
        self.inner, self.good, self.commits = inner, good, 0

    def commit(self, **kwargs):
        self.commits += 1
        if self.commits > self.good:
            raise StorageError("down")
        return self.inner.commit(**kwargs)

    def read(self, *args, **kwargs):
        return self.inner.read(*args, **kwargs)


def test_a_store_that_fails_part_way_leaves_a_valid_prefix_and_an_error_run_and_no_fabricated_failure():
    storage = InMemoryStorage()
    rig = make_rig(storage=storage, events=FailsAfter(storage, good=2))
    context, mission_id = created(rig)
    summary = rig.run_to_the_end(context, mission_id)
    assert summary.run_status is RunStatus.ERROR and summary.run_status_reason.startswith("persistence:") and "lost when the process exits" in summary.run_status_reason
    prefix = storage.read(TENANT_A, mission_id)
    assert 0 < len(prefix) < 10 and [r.event.sequence for r in prefix] == list(range(1, len(prefix) + 1))
    assert replay(prefix).rejection is None  # a prefix of a valid log is a valid log
    assert MissionEventType.MISSION_FAILED not in {r.event.type for r in prefix}  # nothing was invented to explain the gap
    assert summary.mission_status is not MissionStatus.FAILED and summary.last_sequence == len(prefix)
    restarted = make_rig(storage=storage)  # the prefix is what any later reader sees
    again = restarted.service.get_mission(restarted.context("alice"), mission_id)
    assert (again.run_status, again.last_sequence, again.mission_status) == (RunStatus.ERROR, len(prefix), summary.mission_status)
    assert restarted.service.events(restarted.context("alice"), mission_id).events == prefix


def test_a_process_that_died_mid_run_leaves_its_prefix_and_the_next_start_marks_the_run_interrupted():
    rig = make_rig()
    context, mission_id = created(rig)
    record, prepared, outcome = directly(rig, mission_id)
    complete = rig.storage.read(TENANT_A, mission_id)
    crashed = InMemoryStorage()
    crashed.add_tenant(TENANT_A)
    from eidos.service import MissionRecord

    fields = {name: getattr(record, name) for name in MissionRecord.model_fields}
    fields.update(run_status=RunStatus.RUNNING, last_sequence=0)
    crashed.create(MissionRecord.model_validate(fields), ())
    crashed.commit(tenant_id=TENANT_A, mission_id=mission_id, execution_id=record.execution_id, expected_last_sequence=0, artifacts=(), events=complete[:5])
    restarted = make_rig(storage=crashed)  # a new process over the storage the dead one left
    assert restarted.service.startup() == 1
    summary = restarted.service.get_mission(restarted.context("alice"), mission_id)
    assert summary.run_status is RunStatus.INTERRUPTED and summary.last_sequence == 5 and summary.mission_status is MissionStatus.CREATED
    assert crashed.read(TENANT_A, mission_id) == complete[:5]  # recovery wrote nothing


# --- isolation and single execution under concurrency ---------------------------------------------------------------------------------------------


def test_two_tenants_running_at_the_same_time_each_end_with_only_their_own_events_and_artifacts():
    barrier = threading.Barrier(2, timeout=30)

    def meet(request):
        try:
            barrier.wait()  # both runs are inside the model at once: they really do run together
        except threading.BrokenBarrierError:
            pass
        return cite_every_document(request)

    from eidos.service import RunnerConfig

    rig = make_rig(respond=meet, runner=RunnerConfig(worker_pool_size=2, max_queued_runs=2, max_active_runs_per_tenant=1, flush_backoff_seconds=0.0))
    alice, bob = rig.context("alice"), rig.context("bob")
    a = rig.service.create_mission(alice, make_spec(goal="alice's question"))[0].mission_id
    b = rig.service.create_mission(bob, make_spec(goal="bob's question"))[0].mission_id
    rig.service.start_mission(alice, a)
    rig.service.start_mission(bob, b)
    assert rig.runner.wait_idle(60)
    for context, mission_id, tenant in ((alice, a, TENANT_A), (bob, b, TENANT_B)):
        assert rig.service.get_mission(context, mission_id).mission_status is MissionStatus.COMPLETED
        records = rig.storage.read(tenant, mission_id)
        assert {r.event.tenant_id for r in records} == {tenant} and {r.event.mission_id for r in records} == {mission_id}
    record_a, record_b = rig.storage.get(TENANT_A, a), rig.storage.get(TENANT_B, b)
    assert rig.storage.artifacts_for(TENANT_B).get_step_artifact(record_a.execution_id, execution_record(rig.storage.read(TENANT_A, a)).steps[0].step_id) is None
    assert rig.storage.artifacts_for(TENANT_A).supplied(record_b.execution_id) == ()  # neither tenant can reach the other's execution


def test_one_mission_started_by_many_callers_at_once_runs_exactly_once():
    from eidos.service import NotStartable, TenantRunLimit

    rig = make_rig()
    context, mission_id = created(rig)
    outcomes, start = [], threading.Barrier(8, timeout=30)

    def call():
        start.wait()
        try:
            rig.service.start_mission(context, mission_id)
            outcomes.append("started")
        except (NotStartable, TenantRunLimit) as error:
            outcomes.append(error.code)

    threads = [threading.Thread(target=call) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    assert rig.runner.wait_idle(60)
    assert outcomes.count("started") == 1 and len(outcomes) == 8
    records = rig.storage.read(TENANT_A, mission_id)
    assert [r.event.sequence for r in records] == list(range(1, len(records) + 1)) and sum(r.event.type is MissionEventType.MISSION_CREATED for r in records) == 1
    model_calls_of_one_run = rig.model.calls
    second_context, second = created(rig)
    rig.run_to_the_end(second_context, second)
    assert rig.model.calls == 2 * model_calls_of_one_run  # the contended mission cost exactly one run's calls


def test_two_writers_of_one_mission_cannot_both_extend_its_log():
    rig = make_rig()
    _, mission_id = created(rig)
    record = rig.storage.get(TENANT_A, mission_id)
    directly(rig, mission_id)  # the first writer completes and commits its whole log
    first = rig.storage.read(TENANT_A, mission_id)
    prepared = rig.composition.prepare(record, rig.storage.artifacts_for(TENANT_A).supplied(record.execution_id))
    outcome = run_with_replanning(**prepared.run_arguments)  # a second writer starts from an empty log, expecting sequence 0, under event ids of its own
    assert isinstance(outcome, ReplanRun) and prepared.persistence.finish() is False
    assert prepared.persistence.failure.startswith("sequence_conflict")
    assert rig.storage.read(TENANT_A, mission_id) == first  # the first writer's log is exactly as it was: nothing of the second was written


