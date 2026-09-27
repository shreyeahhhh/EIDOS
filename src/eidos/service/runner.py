"""The bounded in-process runner (decisions.md D-234; invariant 7; ``docs/13`` section 6).

A ``ThreadPoolExecutor`` of ``worker_pool_size`` workers runs one ``run_with_replanning`` per mission. **One execution per mission** is guaranteed by the compare-and-set on ``run_status`` and by a
per-process set of missions that are queued or running. There is no cancel, no retry and no separate worker service, and one API process per database is assumed (multi-instance operation needs
leases and heartbeats, which are deferred).

**``run_status`` is API-level. It never enters ``MissionState``, is never an event, and no transition here writes a mission event.** The transitions, all compare-and-set and all by this class:

    created -> queued -> running -> finished | rejected | error        queued | running -> interrupted (startup only)        queued -> error (a failed submission)

``finished`` says the run ended and its log is the whole story; what the mission came to is read from the folded log. ``rejected`` is a ``ReplanRejection`` (nothing was recorded, D-201). ``error``
is a service fault: an unexpected exception, persistence that failed after its bounded retries, or a log that is not the whole story (``refused`` or ``discrepancies`` not empty, D-160).
``interrupted`` is what startup recovery makes of a run the previous process left ``queued`` or ``running``; **it fabricates no ``MISSION_FAILED``.**
"""

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from eidos.contracts import MissionId, TenantId
from eidos.replanning import ReplanRejection, ReplanRun, run_with_replanning

from .composition import Composition, PreparedRun
from .config import RunnerConfig
from .errors import Busy, NotStartable, StorageUnavailable, TenantRunLimit
from .ports import ACTIVE, Repositories, RunStatus, StorageError

_log = logging.getLogger("eidos.service.runner")

INTERRUPTED_REASON = "the service stopped or restarted while this run was queued or running; the events already recorded, if any, are a valid prefix of the log"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _reason(error: BaseException) -> str:
    """What a caller may be told of an unexpected fault: its type and nothing of its message, which can name a host, a path or a value. The full fault goes to the server log."""
    return type(error).__name__


class RunManager:
    def __init__(self, *, repositories: Repositories, composition: Composition, config: RunnerConfig, now: Callable[[], datetime] = _now) -> None:
        self._repositories, self._composition, self._config, self._now = repositories, composition, config, now
        self._pool = ThreadPoolExecutor(max_workers=config.worker_pool_size, thread_name_prefix="eidos-run")
        self._lock = threading.Lock()
        self._idle = threading.Condition(self._lock)
        self._live: set[MissionId] = set()  # queued or running in this process
        self._closed = False

    # --- startup ---------------------------------------------------------------------------------------------------------------------

    def recover(self) -> int:
        """Mark every run the previous process left ``queued`` or ``running`` as ``interrupted``. Writes no event. Call once, before accepting requests."""
        try:
            return self._repositories.missions.interrupt_active(reason=INTERRUPTED_REASON, at=self._now())
        except StorageError as error:
            raise StorageUnavailable(str(error)) from error

    # --- start -----------------------------------------------------------------------------------------------------------------------

    def start(self, tenant_id: TenantId, mission_id: MissionId) -> None:
        """Queue one run. Raises ``NotStartable``, ``TenantRunLimit`` or ``Busy``, in that order (``docs/13`` section 5); on success the run is ``queued`` and submitted.

        A mission that is not ``created`` never becomes startable, so that answer comes first and is not hidden behind a capacity answer that could change. The compare-and-set stays the authority.
        """
        missions = self._repositories.missions
        not_startable = NotStartable("the mission is not in the created state: a mission is started once")
        with self._lock:
            if self._closed:
                raise Busy("the service is shutting down")
            try:
                current = missions.get(tenant_id, mission_id)
                if current is None or current.run_status is not RunStatus.CREATED:
                    raise not_startable
                if missions.count_active(tenant_id) >= self._config.max_active_runs_per_tenant:
                    raise TenantRunLimit(f"this tenant already has {self._config.max_active_runs_per_tenant} run(s) queued or running")
                if len(self._live) >= self._config.worker_pool_size + self._config.max_queued_runs:
                    raise Busy("the runner is full: too many runs are queued or running")
                moved = missions.transition(tenant_id, mission_id, expected=(RunStatus.CREATED,), new=RunStatus.QUEUED, reason=None, at=self._now())
            except StorageError as error:
                raise StorageUnavailable(str(error)) from error
            if not moved:
                raise not_startable
            self._live.add(mission_id)
            try:
                self._pool.submit(self._run, tenant_id, mission_id)
            except RuntimeError as error:  # the pool refused: it is shut down
                self._live.discard(mission_id)
                self._finish(tenant_id, mission_id, (RunStatus.QUEUED,), RunStatus.ERROR, f"submission failed: {_reason(error)}")
                raise Busy("the runner could not take the run") from error

    def wait_idle(self, timeout: float) -> bool:
        """Block until no run is queued or running in this process, or ``timeout`` seconds pass. ``True`` if idle. For shutdown and tests; it does not poll."""
        with self._idle:
            return self._idle.wait_for(lambda: not self._live, timeout)

    def shutdown(self, *, wait: bool = False) -> None:
        with self._lock:
            self._closed = True
        self._pool.shutdown(wait=wait, cancel_futures=not wait)

    # --- the run ---------------------------------------------------------------------------------------------------------------------

    def _finish(self, tenant_id: TenantId, mission_id: MissionId, expected: tuple[RunStatus, ...], new: RunStatus, reason: str | None) -> None:
        try:
            self._repositories.missions.transition(tenant_id, mission_id, expected=expected, new=new, reason=reason, at=self._now())
        except Exception:  # noqa: BLE001 - nothing more can be done from here; a stuck row is recovered as interrupted at the next startup
            pass

    def _run(self, tenant_id: TenantId, mission_id: MissionId) -> None:
        try:
            if not self._repositories.missions.transition(tenant_id, mission_id, expected=(RunStatus.QUEUED,), new=RunStatus.RUNNING, reason=None, at=self._now()):
                return  # something else moved it (startup recovery, in a test): nothing to run
            status, reason = self._execute(tenant_id, mission_id)
            self._finish(tenant_id, mission_id, (RunStatus.RUNNING,), status, reason)
        except BaseException as error:  # noqa: BLE001 - a run never takes the worker down and never leaves the row running
            _log.exception("run %s of tenant %s failed unexpectedly", mission_id, tenant_id)
            self._finish(tenant_id, mission_id, (RunStatus.QUEUED, RunStatus.RUNNING), RunStatus.ERROR, f"internal: {_reason(error)}")
        finally:
            with self._idle:
                self._live.discard(mission_id)
                self._idle.notify_all()

    def _execute(self, tenant_id: TenantId, mission_id: MissionId) -> tuple[RunStatus, str | None]:
        mission = self._repositories.missions.get(tenant_id, mission_id)
        if mission is None:
            return RunStatus.ERROR, "the mission disappeared before it ran"
        documents = self._repositories.artifacts(tenant_id).supplied(mission.execution_id)
        prepared: PreparedRun = self._composition.prepare(mission, documents)
        try:
            outcome = run_with_replanning(**prepared.run_arguments)
        except BaseException as error:  # noqa: BLE001 - keep what was recorded, then report the fault
            _log.exception("run %s of tenant %s failed unexpectedly", mission_id, tenant_id)
            prepared.persistence.finish()
            return RunStatus.ERROR, f"internal: {_reason(error)}"
        durable = prepared.persistence.finish()
        if not durable:
            persistence = prepared.persistence
            _log.error("run %s of tenant %s: its events could not all be stored: %s", mission_id, tenant_id, persistence.failure or persistence.last_error or "unknown")
            detail = persistence.failure or (persistence.last_error or "unknown").split(":", 1)[0]  # a conflict is our own wording; a store fault is told by its type alone
            return RunStatus.ERROR, f"persistence: the events of this run could not all be stored ({detail}); those that were not stored are lost when the process exits"
        if isinstance(outcome, ReplanRejection):
            return RunStatus.REJECTED, f"{outcome.code.value}: {outcome.outcome.value}: {outcome.reason}"
        assert isinstance(outcome, ReplanRun)
        if outcome.refused or outcome.discrepancies:
            return RunStatus.ERROR, f"the recorded log is not the whole story: {len(outcome.refused)} event(s) refused, {len(outcome.discrepancies)} discrepancy(ies)"
        return RunStatus.FINISHED, None


__all__ = ["ACTIVE", "INTERRUPTED_REASON", "RunManager"]
