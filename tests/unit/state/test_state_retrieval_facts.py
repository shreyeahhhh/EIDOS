"""Retrieval and citation facts as recorded (decisions.md D-218, D-225; V1.3 Step 4, phase A).

What is proven: a fact validates itself, so a mislabelled or tampered fact is unconstructible and a tampered log is refused when it is loaded; the facts belong to a dispatched work node
and nowhere else; and the identifiers this package mirrors from the knowledge package are kept equal to their definitions there.
"""

import json

import pytest
from pydantic import ValidationError

from eidos.contracts import ArtifactRef, PlanStepKind, StepId
from eidos.knowledge import RetrievalFailureKind
from eidos.knowledge.identity import SCHEME_ID_PATTERN, SOURCE_ID_PATTERN, evidence_ref_of
from eidos.runtime import NodeStatus
from eidos.state import (
    NodeSettledPayload,
    RetrievalFacts,
    RetrievalHitFacts,
    RetrievalOutcome,
    StepRecord,
    dump_jsonl,
    evidence_ref_of_chunk_id,
    execution_record,
    load_jsonl,
    replay,
)
from eidos.state import payloads as state_payloads

from eidos_retrieval_fact_factories import (
    KB_ID,
    SCHEME_ID,
    SCORE_KIND,
    SNAPSHOT_ID,
    answer,
    empty_answer,
    failure,
    hex64,
    hit,
    scored_hits,
    settle_with_retrievals,
)
from eidos_state_factories import LogBuilder, baseline_state_and_plan, verify_result, work_result

FAILURES = [outcome for outcome in RetrievalOutcome if outcome is not RetrievalOutcome.RESULT]


# --- an answer, an empty answer and a failure ---------------------------------------------------------------------------------------------


def test_an_answer_carries_what_was_asked_and_the_ranked_hits():
    facts = answer(query=7, top_k=5)
    assert (facts.kb_id, facts.snapshot_id, facts.scheme_id, facts.query_id, facts.top_k) == (KB_ID, SNAPSHOT_ID, SCHEME_ID, hex64(7), 5)
    assert facts.outcome is RetrievalOutcome.RESULT and facts.score_kind == SCORE_KIND
    assert [h.rank for h in facts.hits] == [1, 2, 3] and [h.score for h in facts.hits] == [3.0, 2.0, 1.0]
    assert facts.result_bytes == 900 and facts.elapsed_ms == 3


def test_an_empty_answer_is_a_real_answer():
    facts = empty_answer()
    assert facts.outcome is RetrievalOutcome.RESULT and facts.hits == () and facts.result_bytes == 0


def test_a_result_with_no_scores_carries_no_score_label():
    hits = tuple(hit(rank, score=None) for rank in (1, 2))
    facts = answer(hits=hits, score_kind=None)
    assert all(h.score is None for h in facts.hits) and facts.score_kind is None


@pytest.mark.parametrize("outcome", FAILURES)
def test_a_failure_carries_no_answer(outcome):
    facts = failure(outcome)
    assert facts.hits == () and facts.result_bytes is None and facts.score_kind is None and facts.elapsed_ms == 1


@pytest.mark.parametrize("outcome", FAILURES)
@pytest.mark.parametrize("extra", [dict(hits=(hit(1),)), dict(result_bytes=10), dict(score_kind=SCORE_KIND)], ids=["hits", "bytes", "label"])
def test_a_failure_cannot_carry_any_part_of_an_answer(outcome, extra):
    base = failure(outcome).model_dump()
    with pytest.raises(ValidationError, match="no answer to carry"):
        RetrievalFacts(**(base | extra))


def test_an_answer_says_how_large_it_was():
    with pytest.raises(ValidationError, match="how large"):
        answer(result_bytes=None)


def test_the_outcome_vocabulary_is_a_result_and_the_four_failures_the_port_can_return():
    assert [o.value for o in RetrievalOutcome] == ["result", "unavailable", "request_mismatch", "result_too_large", "malformed_result"]


# --- the fields ---------------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("kb_id", ["", " kb", "k b", "-kb", "x" * 65])
def test_a_knowledge_base_id_has_the_shape_of_a_source_id(kb_id):
    with pytest.raises(ValidationError):
        answer(kb_id=kb_id)


@pytest.mark.parametrize("field", ["snapshot_id", "query_id"])
@pytest.mark.parametrize("value", ["", "abc", "A" * 64, "g" * 64, "a" * 63, "a" * 65])
def test_a_snapshot_or_query_id_is_sixty_four_lower_case_hex_digits(field, value):
    with pytest.raises(ValidationError):
        RetrievalFacts(**(failure().model_dump() | {field: value}))


@pytest.mark.parametrize("label", ["", "/x", "-x", "x y", "x" * 129])
def test_a_score_label_has_the_shape_of_a_scheme_id(label):
    with pytest.raises(ValidationError):
        answer(score_kind=label)


@pytest.mark.parametrize("scheme", ["", "/x", "-x", "x y", "x" * 129])
def test_a_scheme_id_has_the_shape_of_a_scheme_id(scheme):
    with pytest.raises(ValidationError):
        RetrievalFacts(**(failure().model_dump() | {"scheme_id": scheme}))


@pytest.mark.parametrize("top_k", [0, -1, True, 1.5, "3", None])
def test_top_k_is_an_integer_of_at_least_one(top_k):
    with pytest.raises(ValidationError):
        RetrievalFacts(**(failure().model_dump() | {"top_k": top_k}))


@pytest.mark.parametrize("field", ["result_bytes", "elapsed_ms"])
def test_a_size_and_a_time_are_never_negative(field):
    with pytest.raises(ValidationError):
        RetrievalFacts(**(answer().model_dump() | {field: -1}))


def test_a_size_and_a_time_may_be_absent_because_nobody_measured_them():
    facts = answer(elapsed_ms=None)
    assert facts.elapsed_ms is None
    assert failure(elapsed_ms=None).elapsed_ms is None


@pytest.mark.parametrize("field", ["chunk_id", "document_id", "content_digest"])
@pytest.mark.parametrize("value", ["", "abc", "A" * 64, "g" * 64, "a" * 63])
def test_a_hit_names_chunk_document_and_content_by_sixty_four_hex_digits(field, value):
    with pytest.raises(ValidationError):
        RetrievalHitFacts(**(hit(1).model_dump() | {field: value}))


@pytest.mark.parametrize("source", ["", " ops", "o p", "-ops", "x" * 65])
def test_a_hit_names_its_source_by_a_source_id(source):
    with pytest.raises(ValidationError):
        RetrievalHitFacts(**(hit(1).model_dump() | {"source_id": source}))


@pytest.mark.parametrize("value", [0, -1, True, 1.0, "1"])
def test_a_hit_rank_is_an_integer_from_one(value):
    with pytest.raises(ValidationError):
        RetrievalHitFacts(**(hit(1).model_dump() | {"rank": value}))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "0.5"])
def test_a_hit_score_is_a_finite_number_when_present(value):
    with pytest.raises(ValidationError):
        RetrievalHitFacts(**(hit(1).model_dump() | {"score": value}))


def test_a_fact_records_no_text_and_no_query_only_identifiers_and_digests():
    for model in (RetrievalFacts, RetrievalHitFacts):
        assert not [name for name in model.model_fields if "text" in name or name in {"query", "content", "chunk"}], model.__name__
    assert "query_id" in RetrievalFacts.model_fields and "content_digest" in RetrievalHitFacts.model_fields


# --- an answer validates itself: ranks, uniqueness, top_k, scores and order --------------------------------------------------------------


def test_hits_are_ranked_from_one_in_order_with_no_gap_and_no_repeat():
    answer(hits=[hit(1, score=3.0), hit(2, score=2.0)])
    for ranks in ([2, 3], [1, 3], [2, 1], [1, 1], [0, 1]):
        with pytest.raises(ValidationError):
            answer(hits=[hit(rank, chunk=100 + i, score=float(9 - i)) for i, rank in enumerate(ranks)])


def test_a_chunk_is_a_hit_at_most_once():
    with pytest.raises(ValidationError, match="at most once"):
        answer(hits=[hit(1, chunk=5, score=3.0), hit(2, chunk=5, score=2.0)])


def test_an_answer_has_at_most_top_k_hits():
    answer(hits=scored_hits(3), top_k=3)
    with pytest.raises(ValidationError, match="top_k"):
        answer(hits=scored_hits(3), top_k=2)


def test_a_score_is_labelled_and_a_labelled_answer_scores_every_hit():
    with pytest.raises(ValidationError, match="labelled"):
        answer(hits=scored_hits(2), score_kind=None)
    with pytest.raises(ValidationError, match="scores every hit"):
        answer(hits=[hit(1, score=None), hit(2, score=None)], score_kind=SCORE_KIND)
    with pytest.raises(ValidationError):
        answer(hits=[hit(1, score=2.0), hit(2, score=None)], score_kind=SCORE_KIND)


def test_scored_hits_are_ordered_by_score_descending_and_then_chunk_id_ascending():
    answer(hits=[hit(1, chunk=1, score=2.0), hit(2, chunk=2, score=2.0), hit(3, chunk=3, score=1.0)])  # a tie in ascending chunk order
    with pytest.raises(ValidationError, match="ordered"):
        answer(hits=[hit(1, score=1.0), hit(2, score=2.0)])
    with pytest.raises(ValidationError, match="ordered"):
        answer(hits=[hit(1, chunk=9, score=2.0), hit(2, chunk=3, score=2.0)])  # a tie in the wrong chunk order


def test_negative_scores_follow_the_same_order():
    answer(hits=[hit(1, chunk=1, score=-1.0), hit(2, chunk=2, score=-3.0)])
    with pytest.raises(ValidationError, match="ordered"):
        answer(hits=[hit(1, chunk=1, score=-3.0), hit(2, chunk=2, score=-1.0)])


def test_a_fact_is_frozen_and_takes_no_undeclared_field():
    facts = answer()
    with pytest.raises(ValidationError):
        facts.top_k = 9
    with pytest.raises(ValidationError):
        RetrievalFacts(**(facts.model_dump() | {"text": "leaked"}))


# --- tampering: what a fact can no longer say once it is on the log -----------------------------------------------------------------------


def test_facts_round_trip_through_json_and_a_tampered_one_is_rejected():
    facts = answer()
    assert RetrievalFacts.model_validate_json(facts.model_dump_json()) == facts
    for edit in (
        lambda d: d["hits"][0].__setitem__("rank", 2),
        lambda d: d["hits"][0].__setitem__("score", 0.5),
        lambda d: d.__setitem__("top_k", 2),
        lambda d: d["hits"].append(d["hits"][0] | {"rank": 4}),
        lambda d: d["hits"][1].__setitem__("chunk_id", d["hits"][0]["chunk_id"]),
        lambda d: d["hits"][0].__setitem__("content_digest", "xyz"),
        lambda d: d.__setitem__("outcome", "unavailable"),
        lambda d: d.__setitem__("score_kind", None),
    ):
        document = json.loads(facts.model_dump_json())
        edit(document)
        with pytest.raises(ValidationError):
            RetrievalFacts.model_validate_json(json.dumps(document))


# --- what the mirrored identifiers must stay equal to -------------------------------------------------------------------------------------


def test_the_outcome_values_are_a_result_and_the_knowledge_packages_failure_kinds_value_for_value():
    assert {o.value for o in RetrievalOutcome if o is not RetrievalOutcome.RESULT} == {k.value for k in RetrievalFailureKind}
    for kind in RetrievalFailureKind:
        assert RetrievalOutcome(kind.value).name == kind.name


def test_the_identifier_shapes_are_the_knowledge_packages_shapes():
    assert state_payloads._SOURCE_ID == SOURCE_ID_PATTERN
    assert state_payloads._SCHEME_ID == SCHEME_ID_PATTERN


def test_the_evidence_reference_rule_is_the_knowledge_packages_rule():
    for number in (1, 2**200, 12345):
        chunk_id = hex64(number)
        assert evidence_ref_of_chunk_id(chunk_id) == evidence_ref_of(chunk_id) == "evidence:" + chunk_id[:16]
    assert hit(3).evidence_ref == "evidence:" + hit(3).chunk_id[:16]


# --- a node's retrievals and citations ---------------------------------------------------------------------------------------------------


def settled(**fields):
    _, plan = baseline_state_and_plan()
    return NodeSettledPayload(plan_id=plan.plan_id, result=fields.pop("result", work_result("gather")), dispatched=fields.pop("dispatched", True), duration_ms=1, **fields)


def test_the_new_fields_default_to_empty_so_a_settlement_without_them_is_unchanged():
    payload = settled()
    assert payload.retrievals == () and payload.citations == ()


def test_a_dispatched_work_node_carries_its_retrievals_and_citations():
    payload = settled(retrievals=(answer(), failure()), citations=(ArtifactRef("evidence:0123456789abcdef"), ArtifactRef("tool:docs/search_documents:abc:doc-1")))
    assert [r.outcome for r in payload.retrievals] == [RetrievalOutcome.RESULT, RetrievalOutcome.UNAVAILABLE]
    assert payload.citations == ("evidence:0123456789abcdef", "tool:docs/search_documents:abc:doc-1")


def test_a_node_that_was_not_dispatched_has_neither():
    skipped = work_result("gather", status=NodeStatus.SKIPPED)
    for extra in (dict(retrievals=(answer(),)), dict(citations=(ArtifactRef("x"),))):
        with pytest.raises(ValidationError, match="not dispatched"):
            NodeSettledPayload(plan_id=baseline_state_and_plan()[1].plan_id, result=skipped, dispatched=False, **extra)


def test_only_a_work_node_retrieves_or_cites():
    for extra, message in ((dict(retrievals=(answer(),)), "retrieves"), (dict(citations=(ArtifactRef("x"),)), "cites")):
        with pytest.raises(ValidationError, match=message):
            settled(result=verify_result("check"), **extra)


def test_a_node_lists_each_reference_it_cited_once_and_none_is_blank():
    with pytest.raises(ValidationError, match="once"):
        settled(citations=(ArtifactRef("a"), ArtifactRef("a")))
    with pytest.raises(ValidationError, match="blank"):
        settled(citations=(ArtifactRef(""),))


def test_the_step_record_carries_the_same_two_fields_and_only_for_a_settled_step():
    step = StepRecord(
        step_id=StepId("gather"), kind=PlanStepKind.AGENT, depends_on=(), started=True, result=work_result("gather"), dispatched=True,
        retrievals=(answer(),), citations=(ArtifactRef("evidence:0123456789abcdef"),),
    )
    assert step.retrievals[0].query_id == hex64(1) and step.citations == ("evidence:0123456789abcdef",)
    for extra in (dict(retrievals=(answer(),)), dict(citations=(ArtifactRef("x"),))):
        with pytest.raises(ValidationError, match="not settled"):
            StepRecord(step_id=StepId("gather"), kind=PlanStepKind.AGENT, depends_on=(), started=False, **extra)


# --- the log: replay, the JSONL form, old logs, tampering --------------------------------------------------------------------------------


def retrieving_log() -> LogBuilder:
    """A finished, verified mission in which the first node retrieves twice and cites two references, and the second cites one."""
    state, plan = baseline_state_and_plan()
    log = LogBuilder(state, plan)
    log.created(), log.generated(), log.compiled()
    log.started("gather")
    settle_with_retrievals(log, work_result("gather"), (answer(query=1), failure(RetrievalOutcome.REQUEST_MISMATCH, query=2)), ("evidence:0123456789abcdef", "doc:1"))
    log.started("analyse")
    settle_with_retrievals(log, work_result("analyse"), (), ("artifact:gather",))
    log.started("check")
    log.settled(verify_result("check"))
    log.completed(verified=True)
    return log


def test_replay_reproduces_every_recorded_retrieval_and_citation_from_the_log_alone():
    log = retrieving_log()
    assert replay(log.records).state is not None
    gather, analyse, check = execution_record(log.records).steps
    assert [r.outcome for r in gather.retrievals] == [RetrievalOutcome.RESULT, RetrievalOutcome.REQUEST_MISMATCH]
    assert gather.retrievals[0] == answer(query=1) and gather.citations == ("evidence:0123456789abcdef", "doc:1")
    assert analyse.retrievals == () and analyse.citations == ("artifact:gather",)
    assert check.retrievals == () and check.citations == ()


def test_the_facts_do_not_change_the_state_the_reducer_folds():
    state, plan = baseline_state_and_plan()
    plain = LogBuilder(state, plan)
    plain.created(), plain.generated(), plain.compiled()
    for step in ("gather", "analyse"):
        plain.started(step)
        plain.settled(work_result(step))
    plain.started("check")
    plain.settled(verify_result("check"))
    plain.completed(verified=True)
    assert replay(retrieving_log().records).state == replay(plain.records).state


def test_the_jsonl_form_round_trips_every_recorded_fact_exactly():
    log = retrieving_log()
    text = dump_jsonl(log.records)
    loaded = load_jsonl(text)
    assert loaded.rejection is None and loaded.records == tuple(log.records)
    assert dump_jsonl(loaded.records) == text
    assert execution_record(loaded.records) == execution_record(log.records)


def test_a_log_written_before_the_fields_existed_replays_to_the_identical_state_and_record():
    log = retrieving_log()
    text = dump_jsonl(log.records)
    old_text = text.replace(',"retrievals":[]', "").replace(',"citations":[]', "")
    assert '"retrievals":[]' not in old_text and '"citations":[]' not in old_text
    loaded = load_jsonl(old_text)
    assert loaded.rejection is None and loaded.records == tuple(log.records)  # the empty fields come back as they were, and the retrieving node keeps its own
    assert replay(loaded.records).state == replay(log.records).state
    assert execution_record(loaded.records) == execution_record(log.records)


def test_a_log_line_whose_retrieval_fact_was_tampered_with_is_refused_when_the_log_is_loaded():
    text = dump_jsonl(retrieving_log().records)
    assert '"rank":1' in text
    tampered = text.replace('"rank":1', '"rank":2', 1)
    assert tampered != text
    assert load_jsonl(tampered).rejection is not None


def test_a_log_whose_hit_beyond_top_k_was_inserted_is_refused():
    text = dump_jsonl(retrieving_log().records)
    assert '"top_k":5' in text
    assert load_jsonl(text.replace('"top_k":5', '"top_k":2', 1)).rejection is not None
