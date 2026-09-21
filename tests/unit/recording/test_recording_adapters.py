"""The recording wrappers: the model port, the work agent and the verifier (decisions.md D-158 item 1; V0.5 Step 5b).

Each wrapper returns exactly what it wraps, changes no exception, and observes. These tests drive them against a stub recorder, so they
say nothing about a log: they pin what each wrapper sends the recorder, in what order, and that nothing about the pass is altered.
"""

import threading

import pytest

from eidos.agents import MeasuredFacts, ModelFailure, ModelFailureKind, ModelResponse
from eidos.contracts import PlanStepKind, StepId
from eidos.recording import ModelCallTracker, RecordingAgent, RecordingModel, RecordingVerifier, facts_of
from eidos.recording.adapters import node_result_of_verification, node_result_of_work
from eidos.runtime import NodeResult, NodeStatus, SequentialExecutor, VerificationResult, WorkResult
from eidos.state import ModelCallFacts, ModelCallOutcome, NodeSettledPayload, NodeStartedPayload

from eidos_agents_factories import compiled_with, node_of
from eidos_runtime_factories import admit_all, context_for
from eidos_state_factories import RESEARCH_AGENT


class StubRecorder:
    """Notes what it is asked and measures time with a counter: each reading is one second after the last."""

    def __init__(self):
        self.calls, self._ticks = [], 0

    def record(self, payload):
        self.calls.append(("record", payload))

    def monotonic_ns(self):
        self._ticks += 1
        return self._ticks * 1_000_000_000

    def duration_ms(self, started):
        return (self.monotonic_ns() - started) // 1_000_000

    def note_observation(self, step_id, duration_ms, calls):
        self.calls.append(("observe", step_id, duration_ms, calls))

    def settle_live(self, plan_id, result, duration_ms, calls, verification):
        self.calls.append(("settle", result, duration_ms, calls, verification))

    def kinds(self):
        return [c[0] for c in self.calls]


class Scripted:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.seen = result, error, []

    def complete(self, request):
        self.seen.append(request)
        if self.error is not None:
            raise self.error
        return self.result


# --- the model wrapper -------------------------------------------------------------------------------------------------------------


def test_a_response_is_recorded_with_exactly_the_facts_the_provider_reported_and_none_is_made_up():
    full = ModelResponse(text="x", measured=MeasuredFacts(prompt_tokens=10, output_tokens=20, elapsed_seconds=1.5))
    assert facts_of(full) == ModelCallFacts(outcome=ModelCallOutcome.RESPONSE, prompt_tokens=10, output_tokens=20, elapsed_seconds=1.5)
    assert facts_of(ModelResponse(text="x")) == ModelCallFacts(outcome=ModelCallOutcome.RESPONSE)  # nothing reported: every fact stays None
    partial = ModelResponse(text="x", measured=MeasuredFacts(prompt_tokens=7))
    assert facts_of(partial) == ModelCallFacts(outcome=ModelCallOutcome.RESPONSE, prompt_tokens=7)


@pytest.mark.parametrize("kind", list(ModelFailureKind), ids=lambda k: k.value)
def test_a_typed_failure_is_recorded_as_the_same_named_outcome_with_no_provider_facts(kind):
    assert facts_of(ModelFailure(kind=kind, message="no")) == ModelCallFacts(outcome=ModelCallOutcome(kind.value))


def test_anything_that_is_neither_a_response_nor_a_typed_failure_is_not_recorded_as_a_call():
    assert facts_of("a string a broken port returned") is None  # type: ignore[arg-type]


def test_the_model_wrapper_returns_the_very_object_the_port_returned_and_records_it_only_inside_a_node():
    response = ModelResponse(text="x", measured=MeasuredFacts(prompt_tokens=1, output_tokens=2))
    tracker = ModelCallTracker()
    model = RecordingModel(Scripted(response), tracker)
    assert model.complete("outside a node") is response  # type: ignore[arg-type]
    assert tracker.current() is None  # a call outside any node is attributed to nothing
    tracker.begin()
    assert model.complete("inside") is response  # type: ignore[arg-type]
    assert model.complete("inside again") is response  # type: ignore[arg-type]
    assert tracker.end() == (facts_of(response), facts_of(response))
    assert tracker.end() == ()  # ended: nothing is carried into the next node


def test_a_port_that_raises_passes_its_exception_through_untouched_and_records_no_call():
    error = TimeoutError("the socket gave up")
    tracker = ModelCallTracker()
    model = RecordingModel(Scripted(error=error), tracker)
    tracker.begin()
    with pytest.raises(TimeoutError) as raised:
        model.complete("x")  # type: ignore[arg-type]
    assert raised.value is error
    assert tracker.end() == ()


def test_each_thread_collects_only_its_own_nodes_calls():
    tracker = ModelCallTracker()
    ok = ModelResponse(text="x", measured=MeasuredFacts(prompt_tokens=1))
    bad = ModelFailure(kind=ModelFailureKind.TIMEOUT, message="no")
    models = {"a": RecordingModel(Scripted(ok), tracker), "b": RecordingModel(Scripted(bad), tracker)}
    collected, barrier = {}, threading.Barrier(2)

    def node(name, calls):
        tracker.begin()
        barrier.wait()  # both threads are inside a node at once
        for _ in range(calls):
            models[name].complete("x")  # type: ignore[arg-type]
        barrier.wait()
        collected[name] = tracker.end()

    threads = [threading.Thread(target=node, args=("a", 3)), threading.Thread(target=node, args=("b", 2))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert [c.outcome for c in collected["a"]] == [ModelCallOutcome.RESPONSE] * 3
    assert [c.outcome for c in collected["b"]] == [ModelCallOutcome.TIMEOUT] * 2


# --- the agent wrapper -------------------------------------------------------------------------------------------------------------


def work_setup():
    compiled = compiled_with({"a": ""})
    return context_for(compiled), node_of(compiled, StepId("a"))


class Agent:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error

    def run(self, context, node):
        if self.error is not None:
            raise self.error
        return self.result


def test_the_agent_wrapper_records_started_then_settled_and_returns_the_very_result_the_agent_returned():
    context, node = work_setup()
    result = WorkResult.produced("artifact:a")
    recorder, tracker = StubRecorder(), ModelCallTracker()
    returned = RecordingAgent(RESEARCH_AGENT, Agent(result), recorder, tracker).run(context, node)
    assert returned is result
    assert recorder.kinds() == ["record", "observe", "settle"]  # started, observed, settled: in that order
    started = recorder.calls[0][1]
    assert isinstance(started, NodeStartedPayload)
    assert (started.plan_id, started.step_id, started.kind, started.capability, started.agent_id) == (
        context.plan_id, node.step_id, PlanStepKind.AGENT, node.capability, RESEARCH_AGENT)
    _, live, duration_ms, calls, verification = recorder.calls[2]
    assert live == NodeResult(step_id=node.step_id, kind=PlanStepKind.AGENT, status=NodeStatus.SUCCEEDED, artifact="artifact:a")
    assert duration_ms == 1000 and calls == () and verification is None  # one counter step between the two readings


def test_the_agent_wrapper_attributes_the_calls_made_during_the_run_to_that_node():
    context, node = work_setup()
    recorder, tracker = StubRecorder(), ModelCallTracker()
    model = RecordingModel(Scripted(ModelResponse(text="x", measured=MeasuredFacts(prompt_tokens=3, output_tokens=4))), tracker)

    class CallsTheModel:
        def run(self, context, node):
            model.complete("prompt")  # type: ignore[arg-type]
            model.complete("prompt")  # type: ignore[arg-type]
            return WorkResult.produced("artifact:a")

    RecordingAgent(RESEARCH_AGENT, CallsTheModel(), recorder, tracker).run(context, node)
    calls = recorder.calls[-1][3]
    assert calls == (ModelCallFacts(outcome=ModelCallOutcome.RESPONSE, prompt_tokens=3, output_tokens=4),) * 2
    assert tracker.current() is None  # the collector is closed once the node is done


def test_an_agent_that_raises_has_its_exception_pass_unchanged_and_is_observed_but_not_settled_live():
    context, node = work_setup()
    error = RuntimeError("boom")
    recorder = StubRecorder()
    with pytest.raises(RuntimeError) as raised:
        RecordingAgent(RESEARCH_AGENT, Agent(error=error), recorder, ModelCallTracker()).run(context, node)
    assert raised.value is error
    assert recorder.kinds() == ["record", "observe"]  # the executor's own FAILED result is recorded after the run
    assert recorder.calls[1][1:3] == (node.step_id, 1000)


def test_a_result_that_is_not_a_work_result_is_returned_as_is_and_not_settled_live():
    context, node = work_setup()
    recorder = StubRecorder()
    garbage = "not a WorkResult"
    assert RecordingAgent(RESEARCH_AGENT, Agent(garbage), recorder, ModelCallTracker()).run(context, node) is garbage  # type: ignore[arg-type]
    assert recorder.kinds() == ["record", "observe"]


# --- the verifier wrapper ----------------------------------------------------------------------------------------------------------


def verify_setup():
    compiled = compiled_with({"a": "", "check": "a"}, verify=("check",))
    return context_for(compiled), node_of(compiled, StepId("check")), node_of(compiled, StepId("a"))


class Verifying:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error

    def verify(self, context, node, predecessors):
        if self.error is not None:
            raise self.error
        return self.result


def test_the_verifier_wrapper_records_the_start_and_the_verdict_and_returns_the_very_result():
    context, node, _ = verify_setup()
    result = VerificationResult.failed("a rule was violated")
    recorder = StubRecorder()
    assert RecordingVerifier(Verifying(result), recorder).verify(context, node, ()) is result
    assert recorder.kinds() == ["record", "observe", "settle"]
    started = recorder.calls[0][1]
    assert (started.kind, started.capability, started.agent_id) == (PlanStepKind.VERIFY, None, None)
    _, live, duration_ms, calls, verification = recorder.calls[2]
    assert live.status is NodeStatus.VERIFICATION_FAILED and live.reason == "a rule was violated"
    assert (verification.verdict, verification.reason) == (result.verdict, "a rule was violated") and calls == () and duration_ms == 1000


def test_a_verifier_that_raises_has_its_exception_pass_unchanged_and_a_non_result_is_not_settled_live():
    context, node, _ = verify_setup()
    error = ValueError("the verifier broke")
    recorder = StubRecorder()
    with pytest.raises(ValueError) as raised:
        RecordingVerifier(Verifying(error=error), recorder).verify(context, node, ())
    assert raised.value is error and recorder.kinds() == ["record", "observe"]
    recorder = StubRecorder()
    assert RecordingVerifier(Verifying("nope"), recorder).verify(context, node, ()) == "nope"  # type: ignore[arg-type]
    assert recorder.kinds() == ["record", "observe"]


# --- the restated mapping is the runtime's own ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("work", [WorkResult.produced("artifact:a"), WorkResult.failed("boom"), WorkResult.no_result("nothing")], ids=["produced", "failed", "no_result"])
def test_the_restated_work_mapping_gives_exactly_the_node_result_the_executor_gives(work):
    compiled = compiled_with({"a": "", "check": "a"}, verify=("check",))

    class Work:
        def execute(self, context, node):
            return work

    executor = SequentialExecutor(work_executor=Work(), verifier=Verifying(VerificationResult.passed("ok")), admission_guard=admit_all())
    run = executor.run(compiled, context_for(compiled))
    assert run.result_for(StepId("a")) == node_result_of_work(node_of(compiled, StepId("a")), work)


@pytest.mark.parametrize("verdict", [VerificationResult.passed("ok"), VerificationResult.failed("no"), VerificationResult.inconclusive("unsure")],
                         ids=["pass", "fail", "inconclusive"])
def test_the_restated_verdict_mapping_gives_exactly_the_node_result_the_executor_gives(verdict):
    compiled = compiled_with({"a": "", "check": "a"}, verify=("check",))

    class Work:
        def execute(self, context, node):
            return WorkResult.produced("artifact:a")

    executor = SequentialExecutor(work_executor=Work(), verifier=Verifying(verdict), admission_guard=admit_all())
    run = executor.run(compiled, context_for(compiled))
    assert run.result_for(StepId("check")) == node_result_of_verification(node_of(compiled, StepId("check")), verdict)


def test_a_live_settlement_payload_can_be_built_for_every_status_the_mapping_produces():
    for work in (WorkResult.produced("artifact:a"), WorkResult.failed("boom"), WorkResult.no_result("nothing")):
        compiled = compiled_with({"a": ""})
        result = node_result_of_work(node_of(compiled, StepId("a")), work)
        NodeSettledPayload(plan_id=compiled.plan_id, result=result, dispatched=True, duration_ms=1, model_calls=())
