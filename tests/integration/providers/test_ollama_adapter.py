"""The local-runtime adapter against a local *fake* runtime over real sockets (decisions.md D-135, D-136).

No real model is involved, so nothing here says anything about a model's speed or quality; ``elapsed_seconds`` is only checked to be a
measured, non-negative number.
"""

import json
import socket
import threading
import time
import urllib.error

import pytest

from eidos.agents import (
    GenerationParameters,
    ModelFailure,
    ModelFailureKind,
    ModelRequest,
    ModelResponse,
    ModelSettings,
)
from eidos.providers import OllamaModel

from eidos_fake_runtime import (
    FakeRuntime,
    answers,
    closes_without_answering,
    free_port_with_nothing_listening,
    send_bytes,
    send_json,
    sends_a_truncated_body,
    sends_garbage,
    sleeps_then,
)


def request(**overrides) -> ModelRequest:
    settings = ModelSettings(
        model="a-test-model",
        parameters=GenerationParameters(temperature=0.25, seed=42, max_output_tokens=128),
        timeout_seconds=overrides.pop("timeout_seconds", 5.0),
    )
    fields = dict(settings=settings, prompt="Say hello.", system="Be brief.")
    fields.update(overrides)
    return ModelRequest(**fields)


# --- what is sent -------------------------------------------------------------------------------------------------------


def test_the_request_carries_exactly_the_explicit_settings_and_nothing_defaulted():
    with FakeRuntime(answers("hello")) as runtime:
        OllamaModel(base_url=runtime.url).complete(request())

    (path, headers, body), = runtime.requests
    assert path == "/api/generate"
    assert headers["content-type"] == "application/json"
    assert body == {
        "model": "a-test-model",
        "prompt": "Say hello.",
        "system": "Be brief.",
        "stream": False,
        "options": {"temperature": 0.25, "seed": 42, "num_predict": 128},
    }


def test_no_system_prompt_is_sent_when_none_was_given():
    with FakeRuntime(answers("hello")) as runtime:
        OllamaModel(base_url=runtime.url).complete(request(system=None))
    assert "system" not in runtime.requests[0][2]


def test_a_trailing_slash_on_the_base_url_is_harmless():
    with FakeRuntime(answers("hello")) as runtime:
        assert isinstance(OllamaModel(base_url=runtime.url + "/").complete(request()), ModelResponse)
    assert runtime.requests[0][0] == "/api/generate"


# --- what comes back ----------------------------------------------------------------------------------------------------


def test_a_good_answer_is_a_response_with_the_facts_the_provider_reported_and_a_measured_elapsed_time():
    with FakeRuntime(answers("Hello there.", prompt_eval_count=11, eval_count=4)) as runtime:
        result = OllamaModel(base_url=runtime.url).complete(request())

    assert isinstance(result, ModelResponse) and result.text == "Hello there."
    assert (result.measured.prompt_tokens, result.measured.output_tokens) == (11, 4)
    assert result.measured.elapsed_seconds is not None and result.measured.elapsed_seconds >= 0


def test_facts_the_provider_did_not_report_are_unknown_never_guessed():
    with FakeRuntime(answers("Hello.")) as runtime:
        result = OllamaModel(base_url=runtime.url).complete(request())
    assert (result.measured.prompt_tokens, result.measured.output_tokens) == (None, None)


@pytest.mark.parametrize("junk", [-1, True, "12", 1.5, None, [3]])
def test_a_token_count_that_is_not_a_count_is_treated_as_unreported(junk):
    with FakeRuntime(answers("Hello.", prompt_eval_count=junk, eval_count=junk)) as runtime:
        result = OllamaModel(base_url=runtime.url).complete(request())
    assert isinstance(result, ModelResponse)
    assert (result.measured.prompt_tokens, result.measured.output_tokens) == (None, None)


# --- every failure is a typed value, never raised ---------------------------------------------------------------------------


def failure_of(behavior, **kwargs) -> ModelFailure:
    with FakeRuntime(behavior) as runtime:
        result = OllamaModel(base_url=runtime.url).complete(request(**kwargs))
    assert isinstance(result, ModelFailure), result
    return result


def test_a_runtime_that_is_not_listening_is_unavailable():
    port = free_port_with_nothing_listening()
    result = OllamaModel(base_url=f"http://127.0.0.1:{port}").complete(request())
    assert isinstance(result, ModelFailure) and result.kind is ModelFailureKind.UNAVAILABLE
    assert "could not be reached" in result.message


@pytest.mark.parametrize("status", [400, 404, 500, 503])
def test_an_error_status_is_unavailable_and_names_the_status(status):
    failure = failure_of(lambda handler, body: send_json(handler, {"error": "no"}, status=status))
    assert failure.kind is ModelFailureKind.UNAVAILABLE and str(status) in failure.message


def test_a_call_that_outlasts_its_timeout_is_a_timeout_and_returns_promptly():
    started = time.monotonic()
    failure = failure_of(sleeps_then(3.0, answers("too late")), timeout_seconds=0.3)
    assert failure.kind is ModelFailureKind.TIMEOUT and "0.3" in failure.message
    assert time.monotonic() - started < 2.5  # it gave up at the timeout, it did not wait for the answer


def test_a_connection_dropped_without_an_answer_is_unavailable():
    failure = failure_of(closes_without_answering)
    assert failure.kind is ModelFailureKind.UNAVAILABLE


@pytest.mark.parametrize(
    "behavior",
    [
        lambda handler, body: send_bytes(handler, b"this is not json"),
        lambda handler, body: send_bytes(handler, b"\xff\xfe\x00"),
        lambda handler, body: send_json(handler, ["a", "list"]),
        lambda handler, body: send_json(handler, {"done": True}),
        lambda handler, body: send_json(handler, {"response": 42}),
        lambda handler, body: send_json(handler, {"response": None}),
        sends_garbage,
        sends_a_truncated_body,
    ],
    ids=["not json", "not utf-8", "a list", "no response field", "a numeric response", "a null response", "not http", "truncated"],
)
def test_an_answer_that_is_not_in_the_promised_shape_is_malformed(behavior):
    assert failure_of(behavior).kind is ModelFailureKind.MALFORMED_RESPONSE


@pytest.mark.parametrize("text", ["", "   ", "\n\t "])
def test_an_answer_with_no_text_is_empty_never_a_response(text):
    assert failure_of(answers(text)).kind is ModelFailureKind.EMPTY_RESPONSE


def test_the_port_never_raises_whatever_the_runtime_does():
    behaviors = [closes_without_answering, sends_garbage, sends_a_truncated_body, answers(""),
                 lambda handler, body: send_bytes(handler, b"{", status=200)]
    for behavior in behaviors:
        with FakeRuntime(behavior) as runtime:
            result = OllamaModel(base_url=runtime.url).complete(request(timeout_seconds=1.0))
        assert isinstance(result, (ModelResponse, ModelFailure))


# --- configuration is explicit and cannot reach a file or another protocol ----------------------------------------------------


def test_the_base_url_is_required_there_is_no_default_host_or_port():
    with pytest.raises(TypeError):
        OllamaModel()


@pytest.mark.parametrize("bad", ["", "localhost:11434", "ftp://host/", "file:///etc/passwd", "http://", "//host", "host"])
def test_only_an_http_or_https_url_with_a_host_is_accepted(bad):
    with pytest.raises(ValueError, match="base_url"):
        OllamaModel(base_url=bad)


def test_the_adapter_is_immutable():
    model = OllamaModel(base_url="http://127.0.0.1:1")
    with pytest.raises(AttributeError):
        model.base_url = "http://127.0.0.1:2"


# --- thread safety ------------------------------------------------------------------------------------------------------------


def test_concurrent_calls_all_get_their_own_answer():
    results = []
    lock = threading.Lock()
    with FakeRuntime(lambda handler, body: send_json(handler, {"response": f"echo {body['prompt']}", "done": True})) as runtime:
        model = OllamaModel(base_url=runtime.url)

        def call(n):
            found = model.complete(request(prompt=f"p{n}"))
            with lock:
                results.append(found)

        threads = [threading.Thread(target=call, args=(n,)) for n in range(16)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    assert sorted(r.text for r in results) == sorted(f"echo p{n}" for n in range(16))
    assert len(runtime.requests) == 16


# --- the adapter through the agents and the runner, on a fake runtime ---------------------------------------------------------------


def test_the_baseline_runs_end_to_end_through_the_adapter_on_both_backends_against_a_fake_runtime():
    from eidos.agents import AnalysisAgent, InMemoryArtifactStore, ResearchAgent, VerificationAgent
    from eidos.backends.langgraph import LangGraphExecutor
    from eidos.baseline import run_baseline
    from eidos.runtime import RunOutcome, SequentialExecutor

    from eidos_agents_factories import doc, make_settings
    from eidos_backend_factories import locked_admit_all
    from eidos_fake_runtime import answers_by_prompt
    from eidos_scenario_factories import make_mission, make_mission_plan
    from eidos_v04_factories import ANALYSIS_AGENT_ID, RESEARCH_AGENT_ID, make_registry
    from eidos_validation_factories import make_system_limits

    state = make_mission(capabilities=("research", "cost"))
    plan = make_mission_plan(state, {"gather": "", "analyse": "gather", "check": "analyse"}, verify=("check",),
                             capability_of={"gather": "research", "analyse": "cost"})
    reports = []
    with FakeRuntime(answers_by_prompt("Found [[doc:1]] [[doc:2]] [[doc:3]].", "Analysis [[artifact:gather]] [[doc:1]].")) as runtime:
        for executor in (SequentialExecutor, LangGraphExecutor):
            store = InMemoryArtifactStore()
            for n in (1, 2, 3):
                store.put_supplied(state.execution_id, doc(f"doc:{n}", f"Document {n}."))
            model = OllamaModel(base_url=runtime.url)
            reports.append(run_baseline(
                state=state, plan=plan, limits=make_system_limits(), registry=make_registry(),
                agents={RESEARCH_AGENT_ID: ResearchAgent(model=model, settings=make_settings(), store=store),
                        ANALYSIS_AGENT_ID: AnalysisAgent(model=model, settings=make_settings(), store=store)},
                verifier=VerificationAgent(store=store), admission_guard=locked_admit_all(), executor_factory=executor,
            ))

    assert reports[0] == reports[1] and reports[0].model_dump_json() == reports[1].model_dump_json()
    run = reports[0].run
    assert run.outcome is RunOutcome.FINISHED and run.verified is True
    assert len(runtime.requests) == 4  # research and analysis, once for each of the two executors
    assert {r[2]["model"] for r in runtime.requests} == {"test-model"}
    assert json.loads(reports[0].model_dump_json())["run"]["outcome"] == "finished"


# --- failures the fake runtime cannot produce portably (a connect that times out): the transport is faked instead ---------------------


@pytest.mark.parametrize(
    "raised, kind",
    [
        (lambda: urllib.error.URLError(TimeoutError("timed out")), ModelFailureKind.TIMEOUT),
        (lambda: urllib.error.URLError(socket.timeout("timed out")), ModelFailureKind.TIMEOUT),
        (lambda: urllib.error.URLError(ConnectionRefusedError("refused")), ModelFailureKind.UNAVAILABLE),
        (lambda: TimeoutError("read timed out"), ModelFailureKind.TIMEOUT),
        (lambda: ConnectionResetError("reset"), ModelFailureKind.UNAVAILABLE),
        (lambda: OSError("network is unreachable"), ModelFailureKind.UNAVAILABLE),
    ],
    ids=["connect timeout", "connect socket timeout", "connect refused", "read timeout", "reset", "unreachable"],
)
def test_transport_errors_map_to_the_failure_they_mean(monkeypatch, raised, kind):
    def urlopen(*args, **kwargs):
        raise raised()

    monkeypatch.setattr("eidos.providers.ollama.urllib.request.urlopen", urlopen)

    result = OllamaModel(base_url="http://127.0.0.1:9").complete(request())

    assert isinstance(result, ModelFailure) and result.kind is kind
