"""ONE reusable benchmark harness for the first controlled EIDOS benchmark (the owner's final approval, 2026-09-23;
decisions.md D-196 — the benchmark itself stays unassigned a milestone number, exactly like MCP/RAG under D-184).

**Location.** Lives under ``tests/support`` (pythonpath'd, never itself collected — mirrors every other
``eidos_*_factories.py`` module here) because that is the narrowest existing convention for reusable,
non-shipped test/experiment machinery already in this repository. Actual assertions and the case tables live in
``tests/scenarios/test_benchmark_execution_control.py`` — ``tests/scenarios`` is already scoped by CLAUDE.md §6
to "full missions, replanning, verification failure, budget exhaustion, policy violation," a near-exact match
for this benchmark's own task classes, and it is already a collected ``testpaths`` entry (``pyproject.toml``).
No new top-level directory. No ``src/eidos/evaluation`` (explicitly reserved for V1.1 in ``progress.md``'s
"Intentionally not built yet" table — creating it now for a still-unnumbered milestone would be exactly what
CLAUDE.md §3 forbids).

**Every condition below composes only already-shipped ``eidos`` code.** Nothing here adds a core contract, a
``MissionEvent``, or a package under ``src/eidos``. The model is always ``eidos_agents_factories.ScriptedModel``
(D-136's own established substitution point): every token or latency figure this harness reports is a
**scripted constant**, never a real provider measurement — ``BenchmarkResult.tokens_are_scripted`` is always
``True`` and must stay visible next to every token figure this benchmark ever reports.

**Four conditions (the owner's final decision):**

- **A — Direct Agent Baseline.** One ``WorkAgent`` called directly (``agent.run(context, node)``). No ``Plan``,
  no validation, no compiler, no ``eidos.runtime`` execution, no ``EventLog``, no ``Telemetry`` — runner-side
  capture only. The one unavoidable concession: ``WorkAgent.run()``'s own fixed signature (D-122) requires an
  ``ExecutionContext``, which itself requires a ``plan_id``/``plan_version`` — a fixed identity label only,
  never a constructed, validated ``Plan``.
- **B — Fixed Workflow.** A hand-authored ``Plan`` through the existing, unmodified
  ``validate_plan -> compile_plan -> bind_plan -> execute -> verify`` chain, recorded by the existing, unmodified
  ``record_baseline`` and projected by the existing, unmodified ``project``.
- **C — LLM-Generated Workflow.** A model's Plan-DSL JSON text through the existing, unmodified
  ``validate_plan_json`` ingress (D-107). A rejected plan is captured directly from its own
  ``PlanValidationReport`` and never reaches ``record_baseline`` — there is nothing to execute. An accepted
  plan continues through the identical path B uses.
- **D — EIDOS Validated Strategy Execution.** The proven chain (mirrors
  ``tests/integration/planning/test_strategy_to_telemetry_integration.py`` exactly):
  ``generate_candidate_strategies -> select_strategy -> expand_strategy -> validate_plan -> record_baseline ->
  project``. Cold path (candidate generation, feasibility, selection, expansion) and hot path (validation
  onward) are timed separately with the runner's own ``time.perf_counter`` — found by inspection that
  ``TelemetryRecord``'s own bounds start at ``MISSION_CREATED``, which ``record_baseline`` emits *after* the
  cold path has already finished, so the cold path is genuinely invisible to core telemetry. Nothing here adds
  a ``MissionEvent`` to close that gap (D-185 stays exactly as it is) — this is runner-side timing only.

D1 uses ``DeterministicSelector`` (D-188, unmodified). D2 (only where >=2 candidates actually exist — where
there is a real choice to make) uses the existing ``ModelAssistedSelector`` (V0.8 Step 5, unmodified) over the
*same* feasible candidate set D1 would see. D2 is a selector comparison, not an adaptive-learning experiment:
nothing here reads or writes history across calls, and the selector's own model call happens during the cold
path, so it is separately counted in ``BenchmarkResult.selector_model_calls`` — ``TelemetryRecord.model_call_count``
never sees it, another instance of the same cold-path blind spot.
"""

import hashlib
import threading
import time
from dataclasses import dataclass, field, replace
from uuid import UUID

from eidos.agents import AnalysisAgent, InMemoryArtifactStore, ModelResponse, ResearchAgent, VerificationAgent
from eidos.compiler import WorkNode
from eidos.contracts import (
    CapabilityId,
    ExecutionId,
    MissionId,
    MissionState,
    Plan,
    PlanId,
    ReliabilityContract,
    StepId,
    TaskGenome,
    TenantId,
)
from eidos.expansion import expand_strategy
from eidos.planning import (
    RuleBasedCandidateGenerator,
    Selector,
    SelectionOutcome,
    generate_candidate_strategies,
    select_strategy,
)
from eidos.recording import ModelCallTracker, RecordedRun, RecordingModel, UuidPlanIds, UuidStrategyIds, record_baseline
from eidos.runtime import AdmissionGuard, ExecutionContext, SequentialExecutor
from eidos.telemetry import TelemetryRecord, project
from eidos.validation import SystemLimits, validate_plan_json

from eidos_agents_factories import make_settings
from eidos_recording_factories import FixedClock, SequentialIds, three_docs
from eidos_runtime_factories import admit_all
from eidos_v04_registry import ANALYSIS_AGENT_ID, RESEARCH_AGENT_ID, make_registry

TOKENS_ARE_SCRIPTED = True  # every model call in this benchmark is eidos_agents_factories.ScriptedModel (D-136)

# A fixed, meaningless identity ExecutionContext requires structurally (D-122's own signature) but that
# Condition A never validates, compiles or executes anything against — see the module docstring.
_DIRECT_PLAN_ID = PlanId(UUID(int=1))


@dataclass(frozen=True, slots=True, kw_only=True)
class BenchmarkResult:
    """One condition's outcome for one task-class case. A metric *vector*, never a combined score (D-188's own
    "never weighted or combined into a single number" discipline, applied here one layer up)."""

    condition: str  # "A" | "B" | "C" | "D1" | "D2"
    task_class: str
    case_id: str

    dispatched_anything: bool  # False proves nothing was ever executed (invalid-plan interception)
    mission_status: str | None = None
    run_outcome: str | None = None  # distinguishes HALTED/AWAITING within a PAUSED mission_status
    verified: bool | None = None
    failure_cause: str | None = None
    plan_rejected_at: str | None = None

    execution_time_used_ms: int | None = None
    mission_wall_clock_ms: int | None = None
    model_call_count: int | None = None
    selector_model_calls: int | None = None  # D2 only: the cold-path selector call, invisible to telemetry
    tokens_used: int | None = None
    tokens_are_scripted: bool = TOKENS_ARE_SCRIPTED

    cold_path_ms: float | None = None  # D1/D2 only: candidate generation + feasibility + selection + expansion
    hot_path_ms: float | None = None  # validation onward (or the whole call, for A)

    digest: str = ""  # sha256 of the deterministic serialized outcome — see digest_of()


def digest_of(value) -> str:
    """sha256 of a Pydantic value's own strict JSON serialization — the reproducibility check's own basis
    (Section 8 of the approval): two runs of the same condition/case must produce the identical digest."""
    return hashlib.sha256(value.model_dump_json().encode()).hexdigest()


@dataclass(slots=True)
class Capture:
    """Wraps a scripted ``respond`` function to keep the ``ModelResult`` values it returned, in call order —
    the only way to recover token facts for a call whose result the port under test (``WorkResult``, a
    ``SelectorChoice``) does not itself carry through."""

    results: list = field(default_factory=list)

    def wrap(self, respond):
        def _respond(request):
            result = respond(request)
            self.results.append(result)
            return result

        return _respond

    @property
    def calls(self) -> int:
        return len(self.results)

    @property
    def tokens(self) -> int:
        total = 0
        for result in self.results:
            if isinstance(result, ModelResponse):
                total += (result.measured.prompt_tokens or 0) + (result.measured.output_tokens or 0)
        return total


# --- Condition A: Direct Agent Baseline --------------------------------------------------------------------------


def run_condition_a(
    *, task_class: str, case_id: str, genome: TaskGenome, contract: ReliabilityContract,
    tenant_id: TenantId, mission_id: MissionId, execution_id: ExecutionId,
    capability: str, documents: tuple, respond,
) -> BenchmarkResult:
    """Call ``ResearchAgent`` directly for one capability. No Plan, no validation, no compiler, no runtime, no
    EventLog, no Telemetry — everything here is captured by the runner alone."""
    store = InMemoryArtifactStore()
    for document in documents:
        store.put_supplied(execution_id, document)
    capture = Capture()
    agent = ResearchAgent(model=ScriptedPort(capture.wrap(respond)), settings=make_settings(), store=store)
    context = ExecutionContext(
        tenant_id=tenant_id, mission_id=mission_id, execution_id=execution_id,
        plan_id=_DIRECT_PLAN_ID, plan_version=1, task_genome=genome, reliability_contract=contract,
    )
    node = WorkNode(step_id=StepId("direct"), position=0, level=1, predecessors=(), capability=CapabilityId(capability))

    start = time.perf_counter()
    result = agent.run(context, node)
    elapsed_ms = (time.perf_counter() - start) * 1000

    return BenchmarkResult(
        condition="A", task_class=task_class, case_id=case_id,
        dispatched_anything=True,
        model_call_count=capture.calls, tokens_used=capture.tokens,
        hot_path_ms=elapsed_ms, digest=digest_of(result),
    )


class ScriptedPort:
    """A minimal ``ModelPort`` over a plain callable, so ``Capture.wrap`` needs no thread lock of its own for a
    single, synchronous direct call (unlike ``ScriptedModel``, which is built for concurrent runtime dispatch)."""

    def __init__(self, respond):
        self._respond = respond

    def complete(self, request):
        return self._respond(request)


# --- Conditions B, C and D share one path from a real Plan onward -------------------------------------------------


def _record_and_project(
    *, state: MissionState, plan: Plan, limits: SystemLimits, respond, guard: AdmissionGuard | None = None,
) -> RecordedRun:
    store = InMemoryArtifactStore()
    for document in three_docs():
        store.put_supplied(state.execution_id, document)
    settings = make_settings()
    tracker = ModelCallTracker()
    model = RecordingModel(_RecordingScriptedPort(respond), tracker)
    agents = {
        RESEARCH_AGENT_ID: ResearchAgent(model=model, settings=settings, store=store),
        ANALYSIS_AGENT_ID: AnalysisAgent(model=model, settings=settings, store=store),
    }
    return record_baseline(
        state=state, plan=plan, limits=limits, registry=make_registry(), agents=agents,
        verifier=VerificationAgent(store=store), admission_guard=guard or admit_all(),
        executor_factory=SequentialExecutor, clock=FixedClock(), ids=SequentialIds(), tracker=tracker,
    )


class _RecordingScriptedPort:
    """Thread-safe ``ModelPort`` over a plain callable: a level's nodes may dispatch on worker threads even
    under the reference ``SequentialExecutor`` (D-136's own ``ScriptedModel`` locks for the identical reason)."""

    def __init__(self, respond):
        self._respond = respond
        self._lock = threading.Lock()

    def complete(self, request):
        with self._lock:
            respond = self._respond
        return respond(request)


def _result_from_recorded(*, condition: str, task_class: str, case_id: str, recorded: RecordedRun,
                           cold_path_ms: float | None = None, hot_path_ms: float | None = None) -> BenchmarkResult:
    assert recorded.refused == () and recorded.discrepancies == (), (recorded.refused, recorded.discrepancies)
    telemetry = project(recorded.log.records)
    assert isinstance(telemetry, TelemetryRecord), telemetry  # a ReplayRejection here is a harness bug, never a valid outcome
    return BenchmarkResult(
        condition=condition, task_class=task_class, case_id=case_id,
        dispatched_anything=recorded.report.dispatched_anything,
        mission_status=telemetry.mission_status.value,
        run_outcome=telemetry.run_outcome.value if telemetry.run_outcome else None,
        verified=telemetry.verified,
        failure_cause=telemetry.failure_cause.value if telemetry.failure_cause else None,
        plan_rejected_at=telemetry.plan_rejected_at.value if telemetry.plan_rejected_at else None,
        execution_time_used_ms=telemetry.execution_time_used_ms, mission_wall_clock_ms=telemetry.mission_wall_clock_ms,
        model_call_count=telemetry.model_call_count, tokens_used=telemetry.tokens_used,
        cold_path_ms=cold_path_ms, hot_path_ms=hot_path_ms, digest=digest_of(telemetry),
    )


# --- Condition B: Fixed Workflow ------------------------------------------------------------------------------------


def run_condition_b(*, task_class: str, case_id: str, state: MissionState, plan: Plan, limits: SystemLimits,
                     respond, guard: AdmissionGuard | None = None) -> BenchmarkResult:
    """A hand-authored Plan through the existing, unmodified execution/recording/telemetry chain."""
    start = time.perf_counter()
    recorded = _record_and_project(state=state, plan=plan, limits=limits, respond=respond, guard=guard)
    elapsed_ms = (time.perf_counter() - start) * 1000
    return _result_from_recorded(condition="B", task_class=task_class, case_id=case_id, recorded=recorded, hot_path_ms=elapsed_ms)


# --- Condition C: LLM-Generated Workflow ----------------------------------------------------------------------------


def run_condition_c(*, task_class: str, case_id: str, state: MissionState, plan_json: str, limits: SystemLimits,
                     respond, guard: AdmissionGuard | None = None) -> BenchmarkResult:
    """``plan_json`` stands in for a model's own Plan-DSL output (D-136's substitution point, one layer up: the
    text just happens to be Plan JSON instead of a research answer). Whatever ``validate_plan_json`` decides is
    exactly what interception means here — a rejected plan is captured from its own report and never dispatched."""
    start = time.perf_counter()
    validation = validate_plan_json(plan_json, state, limits)
    if not validation.accepted:
        elapsed_ms = (time.perf_counter() - start) * 1000
        # Whatever the failing V0.2 stage (schema, capability, ...), record_baseline would never get past the
        # single coarse VALIDATION gate either (baseline.py's own BaselineStage.VALIDATION) — the same vocabulary
        # B/D's own plan_rejected_at uses, so this value is comparable across conditions.
        return BenchmarkResult(
            condition="C", task_class=task_class, case_id=case_id,
            dispatched_anything=False, plan_rejected_at="validation",
            hot_path_ms=elapsed_ms, digest=digest_of(validation),
        )
    plan = Plan.model_validate_json(plan_json)
    recorded = _record_and_project(state=state, plan=plan, limits=limits, respond=respond, guard=guard)
    elapsed_ms = (time.perf_counter() - start) * 1000
    return _result_from_recorded(condition="C", task_class=task_class, case_id=case_id, recorded=recorded, hot_path_ms=elapsed_ms)


# --- Condition D: EIDOS Validated Strategy Execution (D1 deterministic, D2 model-assisted) ---------------------------


def run_condition_d(
    *, condition: str, task_class: str, case_id: str, state: MissionState, selector: Selector,
    limits: SystemLimits, max_candidates: int, respond, guard: AdmissionGuard | None = None,
    selector_capture: Capture | None = None, strategy_ids=None, plan_ids=None,
) -> BenchmarkResult:
    """The proven chain: generate -> feasibility -> select -> expand -> validate -> record -> project. ``selector``
    is ``DeterministicSelector()`` for D1 or ``ModelAssistedSelector(...)`` for D2 — both see the identical
    feasible candidate set (``select_strategy``'s own membership check is the only admission boundary, unchanged
    either way). ``selector_capture``, when given, recovers D2's own cold-path model call (never visible to
    ``TelemetryRecord.model_call_count`` — see the module docstring). ``strategy_ids``/``plan_ids`` default to
    the real ``UuidStrategyIds``/``UuidPlanIds`` (genuinely fresh draws, matching the proven integration test);
    a caller proving reproducibility supplies a fixed test double instead, since a genuinely fresh id is
    expected to differ between two runs by design and is not itself a reproducibility failure."""
    genome = state.task_genome
    cold_start = time.perf_counter()
    generation = generate_candidate_strategies(
        RuleBasedCandidateGenerator(), genome, mission_id=state.mission_id, reliability_contract=state.reliability_contract,
        limits=limits, max_candidates=max_candidates, ids=strategy_ids or UuidStrategyIds(),
    )
    selection = select_strategy(selector, generation.candidates, genome)
    assert selection.outcome is SelectionOutcome.SELECTED, selection
    plan = expand_strategy(selection.selected, ids=plan_ids or UuidPlanIds())
    cold_ms = (time.perf_counter() - cold_start) * 1000

    hot_start = time.perf_counter()
    recorded = _record_and_project(state=state, plan=plan, limits=limits, respond=respond, guard=guard)
    hot_ms = (time.perf_counter() - hot_start) * 1000

    result = _result_from_recorded(condition=condition, task_class=task_class, case_id=case_id, recorded=recorded,
                                    cold_path_ms=cold_ms, hot_path_ms=hot_ms)
    if selector_capture is not None:
        result = replace(result, selector_model_calls=selector_capture.calls)
    return result
