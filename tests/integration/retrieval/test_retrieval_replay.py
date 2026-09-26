"""A recorded mission that retrieves, replayed from its log alone (decisions.md D-015, D-218, D-225; V1.3 Step 4, phase A; invariants 8, 15 and 16).

Real components throughout: the real lexical retriever over a real snapshot, the real recording wrappers, the real recorded run and the real replay; only the two work agents are test
doubles that ask the retriever a question and cite what came back (Research is not integrated yet, D-208). What is proven: what the log records is exactly what the retriever answered; the
log replays to the same state and the same facts with the retriever, the index and the model made impossible to call; a citation is traceable from the log alone to the chunk, document and
source the retriever returned; a tampered log is refused; and the whole story is byte-identical under any hash seed.
"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from eidos.agents import Artifact
from eidos.baseline import run_baseline
from eidos.contracts import ArtifactRef, MissionEventType
from eidos.knowledge import (
    LEXICAL_SCHEME_ID,
    DocumentRef,
    LexicalKnowledgePort,
    RetrievalRequest,
    RetrievalResult,
    build_snapshot,
    canonical_query_text,
    independent_sources,
)
from eidos.recording import RecordingCitations, RecordingKnowledgePort, retrieval_facts_of
from eidos.runtime import SequentialExecutor, VerificationResult, WorkResult
from eidos.state import (
    CitationKind,
    RetrievalOutcome,
    audit_evidence,
    dump_jsonl,
    execution_record,
    load_jsonl,
    replay,
    replay_jsonl,
)

from eidos_knowledge_factories import SCHEME, small_corpus
from eidos_recording_factories import FixedClock, baseline_mission, new_rig, record
from eidos_runtime_factories import admit_all
from eidos_v04_registry import ANALYSIS_AGENT_ID, RESEARCH_AGENT_ID, make_registry
from eidos_validation_factories import make_system_limits

ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT = build_snapshot(small_corpus(), SCHEME)
KB = "facility"
FIRST_QUERY, SECOND_QUERY = "inspection checklist before restart", "grid operator notified before reconnection"


def make_request(text: str, top_k: int = 4) -> RetrievalRequest:
    return RetrievalRequest(
        kb_id=KB, snapshot_id=SNAPSHOT.snapshot_id, scheme_id=LEXICAL_SCHEME_ID, text=canonical_query_text(text), top_k=top_k, max_result_bytes=10**6
    )


class Asking:
    """A work agent that asks the knowledge port one question, keeps an artifact citing the best hits and (optionally) another artifact it read, and reports it produced."""

    def __init__(self, port, store, question: str, cites_artifact: str | None = None, cite_hits: int = 2):
        self.port, self.store, self.question, self.cites_artifact, self.cite_hits = port, store, question, cites_artifact, cite_hits

    def run(self, context, node):
        outcome = self.port.retrieve(make_request(self.question))
        assert isinstance(outcome, RetrievalResult), outcome
        refs = tuple(ArtifactRef(hit.evidence_ref) for hit in outcome.hits[: self.cite_hits])
        if self.cites_artifact is not None:
            refs = (ArtifactRef(self.cites_artifact), *refs)
        ref = ArtifactRef(f"artifact:{node.step_id}")
        self.store.put_step_artifact(context.execution_id, node.step_id, Artifact(ref=ref, content_type="text/plain", content=f"Answer to: {self.question}", source_refs=refs))
        return WorkResult.produced(ref)


class Passing:
    """A verifier that passes: what is under test is the record of retrieval, not the verdict (the verifier is not wired to the ledger until Step 7)."""

    def verify(self, context, node, predecessors):
        return VerificationResult.passed("every rule that was evaluated held")


def rig_with(port_factory, *, cite=True, second_cites: int = 1):
    state, plan = baseline_mission()
    rig = new_rig(state)
    clock = FixedClock()
    port = port_factory(rig, clock)
    agents = {
        RESEARCH_AGENT_ID: Asking(port, rig.store, FIRST_QUERY),
        ANALYSIS_AGENT_ID: Asking(port, rig.store, SECOND_QUERY, cites_artifact="artifact:gather", cite_hits=second_cites),
    }
    rig.agents = {agent_id: RecordingCitations(agent, rig.tracker, rig.store) if cite else agent for agent_id, agent in agents.items()}
    rig.verifier = Passing()
    return state, plan, rig, clock


def recording_port(rig, clock):
    return RecordingKnowledgePort(LexicalKnowledgePort(SNAPSHOT, kb_id=KB), rig.tracker, clock)


def recorded_run(second_cites: int = 1):
    state, plan, rig, clock = rig_with(recording_port, second_cites=second_cites)
    run, _ = record(state, plan, rig, clock=clock)
    return state, plan, run


def settled(run, step: str):
    return next(r.payload for r in run.log.records if r.event.type is MissionEventType.NODE_SETTLED and r.payload.result.step_id == step)


# --- what the log records is what the retriever answered --------------------------------------------------------------------------


def test_the_log_records_each_retrieval_exactly_as_the_retriever_answered_it():
    _, _, run = recorded_run()
    port = LexicalKnowledgePort(SNAPSHOT, kb_id=KB)
    for step, question in (("gather", FIRST_QUERY), ("analyse", SECOND_QUERY)):
        request = make_request(question)
        (facts,) = settled(run, step).retrievals
        expected = retrieval_facts_of(request, port.retrieve(request), facts.elapsed_ms)
        assert facts == expected
        assert facts.outcome is RetrievalOutcome.RESULT and facts.query_id == request.query_id and facts.top_k == 4
        assert len(facts.hits) >= 2 and [h.rank for h in facts.hits] == list(range(1, len(facts.hits) + 1))
    assert settled(run, "check").retrievals == () and settled(run, "check").citations == ()


def test_the_log_records_what_each_artifact_cited_verbatim():
    _, _, run = recorded_run()
    (first,) = settled(run, "gather").retrievals
    (second,) = settled(run, "analyse").retrievals
    assert settled(run, "gather").citations == tuple(h.evidence_ref for h in first.hits[:2])
    assert settled(run, "analyse").citations == ("artifact:gather", second.hits[0].evidence_ref)


def test_a_recorded_run_reports_what_the_same_run_reports_without_recording_anything():
    state, plan, rig, clock = rig_with(recording_port)
    run, _ = record(state, plan, rig, clock=clock)
    bare_state, bare_plan = baseline_mission()
    bare = new_rig(bare_state)
    port = LexicalKnowledgePort(SNAPSHOT, kb_id=KB)
    bare.agents = {RESEARCH_AGENT_ID: Asking(port, bare.store, FIRST_QUERY), ANALYSIS_AGENT_ID: Asking(port, bare.store, SECOND_QUERY, cites_artifact="artifact:gather", cite_hits=1)}
    report = run_baseline(
        state=bare_state, plan=bare_plan, limits=make_system_limits(), registry=make_registry(), agents=bare.agents, verifier=Passing(),
        admission_guard=admit_all(), executor_factory=SequentialExecutor,
    )
    assert run.report == report and run.refused == () and run.discrepancies == ()


def test_retrieval_is_not_budgeted_or_counted_so_no_mission_counter_moves():
    state, plan, run = recorded_run()
    bare_state, bare_plan, bare_rig, bare_clock = rig_with(lambda rig, clock: LexicalKnowledgePort(SNAPSHOT, kb_id=KB), cite=False)
    unrecorded_run, _ = record(bare_state, bare_plan, bare_rig, clock=bare_clock)
    with_retrieval, without = run.log.state.model_dump(), unrecorded_run.log.state.model_dump()
    # The one field that differs is accounted node time: the recording wrapper reads the shared fixed clock twice around each retrieval, so a node is measured longer. Nothing else moves.
    assert {k for k in with_retrieval if with_retrieval[k] != without[k]} == {"execution_time_used_ms"}
    assert with_retrieval["execution_time_used_ms"] > without["execution_time_used_ms"]


# --- replay from the log alone -----------------------------------------------------------------------------------------------------


def test_replay_reproduces_the_state_and_every_recorded_fact_from_the_log():
    _, _, run = recorded_run()
    assert replay(run.log.records).state == run.log.state
    record_of = execution_record(run.log.records)
    assert [step.retrievals for step in record_of.steps] == [settled(run, s).retrievals for s in ("gather", "analyse", "check")]
    assert [step.citations for step in record_of.steps] == [settled(run, s).citations for s in ("gather", "analyse", "check")]


def test_the_jsonl_form_round_trips_and_replays_to_the_same_facts():
    _, _, run = recorded_run()
    text = dump_jsonl(run.log.records)
    loaded = load_jsonl(text)
    assert loaded.rejection is None and loaded.records == run.log.records and dump_jsonl(loaded.records) == text
    assert replay_jsonl(text).state == run.log.state and execution_record(loaded.records) == execution_record(run.log.records)


class Forbidden:
    """Raises if it is ever called: it stands in for a retriever, an index, a model or an embedder."""

    def __init__(self):
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("replay must not retrieve, index, embed or call a model")


def test_replay_and_the_audit_never_call_the_retriever_the_index_or_the_model(monkeypatch):
    state, plan, rig, clock = rig_with(recording_port)
    run, rig = record(state, plan, rig, clock=clock)
    text = dump_jsonl(run.log.records)
    expected = (replay_jsonl(text).state, execution_record(load_jsonl(text).records), audit_evidence(execution_record(load_jsonl(text).records)))

    forbidden = Forbidden()
    monkeypatch.setattr(LexicalKnowledgePort, "retrieve", forbidden)
    monkeypatch.setattr(LexicalKnowledgePort, "__init__", forbidden)
    monkeypatch.setattr(LexicalKnowledgePort, "_ranked", forbidden)
    monkeypatch.setattr(type(rig.scripted), "complete", forbidden)

    again = (replay_jsonl(text).state, execution_record(load_jsonl(text).records), audit_evidence(execution_record(load_jsonl(text).records)))
    assert again == expected
    assert forbidden.calls == 0


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
audit = audit_evidence(execution_record(load_jsonl(text).records))
loaded = sorted(m for m in sys.modules if m in BLOCKED or any(m.startswith(prefix + '.') for prefix in BLOCKED))
print(json.dumps({"audit": json.loads(audit.model_dump_json()), "loaded": loaded, "status": str(replayed.state.status)}, sort_keys=True))
""" % (
    (
        "eidos.knowledge", "eidos.agents", "eidos.recording", "eidos.policy", "eidos.mcp", "eidos.baseline", "eidos.providers", "eidos.backends", "eidos.a2a",
        "langgraph", "langchain", "torch", "sentence_transformers", "transformers", "qdrant_client", "numpy", "faiss", "requests", "httpx",
    ),
)


def test_a_fresh_process_replays_the_log_and_audits_it_with_the_retrieval_stack_unimportable():
    _, _, run = recorded_run()
    text = dump_jsonl(run.log.records)
    completed = subprocess.run([sys.executable, "-c", REPLAY_STORY], input=text, capture_output=True, text=True, cwd=ROOT)
    assert completed.returncode == 0, completed.stderr
    story = json.loads(completed.stdout.strip().splitlines()[-1])
    assert story["loaded"] == []
    assert story["audit"] == json.loads(audit_evidence(execution_record(run.log.records)).model_dump_json())
    assert [t["kind"] for t in story["audit"]["traces"]].count("resolved") == 3


# --- traceability: a citation back to the chunk the retriever returned -----------------------------------------------------------------


def test_every_citation_is_traced_from_the_log_alone_to_the_chunk_document_and_source_the_retriever_returned():
    _, _, run = recorded_run()
    audit = audit_evidence(execution_record(run.log.records))
    port = LexicalKnowledgePort(SNAPSHOT, kb_id=KB)
    answers = {q: port.retrieve(make_request(q)) for q in (FIRST_QUERY, SECOND_QUERY)}
    by_ref = {hit.evidence_ref: hit for result in answers.values() for hit in result.hits}
    resolved = [t for t in audit.traces if t.kind is CitationKind.RESOLVED]
    assert len(resolved) == 3
    for trace in resolved:
        hit = by_ref[trace.ref]
        assert (trace.chunk_id, trace.document_id, trace.source_id, trace.kb_id) == (hit.chunk.chunk_id, hit.chunk.document_id, hit.chunk.source_id, KB)
        assert trace.chunk_id in {c.chunk_id for c in SNAPSHOT.chunks}  # the Step 2 identity, not a copy of it
        assert all(where.snapshot_id == SNAPSHOT.snapshot_id and where.scheme_id == LEXICAL_SCHEME_ID for where in trace.retrieved_by)
    other = [t for t in audit.traces if t.kind is CitationKind.NOT_EVIDENCE]
    assert [t.ref for t in other] == ["artifact:gather"]


def test_the_cited_documents_compose_with_the_snapshots_derivations_into_the_independent_sources():
    _, _, run = recorded_run()
    audit = audit_evidence(execution_record(run.log.records))
    cited = [DocumentRef(source_id=c.source_id, document_id=c.document_id) for c in audit.cited]
    assert set(independent_sources(cited, SNAPSHOT.derivation_map)) <= {c.source_id for c in SNAPSHOT.chunks}
    assert len(independent_sources(cited, SNAPSHOT.derivation_map)) >= 1


def test_a_chunk_two_questions_both_returned_names_both_retrievals_in_recorded_order():
    _, _, run = recorded_run(second_cites=4)  # the second answer cites every hit it got, so a chunk both questions returned is cited
    (first,), (second,) = settled(run, "gather").retrievals, settled(run, "analyse").retrievals
    shared = {h.chunk_id for h in first.hits} & {h.chunk_id for h in second.hits}
    assert shared
    audit = audit_evidence(execution_record(run.log.records))
    for chunk_id in shared:
        traces = [t for t in audit.traces if t.chunk_id == chunk_id]
        assert traces, chunk_id
        for trace in traces:
            assert [w.query_id for w in trace.retrieved_by] == [first.query_id, second.query_id]
            assert [w.step_id for w in trace.retrieved_by] == ["gather", "analyse"]


# --- a tampered log ---------------------------------------------------------------------------------------------------------------------


def tampered(edit) -> str:
    _, _, run = recorded_run()
    document_lines = dump_jsonl(run.log.records).splitlines()
    for index, line in enumerate(document_lines):
        record = json.loads(line)
        payload = record.get("payload", {})
        if payload.get("retrievals"):
            edit(payload["retrievals"][0])
            document_lines[index] = json.dumps(record, separators=(",", ":"))
            break
    else:  # pragma: no cover - the story always retrieves
        raise AssertionError("no retrieval on the log")
    return "\n".join(document_lines) + "\n"


TAMPERINGS = {
    "a rank": lambda facts: facts["hits"][0].__setitem__("rank", 9),
    "a score": lambda facts: facts["hits"][0].__setitem__("score", -1.0),
    "the order of two hits": lambda facts: facts["hits"].reverse(),
    "top_k below the hits": lambda facts: facts.__setitem__("top_k", 1),
    "a repeated chunk": lambda facts: facts["hits"][1].__setitem__("chunk_id", facts["hits"][0]["chunk_id"]),
    "a digest": lambda facts: facts["hits"][0].__setitem__("content_digest", "nothex"),
    "the outcome": lambda facts: facts.__setitem__("outcome", "unavailable"),
    "a hit invented": lambda facts: facts["hits"].append(dict(facts["hits"][0], rank=len(facts["hits"]) + 1, chunk_id="c" * 64)),
    "the score label": lambda facts: facts.__setitem__("score_kind", None),
    "a source id": lambda facts: facts["hits"][0].__setitem__("source_id", "not a source"),
}


@pytest.mark.parametrize("name", sorted(TAMPERINGS))
def test_a_log_whose_retrieval_fact_was_tampered_with_is_refused_when_it_is_loaded(name):
    text = tampered(TAMPERINGS[name])
    assert load_jsonl(text).rejection is not None
    assert replay_jsonl(text).state is None


def test_a_tampered_citation_is_not_traced_it_is_reported_unresolved():
    _, _, run = recorded_run()
    text = dump_jsonl(run.log.records)
    (facts,) = settled(run, "gather").retrievals
    real = facts.hits[0].evidence_ref
    forged = text.replace(f'"{real}"', '"evidence:deadbeefdeadbeef"')
    assert forged != text
    audit = audit_evidence(execution_record(load_jsonl(forged).records))
    assert any(t.kind is CitationKind.UNRESOLVED and t.ref == "evidence:deadbeefdeadbeef" for t in audit.traces)


# --- determinism ---------------------------------------------------------------------------------------------------------------------------

STORY = """
import hashlib, json, sys
sys.path[:0] = ['src', 'tests/support', 'tests/integration/retrieval']
import test_retrieval_replay as t
from eidos.state import audit_evidence, dump_jsonl, execution_record

_, _, run = t.recorded_run()
text = dump_jsonl(run.log.records)
audit = audit_evidence(execution_record(run.log.records)).model_dump_json()
print(hashlib.sha256((text + audit).encode()).hexdigest())
"""


def story_digest(seed: str) -> str:
    completed = subprocess.run([sys.executable, "-c", STORY], capture_output=True, text=True, cwd=ROOT, env=dict(os.environ, PYTHONHASHSEED=seed))
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip().splitlines()[-1]


@pytest.mark.parametrize("seed", ["1", "42", "2718281828"])
def test_the_recorded_log_and_its_audit_are_byte_identical_under_any_hash_seed(seed):
    assert story_digest(seed) == story_digest("0")


def test_the_same_run_twice_records_byte_identical_logs():
    _, _, first = recorded_run()
    _, _, second = recorded_run()
    assert dump_jsonl(first.log.records) == dump_jsonl(second.log.records)
    assert hashlib.sha256(dump_jsonl(first.log.records).encode()).hexdigest() == hashlib.sha256(dump_jsonl(second.log.records).encode()).hexdigest()


def test_the_story_really_retrieves_and_cites():
    _, _, run = recorded_run()
    assert sum(len(settled(run, s).retrievals) for s in ("gather", "analyse", "check")) == 2
    assert sum(len(settled(run, s).citations) for s in ("gather", "analyse", "check")) == 4
