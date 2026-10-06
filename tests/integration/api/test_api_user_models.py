"""Bring-your-own-key over the HTTP surface (decisions.md D-246).

Real FastAPI, real JWT verification, the real runtime. What is held: ``start`` takes an optional body and no endpoint was added; a start with a model of the user's own runs on it; the key is in no answer, no
error body and no log; a bad request is a 422 in the one error shape that never echoes what was sent; an unauthenticated start never reads the key; a service that did not opt in refuses; and an empty
body is exactly the start it always was.
"""

import json
import logging

from pydantic import ValidationError

from eidos.service import RunStatus, StartRequest

from eidos_api_fixture import ALICE, BOB, make_api, spec_json
from eidos_user_models_fixture import KEY, UserRig

JSON = {"Content-Type": "application/json"}


def create(api, user=ALICE):
    return api.client.post("/v1/missions", content=spec_json(), headers={**api.headers(user), **JSON})


def api_for(users: UserRig):
    return make_api(rig=users.rig)


def body_for(provider="openai", model="a-model", key=KEY, **extra) -> str:
    return json.dumps({"model": {"provider": provider, "model": model, "api_key": key, **extra}})


def made(api, who=ALICE) -> str:
    response = create(api, who)
    assert response.status_code == 201, response.text
    return response.json()["mission_id"]


def start(api, mission_id, content=None, who=ALICE):
    headers = {**api.headers(who), **JSON}
    return api.client.post(f"/v1/missions/{mission_id}/start", content=content, headers=headers)


def test_a_start_with_a_model_of_the_users_own_runs_on_it_and_the_answer_never_carries_the_key(caplog):
    users = UserRig()
    api = api_for(users)
    mission_id = made(api)
    with caplog.at_level(logging.DEBUG):
        response = start(api, mission_id, body_for("gemini", "gemini-test"))
        assert response.status_code == 202, response.text
        assert users.rig.runner.wait_idle(60)
    assert response.json()["run_status"] == "queued" and KEY not in response.text
    assert users.rig.model.calls == 0
    [(provider, key, model)] = users.built
    assert (provider, key) == ("gemini", KEY) and {r.settings.model for r in model.requests} == {"gemini-test"}
    summary = api.client.get(f"/v1/missions/{mission_id}", headers=api.headers(ALICE))
    assert summary.json()["run_status"] == RunStatus.FINISHED.value
    for path in ("", "/events", "/execution", "/result", "/evidence"):
        assert KEY not in api.client.get(f"/v1/missions/{mission_id}{path}", headers=api.headers(ALICE)).text, path
    assert KEY not in caplog.text


def test_an_empty_body_is_the_start_it_always_was():
    users = UserRig()
    api = api_for(users)
    mission_id = made(api)
    assert start(api, mission_id).status_code == 202
    assert users.rig.runner.wait_idle(60)
    assert users.rig.model.calls > 0 and users.built == []


def test_a_bad_body_is_a_422_in_the_one_error_shape_and_never_echoes_what_was_sent():
    users = UserRig()
    api = api_for(users)
    for content in (
        "not json",
        body_for(key="short"),
        body_for(model="has space"),
        body_for(provider="openai", unexpected="x"),
        json.dumps({"model": {"provider": "openai", "model": "m"}}),  # no key
        json.dumps({"model": {"provider": "openai", "model": "m", "api_key": KEY}, "extra": 1}),
    ):
        mission_id = made(api)
        response = start(api, mission_id, content)
        assert response.status_code == 422, (content, response.text)
        error = response.json()["error"]
        assert error["code"] == "invalid_request"
        assert KEY not in response.text and "short" not in json.dumps(error["details"])  # no detail repeats what was sent
        assert api.client.get(f"/v1/missions/{mission_id}", headers=api.headers(ALICE)).json()["run_status"] == RunStatus.CREATED.value  # and the mission is still startable
    assert users.built == []


def test_a_provider_the_deployer_did_not_allow_is_a_422_and_nothing_is_built():
    users = UserRig(providers=("gemini",))
    api = api_for(users)
    mission_id = made(api)
    response = start(api, mission_id, body_for("openai"))
    assert response.status_code == 422 and "gemini" in response.json()["error"]["message"] and KEY not in response.text
    assert users.built == []


def test_a_service_that_did_not_opt_in_refuses_a_model_of_the_users_own():
    api = make_api()
    mission_id = made(api)
    response = start(api, mission_id, body_for())
    assert response.status_code == 422 and "does not accept one of your own" in response.json()["error"]["message"] and KEY not in response.text


def test_an_unauthenticated_start_is_a_401_and_builds_nothing():
    users = UserRig()
    api = api_for(users)
    mission_id = made(api)
    response = api.client.post(f"/v1/missions/{mission_id}/start", content=body_for(), headers=JSON)
    assert response.status_code == 401 and KEY not in response.text
    assert users.built == []


def test_another_tenants_mission_is_a_404_and_the_key_builds_nothing():
    users = UserRig()
    api = api_for(users)
    mission_id = made(api, ALICE)
    response = start(api, mission_id, body_for(), who=BOB)
    assert response.status_code == 404 and KEY not in response.text
    assert users.built == []


def test_a_request_body_over_the_ceiling_is_refused_before_it_is_parsed():
    users = UserRig()
    api = api_for(users)
    mission_id = made(api)
    huge = body_for(key="k" * 300_000)
    response = start(api, mission_id, huge)
    assert response.status_code == 413 and users.built == []


def test_a_bad_nested_key_does_not_carry_the_key_in_the_validation_error_either():
    try:
        StartRequest.model_validate_json(body_for(key="bad key 12345678"))
    except ValidationError as error:
        assert "bad key" not in str(error) and "bad key" not in repr(error)
    else:
        raise AssertionError("a key with a space was accepted")
