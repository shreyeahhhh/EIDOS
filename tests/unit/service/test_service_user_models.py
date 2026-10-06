"""Bring-your-own-key and the comparison it makes possible (decisions.md D-246; invariants 1, 2, 9 and 13).

A user may start a mission on their own provider, model and key. What is held: the run uses *their* model and not the service's; the key is held in memory for that run only, is dropped when the run ends
however it ends, and appears in no stored event, no stored mission record, no log line and no error; a mission that is not the caller's never touches a key; a service that did not opt in refuses a model
of the user's own and leaves the mission startable; the request is validated as the shape of a credential; and three missions on three models run side by side and each records its own run.
"""

import json
import logging

import pytest
from pydantic import ValidationError

from eidos.service import InvalidRequest, MissionService, ModelChoice, NotFound, RunStatus, StartRequest, UserModels
from eidos.service.user_models import RunModel

from eidos_agents_factories import ScriptedModel, make_settings
from eidos_service_fixture import make_rig, make_spec
from eidos_user_models_fixture import KEY, UserRig, choice

# --- the run uses the user's model --------------------------------------------------------------------------------------------------------


def test_a_run_started_with_a_model_of_the_users_own_uses_it_and_not_the_services():
    users = UserRig()
    context, mission_id = users.mission()
    users.service.start_mission(context, mission_id, choice("openai", "my-model"))
    assert users.rig.runner.wait_idle(60)
    assert users.service.get_mission(context, mission_id).run_status is RunStatus.FINISHED
    assert users.rig.model.calls == 0  # the service's own model was never asked
    [(provider, key, model)] = users.built
    assert (provider, key) == ("openai", KEY) and model.calls > 0
    assert {request.settings.model for request in model.requests} == {"my-model"}  # the user's model name...
    assert {request.settings.parameters.max_output_tokens for request in model.requests} == {make_settings().parameters.max_output_tokens}  # ...over the deployer's own parameters


def test_without_a_choice_the_service_runs_on_its_own_model_exactly_as_before():
    users = UserRig()
    context, mission_id = users.mission()
    users.service.start_mission(context, mission_id)
    assert users.rig.runner.wait_idle(60)
    assert users.rig.model.calls > 0 and users.built == []


# --- the key is held for the run only, and nowhere else ----------------------------------------------------------------------------------


def test_the_key_is_dropped_when_the_run_ends():
    users = UserRig()
    context, mission_id = users.mission()
    users.service.start_mission(context, mission_id, choice())
    assert users.rig.runner.wait_idle(60)
    assert users.rig.runner._private == {}


def test_the_key_is_dropped_even_when_the_run_ends_in_error(monkeypatch):
    users = UserRig()

    def explode(*args, **kwargs):
        raise RuntimeError("the service failed")

    monkeypatch.setattr(users.rig.composition, "prepare", explode)
    context, mission_id = users.mission()
    users.service.start_mission(context, mission_id, choice())
    assert users.rig.runner.wait_idle(60)
    assert users.service.get_mission(context, mission_id).run_status is RunStatus.ERROR
    assert users.rig.runner._private == {}


def test_the_key_is_in_no_stored_event_no_mission_record_and_no_log_line(caplog):
    users = UserRig()
    context, mission_id = users.mission()
    with caplog.at_level(logging.DEBUG):
        users.service.start_mission(context, mission_id, choice())
        assert users.rig.runner.wait_idle(60)
    assert KEY not in users.stored_text(context, mission_id)
    assert KEY not in caplog.text
    assert KEY not in repr(users.service.get_mission(context, mission_id)) and KEY not in users.service.get_mission(context, mission_id).model_dump_json()


def test_a_key_is_never_held_when_the_start_is_refused():
    users = UserRig()
    context, mission_id = users.mission()
    users.service.start_mission(context, mission_id, choice())
    assert users.rig.runner.wait_idle(60)
    from eidos.service import NotStartable

    with pytest.raises(NotStartable):
        users.service.start_mission(context, mission_id, choice(key="sk-another-0123456789"))  # a mission is started once
    assert users.rig.runner._private == {}


# --- who may bring a model, and which ----------------------------------------------------------------------------------------------------


def test_another_tenants_mission_is_not_found_and_no_model_is_ever_built_from_the_key():
    users = UserRig()
    _, mission_id = users.mission("alice")
    with pytest.raises(NotFound):
        users.service.start_mission(users.rig.context("bob"), mission_id, choice())
    assert users.built == []  # the key was never used to build anything


def test_a_service_that_did_not_opt_in_refuses_a_model_of_the_users_own_and_the_mission_stays_startable():
    rig = make_rig()
    context = rig.context("alice")
    mission_id = rig.service.create_mission(context, make_spec())[0].mission_id
    with pytest.raises(InvalidRequest) as raised:
        rig.service.start_mission(context, mission_id, choice())
    assert "does not accept one of your own" in raised.value.message and KEY not in raised.value.message
    assert rig.service.get_mission(context, mission_id).run_status is RunStatus.CREATED
    rig.service.start_mission(context, mission_id)  # still startable on the service's own model
    assert rig.runner.wait_idle(60)


def test_a_provider_the_deployer_did_not_allow_is_refused_naming_the_allowed_ones():
    users = UserRig(providers=("gemini",))
    context, mission_id = users.mission()
    with pytest.raises(InvalidRequest) as raised:
        users.service.start_mission(context, mission_id, choice("openai"))
    assert "gemini" in raised.value.message and KEY not in raised.value.message
    assert users.built == [] and users.service.get_mission(context, mission_id).run_status is RunStatus.CREATED


def test_a_factory_that_refuses_gives_a_generic_message_that_never_carries_the_key():
    rig = make_rig()

    def refuses(provider, key):
        raise ValueError(f"the key {key} is no good")

    service = MissionService(repositories=rig.storage.repositories(), runner=rig.runner, composition=rig.composition, config=rig.config,
                             user_models=UserModels(providers=frozenset({"openai"}), factory=refuses))
    context = rig.context("alice")
    mission_id = service.create_mission(context, make_spec())[0].mission_id
    with pytest.raises(InvalidRequest) as raised:
        service.start_mission(context, mission_id, choice())
    assert KEY not in raised.value.message and KEY not in repr(raised.value) and raised.value.__cause__ is None and raised.value.__suppress_context__


# --- the request is the shape of a credential --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["short", "has a space in it 123", "line\nbreak-0123456789", "tab\there-0123456789", "non-ascii-é-0123456789", "x" * 513, ""])
def test_a_key_that_is_not_the_shape_of_a_credential_is_refused_and_the_error_never_contains_it(key):
    with pytest.raises(ValidationError) as raised:
        choice(key=key)
    assert key == "" or key not in str(raised.value)


@pytest.mark.parametrize("name", ["", "has space", "../etc/passwd?", "model\n", "-leading-dash", "x" * 101, "semi;colon"])
def test_a_model_name_with_anything_but_the_usual_characters_is_refused(name):
    with pytest.raises(ValidationError):
        choice(model=name)


@pytest.mark.parametrize("name", ["gpt-4o-mini", "gemini-2.5-flash", "openai/gpt-oss-120b", "llama-3.3-70b-versatile", "models/x.y_z:1"])
def test_the_usual_model_names_are_accepted(name):
    assert choice(model=name).model == name


def test_the_key_is_masked_in_repr_str_and_json_and_a_field_the_request_does_not_know_is_refused():
    chosen = choice()
    assert KEY not in repr(chosen) and KEY not in str(chosen)
    assert KEY not in chosen.model_dump_json()  # SecretStr serialises masked
    assert chosen.api_key.get_secret_value() == KEY
    with pytest.raises(ValidationError):
        ModelChoice(provider="openai", model="m", api_key=KEY, base_url="https://evil.example")  # an address is never the user's to give
    with pytest.raises(ValidationError):
        StartRequest.model_validate_json(json.dumps({"model": {"provider": "openai", "model": "m", "api_key": KEY}, "extra": 1}))


def test_a_run_model_shows_no_key_in_its_repr():
    run_model = RunModel(port=ScriptedModel(), settings=make_settings(model="m"))
    assert repr(run_model) == "RunModel(model='m')"


# --- the comparison: the same goal on three models, side by side ------------------------------------------------------------------------


def test_three_missions_on_three_models_run_side_by_side_each_on_its_own_model_and_each_recorded_alone():
    users = UserRig()
    started = []
    for provider in ("openai", "gemini", "groq"):
        context, mission_id = users.mission(goal="Compare these")
        users.service.start_mission(context, mission_id, choice(provider, f"{provider}-model", key=f"key-for-{provider}-0123456789"))
        started.append((context, mission_id, provider))
    assert users.rig.runner.wait_idle(120)
    for context, mission_id, provider in started:
        assert users.service.get_mission(context, mission_id).run_status is RunStatus.FINISHED
        assert users.service.result(context, mission_id).artifacts  # each has its own answer
    assert users.rig.model.calls == 0
    assert sorted(provider for provider, _, _ in users.built) == ["gemini", "groq", "openai"]
    for provider, key, model in users.built:  # each run used its own key, on its own model, and no other
        assert key == f"key-for-{provider}-0123456789" and {r.settings.model for r in model.requests} == {f"{provider}-model"}
    for context, mission_id, provider in started:  # and no run stored any key, its own or another's
        stored = users.stored_text(context, mission_id)
        assert "key-for-" not in stored
    assert users.rig.runner._private == {}
