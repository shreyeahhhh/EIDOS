"""The model seam (decisions.md D-135): typed, explicit, total, and free of any vendor."""

import json
import threading

import pytest
from pydantic import ValidationError

from eidos.agents import (
    GenerationParameters,
    MeasuredFacts,
    ModelFailure,
    ModelFailureKind,
    ModelRequest,
    ModelResponse,
    ModelSettings,
)

from eidos_agents_factories import ScriptedModel, make_settings


def request(**overrides) -> ModelRequest:
    fields = dict(settings=make_settings(), prompt="Summarise the documents.")
    fields.update(overrides)
    return ModelRequest(**fields)


# --- nothing is defaulted (D-135) ----------------------------------------------------------------------------------


@pytest.mark.parametrize("model", [GenerationParameters, ModelSettings, ModelRequest])
def test_no_configuration_field_has_a_default_except_the_optional_system_prompt(model):
    for name, field in model.model_fields.items():
        if model is ModelRequest and name == "system":
            assert not field.is_required()  # absent means "no system prompt", which is a real choice
        else:
            assert field.is_required(), f"{model.__name__}.{name} has a default"


@pytest.mark.parametrize("missing", ["temperature", "seed", "max_output_tokens"])
def test_every_generation_parameter_is_required(missing):
    fields = dict(temperature=0.2, seed=1, max_output_tokens=64)
    del fields[missing]
    with pytest.raises(ValidationError):
        GenerationParameters(**fields)


@pytest.mark.parametrize("missing", ["model", "parameters", "timeout_seconds"])
def test_the_model_the_parameters_and_the_timeout_are_all_required(missing):
    fields = dict(
        model="m", parameters=GenerationParameters(temperature=0.0, seed=1, max_output_tokens=8), timeout_seconds=1.0
    )
    del fields[missing]
    with pytest.raises(ValidationError):
        ModelSettings(**fields)


# --- validation ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [-0.1, "0.5", None])
def test_temperature_is_a_non_negative_number(bad):
    with pytest.raises(ValidationError):
        GenerationParameters(temperature=bad, seed=1, max_output_tokens=8)


@pytest.mark.parametrize("bad", [0, -1, 1.5, "8", None, True])
def test_max_output_tokens_is_a_strict_positive_integer(bad):
    with pytest.raises(ValidationError):
        GenerationParameters(temperature=0.0, seed=1, max_output_tokens=bad)


@pytest.mark.parametrize("bad", [0, 0.0, -1.0, "5", None])
def test_the_timeout_is_a_strictly_positive_number(bad):
    with pytest.raises(ValidationError):
        make_settings(timeout_seconds=bad)


@pytest.mark.parametrize("field", ["model", "prompt", "system"])
def test_blank_identifiers_and_prompts_are_rejected(field):
    if field == "model":
        with pytest.raises(ValidationError):
            make_settings(model="")
    else:
        with pytest.raises(ValidationError):
            request(**{field: ""})


def test_extra_fields_are_rejected_so_nothing_can_be_smuggled_through_the_seam():
    with pytest.raises(ValidationError):
        request(tools=["shell"])
    with pytest.raises(ValidationError):
        make_settings(api_key="secret")


# --- responses and failures ----------------------------------------------------------------------------------------


def test_a_usable_response_carries_text_and_measured_facts():
    response = ModelResponse(text="answer", measured=MeasuredFacts(prompt_tokens=12, output_tokens=3, elapsed_seconds=0.5))
    assert response.text == "answer"
    assert (response.measured.prompt_tokens, response.measured.output_tokens, response.measured.elapsed_seconds) == (12, 3, 0.5)


def test_a_provider_that_reported_nothing_leaves_the_facts_unknown_rather_than_guessed():
    facts = ModelResponse(text="answer").measured
    assert (facts.prompt_tokens, facts.output_tokens, facts.elapsed_seconds) == (None, None, None)


@pytest.mark.parametrize("blank", ["", " ", "\n\t  "])
def test_a_response_with_no_text_is_unconstructible_so_it_cannot_be_read_as_success(blank):
    with pytest.raises(ValidationError):
        ModelResponse(text=blank)


@pytest.mark.parametrize("field", ["prompt_tokens", "output_tokens", "elapsed_seconds"])
def test_measured_facts_are_never_negative(field):
    with pytest.raises(ValidationError):
        MeasuredFacts(**{field: -1})


def test_every_kind_of_failure_is_a_typed_value_never_a_response():
    for kind in ModelFailureKind:
        failure = ModelFailure(kind=kind, message=f"{kind.value} happened")
        assert not isinstance(failure, ModelResponse)
    assert {kind.value for kind in ModelFailureKind} == {"timeout", "unavailable", "malformed_response", "empty_response"}


def test_a_failure_must_say_why():
    with pytest.raises(ValidationError):
        ModelFailure(kind=ModelFailureKind.TIMEOUT, message="")


# --- immutability and round trip -----------------------------------------------------------------------------------


def test_requests_responses_and_failures_are_frozen():
    for value, attribute in (
        (request(), "prompt"),
        (make_settings(), "timeout_seconds"),
        (ModelResponse(text="x"), "text"),
        (ModelFailure(kind=ModelFailureKind.TIMEOUT, message="slow"), "message"),
    ):
        with pytest.raises(ValidationError):
            setattr(value, attribute, None)


def test_a_request_round_trips_through_json_unchanged():
    original = request(system="Be brief.")
    assert ModelRequest.model_validate_json(original.model_dump_json()) == original
    assert set(json.loads(original.model_dump_json())) == {"settings", "prompt", "system"}


# --- the fake at the seam ------------------------------------------------------------------------------------------


def test_the_scripted_model_answers_and_records_what_it_was_asked():
    model = ScriptedModel(lambda r: ModelResponse(text=f"echo: {r.prompt}"))
    result = model.complete(request(prompt="hello"))
    assert result.text == "echo: hello"
    assert [r.prompt for r in model.requests] == ["hello"]


def test_the_scripted_model_can_answer_with_a_typed_failure():
    failure = ModelFailure(kind=ModelFailureKind.UNAVAILABLE, message="no route")
    assert ScriptedModel(lambda r: failure).complete(request()) == failure


def test_the_scripted_model_records_every_request_under_concurrent_callers():
    model = ScriptedModel()
    threads = [threading.Thread(target=lambda n=n: model.complete(request(prompt=f"p{n}"))) for n in range(64)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert model.calls == 64
    assert sorted(r.prompt for r in model.requests) == sorted(f"p{n}" for n in range(64))
