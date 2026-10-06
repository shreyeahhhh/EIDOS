"""Asking several models the same question directly (decisions.md D-248; invariants 13 and 16 are *not* claimed for it).

What is held: the question goes to each named model verbatim and each answer comes back as that model said it, in the order named, with what the provider measured, every one marked unverified; the calls run
concurrently; one model's failure is its own answer and never the others'; it is **not a mission** (no storage is touched, no event is recorded, the service's own model is not asked); the user's key is
handled as for a mission (never stored, logged, echoed or put in a failure); a bad choice refuses the whole request before any model is called; the request is bounded (question length, at most three models,
a ceiling on calls in flight); and the slots are always given back.
"""

import logging
import threading

import pytest
from pydantic import ValidationError

from eidos.agents import MeasuredFacts, ModelFailure, ModelFailureKind, ModelResponse
from eidos.service import ASK_MAX_MODELS, AskRequest, Busy, InvalidRequest, MissionService, ModelChoice, UserModels
from eidos.service.ask import ASK_MAX_IN_FLIGHT, ASK_SYSTEM_PROMPT

from eidos_agents_factories import ScriptedModel
from eidos_service_fixture import make_rig
from eidos_user_models_fixture import KEY, UserRig, choice

QUESTION = "Which is the best time for a beginner to buy and sell stocks?"


def asked(users: UserRig, *choices: ModelChoice, question: str = QUESTION):
    return users.service.ask_models(users.rig.context("alice"), AskRequest(question=question, models=list(choices)))


def says(request):
    """Each model answers in its own words, so the answers differ and the test can tell whose is whose."""
    return ModelResponse(text=f"{request.settings.model} says: wait and spread your buying", measured=MeasuredFacts(prompt_tokens=11, output_tokens=7, elapsed_seconds=0.25))


# --- what each model is asked, and what comes back ----------------------------------------------------------------------------------------


def test_each_model_is_asked_the_question_verbatim_and_each_answer_comes_back_in_its_own_words_in_the_order_named():
    users = UserRig(respond=says)
    result = asked(users, choice("gemini", "gemini-test", "key-gemini-0123456789"), choice("groq", "groq-test", "key-groq-0123456789"))
    assert [(a.provider, a.model, a.ok) for a in result.answers] == [("gemini", "gemini-test", True), ("groq", "groq-test", True)]
    assert [a.text for a in result.answers] == ["gemini-test says: wait and spread your buying", "groq-test says: wait and spread your buying"]
    assert [(a.prompt_tokens, a.output_tokens, a.elapsed_seconds) for a in result.answers] == [(11, 7, 0.25)] * 2  # what the provider measured, not anything made up
    for _, _, model in users.built:
        [request] = model.requests
        assert request.prompt == QUESTION and request.system == ASK_SYSTEM_PROMPT
        assert "do not invent citations" in request.system  # told it has no sources, so it does not make citations up


def test_every_answer_is_marked_unverified_and_the_response_says_plainly_that_nothing_was_checked():
    result = asked(UserRig(respond=says), choice("gemini"), choice("groq"))
    assert result.verified is False
    assert "unverified" in result.note.lower() and "cited none and checked none" in result.note
    with pytest.raises(ValidationError):
        type(result)(answers=[], verified=True)  # it cannot even be built claiming to be verified


# --- it is not a mission ----------------------------------------------------------------------------------------------------------------------


def test_it_touches_no_storage_records_no_event_and_never_asks_the_services_own_model():
    class Untouchable:
        def __getattr__(self, name):
            raise AssertionError(f"asking models directly touched storage ({name})")

    users = UserRig(respond=says)
    service = MissionService(repositories=Untouchable(), runner=users.rig.runner, composition=users.rig.composition, config=users.rig.config,
                             user_models=UserModels(providers=frozenset({"gemini", "groq"}), factory=users.factory))
    result = service.ask_models(users.rig.context("alice"), AskRequest(question=QUESTION, models=[choice("gemini"), choice("groq")]))
    assert all(answer.ok for answer in result.answers)
    assert users.rig.model.calls == 0 and users.rig.runner._private == {}


# --- concurrency and independence ---------------------------------------------------------------------------------------------------------------


def test_the_models_are_asked_at_the_same_time_not_one_after_another():
    barrier = threading.Barrier(2)

    def together(request):
        barrier.wait(timeout=10)  # only passes if the other model's call is in flight at the same moment
        return says(request)

    result = asked(UserRig(respond=together), choice("gemini"), choice("groq"))
    assert [a.ok for a in result.answers] == [True, True], [a.failure for a in result.answers]


def test_one_models_failure_is_its_own_answer_in_the_providers_words_and_never_the_others():
    def respond(request):
        if request.settings.model == "bad":
            return ModelFailure(kind=ModelFailureKind.UNAVAILABLE, message="the provider answered HTTP status 429: Rate limit reached")
        return says(request)

    result = asked(UserRig(respond=respond), choice("gemini", "good"), choice("groq", "bad"))
    good, bad = result.answers
    assert good.ok and good.text and good.failure is None
    assert not bad.ok and bad.text is None and "HTTP status 429: Rate limit reached" in bad.failure


def test_a_model_that_raises_is_told_by_its_type_alone_because_its_message_could_carry_anything():
    def explodes(request):
        raise RuntimeError(f"boom with the key {KEY} in it")

    result = asked(UserRig(respond=explodes), choice("gemini"), choice("groq", key="key-groq-0123456789"))
    for answer in result.answers:
        assert not answer.ok and answer.failure == "the call failed unexpectedly (RuntimeError)"
        assert KEY not in answer.model_dump_json()


# --- the key -----------------------------------------------------------------------------------------------------------------------------------


def test_the_key_goes_to_the_one_model_it_belongs_to_and_is_in_no_answer_no_log_and_no_response(caplog):
    users = UserRig(respond=says)
    with caplog.at_level(logging.DEBUG):
        result = asked(users, choice("gemini", key="key-gemini-0123456789"), choice("groq", key="key-groq-0123456789"))
    assert [(provider, key) for provider, key, _ in users.built] == [("gemini", "key-gemini-0123456789"), ("groq", "key-groq-0123456789")]
    text = result.model_dump_json()
    assert "key-gemini" not in text and "key-groq" not in text and "key-gemini" not in caplog.text


# --- refusals: before any model is called ------------------------------------------------------------------------------------------------------


def test_a_service_that_did_not_opt_in_refuses_and_a_provider_not_allowed_refuses_the_whole_request_before_any_call():
    rig = make_rig()
    with pytest.raises(InvalidRequest) as raised:
        rig.service.ask_models(rig.context("alice"), AskRequest(question=QUESTION, models=[choice()]))
    assert "does not accept one of your own" in raised.value.message

    users = UserRig(providers=("gemini",), respond=says)
    with pytest.raises(InvalidRequest) as raised:
        asked(users, choice("gemini"), choice("groq"))  # the second is not allowed
    assert "gemini" in raised.value.message
    assert all(model.calls == 0 for _, _, model in users.built)  # the allowed one was set up but never asked: nothing was spent


def test_the_request_is_bounded_in_question_length_and_in_how_many_models():
    users = UserRig(respond=says)
    with pytest.raises(InvalidRequest):
        asked(users, choice("gemini"), question="q" * (users.rig.config.ceilings.max_goal_chars + 1))
    for bad in ("", "   ", "has a \x00 nul"):
        with pytest.raises(ValidationError):
            AskRequest(question=bad, models=[choice()])
    with pytest.raises(ValidationError):
        AskRequest(question=QUESTION, models=[])
    with pytest.raises(ValidationError):
        AskRequest(question=QUESTION, models=[choice("openai", f"m{n}") for n in range(ASK_MAX_MODELS + 1)])
    with pytest.raises(ValidationError):
        AskRequest(question=QUESTION, models=[choice()], unexpected=1)


def test_the_error_for_a_bad_request_never_carries_the_key():
    with pytest.raises(ValidationError) as raised:
        AskRequest(question="", models=[choice(key=KEY)])
    assert KEY not in str(raised.value)


# --- the ceiling on calls in flight, and giving the slots back --------------------------------------------------------------------------------


def slots_free(users: UserRig) -> int:
    taken = 0
    while users.service._ask_slots.acquire(blocking=False):
        taken += 1
    for _ in range(taken):
        users.service._ask_slots.release()
    return taken


def test_the_slots_are_given_back_after_a_normal_call_a_failing_one_and_a_refused_one():
    users = UserRig(respond=says)
    assert slots_free(users) == ASK_MAX_IN_FLIGHT
    asked(users, choice("gemini"), choice("groq"))
    assert slots_free(users) == ASK_MAX_IN_FLIGHT
    asked(UserRig(respond=lambda request: (_ for _ in ()).throw(RuntimeError("x"))), choice("gemini"))
    with pytest.raises(InvalidRequest):
        asked(users, choice("gemini"), question="q" * 5000)
    assert slots_free(users) == ASK_MAX_IN_FLIGHT


def test_past_the_ceiling_the_request_is_refused_as_busy_and_what_it_took_is_given_back():
    users = UserRig(respond=says)
    held = [users.service._ask_slots.acquire(blocking=False) for _ in range(ASK_MAX_IN_FLIGHT - 1)]  # leave one slot for a request that needs two
    assert all(held)
    with pytest.raises(Busy):
        asked(users, choice("gemini"), choice("groq"))
    assert all(model.calls == 0 for _, _, model in users.built)
    for _ in held:
        users.service._ask_slots.release()
    assert slots_free(users) == ASK_MAX_IN_FLIGHT
