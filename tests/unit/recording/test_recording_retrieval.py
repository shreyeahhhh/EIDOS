"""Recording retrieval and citation facts: the adapter that maps a port's answer, the tracker's collections, the wrappers, the recorder's hand-off and a live recorded pass
(decisions.md D-204, D-218, D-225; V1.3 Step 4, phase A).

Nothing is retrieved by a scripted answer here except where a real lexical retriever is used on purpose. What is proven: an answer becomes exactly the facts it should, and one that does not
answer its request is recorded as malformed rather than dropped or trusted; the facts reach the right node's settlement in call order; a wrapper changes no result and no exception; and a run
that retrieves nothing records exactly what it always recorded.
"""

import inspect
import threading

import pytest

from eidos.agents import Artifact, WorkAgent
from eidos.contracts import ArtifactRef, CapabilityId, MissionEventType, PlanStepKind, StepId
from eidos.knowledge import (
    LEXICAL_SCHEME_ID,
    KnowledgePort,
    LexicalKnowledgePort,
    RetrievalFailure,
    RetrievalFailureKind,
    RetrievalRequest,
    RetrievalResult,
    build_snapshot,
    canonical_query_text,
)
from eidos.recording import (
    ModelCallTracker,
    Recorder,
    RecordingAgent,
    RecordingCitations,
    RecordingKnowledgePort,
    retrieval_facts_of,
)
from eidos.recording.run import _record_settled_nodes as record_settled_nodes
from eidos.runtime import NodeResult, NodeStatus, WorkResult
from eidos.state import (
    EventLog,
    NodeSettledPayload,
    NodeStartedPayload,
    PlanCompiledPayload,
    PlanGeneratedPayload,
    RetrievalOutcome,
    dump_jsonl,
    execution_record,
    load_jsonl,
    replay,
)

from eidos_agents_factories import compiled_with, node_of
from eidos_knowledge_factories import SCHEME, small_corpus
from eidos_recording_factories import FixedClock, SequentialIds, baseline_mission, new_rig, record, unrecorded
from eidos_retrieval_fact_factories import RetrievalFactsInjector, answer, failure
from eidos_runtime_factories import context_for
from eidos_state_factories import RESEARCH_AGENT, created
from eidos_v04_registry import RESEARCH_AGENT_ID

SNAPSHOT = build_snapshot(small_corpus(), SCHEME)
PORT = LexicalKnowledgePort(SNAPSHOT, kb_id="facility")


def request(text="inspection checklist before restart", **overrides) -> RetrievalRequest:
    fields = dict(
        kb_id="facility", snapshot_id=SNAPSHOT.snapshot_id, scheme_id=LEXICAL_SCHEME_ID, text=canonical_query_text(text), top_k=4, max_result_bytes=10**6
    ) | overrides
    return RetrievalRequest(**fields)


def settled_payload(log, step: str) -> NodeSettledPayload:
    return next(r.payload for r in log.records if r.event.type is MissionEventType.NODE_SETTLED and r.payload.result.step_id == step)


# --- what an answer becomes ---------------------------------------------------------------------------------------------------------------


def test_a_result_becomes_facts_that_carry_what_was_asked_and_what_was_answered():
    r = request()
    result = PORT.retrieve(r)
    facts = retrieval_facts_of(r, result, 7)
    assert (facts.kb_id, facts.snapshot_id, facts.scheme_id, facts.query_id, facts.top_k) == ("facility", SNAPSHOT.snapshot_id, LEXICAL_SCHEME_ID, r.query_id, 4)
    assert facts.outcome is RetrievalOutcome.RESULT and facts.score_kind == result.score_kind
    assert facts.result_bytes == result.result_bytes and facts.elapsed_ms == 7
    assert [(h.rank, h.chunk_id, h.document_id, h.source_id, h.content_digest, h.score) for h in facts.hits] == [
        (h.rank, h.chunk.chunk_id, h.chunk.document_id, h.chunk.source_id, h.content_digest, h.score) for h in result.hits
    ]


def test_an_empty_result_becomes_an_answer_with_no_hits():
    r = request("zzz qqq")
    facts = retrieval_facts_of(r, PORT.retrieve(r), 1)
    assert facts.outcome is RetrievalOutcome.RESULT and facts.hits == () and facts.result_bytes == 0


@pytest.mark.parametrize("kind", list(RetrievalFailureKind))
def test_a_failure_becomes_the_matching_outcome_and_carries_no_answer(kind):
    r = request()
    facts = retrieval_facts_of(r, RetrievalFailure(kind=kind, message="why"), 3)
    assert facts.outcome is RetrievalOutcome(kind.value) and facts.hits == () and facts.result_bytes is None and facts.elapsed_ms == 3
    assert facts.query_id == r.query_id  # a failure still says what was asked


def test_the_elapsed_time_may_be_absent_because_nobody_measured_it():
    assert retrieval_facts_of(request(), PORT.retrieve(request()), None).elapsed_ms is None


def like(ok: RetrievalResult, **changes) -> RetrievalResult:
    """A result with the fields of ``ok``, except those changed: a real answer made wrong in exactly one way."""
    fields = dict(query_id=ok.query_id, kb_id=ok.kb_id, snapshot_id=ok.snapshot_id, scheme_id=ok.scheme_id, score_kind=ok.score_kind, hits=ok.hits)
    return RetrievalResult(**(fields | changes))


MALFORMED = {
    "another query": lambda r, ok: like(ok, query_id="1" * 64),
    "another knowledge base": lambda r, ok: like(ok, kb_id="elsewhere"),
    "another snapshot": lambda r, ok: like(ok, snapshot_id="9" * 64),
    "another scheme": lambda r, ok: like(ok, scheme_id="other/x"),
    "more hits than top_k": lambda r, ok: like(ok, query_id=r.query_id),
    "not a result": lambda r, ok: "a string where a result should be",
    "nothing": lambda r, ok: None,
}


@pytest.mark.parametrize("name", sorted(MALFORMED))
def test_an_answer_that_does_not_answer_its_request_is_recorded_as_malformed_and_carries_nothing(name):
    r = request(top_k=1) if name == "more hits than top_k" else request()
    ok = PORT.retrieve(request())  # a real answer to a wider request: it has up to four hits
    assert len(ok.hits) >= 2
    facts = retrieval_facts_of(r, MALFORMED[name](r, ok), 5)
    assert facts.outcome is RetrievalOutcome.MALFORMED_RESULT and facts.hits == () and facts.result_bytes is None and facts.score_kind is None
    assert facts.elapsed_ms == 5  # the call was made and took its time, whatever came back
    assert (facts.query_id, facts.top_k, facts.kb_id) == (r.query_id, r.top_k, "facility")  # what was asked, never what was claimed


def test_a_result_over_the_byte_bound_is_recorded_as_malformed():
    ok = PORT.retrieve(request())
    tight = request(max_result_bytes=1)
    assert retrieval_facts_of(tight, like(ok, query_id=tight.query_id), 1).outcome is RetrievalOutcome.MALFORMED_RESULT


def test_a_port_that_itself_reports_a_malformed_result_is_recorded_as_one():
    facts = retrieval_facts_of(request(), RetrievalFailure(kind=RetrievalFailureKind.MALFORMED_RESULT, message="the index returned garbage"), 2)
    assert facts.outcome is RetrievalOutcome.MALFORMED_RESULT


def test_no_answer_however_wrong_makes_the_adapter_raise():
    ok = PORT.retrieve(request())
    for wrong in (None, 0, "x", b"y", object(), [], {}, ok.hits, RetrievalOutcome.RESULT):
        assert retrieval_facts_of(request(), wrong, 1).outcome is RetrievalOutcome.MALFORMED_RESULT


# --- the tracker's collections --------------------------------------------------------------------------------------------------------------


def test_the_tracker_collects_a_nodes_retrievals_in_call_order_and_hands_them_over_once():
    tracker = ModelCallTracker()
    facts = (answer(query=1), failure(RetrievalOutcome.UNAVAILABLE, query=2), answer(query=3))
    tracker.begin()
    for fact in facts:
        tracker.current_retrievals().append(fact)
    assert tracker.end_retrievals() == facts
    assert tracker.end_retrievals() == () and tracker.current_retrievals() is None


def test_the_tracker_collects_a_nodes_citations_the_same_way():
    tracker = ModelCallTracker()
    tracker.begin()
    tracker.current_citations().extend([ArtifactRef("evidence:0123456789abcdef"), ArtifactRef("doc:1")])
    assert tracker.end_citations() == ("evidence:0123456789abcdef", "doc:1")
    assert tracker.end_citations() == () and tracker.current_citations() is None


def test_a_retrieval_or_a_citation_outside_any_node_is_attributed_to_nothing():
    tracker = ModelCallTracker()
    assert tracker.current_retrievals() is None and tracker.current_citations() is None


def test_beginning_a_node_starts_every_collection_empty_and_discards_what_a_previous_node_left():
    tracker = ModelCallTracker()
    tracker.begin()
    tracker.current_retrievals().append(answer())
    tracker.current_citations().append(ArtifactRef("x"))
    tracker.begin()
    assert tracker.current_retrievals() == [] and tracker.current_citations() == [] and tracker.current() == [] and tracker.current_tool_calls() == []


def test_the_collections_are_independent_ending_one_leaves_the_others():
    tracker = ModelCallTracker()
    tracker.begin()
    tracker.current_retrievals().append(answer())
    tracker.current_citations().append(ArtifactRef("x"))
    assert tracker.end() == () and tracker.end_tool_calls() == ()  # the model calls and tool calls, exactly as always
    assert tracker.current_retrievals() == [answer()] and tracker.current_citations() == ["x"]
    assert tracker.end_retrievals() == (answer(),) and tracker.end_citations() == ("x",)


def test_each_thread_collects_only_its_own_nodes_retrievals_and_citations():
    tracker = ModelCallTracker()
    collected, barrier = {}, threading.Barrier(2)

    def node(name, facts, refs):
        tracker.begin()
        barrier.wait()
        tracker.current_retrievals().extend(facts)
        tracker.current_citations().extend(refs)
        barrier.wait()
        collected[name] = (tracker.end_retrievals(), tracker.end_citations())

    threads = [
        threading.Thread(target=node, args=("a", (answer(query=1),), (ArtifactRef("a1"),))),
        threading.Thread(target=node, args=("b", (failure(query=2), answer(query=3)), (ArtifactRef("b1"), ArtifactRef("b2")))),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert collected == {"a": ((answer(query=1),), ("a1",)), "b": ((failure(query=2), answer(query=3)), ("b1", "b2"))}


# --- the knowledge port wrapper ------------------------------------------------------------------------------------------------------------


class ScriptedPort:
    def __init__(self, outcome=None, error=None):
        self.outcome, self.error, self.requests = outcome, error, []

    def retrieve(self, request):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.outcome


def test_the_wrapper_returns_exactly_what_it_wrapped_and_notes_it_for_the_node_on_this_thread():
    tracker, clock = ModelCallTracker(), FixedClock()
    wrapped = RecordingKnowledgePort(PORT, tracker, clock)
    tracker.begin()
    r = request()
    result = wrapped.retrieve(r)
    assert result == PORT.retrieve(r)
    (fact,) = tracker.end_retrievals()
    assert fact == retrieval_facts_of(r, result, 1000)  # the fixed clock reads 1000 ms between the two readings around the call


def test_the_wrapper_passes_the_very_same_object_through():
    outcome = PORT.retrieve(request())
    tracker = ModelCallTracker()
    tracker.begin()
    assert RecordingKnowledgePort(ScriptedPort(outcome), tracker, FixedClock()).retrieve(request()) is outcome


def test_the_wrapper_passes_the_request_through_unchanged_and_calls_the_port_once():
    port, tracker = ScriptedPort(PORT.retrieve(request())), ModelCallTracker()
    tracker.begin()
    r = request()
    RecordingKnowledgePort(port, tracker, FixedClock()).retrieve(r)
    assert port.requests == [r] and port.requests[0] is r


def test_several_calls_are_noted_in_call_order_and_a_failure_is_noted_too():
    tracker, port = ModelCallTracker(), PORT
    wrapped = RecordingKnowledgePort(port, tracker, FixedClock())
    tracker.begin()
    first, second = request("inspection checklist"), request("sensors readings", kb_id="elsewhere")  # the second is a mismatch: the port refuses it
    wrapped.retrieve(first)
    wrapped.retrieve(second)
    a, b = tracker.end_retrievals()
    assert (a.outcome, b.outcome) == (RetrievalOutcome.RESULT, RetrievalOutcome.REQUEST_MISMATCH) and (a.query_id, b.query_id) == (first.query_id, second.query_id)


def test_an_exception_from_the_port_passes_through_untouched_and_records_nothing():
    error, tracker = RuntimeError("the index is on fire"), ModelCallTracker()
    tracker.begin()
    with pytest.raises(RuntimeError) as raised:
        RecordingKnowledgePort(ScriptedPort(error=error), tracker, FixedClock()).retrieve(request())
    assert raised.value is error and tracker.end_retrievals() == ()


def test_a_retrieval_made_outside_any_node_is_answered_and_attributed_to_nothing():
    tracker = ModelCallTracker()
    outcome = PORT.retrieve(request())
    assert RecordingKnowledgePort(ScriptedPort(outcome), tracker, FixedClock()).retrieve(request()) is outcome
    assert tracker.current_retrievals() is None


def test_a_malformed_answer_is_passed_through_untouched_and_noted_as_malformed():
    tracker = ModelCallTracker()
    tracker.begin()
    assert RecordingKnowledgePort(ScriptedPort("garbage"), tracker, FixedClock()).retrieve(request()) == "garbage"
    (fact,) = tracker.end_retrievals()
    assert fact.outcome is RetrievalOutcome.MALFORMED_RESULT


class SteppedClock:
    """A monotonic clock a test moves by hand, so an elapsed time is exactly what the test made pass between the two readings."""

    def __init__(self):
        self.now_ns = 10**9

    def monotonic_ns(self) -> int:
        return self.now_ns

    def advance_ms(self, milliseconds: int) -> None:
        self.now_ns += milliseconds * 1_000_000


class SlowPort:
    """A port that takes ``milliseconds`` of the stepped clock's time to answer."""

    def __init__(self, clock, milliseconds, outcome):
        self.clock, self.milliseconds, self.outcome = clock, milliseconds, outcome

    def retrieve(self, request):
        self.clock.advance_ms(self.milliseconds)
        return self.outcome


def test_the_elapsed_time_is_what_passed_between_the_two_readings_around_the_call():
    outcome = PORT.retrieve(request())
    for milliseconds in (0, 1, 250, 4321):
        clock, tracker = SteppedClock(), ModelCallTracker()
        tracker.begin()
        RecordingKnowledgePort(SlowPort(clock, milliseconds, outcome), tracker, clock).retrieve(request())
        (fact,) = tracker.end_retrievals()
        assert fact.elapsed_ms == milliseconds


def test_a_clock_that_runs_backwards_gives_no_negative_time_and_never_makes_the_wrapper_raise():
    class Backwards:
        def __init__(self):
            self.readings = iter([5_000_000_000, 1_000_000_000])

        def monotonic_ns(self):
            return next(self.readings)

    tracker = ModelCallTracker()
    tracker.begin()
    outcome = PORT.retrieve(request())
    assert RecordingKnowledgePort(ScriptedPort(outcome), tracker, Backwards()).retrieve(request()) is outcome
    (fact,) = tracker.end_retrievals()
    assert fact.elapsed_ms == 0


def test_a_node_settled_after_the_run_carries_the_retrievals_and_citations_noted_for_it():
    """A node the executor settles after the run (nothing settled it live) is recorded with what was observed while it ran: here a real run's report, and a recorder handed the facts."""
    state, plan = baseline_mission()
    report = unrecorded(state, plan)
    log = EventLog()
    recorder = Recorder(log=log, clock=FixedClock(), ids=SequentialIds(), tenant_id=state.tenant_id, mission_id=state.mission_id)
    recorder.record(created(state))
    recorder.record(PlanGeneratedPayload(plan=plan))
    recorder.record(PlanCompiledPayload(plan_id=plan.plan_id, plan_version=plan.version))
    facts = (answer(query=1), failure(query=2))
    recorder.note_retrievals(StepId("gather"), facts)
    recorder.note_citations(StepId("gather"), (ArtifactRef("doc:1"), ArtifactRef("evidence:0123456789abcdef")))
    record_settled_nodes(recorder, report)
    gather, analyse = settled_payload(log, "gather"), settled_payload(log, "analyse")
    assert gather.retrievals == facts and gather.citations == ("doc:1", "evidence:0123456789abcdef")
    assert analyse.retrievals == () and analyse.citations == ()
    assert recorder.refused == ()


def test_the_wrapper_is_a_knowledge_port():
    port: KnowledgePort = RecordingKnowledgePort(PORT, ModelCallTracker(), FixedClock())
    assert isinstance(port.retrieve(request()), RetrievalResult)


# --- the citation wrapper ----------------------------------------------------------------------------------------------------------------


class StoreWithOne:
    def __init__(self, artifact):
        self.artifact, self.reads = artifact, []

    def get(self, execution_id, ref):
        self.reads.append((execution_id, ref))
        return self.artifact if self.artifact is not None and ref == self.artifact.ref else None


class Producing:
    def __init__(self, result, error=None):
        self.result, self.error = result, error

    def run(self, context, node):
        if self.error is not None:
            raise self.error
        return self.result


def citation_setup():
    compiled = compiled_with({"a": ""})
    return context_for(compiled), node_of(compiled, StepId("a"))


def artifact_citing(*refs):
    return Artifact(ref=ArtifactRef("artifact:a"), content_type="text/plain", content="Findings.", source_refs=tuple(ArtifactRef(r) for r in refs))


def test_the_wrapper_notes_the_references_the_produced_artifact_cited_verbatim_and_in_order():
    context, node = citation_setup()
    tracker = ModelCallTracker()
    tracker.begin()
    produced = WorkResult.produced("artifact:a")
    store = StoreWithOne(artifact_citing("evidence:0123456789abcdef", "doc:1", "artifact:gather"))
    assert RecordingCitations(Producing(produced), tracker, store).run(context, node) is produced
    assert tracker.end_citations() == ("evidence:0123456789abcdef", "doc:1", "artifact:gather")
    assert store.reads == [(context.execution_id, ArtifactRef("artifact:a"))]


@pytest.mark.parametrize("result", [WorkResult.failed("nothing"), WorkResult.no_result("nothing"), WorkResult.submitted("elsewhere")], ids=["failed", "no_result", "submitted"])
def test_a_node_that_produced_no_artifact_adds_nothing_and_the_store_is_not_read(result):
    context, node = citation_setup()
    tracker, store = ModelCallTracker(), StoreWithOne(artifact_citing("doc:1"))
    tracker.begin()
    assert RecordingCitations(Producing(result), tracker, store).run(context, node) is result
    assert tracker.end_citations() == () and store.reads == []


def test_an_artifact_that_cited_nothing_adds_nothing():
    context, node = citation_setup()
    tracker = ModelCallTracker()
    tracker.begin()
    RecordingCitations(Producing(WorkResult.produced("artifact:a")), tracker, StoreWithOne(artifact_citing())).run(context, node)
    assert tracker.end_citations() == ()


def test_an_artifact_missing_from_the_store_adds_nothing_and_raises_nothing():
    context, node = citation_setup()
    tracker = ModelCallTracker()
    tracker.begin()
    RecordingCitations(Producing(WorkResult.produced("artifact:a")), tracker, StoreWithOne(None)).run(context, node)
    assert tracker.end_citations() == ()


def test_an_exception_from_the_agent_passes_through_untouched_and_the_store_is_not_read():
    context, node = citation_setup()
    error, tracker, store = RuntimeError("the agent gave up"), ModelCallTracker(), StoreWithOne(artifact_citing("doc:1"))
    tracker.begin()
    with pytest.raises(RuntimeError) as raised:
        RecordingCitations(Producing(None, error), tracker, store).run(context, node)
    assert raised.value is error and store.reads == [] and tracker.end_citations() == ()


def test_outside_any_node_nothing_is_collected_and_the_result_is_still_returned():
    context, node = citation_setup()
    tracker, store = ModelCallTracker(), StoreWithOne(artifact_citing("doc:1"))
    produced = WorkResult.produced("artifact:a")
    assert RecordingCitations(Producing(produced), tracker, store).run(context, node) is produced
    assert tracker.current_citations() is None


def test_the_wrapper_is_a_work_agent():
    agent: WorkAgent = RecordingCitations(Producing(WorkResult.produced("artifact:a")), ModelCallTracker(), StoreWithOne(None))
    assert callable(agent.run)


# --- the recorder's hand-off ------------------------------------------------------------------------------------------------------------


def open_recorder():
    state, plan = baseline_mission()
    log = EventLog()
    recorder = Recorder(log=log, clock=FixedClock(), ids=SequentialIds(), tenant_id=state.tenant_id, mission_id=state.mission_id)
    recorder.record(created(state))
    return state, plan, log, recorder


def test_a_node_settled_live_carries_the_retrievals_and_citations_the_recorder_was_handed_for_it():
    state, plan, log, recorder = open_recorder()
    recorder.record(PlanGeneratedPayload(plan=plan))
    recorder.record(PlanCompiledPayload(plan_id=plan.plan_id, plan_version=plan.version))
    recorder.record(NodeStartedPayload(plan_id=plan.plan_id, step_id=StepId("gather"), kind=PlanStepKind.AGENT, capability=CapabilityId("research"), agent_id=RESEARCH_AGENT))
    facts = (answer(query=1), failure(query=2))
    assert recorder.retrievals(StepId("gather")) == () and recorder.citations(StepId("gather")) == ()
    recorder.note_retrievals(StepId("gather"), facts)
    recorder.note_citations(StepId("gather"), (ArtifactRef("doc:1"), ArtifactRef("evidence:0123456789abcdef")))
    result = NodeResult(step_id=StepId("gather"), kind=PlanStepKind.AGENT, status=NodeStatus.SUCCEEDED, artifact=ArtifactRef("artifact:gather"))
    assert recorder.settle_live(plan.plan_id, result, 10, (), None).applied
    payload = settled_payload(log, "gather")
    assert payload.retrievals == facts and payload.citations == ("doc:1", "evidence:0123456789abcdef")
    assert recorder.retrievals(StepId("analyse")) == () and recorder.citations(StepId("analyse")) == ()


# --- the agent wrapper: exactly the recorder calls it always made, plus one only when there is something to say -----------------------


class Recording:
    """A recorder double that notes what it is asked. The hand-offs it offers decide which the wrapper may use: it must never be asked for one it lacks."""

    def __init__(self, *, retrievals: bool = False, citations: bool = False):
        self.calls, self._ticks = [], 0
        if retrievals:
            self.note_retrievals = lambda step_id, facts: self.calls.append(("retrievals", step_id, facts))
        if citations:
            self.note_citations = lambda step_id, refs: self.calls.append(("citations", step_id, refs))

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
        return [call[0] for call in self.calls]


class Inner:
    """A work agent that adds ``facts`` and ``refs`` through the tracker and returns ``result`` (or raises ``error``)."""

    def __init__(self, tracker, facts=(), refs=(), result=None, error=None):
        self.tracker, self.facts, self.refs, self.result, self.error = tracker, facts, refs, result, error

    def run(self, context, node):
        self.tracker.current_retrievals().extend(self.facts)
        self.tracker.current_citations().extend(self.refs)
        if self.error is not None:
            raise self.error
        return self.result


def wrapper_setup():
    compiled = compiled_with({"a": ""})
    return context_for(compiled), node_of(compiled, StepId("a"))


def test_a_node_that_retrieved_and_cited_nothing_makes_exactly_the_recorder_calls_it_always_made():
    context, node = wrapper_setup()
    recorder, tracker = Recording(), ModelCallTracker()  # a double with neither hand-off: it must never be asked for one
    RecordingAgent(RESEARCH_AGENT_ID, Inner(tracker, result=WorkResult.produced("artifact:a")), recorder, tracker).run(context, node)
    assert recorder.kinds() == ["record", "observe", "settle"]


def test_a_node_that_retrieved_and_cited_hands_both_over_before_it_is_observed_and_settled():
    context, node = wrapper_setup()
    recorder, tracker = Recording(retrievals=True, citations=True), ModelCallTracker()
    facts, refs = (answer(query=1), failure(query=2)), (ArtifactRef("doc:1"),)
    RecordingAgent(RESEARCH_AGENT_ID, Inner(tracker, facts, refs, WorkResult.produced("artifact:a")), recorder, tracker).run(context, node)
    assert recorder.kinds() == ["record", "retrievals", "citations", "observe", "settle"]
    assert recorder.calls[1][1:] == (node.step_id, facts) and recorder.calls[2][1:] == (node.step_id, refs)


def test_a_node_that_only_retrieved_hands_over_no_citations_and_the_reverse():
    context, node = wrapper_setup()
    tracker = ModelCallTracker()
    only_facts = Recording(retrievals=True)  # no citation hand-off: it would fail if asked
    RecordingAgent(RESEARCH_AGENT_ID, Inner(tracker, (answer(),), (), WorkResult.produced("artifact:a")), only_facts, tracker).run(context, node)
    assert only_facts.kinds() == ["record", "retrievals", "observe", "settle"]
    only_refs = Recording(citations=True)
    RecordingAgent(RESEARCH_AGENT_ID, Inner(tracker, (), (ArtifactRef("doc:1"),), WorkResult.produced("artifact:a")), only_refs, tracker).run(context, node)
    assert only_refs.kinds() == ["record", "citations", "observe", "settle"]


def test_an_agent_that_raises_after_retrieving_still_hands_the_facts_over_and_the_exception_passes_through_untouched():
    context, node = wrapper_setup()
    recorder, tracker, error = Recording(retrievals=True), ModelCallTracker(), RuntimeError("the agent gave up")
    facts = (answer(),)
    with pytest.raises(RuntimeError) as raised:
        RecordingAgent(RESEARCH_AGENT_ID, Inner(tracker, facts, (), error=error), recorder, tracker).run(context, node)
    assert raised.value is error
    assert recorder.kinds() == ["record", "retrievals", "observe"]  # nothing settled live: the executor's own FAILED result is recorded after the run
    assert recorder.calls[1][1:] == (node.step_id, facts) and tracker.current_retrievals() is None and tracker.current_citations() is None


def test_the_agent_wrappers_own_constructor_is_unchanged():
    assert list(inspect.signature(RecordingAgent.__init__).parameters) == ["self", "agent_id", "agent", "recorder", "tracker"]


# --- a live recorded pass over the real agents --------------------------------------------------------------------------------------------


GATHER = (answer(query=1, hits=(), top_k=4, result_bytes=0), failure(RetrievalOutcome.RESULT_TOO_LARGE, query=2))
ANALYSE = (answer(query=3),)


def run_with_retrievals(facts=None):
    state, plan = baseline_mission()
    rig = new_rig(state)
    rig.agents = {agent_id: RetrievalFactsInjector(agent, rig.tracker, facts or {"gather": GATHER, "analyse": ANALYSE}) for agent_id, agent in rig.agents.items()}
    run, _ = record(state, plan, rig)
    return state, plan, run


def test_the_recorded_pass_settles_each_node_with_the_retrievals_it_made_in_call_order():
    _, _, run = run_with_retrievals()
    assert settled_payload(run.log, "gather").retrievals == GATHER
    assert settled_payload(run.log, "analyse").retrievals == ANALYSE
    assert settled_payload(run.log, "check").retrievals == ()
    assert run.refused == () and run.discrepancies == ()


def test_replay_reproduces_the_state_and_every_retrieval_fact_from_the_log_alone():
    _, _, run = run_with_retrievals()
    assert replay(run.log.records).state == run.log.state
    steps = execution_record(run.log.records).steps
    assert [step.retrievals for step in steps] == [GATHER, ANALYSE, ()]
    reloaded = load_jsonl(dump_jsonl(run.log.records))
    assert reloaded.records == run.log.records and replay(reloaded.records).state == run.log.state


def test_the_recorded_pass_reports_exactly_what_the_same_pass_unrecorded_reports():
    state, plan, run = run_with_retrievals()
    assert run.report == unrecorded(state, plan)


def test_retrieval_facts_change_no_counter_and_no_other_fact_of_the_run():
    state, plan, run = run_with_retrievals()
    plain, _ = record(state, plan)
    for step in ("gather", "analyse", "check"):
        assert settled_payload(run.log, step).model_calls == settled_payload(plain.log, step).model_calls
        assert settled_payload(run.log, step).duration_ms == settled_payload(plain.log, step).duration_ms
    assert run.log.state == plain.log.state  # retrievals are not budgeted or counted: nothing in the mission state moves


def test_a_pass_that_retrieved_nothing_records_a_log_that_differs_from_before_only_by_the_empty_new_fields():
    state, plan = baseline_mission()
    run, _ = record(state, plan)
    text = dump_jsonl(run.log.records)
    assert text.count('"retrievals":[]') == 3 and text.count('"citations":[]') == 3 and '"hits"' not in text


def test_the_same_pass_twice_records_byte_identical_logs():
    _, _, first = run_with_retrievals()
    _, _, second = run_with_retrievals()
    assert dump_jsonl(first.log.records) == dump_jsonl(second.log.records)


def test_an_agent_that_raises_has_its_retrievals_recorded_with_the_settlement_the_executor_reports():
    state, plan = baseline_mission()
    rig = new_rig(state)
    facts = {"gather": (answer(query=1),)}
    rig.agents = {agent_id: RetrievalFactsInjector(agent, rig.tracker, facts, raise_after=RuntimeError("the agent failed")) for agent_id, agent in rig.agents.items()}
    run, _ = record(state, plan, rig)
    gather = settled_payload(run.log, "gather")
    assert gather.result.status is NodeStatus.FAILED and gather.dispatched and gather.retrievals == facts["gather"]
    assert run.discrepancies == () and replay(run.log.records).state == run.log.state


def test_a_node_that_never_ran_carries_no_retrievals_even_when_an_earlier_node_made_some():
    state, plan = baseline_mission()
    rig = new_rig(state)
    facts = {"gather": (answer(query=1),)}
    rig.agents = {agent_id: RetrievalFactsInjector(agent, rig.tracker, facts, raise_after=RuntimeError("the agent failed")) for agent_id, agent in rig.agents.items()}
    run, _ = record(state, plan, rig)
    for step in ("analyse", "check"):
        skipped = settled_payload(run.log, step)
        assert not skipped.dispatched and skipped.retrievals == () and skipped.citations == ()


def test_two_recorded_passes_do_not_share_retrieval_facts():
    state, plan = baseline_mission()
    first_rig, second_rig = new_rig(state), new_rig(state)
    for rig, facts in ((first_rig, {"gather": (answer(query=1),)}), (second_rig, {})):
        rig.agents = {agent_id: RetrievalFactsInjector(agent, rig.tracker, facts) for agent_id, agent in rig.agents.items()}
    first, _ = record(state, plan, first_rig)
    second, _ = record(state, plan, second_rig)
    assert settled_payload(first.log, "gather").retrievals == (answer(query=1),) and settled_payload(second.log, "gather").retrievals == ()


def test_the_real_agents_wrapped_with_the_citation_wrapper_record_what_their_artifacts_cited():
    state, plan = baseline_mission()
    rig = new_rig(state)
    rig.agents = {agent_id: RecordingCitations(agent, rig.tracker, rig.store) for agent_id, agent in rig.agents.items()}
    run, _ = record(state, plan, rig)
    assert settled_payload(run.log, "gather").citations == ("doc:1", "doc:2", "doc:3")  # what the scripted research answer cited
    assert settled_payload(run.log, "analyse").citations == ("artifact:gather", "doc:1")
    assert settled_payload(run.log, "check").citations == ()
    assert run.report == unrecorded(state, plan) and run.log.state.status == replay(run.log.records).state.status


def test_the_public_entry_points_keep_their_signatures():
    from eidos.recording import record_attempt, record_baseline

    assert list(inspect.signature(record_baseline).parameters) == [
        "state", "plan", "limits", "registry", "agents", "verifier", "admission_guard", "executor_factory", "clock", "ids", "prior", "log", "tracker",
    ]
    assert list(inspect.signature(record_attempt).parameters) == [
        "state", "plan", "limits", "registry", "agents", "verifier", "admission_guard", "executor_factory", "clock", "ids", "log", "prior", "tracker",
    ]
