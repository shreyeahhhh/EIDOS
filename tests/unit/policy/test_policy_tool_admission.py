"""Deterministic tool admission: every accepted rule, every typed denial, the check order, the budget scope and duplicate service
(decisions.md D-203, invariant 14; V1.2 Step 2). Pure: no server, no clock, no model."""

import inspect

import pytest
from pydantic import ValidationError

from eidos.capabilities import ToolArgumentKind, ToolArgumentSpec, ToolDescriptor, ToolRegistry
from eidos.contracts import ActionId, AutonomyLevel
from eidos.policy import (
    ArgumentViolationCode,
    ToolAdmission,
    ToolDecision,
    ToolDenial,
    ToolDenialCode,
    ToolInvocationRecord,
    admit_tool_call,
    args_digest,
)

from eidos_tool_factories import (
    DEFAULT_ARGUMENTS,
    READ_ACTION,
    SEARCH_TOOL_ID,
    admit,
    invocation,
    limit_spec,
    make_attempt_plan_id,
    make_execution_id,
    make_search_descriptor,
    make_tool_registry,
    query_spec,
)


def denial_of(admission: ToolAdmission) -> ToolDenial:
    assert admission.decision is ToolDecision.DENY, admission
    return admission.denial


# --- the admitted path: what an invocation carries ---------------------------------------------------------------------------


def test_a_call_that_passes_every_rule_is_admitted_with_the_entrys_own_bounds():
    admission = admit()
    assert admission.decision is ToolDecision.INVOKE and admission.denial is None
    assert admission.tool_id == SEARCH_TOOL_ID
    assert admission.args_digest == args_digest(DEFAULT_ARGUMENTS)
    assert (admission.timeout_seconds, admission.max_result_bytes) == (5.0, 4096)


def test_the_granted_timeout_and_size_bound_are_the_entrys_and_change_with_it():
    registry = make_tool_registry(make_search_descriptor(timeout_seconds=1.5, max_result_bytes=77))
    admission = admit(registry=registry)
    assert (admission.timeout_seconds, admission.max_result_bytes) == (1.5, 77)


# --- the precondition: an unset budget is unresolved configuration (D-205 ruling 1) -----------------------------------------------


def test_an_unset_budget_is_unresolved_configuration_denied_with_its_own_typed_code():
    admission = admit(max_tool_calls=None)
    denial = denial_of(admission)
    assert denial.code is ToolDenialCode.BUDGET_UNRESOLVED and "unset" in denial.message and denial.violations == ()
    assert (admission.args_digest, admission.timeout_seconds, admission.max_result_bytes) == (None, None, None)
    assert admission.tool_id == SEARCH_TOOL_ID


@pytest.mark.parametrize("history", [
    (),
    (invocation(arguments={"query": "a"}),),
    (invocation(arguments={"query": "a"}, stored=False),),
    (invocation(),),  # a stored duplicate of this very call: an unset budget serves nothing either
    tuple(invocation(arguments={"query": f"q{n}"}) for n in range(50)),
], ids=["empty", "one-stored", "one-failed", "stored-duplicate", "fifty-stored"])
def test_an_unset_budget_is_never_unlimited_whatever_the_history(history):
    admission = admit(max_tool_calls=None, prior_invocations=history)
    assert denial_of(admission).code is ToolDenialCode.BUDGET_UNRESOLVED


def test_an_unset_budget_is_rejected_before_any_duplicate_lookup_the_history_is_never_read():
    # D-205 item 2: decided ahead of duplicate detection, so a stored duplicate is not served and the history is not even consulted.
    reads = []

    def history():
        reads.append("read")
        yield invocation()

    admission = admit(max_tool_calls=None, prior_invocations=history())
    assert denial_of(admission).code is ToolDenialCode.BUDGET_UNRESOLVED
    assert reads == []
    assert (admission.args_digest, admission.timeout_seconds, admission.max_result_bytes) == (None, None, None)  # no invocation, nothing charged


def test_an_explicit_budget_still_serves_the_stored_duplicate_the_unset_one_would_have_refused():
    stored = (invocation(),)
    assert admit(max_tool_calls=0, prior_invocations=stored).decision is ToolDecision.SERVE_STORED
    assert denial_of(admit(max_tool_calls=None, prior_invocations=stored)).code is ToolDenialCode.BUDGET_UNRESOLVED


def test_an_unset_budget_is_not_silently_zero_it_is_a_different_outcome_from_an_exhausted_one():
    assert denial_of(admit(max_tool_calls=0)).code is ToolDenialCode.BUDGET_EXHAUSTED
    assert denial_of(admit(max_tool_calls=None)).code is ToolDenialCode.BUDGET_UNRESOLVED


@pytest.mark.parametrize("overrides", [
    {},
    {"tool_id": "docs/nope"},
    {"registry": make_tool_registry(make_search_descriptor(read_only=False))},
    {"allowed_actions": ()},
    {"autonomy_level": AutonomyLevel.RECOMMEND_ONLY},
    {"arguments": {"zzz": 1}},
    {"prior_invocations": (invocation(),)},
], ids=["valid-call", "unknown-tool", "not-read-only", "action-not-allowed", "autonomy-too-low", "invalid-arguments", "stored-duplicate"])
def test_the_unset_budget_is_decided_before_every_other_rule(overrides):
    assert denial_of(admit(max_tool_calls=None, **overrides)).code is ToolDenialCode.BUDGET_UNRESOLVED


@pytest.mark.parametrize("bad", [True, False, 1.0, 2.5, float("inf"), float("nan"), "3", b"1", [1]])
def test_a_budget_that_is_set_but_not_an_integer_is_a_programming_error_never_read_as_unlimited(bad):
    with pytest.raises(ValueError):
        admit(max_tool_calls=bad)


def test_any_finite_integer_budget_is_honoured_and_no_ceiling_is_invented():
    many = tuple(invocation(arguments={"query": f"q{n}"}) for n in range(200))
    assert admit(max_tool_calls=10**12).decision is ToolDecision.INVOKE
    assert admit(max_tool_calls=201, prior_invocations=many).decision is ToolDecision.INVOKE
    assert denial_of(admit(max_tool_calls=200, prior_invocations=many)).code is ToolDenialCode.BUDGET_EXHAUSTED


def test_no_admission_input_has_a_default_so_a_budget_is_never_supplied_by_omission():
    assert all(parameter.default is inspect.Parameter.empty for parameter in inspect.signature(admit_tool_call).parameters.values())


# --- rule 1: the pinned allowlist -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("tool_id", [
    "docs/other_tool", "other/search_documents", "Docs/search_documents", "docs/Search_documents", " docs/search_documents",
    "docs/search_documents ", "search_documents", "docs/search", "", "docs/search_documents/x",
])
def test_a_tool_not_exactly_in_the_allowlist_is_denied_unknown_tool(tool_id):
    denial = denial_of(admit(tool_id=tool_id))
    assert denial.code is ToolDenialCode.UNKNOWN_TOOL and denial.message


def test_an_empty_allowlist_admits_nothing():
    assert denial_of(admit(registry=ToolRegistry(tools=()))).code is ToolDenialCode.UNKNOWN_TOOL


# --- rule 2: read-only, from the allowlist entry and nothing a provider says -----------------------------------------------------


def test_an_entry_not_declared_read_only_is_denied_whatever_else_is_true():
    admission = admit(registry=make_tool_registry(make_search_descriptor(read_only=False)), autonomy_level=AutonomyLevel.AUTHORIZED_AUTONOMOUS)
    assert denial_of(admission).code is ToolDenialCode.NOT_READ_ONLY


def test_a_name_that_merely_sounds_read_only_is_not_trusted_the_entry_decides():
    registry = make_tool_registry(make_search_descriptor(tool_name="read_only_search", read_only=False))
    assert denial_of(admit(registry=registry, tool_id="docs/read_only_search")).code is ToolDenialCode.NOT_READ_ONLY


def test_admission_has_no_input_a_providers_own_claim_about_a_tool_could_arrive_through():
    parameters = set(inspect.signature(admit_tool_call).parameters)
    assert parameters == {
        "registry", "tool_id", "arguments", "execution_id", "plan_id", "allowed_actions", "autonomy_level", "max_tool_calls", "prior_invocations",
    }
    assert not any("annot" in name or "hint" in name or "claim" in name for name in parameters)


# --- rule 3: the exact allowed action -------------------------------------------------------------------------------------------


def test_the_entrys_action_must_be_exactly_one_of_the_missions_allowed_actions():
    assert admit(allowed_actions=(ActionId("other"), READ_ACTION, ActionId("more"))).decision is ToolDecision.INVOKE
    assert admit(allowed_actions=frozenset({READ_ACTION})).decision is ToolDecision.INVOKE


@pytest.mark.parametrize("allowed", [
    (), (ActionId("read_document"),), (ActionId("read_documents_x"),), (ActionId("READ_DOCUMENTS"),), (ActionId(" read_documents"),),
    (ActionId("read_documents "),), (ActionId("read"),), (ActionId("read_repository"), ActionId("query_monitoring")),
])
def test_anything_short_of_an_exact_match_is_denied_action_not_allowed(allowed):
    assert denial_of(admit(allowed_actions=allowed)).code is ToolDenialCode.ACTION_NOT_ALLOWED


# --- rule 4: autonomy at or above safe-read-only --------------------------------------------------------------------------------


@pytest.mark.parametrize("level", [AutonomyLevel.SAFE_READ_ONLY, AutonomyLevel.REVERSIBLE, AutonomyLevel.HUMAN_APPROVAL_REQUIRED, AutonomyLevel.AUTHORIZED_AUTONOMOUS])
def test_autonomy_level_one_and_above_is_admitted(level):
    assert admit(autonomy_level=level).decision is ToolDecision.INVOKE


def test_recommend_only_autonomy_is_denied_autonomy_too_low():
    denial = denial_of(admit(autonomy_level=AutonomyLevel.RECOMMEND_ONLY))
    assert denial.code is ToolDenialCode.AUTONOMY_TOO_LOW and "0" in denial.message


# --- rule 5: the argument schema ------------------------------------------------------------------------------------------------


def violations_of(arguments, registry=None):
    kwargs = {"arguments": arguments} | ({"registry": registry} if registry else {})
    denial = denial_of(admit(**kwargs))
    assert denial.code is ToolDenialCode.INVALID_ARGUMENTS and denial.violations
    return [(violation.name, violation.code) for violation in denial.violations]


def test_the_optional_argument_may_be_omitted_and_supplied():
    assert admit(arguments={"query": "x"}).decision is ToolDecision.INVOKE
    assert admit(arguments={"query": "x", "limit": 3}).decision is ToolDecision.INVOKE


def test_an_unknown_argument_is_a_schema_mismatch():
    assert violations_of({"query": "x", "foo": 1}) == [("foo", ArgumentViolationCode.UNKNOWN_ARGUMENT)]


def test_a_missing_required_argument_is_a_schema_mismatch():
    assert violations_of({"limit": 2}) == [("query", ArgumentViolationCode.MISSING_ARGUMENT)]
    assert violations_of({}) == [("query", ArgumentViolationCode.MISSING_ARGUMENT)]


def test_an_entirely_different_schema_reports_both_the_stranger_and_the_gap():
    assert violations_of({"q": "x"}) == [("q", ArgumentViolationCode.UNKNOWN_ARGUMENT), ("query", ArgumentViolationCode.MISSING_ARGUMENT)]


@pytest.mark.parametrize("value", [5, None, ["a"], b"x", 1.5, True, {"a": 1}])
def test_a_string_argument_must_be_a_string(value):
    assert violations_of({"query": value}) == [("query", ArgumentViolationCode.WRONG_TYPE)]


@pytest.mark.parametrize("value", ["3", 3.0, True, False, None, [3], b"3"])
def test_an_integer_argument_must_be_an_integer_and_a_boolean_is_not_one(value):
    assert violations_of({"query": "x", "limit": value}) == [("limit", ArgumentViolationCode.WRONG_TYPE)]


@pytest.mark.parametrize("value, ok", [("", False), ("a", True), ("x" * 256, True), ("x" * 257, False)])
def test_a_string_argument_is_bounded_in_characters_at_both_ends(value, ok):
    admission = admit(arguments={"query": value})
    assert (admission.decision is ToolDecision.INVOKE) is ok
    if not ok:
        assert violations_of({"query": value}) == [("query", ArgumentViolationCode.OUT_OF_BOUNDS)]


@pytest.mark.parametrize("value, ok", [(0, False), (1, True), (10, True), (11, False), (-4, False)])
def test_an_integer_argument_is_bounded_in_value_at_both_ends(value, ok):
    assert (admit(arguments={"query": "x", "limit": value}).decision is ToolDecision.INVOKE) is ok


def test_string_bounds_count_characters_not_bytes():
    assert admit(arguments={"query": "€" * 256}).decision is ToolDecision.INVOKE  # 256 characters, 768 bytes


def test_every_violation_is_reported_in_a_fixed_order_by_name_then_code():
    reported = violations_of({"zzz": 1, "query": 5, "limit": 0, "aaa": "x"})
    assert reported == [
        ("aaa", ArgumentViolationCode.UNKNOWN_ARGUMENT), ("limit", ArgumentViolationCode.OUT_OF_BOUNDS),
        ("query", ArgumentViolationCode.WRONG_TYPE), ("zzz", ArgumentViolationCode.UNKNOWN_ARGUMENT),
    ]
    assert reported == violations_of({"limit": 0, "aaa": "x", "query": 5, "zzz": 1})  # the order arguments were given in changes nothing


def test_a_tool_with_no_arguments_accepts_only_none():
    registry = make_tool_registry(make_search_descriptor(arguments=()))
    assert admit(registry=registry, arguments={}).decision is ToolDecision.INVOKE
    assert violations_of({"query": "x"}, registry) == [("query", ArgumentViolationCode.UNKNOWN_ARGUMENT)]


def test_a_required_integer_and_an_optional_string_are_honoured_too():
    registry = make_tool_registry(make_search_descriptor(arguments=(
        limit_spec(required=True), query_spec(name="note", required=False, minimum=0, maximum=5),
    )))
    assert violations_of({}, registry) == [("limit", ArgumentViolationCode.MISSING_ARGUMENT)]
    assert admit(registry=registry, arguments={"limit": 2, "note": ""}).decision is ToolDecision.INVOKE
    assert admit(registry=registry, arguments={"limit": 2, "note": "toolong"}).decision is ToolDecision.DENY


def test_a_denial_for_invalid_arguments_carries_no_digest_and_no_bounds_and_says_why():
    admission = admit(arguments={"query": 5})
    assert (admission.args_digest, admission.timeout_seconds, admission.max_result_bytes) == (None, None, None)
    assert all(violation.message for violation in admission.denial.violations) and admission.denial.message


# --- rule 7: the per-attempt budget ---------------------------------------------------------------------------------------------


def test_the_budget_is_spent_exactly_at_max_tool_calls_for_the_attempt():
    two = (invocation(arguments={"query": "one"}), invocation(arguments={"query": "two"}))
    assert admit(max_tool_calls=3, prior_invocations=two).decision is ToolDecision.INVOKE
    denial = denial_of(admit(max_tool_calls=2, prior_invocations=two))
    assert denial.code is ToolDenialCode.BUDGET_EXHAUSTED and "2" in denial.message


def test_a_budget_of_zero_admits_no_new_invocation():
    assert denial_of(admit(max_tool_calls=0)).code is ToolDenialCode.BUDGET_EXHAUSTED


def test_a_negative_budget_is_a_programming_error_not_an_outcome():
    with pytest.raises(ValueError):
        admit(max_tool_calls=-1)


def test_each_replan_attempt_starts_a_fresh_budget_scoped_by_execution_and_plan():
    spent_in_plan_1 = tuple(invocation(plan=1, arguments={"query": str(n)}) for n in range(2))
    assert denial_of(admit(plan_id=make_attempt_plan_id(1), max_tool_calls=2, prior_invocations=spent_in_plan_1)).code is ToolDenialCode.BUDGET_EXHAUSTED
    assert admit(plan_id=make_attempt_plan_id(2), max_tool_calls=2, prior_invocations=spent_in_plan_1).decision is ToolDecision.INVOKE


def test_another_executions_invocations_never_count_against_this_one():
    elsewhere = tuple(invocation(execution=2, plan=1, arguments={"query": str(n)}) for n in range(5))
    assert admit(execution_id=make_execution_id(1), plan_id=make_attempt_plan_id(1), max_tool_calls=1, prior_invocations=elsewhere).decision is ToolDecision.INVOKE


def test_the_budget_is_never_cumulative_across_the_missions_attempts():
    # D-203 ruling 5 / D-043: five spent attempts in five other plans leave a sixth attempt its full budget.
    spent_elsewhere = tuple(invocation(plan=n, arguments={"query": f"q{n}"}) for n in range(2, 7))
    assert admit(plan_id=make_attempt_plan_id(1), max_tool_calls=1, prior_invocations=spent_elsewhere).decision is ToolDecision.INVOKE


def test_only_this_attempts_share_of_a_mixed_history_is_counted():
    mixed = (invocation(plan=1, arguments={"query": "a"}), invocation(plan=2, arguments={"query": "b"}), invocation(plan=2, arguments={"query": "c"}))
    assert admit(plan_id=make_attempt_plan_id(1), max_tool_calls=2, prior_invocations=mixed).decision is ToolDecision.INVOKE
    assert denial_of(admit(plan_id=make_attempt_plan_id(2), max_tool_calls=2, prior_invocations=mixed)).code is ToolDenialCode.BUDGET_EXHAUSTED


def test_an_invocation_that_reached_the_tool_counts_whether_or_not_it_stored_a_result():
    failed = (invocation(arguments={"query": "a"}, stored=False), invocation(arguments={"query": "b"}, stored=False))
    assert denial_of(admit(max_tool_calls=2, prior_invocations=failed)).code is ToolDenialCode.BUDGET_EXHAUSTED


def test_the_budget_counts_invocations_of_every_tool_in_the_attempt():
    other = make_search_descriptor(provider_id="wiki", tool_name="lookup")
    registry = make_tool_registry(make_search_descriptor(), other)
    prior = (invocation(tool_id="wiki/lookup", arguments={"query": "a"}),)
    assert denial_of(admit(registry=registry, max_tool_calls=1, prior_invocations=prior)).code is ToolDenialCode.BUDGET_EXHAUSTED


# --- rule 6: duplicates are execution-wide and cost nothing ---------------------------------------------------------------------


def test_a_duplicate_of_a_stored_result_is_served_from_it_and_invokes_nothing():
    admission = admit(prior_invocations=(invocation(),))
    assert admission.decision is ToolDecision.SERVE_STORED and admission.denial is None
    assert admission.args_digest == args_digest(DEFAULT_ARGUMENTS)
    assert (admission.timeout_seconds, admission.max_result_bytes) == (None, None)  # nothing is invoked, so nothing is bounded


def test_a_duplicate_is_recognised_across_plan_attempts_of_the_same_execution():
    assert admit(plan_id=make_attempt_plan_id(3), prior_invocations=(invocation(plan=1),)).decision is ToolDecision.SERVE_STORED


def test_a_duplicate_is_served_even_when_the_attempts_budget_is_spent_or_zero():
    stored = invocation(plan=1)
    spent = (stored, invocation(plan=1, arguments={"query": "other"}))
    assert admit(plan_id=make_attempt_plan_id(1), max_tool_calls=2, prior_invocations=spent).decision is ToolDecision.SERVE_STORED
    assert admit(max_tool_calls=0, prior_invocations=(stored,)).decision is ToolDecision.SERVE_STORED


def test_serving_duplicates_consumes_no_budget_a_run_of_calls_is_charged_only_for_real_invocations():
    history: list[ToolInvocationRecord] = []
    outcomes = []
    for query in ("a", "a", "a", "b", "a", "b", "c"):
        arguments = {"query": query}
        admission = admit(arguments=arguments, max_tool_calls=2, prior_invocations=tuple(history))
        outcomes.append(admission.decision.value)
        if admission.decision is ToolDecision.INVOKE:
            history.append(invocation(arguments=arguments))
    assert outcomes == ["invoke", "serve_stored", "serve_stored", "invoke", "serve_stored", "serve_stored", "deny"]
    assert len(history) == 2  # only the two distinct calls were ever charged


def test_a_prior_invocation_that_stored_no_result_cannot_serve_a_duplicate():
    assert admit(prior_invocations=(invocation(stored=False),)).decision is ToolDecision.INVOKE
    assert denial_of(admit(max_tool_calls=1, prior_invocations=(invocation(stored=False),))).code is ToolDenialCode.BUDGET_EXHAUSTED


@pytest.mark.parametrize("prior", [
    invocation(execution=2),  # another execution
    invocation(arguments={"query": "different"}),  # other arguments
    invocation(arguments={"query": "evidence", "limit": 3}),  # the same query with an extra argument is another call
    invocation(tool_id="docs/other"),  # another tool
])
def test_a_call_that_differs_in_execution_arguments_or_tool_is_not_a_duplicate(prior):
    assert admit(prior_invocations=(prior,)).decision is ToolDecision.INVOKE


def test_argument_order_is_irrelevant_to_recognising_a_duplicate():
    prior = invocation(arguments={"limit": 3, "query": "evidence"})
    assert admit(arguments={"query": "evidence", "limit": 3}, prior_invocations=(prior,)).decision is ToolDecision.SERVE_STORED


# --- the fixed check order ------------------------------------------------------------------------------------------------------


def test_the_first_failing_rule_decides_the_denial_in_the_documented_order():
    everything_wrong = dict(
        registry=make_tool_registry(make_search_descriptor(read_only=False)), tool_id="docs/nope", allowed_actions=(),
        autonomy_level=AutonomyLevel.RECOMMEND_ONLY, arguments={"zzz": 1}, max_tool_calls=0,
    )
    assert denial_of(admit(**everything_wrong)).code is ToolDenialCode.UNKNOWN_TOOL
    everything_wrong["tool_id"] = SEARCH_TOOL_ID
    assert denial_of(admit(**everything_wrong)).code is ToolDenialCode.NOT_READ_ONLY
    everything_wrong["registry"] = make_tool_registry()
    assert denial_of(admit(**everything_wrong)).code is ToolDenialCode.ACTION_NOT_ALLOWED
    everything_wrong["allowed_actions"] = (READ_ACTION,)
    assert denial_of(admit(**everything_wrong)).code is ToolDenialCode.AUTONOMY_TOO_LOW
    everything_wrong["autonomy_level"] = AutonomyLevel.SAFE_READ_ONLY
    assert denial_of(admit(**everything_wrong)).code is ToolDenialCode.INVALID_ARGUMENTS
    everything_wrong["arguments"] = dict(DEFAULT_ARGUMENTS)
    assert denial_of(admit(**everything_wrong)).code is ToolDenialCode.BUDGET_EXHAUSTED
    everything_wrong["max_tool_calls"] = 1
    assert admit(**everything_wrong).decision is ToolDecision.INVOKE


def test_a_duplicate_is_only_served_after_every_policy_rule_has_passed_and_before_the_budget_rule():
    stored = (invocation(),)
    assert denial_of(admit(prior_invocations=stored, autonomy_level=AutonomyLevel.RECOMMEND_ONLY)).code is ToolDenialCode.AUTONOMY_TOO_LOW
    assert denial_of(admit(prior_invocations=stored, allowed_actions=())).code is ToolDenialCode.ACTION_NOT_ALLOWED
    assert denial_of(admit(prior_invocations=stored, registry=make_tool_registry(make_search_descriptor(read_only=False)))).code is ToolDenialCode.NOT_READ_ONLY
    assert admit(prior_invocations=stored, max_tool_calls=0).decision is ToolDecision.SERVE_STORED


# --- purity and totality --------------------------------------------------------------------------------------------------------


def test_admission_changes_none_of_its_inputs_and_repeats_exactly():
    registry, arguments, history = make_tool_registry(), {"query": "evidence", "limit": 2}, (invocation(),)
    before = (registry.model_dump(), dict(arguments), tuple(record.model_dump() for record in history))
    first = admit(registry=registry, arguments=arguments, prior_invocations=history)
    second = admit(registry=registry, arguments=arguments, prior_invocations=history)
    assert first == second
    assert before == (registry.model_dump(), dict(arguments), tuple(record.model_dump() for record in history))


def test_single_pass_iterables_are_accepted_for_the_history_and_the_actions():
    assert admit(prior_invocations=(record for record in (invocation(),)), allowed_actions=(action for action in (READ_ACTION,))).decision is ToolDecision.SERVE_STORED


@pytest.mark.parametrize("overrides", [
    {}, {"tool_id": "nope/nope"}, {"allowed_actions": ()}, {"autonomy_level": AutonomyLevel.RECOMMEND_ONLY}, {"arguments": {}},
    {"max_tool_calls": 0}, {"max_tool_calls": None}, {"prior_invocations": (invocation(),)},
])
def test_every_outcome_including_a_refusal_is_a_returned_and_round_trippable_decision(overrides):
    admission = admit(**overrides)
    assert isinstance(admission, ToolAdmission)
    assert ToolAdmission.model_validate_json(admission.model_dump_json()) == admission


# --- the decision and denial types refuse a mislabelled value -------------------------------------------------------------------


def test_a_denial_lists_argument_violations_exactly_when_the_code_is_invalid_arguments():
    with pytest.raises(ValidationError):
        ToolDenial(code=ToolDenialCode.INVALID_ARGUMENTS, message="x")
    with pytest.raises(ValidationError):
        ToolDenial(code=ToolDenialCode.UNKNOWN_TOOL, message="x", violations=denial_of(admit(arguments={"q": 1})).violations)
    with pytest.raises(ValidationError):
        ToolDenial(code=ToolDenialCode.UNKNOWN_TOOL, message="")


DIGEST = args_digest({"query": "x"})


@pytest.mark.parametrize("fields", [
    dict(decision=ToolDecision.DENY),  # a denial without its reason
    dict(decision=ToolDecision.DENY, denial=ToolDenial(code=ToolDenialCode.UNKNOWN_TOOL, message="m"), args_digest=DIGEST),
    dict(decision=ToolDecision.DENY, denial=ToolDenial(code=ToolDenialCode.UNKNOWN_TOOL, message="m"), timeout_seconds=1.0),
    dict(decision=ToolDecision.INVOKE, args_digest=DIGEST),  # an invocation without its bounds
    dict(decision=ToolDecision.INVOKE, timeout_seconds=1.0, max_result_bytes=1),  # ... or without its digest
    dict(decision=ToolDecision.INVOKE, args_digest=DIGEST, timeout_seconds=1.0, max_result_bytes=1, denial=ToolDenial(code=ToolDenialCode.UNKNOWN_TOOL, message="m")),
    dict(decision=ToolDecision.SERVE_STORED),  # serving without saying which stored result
    dict(decision=ToolDecision.SERVE_STORED, args_digest=DIGEST, timeout_seconds=1.0),  # nothing is invoked, so no bound
    dict(decision=ToolDecision.SERVE_STORED, args_digest=DIGEST, max_result_bytes=1),
    dict(decision=ToolDecision.INVOKE, args_digest="not-a-digest", timeout_seconds=1.0, max_result_bytes=1),
])
def test_a_mislabelled_decision_is_unconstructible(fields):
    with pytest.raises(ValidationError):
        ToolAdmission(tool_id="docs/x", **fields)


def test_an_invocation_record_needs_a_real_digest_and_a_tool():
    good = dict(execution_id=make_execution_id(), plan_id=make_attempt_plan_id(), tool_id="a/b", args_digest=DIGEST, result_stored=True)
    ToolInvocationRecord(**good)
    for bad in ({"args_digest": "xyz"}, {"tool_id": ""}, {"result_stored": "yes"}):
        with pytest.raises(ValidationError):
            ToolInvocationRecord(**{**good, **bad})


def test_the_denial_vocabulary_is_exactly_the_six_rules_and_the_unset_budget_and_the_violation_vocabulary_exactly_four():
    assert {code.value for code in ToolDenialCode} == {
        "unknown_tool", "not_read_only", "action_not_allowed", "autonomy_too_low", "invalid_arguments", "budget_exhausted", "budget_unresolved",
    }
    assert {code.value for code in ArgumentViolationCode} == {"unknown_argument", "missing_argument", "wrong_type", "out_of_bounds"}
