"""A mission that retrieves semantically, recorded through the real process boundary and replayed with the worker gone (decisions.md D-015, D-218, D-226; V1.3 Step 5; invariants 8, 15 and 16).

Real components throughout, except that the model behind the worker is a stub (the real worker program with a stub model, as in the protocol tests): the real ``SemanticKnowledgePort`` over the real
``IsolatedEmbedder`` over a real worker process, the real recording wrappers, the real recorded run and the real replay; the two work agents are test doubles that ask the retriever a question and
cite what came back. What is proven: what the log records is what the semantic retriever answered, with the semantic scheme and score label; the log replays to the same state and the same facts and
audits to the same traces when starting a process, opening a socket and calling the retriever are made impossible; a fresh interpreter replays it with the whole retrieval stack, and every model
library, unimportable; and a worker that fails is recorded as the typed outcome it maps to.
"""

import json
import socket
import subprocess
from pathlib import Path

import pytest

from eidos.agents import Artifact
from eidos.contracts import ArtifactRef, MissionEventType
from eidos.knowledge import (
    RetrievalFailure,
    RetrievalFailureKind,
    RetrievalRequest,
    RetrievalResult,
    SemanticKnowledgePort,
    build_snapshot,
    canonical_query_text,
    semantic_scheme_id,
)
from eidos.knowledge.semantic_process import IsolatedEmbedder
from eidos.recording import RecordingCitations, RecordingKnowledgePort, retrieval_facts_of
from eidos.runtime import VerificationResult, WorkResult
from eidos.state import CitationKind, RetrievalOutcome, audit_evidence, dump_jsonl, execution_record, load_jsonl, replay, replay_jsonl

from eidos_knowledge_factories import SCHEME, small_corpus
from eidos_recording_factories import FixedClock, baseline_mission, new_rig, record
from eidos_replay_story import replay_in_fresh_process
from eidos_semantic_process_factories import FAST, fake_command, make_fake_model
from eidos_v04_registry import ANALYSIS_AGENT_ID, RESEARCH_AGENT_ID

ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT = build_snapshot(small_corpus(), SCHEME)
KB = "facility"
FIRST_QUERY, SECOND_QUERY = "inspection checklist before restart", "grid operator notified before reconnection"


class Asking:
    def __init__(self, port, store, scheme_id, question, cites_artifact=None):
        self.port, self.store, self.scheme_id, self.question, self.cites_artifact = port, store, scheme_id, question, cites_artifact

    def run(self, context, node):
        outcome = self.port.retrieve(request_for(self.scheme_id, self.question))
        assert isinstance(outcome, RetrievalResult), outcome
        refs = tuple(ArtifactRef(hit.evidence_ref) for hit in outcome.hits[:2])
        if self.cites_artifact is not None:
            refs = (ArtifactRef(self.cites_artifact), *refs)
        ref = ArtifactRef(f"artifact:{node.step_id}")
        self.store.put_step_artifact(context.execution_id, node.step_id, Artifact(ref=ref, content_type="text/plain", content=f"Answer to: {self.question}", source_refs=refs))
        return WorkResult.produced(ref)


class Passing:
    def verify(self, context, node, predecessors):
        return VerificationResult.passed("every rule that was evaluated held")


def request_for(scheme_id: str, text: str, top_k: int = 4) -> RetrievalRequest:
    return RetrievalRequest(kb_id=KB, snapshot_id=SNAPSHOT.snapshot_id, scheme_id=scheme_id, text=canonical_query_text(text), top_k=top_k, max_result_bytes=10**6)


@pytest.fixture(scope="module")
def semantic(tmp_path_factory):
    directory, identity = make_fake_model(tmp_path_factory.mktemp("model"))
    embedder = IsolatedEmbedder.start(fake_command(directory, identity), expected=identity, limits=FAST)
    assert isinstance(embedder, IsolatedEmbedder), embedder
    port = SemanticKnowledgePort.open(SNAPSHOT, kb_id=KB, embedder=embedder)
    assert isinstance(port, SemanticKnowledgePort), port
    yield port, embedder, semantic_scheme_id(identity)
    embedder.close()


def recorded(semantic):
    port, _, scheme_id = semantic
    state, plan = baseline_mission()
    rig = new_rig(state)
    clock = FixedClock()
    wrapped = RecordingKnowledgePort(port, rig.tracker, clock)
    agents = {
        RESEARCH_AGENT_ID: Asking(wrapped, rig.store, scheme_id, FIRST_QUERY),
        ANALYSIS_AGENT_ID: Asking(wrapped, rig.store, scheme_id, SECOND_QUERY, cites_artifact="artifact:gather"),
    }
    rig.agents = {agent_id: RecordingCitations(agent, rig.tracker, rig.store) for agent_id, agent in agents.items()}
    rig.verifier = Passing()
    run, _ = record(state, plan, rig, clock=clock)
    return run


def settled(run, step):
    return next(r.payload for r in run.log.records if r.event.type is MissionEventType.NODE_SETTLED and r.payload.result.step_id == step)


def test_the_log_records_each_semantic_retrieval_as_the_port_answered_it(semantic):
    port, _, scheme_id = semantic
    run = recorded(semantic)
    for step, question in (("gather", FIRST_QUERY), ("analyse", SECOND_QUERY)):
        request = request_for(scheme_id, question)
        (facts,) = settled(run, step).retrievals
        assert facts == retrieval_facts_of(request, port.retrieve(request), facts.elapsed_ms)
        assert facts.outcome is RetrievalOutcome.RESULT and facts.scheme_id == scheme_id and facts.score_kind == "semantic-cosine-v1" and facts.query_id == request.query_id
        assert len(facts.hits) == 4 and [hit.rank for hit in facts.hits] == [1, 2, 3, 4]
        assert all(-1.0 <= hit.score <= 1.0 for hit in facts.hits)
    assert settled(run, "gather").citations == tuple(h.evidence_ref for h in settled(run, "gather").retrievals[0].hits[:2])


def test_replay_and_the_audit_start_no_process_open_no_socket_and_never_ask_the_port_or_the_worker(semantic, monkeypatch):
    port, embedder, _ = semantic
    run = recorded(semantic)
    text = dump_jsonl(run.log.records)
    expected = (replay_jsonl(text).state, execution_record(load_jsonl(text).records), audit_evidence(execution_record(load_jsonl(text).records)))
    calls_before = embedder.requests

    def forbidden(*args, **kwargs):
        raise AssertionError("replay must not start a process, open a connection, or ask a retriever or a worker")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(SemanticKnowledgePort, "retrieve", forbidden)
    monkeypatch.setattr(IsolatedEmbedder, "embed", forbidden)
    monkeypatch.setattr(IsolatedEmbedder, "start", forbidden)

    again = (replay_jsonl(text).state, execution_record(load_jsonl(text).records), audit_evidence(execution_record(load_jsonl(text).records)))
    assert again == expected and replay(run.log.records).state == run.log.state
    assert embedder.requests == calls_before  # the worker was not asked


def test_a_fresh_process_replays_a_semantic_log_with_the_retrieval_stack_and_every_model_library_unimportable(semantic):
    run = recorded(semantic)
    text = dump_jsonl(run.log.records)
    story = replay_in_fresh_process(text, ROOT)
    assert story["loaded"] == []
    assert story["audit"] == json.loads(audit_evidence(execution_record(run.log.records)).model_dump_json())
    assert [t["kind"] for t in story["audit"]["traces"]].count(CitationKind.RESOLVED.value) == 4


def test_every_citation_of_a_semantic_run_is_traced_from_the_log_alone_to_the_chunk_the_port_returned(semantic):
    port, _, scheme_id = semantic
    run = recorded(semantic)
    audit = audit_evidence(execution_record(run.log.records))
    by_ref = {hit.evidence_ref: hit for question in (FIRST_QUERY, SECOND_QUERY) for hit in port.retrieve(request_for(scheme_id, question)).hits}
    resolved = [t for t in audit.traces if t.kind is CitationKind.RESOLVED]
    assert len(resolved) == 4  # two cited by each of the two questions' answers
    for trace in resolved:
        hit = by_ref[trace.ref]
        assert (trace.chunk_id, trace.document_id, trace.source_id, trace.kb_id) == (hit.chunk.chunk_id, hit.chunk.document_id, hit.chunk.source_id, KB)
        assert all(where.snapshot_id == SNAPSHOT.snapshot_id and where.scheme_id == scheme_id for where in trace.retrieved_by)


def test_a_worker_that_has_failed_is_recorded_as_the_typed_outcome_it_maps_to_with_no_hits(tmp_path):
    directory, identity = make_fake_model(tmp_path)
    embedder = IsolatedEmbedder.start(fake_command(directory, identity), expected=identity, limits=FAST)
    port = SemanticKnowledgePort.open(SNAPSHOT, kb_id=KB, embedder=embedder)
    scheme_id = semantic_scheme_id(identity)
    embedder.close()  # the worker is gone
    request = request_for(scheme_id, FIRST_QUERY)
    outcome = port.retrieve(request)
    assert isinstance(outcome, RetrievalFailure) and outcome.kind is RetrievalFailureKind.UNAVAILABLE
    facts = retrieval_facts_of(request, outcome, 5)
    assert facts.outcome is RetrievalOutcome.UNAVAILABLE and facts.hits == () and facts.score_kind is None and facts.result_bytes is None
