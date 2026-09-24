"""ONE reusable benchmark harness for the second controlled EIDOS benchmark (decisions.md D-198 ruling 11;
V1.0 Step 7 — the final V1.0 step).

**Location.** Same convention as Benchmark 1 (`eidos_benchmark_harness.py` / `test_benchmark_execution_control.py`,
5842244): this module lives under `tests/support` (pythonpath'd, never itself collected); the actual assertions,
mutation targets and the per-mission report live in `tests/scenarios/test_benchmark2_experience_informed_selection.py`.
No new top-level directory, no `src/eidos/evaluation` — the benchmark itself stays unassigned a milestone number,
exactly like Benchmark 1 (D-196/D-197).

**Research question** (D-198's own framing, restated by the owner's Step 7 brief): can measured execution
experience from previous missions change future strategy selection under controlled conditions? This is not a
"best strategy" claim. Nothing here produces a quality score, a combined benchmark score, a statistical
significance claim, a general superiority claim, or ranking/election language — `BenchmarkResult` is a metric
*vector*, never a combined score (D-188's own discipline, applied here two layers up), and every reporting
function below prints a plain per-condition, per-pair, per-mission table only.

**Three fixed capability pairs** (D-198 ruling 11; never generated, never resized): research+cost,
research+security, cost+security. Each pair's two-capability `TaskGenome` yields exactly two
`RuleBasedCandidateGenerator` candidates — `generator.py`'s own shape-gating rules mean `_staged_shape` returns
`None` below three capabilities, so a 2-capability genome is always exactly `{linear, parallel}}`, linear always
first (the generator's own fixed shape order). `DeterministicSelector`'s own `structural_cost` tie-break
(`(total capability occurrences, stage count)`) always prefers parallel for any 2-capability genome — both
candidates tie on the first component (`2`), decided by fewer stages (`1 < 2`) — a fact that holds for all three
pairs regardless of the actual capability names involved (confirmed by inspection of `generator.py`/`selector.py`,
not assumed).

**Three conditions, five missions each, per pair — 3 x 3 x 5 = 45 mission executions**:

- **D1 — Deterministic baseline.** `DeterministicSelector`, no memory. Five independent missions; each one is
  cold with respect to `eidos.memory` because this condition never constructs or touches an `ExperienceStore`.
- **D2 — Model-assisted baseline.** `ModelAssistedSelector` over a scripted, deterministic model response fixed
  to the parallel candidate's own label every time (`CANDIDATE_2`, the generator's own fixed second shape) — the
  same choice `DeterministicSelector` already makes, so D1 and D2 agree throughout the whole sequence. This is a
  selector-implementation comparison, never an adaptive-learning one: D2 also never touches an `ExperienceStore`.
- **E1 — Experience-informed selection.** The real `ExperienceInformedSelector` over a real, JSONL-backed
  `ExperienceStore` — one dedicated store file per capability pair, never shared across pairs or with D1/D2 (a
  research+cost record and a research+security record would otherwise overlap under `TaskRelevance.SIMILAR`,
  confounding the comparison; D1/D2 must stay cold by construction, per the approved design's own control).
  Mission 1 of each pair's own sequence is a genuine cold start — empty store, defers to its own injected
  `DeterministicSelector` fallback, matching D1/D2's own first-mission choice exactly. Missions 2 to 5 read the
  history accumulated so far, reopened fresh from disk every mission (stronger than V1.0 Step 6's own
  one-reopen proof): a real demonstration of persistence, not object reuse.

**Controlled failure mechanism** (D-198 ruling 11, the topology-driven mechanism already approved and already
used unmodified in V1.0 Step 6): a deterministic `AdmissionGuard`, fresh per mission,
`halt_when(lambda r: r.rank_in_level >= 1, ...)`. Parallel always dispatches a second, concurrent node at
`rank_in_level == 1` and halts before `VERIFY`; linear never dispatches more than one node per level and never
halts. Every mission uses a uniformly sufficient scripted response (`_uniformly_sufficient` — all three supplied
documents cited by every capability) so citation quality is never the cause of any observed difference: the only
thing that differs between the two candidates is topology/concurrency.

**Metrics are a vector, never a combined score.** `BenchmarkResult` carries condition, capability pair, mission
index, the selected shape and id, every already-available `TelemetryRecord` outcome/cost field, the selector's
own cold-path model-call count (D2 only — 0 for D1/E1, neither ever calls a model to select), whether relevant
history was available before selection and how many relevant records existed, and a reproducibility digest.

**Reproducibility.** `digest_of` hashes only the semantic outcome fields — condition, capability pair, mission
index, the selected *shape* (never the raw `selected_strategy_id`, a genuinely fresh `uuid4()` draw every mission
by design, D-182), every mission status/outcome/verification/failure field, every cost field already listed
above, and the history-availability facts. `FixedClock`/`SequentialIds`, fresh per mission, make every timestamp
and accounted-time fact deterministic regardless of `PYTHONHASHSEED`; only the raw, genuinely-fresh
`strategy_id`/`plan_id` values are excluded from what is hashed — exactly the approved design's own "exclude raw
random IDs from the digest" instruction.
"""

import hashlib
import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from eidos.agents import MeasuredFacts, ModelResponse
from eidos.contracts import MissionState
from eidos.expansion import expand_strategy
from eidos.memory import ExperienceStore, JsonlExperienceStore, evaluate_experience, relevant_experience
from eidos.planning import (
    CandidateGenerationResult,
    DeterministicSelector,
    RuleBasedCandidateGenerator,
    SelectionOutcome,
    Selector,
    Strategy,
    generate_candidate_strategies,
    select_strategy,
)
from eidos.recording import UuidPlanIds, UuidStrategyIds
from eidos.selectors import ExperienceInformedSelector, ModelAssistedSelector
from eidos.telemetry import TelemetryRecord, project
from eidos.validation import validate_plan

from eidos_agents_factories import make_settings
from eidos_benchmark_harness import Capture, ScriptedPort  # reused test-support infra, not benchmark-1-specific
from eidos_mission_factories import make_mission
from eidos_planning_factories import GENEROUS_LIMITS
from eidos_recording_factories import FixedClock, SequentialIds, record
from eidos_runtime_factories import halt_when
from eidos_state_factories import T0
from eidos_v04_registry import make_registry

CAPABILITY_PAIRS: tuple[tuple[str, str], ...] = (
    ("research", "cost"),
    ("research", "security"),
    ("cost", "security"),
)
N_MISSIONS = 5
TOKENS_ARE_SCRIPTED = True  # every model call in this benchmark is scripted (D-136), mirroring Benchmark 1


def _seed(pair_index: int, condition_offset: int, mission_index: int) -> int:
    """A fixed, deterministic, collision-free `make_mission` seed per (pair, condition, mission) triple.
    `condition_offset` is 1 (D1), 2 (D2) or 3 (E1); `mission_index` is 1..N_MISSIONS < 10, so the three
    conditions' own seed ranges never overlap within a pair, and `pair_index * 100` keeps pairs apart."""
    return 1000 + pair_index * 100 + condition_offset * 10 + mission_index


def _uniformly_sufficient(request):
    # Every capability cites all three supplied documents — sufficient for min_independent_evidence=3 regardless
    # of which stage VERIFY ends up seeing (final-stage-only for linear, the whole stage for parallel). The
    # causal mechanism under test is topology/concurrency, never citation quality (D-198 ruling 11).
    text = "Findings [[doc:1]] [[doc:2]] [[doc:3]]." if "Documents:" in request.prompt else "Analysis [[doc:1]] [[doc:2]] [[doc:3]]."
    return ModelResponse(text=text, measured=MeasuredFacts(prompt_tokens=100, output_tokens=200, elapsed_seconds=0.5))


def _selector_picks_parallel(request):
    # CANDIDATE_2 is always the parallel shape for a two-capability genome (RuleBasedCandidateGenerator's own
    # fixed (linear, parallel) order — staged is never produced below three capabilities). Fixed, reproducible,
    # never random — D2's own scripted choice always matches D1's own structural-cost bias (D-198 ruling 11).
    return ModelResponse(text="[[CANDIDATE_2]]", measured=MeasuredFacts(prompt_tokens=80, output_tokens=5, elapsed_seconds=0.1))


def _concurrent_halt_guard():
    """A fresh `AdmissionGuard` per mission — the approved topology-driven mechanism (D-198 ruling 11, reused
    unmodified from V1.0 Step 6): halts any shape dispatching more than one node per level."""
    return halt_when(lambda request: request.rank_in_level >= 1, "benchmark2: no concurrent dispatch")


def _shape_of(strategy: Strategy) -> tuple[tuple[str, ...], ...]:
    return tuple(tuple(stage.capabilities) for stage in strategy.stages)


@dataclass(frozen=True, slots=True, kw_only=True)
class BenchmarkResult:
    """One mission's outcome for one condition/capability-pair/mission-index. A metric *vector*, never a combined
    score (D-188's own discipline, applied here two layers up)."""

    condition: str  # "D1" | "D2" | "E1"
    capability_pair: tuple[str, str]
    mission_index: int  # 1..N_MISSIONS

    mission_id: str  # descriptive only — deterministic from `seed` (never random); excluded from digest_of() for scope, not risk
    execution_id: str
    selected_strategy_shape: tuple[tuple[str, ...], ...]
    selected_strategy_id: str  # descriptive only — deliberately excluded from digest_of(), see module docstring

    mission_status: str
    run_outcome: str | None
    verified: bool | None
    failure_cause: str | None
    plan_rejected_at: str | None

    execution_time_used_ms: int
    mission_wall_clock_ms: int
    model_call_count: int
    selector_model_calls: int  # D2 only: the cold-path selector call, invisible to TelemetryRecord; 0 for D1/E1
    tokens_used: int
    tokens_are_scripted: bool = TOKENS_ARE_SCRIPTED

    agent_calls_used: int
    tool_calls_used: int
    retries_used: int
    replans_used: int

    history_available: bool  # was the ExperienceStore non-empty before this mission's selection? (E1 only; else False)
    relevant_history_count: int  # len(relevant_experience(...)) before this mission's selection (E1 only; else 0)

    digest: str = ""


def digest_of(result: BenchmarkResult) -> str:
    """sha256 over the semantic outcome only — never `selected_strategy_id` (a fresh `uuid4()` draw every
    mission by design, D-182) — so two independent runs of the identical condition/pair/mission produce the
    identical digest despite genuinely fresh strategy/plan ids each time. See the module docstring."""
    payload = {
        "condition": result.condition,
        "capability_pair": list(result.capability_pair),
        "mission_index": result.mission_index,
        "selected_strategy_shape": [list(stage) for stage in result.selected_strategy_shape],
        "mission_status": result.mission_status,
        "run_outcome": result.run_outcome,
        "verified": result.verified,
        "failure_cause": result.failure_cause,
        "plan_rejected_at": result.plan_rejected_at,
        "execution_time_used_ms": result.execution_time_used_ms,
        "mission_wall_clock_ms": result.mission_wall_clock_ms,
        "model_call_count": result.model_call_count,
        "selector_model_calls": result.selector_model_calls,
        "tokens_used": result.tokens_used,
        "agent_calls_used": result.agent_calls_used,
        "tool_calls_used": result.tool_calls_used,
        "retries_used": result.retries_used,
        "replans_used": result.replans_used,
        "history_available": result.history_available,
        "relevant_history_count": result.relevant_history_count,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def generate_pair_candidates(capability_pair: tuple[str, str], seed: int) -> tuple[MissionState, CandidateGenerationResult]:
    """The one candidate-generation call every condition shares — fresh `StrategyId`s every call
    (`UuidStrategyIds()`, D-182), so no two calls (even for the identical pair/seed) ever share an id. Exposed
    separately from `_run_one_mission` so tests can prove candidate equivalence and fresh-id structural matching
    directly, without re-deriving generation from three separate mission runs."""
    state = make_mission(capabilities=capability_pair, seed=seed)
    generation = generate_candidate_strategies(
        RuleBasedCandidateGenerator(), state.task_genome, mission_id=state.mission_id,
        reliability_contract=state.reliability_contract, limits=GENEROUS_LIMITS, max_candidates=3,
        ids=UuidStrategyIds(),
    )
    assert len(generation.candidates) == 2, "a two-capability genome yields exactly linear and parallel"
    return state, generation


def _run_one_mission(
    *, condition: str, capability_pair: tuple[str, str], mission_index: int, seed: int,
    selector: Selector, store: ExperienceStore | None = None, selector_capture: Capture | None = None,
):
    """The one execution path every condition shares: generate -> (relevance snapshot) -> select -> expand ->
    validate -> record -> project -> (persist, E1 only). `store`, when given, is read for the pre-selection
    relevance snapshot and is where the resulting `ExecutionExperience` is appended — the *same* store object
    the caller's own `selector` already holds, so both see one consistent history (single-threaded, no race)."""
    state, generation = generate_pair_candidates(capability_pair, seed)
    genome = state.task_genome

    if store is not None:
        history_before = store.all()
        relevant = relevant_experience(generation.candidates, genome, history_before)
        history_available = len(history_before) > 0
        relevant_history_count = len(relevant)
    else:
        history_available = False
        relevant_history_count = 0

    selection = select_strategy(selector, generation.candidates, genome)
    assert selection.outcome is SelectionOutcome.SELECTED, selection
    selected = selection.selected

    plan = expand_strategy(selected, ids=UuidPlanIds())
    validation = validate_plan(plan, state, GENEROUS_LIMITS)
    assert validation.accepted, validation.violations

    recorded, _rig = record(
        state, plan, respond=_uniformly_sufficient, registry=make_registry(), guard=_concurrent_halt_guard(),
        limits=GENEROUS_LIMITS, clock=FixedClock(), ids=SequentialIds(),
    )
    assert recorded.refused == () and recorded.discrepancies == ()
    telemetry = project(recorded.log.records)
    assert isinstance(telemetry, TelemetryRecord), telemetry

    if store is not None:
        experience = evaluate_experience(selected, genome, telemetry, recorded_at=T0)
        store.append(experience)

    result = BenchmarkResult(
        condition=condition, capability_pair=capability_pair, mission_index=mission_index,
        mission_id=str(state.mission_id), execution_id=str(state.execution_id),
        selected_strategy_shape=_shape_of(selected), selected_strategy_id=str(selected.strategy_id),
        mission_status=telemetry.mission_status.value,
        run_outcome=telemetry.run_outcome.value if telemetry.run_outcome else None,
        verified=telemetry.verified,
        failure_cause=telemetry.failure_cause.value if telemetry.failure_cause else None,
        plan_rejected_at=telemetry.plan_rejected_at.value if telemetry.plan_rejected_at else None,
        execution_time_used_ms=telemetry.execution_time_used_ms,
        mission_wall_clock_ms=telemetry.mission_wall_clock_ms,
        model_call_count=telemetry.model_call_count,
        selector_model_calls=selector_capture.calls if selector_capture is not None else 0,
        tokens_used=telemetry.tokens_used,
        agent_calls_used=telemetry.agent_calls_used, tool_calls_used=telemetry.tool_calls_used,
        retries_used=telemetry.retries_used, replans_used=telemetry.replans_used,
        history_available=history_available, relevant_history_count=relevant_history_count,
    )
    result = replace(result, digest=digest_of(result))
    return result, selected, telemetry, state, plan


# --- Condition sequences: 5 missions each -----------------------------------------------------------------------


def run_d1_sequence(capability_pair: tuple[str, str], *, pair_index: int) -> tuple[BenchmarkResult, ...]:
    """Five independent missions, `DeterministicSelector`, no `ExperienceStore` ever constructed — cold by
    construction, never merely by convention."""
    results = []
    for mission_index in range(1, N_MISSIONS + 1):
        seed = _seed(pair_index, 1, mission_index)
        result, *_ = _run_one_mission(
            condition="D1", capability_pair=capability_pair, mission_index=mission_index, seed=seed,
            selector=DeterministicSelector(),
        )
        results.append(result)
    return tuple(results)


def run_d2_sequence(capability_pair: tuple[str, str], *, pair_index: int) -> tuple[BenchmarkResult, ...]:
    """Five independent missions, `ModelAssistedSelector` scripted to the parallel candidate every time, no
    `ExperienceStore` ever constructed — a fresh `Capture` per mission counts that mission's own cold-path call."""
    results = []
    for mission_index in range(1, N_MISSIONS + 1):
        seed = _seed(pair_index, 2, mission_index)
        capture = Capture()
        selector = ModelAssistedSelector(model=ScriptedPort(capture.wrap(_selector_picks_parallel)), settings=make_settings())
        result, *_ = _run_one_mission(
            condition="D2", capability_pair=capability_pair, mission_index=mission_index, seed=seed,
            selector=selector, selector_capture=capture,
        )
        results.append(result)
    return tuple(results)


def run_e1_sequence(capability_pair: tuple[str, str], *, pair_index: int, store_path: Path) -> tuple[BenchmarkResult, ...]:
    """Five missions sharing one on-disk `ExperienceStore`, reopened fresh from disk *every* mission (stronger
    than V1.0 Step 6's own one-reopen proof): a real demonstration of persistence, never object reuse. Mission 1
    is a genuine cold start (the file does not exist yet); missions 2-5 read what came before."""
    results = []
    for mission_index in range(1, N_MISSIONS + 1):
        seed = _seed(pair_index, 3, mission_index)
        store = JsonlExperienceStore.open(store_path)
        assert isinstance(store, JsonlExperienceStore), store
        selector = ExperienceInformedSelector(store=store, fallback=DeterministicSelector())
        result, *_ = _run_one_mission(
            condition="E1", capability_pair=capability_pair, mission_index=mission_index, seed=seed,
            selector=selector, store=store,
        )
        results.append(result)
    return tuple(results)


def run_full_benchmark(store_dir: Path) -> tuple[BenchmarkResult, ...]:
    """All 3 capability pairs x 3 conditions x 5 missions = 45 mission executions (D-198 ruling 11). Each
    capability pair's own E1 sequence gets its own dedicated `ExperienceStore` file under `store_dir`, named by
    pair index — never shared across pairs or conditions, per the approved design's own isolation requirement."""
    results: list[BenchmarkResult] = []
    for pair_index, pair in enumerate(CAPABILITY_PAIRS):
        results.extend(run_d1_sequence(pair, pair_index=pair_index))
        results.extend(run_d2_sequence(pair, pair_index=pair_index))
        results.extend(run_e1_sequence(pair, pair_index=pair_index, store_path=store_dir / f"experience_pair{pair_index}.jsonl"))
    return tuple(results)


def report_table(results: tuple[BenchmarkResult, ...]) -> str:
    """A plain per-mission table (condition | pair | mission | selected_shape | outcome | verified |
    experience_available) — never a combined score, a win rate, or a ranking (D-198 ruling 11)."""
    header = (
        f"{'condition':<10} {'pair':<18} {'mission':<8} {'shape':<22} {'status':<10} "
        f"{'outcome':<9} {'verified':<9} {'history':<8} {'relevant':<9}"
    )
    lines = [header, "-" * len(header)]
    for r in results:
        shape = "/".join("+".join(stage) for stage in r.selected_strategy_shape)
        lines.append(
            f"{r.condition:<10} {'+'.join(r.capability_pair):<18} {r.mission_index:<8} {shape:<22} "
            f"{r.mission_status:<10} {str(r.run_outcome):<9} {str(r.verified):<9} "
            f"{str(r.history_available):<8} {r.relevant_history_count:<9}"
        )
    return "\n".join(lines)
