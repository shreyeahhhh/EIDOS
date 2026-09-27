"""The HTTP surface, end to end over the in-memory service (decisions.md D-233, D-234; invariants 2, 13 and 15; V1.4-B).

Real FastAPI, real JWT verification and the real runtime on a scripted model. What is held: the eight endpoints and no others; every route but the health check needs a token; a client names no
tenant it does not belong to and sets no identifier; another tenant's mission is a 404 identical to a missing one; an API failure and a mission failure never share a channel (a failed mission is a
200); an unexpected fault is a generic 500; and nothing in any answer is a confidence or a score.
"""

import json
from uuid import UUID, uuid4

import pytest

from eidos.service import RunnerConfig, RunStatus, ServiceConfig
from eidos.validation import SystemLimits

from eidos_agents_factories import make_settings
from eidos_replanning_factories import ScriptedCalls, always_fails
from eidos_search_fixture import cite_every_document
from eidos_api_fixture import ALICE, BOB, CAROL, DAVE, TENANT_A, TENANT_B, make_api, spec_json, token_for

JSON = {"Content-Type": "application/json"}


def create(api, user=ALICE, body=None, *, tenant=None, key=None, **spec):
    headers = {**api.headers(user, tenant=tenant), **JSON}
    if key is not None:
        headers["Idempotency-Key"] = key
    return api.client.post("/v1/missions", content=body if body is not None else spec_json(**spec), headers=headers)


def run(api, user=ALICE, **spec):
    made = create(api, user, **spec)
    assert made.status_code == 201, made.text
    mission_id = made.json()["mission_id"]
    started = api.client.post(f"/v1/missions/{mission_id}/start", headers=api.headers(user))
    assert started.status_code == 202, started.text
    assert api.rig.runner.wait_idle(60)
    return mission_id


def get(api, path, user=ALICE, **kwargs):
    return api.client.get(path, headers=api.headers(user, **kwargs))


def keys_of(document):
    if isinstance(document, dict):
        for name, value in document.items():
            yield name
            yield from keys_of(value)
    elif isinstance(document, list):
        for value in document:
            yield from keys_of(value)


# --- the surface: eight endpoints and no others -----------------------------------------------------------------------------------------


def test_the_surface_is_exactly_the_eight_endpoints():
    api = make_api()
    routes = {(method, route.path) for route in api.client.app.routes for method in getattr(route, "methods", ()) if method != "HEAD" and route.path.startswith("/v1/")}
    assert routes - {("GET", "/v1/openapi.json")} == {
        ("POST", "/v1/missions"), ("POST", "/v1/missions/{mission_id}/start"), ("GET", "/v1/missions/{mission_id}"), ("GET", "/v1/missions/{mission_id}/execution"),
        ("GET", "/v1/missions/{mission_id}/events"), ("GET", "/v1/missions/{mission_id}/result"), ("GET", "/v1/missions/{mission_id}/evidence"), ("GET", "/v1/healthz"),
    }


@pytest.mark.parametrize("method, path", [("GET", "/v1/missions"), ("DELETE", "/v1/missions/x"), ("POST", "/v1/missions/x/cancel"), ("GET", "/v1/missions/x/replay"),
                                          ("GET", "/v1/missions/x/strategy"), ("GET", "/docs"), ("GET", "/redoc"), ("GET", "/")])
def test_the_deferred_endpoints_and_the_interactive_docs_do_not_exist(method, path):
    api = make_api()
    assert api.client.request(method, path, headers=api.headers()).status_code in (404, 405)


def test_the_health_check_needs_no_token_and_says_only_that_it_is_up():
    api = make_api()
    response = api.client.get("/v1/healthz")
    assert (response.status_code, response.json()) == (200, {"status": "ok"})


# --- authentication ---------------------------------------------------------------------------------------------------------------------


AUTHENTICATED = [("POST", "/v1/missions"), ("POST", "/v1/missions/{id}/start"), ("GET", "/v1/missions/{id}"), ("GET", "/v1/missions/{id}/execution"), ("GET", "/v1/missions/{id}/events"),
                 ("GET", "/v1/missions/{id}/result"), ("GET", "/v1/missions/{id}/evidence")]


@pytest.mark.parametrize("method, path", AUTHENTICATED)
@pytest.mark.parametrize("authorization", [None, "", "Bearer", "Bearer ", "Basic abc", "Token abc", "Bearer not.a.jwt"])
def test_every_route_but_the_health_check_refuses_a_missing_or_unusable_token(method, path, authorization):
    api = make_api()
    headers = {} if authorization is None else {"Authorization": authorization}
    response = api.client.request(method, path.format(id=uuid4()), headers=headers, content=b"{}")
    assert response.status_code == 401 and response.json()["error"]["code"] == "unauthenticated" and response.headers["www-authenticate"] == "Bearer"


def test_an_expired_or_foreign_audience_or_wrongly_signed_token_is_a_401_that_says_nothing_of_why():
    api = make_api()
    bodies = set()
    for kwargs in ({"expires_in": -10}, {"audience": "anon"}, {"secret": "x" * 40}, {"subject": "nope"}):
        response = api.client.get(f"/v1/missions/{uuid4()}", headers=api.headers(**kwargs))
        assert response.status_code == 401
        bodies.add(response.text)
    assert len(bodies) == 1  # the four are indistinguishable to a caller


def test_a_lowercase_bearer_scheme_is_accepted():
    api = make_api()
    token = token_for(ALICE)
    assert api.client.get(f"/v1/missions/{uuid4()}", headers={"Authorization": f"bearer {token}"}).status_code == 404


def test_a_valid_token_of_a_user_with_no_tenant_is_a_403():
    api = make_api()
    response = api.client.get(f"/v1/missions/{uuid4()}", headers=api.headers(DAVE))
    assert response.status_code == 403 and response.json()["error"]["code"] == "no_tenant_membership"


def test_a_key_source_that_is_down_is_a_503_and_not_a_401():
    from eidos.api import AuthUnavailable, JwtSettings, JwtVerifier

    class Down:
        def key_for(self, token):
            raise AuthUnavailable("down")

    api = make_api(verifier=JwtVerifier(keys=Down(), settings=JwtSettings(audience="authenticated", algorithms=("HS256",))))
    response = api.client.get(f"/v1/missions/{uuid4()}", headers=api.headers())
    assert response.status_code == 503 and response.json()["error"]["code"] == "auth_unavailable"


# --- tenancy ------------------------------------------------------------------------------------------------------------------------------


def test_a_user_of_several_tenants_must_name_one_and_may_only_name_their_own():
    api = make_api()
    assert create(api, CAROL).status_code == 422 and create(api, CAROL).json()["error"]["code"] == "tenant_required"
    made = create(api, CAROL, tenant=TENANT_B)
    assert made.status_code == 201
    stranger = create(api, ALICE, tenant=TENANT_B)  # a real tenant, not hers
    missing = create(api, ALICE, tenant=UUID(int=0xC0C0))  # one that does not exist
    assert (stranger.status_code, missing.status_code) == (404, 404) and stranger.json() == missing.json()
    assert create(api, ALICE, tenant="not-a-uuid").status_code == 404


def test_a_mission_belongs_to_the_tenant_it_was_created_for_and_the_client_cannot_move_it():
    api = make_api()
    mission_id = create(api, CAROL, tenant=TENANT_A).json()["mission_id"]
    assert get(api, f"/v1/missions/{mission_id}", CAROL, tenant=TENANT_A).json()["tenant_id"] == str(TENANT_A)
    assert get(api, f"/v1/missions/{mission_id}", CAROL, tenant=TENANT_B).status_code == 404
    assert get(api, f"/v1/missions/{mission_id}", ALICE).status_code == 200  # her own tenant's mission, by her token


def test_a_client_supplied_tenant_or_identifier_in_the_body_is_refused():
    api = make_api()
    base = json.loads(spec_json())
    for extra in ({"tenant_id": str(TENANT_B)}, {"mission_id": str(uuid4())}, {"execution_id": str(uuid4())}, {"created_by": str(BOB)}, {"reliability_contract_id": str(uuid4())}):
        response = create(api, ALICE, body=json.dumps({**base, **extra}))
        assert response.status_code == 422 and response.json()["error"]["code"] == "invalid_spec", extra
    body = json.loads(spec_json())
    body["reliability"]["tenant_id"] = str(TENANT_B)
    assert create(api, ALICE, body=json.dumps(body)).status_code == 422
    assert api.rig.storage._missions == {}


def test_every_read_and_start_of_another_tenants_mission_is_the_same_404_as_a_missing_mission():
    api = make_api()
    mission_id = run(api)
    missing = str(uuid4())
    for method, suffix in (("GET", ""), ("GET", "/execution"), ("GET", "/events"), ("GET", "/result"), ("GET", "/evidence"), ("POST", "/start")):
        theirs = api.client.request(method, f"/v1/missions/{mission_id}{suffix}", headers=api.headers(BOB))
        nothing = api.client.request(method, f"/v1/missions/{missing}{suffix}", headers=api.headers(BOB))
        assert theirs.status_code == nothing.status_code == 404 and theirs.json() == nothing.json(), suffix
    assert get(api, f"/v1/missions/{mission_id}").json()["run_status"] == "finished"


@pytest.mark.parametrize("bad", ["x", "1234", "00000000-0000-0000-0000-00000000000g", "%00", "a" * 300])
def test_a_mission_id_that_is_not_a_uuid_is_a_404(bad):
    api = make_api()
    for method, suffix in (("GET", ""), ("GET", "/events"), ("POST", "/start")):
        assert api.client.request(method, f"/v1/missions/{bad}{suffix}", headers=api.headers()).status_code == 404


# --- create -------------------------------------------------------------------------------------------------------------------------------


def test_creating_a_mission_is_a_201_with_its_id_and_a_created_run_and_it_writes_no_event():
    api = make_api()
    response = create(api)
    body = response.json()
    assert response.status_code == 201 and set(body) == {"mission_id", "run_status", "created_at"} and body["run_status"] == "created"
    assert UUID(body["mission_id"]) and api.rig.storage.read(TENANT_A, UUID(body["mission_id"])) == ()
    summary = get(api, f"/v1/missions/{body['mission_id']}").json()
    assert (summary["run_status"], summary["mission_status"], summary["last_sequence"], summary["counters"]) == ("created", None, 0, None)


def test_the_same_idempotency_key_is_the_same_mission_and_a_changed_request_is_a_409():
    api = make_api()
    first = create(api, key="key-1")
    again = create(api, key="key-1")
    assert (first.status_code, again.status_code) == (201, 200) and again.json()["mission_id"] == first.json()["mission_id"]
    changed = create(api, key="key-1", goal="a different goal")
    assert changed.status_code == 409 and changed.json()["error"]["code"] == "idempotency_conflict"
    assert len(api.rig.storage._missions) == 1
    assert create(api, key="k" * 129).status_code == 422 and create(api, key="").status_code == 422


def test_an_invalid_specification_is_a_422_with_every_problem_named_by_field():
    api = make_api()
    response = create(api, goal="   ", required_capabilities=())
    error = response.json()["error"]
    assert response.status_code == 422 and error["code"] == "invalid_spec" and {item["field"] for item in error["details"]} >= {"goal", "required_capabilities"}
    assert api.rig.storage._missions == {}


@pytest.mark.parametrize("body", [b"", b"not json", b"[]", b"null", b'{"goal": 1}', b"{" * 10, b"\xff\xfe\x00"])
def test_a_body_that_is_not_a_mission_specification_is_a_422_and_never_a_500(body):
    api = make_api()
    response = create(api, body=body)
    assert response.status_code == 422 and response.json()["error"]["code"] == "invalid_spec"


def test_a_wrong_type_is_refused_where_the_contracts_are_strict_and_a_json_number_is_accepted():
    api = make_api()
    body = json.loads(spec_json())
    body["reliability"]["min_quality"] = "0.5"
    assert create(api, body=json.dumps(body)).status_code == 422
    body["reliability"]["min_quality"] = 1  # a JSON integer is a valid float
    assert create(api, body=json.dumps(body)).status_code == 201


def test_a_body_over_the_limit_is_a_413_whether_or_not_it_declares_its_length():
    api = make_api()
    limit = api.rig.config.ceilings.max_request_body_bytes
    big = b'{"goal": "' + b"x" * (limit + 10) + b'"}'
    declared = api.client.post("/v1/missions", content=big, headers={**api.headers(), **JSON})
    assert declared.status_code == 413 and declared.json()["error"]["code"] == "payload_too_large"
    chunks = (big[i:i + 4096] for i in range(0, len(big), 4096))  # no Content-Length: the body is counted as it arrives
    streamed = api.client.post("/v1/missions", content=chunks, headers={**api.headers(), **JSON})
    assert streamed.status_code == 413
    assert api.rig.storage._missions == {}


def test_a_ceiling_is_a_422_and_the_request_is_not_clamped():
    api = make_api()
    response = create(api, goal="x" * (api.rig.config.ceilings.max_goal_chars + 1))
    assert response.status_code == 422 and "goal" in {item["field"] for item in response.json()["error"]["details"]}


# --- start ---------------------------------------------------------------------------------------------------------------------------------


def test_starting_a_mission_is_a_202_and_a_mission_is_started_once():
    api = make_api()
    mission_id = create(api).json()["mission_id"]
    started = api.client.post(f"/v1/missions/{mission_id}/start", headers=api.headers())
    assert started.status_code == 202 and started.json() == {"mission_id": mission_id, "run_status": "queued"}
    assert api.rig.runner.wait_idle(60)
    again = api.client.post(f"/v1/missions/{mission_id}/start", headers=api.headers())
    assert again.status_code == 409 and again.json()["error"]["code"] == "not_startable"


def test_a_tenants_second_run_while_one_is_active_is_a_409_and_a_full_runner_is_a_503():
    import threading

    gate, entered = threading.Event(), threading.Semaphore(0)

    def held(request):
        entered.release()
        assert gate.wait(60)
        return cite_every_document(request)

    api = make_api(respond=held, runner=RunnerConfig(worker_pool_size=1, max_queued_runs=0, max_active_runs_per_tenant=1, flush_backoff_seconds=0.0))
    first, second = create(api).json()["mission_id"], create(api).json()["mission_id"]
    assert api.client.post(f"/v1/missions/{first}/start", headers=api.headers()).status_code == 202
    assert entered.acquire(timeout=30)
    limited = api.client.post(f"/v1/missions/{second}/start", headers=api.headers())
    assert limited.status_code == 409 and limited.json()["error"]["code"] == "tenant_run_limit"
    busy = create(api, BOB).json()["mission_id"]
    full = api.client.post(f"/v1/missions/{busy}/start", headers=api.headers(BOB))
    assert full.status_code == 503 and full.json()["error"]["code"] == "busy"
    assert get(api, f"/v1/missions/{second}").json()["run_status"] == "created" and get(api, f"/v1/missions/{busy}", BOB).json()["run_status"] == "created"  # both are still startable
    gate.set()
    assert api.rig.runner.wait_idle(60)
    assert api.client.post(f"/v1/missions/{second}/start", headers=api.headers()).status_code == 202
    assert api.rig.runner.wait_idle(60)


# --- reads before and after a run --------------------------------------------------------------------------------------------------------------


def test_before_a_run_there_is_nothing_to_read_and_each_read_says_so_in_its_own_409():
    api = make_api()
    mission_id = create(api).json()["mission_id"]
    for suffix, code in (("/execution", "no_events"), ("/evidence", "no_events"), ("/result", "not_finished")):
        response = get(api, f"/v1/missions/{mission_id}{suffix}")
        assert response.status_code == 409 and response.json()["error"]["code"] == code, suffix
    events = get(api, f"/v1/missions/{mission_id}/events")
    assert events.status_code == 200 and events.json() == {"events": [], "last_sequence": 0, "next_after": 0}


def test_a_completed_mission_reads_back_as_its_summary_execution_events_result_and_evidence():
    api = make_api()
    mission_id = run(api)
    summary = get(api, f"/v1/missions/{mission_id}").json()
    assert (summary["run_status"], summary["mission_status"], summary["verified"], summary["failure_cause"]) == ("finished", "completed", True, None)
    assert summary["run_status_reason"] is None and summary["counters"]["agent_calls_used"] > 0 and summary["counters"]["tokens_used"] > 0 and summary["goal"]
    execution = get(api, f"/v1/missions/{mission_id}/execution")
    assert execution.status_code == 200 and execution.json()["mission_status"] == "completed" and execution.json()["steps"]
    result = get(api, f"/v1/missions/{mission_id}/result").json()
    assert (result["mission_status"], result["verified"], result["failure"]) == ("completed", True, None) and result["verdict"]["verdict"] == "pass" and result["artifacts"]
    evidence = get(api, f"/v1/missions/{mission_id}/evidence").json()
    assert evidence["audit"]["traces"] and {trace["kind"] for trace in evidence["audit"]["traces"]} == {"not_evidence"}  # no knowledge base was supplied, so nothing was retrieved


def test_the_events_endpoint_pages_by_sequence_and_the_pages_are_the_recorded_log():
    api = make_api()
    mission_id = run(api)
    total = get(api, f"/v1/missions/{mission_id}").json()["last_sequence"]
    assert total > 6
    seen, after = [], 0
    while True:
        page = get(api, f"/v1/missions/{mission_id}/events?after={after}&limit=5").json()
        assert page["last_sequence"] == total
        if not page["events"]:
            break
        assert len(page["events"]) <= 5 and page["events"][0]["event"]["sequence"] == after + 1
        seen.extend(page["events"])
        after = page["next_after"]
    assert [item["event"]["sequence"] for item in seen] == list(range(1, total + 1))
    assert seen[0]["event"]["type"] == "MISSION_CREATED" and seen[-1]["event"]["type"] in ("MISSION_COMPLETED", "MISSION_FAILED")
    assert get(api, f"/v1/missions/{mission_id}/events").json()["events"] == seen  # the default page holds the whole of a short log


@pytest.mark.parametrize("query", ["after=-1", "limit=0", "limit=-3", "limit=100000", "after=x", "limit=x", "after=1.5"])
def test_a_page_request_outside_its_bounds_is_a_422_and_never_clamped(query):
    api = make_api()
    mission_id = create(api).json()["mission_id"]
    response = get(api, f"/v1/missions/{mission_id}/events?{query}")
    assert response.status_code == 422 and response.json()["error"]["code"] == "invalid_request"


def test_a_replanned_mission_reports_its_replan_and_the_run_still_finished():
    api = make_api(respond=ScriptedCalls((cite_every_document, always_fails), then=cite_every_document))
    mission_id = run(api)
    summary = get(api, f"/v1/missions/{mission_id}").json()
    assert (summary["run_status"], summary["mission_status"], summary["plan_version"], summary["counters"]["replans_used"]) == ("finished", "completed", 2, 1)
    kinds = [item["event"]["type"] for item in get(api, f"/v1/missions/{mission_id}/events?limit=500").json()["events"]]
    assert kinds.count("PLAN_GENERATED") == 2 and "REPLAN_TRIGGERED" in kinds


# --- an API failure and a mission failure never share a channel ---------------------------------------------------------------------------------


def test_a_mission_that_failed_is_a_200_that_says_why_and_never_an_http_error():
    api = make_api(respond=always_fails)
    mission_id = run(api)
    summary = get(api, f"/v1/missions/{mission_id}")
    result = get(api, f"/v1/missions/{mission_id}/result")
    assert (summary.status_code, result.status_code) == (200, 200)
    assert (summary.json()["run_status"], summary.json()["mission_status"]) == ("finished", "failed") and summary.json()["failure_cause"]
    assert result.json()["mission_status"] == "failed" and result.json()["failure"]["cause"] == summary.json()["failure_cause"] and result.json()["artifacts"] == []
    assert get(api, f"/v1/missions/{mission_id}/execution").status_code == 200 and get(api, f"/v1/missions/{mission_id}/evidence").status_code == 200


def test_a_rejected_run_is_reported_as_a_run_status_and_has_no_result():
    tiny = SystemLimits(max_nodes=1, max_depth=1, max_parallel_branches=1, max_retries=3, max_replans=3, max_agent_calls=64, max_tool_calls=16, max_execution_time=600_000, max_tokens=200_000)
    config = ServiceConfig(limits=tiny, model_settings=make_settings(), allowed_actions=frozenset(), runner=RunnerConfig(flush_backoff_seconds=0.0))
    api = make_api(config=config)
    mission_id = run(api)
    summary = get(api, f"/v1/missions/{mission_id}").json()
    assert summary["run_status"] == "rejected" and summary["run_status_reason"].startswith("no_selectable_strategy") and summary["mission_status"] is None
    assert get(api, f"/v1/missions/{mission_id}/result").status_code == 409


def test_an_unexpected_fault_is_a_generic_500_that_tells_nothing_of_the_inside(monkeypatch):
    api = make_api()
    mission_id = create(api).json()["mission_id"]

    def explode(*args, **kwargs):
        raise RuntimeError("secret-connection-string postgresql://user:hunter2@host/db")

    monkeypatch.setattr(api.rig.service, "get_mission", explode)
    response = get(api, f"/v1/missions/{mission_id}")
    assert response.status_code == 500 and response.json()["error"]["code"] == "internal_error"
    assert "hunter2" not in response.text and "secret" not in response.text and "RuntimeError" not in response.text


def test_a_storage_fault_is_a_503_and_a_stored_log_that_does_not_replay_is_a_500(monkeypatch):
    from eidos.service import StorageError

    api = make_api()
    mission_id = run(api)

    def down(*args, **kwargs):
        raise StorageError("connection refused by 10.0.0.5")

    monkeypatch.setattr(api.rig.storage, "read", down)
    response = get(api, f"/v1/missions/{mission_id}")
    assert response.status_code == 503 and response.json()["error"]["code"] == "storage_unavailable" and "10.0.0.5" not in response.text
    monkeypatch.undo()
    del api.rig.storage._events[UUID(mission_id)][2]
    broken = get(api, f"/v1/missions/{mission_id}/execution")
    assert broken.status_code == 500 and broken.json()["error"]["code"] == "integrity_error"


# --- invariants visible in every answer ------------------------------------------------------------------------------------------------------------


def test_no_answer_carries_a_confidence_or_a_score():
    api = make_api()
    mission_id = run(api)
    banned = {"confidence", "score", "probability", "certainty", "reliability_score", "quality_score"}
    for suffix in ("", "/execution", "/result", "/evidence", "/events?limit=500"):
        names = set(keys_of(get(api, f"/v1/missions/{mission_id}{suffix}").json()))
        assert not names & banned, (suffix, names & banned)


def test_run_status_is_an_api_field_and_never_appears_inside_the_recorded_events_or_the_execution():
    api = make_api()
    mission_id = run(api)
    assert "run_status" not in json.dumps(get(api, f"/v1/missions/{mission_id}/events?limit=500").json())
    assert "run_status" not in json.dumps(get(api, f"/v1/missions/{mission_id}/execution").json())
    assert "queued" not in json.dumps(get(api, f"/v1/missions/{mission_id}/events?limit=500").json())


def test_every_error_has_one_shape_and_no_stack_or_internal_name():
    api = make_api()
    samples = [
        api.client.get("/v1/missions/x", headers={}),
        api.client.get(f"/v1/missions/{uuid4()}", headers=api.headers(DAVE)),
        api.client.get(f"/v1/missions/{uuid4()}", headers=api.headers()),
        create(api, body=b"nope"),
        get(api, f"/v1/missions/{uuid4()}/events?limit=0"),
        api.client.get("/v1/nope", headers=api.headers()),
        api.client.delete(f"/v1/missions/{uuid4()}", headers=api.headers()),
    ]
    for response in samples:
        body = response.json()
        assert set(body) == {"error"} and {"code", "message"} <= set(body["error"]) and set(body["error"]) <= {"code", "message", "details"}
        assert "Traceback" not in response.text and "site-packages" not in response.text and ".py" not in response.text


def test_the_openapi_document_is_served_under_v1_and_the_interactive_docs_are_off():
    api = make_api()
    assert api.client.get("/v1/openapi.json").status_code == 200
    assert api.client.get("/docs").status_code == 404 and api.client.get("/redoc").status_code == 404


# --- startup and shutdown -----------------------------------------------------------------------------------------------------------------------


def test_starting_the_app_recovers_runs_a_previous_process_left_active_and_writes_no_event():
    from eidos_service_fixture import make_rig, make_spec
    from eidos_storage_helpers import NOW

    rig = make_rig()
    context = rig.context("alice")
    queued, running, waiting = (rig.service.create_mission(context, make_spec())[0].mission_id for _ in range(3))
    for mission_id, status in ((queued, RunStatus.QUEUED), (running, RunStatus.RUNNING)):
        assert rig.storage.transition(TENANT_A, mission_id, expected=(RunStatus.CREATED,), new=status, reason=None, at=NOW)
    api = make_api(rig=rig)  # entering the app runs startup recovery
    for mission_id in (queued, running):
        summary = get(api, f"/v1/missions/{mission_id}").json()
        assert summary["run_status"] == "interrupted" and "restarted" in summary["run_status_reason"] and summary["mission_status"] is None and summary["last_sequence"] == 0
        assert api.client.post(f"/v1/missions/{mission_id}/start", headers=api.headers()).status_code == 409  # an interrupted run is never resumed
        assert get(api, f"/v1/missions/{mission_id}/events").json()["events"] == []  # and recovery wrote no event
    assert get(api, f"/v1/missions/{waiting}").json()["run_status"] == "created"


def test_leaving_the_app_runs_its_closers_after_the_runner_is_shut_down():
    from fastapi.testclient import TestClient

    from eidos.api import JwtSettings, JwtVerifier, StaticKey, create_app

    from eidos_api_fixture import SECRET
    from eidos_service_fixture import make_rig

    rig = make_rig()
    order = []
    original = rig.runner.shutdown
    rig.runner.shutdown = lambda **kwargs: (order.append("runner"), original(**kwargs))[1]
    verifier = JwtVerifier(keys=StaticKey(SECRET), settings=JwtSettings(audience="authenticated", algorithms=("HS256",)))
    app = create_app(service=rig.service, verifier=verifier, max_body_bytes=1000, closers=(lambda: order.append("closer"),))
    with TestClient(app):
        assert order == []
    assert order == ["runner", "closer"]


# --- V1.4-C acceptance audit ------------------------------------------------------------------------------------------------------------------------


def test_free_text_holding_a_nul_is_a_422_naming_the_field_and_never_a_500():
    """Found over a real PostgreSQL: a NUL in the goal, an information dependency or a document was a 500 (the database refuses it). The door refuses it whatever the storage is."""
    api = make_api()
    nul = chr(0)
    body = json.loads(spec_json())
    body["goal"] = "a" + nul + "b"
    body["information_dependencies"] = ["ok", "dep" + nul]
    body["supplied_documents"][0]["content"] = "x" + nul
    response = create(api, body=json.dumps(body))
    assert response.status_code == 422 and response.json()["error"]["code"] == "invalid_spec"
    assert {"goal", "information_dependencies[1]", "supplied_documents[0].content"} <= {item["field"] for item in response.json()["error"]["details"]}
    assert api.rig.storage._missions == {}


def test_a_path_or_a_method_the_api_does_not_have_answers_in_the_same_error_shape_as_every_other_error():
    api = make_api()
    missing = api.client.get("/v1/nope", headers=api.headers())
    assert missing.status_code == 404 and missing.json() == {"error": {"code": "not_found", "message": "no such resource"}}
    for method, path in (("POST", "/v1/healthz"), ("DELETE", f"/v1/missions/{uuid4()}"), ("PUT", "/v1/missions"), ("GET", f"/v1/missions/{uuid4()}/start")):
        wrong = api.client.request(method, path, headers=api.headers())
        assert wrong.status_code == 405 and wrong.json()["error"]["code"] == "method_not_allowed" and set(wrong.json()) == {"error"}, (method, path)
        assert "allow" in wrong.headers  # the framework's own hint survives
    assert api.client.get("/nope").json()["error"]["code"] == "not_found"  # even without a token: it is not an authenticated route


def test_every_code_the_api_can_answer_with_is_documented_in_section_8_of_docs_13():
    from pathlib import Path

    from eidos.api.errors import STATUS_OF

    text = (Path(__file__).resolve().parents[3] / "docs" / "13_product_backend.md").read_text(encoding="utf-8")
    section = text[text.index("## 8. Failure semantics"):text.index("## 9. The configuration profile")]
    assert {code for code in STATUS_OF if f"`{code}`" not in section} == set()
    for code, status in STATUS_OF.items():
        row = next(line for line in section.splitlines() if f"`{code}`" in line and line.startswith("|"))
        assert str(status) in row, (code, status, row)


def test_many_simultaneous_creates_with_one_key_make_one_mission_and_a_different_body_conflicts():
    api = make_api()
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(8) as pool:
        answers = list(pool.map(lambda _: create(api, key="race"), range(8)))
    assert sorted(r.status_code for r in answers) == [200] * 7 + [201]
    assert len({r.json()["mission_id"] for r in answers}) == 1 and len(api.rig.storage._missions) == 1
    assert create(api, key="race", goal="another").status_code == 409
