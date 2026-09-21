"""The recorder: the one door events go through on the way to the log (decisions.md D-158, D-160).

It holds **no** ``MissionState`` and cannot write one. It builds an ``EventProposal`` — identity, the time from the injected clock, a typed
payload, and no sequence — and hands it to the log's intake, which orders it; only the reducer, behind the intake, writes state (invariants 1
and 2). A proposal the intake refuses is **kept and surfaced** (``refused``), never dropped, so both outcomes reach the caller (D-160 item 7).

It is safe to call from several threads — an execution backend may run the nodes of one level on worker threads — because one lock covers the clock read, the
intake and the bookkeeping. The order in which callers get through the lock is the order the log records; that acceptance order is the only
ordering there is, and it can differ between two live runs of a plan with parallel nodes (D-158 item 6). No ordering is inferred from a time.
"""

import threading

from eidos.contracts import MissionId, StepId, TenantId
from eidos.runtime import NodeResult
from eidos.state import EventLog, EventProposal, IntakeResult, ModelCallFacts, NodeSettledPayload, VerificationFacts

from .ports import Clock, IdSource


class Observation:
    """What was seen while one node ran: how long, and the model calls made. Facts only; nothing here is an estimate."""

    __slots__ = ("duration_ms", "model_calls")

    def __init__(self, duration_ms: int, model_calls: tuple[ModelCallFacts, ...]):
        self.duration_ms, self.model_calls = duration_ms, model_calls


class Recorder:
    def __init__(self, *, log: EventLog, clock: Clock, ids: IdSource, tenant_id: TenantId, mission_id: MissionId):
        self.log, self.clock, self.ids = log, clock, ids
        self.tenant_id, self.mission_id = tenant_id, mission_id
        self._lock = threading.Lock()
        self._refused: list[IntakeResult] = []
        self._live: dict[StepId, NodeResult] = {}  # nodes already settled in the log, live, as their work returned
        self._observed: dict[StepId, Observation] = {}  # what was seen while a node ran, for a node settled after the run
        self._discrepancies: list[str] = []

    # --- the door ---------------------------------------------------------------------------------------------------------------

    def record(self, payload) -> IntakeResult:
        with self._lock:
            return self._propose(payload)

    def _propose(self, payload) -> IntakeResult:
        moment = self.clock.now()  # one reading: for an EIDOS-internal event the two times are the same instant (D-086)
        result = self.log.accept(
            EventProposal(
                event_id=self.ids.next_event_id(),
                tenant_id=self.tenant_id,
                mission_id=self.mission_id,
                occurred_at=moment,
                recorded_at=moment,
                payload=payload,
            )
        )
        if not result.applied:
            self._refused.append(result)
        return result

    # --- measuring --------------------------------------------------------------------------------------------------------------

    def monotonic_ns(self) -> int:
        return self.clock.monotonic_ns()

    def duration_ms(self, started_ns: int) -> int:
        """Whole milliseconds since ``started_ns``, as the injected monotonic clock measured them."""
        return max(0, (self.clock.monotonic_ns() - started_ns) // 1_000_000)

    # --- nodes ------------------------------------------------------------------------------------------------------------------

    def note_observation(self, step_id: StepId, duration_ms: int, model_calls: tuple[ModelCallFacts, ...]) -> None:
        with self._lock:
            self._observed[step_id] = Observation(duration_ms, model_calls)

    def settle_live(self, plan_id, result: NodeResult, duration_ms: int, model_calls, verification: VerificationFacts | None) -> IntakeResult:
        """Record a node's settlement now, as its work returns, and remember what was recorded so the run's own result can be checked against it."""
        with self._lock:
            outcome = self._propose(
                NodeSettledPayload(
                    plan_id=plan_id, result=result, dispatched=True, duration_ms=duration_ms,
                    model_calls=tuple(model_calls), verification=verification,
                )
            )
            if outcome.applied:
                self._live[result.step_id] = result
            return outcome

    def live_result(self, step_id: StepId) -> NodeResult | None:
        with self._lock:
            return self._live.get(step_id)

    def observation(self, step_id: StepId) -> Observation | None:
        with self._lock:
            return self._observed.get(step_id)

    def note_discrepancy(self, text: str) -> None:
        with self._lock:
            self._discrepancies.append(text)

    # --- what the caller may inspect --------------------------------------------------------------------------------------------

    @property
    def refused(self) -> tuple[IntakeResult, ...]:
        with self._lock:
            return tuple(self._refused)

    @property
    def discrepancies(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._discrepancies)
