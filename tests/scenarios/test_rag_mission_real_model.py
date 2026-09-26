"""Scenario: the retrieval-augmented mission with the real pinned model behind the process boundary (decisions.md D-226, D-227, D-228; V1.3 Step 7).

The default scenario (``test_rag_mission.py``) proves the whole path with a stub model behind the real worker program. This is the one opt-in run with the real thing: the isolated Python 3.13
interpreter, the model library and the cached ``paraphrase-multilingual-MiniLM-L12-v2`` at its pinned revision, retrieving from the frozen fixture's knowledge base for one **development** query (never
a test query: the frozen test queries are for the benchmark alone, D-208). It runs only when selected (``-m real_model``, D-136), is deselected by default, never skips, and fails loudly with what is
missing named. Nothing is downloaded and the network is never used.

**It judges nothing about retrieval.** What is asserted is the path: the recorded retrieval carries the pinned model's scheme, every hit is a real chunk of the fixture, every citation is traced from
the log alone to what was retrieved, the mission completes through the existing verification (its model scripted, as everywhere: only the retriever is real), the log replays in a fresh interpreter with
the retrieval stack and the model libraries unimportable, and replay does not ask the worker. Which chunks came back for the query is printed (``-s``) as an observation of one run, never asserted, and it is
not a measurement of retrieval quality: that is the benchmark's, on the frozen test queries.
"""

from hashlib import sha256
from pathlib import Path

import pytest

from eidos.knowledge import PINNED_MODEL, SemanticKnowledgePort, semantic_scheme_id
from eidos.state import CitationKind, RetrievalOutcome, audit_evidence, dump_jsonl, execution_record, load_jsonl, replay, replay_jsonl

from eidos_rag_rig import run_rag
from eidos_replay_story import replay_in_fresh_process
from eidos_retrieval_fixture import KB_ID, QUERIES, build_fixture_snapshot, group_of, gold_groups
from eidos_semantic_benchmark import cache_file_count, start_real_embedder

pytestmark = pytest.mark.real_model

ROOT = Path(__file__).resolve().parents[2]
QUERY = next(query for query in QUERIES if query.query_id == "LD1")
TOP_K = 5


@pytest.fixture(scope="module")
def embedder():
    cache_before = cache_file_count()
    with start_real_embedder() as started:
        yield started
    assert cache_file_count() == cache_before, "the worker changed the model cache: something was downloaded or written"


@pytest.fixture(scope="module")
def mission(embedder):
    snapshot = build_fixture_snapshot()
    port = SemanticKnowledgePort.open(snapshot, kb_id=KB_ID, embedder=embedder)
    assert isinstance(port, SemanticKnowledgePort), port
    return snapshot, run_rag(port, snapshot=snapshot, goal=QUERY.text, kb_id=KB_ID, scheme_id=semantic_scheme_id(PINNED_MODEL), top_k=TOP_K)


def test_the_mission_asks_a_development_query_and_never_a_test_query():
    assert QUERY.split == "dev" and QUERY.text.endswith("?")


def test_the_real_model_mission_retrieves_is_verified_and_completes_with_every_citation_traced_to_the_fixture(mission):
    snapshot, rag = mission
    record = execution_record(rag.run.log.records)
    assert rag.run.refused == () and rag.run.discrepancies == ()
    assert (record.mission_status.value, record.verified) == ("completed", True)
    (facts,) = record.steps[0].retrievals
    assert facts.outcome is RetrievalOutcome.RESULT and facts.scheme_id == semantic_scheme_id(PINNED_MODEL) and facts.score_kind == "semantic-cosine-v1"
    assert len(facts.hits) == TOP_K and all(-1.0 <= hit.score <= 1.0 for hit in facts.hits) and rag.port.calls == 1
    chunks = {chunk.chunk_id: chunk for chunk in snapshot.chunks}
    assert all(hit.chunk_id in chunks for hit in facts.hits)  # every hit is a chunk of the fixture's snapshot
    records = rag.ledger.records(rag.state.execution_id)
    assert {r.chunk.chunk_id for r in records} == {hit.chunk_id for hit in facts.hits}
    audit = audit_evidence(record)
    resolved = [t for t in audit.traces if t.kind is CitationKind.RESOLVED]
    assert len(resolved) == 2 * TOP_K and {t.kind for t in audit.traces} == {CitationKind.RESOLVED, CitationKind.NOT_EVIDENCE}
    assert all(t.kb_id == KB_ID and t.chunk_id in chunks for t in resolved)
    gold = gold_groups(snapshot, QUERY)
    print(f"\nobserved on one run, not a measurement: development query {QUERY.query_id} {QUERY.text!r}")
    for hit in facts.hits:
        chunk = chunks[hit.chunk_id]
        print(f"  rank {hit.rank} score {hit.score:.4f} source {chunk.source_id} gold {group_of(chunk) in gold}")


def test_the_log_replays_in_a_fresh_interpreter_without_the_model_stack_and_replay_does_not_ask_the_worker(mission, embedder):
    _, rag = mission
    log = rag.run.log
    text = dump_jsonl(log.records)
    asked = embedder.requests
    assert replay_jsonl(text).state == log.state and replay(load_jsonl(text).records).state == log.state
    story = replay_in_fresh_process(text, ROOT)
    assert story["loaded"] == [] and story["audit"] == audit_evidence(execution_record(log.records)).model_dump(mode="json")
    assert story["state_sha256"] == sha256(log.state.model_dump_json().encode("utf-8")).hexdigest()
    assert embedder.requests == asked  # replaying asked the worker nothing
