"""``POST /v1/ask`` over the HTTP surface: one question to several models with the user's own keys (decisions.md D-248).

Real FastAPI, real JWT verification, scripted models. What is held: the answers come back marked unverified and the key is nowhere in them; a bad body is a 422 in the one error shape that never echoes what was
sent; an unauthenticated request builds nothing; a service that did not opt in refuses; a body over the ceiling is refused before it is parsed; and no mission is created.
"""

import json

from eidos.agents import ModelResponse

from eidos_api_fixture import ALICE, make_api
from eidos_user_models_fixture import KEY, UserRig

JSON = {"Content-Type": "application/json"}
QUESTION = "Which is the best time for a beginner to buy and sell stocks?"


def body(models=None, question=QUESTION, **extra) -> str:
    models = models if models is not None else [{"provider": "gemini", "model": "gemini-test", "api_key": KEY}, {"provider": "groq", "model": "groq-test", "api_key": "key-groq-0123456789"}]
    return json.dumps({"question": question, "models": models, **extra})


def ask(api, content, who=ALICE):
    return api.client.post("/v1/ask", content=content, headers={**api.headers(who), **JSON})


def users_api(**kwargs):
    users = UserRig(respond=lambda request: ModelResponse(text=f"{request.settings.model} answers"), **kwargs)
    return users, make_api(rig=users.rig)


def test_two_models_answer_side_by_side_marked_unverified_and_no_key_is_in_the_response():
    users, api = users_api()
    response = ask(api, body())
    assert response.status_code == 200, response.text
    document = response.json()
    assert [(a["provider"], a["model"], a["ok"], a["text"]) for a in document["answers"]] == [("gemini", "gemini-test", True, "gemini-test answers"), ("groq", "groq-test", True, "groq-test answers")]
    assert document["verified"] is False and "unverified" in document["note"].lower()
    assert KEY not in response.text and "key-groq" not in response.text
    assert users.rig.model.calls == 0  # the service's own model was never asked: it is not a mission


def test_no_mission_is_created_so_there_is_nothing_to_replay_or_list():
    users, api = users_api()
    assert ask(api, body()).status_code == 200
    assert api.client.get("/v1/missions", headers=api.headers(ALICE)).status_code in (404, 405)  # there is still no listing, and nothing was recorded for one to show


def test_a_bad_body_is_a_422_in_the_one_error_shape_and_never_echoes_what_was_sent():
    users, api = users_api()
    bad = [
        "not json",
        body(question=""),
        body(models=[]),
        body(models=[{"provider": "gemini", "model": "m", "api_key": "short"}]),
        body(models=[{"provider": "gemini", "model": "has space", "api_key": KEY}]),
        body(models=[{"provider": "gemini", "model": "m", "api_key": KEY, "base_url": "https://evil.example"}]),  # an address is never the user's to give
        body(unexpected=1),
        body(models=[{"provider": "openai", "model": f"m{n}", "api_key": KEY} for n in range(4)]),
    ]
    for content in bad:
        response = ask(api, content)
        assert response.status_code == 422, (content[:60], response.text)
        assert response.json()["error"]["code"] == "invalid_request" and KEY not in response.text
    assert users.built == []


def test_a_provider_not_allowed_is_a_422_naming_the_allowed_ones_and_no_model_is_asked():
    users, api = users_api(providers=("gemini",))
    response = ask(api, body())
    assert response.status_code == 422 and "gemini" in response.json()["error"]["message"] and KEY not in response.text
    assert all(model.calls == 0 for _, _, model in users.built)


def test_a_service_that_did_not_opt_in_refuses():
    api = make_api()
    response = ask(api, body())
    assert response.status_code == 422 and "does not accept one of your own" in response.json()["error"]["message"] and KEY not in response.text


def test_an_unauthenticated_request_is_a_401_and_builds_nothing():
    users, api = users_api()
    response = api.client.post("/v1/ask", content=body(), headers=JSON)
    assert response.status_code == 401 and KEY not in response.text
    assert users.built == []


def test_a_body_over_the_ceiling_is_refused_before_it_is_parsed():
    users, api = users_api()
    response = ask(api, body(question="q" * 300_000))
    assert response.status_code == 413 and users.built == []


def test_only_post_is_allowed_here():
    users, api = users_api()
    assert api.client.get("/v1/ask", headers=api.headers(ALICE)).status_code == 405
