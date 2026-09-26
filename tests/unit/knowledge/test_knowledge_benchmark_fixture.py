"""The frozen benchmark fixture: its integrity, its strata by construction, and its freeze (decisions.md D-213, D-225 reading 10; V1.3 Step 4, phase C).

Nothing here retrieves. Every check is mechanical and is made from the fixture's own fixed stop list, never from what a retriever returns: the corpus has the shape the design approved
(about 12 documents in about 6 sources and 48 to 60 chunks, a byte-identical mirror, an undeclared restating source, distractors); each chunk is one paragraph of at most 60 words; each
query belongs to the stratum that its definition puts it in; the gold labels resolve; and the whole is pinned by a digest that was recorded before the first retrieval run.
"""

import ast
import random
from pathlib import Path

import pytest

import eidos_retrieval_fixture as fixture
from eidos.knowledge import build_snapshot, canonical_query_text, chunk_spans
from eidos_retrieval_fixture import (
    CHUNKING,
    DOCUMENTS,
    KB_ID,
    MAX_CHUNK_WORDS,
    QUERIES,
    STOP_WORDS,
    build_fixture_snapshot,
    chunk_of,
    content_tokens,
    fixture_digest,
    gold_chunks,
    gold_groups,
    group_of,
    knowledge_documents,
)

FROZEN_DIGEST = "93db0b1f14c7c444073f86c763e891f1ccab92e5259f62351305b374db57df6b"  # recorded 2026-09-25 23:14, before any retrieval run
FROZEN_SNAPSHOT_ID = "b76e15e080adadab784effc727ec8876145b0e2a2ba80b833dce4b043d58491c"
SNAPSHOT = build_fixture_snapshot()
BY_KEY = {d.key: d for d in DOCUMENTS}
TEST = [q for q in QUERIES if q.split == "test"]
DEV = [q for q in QUERIES if q.split == "dev"]


# --- the freeze ----------------------------------------------------------------------------------------------------------------------------


def test_the_fixture_is_exactly_the_one_that_was_frozen_before_any_retrieval_result_was_observed():
    assert fixture_digest() == FROZEN_DIGEST
    assert SNAPSHOT.snapshot_id == FROZEN_SNAPSHOT_ID


def test_the_digest_covers_the_corpus_the_queries_the_gold_labels_the_stop_list_and_the_chunking(monkeypatch):
    base = fixture_digest()
    tweaked = tuple(fixture.FixtureDocument(d.key, d.source_id, (d.paragraphs[0] + " x",) + d.paragraphs[1:]) if d.key == "ops-startup" else d for d in DOCUMENTS)
    monkeypatch.setattr(fixture, "DOCUMENTS", tweaked)
    assert fixture_digest() != base
    monkeypatch.undo()
    monkeypatch.setattr(fixture, "QUERIES", (QUERIES[0].__class__("L01", "test", "lexical", QUERIES[0].text, (("ops-startup", 2),)),) + QUERIES[1:])
    assert fixture_digest() != base  # a changed gold label
    monkeypatch.undo()
    monkeypatch.setattr(fixture, "STOP_WORDS", STOP_WORDS | {"engine"})
    assert fixture_digest() != base
    monkeypatch.undo()
    monkeypatch.setattr(fixture, "CHUNKING", type(CHUNKING)(max_words=50))
    assert fixture_digest() != base
    monkeypatch.undo()
    assert fixture_digest() == base


def test_building_the_snapshot_twice_or_from_shuffled_documents_gives_the_same_snapshot():
    assert build_fixture_snapshot() == SNAPSHOT
    generator = random.Random(9)
    for _ in range(10):
        documents = list(knowledge_documents())
        generator.shuffle(documents)
        assert build_snapshot(documents, CHUNKING) == SNAPSHOT


def test_the_fixture_module_holds_only_ascii_and_imports_no_retrieval():
    path = Path(fixture.__file__)
    text = path.read_text(encoding="utf-8")
    assert all(ord(c) < 128 for c in text)
    imported = {alias.name for node in ast.walk(ast.parse(text)) if isinstance(node, ast.ImportFrom) for alias in node.names}
    assert imported & {"LexicalKnowledgePort", "RetrievalRequest", "RetrievalResult", "KnowledgePort"} == set()
    assert KB_ID == "kestrel-reach"


# --- the shape the design approved -------------------------------------------------------------------------------------------------------


def test_the_corpus_has_twelve_documents_in_six_sources_and_between_forty_eight_and_sixty_chunks():
    assert len(DOCUMENTS) == 12 and len({d.source_id for d in DOCUMENTS}) == 6
    assert 48 <= len(SNAPSHOT.chunks) <= 60 and len(SNAPSHOT.chunks) == 53
    assert {d.source_id for d in DOCUMENTS} == {"ops", "safety", "maint", "grid", "archive", "outreach"}


def test_one_source_holds_several_documents():
    counts = {}
    for d in DOCUMENTS:
        counts[d.source_id] = counts.get(d.source_id, 0) + 1
    assert counts == {"ops": 2, "safety": 2, "maint": 2, "grid": 1, "archive": 1, "outreach": 4}


def test_every_paragraph_is_exactly_one_chunk_of_at_most_sixty_words():
    assert len(SNAPSHOT.chunks) == sum(len(d.paragraphs) for d in DOCUMENTS)
    for d in DOCUMENTS:
        for index, paragraph in enumerate(d.paragraphs):
            assert len(paragraph.split()) <= MAX_CHUNK_WORDS <= 60, (d.key, index)
            assert chunk_of(SNAPSHOT, d.key, index).text == paragraph


def test_no_two_adjacent_paragraphs_fit_one_chunk_so_paragraphs_never_merge():
    for d in DOCUMENTS:
        for left, right in zip(d.paragraphs, d.paragraphs[1:]):
            assert len(left.split()) + len(right.split()) > MAX_CHUNK_WORDS, d.key
        assert len(chunk_spans(d.text, CHUNKING)) == len(d.paragraphs), d.key


def test_the_proxy_for_the_semantic_models_window_holds_the_word_piece_check_itself_waits_for_its_tokenizer():
    """At most 60 words a chunk is well inside the approximately 85 words that fit 128 word pieces (D-215); the authoritative word-piece count needs the tokenizer, at Step 5."""
    assert max(len(c.text.split()) for c in SNAPSHOT.chunks) <= 60 < 85


def test_a_byte_identical_mirror_is_declared_under_a_second_source():
    original, copy = BY_KEY["safety-audit"], BY_KEY["archive-audit-copy"]
    assert original.text == copy.text and original.source_id != copy.source_id
    for index in range(len(original.paragraphs)):
        a, b = chunk_of(SNAPSHOT, "safety-audit", index), chunk_of(SNAPSHOT, "archive-audit-copy", index)
        assert (a.document_id, a.text, a.start, a.end) == (b.document_id, b.text, b.start, b.end)
        assert a.chunk_id != b.chunk_id and a.source_id != b.source_id and group_of(a) == group_of(b)


def test_no_other_chunk_is_a_byte_identical_copy_of_another():
    groups = {}
    for chunk in SNAPSHOT.chunks:
        groups.setdefault(group_of(chunk), []).append(chunk.source_id)
    duplicated = {g: s for g, s in groups.items() if len(s) > 1}
    assert len(duplicated) == 5 and all(sorted(s) == ["archive", "safety"] for s in duplicated.values())


def test_a_source_restates_another_sources_facts_in_other_words_and_declares_nothing():
    assert SNAPSHOT.derivations == ()
    original, restated = BY_KEY["maint-schedule"], BY_KEY["outreach-news-bulletin"]
    for index in range(4):
        a, b = original.paragraphs[index], restated.paragraphs[index]
        assert a != b
        shared = content_tokens(a) & content_tokens(b)
        assert len(shared) < 0.6 * len(content_tokens(b))  # the same facts, in largely other words


def test_at_least_three_distractor_documents_reuse_the_queries_vocabulary_without_being_their_answers():
    distractors = ("outreach-visitor-guide", "outreach-staff-newsletter", "outreach-training-syllabus")
    bait_documents = set()
    for query in QUERIES:
        gold_ids = {c.chunk_id for c in gold_chunks(SNAPSHOT, query)}
        qt = content_tokens(query.text)
        for key in distractors:
            for index, paragraph in enumerate(BY_KEY[key].paragraphs):
                chunk = chunk_of(SNAPSHOT, key, index)
                if chunk.chunk_id not in gold_ids and len(qt & content_tokens(chunk.text)) >= 2:
                    bait_documents.add(key)
    assert bait_documents == set(distractors)


# --- the queries -----------------------------------------------------------------------------------------------------------------------------


def test_there_are_thirty_six_english_queries_six_for_development_and_thirty_frozen_for_test():
    assert len(QUERIES) == 36 and len(TEST) == 30 and len(DEV) == 6
    assert len({q.query_id for q in QUERIES}) == 36 and len({q.text for q in QUERIES}) == 36
    assert all(q.text.isascii() for q in QUERIES)


def test_the_strata_have_the_sizes_the_design_approved():
    def count(items, stratum):
        return sum(1 for q in items if q.stratum == stratum)

    assert [count(TEST, s) for s in ("lexical", "paraphrase", "multi_source", "distractor")] == [8, 10, 6, 6]
    assert [count(DEV, s) for s in ("lexical", "paraphrase", "multi_source", "distractor")] == [2, 2, 1, 1]
    assert {q.stratum for q in QUERIES} == {"lexical", "paraphrase", "multi_source", "distractor"} and {q.split for q in QUERIES} == {"test", "dev"}


def test_every_query_is_in_its_canonical_form_and_names_a_gold_label():
    for q in QUERIES:
        assert canonical_query_text(q.text) == q.text and q.text
        assert q.gold and len(set(q.gold)) == len(q.gold), q.query_id


def test_every_gold_label_resolves_to_exactly_one_chunk_and_names_the_original_never_the_mirror():
    for q in QUERIES:
        for key, paragraph in q.gold:
            assert 0 <= paragraph < len(BY_KEY[key].paragraphs)
            chunk_of(SNAPSHOT, key, paragraph)
            assert key != "archive-audit-copy", q.query_id  # gold is over content-equivalence groups: the mirror's copy is gold through its original


def test_the_gold_of_a_mirrored_chunk_includes_the_mirrors_copy_by_content_equivalence():
    query = next(q for q in QUERIES if q.query_id == "L06")
    chunks = gold_chunks(SNAPSHOT, query)
    assert len(gold_groups(SNAPSHOT, query)) == 1 and sorted(c.source_id for c in chunks) == ["archive", "safety"]


def test_a_gold_group_holds_at_least_one_chunk_and_no_query_has_more_than_nine_gold_groups():
    for q in QUERIES:
        assert 1 <= len(gold_groups(SNAPSHOT, q)) <= 9


# --- each stratum is what its definition says, by construction ---------------------------------------------------------------------------


def overlaps(query):
    qt = content_tokens(query.text)
    return {c.chunk_id: len(qt & content_tokens(c.text)) for c in SNAPSHOT.chunks}


@pytest.mark.parametrize("query", [q for q in QUERIES if q.stratum == "lexical"], ids=lambda q: q.query_id)
def test_a_lexical_overlap_query_shares_at_least_two_content_tokens_with_every_gold_chunk(query):
    shared = overlaps(query)
    assert all(shared[c.chunk_id] >= 2 for c in gold_chunks(SNAPSHOT, query))


@pytest.mark.parametrize("query", [q for q in QUERIES if q.stratum == "paraphrase"], ids=lambda q: q.query_id)
def test_a_paraphrase_query_shares_no_content_token_with_any_gold_chunk(query):
    shared = overlaps(query)
    assert all(shared[c.chunk_id] == 0 for c in gold_chunks(SNAPSHOT, query))


@pytest.mark.parametrize("query", [q for q in QUERIES if q.stratum == "multi_source"], ids=lambda q: q.query_id)
def test_a_multi_source_query_has_gold_chunks_in_at_least_three_sources_even_without_the_mirror(query):
    sources = {c.source_id for c in gold_chunks(SNAPSHOT, query) if c.source_id != "archive"}
    assert len(sources) >= 3


@pytest.mark.parametrize("query", [q for q in QUERIES if q.stratum == "distractor"], ids=lambda q: q.query_id)
def test_a_distractor_bait_query_shares_at_least_two_content_tokens_with_some_chunk_that_is_not_gold(query):
    gold_ids = {c.chunk_id for c in gold_chunks(SNAPSHOT, query)}
    shared = overlaps(query)
    assert max(v for k, v in shared.items() if k not in gold_ids) >= 2


def test_the_content_tokens_are_word_runs_lower_cased_less_the_fixed_stop_list():
    assert content_tokens("How long must the Skerry Gate sensors report normal readings?") == frozenset({"long", "skerry", "gate", "sensors", "report", "normal", "readings"})
    assert content_tokens("the and of") == frozenset()
    assert "the" in STOP_WORDS and "turbine" not in STOP_WORDS and STOP_WORDS == frozenset(sorted(STOP_WORDS))
    assert content_tokens("Alpha alpha BETA") == frozenset({"alpha", "beta"})


def test_the_stop_list_is_a_plain_set_of_lower_case_ascii_words():
    assert all(w.isascii() and w == w.lower() and w.isalpha() for w in STOP_WORDS) and 80 < len(STOP_WORDS) < 200
