"""Scenario: one whole retrieval-augmented mission, recorded, audited and replayed (decisions.md D-215, D-217, D-218, D-225, D-226, D-227, D-228; V1.3 Step 7; invariants 1, 2, 9, 12, 13, 15 and 16).

Mission -> Research -> the knowledge gate -> a retriever -> the evidence ledger -> a cited research result -> Analysis -> the existing verification -> the mission's result, as one recorded pass, over
**both** retrievers: the semantic one behind the real process boundary (the real worker program over a stub model, so it needs no model library) and the exact lexical one. Research is the same
agent over either; nothing after the gate can tell which answered. The model is scripted, so nothing here is a measurement and nothing depends on a model.

What is proven, for each retriever: the mission completes and is verified by the existing verification; the log carries the retrieval exactly as the port answered it (its scheme, score label, query
identity and hits) and the references the artifacts cited; the ledger holds each retrieved chunk once, with the query that retrieved it; every citation is traced from the log alone to the chunk the port
returned; and the recorded log replays to the same state, the same execution record and the same audit with a process, a socket, the retriever and the worker made impossible, and in a fresh
interpreter in which the retrieval stack and every model library cannot be imported. Then the failure paths (a retrieval that fails, that finds nothing, that answers wrongly, that raises; a citation
nobody retrieved; a worker that is gone), a duplicate query, determinism, and the named limitation of the existing verification that D-228 puts to the owner.
"""

import socket
import subprocess
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import pytest

from eidos.contracts import MissionEventType, MissionStatus
from eidos.knowledge import (
    LEXICAL_SCHEME_ID,
    LexicalKnowledgePort,
    RetrievalFailureKind,
    RetrievalRequest,
    SemanticKnowledgePort,
    canonical_query_text,
    semantic_scheme_id,
)
from eidos.knowledge.semantic_process import IsolatedEmbedder
from eidos.recording import retrieval_facts_of
from eidos.state import CitationKind, RetrievalOutcome, audit_evidence, dump_jsonl, evidence_ref_of_chunk_id, execution_record, load_jsonl, replay, replay_jsonl

from eidos_knowledge_gate_fixture import GOAL, KB, SNAPSHOT, ScriptedKnowledgePort, answer_with, failing_port
from eidos_mission_factories import make_mission_plan
from eidos_rag_rig import RagRun, cite_a_reference_nobody_retrieved, cite_a_reference_nobody_retrieved_in_research, run_rag
from eidos_replay_story import replay_in_fresh_process
from eidos_semantic_process_factories import FAST, fake_command, make_fake_model

ROOT = Path(__file__).resolve().parents[2]
TOP_K = 4


@dataclass
class Case:
    """One retriever the mission runs over, the scheme it answers under, and the recorded pass that ran over it."""

    name: str
    retriever: object
    scheme_id: str
    rag: RagRun
    embedder: IsolatedEmbedder | None = None


@pytest.fixture(scope="module")
def semantic(tmp_path_factory):
    directory, identity = make_fake_model(tmp_path_factory.mktemp("model"))
    embedder = IsolatedEmbedder.start(fake_command(directory, identity), expected=identity, limits=FAST)
    assert isinstance(embedder, IsolatedEmbedder), embedder
    port = SemanticKnowledgePort.open(SNAPSHOT, kb_id=KB, embedder=embedder)
    assert isinstance(port, SemanticKnowledgePort), port
    yield port, embedder, semantic_scheme_id(identity)
    embedder.close()


@pytest.fixture(scope="module", params=("semantic", "lexical"))
def case(request, semantic) -> Case:
    port, embedder, scheme_id = semantic
    if request.param == "semantic":
        return Case("semantic", port, scheme_id, run_rag(port, scheme_id=scheme_id, top_k=TOP_K), embedder)
    lexical = LexicalKnowledgePort(SNAPSHOT, kb_id=KB)
    return Case("lexical", lexical, LEXICAL_SCHEME_ID, run_rag(lexical, scheme_id=LEXICAL_SCHEME_ID, top_k=TOP_K))


def request_for(scheme_id: str, text: str = GOAL, top_k: int = TOP_K) -> RetrievalRequest:
    return RetrievalRequest(kb_id=KB, snapshot_id=SNAPSHOT.snapshot_id, scheme_id=scheme_id, text=canonical_query_text(text), top_k=top_k, max_result_bytes=10**6)


def settled(run, step):
    return next(r.payload for r in run.log.records if r.event.type is MissionEventType.NODE_SETTLED and r.payload.result.step_id == step)


def answer_of(case: Case):
    return case.retriever.retrieve(request_for(case.scheme_id))


# --- the mission: a whole pass, on either retriever -------------------------------------------------------------------------------


def test_the_mission_retrieves_researches_is_verified_by_the_existing_verification_and_completes(case):
    rag = case.rag
    record = execution_record(rag.run.log.records)
    assert rag.run.refused == () and rag.run.discrepancies == ()  # the log is the whole story
    assert rag.run.log.state.status is MissionStatus.COMPLETED
    assert (record.mission_status.value, record.failure_cause, record.verified, record.run_outcome.value) == ("completed", None, True, "finished")
    assert [(s.step_id, s.result.status.value) for s in record.steps if s.result] == [("gather", "succeeded"), ("analyse", "succeeded"), ("check", "succeeded")]
    verdict = next(s.verification for s in record.steps if s.verification is not None)
    assert verdict.verdict.value == "pass" and "citation_coverage satisfied" in verdict.reason and "minimum_distinct_sources satisfied" in verdict.reason
    assert rag.port.calls == 1  # one distinct query, asked once; the second consumer of the evidence was served from what was stored
    assert len(rag.rig.scripted.requests) == 2  # one research call, one analysis call: no model was asked about retrieval


def test_the_research_node_settles_with_the_retrieval_exactly_as_the_port_answered_it(case):
    request = request_for(case.scheme_id)
    (facts,) = settled(case.rag.run, "gather").retrievals
    assert facts == retrieval_facts_of(request, case.retriever.retrieve(request), facts.elapsed_ms)
    assert facts.outcome is RetrievalOutcome.RESULT and facts.scheme_id == case.scheme_id and facts.query_id == request.query_id
    assert (facts.kb_id, facts.snapshot_id, facts.top_k) == (KB, SNAPSHOT.snapshot_id, TOP_K)
    assert len(facts.hits) == TOP_K and [hit.rank for hit in facts.hits] == list(range(1, TOP_K + 1))
    assert facts.score_kind == answer_of(case).score_kind
    assert settled(case.rag.run, "analyse").retrievals == () and settled(case.rag.run, "check").retrievals == ()  # only the node that asked recorded a retrieval


def test_no_evidence_text_is_recorded_in_the_log_only_identities_and_digests(case):
    text = dump_jsonl(case.rag.run.log.records)
    for chunk in SNAPSHOT.chunks:
        assert chunk.text not in text  # the log carries what was retrieved, never the retrieved text (D-218)


def test_the_artifacts_cite_the_evidence_the_port_returned_by_its_reference(case):
    hits = answer_of(case).hits
    refs = {hit.evidence_ref for hit in hits}
    assert all(hit.evidence_ref == evidence_ref_of_chunk_id(hit.chunk.chunk_id) for hit in hits)  # the reference is the one the recorded chunk id maps to
    assert set(map(str, settled(case.rag.run, "gather").citations)) == refs
    analysis = list(map(str, settled(case.rag.run, "analyse").citations))
    assert set(analysis) == refs | {"artifact:gather"} and len(analysis) == len(set(analysis))
    assert settled(case.rag.run, "check").citations == ()


def test_the_ledger_holds_each_retrieved_chunk_once_with_the_query_that_retrieved_it_and_the_store_holds_its_text(case):
    rag, hits = case.rag, answer_of(case).hits
    query_id = request_for(case.scheme_id).query_id
    records = rag.ledger.records(rag.state.execution_id)
    assert {record.evidence_ref for record in records} == {hit.evidence_ref for hit in hits} and len(records) == len(hits)
    supplied = {str(artifact.ref): artifact for artifact in rag.rig.store.supplied(rag.state.execution_id)}
    for record in records:
        assert record.retrieved_by == (query_id,) and record.snapshot_id == SNAPSHOT.snapshot_id
        assert record.chunk in SNAPSHOT.chunks  # the ledger holds the snapshot's own chunk
        assert supplied[record.evidence_ref].content == record.chunk.text and supplied[record.evidence_ref].content_type == "text/plain"
    assert set(supplied) == {record.evidence_ref for record in records}


def test_every_citation_is_traced_from_the_log_alone_to_the_chunk_the_port_returned(case):
    audit = audit_evidence(execution_record(case.rag.run.log.records))
    by_ref = {hit.evidence_ref: hit for hit in answer_of(case).hits}
    resolved = [trace for trace in audit.traces if trace.kind is CitationKind.RESOLVED]
    assert len(resolved) == 2 * TOP_K and all(t.kind in (CitationKind.RESOLVED, CitationKind.NOT_EVIDENCE) for t in audit.traces)
    assert [t.ref for t in audit.traces if t.kind is CitationKind.NOT_EVIDENCE] == ["artifact:gather"]  # a produced artifact is not evidence, and is said so
    for trace in resolved:
        hit = by_ref[trace.ref]
        assert (trace.chunk_id, trace.document_id, trace.source_id, trace.kb_id) == (hit.chunk.chunk_id, hit.chunk.document_id, hit.chunk.source_id, KB)
        assert [where.step_id for where in trace.retrieved_by] == ["gather"]  # every one was retrieved by the research step, by this query, under this scheme
        assert all(where.query_id == request_for(case.scheme_id).query_id and where.scheme_id == case.scheme_id for where in trace.retrieved_by)
    assert {(cited.source_id, cited.document_id) for cited in audit.cited} == {(hit.chunk.source_id, hit.chunk.document_id) for hit in by_ref.values()}


def test_the_independent_sources_behind_the_citations_are_resolved_from_the_ledger_and_the_snapshots_declared_derivations(case):
    rag = case.rag
    record = execution_record(rag.run.log.records)
    cited = [str(ref) for step in record.steps for ref in step.citations if str(ref).startswith("evidence:")]
    resolution = rag.ledger.resolve_independence(rag.state.execution_id, cited, derived_from=SNAPSHOT.derivation_map)
    assert resolution.unresolved == () and set(resolution.evidence) == set(cited)  # nothing cited is unknown to the ledger
    sources_of_hits = {hit.chunk.source_id for hit in answer_of(case).hits}
    assert 1 <= resolution.source_count <= len(sources_of_hits)  # a derived source can only ever reduce the count, never add to it


# --- a mission is deterministic and its record is the authority ---------------------------------------------------------------------


def test_the_same_mission_over_the_same_retriever_records_the_same_log_byte_for_byte(case):
    again = run_rag(case.retriever, scheme_id=case.scheme_id, top_k=TOP_K)
    assert again.run.log.to_jsonl() == case.rag.run.log.to_jsonl()
    assert again.run.report.model_dump_json() == case.rag.run.report.model_dump_json()


def test_the_mission_state_is_what_the_reducer_folds_from_the_log_and_the_evidence_is_no_part_of_it(case):
    log = case.rag.run.log
    assert replay(log.records).state == log.state == replay_jsonl(dump_jsonl(log.records)).state
    assert not [name for name in type(log.state).model_fields if "evidence" in name or "retriev" in name or "citation" in name]  # the ledger is not global truth (invariant 1)
    assert log.state.tool_calls_used == 0  # a retrieval is a knowledge-base call, not a tool call, and no budget counts it here (D-228 reading 6)
    assert log.state.agent_calls_used == 2


# --- replay: recorded facts only ---------------------------------------------------------------------------------------------------


def test_replay_and_the_audit_start_no_process_open_no_socket_and_never_ask_a_retriever_or_a_worker(case, monkeypatch):
    log = case.rag.run.log
    text = dump_jsonl(log.records)
    expected = (replay_jsonl(text).state, execution_record(load_jsonl(text).records), audit_evidence(execution_record(load_jsonl(text).records)))
    asked_before = case.embedder.requests if case.embedder is not None else None
    reached = case.rag.port.calls

    def forbidden(*args, **kwargs):
        raise AssertionError("replay must not start a process, open a connection, or ask a retriever, a worker, the gate or an agent")

    for target, name in (
        (subprocess, "Popen"), (socket.socket, "connect"), (type(case.retriever), "retrieve"), (IsolatedEmbedder, "embed"), (IsolatedEmbedder, "start"),
    ):
        monkeypatch.setattr(target, name, forbidden)
    monkeypatch.setattr(type(case.rag.gate), "retrieve", forbidden)

    again = (replay_jsonl(text).state, execution_record(load_jsonl(text).records), audit_evidence(execution_record(load_jsonl(text).records)))
    assert again == expected and replay(log.records).state == log.state
    assert case.rag.port.calls == reached and (case.embedder is None or case.embedder.requests == asked_before)  # nothing was asked


def test_a_fresh_interpreter_replays_and_audits_the_log_with_the_retrieval_stack_and_every_model_library_unimportable(case):
    log = case.rag.run.log
    story = replay_in_fresh_process(dump_jsonl(log.records), ROOT)
    assert story["loaded"] == []  # neither the knowledge package, an agent, a provider, a backend nor a model library was imported to do it
    assert story["audit"] == audit_evidence(execution_record(log.records)).model_dump(mode="json")
    assert story["status"] == str(log.state.status)
    assert story["state_sha256"] == sha256(log.state.model_dump_json().encode("utf-8")).hexdigest()  # the same state, to the byte


# --- when retrieval fails, or the model cites what was never retrieved ------------------------------------------------------------------


def rag_over(retriever, **kwargs) -> RagRun:
    return run_rag(retriever, top_k=TOP_K, **kwargs)


def failed_outcome(rag: RagRun):
    record = execution_record(rag.run.log.records)
    assert rag.run.refused == () and rag.run.discrepancies == ()
    assert (record.mission_status.value, record.verified) == ("failed", None)  # only a completed mission says whether it was verified
    assert [s.result.status.value for s in record.steps if s.result][1:] == ["skipped", "skipped"]  # nothing after the failed research step ran
    assert len(rag.rig.scripted.requests) == 0  # and the model was never asked: there was nothing to research
    assert audit_evidence(record).traces == ()
    return record


@pytest.mark.parametrize(
    "kind, node_status, cause",
    [
        (RetrievalFailureKind.UNAVAILABLE, "failed", "execution_failed"),
        (RetrievalFailureKind.REQUEST_MISMATCH, "no_result", "no_result"),
        (RetrievalFailureKind.RESULT_TOO_LARGE, "no_result", "no_result"),
        (RetrievalFailureKind.MALFORMED_RESULT, "no_result", "no_result"),
    ],
    ids=lambda x: getattr(x, "value", x),
)
def test_a_retrieval_that_fails_fails_the_mission_and_the_log_says_which_failure_it_was(kind, node_status, cause):
    rag = rag_over(failing_port(kind))
    record = failed_outcome(rag)
    assert record.failure_cause == cause
    gather = record.steps[0]
    assert gather.result.status.value == node_status and f"the knowledge retrieval failed ({kind.value})" in gather.result.reason
    assert [(f.outcome.value, f.hits) for f in gather.retrievals] == [(kind.value, ())]  # the failure is recorded, typed, with no hits
    assert gather.citations == () and rag.rig.store.supplied(rag.state.execution_id) == () and rag.ledger.records(rag.state.execution_id) == ()


def test_a_retrieval_that_finds_nothing_is_a_recorded_empty_answer_and_a_mission_with_no_result():
    rag = rag_over(ScriptedKnowledgePort(lambda request: answer_with(request, ())))
    record = failed_outcome(rag)
    gather = record.steps[0]
    assert record.failure_cause == "no_result" and "the knowledge base returned no evidence" in gather.result.reason
    assert [(f.outcome, f.hits) for f in gather.retrievals] == [(RetrievalOutcome.RESULT, ())]


def test_an_answer_to_a_different_question_is_recorded_as_malformed_and_nothing_of_it_is_trusted():
    wrong = ScriptedKnowledgePort(lambda request: answer_with(request, SNAPSHOT.chunks[:2]).model_copy(update={"query_id": "e" * 64}))
    rag = rag_over(wrong)
    record = failed_outcome(rag)
    assert [(f.outcome, f.hits) for f in record.steps[0].retrievals] == [(RetrievalOutcome.MALFORMED_RESULT, ())]
    assert record.failure_cause == "no_result" and rag.ledger.records(rag.state.execution_id) == ()


def test_a_port_that_raises_fails_the_step_and_only_the_steps_reason_says_so_the_recording_wrapper_records_no_fact_for_a_call_that_did_not_return():
    rag = rag_over(ScriptedKnowledgePort(RuntimeError("boom")))
    record = failed_outcome(rag)
    gather = record.steps[0]
    assert record.failure_cause == "execution_failed" and "the knowledge port raised RuntimeError" in gather.result.reason
    assert gather.retrievals == ()  # observation for the owner (D-228): a raise is off the port's contract, the recorder passes it through untouched (D-218) and the gate converts it after


def test_a_semantic_worker_that_is_gone_is_recorded_as_an_unavailable_retrieval_and_the_mission_fails(tmp_path):
    directory, identity = make_fake_model(tmp_path)
    embedder = IsolatedEmbedder.start(fake_command(directory, identity), expected=identity, limits=FAST)
    port = SemanticKnowledgePort.open(SNAPSHOT, kb_id=KB, embedder=embedder)
    embedder.close()  # the worker is gone before the mission asks
    rag = run_rag(port, scheme_id=semantic_scheme_id(identity), top_k=TOP_K)
    record = failed_outcome(rag)
    (facts,) = record.steps[0].retrievals
    assert facts.outcome is RetrievalOutcome.UNAVAILABLE and facts.scheme_id == semantic_scheme_id(identity) and facts.hits == () and facts.score_kind is None
    assert record.failure_cause == "execution_failed"
    assert replay_jsonl(rag.run.log.to_jsonl()).state == rag.run.log.state  # and a failed mission replays like any other


def test_a_citation_nobody_retrieved_fails_verification_and_the_audit_names_it_unresolved():
    rag = rag_over(LexicalKnowledgePort(SNAPSHOT, kb_id=KB), respond=cite_a_reference_nobody_retrieved)
    record = execution_record(rag.run.log.records)
    assert (record.mission_status.value, record.failure_cause, record.verified) == ("failed", "verification_failed", None)
    verdict = next(s.verification for s in record.steps if s.verification is not None)
    assert verdict.verdict.value == "fail" and "citation_coverage violated" in verdict.reason and "evidence:0000000000000000" in verdict.reason
    unresolved = [t for t in audit_evidence(record).traces if t.kind is CitationKind.UNRESOLVED]
    assert [(t.step_id, t.ref) for t in unresolved] == [("analyse", "evidence:0000000000000000")]
    assert unresolved[0].retrieved_by == () and unresolved[0].chunk_id is None  # a claim with no recorded retrieval behind it is reported as exactly that


def test_known_limitation_a_citation_nobody_retrieved_in_the_research_artifact_passes_verification_and_only_the_audit_names_it():
    """D-228 puts this to the owner too. The existing ``citation_coverage`` rule checks that what the artifacts *it is handed* cite exists, and it is handed the analysis, which cites the research
    artifact and real evidence: it does not follow the citation into the research artifact. The audit, which reads every step's recorded citations, does. Pinned, not changed."""
    rag = rag_over(LexicalKnowledgePort(SNAPSHOT, kb_id=KB), respond=cite_a_reference_nobody_retrieved_in_research)
    record = execution_record(rag.run.log.records)
    assert (record.mission_status.value, record.verified) == ("completed", True)  # verified by the existing rules
    unresolved = [t for t in audit_evidence(record).traces if t.kind is CitationKind.UNRESOLVED]
    assert [(t.step_id, t.ref) for t in unresolved] == [("gather", "evidence:0000000000000000")]  # yet the recorded citation of the research step resolves to nothing retrieved


# --- a duplicate query, and the limitation of the existing verification -----------------------------------------------------------


def two_research_steps(state):
    return make_mission_plan(
        state, {"gather": "", "gather_two": "", "analyse": "gather gather_two", "check": "analyse"}, verify=("check",),
        capability_of={"gather": "research", "gather_two": "research", "analyse": "cost"},
    )


def test_a_second_research_step_asking_the_same_question_is_served_what_was_stored_and_the_port_is_asked_once(case):
    rag = run_rag(case.retriever, scheme_id=case.scheme_id, top_k=TOP_K, plan_of=two_research_steps)
    record = execution_record(rag.run.log.records)
    assert record.mission_status.value == "completed" and record.verified is True
    assert rag.port.calls == 1  # the same execution, the same query: answered once
    first, second = record.steps[0], record.steps[1]
    assert len(first.retrievals) == 1 and second.retrievals == ()  # the serving node made no retrieval, so it records none
    assert set(second.citations) == set(first.citations) and len(second.citations) == TOP_K  # yet it cites the same evidence
    audit = audit_evidence(record)
    assert all(t.kind is not CitationKind.UNRESOLVED and t.kind is not CitationKind.AMBIGUOUS for t in audit.traces)  # and each of those resolves to the first node's recorded hits
    assert {where.step_id for t in audit.traces if t.kind is CitationKind.RESOLVED for where in t.retrieved_by} == {"gather"}
    assert len(rag.ledger.records(rag.state.execution_id)) == TOP_K


def test_known_limitation_the_existing_verification_counts_stored_chunks_not_independent_sources_so_it_can_pass_a_mission_the_contract_should_not(case):
    """D-228 puts this to the owner; it is pinned, not fixed, because the Step 7 brief says the existing verification is used as it is.

    The lexical retriever answers this goal with six chunks from four independent sources (a source and its byte-identical mirror are declared different sources, D-209). The V1.2 rule
    ``minimum_distinct_sources`` counts each stored chunk as a distinct supplied source, so it reaches six, and a contract that requires five independent sources is passed. The ledger and
    the D-209 resolver say four. If the owner rules that the verifier is to use the resolver, this test is the one that must change, on purpose, and the ruling goes in decisions.md.
    """
    lexical = LexicalKnowledgePort(SNAPSHOT, kb_id=KB)
    rag = run_rag(lexical, top_k=8, min_independent_evidence=5)
    record = execution_record(rag.run.log.records)
    verdict = next(s.verification for s in record.steps if s.verification is not None)
    assert verdict.verdict.value == "pass" and "6 distinct supplied source(s) reached, 5 required" in verdict.reason
    cited = [str(ref) for step in record.steps for ref in step.citations if str(ref).startswith("evidence:")]
    resolution = rag.ledger.resolve_independence(rag.state.execution_id, cited, derived_from=SNAPSHOT.derivation_map)
    assert resolution.source_count == 4 and resolution.sources == ("blog", "grid", "mirror", "ops")
    assert resolution.source_count < 5 <= 6  # verified by the V1.2 count, not by the independent count: the mission is "verified" although fewer than five independent sources stand behind it
    assert record.verified is True and record.mission_status.value == "completed"
