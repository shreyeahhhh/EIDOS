"""The evidence ledger and the resolver for existing V1.2 documents (decisions.md D-208, D-209, D-210, D-222; V1.3 Step 3).

Real components throughout: the real artifact store, the real tool gate and the real verification agent; only the tool provider is scripted. What is proven: the
ledger keeps one record per evidence reference per execution, merges the retrieving queries of the same chunk and refuses everything else, and does so under
threads; independence is resolved over a set, with the declared derivations passed explicitly and unresolved references reported rather than counted; a V1.2
supplied or tool document is mapped into the knowledge identity by reading the store only, so no artifact, reference, invocation or verifier result changes; and
the same document reached by two queries counts once where the unchanged V1.2 verifier counts it twice.
"""

import functools
import os
import random
import subprocess
import sys
import threading
import time
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from eidos.agents import (
    Artifact,
    ArtifactEvidence,
    EvidenceLedger,
    InMemoryArtifactStore,
    ToolDocument,
    ToolGate,
    Rule,
    ToolResult,
    VerificationAgent,
    parse_tool_document_ref,
    resolve_supplied_evidence,
    tool_document_ref,
)
from eidos.contracts import ArtifactRef, ExecutionId, StepId
from eidos.knowledge import (
    EvidenceRecord,
    EvidenceRefusal,
    EvidenceRefusalCode,
    build_snapshot,
    legacy_supplied_record,
    legacy_tool_record,
    merge_evidence,
)

from eidos_knowledge_factories import SCHEME, chunk_of, doc, evidence_of, query_id, small_corpus
from eidos_runtime_factories import succeeded_result
from eidos_search_fixture import TOOL_ID, ScriptedToolPort, attempt_context, make_tool_mission, search_registry

ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT = build_snapshot(small_corpus(), SCHEME)
EXECUTION, OTHER_EXECUTION = ExecutionId(UUID(int=101)), ExecutionId(UUID(int=202))

REPLAY = "Replay rebuilds a mission from its recorded events without running any agent again."
EVENTS = "Events are recorded in an append-only log."


def record_or_fail(outcome) -> EvidenceRecord:
    assert isinstance(outcome, EvidenceRecord), outcome
    return outcome


def refusal_code(outcome) -> EvidenceRefusalCode:
    assert isinstance(outcome, EvidenceRefusal), outcome
    return outcome.code


def artifact(ref: str, content: str, *sources: str) -> Artifact:
    return Artifact(ref=ArtifactRef(ref), content_type="text/plain", content=content, source_refs=tuple(ArtifactRef(s) for s in sources))


# --- recording and duplicate handling ---------------------------------------------------------------------------------------------


def test_a_recorded_record_is_held_and_returned_by_its_evidence_reference():
    ledger = EvidenceLedger()
    record = evidence_of(SNAPSHOT, chunk_of(SNAPSHOT, "audit"))
    assert ledger.record(EXECUTION, record) == record
    assert ledger.get(EXECUTION, record.evidence_ref) == record
    assert ledger.records(EXECUTION) == (record,)
    assert ledger.get(EXECUTION, "evidence:" + "0" * 16) is None


def test_records_are_ordered_by_evidence_reference_never_by_the_order_they_were_recorded_in():
    ledger = EvidenceLedger()
    records = [evidence_of(SNAPSHOT, chunk) for chunk in SNAPSHOT.chunks]
    for record in random.Random(5).sample(records, len(records)):
        ledger.record(EXECUTION, record)
    assert [r.evidence_ref for r in ledger.records(EXECUTION)] == sorted(r.evidence_ref for r in records)
    assert len(ledger.records(EXECUTION)) == 13


def test_an_execution_sees_only_its_own_evidence():
    ledger = EvidenceLedger()
    audit, grid = evidence_of(SNAPSHOT, chunk_of(SNAPSHOT, "audit"), "a"), evidence_of(SNAPSHOT, chunk_of(SNAPSHOT, "grid"), "g")
    ledger.record(EXECUTION, audit)
    ledger.record(OTHER_EXECUTION, grid)
    assert ledger.records(EXECUTION) == (audit,) and ledger.records(OTHER_EXECUTION) == (grid,)
    assert ledger.get(EXECUTION, grid.evidence_ref) is None
    later = evidence_of(SNAPSHOT, chunk_of(SNAPSHOT, "audit"), "elsewhere")
    ledger.record(OTHER_EXECUTION, later)  # the same chunk in another execution is a record of its own, with its own provenance
    assert ledger.get(EXECUTION, audit.evidence_ref).retrieved_by == (query_id("a"),)
    assert ledger.get(OTHER_EXECUTION, audit.evidence_ref).retrieved_by == (query_id("elsewhere"),)


def test_the_same_chunk_retrieved_by_the_same_query_again_leaves_one_unchanged_record():
    ledger = EvidenceLedger()
    record = evidence_of(SNAPSHOT, chunk_of(SNAPSHOT, "audit"), "q")
    for _ in range(3):
        assert ledger.record(EXECUTION, record) == record
    assert ledger.records(EXECUTION) == (record,)


def test_the_same_chunk_retrieved_by_several_queries_is_one_record_that_names_them_all():
    ledger = EvidenceLedger()
    chunk = chunk_of(SNAPSHOT, "audit")
    for name in ("third", "first", "second", "first"):
        ledger.record(EXECUTION, evidence_of(SNAPSHOT, chunk, name))
    (held,) = ledger.records(EXECUTION)
    assert held.retrieved_by == tuple(sorted(query_id(n) for n in ("first", "second", "third")))
    assert held.chunk == chunk and held.snapshot_id == SNAPSHOT.snapshot_id


def test_different_chunks_of_one_document_are_different_evidence_of_one_document():
    ledger = EvidenceLedger()
    first, second = (evidence_of(SNAPSHOT, chunk_of(SNAPSHOT, "ops", n)) for n in (0, 1))
    ledger.record(EXECUTION, first)
    ledger.record(EXECUTION, second)
    assert len(ledger.records(EXECUTION)) == 2 and first.evidence_ref != second.evidence_ref and first.document_ref == second.document_ref


def test_a_different_chunk_under_a_held_evidence_reference_is_refused_and_the_ledger_is_unchanged(monkeypatch):
    snapshot = build_snapshot(tuple(doc(f"s{n}", f"Document number {n} says something distinct about the plant.") for n in range(20)), SCHEME)
    monkeypatch.setattr("eidos.knowledge.identity.EVIDENCE_REF_HEX_LENGTH", 1)
    seen: dict[str, object] = {}
    pair = None
    for chunk in snapshot.chunks:
        if chunk.evidence_ref in seen:
            pair = (seen[chunk.evidence_ref], chunk)
            break
        seen[chunk.evidence_ref] = chunk
    assert pair is not None
    held, colliding = (evidence_of(snapshot, chunk, "q") for chunk in pair)
    ledger = EvidenceLedger()
    ledger.record(EXECUTION, held)
    assert refusal_code(ledger.record(EXECUTION, colliding)) is EvidenceRefusalCode.EVIDENCE_REF_COLLISION
    assert ledger.records(EXECUTION) == (held,)


def test_the_same_chunk_from_a_different_snapshot_is_refused_and_the_ledger_is_unchanged():
    bigger = build_snapshot((*small_corpus(), doc("extra", "An additional document that makes this a different snapshot.")), SCHEME)
    chunk = chunk_of(SNAPSHOT, "audit")
    held = evidence_of(SNAPSHOT, chunk, "q1")
    ledger = EvidenceLedger()
    ledger.record(EXECUTION, held)
    assert refusal_code(ledger.record(EXECUTION, evidence_of(bigger, chunk, "q2"))) is EvidenceRefusalCode.SNAPSHOT_CONFLICT
    assert ledger.records(EXECUTION) == (held,)  # the refused query was not added to the held record


def test_the_same_chunks_recorded_from_many_threads_at_once_keep_every_query_and_one_record_each():
    ledger = EvidenceLedger()
    chunks = [chunk_of(SNAPSHOT, source) for source in ("ops", "audit", "grid", "blog", "mirror")]
    workers, per_worker = 12, 10
    barrier = threading.Barrier(workers)
    failures: list[BaseException] = []

    def work(worker: int) -> None:
        try:
            barrier.wait()
            for turn in range(per_worker):
                for chunk in chunks:
                    ledger.record(EXECUTION, evidence_of(SNAPSHOT, chunk, f"query {worker}-{turn}"))
        except BaseException as error:  # pragma: no cover - reported below
            failures.append(error)

    threads = [threading.Thread(target=work, args=(n,)) for n in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert failures == []
    expected = tuple(sorted(query_id(f"query {w}-{t}") for w in range(workers) for t in range(per_worker)))
    held = ledger.records(EXECUTION)
    assert len(held) == len(chunks) and all(record.retrieved_by == expected for record in held)


def test_a_slow_merge_cannot_make_two_threads_lose_each_others_queries_because_recording_is_atomic(monkeypatch):
    real_merge = merge_evidence

    def slow_merge(held, incoming):
        time.sleep(0.01)  # a scheduling point between reading the held record and writing the merged one
        return real_merge(held, incoming)

    monkeypatch.setattr("eidos.agents.evidence_ledger.merge_evidence", slow_merge)
    ledger = EvidenceLedger()
    chunk = chunk_of(SNAPSHOT, "audit")
    ledger.record(EXECUTION, evidence_of(SNAPSHOT, chunk, "seed"))
    workers = 8
    barrier = threading.Barrier(workers)

    def work(worker: int) -> None:
        barrier.wait()
        ledger.record(EXECUTION, evidence_of(SNAPSHOT, chunk, f"query {worker}"))

    threads = [threading.Thread(target=work, args=(n,)) for n in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    (held,) = ledger.records(EXECUTION)
    assert held.retrieved_by == tuple(sorted([query_id("seed"), *(query_id(f"query {n}") for n in range(workers))]))


# --- independence is resolved over the set of cited evidence --------------------------------------------------------------------


def filled_ledger(snapshot=SNAPSHOT, sources=("ops", "audit", "grid", "blog", "mirror")) -> EvidenceLedger:
    ledger = EvidenceLedger()
    for source in sources:
        for chunk in snapshot.chunks:
            if chunk.source_id == source:
                ledger.record(EXECUTION, evidence_of(snapshot, chunk))
    return ledger


def refs_of(ledger: EvidenceLedger, *sources: str) -> list[str]:
    return [r.evidence_ref for r in ledger.records(EXECUTION) if r.chunk.source_id in sources]


def test_the_ledger_resolves_independence_by_declared_source_with_the_declarations_it_is_given():
    ledger = filled_ledger()
    cited = refs_of(ledger, "audit", "blog", "ops", "mirror")
    assert ledger.resolve_independence(EXECUTION, cited, derived_from=SNAPSHOT.derivation_map).sources == ("audit", "mirror", "ops")
    assert ledger.resolve_independence(EXECUTION, cited, derived_from={}).sources == ("audit", "blog", "mirror", "ops")  # no declaration, no collapse


def test_the_declared_derivations_are_a_required_argument_so_leaving_them_out_is_never_a_silent_default():
    ledger = filled_ledger()
    with pytest.raises(TypeError):
        ledger.resolve_independence(EXECUTION, refs_of(ledger, "audit"))


def test_a_reference_another_execution_holds_is_reported_as_unresolved_never_counted():
    ledger = EvidenceLedger()
    audit, grid = evidence_of(SNAPSHOT, chunk_of(SNAPSHOT, "audit")), evidence_of(SNAPSHOT, chunk_of(SNAPSHOT, "grid"))
    ledger.record(EXECUTION, audit)
    ledger.record(OTHER_EXECUTION, grid)
    resolution = ledger.resolve_independence(EXECUTION, [audit.evidence_ref, grid.evidence_ref], derived_from={})
    assert resolution.sources == ("audit",) and resolution.unresolved == (grid.evidence_ref,)


def test_resolving_independence_changes_nothing_in_the_ledger():
    ledger = filled_ledger()
    before = ledger.records(EXECUTION)
    ledger.resolve_independence(EXECUTION, refs_of(ledger, "ops") + ["evidence:" + "0" * 16], derived_from=SNAPSHOT.derivation_map)
    assert ledger.records(EXECUTION) == before


def test_the_resolution_does_not_depend_on_the_order_of_the_citations():
    ledger = filled_ledger()
    cited = refs_of(ledger, "audit", "blog", "ops", "mirror", "grid")
    expected = ledger.resolve_independence(EXECUTION, cited, derived_from=SNAPSHOT.derivation_map)
    generator = random.Random(11)
    for _ in range(20):
        generator.shuffle(cited)
        assert ledger.resolve_independence(EXECUTION, cited + cited[:3], derived_from=SNAPSHOT.derivation_map) == expected


# --- V1.2 documents are mapped into the knowledge identity without touching anything recorded (D-210) -------------------------------


def query_answers(request):
    query = {argument.name: argument.value for argument in request.arguments}["query"]
    documents = {
        "first query": (ToolDocument(document_id="doc-replay", content=REPLAY), ToolDocument(document_id="doc-events", content=EVENTS)),
        "second query": (ToolDocument(document_id="doc-replay", content=REPLAY),),
    }
    return ToolResult(documents=documents[query])


class Rig:
    """A real mission, store and tool gate over a scripted provider that answers ``first query`` with two documents and ``second query`` with one of them."""

    def __init__(self):
        self.state = make_tool_mission(min_independent_evidence=2)
        self.context = attempt_context(self.state)
        self.execution_id = self.state.execution_id
        self.store = InMemoryArtifactStore()
        self.gate = ToolGate(registry=search_registry(), port=ScriptedToolPort(query_answers), store=self.store)

    def ask(self, query: str) -> tuple[ArtifactRef, ...]:
        outcome = self.gate.call(self.context, TOOL_ID, {"query": query})
        assert outcome.refs, outcome
        return outcome.refs

    def supply(self, ref: str, content: str) -> ArtifactRef:
        self.store.put_supplied(self.execution_id, artifact(ref, content))
        return ArtifactRef(ref)

    def snapshot_of_what_was_recorded(self):
        return (self.store.supplied(self.execution_id), self.gate.invocations)


def test_a_tool_document_reached_by_two_queries_is_two_v1_2_references_and_one_knowledge_identity():
    rig = Rig()
    first, second = rig.ask("first query"), rig.ask("second query")
    replay_first, replay_second = first[0], second[0]
    assert replay_first != replay_second  # V1.2 keys a retrieved document by a reference that embeds the request digest
    assert parse_tool_document_ref(replay_first)[0::2] == parse_tool_document_ref(replay_second)[0::2] == (TOOL_ID, "doc-replay")
    resolved = resolve_supplied_evidence(rig.store, rig.execution_id, [replay_first, replay_second])
    evidence = [entry.evidence for entry in resolved]
    assert all(isinstance(e, EvidenceRecord) for e in evidence)
    assert evidence[0] == evidence[1] == record_or_fail(legacy_tool_record(TOOL_ID, "doc-replay", REPLAY))


def test_a_v1_2_verifier_counts_the_repeat_twice_and_the_resolver_counts_it_once_and_neither_changes_the_other():
    rig = Rig()
    first, second = rig.ask("first query"), rig.ask("second query")
    every_ref = (*first, *second)
    assert len(every_ref) == 3
    rig.store.put_step_artifact(rig.execution_id, StepId("analyse"), artifact("artifact:analyse", "Analysis.", *every_ref))
    agent = VerificationAgent(store=rig.store)
    predecessors = (succeeded_result("analyse"),)
    before = agent.report(rig.context, predecessors)
    assert "3 distinct supplied source(s) reached, 2 required" in next(r for r in before.rules if r.rule is Rule.MINIMUM_DISTINCT_SOURCES).detail

    ledger = EvidenceLedger()
    for entry in resolve_supplied_evidence(rig.store, rig.execution_id, every_ref):
        ledger.record(rig.execution_id, entry.evidence)
    resolution = ledger.resolve_independence(rig.execution_id, [r.evidence_ref for r in ledger.records(rig.execution_id)], derived_from={})
    assert resolution.source_count == 2 and len(ledger.records(rig.execution_id)) == 2  # replay once, events once

    assert agent.report(rig.context, predecessors) == before  # the verifier reads the same store and answers exactly as before


def test_resolving_writes_nothing_no_artifact_reference_invocation_or_produced_artifact_changes():
    rig = Rig()
    refs = (*rig.ask("first query"), *rig.ask("second query"), rig.supply("brief-1", "A caller document."))
    rig.store.put_step_artifact(rig.execution_id, StepId("analyse"), artifact("artifact:analyse", "Analysis.", *refs))
    before = (rig.snapshot_of_what_was_recorded(), rig.store.get(rig.execution_id, ArtifactRef("artifact:analyse")))
    resolve_supplied_evidence(rig.store, rig.execution_id, refs)
    resolve_supplied_evidence(rig.store, rig.execution_id, [*refs, ArtifactRef("artifact:analyse"), ArtifactRef("ghost")])
    assert (rig.snapshot_of_what_was_recorded(), rig.store.get(rig.execution_id, ArtifactRef("artifact:analyse"))) == before
    assert rig.gate.invocations[0].tool_id == TOOL_ID and len(rig.gate.invocations) == 2


def test_the_resolver_needs_nothing_from_a_store_but_the_ability_to_list_its_supplied_artifacts():
    rig = Rig()
    refs = rig.ask("first query")

    class ReadOnlyView:
        def supplied(self, execution_id):
            return rig.store.supplied(execution_id)

    assert resolve_supplied_evidence(ReadOnlyView(), rig.execution_id, refs) == resolve_supplied_evidence(rig.store, rig.execution_id, refs)


def test_a_caller_supplied_document_is_identified_by_its_reference_and_its_normalised_content():
    rig = Rig()
    ref = rig.supply("brief-1", "Line one\r\nline two")
    (entry,) = resolve_supplied_evidence(rig.store, rig.execution_id, [ref])
    assert entry == ArtifactEvidence(artifact_ref=ref, evidence=record_or_fail(legacy_supplied_record("brief-1", "Line one\nline two")))
    assert entry.evidence.chunk.text == "Line one\nline two" and entry.refusal is None


def test_identical_text_under_two_supplied_references_is_two_sources_and_one_tool_document_under_two_queries_is_one():
    rig = Rig()
    one, two = rig.supply("brief-1", REPLAY), rig.supply("brief-2", REPLAY)
    tool_refs = (*rig.ask("first query"), *rig.ask("second query"))
    entries = resolve_supplied_evidence(rig.store, rig.execution_id, [one, two, *tool_refs])
    ledger = EvidenceLedger()
    for entry in entries:
        ledger.record(rig.execution_id, entry.evidence)
    resolution = ledger.resolve_independence(rig.execution_id, [e.evidence.evidence_ref for e in entries], derived_from={})
    assert len(entries) == 5 and len(ledger.records(rig.execution_id)) == 4  # brief-1, brief-2, tool replay, tool events
    assert resolution.source_count == 4 and len(resolution.documents) == 4  # a document is a source's copy of some content: REPLAY under three sources, EVENTS under one
    assert len({e.evidence.chunk.document_id for e in entries}) == 2  # ...but there are only two distinct contents


def test_the_request_digest_in_a_tool_reference_takes_no_part_in_the_identity_but_the_tool_and_document_do():
    rig = Rig()
    ref_a = rig.supply(str(tool_document_ref(TOOL_ID, "1" * 64, "doc-x")), "The same text.")
    ref_b = rig.supply(str(tool_document_ref(TOOL_ID, "2" * 64, "doc-x")), "The same text.")
    ref_c = rig.supply(str(tool_document_ref(TOOL_ID, "1" * 64, "doc-y")), "The same text.")
    ref_d = rig.supply(str(tool_document_ref("docs/other", "1" * 64, "doc-x")), "The same text.")
    by_ref = {e.artifact_ref: e.evidence for e in resolve_supplied_evidence(rig.store, rig.execution_id, [ref_a, ref_b, ref_c, ref_d])}
    a, b, c, d = by_ref[ref_a], by_ref[ref_b], by_ref[ref_c], by_ref[ref_d]
    assert a == b
    assert len({a.chunk.source_id, c.chunk.source_id, d.chunk.source_id}) == 3


def test_a_supplied_reference_shaped_like_a_tool_reference_is_read_as_the_tool_document_it_names():
    """The V1.2 convention decides: a reference ``tool_document_ref`` could have made is a tool document (a known limitation, decisions.md D-224)."""
    rig = Rig()
    ref = rig.supply(f"tool:{TOOL_ID}:abc:doc-replay", REPLAY)
    (entry,) = resolve_supplied_evidence(rig.store, rig.execution_id, [ref])
    assert entry.evidence == record_or_fail(legacy_tool_record(TOOL_ID, "doc-replay", REPLAY))


def test_a_document_that_changed_between_queries_is_one_source_with_two_documents():
    rig = Rig()
    a = rig.supply(str(tool_document_ref(TOOL_ID, "1" * 64, "doc-x")), "The text as first served.")
    b = rig.supply(str(tool_document_ref(TOOL_ID, "2" * 64, "doc-x")), "The text as later served.")
    by_ref = {e.artifact_ref: e.evidence for e in resolve_supplied_evidence(rig.store, rig.execution_id, [a, b])}
    first, second = by_ref[a], by_ref[b]
    assert first.chunk.source_id == second.chunk.source_id and first.chunk.document_id != second.chunk.document_id
    ledger = EvidenceLedger()
    for record in (first, second):
        ledger.record(rig.execution_id, record)
    resolution = ledger.resolve_independence(rig.execution_id, [first.evidence_ref, second.evidence_ref], derived_from={})
    assert resolution.source_count == 1 and len(resolution.documents) == 2


def test_what_is_not_a_supplied_artifact_of_the_execution_is_refused_never_guessed():
    rig = Rig()
    supplied = rig.supply("brief-1", "A caller document.")
    rig.store.put_step_artifact(rig.execution_id, StepId("analyse"), artifact("artifact:analyse", "Analysis.", supplied))
    entries = resolve_supplied_evidence(rig.store, rig.execution_id, [supplied, ArtifactRef("artifact:analyse"), ArtifactRef("ghost")])
    codes = {str(e.artifact_ref): (e.refusal.code if e.refusal else None) for e in entries}
    assert codes == {"brief-1": None, "artifact:analyse": EvidenceRefusalCode.NOT_SUPPLIED, "ghost": EvidenceRefusalCode.NOT_SUPPLIED}
    other = resolve_supplied_evidence(rig.store, OTHER_EXECUTION, [supplied])
    assert [e.refusal.code for e in other] == [EvidenceRefusalCode.NOT_SUPPLIED]  # a store is namespaced by execution


def test_an_empty_supplied_document_is_refused_as_not_evidence():
    rig = Rig()
    ref = rig.supply("empty", "")
    (entry,) = resolve_supplied_evidence(rig.store, rig.execution_id, [ref])
    assert entry.evidence is None and entry.refusal.code is EvidenceRefusalCode.EMPTY_DOCUMENT


def test_one_result_per_distinct_reference_ordered_by_reference_whatever_the_input_order_or_repetition():
    rig = Rig()
    refs = [rig.supply(name, f"Document {name}.") for name in ("delta", "alpha", "charlie", "bravo")]
    expected = resolve_supplied_evidence(rig.store, rig.execution_id, refs)
    assert [str(e.artifact_ref) for e in expected] == ["alpha", "bravo", "charlie", "delta"]
    generator = random.Random(3)
    for _ in range(10):
        shuffled = refs + refs[:2]
        generator.shuffle(shuffled)
        assert resolve_supplied_evidence(rig.store, rig.execution_id, shuffled) == expected
    assert resolve_supplied_evidence(rig.store, rig.execution_id, []) == ()


def test_an_artifact_result_is_evidence_or_a_refusal_never_both_and_never_neither():
    record = record_or_fail(legacy_supplied_record("brief-1", "A caller document."))
    refusal = EvidenceRefusal(code=EvidenceRefusalCode.NOT_SUPPLIED, message="not supplied")
    ArtifactEvidence(artifact_ref=ArtifactRef("brief-1"), evidence=record)
    ArtifactEvidence(artifact_ref=ArtifactRef("brief-1"), refusal=refusal)
    for fields in ({}, {"evidence": record, "refusal": refusal}):
        with pytest.raises(ValidationError, match="never both and never neither"):
            ArtifactEvidence(artifact_ref=ArtifactRef("brief-1"), **fields)


def test_the_resolver_produces_records_only_it_does_not_record_them_the_caller_decides():
    rig = Rig()
    ref = rig.supply("brief-1", "A caller document.")
    ledger = EvidenceLedger()
    (entry,) = resolve_supplied_evidence(rig.store, rig.execution_id, [ref])
    assert ledger.records(rig.execution_id) == ()
    ledger.record(rig.execution_id, entry.evidence)
    assert ledger.records(rig.execution_id) == (entry.evidence,)


# --- identity does not depend on the hash seed ---------------------------------------------------------------------------------------

STORY = r"""
import hashlib, sys
sys.path[:0] = ['src', 'tests/support']
from eidos.agents import EvidenceLedger, InMemoryArtifactStore, ToolDocument, ToolGate, ToolResult, resolve_supplied_evidence
from eidos.contracts import ArtifactRef
from eidos.knowledge import build_snapshot
from eidos_knowledge_factories import SCHEME, chunk_of, evidence_of, small_corpus
from eidos_search_fixture import TOOL_ID, ScriptedToolPort, attempt_context, make_tool_mission, search_registry

def answers(request):
    query = {a.name: a.value for a in request.arguments}["query"]
    return ToolResult(documents=(ToolDocument(document_id="doc-replay", content="Replay one."), ToolDocument(document_id="doc-events", content="Events " + query)))

state = make_tool_mission()
store = InMemoryArtifactStore()
gate = ToolGate(registry=search_registry(), port=ScriptedToolPort(answers), store=store)
refs = [ref for query in ("first query", "second query") for ref in gate.call(attempt_context(state), TOOL_ID, {"query": query}).refs]
from eidos.agents import Artifact
store.put_supplied(state.execution_id, Artifact(ref=ArtifactRef("brief-1"), content_type="text/plain", content="A caller document."))
entries = resolve_supplied_evidence(store, state.execution_id, [*refs, ArtifactRef("brief-1"), ArtifactRef("ghost")])
snapshot = build_snapshot(small_corpus(), SCHEME)
ledger = EvidenceLedger()
for entry in entries:
    if entry.evidence is not None:
        ledger.record(state.execution_id, entry.evidence)
for chunk in snapshot.chunks:
    ledger.record(state.execution_id, evidence_of(snapshot, chunk, "q1"))
    ledger.record(state.execution_id, evidence_of(snapshot, chunk, "q2"))
cited = [r.evidence_ref for r in ledger.records(state.execution_id)] + ["evidence:" + "0" * 16]
resolution = ledger.resolve_independence(state.execution_id, cited, derived_from=snapshot.derivation_map)
digest = hashlib.sha256()
for entry in entries:
    digest.update(entry.model_dump_json().encode())
digest.update(resolution.model_dump_json().encode())
digest.update("".join(r.model_dump_json() for r in ledger.records(state.execution_id)).encode())
print(digest.hexdigest())
print(len(entries), len(ledger.records(state.execution_id)), resolution.source_count, len(resolution.unresolved))
"""


@functools.lru_cache(maxsize=None)
def story_digest(seed: str, summary: bool = False) -> str:
    completed = subprocess.run([sys.executable, "-c", STORY], capture_output=True, text=True, cwd=ROOT, env=dict(os.environ, PYTHONHASHSEED=seed))
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip().splitlines()[0] if not summary else completed.stdout.strip().splitlines()[1]


@pytest.mark.parametrize("seed", ["1", "42", "112233", "2718281828"])
def test_the_legacy_identities_the_ledger_and_the_resolution_are_identical_under_any_hash_seed(seed):
    assert story_digest(seed) == story_digest("0")


def test_the_story_really_reaches_the_ledger_and_the_resolution():
    # 6 results (four tool references, brief-1, and a ghost that is refused); 17 records (13 chunks, brief-1, the tool's replay document, and its events
    # document as first served and as later served); 7 sources (ops, audit, grid and mirror, the blog collapsing onto the audit, and the three V1.2 sources);
    # the one unknown evidence reference reported.
    assert story_digest("3", summary=True) == "6 17 7 1"
