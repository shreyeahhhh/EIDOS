"""Counting independent sources (decisions.md D-209, D-221; V1.3 Step 2).

The rule under test: a cited document that declares a direct origin which is also cited is set aside, and the distinct declared sources of what remains
are counted. Different sources stay distinct whatever their content, derivation is declared between documents, never inferred, and never followed as a chain.
"""

import itertools
import random

import pytest

from eidos.knowledge import DocumentRef, build_snapshot, independent_source_count, independent_sources
from eidos_knowledge_factories import BLOG_POST, GRID_AGREEMENT, OPS_MANUAL, SAFETY_AUDIT, SCHEME, doc, ref_of, small_corpus


def named(name: str, source: str) -> DocumentRef:
    return ref_of(source, f"the text of document {name}")


A, B, C, D = named("a", "s1"), named("b", "s2"), named("c", "s3"), named("d", "s4")


# --- the consequences ruled in D-209 ---------------------------------------------------------------------------------------------


def test_the_same_chunk_retrieved_again_is_one_source():
    snapshot = build_snapshot(small_corpus(), SCHEME)
    chunk = next(c for c in snapshot.chunks if c.source_id == "grid")
    assert independent_sources([chunk.document_ref, chunk.document_ref, chunk.document_ref], snapshot.derivation_map) == ("grid",)


def test_several_chunks_of_one_document_are_one_source():
    snapshot = build_snapshot(small_corpus(), SCHEME)
    chunks = [c for c in snapshot.chunks if c.source_id == "ops"]
    assert len(chunks) == 4
    assert independent_source_count([c.document_ref for c in chunks], snapshot.derivation_map) == 1


def test_several_documents_under_one_declared_source_are_one_source():
    first, second, third = ref_of("ops", "first document"), ref_of("ops", "second document"), ref_of("ops", "third document")
    assert independent_sources([first, second, third], {}) == ("ops",)


def test_identical_content_under_different_declared_sources_is_separate_sources():
    snapshot = build_snapshot(small_corpus(), SCHEME)
    ops = ref_of("ops", OPS_MANUAL)
    mirror = ref_of("mirror", OPS_MANUAL)
    assert ops.document_id == mirror.document_id
    assert independent_sources([ops, mirror], snapshot.derivation_map) == ("mirror", "ops")
    assert independent_source_count([mirror], snapshot.derivation_map) == 1


def test_known_derived_content_collapses_through_a_declared_derivation():
    snapshot = build_snapshot(small_corpus(), SCHEME)  # the blog is declared derived from the audit
    audit, blog = ref_of("audit", SAFETY_AUDIT), ref_of("blog", BLOG_POST)
    assert independent_sources([audit, blog], snapshot.derivation_map) == ("audit",)
    assert independent_sources([blog], snapshot.derivation_map) == ("blog",)  # the origin was not cited, so nothing collapses


def test_undeclared_derivation_is_not_inferred_from_similarity_or_matching_text():
    undeclared = build_snapshot(
        (doc("audit", SAFETY_AUDIT), doc("blog", BLOG_POST), doc("copy", SAFETY_AUDIT), doc("grid", GRID_AGREEMENT)), SCHEME
    )
    audit, blog, copy = ref_of("audit", SAFETY_AUDIT), ref_of("blog", BLOG_POST), ref_of("copy", SAFETY_AUDIT)
    assert undeclared.derivation_map == {}
    assert independent_sources([audit, blog, copy], undeclared.derivation_map) == ("audit", "blog", "copy")


# --- the four points ruled in D-221 ----------------------------------------------------------------------------------------------


def test_point_one_content_identity_never_collapses_two_declared_sources():
    same_text = "identical words in two places"
    assert independent_source_count([ref_of("x", same_text), ref_of("y", same_text), ref_of("z", same_text)], {}) == 3


def test_point_two_derivation_is_between_documents_so_a_source_keeps_its_other_documents():
    other_in_s2 = ref_of("s2", "an independent second document of source two")
    derived = {B: [A]}
    assert independent_sources([A, B], derived) == ("s1",)  # B is set aside
    assert independent_sources([A, B, other_in_s2], derived) == ("s1", "s2")  # source s2 still counts through its other document
    assert independent_sources([B, other_in_s2], derived) == ("s2",)


def test_point_three_a_relationship_is_only_what_was_declared():
    assert independent_sources([A, B], {}) == ("s1", "s2")
    assert independent_sources([A, B], {C: [A]}) == ("s1", "s2")  # a declaration about an uncited document changes nothing here
    assert independent_sources([A, B], {A: [C]}) == ("s1", "s2")


def test_point_four_only_directly_declared_relationships_are_considered():
    chain = {B: [A], C: [B]}  # b derives from a, c derives from b; c does not declare a
    assert independent_sources([A, C], chain) == ("s1", "s3")  # a and c are not related: the middle document was not declared for c and a
    assert independent_sources([A, B, C], chain) == ("s1",)  # every link is cited, each is set aside by its direct origin
    assert independent_sources([B, C], chain) == ("s2",)
    assert independent_sources([A, B], chain) == ("s1",)
    assert independent_sources([C], chain) == ("s3",)
    assert independent_sources([A, C], {B: [A], C: [A]}) == ("s1",)  # declared directly, so it collapses


def test_a_document_derived_from_several_origins_is_set_aside_when_any_of_them_is_cited():
    derived = {D: [B, C]}
    assert independent_sources([D, B], derived) == ("s2",)
    assert independent_sources([D, C], derived) == ("s3",)
    assert independent_sources([D, B, C], derived) == ("s2", "s3")
    assert independent_sources([D, A], derived) == ("s1", "s4")


def test_a_diamond_of_derivations():
    derived = {B: [A], C: [A], D: [B, C]}
    assert independent_sources([B, C, D], derived) == ("s2", "s3")
    assert independent_sources([D, A], derived) == ("s1", "s4")
    assert independent_sources([A, B, C, D], derived) == ("s1",)


# --- shape of the result ---------------------------------------------------------------------------------------------------------


def test_nothing_cited_is_no_source():
    assert independent_sources([], {}) == ()
    assert independent_source_count([], {B: [A]}) == 0
    assert independent_sources(iter(()), {}) == ()


def test_the_result_is_the_sorted_distinct_declared_sources_and_the_count_is_its_length():
    refs = [ref_of(source, f"text {n}") for n, source in enumerate(["zeta", "alpha", "mid", "alpha", "zeta"])]
    assert independent_sources(refs, {}) == ("alpha", "mid", "zeta")
    assert independent_source_count(refs, {}) == 3
    assert isinstance(independent_sources(refs, {}), tuple)


def test_the_order_and_repetition_of_what_was_cited_never_matter():
    derived = {B: [A], C: [B], D: [A]}
    cited = [A, B, C, D]
    expected = independent_sources(cited, derived)
    for order in itertools.permutations(cited):
        assert independent_sources(order, derived) == expected
    assert independent_sources(cited + cited, derived) == expected


def test_any_iterable_of_cited_documents_and_any_collection_of_origins_is_accepted():
    derived_forms = [{B: [A]}, {B: (A,)}, {B: {A}}, {B: frozenset({A})}]
    for derived in derived_forms:
        assert independent_sources(iter([A, B]), derived) == ("s1",)
        assert independent_sources((x for x in [A, B]), derived) == ("s1",)


def test_the_inputs_are_neither_read_more_than_needed_nor_changed():
    derived = {B: [A], C: [B]}
    cited = [A, B, C]
    independent_sources(cited, derived)
    assert cited == [A, B, C] and derived == {B: [A], C: [B]}


def test_documents_the_map_does_not_mention_have_no_declared_origin():
    assert independent_sources([A, B], {D: [C]}) == ("s1", "s2")


# --- through a snapshot ----------------------------------------------------------------------------------------------------------


def test_a_mission_that_cites_every_chunk_of_the_small_corpus_counts_four_sources_not_five_or_thirteen():
    snapshot = build_snapshot(small_corpus(), SCHEME)
    cited = [c.document_ref for c in snapshot.chunks]
    assert len(cited) == 13
    # ops, audit, grid and mirror are separate declared sources; the blog is set aside because the audit, which it declares as its origin, is cited too
    assert independent_sources(cited, snapshot.derivation_map) == ("audit", "grid", "mirror", "ops")


def test_a_mirror_that_declares_its_original_collapses_and_a_mirror_that_does_not_stays_separate():
    plain = build_snapshot((doc("ops", OPS_MANUAL), doc("mirror", OPS_MANUAL)), SCHEME)
    declared = build_snapshot((doc("ops", OPS_MANUAL), doc("mirror", OPS_MANUAL, ref_of("ops", OPS_MANUAL))), SCHEME)
    for snapshot, expected in ((plain, ("mirror", "ops")), (declared, ("ops",))):
        assert independent_sources([c.document_ref for c in snapshot.chunks], snapshot.derivation_map) == expected


# --- properties over seeded random derivation graphs -----------------------------------------------------------------------------


def shadowed_by_origin_first_oracle(cited, derived):
    """The same rule written the other way round: mark what each cited origin sets aside, then collect the sources of what is left."""
    cited_set = set(cited)
    set_aside = set()
    for document, origins in derived.items():
        for origin in origins:
            if origin in cited_set and document in cited_set:
                set_aside.add(document)
    return sorted({d.source_id for d in cited_set if d not in set_aside})


def random_graph(rng):
    documents = [ref_of(f"s{rng.randint(1, 4)}", f"random document {n}") for n in range(rng.randint(1, 9))]
    derived = {}
    for n, document in enumerate(documents):
        origins = [o for o in documents[:n] if rng.random() < 0.3]  # only earlier documents, so there is never a cycle
        if origins:
            derived[document] = origins
    return documents, derived


@pytest.mark.parametrize("seed", range(150))
def test_the_count_agrees_with_the_rule_written_the_other_way_round(seed):
    rng = random.Random(seed)
    documents, derived = random_graph(rng)
    cited = [d for d in documents if rng.random() < 0.6]
    result = independent_sources(cited, derived)
    assert list(result) == shadowed_by_origin_first_oracle(cited, derived)
    assert len(result) <= len({d.source_id for d in cited})
    assert independent_sources(cited, {}) == tuple(sorted({d.source_id for d in cited}))


@pytest.mark.parametrize("seed", range(60))
def test_citing_a_document_from_a_new_source_with_no_declarations_adds_exactly_one(seed):
    rng = random.Random(500 + seed)
    documents, derived = random_graph(rng)
    cited = [d for d in documents if rng.random() < 0.6]
    fresh = ref_of("brand-new-source", "a document nobody derives from")
    assert independent_source_count(cited + [fresh], derived) == independent_source_count(cited, derived) + 1
