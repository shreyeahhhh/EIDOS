"""Real-model tests: an explicit opt-in, excluded from the default run (decisions.md D-136).

These call a **real** local model runtime. They never run unless selected with ``-m real_model``, and when selected they never skip: if the
configuration is missing they **fail** and say what is missing. Nothing here is asserted about a model's quality or speed, because nothing
about either has been measured; the tests print what a real run measured so that it can be recorded from that run (CLAUDE.md section 7).

To run, after installing and starting the runtime yourself and pulling a model:

    set EIDOS_REAL_MODEL_URL=http://<host>:<port>
    set EIDOS_REAL_MODEL_NAME=<the model you pulled>
    set EIDOS_REAL_MODEL_TIMEOUT_SECONDS=<seconds to wait for one call>
    python -m pytest -m real_model -s tests/integration/providers/test_ollama_real.py

Every one of the three is required: there is no default endpoint, model or timeout (D-135). The generation parameters below are fixed here,
explicitly, and are part of what a recorded run reports.
"""

import json
import os
import threading

import pytest

from eidos.agents import (
    AnalysisAgent,
    GenerationParameters,
    InMemoryArtifactStore,
    ModelFailure,
    ModelRequest,
    ModelResponse,
    ModelSettings,
    ResearchAgent,
    VerificationAgent,
)
from eidos.backends.langgraph import LangGraphExecutor
from eidos.baseline import run_baseline
from eidos.providers import OllamaModel
from eidos.runtime import RunResult

from eidos_agents_factories import doc
from eidos_backend_factories import locked_admit_all
from eidos_scenario_factories import make_mission, make_mission_plan
from eidos_v04_factories import ANALYSIS_AGENT_ID, RESEARCH_AGENT_ID, make_registry
from eidos_validation_factories import make_system_limits

pytestmark = pytest.mark.real_model

REQUIRED = ("EIDOS_REAL_MODEL_URL", "EIDOS_REAL_MODEL_NAME", "EIDOS_REAL_MODEL_TIMEOUT_SECONDS")
GENERATION = GenerationParameters(temperature=0.0, seed=7, max_output_tokens=512)


def configuration() -> tuple[str, ModelSettings]:
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:  # never a skip: an opt-in that silently does nothing would look like a pass
        pytest.fail(
            f"real-model tests were selected but {', '.join(missing)} is not set. Install and start the runtime, pull a model, "
            "and set all of " + ", ".join(REQUIRED) + " (there are no defaults)."
        )
    settings = ModelSettings(
        model=os.environ["EIDOS_REAL_MODEL_NAME"],
        parameters=GENERATION,
        timeout_seconds=float(os.environ["EIDOS_REAL_MODEL_TIMEOUT_SECONDS"]),
    )
    return os.environ["EIDOS_REAL_MODEL_URL"], settings


class RecordingModel:
    """Wraps the real port and records every result, so a run can report what each call measured."""

    def __init__(self, inner):
        self.inner = inner
        self.results = []
        self._lock = threading.Lock()

    def complete(self, request):
        result = self.inner.complete(request)
        with self._lock:
            self.results.append(result)
        return result


def describe(result) -> dict:
    if isinstance(result, ModelResponse):
        return {"kind": "response", "characters": len(result.text), **result.measured.model_dump()}
    assert isinstance(result, ModelFailure)
    return {"kind": "failure", "failure": result.kind.value, "message": result.message}


def test_one_real_completion_returns_a_typed_result_and_reports_what_was_measured():
    url, settings = configuration()

    result = OllamaModel(base_url=url).complete(
        ModelRequest(settings=settings, prompt="Reply with the single word: ready.", system="Answer as briefly as you can.")
    )

    assert isinstance(result, (ModelResponse, ModelFailure))
    print("\nREAL COMPLETION:", json.dumps({"model": settings.model, "generation": GENERATION.model_dump(),
                                            "timeout_seconds": settings.timeout_seconds, **describe(result)}, indent=2))


def test_the_real_baseline_run_reports_what_it_measured():
    url, settings = configuration()
    state = make_mission(capabilities=("research", "cost"))
    plan = make_mission_plan(state, {"gather": "", "analyse": "gather", "check": "analyse"}, verify=("check",),
                             capability_of={"gather": "research", "analyse": "cost"})
    store = InMemoryArtifactStore()
    for n, text in enumerate(
        (
            "The application runs as a single process and stores its data in one relational database.",
            "Deployment is manual: an engineer copies a build to one server and restarts it.",
            "Nightly backups are written to the same disk as the database.",
        ),
        start=1,
    ):
        store.put_supplied(state.execution_id, doc(f"doc:{n}", text))
    model = RecordingModel(OllamaModel(base_url=url))

    report = run_baseline(
        state=state, plan=plan, limits=make_system_limits(), registry=make_registry(),
        agents={RESEARCH_AGENT_ID: ResearchAgent(model=model, settings=settings, store=store),
                ANALYSIS_AGENT_ID: AnalysisAgent(model=model, settings=settings, store=store)},
        verifier=VerificationAgent(store=store), admission_guard=locked_admit_all(), executor_factory=LangGraphExecutor,
    )

    # Structure only: a small model may or may not cite its sources, and whichever it does is what gets recorded.
    assert report.run is not None and isinstance(report.run, RunResult)
    summary = {
        "model": settings.model,
        "generation": GENERATION.model_dump(),
        "timeout_seconds": settings.timeout_seconds,
        "outcome": report.run.outcome.value,
        "verified": report.run.verified,
        "steps": {r.step_id: r.status.value for r in report.run.results},
        "verification_reason": report.run.result_for(report.run.results[-1].step_id).reason,
        "model_calls": [describe(r) for r in model.results],
    }
    print("\nREAL BASELINE RUN:", json.dumps(summary, indent=2))
