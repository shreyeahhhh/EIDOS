"""The evidence audit: citations traced to recorded retrievals, from the log alone (decisions.md D-218, D-225; V1.3 Step 4; invariants 15 and 16).

Real chunks and a real lexical retriever produce the facts; the audit then reads only the recorded log. What is proven: a citation resolves to exactly the chunk, document, source,
query, snapshot, scheme and rank that were recorded; what the record cannot resolve is reported as such and never guessed; and the audit and the replay beneath it run with
everything that could retrieve blocked from being imported.
"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from eidos.knowledge import (
    LEXICAL_SCHEME_ID,
    DocumentRef,
    LexicalKnowledgePort,
    RetrievalRequest,
    build_snapshot,
    canonical_query_text,
    independent_sources,
)
from eidos.recording import retrieval_facts_of
from eidos.state import (
    CitationKind,
    EvidenceAudit,
    RetrievalOutcome,
    audit_evidence,
    dump_jsonl,
    execution_record,
    load_jsonl,
)

from eidos_knowledge_factories import SCHEME, small_corpus
from eidos_retrieval_fact_factories import answer, failure, hit, settle_with_retrievals
from eidos_state_factories import LogBuilder, baseline_state_and_plan, verify_result, work_result

ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT = build_snapshot(small_corpus(), SCHEME)
PORT = LexicalKnowledgePort(SNAPSHOT, kb_id="facility")


def retrieve(text: str, top_k: int = 4):
    request = RetrievalRequest(
        kb_id="facility", snapshot_id=SNAPSHOT.snapshot_id, scheme_id=LEXICAL_SCHEME_ID, text=canonical_query_text(text), top_k=top_k, max_result_bytes=10**6
    )
    result = PORT.retrieve(request)
    return result, retrieval_facts_of(request, result, 4)


def audit_of(retrievals, citations_by_step, *, extra_steps=()) -> EvidenceAudit:
    """Settle ``gather`` with ``retrievals`` and the given steps with their citations, then audit the recorded log."""
    state, plan = baseline_state_and_plan()
    log = LogBuilder(state, plan)
    log.created(), log.generated(), log.compiled()
    log.started("gather")
    settle_with_retrievals(log, work_result("gather"), retrievals, citations_by_step.get("gather", ()))
    log.started("analyse")
    settle_with_retrievals(log, work_result("analyse"), (), citations_by_step.get("analyse", ()))
    log.started("check")
    log.settled(verify_result("check"))
    log.completed(verified=True)
    record = execution_record(log.records)
    return audit_evidence(record)


# --- a citation resolves to exactly what was recorded ---------------------------------------------------------------------------------


def test_a_cited_evidence_reference_resolves_to_the_recorded_chunk_document_source_query_snapshot_scheme_and_rank():
    result, facts = retrieve("inspection checklist before restart")
    top = result.hits[2]
    audit = audit_of((facts,), {"analyse": (top.evidence_ref,)})
    (trace,) = audit.traces
    assert trace.kind is CitationKind.RESOLVED and trace.step_id == "analyse" and trace.ref == top.evidence_ref
    assert (trace.kb_id, trace.chunk_id, trace.document_id, trace.source_id) == ("facility", top.chunk.chunk_id, top.chunk.document_id, top.chunk.source_id)
    (where,) = trace.retrieved_by
    assert (where.step_id, where.query_id, where.snapshot_id, where.scheme_id, where.rank) == ("gather", facts.query_id, SNAPSHOT.snapshot_id, LEXICAL_SCHEME_ID, 3)


def test_the_chain_reaches_the_step_two_identities_of_the_chunk():
    result, facts = retrieve("the tidal barrier sensors must report normal readings")
    hit_ = result.hits[0]
    (trace,) = audit_of((facts,), {"analyse": (hit_.evidence_ref,)}).traces
    document_refs = {(d.source_id, d.document_id) for d in SNAPSHOT.documents}
    assert (trace.source_id, trace.document_id) in document_refs
    assert trace.chunk_id in {c.chunk_id for c in SNAPSHOT.chunks} and trace.ref == "evidence:" + trace.chunk_id[:16]


def test_a_chunk_retrieved_by_two_queries_names_both_in_the_order_they_were_recorded():
    first_result, first = retrieve("inspection checklist before restart")
    second_result, second = retrieve("the checklist is completed by the duty engineer", top_k=6)
    shared = next(h for h in first_result.hits if h.chunk.chunk_id in {x.chunk.chunk_id for x in second_result.hits})
    (trace,) = audit_of((first, second), {"analyse": (shared.evidence_ref,)}).traces
    assert trace.kind is CitationKind.RESOLVED
    assert [w.query_id for w in trace.retrieved_by] == [first.query_id, second.query_id]
    assert all(w.step_id == "gather" for w in trace.retrieved_by)


def test_a_byte_identical_mirror_is_two_citations_of_one_document_under_two_sources():
    result, facts = retrieve("inspection checklist before restart", top_k=6)
    ops = next(h for h in result.hits if h.chunk.source_id == "ops" and h.rank <= 2)
    mirror = next(h for h in result.hits if h.chunk.source_id == "mirror" and h.chunk.text == ops.chunk.text)
    audit = audit_of((facts,), {"analyse": (ops.evidence_ref, mirror.evidence_ref)})
    assert [t.source_id for t in audit.traces] == ["ops", "mirror"]
    assert audit.traces[0].document_id == audit.traces[1].document_id
    assert [(c.source_id, c.document_id) for c in audit.cited] == sorted({("ops", ops.chunk.document_id), ("mirror", mirror.chunk.document_id)})


def test_the_cited_documents_are_distinct_and_sorted_whatever_was_cited_how_often():
    result, facts = retrieve("inspection checklist before restart", top_k=6)
    refs = [h.evidence_ref for h in result.hits]
    audit = audit_of((facts,), {"gather": tuple(refs[:3]), "analyse": tuple(reversed(refs))})
    cited = [(c.source_id, c.document_id) for c in audit.cited]
    assert cited == sorted(set(cited)) and len(audit.traces) == len(refs) + 3


def test_the_traces_follow_plan_order_and_then_the_order_each_artifact_listed_its_references():
    result, facts = retrieve("inspection checklist before restart", top_k=6)
    a, b, c = (h.evidence_ref for h in result.hits[:3])
    audit = audit_of((facts,), {"gather": (c, a), "analyse": (b, a)})
    assert [(t.step_id, t.ref) for t in audit.traces] == [("gather", c), ("gather", a), ("analyse", b), ("analyse", a)]


# --- what the record cannot resolve is said so --------------------------------------------------------------------------------------------


def test_an_evidence_shaped_reference_that_no_recorded_retrieval_carries_is_unresolved():
    _, facts = retrieve("inspection checklist before restart")
    (trace,) = audit_of((facts,), {"analyse": ("evidence:0000000000000000",)}).traces
    assert trace.kind is CitationKind.UNRESOLVED
    assert (trace.chunk_id, trace.document_id, trace.source_id, trace.kb_id, trace.retrieved_by) == (None, None, None, None, ())


def test_a_reference_that_is_not_shaped_like_evidence_is_not_evidence():
    refs = ("doc:1", "tool:docs/search_documents:abc:doc-1", "artifact:gather", "evidence:0123456789ABCDEF", "evidence:0123", "evidence:0123456789abcdef0", "Evidence:0123456789abcdef", "evidence:0123456789abcdeg")
    audit = audit_of((), {"analyse": refs})
    assert [t.kind for t in audit.traces] == [CitationKind.NOT_EVIDENCE] * len(refs) and audit.cited == ()


def test_a_reference_carried_by_hits_of_two_chunks_is_ambiguous_and_names_every_hit():
    a = hit(1, chunk=int("1" * 16 + "a" * 48, 16), source="ops", score=2.0)
    b = hit(2, chunk=int("1" * 16 + "b" * 48, 16), source="ops", score=1.0)
    assert a.evidence_ref == b.evidence_ref and a.chunk_id != b.chunk_id
    (trace,) = audit_of((answer(hits=(a, b)),), {"analyse": (a.evidence_ref,)}).traces
    assert trace.kind is CitationKind.AMBIGUOUS and len(trace.retrieved_by) == 2 and trace.chunk_id is None


def test_one_chunk_recorded_under_two_sources_is_ambiguous_too():
    ops, other = hit(1, chunk=5, source="ops", score=2.0), hit(1, chunk=5, source="other", score=2.0)
    audit = audit_of((answer(query=1, hits=(ops,)), answer(query=2, hits=(other,))), {"analyse": (ops.evidence_ref,)})
    assert audit.traces[0].kind is CitationKind.AMBIGUOUS


def test_a_retrieval_that_failed_or_came_back_empty_resolves_nothing():
    _, real = retrieve("inspection checklist before restart")
    ref = "evidence:" + real.hits[0].chunk_id[:16]
    audit = audit_of((failure(RetrievalOutcome.UNAVAILABLE), answer(query=9, hits=(), result_bytes=0)), {"analyse": (ref,)})
    assert audit.traces[0].kind is CitationKind.UNRESOLVED


def test_an_execution_that_retrieved_and_cited_nothing_has_an_empty_audit():
    audit = audit_of((), {})
    assert audit == EvidenceAudit(traces=(), cited=())
    assert audit_of((answer(),), {}).traces == ()


# --- composition with the counting rule the snapshot pins ---------------------------------------------------------------------------------


def test_the_cited_documents_compose_with_the_snapshots_derivations_to_the_independent_sources():
    result, facts = retrieve("the audit found no turbine may be released and a blog writes that engineers inspect", top_k=10)
    by_source = {}
    for h in result.hits:
        by_source.setdefault(h.chunk.source_id, h)
    assert {"audit", "blog"} <= set(by_source)
    audit = audit_of((facts,), {"analyse": (by_source["audit"].evidence_ref, by_source["blog"].evidence_ref)})
    cited = [DocumentRef(source_id=c.source_id, document_id=c.document_id) for c in audit.cited]
    assert independent_sources(cited, SNAPSHOT.derivation_map) == ("audit",)  # the blog is declared derived from the audit, and both were cited
    blog_alone = [d for d in cited if d.source_id == "blog"]
    assert independent_sources(blog_alone, SNAPSHOT.derivation_map) == ("blog",)  # cited without its origin, it stands alone


# --- purity, determinism and replay with nothing that could retrieve --------------------------------------------------------------------


def log_text() -> str:
    result, facts = retrieve("inspection checklist before restart", top_k=6)
    state, plan = baseline_state_and_plan()
    log = LogBuilder(state, plan)
    log.created(), log.generated(), log.compiled()
    log.started("gather")
    settle_with_retrievals(log, work_result("gather"), (facts, failure(RetrievalOutcome.RESULT_TOO_LARGE, query=3)), (result.hits[0].evidence_ref, "doc:1"))
    log.started("analyse")
    settle_with_retrievals(log, work_result("analyse"), (), (result.hits[1].evidence_ref, "evidence:ffffffffffffffff", result.hits[0].evidence_ref))
    log.started("check")
    log.settled(verify_result("check"))
    log.completed(verified=True)
    return dump_jsonl(log.records)


BLOCKED = (
    "eidos.knowledge", "eidos.agents", "eidos.recording", "eidos.policy", "eidos.mcp", "eidos.capabilities", "eidos.providers", "eidos.a2a", "eidos.backends", "eidos.selectors",
    "langgraph", "langchain", "langsmith", "torch", "sentence_transformers", "transformers", "qdrant_client", "numpy", "sklearn", "faiss", "requests", "httpx",
)

REPLAY_STORY = """
import json, sys
sys.path.insert(0, 'src')
BLOCKED = %r

class Blocker:
    def find_spec(self, name, path=None, target=None):
        if name in BLOCKED or any(name.startswith(prefix + '.') for prefix in BLOCKED):
            raise ImportError('blocked: ' + name)
        return None

sys.meta_path.insert(0, Blocker())
from eidos.state import audit_evidence, execution_record, load_jsonl, replay_jsonl

text = sys.stdin.read()
replayed = replay_jsonl(text)
record = execution_record(load_jsonl(text).records)
audit = audit_evidence(record)
loaded = sorted(m for m in sys.modules if m in BLOCKED or any(m.startswith(prefix + '.') for prefix in BLOCKED))
print(json.dumps({"status": str(replayed.state.status), "audit": json.loads(audit.model_dump_json()), "loaded": loaded}, sort_keys=True))
""" % (BLOCKED,)


def run_story(text: str, seed: str = "0") -> dict:
    completed = subprocess.run([sys.executable, "-c", REPLAY_STORY], input=text, capture_output=True, text=True, cwd=ROOT, env=dict(os.environ, PYTHONHASHSEED=seed))
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_replay_and_the_audit_run_with_every_retriever_model_index_and_transport_blocked_from_being_imported():
    text = log_text()
    answer_ = run_story(text)
    assert answer_["loaded"] == []  # nothing that could retrieve, embed, search or reach the network was so much as imported
    kinds = [t["kind"] for t in answer_["audit"]["traces"]]
    assert kinds == ["resolved", "not_evidence", "resolved", "unresolved", "resolved"]
    assert len(answer_["audit"]["cited"]) >= 1


def test_the_audit_replayed_without_them_equals_the_audit_computed_in_process():
    text = log_text()
    in_process = json.loads(audit_evidence(execution_record(load_jsonl(text).records)).model_dump_json())
    assert run_story(text)["audit"] == in_process


@pytest.mark.parametrize("seed", ["1", "42", "112233", "2718281828"])
def test_the_audit_is_identical_under_any_hash_seed(seed):
    text = log_text()
    def digest(story):
        return hashlib.sha256(json.dumps(story["audit"], sort_keys=True).encode()).hexdigest()

    assert digest(run_story(text, seed)) == digest(run_story(text, "0"))


def test_the_audit_reads_the_record_and_changes_nothing_in_it():
    record = execution_record(load_jsonl(log_text()).records)
    before = record.model_dump_json()
    first, second = audit_evidence(record), audit_evidence(record)
    assert first == second and record.model_dump_json() == before


def test_a_tampered_log_never_reaches_the_audit():
    text = log_text()
    assert load_jsonl(text.replace('"rank":1', '"rank":9', 1)).rejection is not None
