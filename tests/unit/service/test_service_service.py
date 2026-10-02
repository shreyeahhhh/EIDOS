"""The application service: identity, creation, idempotency, tenant isolation and every read as a replay (decisions.md D-230 to D-234; invariants 1, 2, 15 and 16; V1.4-B).

What is held: a client never chooses a tenant it does not belong to and never sets an identifier; creating a mission writes no event; a repeated Idempotency-Key is the same mission and a changed
request under it is a conflict; a resource of another tenant is indistinguishable from one that does not exist on every method; and every derived answer is the fold of the recorded events, so a
stored log that does not replay is a fault of the store and never a mission outcome.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from eidos.contracts import MissionId, MissionStatus, TenantId
from eidos.service import (
    DuplicateIdempotencyKey,
    IdempotencyConflict,
    IntegrityFailure,
    InvalidRequest,
    InvalidSpec,
    MissionService,
    NoEvents,
    NoTenantMembership,
    NotFinished,
    NotFound,
    NotStartable,
    RequestContext,
    Role,
    RunStatus,
    StorageError,
    StorageUnavailable,
    TenantRequired,
    UserId,
    personal_workspace_id,
)
from eidos.service.views import replayed_state
from eidos.state import CitationKind, audit_evidence, execution_record

from eidos_replanning_factories import ScriptedCalls, always_fails
from eidos_search_fixture import cite_every_document
from eidos_service_fixture import ALICE, BOB, CAROL, DAVE, TENANT_A, TENANT_B, make_rig, make_spec
from eidos_storage_helpers import events_for, make_record


def created(rig, who="alice", key=None, **spec):
    context = rig.context(who)
    return context, rig.service.create_mission(context, make_spec(**spec), key)[0].mission_id


def finished(rig, who="alice", **spec):
    context, mission_id = created(rig, who, **spec)
    rig.run_to_the_end(context, mission_id)
    return context, mission_id


# --- identity: the tenant a request acts for ---------------------------------------------------------------------------------------------


def test_a_user_of_one_tenant_acts_for_it_without_naming_it():
    rig = make_rig()
    context = rig.service.resolve_context(ALICE, None)
    assert (context.user_id, context.tenant_id, context.role) == (ALICE, TENANT_A, Role.OWNER)


def test_a_user_of_several_tenants_must_name_one_and_only_one_of_their_own():
    rig = make_rig()
    with pytest.raises(TenantRequired):
        rig.service.resolve_context(CAROL, None)
    assert rig.service.resolve_context(CAROL, str(TENANT_B)).tenant_id == TENANT_B
    assert rig.service.resolve_context(CAROL, str(TENANT_A)).tenant_id == TENANT_A


@pytest.mark.parametrize("requested", [str(TenantId(UUID(int=0xC0C0))), "not-a-uuid", "", str(UUID(int=0))])
def test_a_tenant_the_user_does_not_belong_to_is_not_found_whether_or_not_it_exists(requested):
    rig = make_rig()
    with pytest.raises(NotFound):
        rig.service.resolve_context(ALICE, requested)
    with pytest.raises(NotFound):
        rig.service.resolve_context(ALICE, str(TENANT_B))  # a real tenant, not hers: the answer is the same as for one that does not exist


def test_a_user_with_no_membership_has_no_tenant_and_a_named_tenant_does_not_change_that():
    rig = make_rig()
    with pytest.raises(NoTenantMembership):
        rig.service.resolve_context(DAVE, None)
    with pytest.raises(NoTenantMembership):
        rig.service.resolve_context(DAVE, str(TENANT_A))


def test_a_tenancy_store_that_is_down_is_an_unavailable_service_not_a_missing_membership():
    rig = make_rig()
    repositories = rig.storage.repositories()

    class Down:
        def memberships_of(self, user_id):
            raise StorageError("down")

    service = MissionService(repositories=replace(repositories, tenancy=Down()), runner=rig.runner, composition=rig.composition, config=rig.config)
    with pytest.raises(StorageUnavailable):
        service.resolve_context(ALICE, None)


# --- identity: a workspace of one's own for a user who has none (D-237) --------------------------------------------------------------------


def auto_provisioning_service(rig):
    return MissionService(
        repositories=rig.storage.repositories(), runner=rig.runner, composition=rig.composition, config=replace(rig.config, auto_provision_workspaces=True)
    )


def test_a_user_with_no_tenant_is_given_a_workspace_of_their_own_when_the_deployment_allows_it():
    rig = make_rig()
    service = auto_provisioning_service(rig)
    context = service.resolve_context(DAVE, None)
    assert (context.user_id, context.tenant_id, context.role) == (DAVE, personal_workspace_id(DAVE), Role.OWNER)
    assert context.tenant_id not in (TENANT_A, TENANT_B)
    assert service.resolve_context(DAVE, None) == context  # the second request reads it, it does not make another
    assert [m.tenant_id for m in rig.storage.repositories().tenancy.memberships_of(DAVE)] == [context.tenant_id]


def test_a_user_who_already_has_a_tenant_keeps_exactly_it_and_gets_no_extra_workspace():
    rig = make_rig()
    service = auto_provisioning_service(rig)
    assert service.resolve_context(ALICE, None).tenant_id == TENANT_A
    assert [m.tenant_id for m in rig.storage.repositories().tenancy.memberships_of(ALICE)] == [TENANT_A]
    assert [m.tenant_id for m in rig.storage.repositories().tenancy.memberships_of(CAROL)] == sorted([TENANT_A, TENANT_B], key=str)
    assert service.resolve_context(CAROL, str(TENANT_B)).tenant_id == TENANT_B  # and several tenants still means naming one


def test_each_new_user_gets_a_different_workspace_and_may_not_name_anothers():
    rig = make_rig()
    service = auto_provisioning_service(rig)
    stranger = UserId(UUID(int=0xABCDEF))
    mine, theirs = service.resolve_context(DAVE, None), service.resolve_context(stranger, None)
    assert mine.tenant_id != theirs.tenant_id
    with pytest.raises(NotFound):
        service.resolve_context(DAVE, str(theirs.tenant_id))


def test_workspaces_made_by_racing_first_requests_are_one_workspace():
    rig = make_rig()
    service = auto_provisioning_service(rig)
    with ThreadPoolExecutor(max_workers=8) as pool:
        contexts = list(pool.map(lambda _: service.resolve_context(DAVE, None), range(16)))
    assert {c.tenant_id for c in contexts} == {personal_workspace_id(DAVE)}
    assert len(rig.storage.repositories().tenancy.memberships_of(DAVE)) == 1


def test_a_store_that_is_down_while_giving_a_workspace_is_an_unavailable_service():
    rig = make_rig()

    class Down:
        def memberships_of(self, user_id):
            return ()

        def provision_personal_workspace(self, user_id, name):
            raise StorageError("down")

    service = MissionService(
        repositories=replace(rig.storage.repositories(), tenancy=Down()), runner=rig.runner, composition=rig.composition,
        config=replace(rig.config, auto_provision_workspaces=True),
    )
    with pytest.raises(StorageUnavailable):
        service.resolve_context(DAVE, None)


# --- create: no event, server-assigned identity, the documents kept ------------------------------------------------------------------------


def test_creating_a_mission_stores_it_writes_no_event_and_the_server_assigns_the_identity():
    rig = make_rig()
    context = rig.context("alice")
    created_mission, is_new = rig.service.create_mission(context, make_spec())
    assert is_new and created_mission.run_status is RunStatus.CREATED
    record = rig.storage.get(TENANT_A, created_mission.mission_id)
    assert (record.tenant_id, record.created_by, record.run_status, record.last_sequence) == (TENANT_A, ALICE, RunStatus.CREATED, 0)
    assert rig.storage.read(TENANT_A, created_mission.mission_id) == ()  # before a run the mission does not exist for the log (D-201)
    assert record.mission_id != record.execution_id and record.contract_id not in (record.mission_id, record.execution_id)
    assert record.spec.supplied_documents == ()  # the documents are supplied artifacts, not part of the stored spec


def test_the_supplied_documents_are_stored_as_the_missions_supplied_artifacts_and_only_for_its_tenant():
    rig = make_rig()
    _, mission_id = created(rig)
    record = rig.storage.get(TENANT_A, mission_id)
    supplied = rig.storage.artifacts_for(TENANT_A).supplied(record.execution_id)
    assert [str(a.ref) for a in supplied] == ["doc:1", "doc:2", "doc:3"] and supplied[0].content == "Source document 1."
    assert rig.storage.artifacts_for(TENANT_B).supplied(record.execution_id) == ()  # the same execution id under another tenant is nothing


def test_an_invalid_specification_is_refused_with_its_problems_and_nothing_is_stored():
    rig = make_rig()
    context = rig.context("alice")
    with pytest.raises(InvalidSpec) as raised:
        rig.service.create_mission(context, make_spec(goal="  ", required_capabilities=()))
    assert {item["field"] for item in raised.value.details} >= {"goal", "required_capabilities"}
    assert rig.storage.count_active(TENANT_A) == 0 and rig.storage._missions == {}


def test_a_ceiling_rejects_and_never_clamps():
    from eidos.service import ApiCeilings

    rig = make_rig(ceilings=ApiCeilings(max_goal_chars=10))
    with pytest.raises(InvalidSpec):
        rig.service.create_mission(rig.context("alice"), make_spec(goal="x" * 11))
    assert rig.storage._missions == {}


# --- idempotency ----------------------------------------------------------------------------------------------------------------------


def test_the_same_key_and_the_same_request_is_the_same_mission_and_creates_nothing_new():
    rig = make_rig()
    context = rig.context("alice")
    first, was_new = rig.service.create_mission(context, make_spec(), "key-1")
    again, is_new = rig.service.create_mission(context, make_spec(), "key-1")
    assert was_new and not is_new and again.mission_id == first.mission_id and len(rig.storage._missions) == 1


def test_a_repeat_reports_the_missions_current_run_status():
    rig = make_rig()
    context, mission_id = finished(rig, key=None)
    keyed, _ = rig.service.create_mission(context, make_spec(goal="keyed"), "key-2")
    rig.service.start_mission(context, keyed.mission_id)
    assert rig.runner.wait_idle(60)
    repeat, is_new = rig.service.create_mission(context, make_spec(goal="keyed"), "key-2")
    assert not is_new and repeat.run_status is RunStatus.FINISHED  # what the mission is now, not what it was when created


def test_the_same_key_with_a_different_request_is_a_conflict_and_the_first_mission_is_untouched():
    rig = make_rig()
    context = rig.context("alice")
    first, _ = rig.service.create_mission(context, make_spec(), "key-1")
    with pytest.raises(IdempotencyConflict):
        rig.service.create_mission(context, make_spec(goal="something else"), "key-1")
    with pytest.raises(IdempotencyConflict):
        rig.service.create_mission(context, make_spec(supplied_documents=()), "key-1")  # the documents are part of the request
    assert len(rig.storage._missions) == 1 and rig.storage.get(TENANT_A, first.mission_id).spec.goal == make_spec().goal


def test_an_idempotency_key_belongs_to_its_tenant():
    rig = make_rig()
    one, _ = rig.service.create_mission(rig.context("alice"), make_spec(), "shared-key")
    other, is_new = rig.service.create_mission(rig.context("bob"), make_spec(), "shared-key")
    assert is_new and other.mission_id != one.mission_id  # another tenant's key is not this tenant's key, and this tenant learns nothing of it


@pytest.mark.parametrize("key", ["", "k" * 129])
def test_an_idempotency_key_is_one_to_128_characters(key):
    rig = make_rig()
    with pytest.raises(InvalidRequest):
        rig.service.create_mission(rig.context("alice"), make_spec(), key)
    assert rig.storage._missions == {}


def test_a_create_that_loses_the_race_for_a_key_returns_the_winner_and_a_different_request_conflicts():
    rig = make_rig()
    context = rig.context("alice")
    winner, _ = rig.service.create_mission(context, make_spec(), "race")
    missions = rig.storage

    class Racing:
        """Does not see the key on the first look, then loses the insert to it: what two concurrent creates look like."""

        def __init__(self):
            self.looked = 0

        def __getattr__(self, name):
            return getattr(missions, name)

        def find_by_idempotency_key(self, tenant_id, key):
            self.looked += 1
            return None if self.looked == 1 else missions.find_by_idempotency_key(tenant_id, key)

        def create(self, record, documents):
            raise DuplicateIdempotencyKey(record.idempotency_key)

    service = MissionService(repositories=replace(rig.storage.repositories(), missions=Racing()), runner=rig.runner, composition=rig.composition, config=rig.config)
    same, is_new = service.create_mission(context, make_spec(), "race")
    assert not is_new and same.mission_id == winner.mission_id
    racing_service = MissionService(repositories=replace(rig.storage.repositories(), missions=Racing()), runner=rig.runner, composition=rig.composition, config=rig.config)
    with pytest.raises(IdempotencyConflict):
        racing_service.create_mission(context, make_spec(goal="different"), "race")


def test_a_storage_fault_while_creating_is_an_unavailable_service_and_stores_nothing():
    rig = make_rig()

    class Down:
        def find_by_idempotency_key(self, tenant_id, key):
            return None

        def create(self, record, documents):
            raise StorageError("down")

    service = MissionService(repositories=replace(rig.storage.repositories(), missions=Down()), runner=rig.runner, composition=rig.composition, config=rig.config)
    with pytest.raises(StorageUnavailable):
        service.create_mission(rig.context("alice"), make_spec())
    assert rig.storage._missions == {}


# --- reads before any event -----------------------------------------------------------------------------------------------------------


def test_a_mission_that_has_not_run_has_a_status_and_no_log_to_read():
    rig = make_rig()
    context, mission_id = created(rig)
    summary = rig.service.get_mission(context, mission_id)
    assert (summary.run_status, summary.mission_status, summary.counters, summary.last_sequence, summary.verified) == (RunStatus.CREATED, None, None, 0, None)
    assert (summary.tenant_id, summary.created_by, summary.goal) == (TENANT_A, ALICE, make_spec().goal)
    with pytest.raises(NoEvents):
        rig.service.execution(context, mission_id)
    with pytest.raises(NoEvents):
        rig.service.evidence(context, mission_id)
    with pytest.raises(NotFinished):
        rig.service.result(context, mission_id)
    page = rig.service.events(context, mission_id)
    assert (page.events, page.last_sequence, page.next_after) == ((), 0, 0)


# --- every derived answer is the fold of the recorded log ----------------------------------------------------------------------------------


def test_the_summary_the_execution_and_the_state_are_all_derived_from_the_same_recorded_events():
    rig = make_rig()
    context, mission_id = finished(rig)
    records = rig.storage.read(TENANT_A, mission_id)
    summary, execution = rig.service.get_mission(context, mission_id), rig.service.execution(context, mission_id)
    assert execution == execution_record(records) and summary.last_sequence == len(records)
    state = replayed_state(records)
    assert (summary.mission_status, summary.verified, summary.plan_version) == (state.status, execution.verified, execution.plan_version)
    assert summary.mission_status is MissionStatus.COMPLETED and summary.verified is True and summary.failure_cause is None
    assert (summary.counters.agent_calls_used, summary.counters.tokens_used) == (execution.agent_calls_used, execution.tokens_used) and summary.counters.tokens_used > 0


def test_a_mission_status_comes_from_the_log_and_not_from_the_run_status_row():
    rig = make_rig()
    context, mission_id = finished(rig)
    assert rig.storage.transition(TENANT_A, mission_id, expected=(RunStatus.FINISHED,), new=RunStatus.ERROR, reason="test: a service fault after the run", at=datetime.now(timezone.utc))
    summary = rig.service.get_mission(context, mission_id)
    assert summary.run_status is RunStatus.ERROR and summary.mission_status is MissionStatus.COMPLETED  # the row says error; the log is still the whole story of the mission


def test_the_events_are_the_recorded_records_in_sequence_and_page_without_gap_or_overlap():
    rig = make_rig()
    context, mission_id = finished(rig)
    records = rig.storage.read(TENANT_A, mission_id)
    assert len(records) > 6
    everything = rig.service.events(context, mission_id)
    assert everything.events == records and everything.last_sequence == everything.next_after == len(records)
    seen, after = [], 0
    while True:
        page = rig.service.events(context, mission_id, after=after, limit=4)
        seen.extend(page.events)
        assert page.last_sequence == len(records)
        if not page.events:
            break
        assert len(page.events) <= 4 and page.events[0].event.sequence == after + 1
        after = page.next_after
    assert tuple(seen) == records
    assert rig.service.events(context, mission_id, after=len(records)).events == ()  # nothing after the end, and the cursor stays where it was
    assert rig.service.events(context, mission_id, after=len(records)).next_after == len(records)


@pytest.mark.parametrize("after, limit", [(-1, None), (0, 0), (0, -1), (0, 100_000)])
def test_a_page_request_outside_its_bounds_is_refused_not_clamped(after, limit):
    rig = make_rig()
    context, mission_id = created(rig)
    with pytest.raises(InvalidRequest):
        rig.service.events(context, mission_id, after=after, limit=limit)


def test_the_result_is_the_verdict_and_the_sink_artifacts_of_a_verified_mission():
    rig = make_rig()
    context, mission_id = finished(rig)
    result = rig.service.result(context, mission_id)
    assert (result.mission_status, result.verified, result.failure) == (MissionStatus.COMPLETED, True, None)
    assert result.verdict is not None and result.verdict.verdict.value == "pass"
    assert sorted(a.content.split()[0] for a in result.artifacts) == ["Analysis", "Findings"]  # the plan is parallel: both work steps are sinks, and both are what the verifier read
    assert all(a.source_refs and a.content_type == "text/markdown" for a in result.artifacts)


def test_a_failed_mission_is_a_result_that_says_why_and_never_an_api_error():
    rig = make_rig(respond=always_fails)
    context, mission_id = finished(rig)
    result = rig.service.result(context, mission_id)
    assert result.mission_status is MissionStatus.FAILED and result.verified is None and result.failure is not None and result.failure.cause is not None
    assert result.artifacts == ()  # nothing succeeded, so nothing is claimed
    assert rig.service.get_mission(context, mission_id).run_status is RunStatus.FINISHED


def test_without_a_knowledge_base_a_citation_of_a_supplied_document_is_not_evidence_and_the_view_says_so():
    rig = make_rig()
    context, mission_id = finished(rig)
    view = rig.service.evidence(context, mission_id)
    assert view.audit == audit_evidence(execution_record(rig.storage.read(TENANT_A, mission_id)))
    assert view.audit.traces and {trace.kind for trace in view.audit.traces} == {CitationKind.NOT_EVIDENCE}  # evidence is what a knowledge base retrieved (D-228), and none was
    assert view.evidence == ()
    assert rig.service.get_mission(context, mission_id).verified is True  # the verdict counted the cited sources; the audit is a separate, stricter reading


def knowledge_rig(**kwargs):
    from eidos.knowledge import LexicalKnowledgePort
    from eidos.service import KnowledgeProvision

    from eidos_knowledge_gate_fixture import KB, SNAPSHOT, descriptor_for

    return make_rig(knowledge=KnowledgeProvision(descriptor=descriptor_for(), port=LexicalKnowledgePort(SNAPSHOT, kb_id=KB)), **kwargs)


def test_with_a_knowledge_base_the_evidence_is_the_audit_of_the_recorded_retrievals_and_the_text_they_resolve_to():
    from eidos_knowledge_gate_fixture import GOAL

    rig = knowledge_rig()
    context, mission_id = finished(rig, goal=GOAL, supplied_documents=())
    view = rig.service.evidence(context, mission_id)
    assert view.audit == audit_evidence(execution_record(rig.storage.read(TENANT_A, mission_id)))
    assert view.audit.traces and {trace.kind for trace in view.audit.traces} == {CitationKind.RESOLVED}
    assert view.evidence and all(item.content.strip() for item in view.evidence) and {item.ref for item in view.evidence} == {trace.ref for trace in view.audit.traces}


def test_a_replanned_missions_evidence_is_audited_across_every_plan_not_only_the_last():
    from eidos_knowledge_gate_fixture import GOAL

    rig = knowledge_rig(respond=ScriptedCalls((cite_every_document, always_fails), then=cite_every_document))
    context, mission_id = finished(rig, goal=GOAL, supplied_documents=())
    summary = rig.service.get_mission(context, mission_id)
    assert summary.mission_status is MissionStatus.COMPLETED and summary.plan_version == 2 and summary.counters.replans_used == 1
    records = rig.storage.read(TENANT_A, mission_id)
    assert CitationKind.UNRESOLVED in {trace.kind for trace in audit_evidence(execution_record(records)).traces}  # the last plan alone cannot resolve the replan attempt's citations
    view = rig.service.evidence(context, mission_id)
    kinds = {trace.kind for trace in view.audit.traces}
    assert CitationKind.RESOLVED in kinds and CitationKind.UNRESOLVED not in kinds and CitationKind.AMBIGUOUS not in kinds and view.evidence  # the whole execution can


# --- tenant isolation: on every method another tenant's mission is not there --------------------------------------------------------------------


def test_every_operation_on_another_tenants_mission_is_not_found_exactly_as_if_it_did_not_exist():
    rig = make_rig()
    alice, mission_id = finished(rig)
    bob = rig.context("bob")
    missing = MissionId(uuid4())
    for call in (
        lambda ctx, mid: rig.service.get_mission(ctx, mid),
        lambda ctx, mid: rig.service.execution(ctx, mid),
        lambda ctx, mid: rig.service.events(ctx, mid),
        lambda ctx, mid: rig.service.result(ctx, mid),
        lambda ctx, mid: rig.service.evidence(ctx, mid),
        lambda ctx, mid: rig.service.start_mission(ctx, mid),
    ):
        with pytest.raises(NotFound) as theirs:
            call(bob, mission_id)
        with pytest.raises(NotFound) as nothing:
            call(bob, missing)
        assert str(theirs.value) == str(nothing.value) and theirs.value.code == nothing.value.code == "not_found"
    call_ok = rig.service.get_mission(alice, mission_id)
    assert call_ok.run_status is RunStatus.FINISHED  # and the owner's mission is untouched by all of it


def test_a_user_of_both_tenants_sees_each_tenants_missions_only_when_acting_for_that_tenant():
    rig = make_rig()
    _, alices = finished(rig)
    carol_a = rig.service.resolve_context(CAROL, str(TENANT_A))
    carol_b = rig.service.resolve_context(CAROL, str(TENANT_B))
    assert rig.service.get_mission(carol_a, alices).tenant_id == TENANT_A
    with pytest.raises(NotFound):
        rig.service.get_mission(carol_b, alices)  # the same person, acting for the other tenant, cannot see it


def test_an_unstarted_mission_of_another_tenant_cannot_be_started_and_stays_startable_by_its_own():
    rig = make_rig()
    _, mission_id = created(rig)
    with pytest.raises(NotFound):
        rig.service.start_mission(rig.context("bob"), mission_id)
    assert rig.service.get_mission(rig.context("alice"), mission_id).run_status is RunStatus.CREATED
    rig.run_to_the_end(rig.context("alice"), mission_id)
    with pytest.raises(NotStartable):
        rig.service.start_mission(rig.context("alice"), mission_id)


# --- a stored log that does not replay is the store's fault, never a mission outcome -----------------------------------------------------------


def test_a_stored_log_that_does_not_replay_is_an_integrity_failure_on_every_derived_read():
    rig = make_rig()
    record = make_record()
    rig.storage.create(record, ())
    rig.storage.commit(tenant_id=record.tenant_id, mission_id=record.mission_id, execution_id=record.execution_id, expected_last_sequence=0, artifacts=(), events=events_for(record))
    context = rig.context("alice")
    assert rig.service.get_mission(context, record.mission_id).mission_status is MissionStatus.CREATED  # a valid log reads
    del rig.storage._events[record.mission_id][1]  # a gap: the second event is gone
    for call in (rig.service.get_mission, rig.service.execution, rig.service.result, rig.service.evidence):
        with pytest.raises(IntegrityFailure):
            call(context, record.mission_id)
    assert isinstance(IntegrityFailure("x").code, str) and IntegrityFailure("x").code == "integrity_error"


def test_a_storage_fault_on_a_read_is_an_unavailable_service():
    rig = make_rig()
    context, mission_id = created(rig)

    class Down:
        def read(self, *args, **kwargs):
            raise StorageError("down")

    service = MissionService(repositories=replace(rig.storage.repositories(), events=Down()), runner=rig.runner, composition=rig.composition, config=rig.config)
    for call in (service.get_mission, service.execution, service.result, service.evidence, service.events):
        with pytest.raises(StorageUnavailable):
            call(context, mission_id)


def test_the_service_holds_no_mission_state_and_writes_no_event_itself():
    import inspect

    import eidos.service.service as service_module

    source = inspect.getsource(service_module)
    assert "EventLog" not in source and "MissionState(" not in source and ".accept(" not in source and "model_construct" not in source
    assert "commit(" not in source  # only a run's outbox writes events, and it is not this class


def test_a_user_id_is_the_tokens_subject_and_nothing_more():
    rig = make_rig()
    stranger = UserId(UUID(int=0x99))
    with pytest.raises(NoTenantMembership):
        rig.service.resolve_context(stranger, None)
    assert {ALICE, BOB, CAROL, DAVE} == {UserId(UUID(int=n)) for n in (0x11, 0x22, 0x33, 0x44)}
    assert RequestContext(user_id=ALICE, tenant_id=TENANT_A, role=Role.OWNER) == rig.context("alice")
