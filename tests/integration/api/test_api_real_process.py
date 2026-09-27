"""The backend as it is actually run: a real ``uvicorn`` process over a real PostgreSQL and a real model adapter talking to a fake model runtime over a socket (decisions.md D-230, D-233, D-234; V1.4-C).

Everything else in the suite reaches the API through ``TestClient`` in this process. These tests start the documented command (``uvicorn eidos.api.main:create_app_from_environment --factory``) as a child
process, so the environment composition root, the connection pool, real HTTP and a real process death are exercised once. The fake runtime answers over the model adapter's real wire format, so nothing here is a
measurement of any model. The PostgreSQL tests are opt-in (``-m postgres``, ``EIDOS_TEST_DATABASE_URL``, a disposable database) and never skip; the configuration-failure test needs no database and runs by default.
Every wait is bounded and a failure names what it was waiting for.
"""

import os
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import httpx
import psycopg
import pytest

import eidos_postgres_fixture as pg
from eidos_api_fixture import ALICE, BOB, SECRET, TENANT_A, TENANT_B, bearer
from eidos_fake_runtime import FakeRuntime, send_json
from eidos_search_fixture import cite_every_document
from eidos_service_fixture import make_spec

ROOT = Path(__file__).resolve().parents[3]
COMMAND = [sys.executable, "-m", "uvicorn", "eidos.api.main:create_app_from_environment", "--factory", "--host", "127.0.0.1", "--log-level", "warning"]
JSON = {"Content-Type": "application/json"}


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for(description: str, condition, timeout: float = 60.0, pause: float = 0.1):
    """A bounded wait: the condition's value once it is truthy, or a failure that says what did not happen."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = condition()
        if found:
            return found
        time.sleep(pause)
    raise AssertionError(f"timed out after {timeout:.0f}s waiting for: {description}")


def model_answers(gate: threading.Event | None = None, entered: threading.Event | None = None):
    """The fake runtime's behaviour: answer every prompt by citing every reference it shows (the scenarios' scripted model), in the runtime's own wire format. With a gate, hold each call until released."""

    def behavior(handler, body):
        if entered is not None:
            entered.set()
        if gate is not None:
            gate.wait(120)
        try:
            reply = cite_every_document(SimpleNamespace(prompt=body["prompt"]))
            send_json(handler, {"model": body["model"], "response": reply.text, "done": True, "prompt_eval_count": 100, "eval_count": 50})
        except OSError:
            pass  # the process that asked was killed

    return behavior


class Backend:
    """One ``uvicorn`` child process serving the API, configured only through its environment."""

    def __init__(self, database_url: str, model_url: str, log_path: Path, **extra):
        self.port = free_port()
        environment = {name: value for name, value in os.environ.items() if not name.startswith("EIDOS_")}
        environment.update(
            EIDOS_DATABASE_URL=database_url, EIDOS_MODEL_PROVIDER="ollama", EIDOS_MODEL_BASE_URL=model_url, EIDOS_MODEL_NAME="a-fake-model", EIDOS_MODEL_TEMPERATURE="0.0",
            EIDOS_MODEL_SEED="7", EIDOS_MODEL_MAX_OUTPUT_TOKENS="256", EIDOS_MODEL_TIMEOUT_SECONDS="60", EIDOS_JWT_SECRET=SECRET, EIDOS_WORKER_POOL_SIZE="2",
        )
        environment.update(extra)
        self.log_path = log_path
        self._log = open(log_path, "wb")
        self.process = subprocess.Popen(COMMAND + ["--port", str(self.port)], env=environment, cwd=ROOT, stdout=self._log, stderr=subprocess.STDOUT)
        self.client = httpx.Client(base_url=f"http://127.0.0.1:{self.port}", timeout=30.0)

    def ready(self):
        def up():
            assert self.process.poll() is None, f"the server exited with {self.process.returncode}:\n{self.log()}"
            try:
                return self.client.get("/v1/healthz").status_code == 200
            except httpx.TransportError:
                return False

        wait_for("the server to answer /v1/healthz", up, timeout=60.0, pause=0.2)
        return self

    def log(self) -> str:
        self._log.flush()
        return self.log_path.read_text(encoding="utf-8", errors="replace")[-3000:]

    def kill(self):
        self.process.kill()  # no shutdown hook runs: what a crash or an OOM kill looks like
        self.process.wait(30)

    def stop(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(30)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(30)
        self.client.close()
        self._log.close()


@pytest.fixture
def stack(tmp_path):
    """A migrated database with two tenants, a fake model runtime, and a factory for backends over them. Torn down completely."""
    url = pg.reset_schema()
    storage = pg.open_storage(url)
    storage.add_tenant(TENANT_A, "a")
    storage.add_tenant(TENANT_B, "b")
    from eidos.service import Role

    storage.add_member(TENANT_A, ALICE, Role.OWNER)
    storage.add_member(TENANT_B, BOB, Role.MEMBER)
    gate, entered = threading.Event(), threading.Event()
    gate.set()  # open unless a test closes it
    runtime = FakeRuntime(model_answers(gate, entered)).__enter__()
    started: list[Backend] = []

    def backend(**extra) -> Backend:
        server = Backend(url, runtime.url, tmp_path / f"server{len(started)}.log", **extra)
        started.append(server)
        return server.ready()

    try:
        yield SimpleNamespace(url=url, storage=storage, runtime=runtime, gate=gate, entered=entered, backend=backend)
    finally:
        gate.set()
        for server in started:
            server.stop()
        runtime.__exit__(None, None, None)
        storage.close()


def create(server, user=ALICE, key=None, **spec):
    headers = {**bearer(user), **JSON, **({"Idempotency-Key": key} if key else {})}
    return server.client.post("/v1/missions", content=make_spec(**spec).model_dump_json(), headers=headers)


def summary(server, mission_id, user=ALICE):
    response = server.client.get(f"/v1/missions/{mission_id}", headers=bearer(user))
    assert response.status_code == 200, response.text
    return response.json()


def rows(url: str, query: str, *params):
    with psycopg.connect(url) as connection:
        return connection.execute(query, params).fetchall()


# --- the default suite: a process that cannot be configured says which variable, and never a value ---------------------------------------------


def test_a_misconfigured_process_exits_naming_the_variable_and_echoing_no_secret(tmp_path):
    secret = "database-password-that-must-never-be-echoed-0123456789"
    environment = {name: value for name, value in os.environ.items() if not name.startswith("EIDOS_")}
    environment.update(
        EIDOS_DATABASE_URL=f"postgresql://someone:{secret}@127.0.0.1:1/postgres", EIDOS_MODEL_PROVIDER="ollama", EIDOS_MODEL_BASE_URL="http://127.0.0.1:1", EIDOS_JWT_SECRET=secret,
        EIDOS_MODEL_TEMPERATURE="0.0", EIDOS_MODEL_SEED="7", EIDOS_MODEL_MAX_OUTPUT_TOKENS="256", EIDOS_MODEL_TIMEOUT_SECONDS="60",  # EIDOS_MODEL_NAME is missing
    )
    finished = subprocess.run(COMMAND + ["--port", str(free_port())], env=environment, cwd=ROOT, capture_output=True, text=True, timeout=120)
    output = finished.stdout + finished.stderr
    assert finished.returncode != 0
    assert "EIDOS_MODEL_NAME is required" in output
    assert secret not in output and "someone" not in output  # the connection string was never opened, and never echoed


# --- PostgreSQL: the whole stack, as a real process --------------------------------------------------------------------------------------------


@pytest.mark.postgres
def test_the_documented_start_command_serves_a_whole_mission_over_real_http_and_postgres(stack):
    server = stack.backend()
    assert server.client.get("/v1/healthz").json() == {"status": "ok"}
    for headers in ({}, {"Authorization": "Bearer nonsense"}, bearer(ALICE, secret="x" * 40), bearer(ALICE, expires_in=-5), bearer(ALICE, audience="anon")):
        assert server.client.get(f"/v1/missions/{UUID(int=1)}", headers=headers).status_code == 401
    nul = create(server, goal="a" + chr(0) + "b")  # PostgreSQL cannot hold it: a 422 at the door, and never the 500 the audit found
    assert nul.status_code == 422 and nul.json()["error"]["code"] == "invalid_spec"
    assert server.client.get("/v1/nope", headers=bearer(ALICE)).json() == {"error": {"code": "not_found", "message": "no such resource"}}
    assert server.client.delete("/v1/missions/x", headers=bearer(ALICE)).json()["error"]["code"] == "method_not_allowed"
    first = create(server, key="one")
    assert first.status_code == 201 and first.json()["run_status"] == "created"
    mission_id = first.json()["mission_id"]
    assert create(server, key="one").json()["mission_id"] == mission_id and create(server, key="one").status_code == 200
    assert create(server, key="one", goal="something else").status_code == 409
    assert rows(stack.url, "select count(*) from eidos.mission_events where mission_id = %s", mission_id)[0][0] == 0  # creating wrote no event
    started = server.client.post(f"/v1/missions/{mission_id}/start", headers=bearer(ALICE))
    assert started.status_code == 202 and started.json()["run_status"] == "queued"
    assert server.client.post(f"/v1/missions/{mission_id}/start", headers=bearer(ALICE)).status_code == 409
    done = wait_for("the run to end", lambda: (s := summary(server, mission_id))["run_status"] in ("finished", "rejected", "error", "interrupted") and s, timeout=90)
    assert (done["run_status"], done["mission_status"], done["verified"], done["failure_cause"]) == ("finished", "completed", True, None), done
    assert done["counters"]["tokens_used"] > 0  # the tracker's facts reached the log through the real model adapter
    events = server.client.get(f"/v1/missions/{mission_id}/events?limit=500", headers=bearer(ALICE)).json()
    assert events["last_sequence"] == len(events["events"]) == done["last_sequence"]
    assert rows(stack.url, "select count(*) from eidos.mission_events where mission_id = %s", mission_id)[0][0] == events["last_sequence"]
    assert rows(stack.url, "select count(*) from eidos.artifacts where kind = 'supplied'")[0][0] == 3 and rows(stack.url, "select count(*) from eidos.artifacts where kind = 'step'")[0][0] >= 2
    result = server.client.get(f"/v1/missions/{mission_id}/result", headers=bearer(ALICE))
    assert result.status_code == 200 and result.json()["verified"] is True and result.json()["artifacts"] and result.json()["failure"] is None
    for suffix in ("/execution", "/evidence"):
        assert server.client.get(f"/v1/missions/{mission_id}{suffix}", headers=bearer(ALICE)).status_code == 200
    for method, suffix in (("GET", ""), ("GET", "/execution"), ("GET", "/events"), ("GET", "/result"), ("GET", "/evidence"), ("POST", "/start")):  # another tenant's user
        other = server.client.request(method, f"/v1/missions/{mission_id}{suffix}", headers=bearer(BOB))
        nothing = server.client.request(method, f"/v1/missions/{UUID(int=7)}{suffix}", headers=bearer(BOB))
        assert other.status_code == nothing.status_code == 404 and other.json() == nothing.json(), suffix
    assert stack.runtime.requests and all(path == "/api/generate" for path, _, _ in stack.runtime.requests)


@pytest.mark.postgres
def test_a_process_killed_mid_run_leaves_a_readable_prefix_and_the_next_process_marks_the_run_interrupted(stack):
    stack.gate.clear()  # every model call is held: the run cannot finish while the process is killed
    first = stack.backend()
    mission_id = create(first).json()["mission_id"]
    assert first.client.post(f"/v1/missions/{mission_id}/start", headers=bearer(ALICE)).status_code == 202
    wait_for("the run to reach its first model call", stack.entered.is_set, timeout=60)
    wait_for("the run's first events to be durable", lambda: summary(first, mission_id)["last_sequence"] >= 3, timeout=30)
    assert summary(first, mission_id)["run_status"] == "running"
    first.kill()
    durable = rows(stack.url, "select sequence from eidos.mission_events where mission_id = %s order by sequence", mission_id)
    assert [row[0] for row in durable] == list(range(1, len(durable) + 1)) and len(durable) >= 3  # a contiguous prefix, whatever moment the process died at
    assert rows(stack.url, "select run_status from eidos.missions where mission_id = %s", mission_id)[0][0] == "running"  # the dead process could not say otherwise

    stack.gate.set()
    second = stack.backend()  # startup recovery runs before the first request is served
    recovered = summary(second, mission_id)
    assert recovered["run_status"] == "interrupted" and "restarted" in recovered["run_status_reason"]
    assert recovered["last_sequence"] == len(durable) and recovered["mission_status"] == "created" and recovered["failure_cause"] is None  # nothing was invented to explain the gap
    page = second.client.get(f"/v1/missions/{mission_id}/events?limit=500", headers=bearer(ALICE)).json()
    assert [item["event"]["sequence"] for item in page["events"]] == [row[0] for row in durable]
    assert page["events"][-1]["event"]["type"] not in ("MISSION_COMPLETED", "MISSION_FAILED")
    assert second.client.get(f"/v1/missions/{mission_id}/execution", headers=bearer(ALICE)).status_code == 200
    assert second.client.get(f"/v1/missions/{mission_id}/result", headers=bearer(ALICE)).status_code == 409
    assert second.client.post(f"/v1/missions/{mission_id}/start", headers=bearer(ALICE)).status_code == 409  # never resumed and never retried
    fresh = create(second).json()["mission_id"]
    assert second.client.post(f"/v1/missions/{fresh}/start", headers=bearer(ALICE)).status_code == 202
    wait_for("a new mission to finish on the recovered service", lambda: summary(second, fresh)["run_status"] == "finished", timeout=90)
    assert summary(second, fresh)["mission_status"] == "completed"
    assert summary(second, mission_id)["run_status"] == "interrupted" and summary(second, mission_id)["last_sequence"] == len(durable)  # and it stays as it was


@pytest.mark.postgres
def test_many_simultaneous_starts_over_real_http_run_the_mission_exactly_once(stack):
    server = stack.backend()
    mission_id = create(server).json()["mission_id"]
    with ThreadPoolExecutor(8) as pool:
        codes = list(pool.map(lambda _: server.client.post(f"/v1/missions/{mission_id}/start", headers=bearer(ALICE)).status_code, range(8)))
    assert codes.count(202) == 1 and sorted(set(codes)) == [202, 409], codes
    done = wait_for("the run to end", lambda: (s := summary(server, mission_id))["run_status"] == "finished" and s, timeout=90)
    calls_of_one_run = len(stack.runtime.requests)
    sequences = [row[0] for row in rows(stack.url, "select sequence from eidos.mission_events where mission_id = %s order by sequence", mission_id)]
    assert sequences == list(range(1, len(sequences) + 1)) == list(range(1, done["last_sequence"] + 1))
    assert rows(stack.url, "select count(*) from eidos.mission_events where mission_id = %s and event_type = 'MISSION_CREATED'", mission_id)[0][0] == 1
    other = create(server).json()["mission_id"]
    assert server.client.post(f"/v1/missions/{other}/start", headers=bearer(ALICE)).status_code == 202
    wait_for("a second, uncontended run to end", lambda: summary(server, other)["run_status"] == "finished", timeout=90)
    assert len(stack.runtime.requests) == 2 * calls_of_one_run  # the contended mission cost exactly one run's model calls


@pytest.mark.postgres
def test_many_simultaneous_creates_with_one_key_over_real_http_and_postgres_make_one_mission(stack):
    server = stack.backend()
    with ThreadPoolExecutor(8) as pool:
        answers = list(pool.map(lambda _: create(server, key="race"), range(8)))
    assert sorted(r.status_code for r in answers) == [200] * 7 + [201], [r.text for r in answers]  # the database's unique constraint decided the race, and the losers were told the winner's mission
    assert len({r.json()["mission_id"] for r in answers}) == 1
    assert rows(stack.url, "select count(*) from eidos.missions where idempotency_key = 'race'")[0][0] == 1
    assert create(server, key="race", goal="another").status_code == 409


@pytest.mark.postgres
def test_two_tenants_running_at_once_over_real_http_each_read_only_their_own_missions(stack):
    server = stack.backend()
    alices, bobs = create(server, ALICE).json()["mission_id"], create(server, BOB).json()["mission_id"]
    assert server.client.post(f"/v1/missions/{alices}/start", headers=bearer(ALICE)).status_code == 202
    assert server.client.post(f"/v1/missions/{bobs}/start", headers=bearer(BOB)).status_code == 202
    for mission_id, user in ((alices, ALICE), (bobs, BOB)):
        wait_for("a run to finish", lambda: summary(server, mission_id, user)["run_status"] == "finished", timeout=90)
    tenants = {mission: tenant for mission, tenant in rows(stack.url, "select mission_id::text, tenant_id from eidos.missions")}
    assert tenants[alices] == TENANT_A and tenants[bobs] == TENANT_B
    for mission_id, tenant in ((alices, TENANT_A), (bobs, TENANT_B)):
        assert {row[0] for row in rows(stack.url, "select tenant_id from eidos.mission_events where mission_id = %s", mission_id)} == {tenant}
    assert server.client.get(f"/v1/missions/{alices}", headers=bearer(BOB)).status_code == 404
    assert server.client.get(f"/v1/missions/{bobs}", headers=bearer(ALICE)).status_code == 404
