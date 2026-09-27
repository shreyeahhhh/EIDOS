"""The bounded in-process runner and the API-level ``run_status`` (decisions.md D-234, D-230; invariants 1, 2 and 7; V1.4-B).

What is held: a run moves created, queued, running, then finished, rejected or error, only by compare-and-set and never twice; the runner is bounded (a full queue and a tenant's own limit are refused, not
waited on); startup recovery makes an orphaned run interrupted and writes no event; a failure of the service is an ``error`` run and never a mission outcome; and ``run_status`` is not a ``MissionStatus``, never an
event and never in ``MissionState``.
"""

import threading
from dataclasses import replace

import pytest

import eidos.service.runner as runner_module
from eidos.contracts import MissionEventType, MissionState, MissionStatus
from eidos.service import (
    Busy,
    NotFinished,
    NotFound,
    NotStartable,
    RunnerConfig,
    RunStatus,
    ServiceConfig,
    StorageError,
    TenantRunLimit,
    provisional_system_limits,
)
from eidos.state import execution_record
from eidos.validation import SystemLimits

from eidos_agents_factories import make_settings
from eidos_replanning_factories import always_fails
from eidos_search_fixture import cite_every_document
from eidos_service_fixture import make_rig, make_spec


def created(rig, who="alice", **spec):
    context = rig.context(who)
    return context, rig.service.create_mission(context, make_spec(**spec))[0].mission_id


class Blocked:
    """A scripted model that holds every call until released, so a test can keep runs running."""

    def __init__(self):
        self.gate = threading.Event()
        self.entered = threading.Semaphore(0)

    def __call__(self, request):
        self.entered.release()
        assert self.gate.wait(60), "the test never released the model"
        return cite_every_document(request)


def test_a_run_goes_from_created_to_finished_and_the_mission_outcome_is_read_from_the_log():
    rig = make_rig()
    context, mission_id = created(rig)
    assert rig.service.get_mission(context, mission_id).run_status is RunStatus.CREATED
    summary = rig.run_to_the_end(context, mission_id)
    assert (summary.run_status, summary.run_status_reason) == (RunStatus.FINISHED, None)
    assert (summary.mission_status, summary.verified, summary.failure_cause) == (MissionStatus.COMPLETED, True, None)
    assert summary.last_sequence == len(rig.storage.read(context.tenant_id, mission_id)) > 0


def test_a_mission_is_started_once():
    rig = make_rig()
    context, mission_id = created(rig)
    rig.run_to_the_end(context, mission_id)
    with pytest.raises(NotStartable):
        rig.service.start_mission(context, mission_id)  # finished
    context2, second = created(rig)
    rig.service.start_mission(context2, second)
    with pytest.raises(NotStartable):
        rig.service.start_mission(context2, second)  # queued or running: never a second execution
    assert rig.runner.wait_idle(60)


def test_a_missions_run_is_only_startable_by_its_own_tenant():
    rig = make_rig()
    _, mission_id = created(rig)
    with pytest.raises(NotFound):
        rig.service.start_mission(rig.context("bob"), mission_id)
    assert rig.service.get_mission(rig.context("alice"), mission_id).run_status is RunStatus.CREATED


def test_a_mission_that_fails_is_a_finished_run_whose_mission_failed_never_an_error_run():
    rig = make_rig(respond=always_fails)
    context, mission_id = created(rig)
    summary = rig.run_to_the_end(context, mission_id)
    assert summary.run_status is RunStatus.FINISHED  # the run ended and its log is the whole story
    assert summary.mission_status is MissionStatus.FAILED and summary.failure_cause is not None and summary.verified is None
    assert rig.service.result(context, mission_id).failure.cause == summary.failure_cause


def test_a_mission_with_no_selectable_strategy_is_a_rejected_run_that_recorded_nothing():
    tiny = SystemLimits(
        max_nodes=1, max_depth=1, max_parallel_branches=1, max_retries=3, max_replans=3, max_agent_calls=64, max_tool_calls=16, max_execution_time=600_000, max_tokens=200_000
    )
    config = ServiceConfig(limits=tiny, model_settings=make_settings(), allowed_actions=frozenset(), runner=RunnerConfig(flush_backoff_seconds=0.0))
    rig = make_rig(config=config)
    context, mission_id = created(rig)
    summary = rig.run_to_the_end(context, mission_id)
    assert summary.run_status is RunStatus.REJECTED and summary.run_status_reason.startswith("no_selectable_strategy")
    assert summary.mission_status is None and summary.last_sequence == 0 and rig.storage.read(context.tenant_id, mission_id) == ()  # the mission never existed for the log (D-201)
    with pytest.raises(NotFinished):
        rig.service.result(context, mission_id)


def test_an_unexpected_fault_in_the_run_is_an_error_run_and_never_a_mission_event(monkeypatch):
    rig = make_rig()

    def explode(**kwargs):
        raise RuntimeError("the service broke")

    monkeypatch.setattr(runner_module, "run_with_replanning", explode)
    context, mission_id = created(rig)
    summary = rig.run_to_the_end(context, mission_id)
    assert summary.run_status is RunStatus.ERROR and "RuntimeError" in summary.run_status_reason
    assert summary.mission_status is None and rig.storage.read(context.tenant_id, mission_id) == ()  # nothing was fabricated: no MISSION_FAILED


def test_an_unexpected_fault_is_told_to_the_caller_by_its_type_alone_and_in_full_to_the_server_log(monkeypatch, caplog):
    rig = make_rig()

    def explode(**kwargs):
        raise RuntimeError("could not reach postgresql://user:hunter2@10.0.0.5/db")

    monkeypatch.setattr(runner_module, "run_with_replanning", explode)
    context, mission_id = created(rig)
    with caplog.at_level("ERROR", logger="eidos.service.runner"):
        summary = rig.run_to_the_end(context, mission_id)
    assert summary.run_status_reason == "internal: RuntimeError"  # a message can name a host, a path or a value: the tenant is not told it
    assert "hunter2" in caplog.text and str(mission_id) in caplog.text  # the operator is


def test_a_persistence_fault_is_told_by_its_type_alone_but_a_conflict_by_its_own_wording():
    class Down:
        def __init__(self, inner):
            self.inner = inner

        def commit(self, **kwargs):
            raise StorageError("connection to 10.0.0.5:5432 refused")

        def read(self, *args, **kwargs):
            return self.inner.read(*args, **kwargs)

    from eidos.service import InMemoryStorage

    storage = InMemoryStorage()
    rig = make_rig(storage=storage, events=Down(storage))
    context, mission_id = created(rig)
    summary = rig.run_to_the_end(context, mission_id)
    assert "10.0.0.5" not in summary.run_status_reason and "(StorageError)" in summary.run_status_reason


def test_a_log_that_is_not_the_whole_story_is_an_error_run_with_the_log_kept(monkeypatch):
    real = runner_module.run_with_replanning
    monkeypatch.setattr(runner_module, "run_with_replanning", lambda **kwargs: replace(real(**kwargs), refused=("an event was refused",)))
    rig = make_rig()
    context, mission_id = created(rig)
    summary = rig.run_to_the_end(context, mission_id)
    assert summary.run_status is RunStatus.ERROR and "not the whole story" in summary.run_status_reason and "1 event(s) refused" in summary.run_status_reason
    assert summary.mission_status is MissionStatus.COMPLETED  # the recorded log itself is intact and readable


def test_a_store_that_cannot_take_the_events_ends_the_run_in_error_and_says_what_is_lost():
    class Down:
        def __init__(self, inner):
            self.inner = inner

        def commit(self, **kwargs):
            raise StorageError("down")

        def read(self, *args, **kwargs):
            return self.inner.read(*args, **kwargs)

    from eidos.service import InMemoryStorage

    storage = InMemoryStorage()
    rig = make_rig(storage=storage, events=Down(storage))
    context, mission_id = created(rig)
    summary = rig.run_to_the_end(context, mission_id)
    assert summary.run_status is RunStatus.ERROR and summary.run_status_reason.startswith("persistence:") and "lost when the process exits" in summary.run_status_reason
    assert summary.last_sequence == 0 and storage.read(context.tenant_id, mission_id) == ()


def test_the_runner_is_bounded_a_full_queue_and_a_tenants_own_limit_are_refused_not_waited_on():
    blocked = Blocked()
    runner = RunnerConfig(worker_pool_size=1, max_queued_runs=1, max_active_runs_per_tenant=2, flush_backoff_seconds=0.0)
    rig = make_rig(respond=blocked, runner=runner)
    context = rig.context("alice")
    first, second, third = (rig.service.create_mission(context, make_spec())[0].mission_id for _ in range(3))
    rig.service.start_mission(context, first)
    assert blocked.entered.acquire(timeout=30)  # the first run holds the only worker
    rig.service.start_mission(context, second)  # queued behind it
    with pytest.raises(TenantRunLimit):
        rig.service.start_mission(context, third)  # this tenant already has two runs active
    assert rig.service.get_mission(context, third).run_status is RunStatus.CREATED  # a refused start leaves the mission startable
    other = rig.context("bob")
    bobs = rig.service.create_mission(other, make_spec())[0].mission_id
    with pytest.raises(Busy):
        rig.service.start_mission(other, bobs)  # the runner itself is full: one running and one queued
    assert rig.service.get_mission(other, bobs).run_status is RunStatus.CREATED
    blocked.gate.set()
    assert rig.runner.wait_idle(60)
    assert rig.service.get_mission(context, first).run_status is rig.service.get_mission(context, second).run_status is RunStatus.FINISHED
    rig.service.start_mission(context, third)  # capacity is back
    assert rig.runner.wait_idle(60)


def test_a_tenants_active_runs_do_not_stop_another_tenants():
    blocked = Blocked()
    rig = make_rig(respond=blocked, runner=RunnerConfig(worker_pool_size=2, max_queued_runs=4, max_active_runs_per_tenant=1, flush_backoff_seconds=0.0))
    alice, bob = rig.context("alice"), rig.context("bob")
    first = rig.service.create_mission(alice, make_spec())[0].mission_id
    again = rig.service.create_mission(alice, make_spec())[0].mission_id
    theirs = rig.service.create_mission(bob, make_spec())[0].mission_id
    rig.service.start_mission(alice, first)
    with pytest.raises(TenantRunLimit):
        rig.service.start_mission(alice, again)
    rig.service.start_mission(bob, theirs)
    blocked.gate.set()
    assert rig.runner.wait_idle(60)


def test_startup_recovery_makes_an_orphaned_run_interrupted_and_writes_no_event():
    rig = make_rig()
    alice = rig.context("alice")
    queued, running, waiting = (rig.service.create_mission(alice, make_spec())[0].mission_id for _ in range(3))
    from eidos_storage_helpers import NOW

    for mission_id, status in ((queued, RunStatus.QUEUED), (running, RunStatus.RUNNING)):
        assert rig.storage.transition(alice.tenant_id, mission_id, expected=(RunStatus.CREATED,), new=status, reason=None, at=NOW)
    assert rig.service.startup() == 2
    for mission_id in (queued, running):
        summary = rig.service.get_mission(alice, mission_id)
        assert summary.run_status is RunStatus.INTERRUPTED and "restarted" in summary.run_status_reason
        assert summary.mission_status is None and summary.last_sequence == 0 and rig.storage.read(alice.tenant_id, mission_id) == ()
        with pytest.raises(NotStartable):
            rig.service.start_mission(alice, mission_id)  # an interrupted run is not resumed or retried
    assert rig.service.get_mission(alice, waiting).run_status is RunStatus.CREATED
    assert rig.service.startup() == 0


def test_a_run_interrupted_mid_way_keeps_the_valid_prefix_it_had_written():
    rig = make_rig()
    context, mission_id = created(rig)
    rig.run_to_the_end(context, mission_id)
    records = rig.storage.read(context.tenant_id, mission_id)
    # simulate a crash after the third event: the row still says running and only a prefix of the log is durable
    from eidos.service import InMemoryStorage
    from eidos_storage_helpers import NOW

    crashed = InMemoryStorage()
    crashed.add_tenant(context.tenant_id)
    record = rig.storage.get(context.tenant_id, mission_id)
    crashed.create(replace_status(record, RunStatus.RUNNING), ())
    crashed.commit(tenant_id=context.tenant_id, mission_id=mission_id, execution_id=record.execution_id, expected_last_sequence=0, artifacts=(), events=records[:3])
    assert crashed.interrupt_active(reason="restart", at=NOW) == 1
    prefix = crashed.read(context.tenant_id, mission_id)
    assert prefix == records[:3] and execution_record(prefix).mission_status is MissionStatus.CREATED  # a replayable prefix, still not terminal


def replace_status(record, status):
    from eidos.service import MissionRecord

    fields = {name: getattr(record, name) for name in MissionRecord.model_fields}
    fields.update(run_status=status, last_sequence=0)
    return MissionRecord.model_validate(fields)


def test_a_run_manager_that_has_shut_down_takes_no_more_runs():
    rig = make_rig()
    context, mission_id = created(rig)
    rig.runner.shutdown(wait=True)
    with pytest.raises(Busy):
        rig.service.start_mission(context, mission_id)
    assert rig.service.get_mission(context, mission_id).run_status is RunStatus.CREATED


def test_run_status_is_api_level_it_is_not_a_mission_status_never_an_event_and_never_in_mission_state():
    assert RunStatus is not MissionStatus and "run_status" not in MissionState.model_fields
    assert {status.value for status in RunStatus} == {"created", "queued", "running", "finished", "rejected", "interrupted", "error"}
    rig = make_rig()
    context, mission_id = created(rig)
    rig.run_to_the_end(context, mission_id)
    types = {record.event.type for record in rig.storage.read(context.tenant_id, mission_id)}
    assert types <= set(MissionEventType) and not any(word in event.value.lower() for event in types for word in ("queued", "interrupted", "run_"))
    text = "".join(record.model_dump_json() for record in rig.storage.read(context.tenant_id, mission_id))
    assert '"interrupted"' not in text and '"queued"' not in text


def test_the_provisional_limits_and_ceilings_are_labelled_as_such_and_the_admission_guard_admits_everything_and_says_so():
    import eidos.service.composition as composition_module
    import eidos.service.config as config_module

    assert "PROVISIONAL" in config_module.__doc__ and "PROVISIONAL" in config_module.ApiCeilings.__doc__ and "PROVISIONAL" in config_module.provisional_system_limits.__doc__
    assert "enforces no budget" in composition_module.AlwaysAdmit.__doc__
    assert provisional_system_limits().max_nodes > 0


# --- V1.4-C acceptance audit: a store fault around the edges of a run ------------------------------------------------------------------------------


class Flaky:
    """Wraps a storage's ``transition`` so it raises ``StorageError`` for the first ``failures`` calls that move a run to one of ``targets``."""

    def __init__(self, storage, targets, failures):
        self.storage, self.targets, self.failures, self.calls = storage, set(targets), failures, 0
        self.original = storage.transition

    def __call__(self, tenant_id, mission_id, *, expected, new, reason, at):
        if new in self.targets:
            self.calls += 1
            if self.calls <= self.failures:
                raise StorageError("down")
        return self.original(tenant_id, mission_id, expected=expected, new=new, reason=reason, at=at)


def test_a_short_outage_at_the_end_of_a_run_does_not_leave_the_row_running(monkeypatch):
    sleeps = []
    rig = make_rig(runner=RunnerConfig(flush_attempts=3, flush_backoff_seconds=0.5), sleep=sleeps.append)
    flaky = Flaky(rig.storage, {RunStatus.FINISHED}, failures=2)
    monkeypatch.setattr(rig.storage, "transition", flaky)
    context, mission_id = created(rig)
    summary = rig.run_to_the_end(context, mission_id)
    assert summary.run_status is RunStatus.FINISHED and flaky.calls == 3  # two failures, then the third try recorded it
    assert sleeps == [0.5, 1.0]  # a growing pause between the tries, and no other pause


def test_an_outage_that_outlasts_the_bound_leaves_the_row_for_startup_to_interrupt_and_never_raises(monkeypatch, caplog):
    sleeps = []
    rig = make_rig(runner=RunnerConfig(flush_attempts=3, flush_backoff_seconds=0.5), sleep=sleeps.append)
    flaky = Flaky(rig.storage, {RunStatus.FINISHED}, failures=10**6)
    monkeypatch.setattr(rig.storage, "transition", flaky)
    context, mission_id = created(rig)
    with caplog.at_level("ERROR", logger="eidos.service.runner"):
        summary = rig.run_to_the_end(context, mission_id)
    assert flaky.calls == 3 and sleeps == [0.5, 1.0]  # bounded: exactly the attempts configured, then it stops
    assert summary.run_status is RunStatus.RUNNING and summary.mission_status is MissionStatus.COMPLETED  # the log says what the mission came to; the row could not be told
    assert "could not be recorded" in caplog.text and str(mission_id) in caplog.text
    monkeypatch.undo()
    assert rig.service.startup() == 1  # and the next startup marks it interrupted, as designed
    assert rig.service.get_mission(context, mission_id).run_status is RunStatus.INTERRUPTED


def test_a_short_outage_when_a_run_begins_does_not_strand_it_queued(monkeypatch):
    rig = make_rig(runner=RunnerConfig(flush_attempts=3, flush_backoff_seconds=0.0))
    flaky = Flaky(rig.storage, {RunStatus.RUNNING}, failures=2)
    monkeypatch.setattr(rig.storage, "transition", flaky)
    context, mission_id = created(rig)
    assert rig.run_to_the_end(context, mission_id).run_status is RunStatus.FINISHED and flaky.calls == 3


def test_an_outage_at_start_is_a_503_for_the_caller_to_retry_and_the_mission_stays_startable(monkeypatch):
    from eidos.service import StorageUnavailable

    rig = make_rig()
    context, mission_id = created(rig)
    original = rig.storage.count_active

    def down(tenant_id):
        raise StorageError("down")

    monkeypatch.setattr(rig.storage, "count_active", down)
    with pytest.raises(StorageUnavailable):
        rig.service.start_mission(context, mission_id)
    monkeypatch.setattr(rig.storage, "count_active", original)
    assert rig.service.get_mission(context, mission_id).run_status is RunStatus.CREATED
    assert rig.run_to_the_end(context, mission_id).run_status is RunStatus.FINISHED  # nothing was left half-done: the same mission starts
