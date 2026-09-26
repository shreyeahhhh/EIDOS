"""The knowledge gate: bounds, duplicates, checked answers, and evidence that enters the ledger and the store (decisions.md D-208, D-216, D-217, D-225, D-228; V1.3 Step 7).

Real gate, real ledger, real artifact store and, where the answer matters, the real exact lexical retriever over a real snapshot; a scripted port where a test needs to say exactly what
came back, wrongly or not at all. What is proven: the request is built from the knowledge base's own bounds and nothing else; a duplicate is served without asking; every answer is
checked and a bad one is a typed failure that stores and records nothing; each hit becomes one ledger record and one citable artifact under its evidence reference; the same chunk from two
queries is one record with both query ids and one artifact; an executions' evidence never mixes with another's; and the gate never raises for a retrieval outcome.
"""

import threading
import unicodedata

import pytest
from pydantic import ValidationError

from eidos.agents import (
    EVIDENCE_CONTENT_TYPE,
    Artifact,
    EvidenceLedger,
    InMemoryArtifactStore,
    KnowledgeGate,
    KnowledgeGateKind,
    KnowledgeGateOutcome,
)
from eidos.contracts import ArtifactRef
from eidos.knowledge import (
    LEXICAL_SCHEME_ID,
    LexicalKnowledgePort,
    RetrievalFailure,
    RetrievalFailureKind,
    RetrievalRequest,
    RetrievalResult,
    build_snapshot,
    canonical_query_text,
    evidence_from_snapshot,
    query_id_of,
)

from eidos_knowledge_factories import SCHEME, doc, small_corpus
from eidos_knowledge_gate_fixture import (
    GOAL,
    KB,
    SECOND_GOAL,
    SNAPSHOT,
    ScriptedKnowledgePort,
    answer_with,
    attempt_context,
    descriptor_for,
    failing_port,
    make_rag_mission,
)

STATE = make_rag_mission()
OTHER_STATE = make_rag_mission(seed=2)
CONTEXT = attempt_context(STATE)
CHUNKS = {chunk.text: chunk for chunk in SNAPSHOT.chunks}
FIRST, SECOND, THIRD = SNAPSHOT.chunks[5], SNAPSHOT.chunks[9], SNAPSHOT.chunks[4]


def build(port=None, *, descriptor=None, store=None, ledger=None):
    descriptor = descriptor or descriptor_for()
    port = port if port is not None else LexicalKnowledgePort(SNAPSHOT, kb_id=KB)
    counted = port if isinstance(port, ScriptedKnowledgePort) else ScriptedKnowledgePort(port.retrieve)
    store = store or InMemoryArtifactStore()
    ledger = ledger or EvidenceLedger()
    return KnowledgeGate(descriptor=descriptor, port=counted, ledger=ledger, store=store), counted, ledger, store


def scripted(*chunks):
    return ScriptedKnowledgePort(lambda request: answer_with(request, tuple(chunks)))


# --- the knowledge base ----------------------------------------------------------------------------------------------------------


def test_a_descriptor_holds_the_knowledge_base_its_snapshot_its_scheme_and_its_two_bounds():
    descriptor = descriptor_for(top_k=3, max_result_bytes=999)
    assert (descriptor.kb_id, descriptor.snapshot, descriptor.scheme_id, descriptor.top_k, descriptor.max_result_bytes) == (KB, SNAPSHOT, LEXICAL_SCHEME_ID, 3, 999)


@pytest.mark.parametrize(
    "change",
    [{"kb_id": "Not A Source Id"}, {"scheme_id": "not a scheme id"}, {"scheme_id": ""}, {"top_k": 0}, {"max_result_bytes": 0}, {"top_k": -1}],
)
def test_a_descriptor_from_which_no_request_can_be_made_is_refused(change):
    with pytest.raises(ValidationError):
        descriptor_for(**change)


def test_a_descriptor_accepts_the_smallest_bounds():
    assert descriptor_for(top_k=1, max_result_bytes=1).top_k == 1


# --- the request the gate makes ---------------------------------------------------------------------------------------------------


def test_the_request_is_built_from_the_knowledge_bases_own_bounds_snapshot_and_scheme_and_the_canonical_query():
    gate, port, _, _ = build(scripted(FIRST), descriptor=descriptor_for(top_k=3, max_result_bytes=777))
    outcome = gate.retrieve(CONTEXT, "  " + GOAL + "\r\n")
    (request,) = port.requests
    assert request == RetrievalRequest(kb_id=KB, snapshot_id=SNAPSHOT.snapshot_id, scheme_id=LEXICAL_SCHEME_ID, text=GOAL, top_k=3, max_result_bytes=777)
    assert outcome.query_id == request.query_id == query_id_of(kb_id=KB, snapshot_id=SNAPSHOT.snapshot_id, scheme_id=LEXICAL_SCHEME_ID, text=GOAL, top_k=3)


def test_two_spellings_of_one_query_are_one_query():
    decomposed = "cafe" + chr(0x301)
    precomposed = unicodedata.normalize("NFC", decomposed)
    gate, port, _, _ = build(scripted())
    first = gate.retrieve(CONTEXT, decomposed)
    second = gate.retrieve(CONTEXT, "  " + precomposed + chr(13) + chr(10))
    assert first.query_id == second.query_id and second.kind is KnowledgeGateKind.SERVED
    assert [request.text for request in port.requests] == [canonical_query_text(precomposed)]


@pytest.mark.parametrize("query", ["", "   ", chr(13) + chr(10), chr(9) + chr(0xA0)])
def test_an_empty_query_is_a_programming_error_and_the_port_is_never_asked(query):
    gate, port, _, _ = build(scripted(FIRST))
    with pytest.raises(ValueError, match="not empty"):
        gate.retrieve(CONTEXT, query)
    assert port.calls == 0


def test_the_gate_exposes_the_descriptor_it_serves():
    descriptor = descriptor_for()
    gate, _, _, _ = build(scripted(), descriptor=descriptor)
    assert gate.descriptor is descriptor


# --- an answer becomes evidence ---------------------------------------------------------------------------------------------------


def test_each_hit_becomes_a_supplied_artifact_under_its_evidence_reference_and_a_record_in_the_ledger():
    assert EVIDENCE_CONTENT_TYPE == "text/plain"
    gate, port, ledger, store = build()
    outcome = gate.retrieve(CONTEXT, GOAL)
    assert outcome.kind is KnowledgeGateKind.RETRIEVED and isinstance(outcome.result, RetrievalResult) and not outcome.failed
    assert [str(ref) for ref in outcome.refs] == [hit.evidence_ref for hit in outcome.result.hits] and len(outcome.refs) == 4
    supplied = {artifact.ref: artifact for artifact in store.supplied(STATE.execution_id)}
    assert set(supplied) == set(outcome.refs)
    for hit in outcome.result.hits:
        artifact = supplied[ArtifactRef(hit.evidence_ref)]
        assert (artifact.content, artifact.content_type, artifact.source_refs) == (hit.chunk.text, "text/plain", ())
        record = ledger.get(STATE.execution_id, hit.evidence_ref)
        assert record.chunk == hit.chunk and record.snapshot_id == SNAPSHOT.snapshot_id and record.retrieved_by == (outcome.query_id,)
        assert record == evidence_from_snapshot(SNAPSHOT, hit.chunk.chunk_id, query_id=outcome.query_id)
    assert [record.evidence_ref for record in ledger.records(STATE.execution_id)] == sorted(hit.evidence_ref for hit in outcome.result.hits)


def test_an_answer_with_no_hits_is_a_real_answer_that_stores_and_records_nothing_and_is_served_when_repeated():
    gate, port, ledger, store = build(scripted())
    first = gate.retrieve(CONTEXT, GOAL)
    assert first.kind is KnowledgeGateKind.RETRIEVED and first.refs == () and not first.failed
    assert first.explanation == "the knowledge base returned no evidence" and not first.did_not_complete
    assert store.supplied(STATE.execution_id) == () and ledger.records(STATE.execution_id) == ()
    assert gate.retrieve(CONTEXT, GOAL).kind is KnowledgeGateKind.SERVED and port.calls == 1


# --- a duplicate ------------------------------------------------------------------------------------------------------------------


def test_the_same_query_again_in_an_execution_is_served_from_storage_without_asking_the_port_or_changing_anything():
    gate, port, ledger, store = build()
    first = gate.retrieve(CONTEXT, GOAL)
    held = (ledger.records(STATE.execution_id), store.supplied(STATE.execution_id))
    second = gate.retrieve(attempt_context(STATE, 2), GOAL)  # another plan attempt of the same execution
    assert second.kind is KnowledgeGateKind.SERVED and (second.query_id, second.result, second.refs) == (first.query_id, first.result, first.refs)
    assert port.calls == 1 and (ledger.records(STATE.execution_id), store.supplied(STATE.execution_id)) == held


def test_another_execution_asks_again_and_its_evidence_is_its_own():
    gate, port, ledger, store = build()
    first = gate.retrieve(CONTEXT, GOAL)
    second = gate.retrieve(attempt_context(OTHER_STATE), GOAL)
    assert second.kind is KnowledgeGateKind.RETRIEVED and port.calls == 2 and second.refs == first.refs
    assert len(store.supplied(STATE.execution_id)) == len(store.supplied(OTHER_STATE.execution_id)) == 4
    assert all(record.retrieved_by == (first.query_id,) for record in ledger.records(OTHER_STATE.execution_id))


def test_a_different_query_is_asked_and_keeps_its_own_identity():
    gate, port, _, _ = build()
    first, second = gate.retrieve(CONTEXT, GOAL), gate.retrieve(CONTEXT, SECOND_GOAL)
    assert second.kind is KnowledgeGateKind.RETRIEVED and port.calls == 2 and first.query_id != second.query_id


def test_the_same_chunk_retrieved_by_two_queries_is_one_record_with_both_query_ids_and_one_artifact():
    gate, port, ledger, store = build(ScriptedKnowledgePort(lambda request: answer_with(request, (FIRST, SECOND) if request.text == GOAL else (SECOND, THIRD))))
    a, b = gate.retrieve(CONTEXT, GOAL), gate.retrieve(CONTEXT, SECOND_GOAL)
    assert a.refs[1] == b.refs[0]  # the shared chunk
    shared = ledger.get(STATE.execution_id, str(a.refs[1]))
    assert shared.retrieved_by == tuple(sorted((a.query_id, b.query_id)))
    assert len(ledger.records(STATE.execution_id)) == 3 and len(store.supplied(STATE.execution_id)) == 3


def test_concurrent_nodes_asking_the_same_query_ask_the_port_once_and_all_get_the_same_evidence():
    gate, port, ledger, store = build()
    outcomes, errors = [], []

    def ask():
        try:
            outcomes.append(gate.retrieve(CONTEXT, GOAL))
        except Exception as error:  # pragma: no cover - reported below
            errors.append(error)

    threads = [threading.Thread(target=ask) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors and port.calls == 1
    assert sorted(outcome.kind.value for outcome in outcomes) == ["retrieved"] + ["served"] * 11
    assert len({outcome.refs for outcome in outcomes}) == 1 and len(store.supplied(STATE.execution_id)) == 4


# --- a failure --------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", list(RetrievalFailureKind))
def test_every_failure_of_the_port_is_a_typed_outcome_with_no_evidence(kind):
    gate, port, ledger, store = build(failing_port(kind, "scripted failure"))
    outcome = gate.retrieve(CONTEXT, GOAL)
    assert outcome.failed and outcome.refs == () and outcome.result == RetrievalFailure(kind=kind, message="scripted failure") and outcome.kind is KnowledgeGateKind.RETRIEVED
    assert outcome.did_not_complete is (kind is RetrievalFailureKind.UNAVAILABLE)
    assert outcome.explanation == f"the knowledge retrieval failed ({kind.value}): scripted failure"
    assert store.supplied(STATE.execution_id) == () and ledger.records(STATE.execution_id) == ()


def test_a_failed_retrieval_is_not_stored_so_a_repeat_asks_the_port_again():
    answers = [RetrievalFailure(kind=RetrievalFailureKind.UNAVAILABLE, message="down"), None]
    gate, port, ledger, store = build(ScriptedKnowledgePort(lambda request: answers.pop(0) or answer_with(request, (FIRST,))))
    assert gate.retrieve(CONTEXT, GOAL).failed
    second = gate.retrieve(CONTEXT, GOAL)
    assert not second.failed and second.kind is KnowledgeGateKind.RETRIEVED and port.calls == 2 and len(store.supplied(STATE.execution_id)) == 1


def test_a_result_that_is_too_large_for_the_bound_is_the_typed_failure_and_nothing_is_stored():
    gate, port, ledger, store = build(descriptor=descriptor_for(top_k=4, max_result_bytes=20))
    outcome = gate.retrieve(CONTEXT, GOAL)
    assert outcome.failed and outcome.result.kind is RetrievalFailureKind.RESULT_TOO_LARGE
    assert store.supplied(STATE.execution_id) == () and ledger.records(STATE.execution_id) == ()


def test_a_port_that_raises_is_an_unavailable_failure_and_never_an_exception():
    gate, port, ledger, store = build(ScriptedKnowledgePort(RuntimeError("boom")))
    outcome = gate.retrieve(CONTEXT, GOAL)
    assert outcome.result == RetrievalFailure(kind=RetrievalFailureKind.UNAVAILABLE, message="the knowledge port raised RuntimeError") and outcome.did_not_complete
    assert store.supplied(STATE.execution_id) == () and ledger.records(STATE.execution_id) == ()


@pytest.mark.parametrize("junk", [None, "an answer", 42, {"hits": []}])
def test_a_port_that_answers_in_a_shape_it_did_not_promise_is_a_malformed_failure(junk):
    gate, _, ledger, store = build(ScriptedKnowledgePort(junk))
    outcome = gate.retrieve(CONTEXT, GOAL)
    assert outcome.result == RetrievalFailure(kind=RetrievalFailureKind.MALFORMED_RESULT, message="the knowledge port returned neither an answer nor a failure")
    assert store.supplied(STATE.execution_id) == () and ledger.records(STATE.execution_id) == ()


@pytest.mark.parametrize("field", ["query_id", "kb_id", "snapshot_id", "scheme_id"])
def test_an_answer_to_another_request_is_a_malformed_failure_and_nothing_is_stored(field):
    def wrong(request):
        good = answer_with(request, (FIRST,))
        other = {"query_id": "f" * 64, "kb_id": "elsewhere", "snapshot_id": "f" * 64, "scheme_id": "another-scheme"}[field]
        return good.model_copy(update={field: other})

    gate, _, ledger, store = build(ScriptedKnowledgePort(wrong))
    outcome = gate.retrieve(CONTEXT, GOAL)
    assert outcome.failed and outcome.result.kind is RetrievalFailureKind.MALFORMED_RESULT
    assert store.supplied(STATE.execution_id) == () and ledger.records(STATE.execution_id) == ()


def test_an_answer_with_more_hits_than_top_k_is_a_malformed_failure():
    gate, _, ledger, store = build(scripted(*SNAPSHOT.chunks[:5]), descriptor=descriptor_for(top_k=2))
    outcome = gate.retrieve(CONTEXT, GOAL)
    assert outcome.failed and outcome.result.kind is RetrievalFailureKind.MALFORMED_RESULT and "top_k" in outcome.result.message
    assert store.supplied(STATE.execution_id) == () and ledger.records(STATE.execution_id) == ()


def test_a_hit_the_pinned_snapshot_does_not_hold_is_refused_and_no_hit_of_that_answer_is_stored_or_recorded():
    other = build_snapshot((*small_corpus(), doc("extra", "An extra document that the pinned snapshot does not hold at all.")), SCHEME)
    stranger = next(chunk for chunk in other.chunks if chunk.source_id == "extra")
    gate, _, ledger, store = build(scripted(FIRST, stranger))
    outcome = gate.retrieve(CONTEXT, GOAL)
    assert outcome.failed and outcome.result.kind is RetrievalFailureKind.MALFORMED_RESULT and "does not hold" in outcome.result.message
    assert store.supplied(STATE.execution_id) == () and ledger.records(STATE.execution_id) == ()  # not even the good hit


def test_an_evidence_reference_already_taken_by_other_content_refuses_the_answer_and_records_nothing():
    store = InMemoryArtifactStore()
    store.put_supplied(STATE.execution_id, Artifact(ref=ArtifactRef(SECOND.evidence_ref), content_type="text/plain", content="a supplied document that happens to use the reference"))
    gate, _, ledger, _ = build(scripted(FIRST, SECOND), store=store)
    outcome = gate.retrieve(CONTEXT, GOAL)
    assert outcome.failed and outcome.result.kind is RetrievalFailureKind.MALFORMED_RESULT and "already taken" in outcome.result.message
    assert ledger.records(STATE.execution_id) == () and len(store.supplied(STATE.execution_id)) == 1  # the one supplied document, and nothing of the answer


def test_the_same_evidence_already_in_the_store_is_reused_not_a_conflict():
    store = InMemoryArtifactStore()
    store.put_supplied(STATE.execution_id, Artifact(ref=ArtifactRef(FIRST.evidence_ref), content_type="text/plain", content=FIRST.text))
    gate, _, ledger, _ = build(scripted(FIRST), store=store)
    outcome = gate.retrieve(CONTEXT, GOAL)
    assert not outcome.failed and len(store.supplied(STATE.execution_id)) == 1 and ledger.get(STATE.execution_id, FIRST.evidence_ref) is not None


def test_a_chunk_the_ledger_already_holds_from_another_snapshot_is_refused_and_nothing_is_stored():
    other = build_snapshot((*small_corpus(), doc("extra", "An extra document that makes this a different snapshot.")), SCHEME)
    same_chunk_elsewhere = evidence_from_snapshot(other, FIRST.chunk_id, query_id="a" * 64)
    ledger = EvidenceLedger()
    assert ledger.record(STATE.execution_id, same_chunk_elsewhere) == same_chunk_elsewhere
    gate, _, _, store = build(scripted(FIRST), ledger=ledger)
    outcome = gate.retrieve(CONTEXT, GOAL)
    assert outcome.failed and outcome.result.kind is RetrievalFailureKind.MALFORMED_RESULT and "ledger refuses" in outcome.result.message
    assert store.supplied(STATE.execution_id) == () and ledger.get(STATE.execution_id, FIRST.evidence_ref) == same_chunk_elsewhere  # untouched


# --- the outcome ------------------------------------------------------------------------------------------------------------------


def test_an_outcome_is_consistent_with_its_answer_or_it_is_refused():
    request = RetrievalRequest(kb_id=KB, snapshot_id=SNAPSHOT.snapshot_id, scheme_id=LEXICAL_SCHEME_ID, text=GOAL, top_k=4, max_result_bytes=10**6)
    good = answer_with(request, (FIRST, SECOND))
    refs = tuple(ArtifactRef(hit.evidence_ref) for hit in good.hits)
    assert KnowledgeGateOutcome(kind=KnowledgeGateKind.RETRIEVED, query_id=request.query_id, result=good, refs=refs).refs == refs
    failure = RetrievalFailure(kind=RetrievalFailureKind.UNAVAILABLE, message="down")
    for bad in (
        dict(result=good, refs=refs[:1]),
        dict(result=good, refs=tuple(reversed(refs))),
        dict(result=good, refs=()),
        dict(result=failure, refs=refs),
        dict(result=failure, refs=(), kind=KnowledgeGateKind.SERVED),
    ):
        with pytest.raises(ValidationError):
            KnowledgeGateOutcome(**({"kind": KnowledgeGateKind.RETRIEVED, "query_id": request.query_id} | bad))
