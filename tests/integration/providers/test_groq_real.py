"""Real-Groq tests: an explicit opt-in, excluded from the default run (decisions.md D-135, D-136; V1.6).

These call the **real**, hosted Groq API. They never run unless selected with ``-m groq``, and when
selected they never skip: if ``GROQ_API_KEY`` is missing they **fail** and say what is missing — an
opt-in that silently does nothing would look like a pass (CLAUDE.md section 6). Nothing here is asserted
about a model's quality or speed: this is a real-call smoke test, not a benchmark.

To run, after setting a real key:

    set GROQ_API_KEY=<your real key>
    python -m pytest -m groq -s tests/integration/providers/test_groq_real.py

The endpoint (``https://api.groq.com/openai/v1``) is Groq's one public API base, not per-deployer
configuration, so it is fixed here rather than read from another variable; the model is explicit and
required (``EIDOS_REAL_GROQ_MODEL``; no default, D-135) because which models an account may use varies.
"""

import json
import os

import pytest

from eidos.agents import GenerationParameters, ModelFailure, ModelRequest, ModelResponse, ModelSettings
from eidos.providers import GroqModel

pytestmark = pytest.mark.groq

BASE_URL = "https://api.groq.com/openai/v1"
GENERATION = GenerationParameters(temperature=0.0, seed=7, max_output_tokens=256)
TIMEOUT_SECONDS = 60.0


def configuration() -> tuple[str, ModelSettings]:
    api_key = os.environ.get("GROQ_API_KEY")
    model = os.environ.get("EIDOS_REAL_GROQ_MODEL")
    missing = [name for name, value in (("GROQ_API_KEY", api_key), ("EIDOS_REAL_GROQ_MODEL", model)) if not value]
    if missing:  # never a skip: an opt-in that silently does nothing would look like a pass
        pytest.fail(f"groq tests were selected but {', '.join(missing)} is not set (there are no defaults).")
    return api_key, ModelSettings(model=model, parameters=GENERATION, timeout_seconds=TIMEOUT_SECONDS)


def describe(result) -> dict:
    if isinstance(result, ModelResponse):
        return {"kind": "response", "characters": len(result.text), **result.measured.model_dump()}
    assert isinstance(result, ModelFailure)
    return {"kind": "failure", "failure": result.kind.value, "message": result.message}


def test_one_real_completion_returns_a_typed_result_and_reports_what_was_measured():
    api_key, settings = configuration()

    result = GroqModel(base_url=BASE_URL, api_key=api_key).complete(
        ModelRequest(settings=settings, prompt="Reply with the single word: ready.", system="Answer as briefly as you can.")
    )

    assert isinstance(result, (ModelResponse, ModelFailure))
    print("\nREAL GROQ COMPLETION:", json.dumps({"model": settings.model, "generation": GENERATION.model_dump(),
                                                  "timeout_seconds": settings.timeout_seconds, **describe(result)}, indent=2))


def test_a_bad_api_key_is_a_typed_unavailable_failure_never_raised():
    _, settings = configuration()

    result = GroqModel(base_url=BASE_URL, api_key="not-a-real-key-obviously-wrong").complete(
        ModelRequest(settings=settings, prompt="Reply with the single word: ready.")
    )

    assert isinstance(result, ModelFailure)
    print("\nREAL GROQ BAD-KEY RESULT:", json.dumps(describe(result), indent=2))
