"""The composition root: configuration fails before anything is served, names the variable and never echoes a value (decisions.md D-233, D-234; ``docs/13`` section 9; V1.4-B).

Nothing here needs a database: every case that must fail fails before the connection is opened, and the one that succeeds is handed a stand-in for the storage.
"""

import pytest

import eidos.api.main as main
from eidos.api.main import ConfigurationError, build_verifier, create_app_from_environment
from eidos.service import InMemoryStorage

SECRET_VALUE = "value-that-must-never-be-echoed-0123456789abcdef"

GOOD = {
    "EIDOS_MODEL_PROVIDER": "ollama",
    "EIDOS_MODEL_BASE_URL": "http://model.example.test:1234",
    "EIDOS_MODEL_NAME": "some-model",
    "EIDOS_MODEL_TEMPERATURE": "0.0",
    "EIDOS_MODEL_SEED": "7",
    "EIDOS_MODEL_MAX_OUTPUT_TOKENS": "512",
    "EIDOS_MODEL_TIMEOUT_SECONDS": "60",
    "EIDOS_DATABASE_URL": "postgresql://user:" + SECRET_VALUE + "@db.example.test:5432/postgres",
    "EIDOS_JWT_SECRET": SECRET_VALUE,
}


def without(*names, **more):
    environ = {**GOOD, **more}
    for name in names:
        environ.pop(name, None)
    return environ


def refuses(environ) -> str:
    with pytest.raises(ConfigurationError) as raised:
        create_app_from_environment(environ)
    return str(raised.value)


@pytest.mark.parametrize(
    "name",
    ["EIDOS_MODEL_PROVIDER", "EIDOS_MODEL_BASE_URL", "EIDOS_MODEL_NAME", "EIDOS_MODEL_TEMPERATURE", "EIDOS_MODEL_SEED", "EIDOS_MODEL_MAX_OUTPUT_TOKENS", "EIDOS_MODEL_TIMEOUT_SECONDS"],
)
def test_the_model_and_its_generation_settings_are_required_and_have_no_default(name):
    message = refuses(without(name))
    assert name in message and SECRET_VALUE not in message


def test_a_missing_database_url_is_named_and_a_malformed_number_is_named_without_its_value():
    assert "EIDOS_DATABASE_URL" in refuses(without("EIDOS_DATABASE_URL"))
    message = refuses(without(EIDOS_MODEL_SEED=SECRET_VALUE))
    assert "EIDOS_MODEL_SEED" in message and SECRET_VALUE not in message


def test_a_blank_value_is_a_missing_one():
    assert "EIDOS_MODEL_NAME" in refuses(without(EIDOS_MODEL_NAME="   "))


def test_an_unknown_model_provider_is_refused():
    message = refuses(without(EIDOS_MODEL_PROVIDER="not-a-provider"))
    assert "not-a-provider" in message or "provider" in message


def test_the_groq_provider_requires_an_api_key_that_ollama_never_needed():
    # No GROQ_API_KEY at all: refused, naming the key, not the (absent) value.
    message = refuses(without(EIDOS_MODEL_PROVIDER="groq"))
    assert "api_key" in message.lower() or "groq_api_key" in message.lower()
    # Blank is the same as missing (the same rule every other required variable follows).
    message = refuses(without(EIDOS_MODEL_PROVIDER="groq", GROQ_API_KEY="   "))
    assert "api_key" in message.lower() or "groq_api_key" in message.lower()


def test_a_complete_groq_configuration_builds_the_app_and_never_echoes_the_key(monkeypatch):
    storage = InMemoryStorage()

    class Stand:
        def repositories(self):
            return storage.repositories()

        def close(self):
            pass

    monkeypatch.setattr(main.PostgresStorage, "open", classmethod(lambda cls, url, **kwargs: Stand()))
    from fastapi.testclient import TestClient

    groq = without(EIDOS_MODEL_PROVIDER="groq", EIDOS_MODEL_BASE_URL="https://api.groq.com/openai/v1", GROQ_API_KEY=SECRET_VALUE)
    app = create_app_from_environment(groq)
    with TestClient(app) as client:
        assert client.get("/v1/healthz").json() == {"status": "ok"}
    # A config error elsewhere, with the same real key present, must still never mention it.
    assert SECRET_VALUE not in refuses(without("EIDOS_MODEL_NAME", EIDOS_MODEL_PROVIDER="groq", GROQ_API_KEY=SECRET_VALUE))


def test_exactly_one_authentication_source_is_required():
    assert "exactly one" in refuses(without("EIDOS_JWT_SECRET"))
    assert "exactly one" in refuses(without(EIDOS_JWKS_URL="https://project.example.test/auth/v1/.well-known/jwks.json"))
    assert SECRET_VALUE not in refuses(without(EIDOS_JWKS_URL="https://project.example.test/auth/v1/.well-known/jwks.json"))


def test_a_jwks_endpoint_that_is_not_https_is_refused_naming_no_value():
    message = refuses(without("EIDOS_JWT_SECRET", EIDOS_JWKS_URL="http://project.example.test/keys"))
    assert "https" in message and "project.example.test" not in message


def test_the_verifier_is_asymmetric_for_a_jwks_url_and_hs256_for_a_secret_and_the_audience_defaults_to_supabases():
    jwks = build_verifier({"EIDOS_JWKS_URL": "https://project.example.test/auth/v1/.well-known/jwks.json"})
    assert jwks._algorithms == ("RS256", "ES256") and jwks._settings.audience == "authenticated"
    secret = build_verifier({"EIDOS_JWT_SECRET": SECRET_VALUE, "EIDOS_JWT_AUDIENCE": "custom", "EIDOS_JWT_ISSUER": "https://project.example.test/auth/v1"})
    assert secret._algorithms == ("HS256",) and secret._settings.audience == "custom" and secret._settings.issuer == "https://project.example.test/auth/v1"


def test_configuration_is_checked_before_the_database_is_opened(monkeypatch):
    opened = []
    monkeypatch.setattr(main.PostgresStorage, "open", classmethod(lambda cls, url, **kwargs: opened.append(url)))
    for bad in (without("EIDOS_MODEL_NAME"), without("EIDOS_JWT_SECRET"), without(EIDOS_MODEL_SEED="x")):
        refuses(bad)
    assert opened == []


def test_a_complete_configuration_builds_the_app_and_hands_the_storage_to_the_closers(monkeypatch):
    storage = InMemoryStorage()
    closed = []
    seen = {}

    class Stand:
        def repositories(self):
            return storage.repositories()

        def close(self):
            closed.append(True)

    def open_it(cls, url, **kwargs):
        seen["url"] = url
        return Stand()

    monkeypatch.setattr(main.PostgresStorage, "open", classmethod(open_it))
    from fastapi.testclient import TestClient

    app = create_app_from_environment(GOOD)
    assert seen["url"] == GOOD["EIDOS_DATABASE_URL"]
    with TestClient(app) as client:
        assert client.get("/v1/healthz").json() == {"status": "ok"}
    assert closed == [True]


def test_runner_bounds_come_from_the_environment_only_when_given(monkeypatch):
    captured = {}
    original = main.RunnerConfig

    def spy(**kwargs):
        captured.update(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(main.PostgresStorage, "open", classmethod(lambda cls, url, **kwargs: type("S", (), {"repositories": lambda self: InMemoryStorage().repositories(), "close": lambda self: None})()))
    monkeypatch.setattr(main, "RunnerConfig", spy)
    create_app_from_environment(GOOD)
    defaults = original()
    assert (captured["worker_pool_size"], captured["max_queued_runs"], captured["max_active_runs_per_tenant"]) == (defaults.worker_pool_size, defaults.max_queued_runs, defaults.max_active_runs_per_tenant)
    captured.clear()
    create_app_from_environment({**GOOD, "EIDOS_WORKER_POOL_SIZE": "5", "EIDOS_MAX_QUEUED_RUNS": "9", "EIDOS_MAX_ACTIVE_RUNS_PER_TENANT": "3"})
    assert (captured["worker_pool_size"], captured["max_queued_runs"], captured["max_active_runs_per_tenant"]) == (5, 9, 3)


@pytest.mark.parametrize(("value", "expected"), [(None, False), ("", False), ("false", False), ("0", False), ("true", True), (" TRUE ", True), ("1", True), ("yes", True)])
def test_automatic_workspaces_are_off_unless_the_environment_turns_them_on(monkeypatch, value, expected):
    seen = {}
    original = main.ServiceConfig

    def spy(**kwargs):
        config = original(**kwargs)
        seen["flag"] = config.auto_provision_workspaces
        return config

    monkeypatch.setattr(main.PostgresStorage, "open", classmethod(lambda cls, url, **kwargs: type("S", (), {"repositories": lambda self: InMemoryStorage().repositories(), "close": lambda self: None})()))
    monkeypatch.setattr(main, "ServiceConfig", spy)
    environment = dict(GOOD) if value is None else {**GOOD, "EIDOS_AUTO_PROVISION_WORKSPACES": value}
    create_app_from_environment(environment)
    assert seen["flag"] is expected


@pytest.mark.parametrize(
    ("actions", "wired"),
    [(None, False), ("", False), ("read_documents", False), ("web_fetch", True), ("read_documents, web_fetch", True), ("WEB_FETCH", False), ("web_fetch_all", False)],
)
def test_the_web_fetch_tool_is_wired_only_where_the_deployer_listed_its_action(monkeypatch, actions, wired):
    seen = {}
    original = main.Composition

    def spy(**kwargs):
        seen["tools"] = kwargs.get("tools")
        return original(**kwargs)

    monkeypatch.setattr(main.PostgresStorage, "open", classmethod(lambda cls, url, **kwargs: type("S", (), {"repositories": lambda self: InMemoryStorage().repositories(), "close": lambda self: None})()))
    monkeypatch.setattr(main, "Composition", spy)
    environment = dict(GOOD) if actions is None else {**GOOD, "EIDOS_ALLOWED_ACTIONS": actions}
    create_app_from_environment(environment)
    if wired:
        assert seen["tools"] is not None and seen["tools"].tool_id == "web/fetch"
        assert seen["tools"].registry.resolve("web/fetch") is not None and len(seen["tools"].registry.tools) == 1
    else:
        assert seen["tools"] is None


def test_the_module_reads_the_environment_only_through_its_argument_and_logs_and_prints_nothing():
    import ast
    import inspect

    source = inspect.getsource(main)
    tree = ast.parse(source)
    calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert not calls & {"print", "eval", "exec", "open"}
    assert "logging" not in source and "getLogger" not in source


def test_a_shared_secret_shorter_than_an_hs256_key_may_be_is_refused_at_startup_naming_the_variable_and_not_the_value():
    weak = "short-secret"
    message = refuses(without(EIDOS_JWT_SECRET=weak))
    assert "EIDOS_JWT_SECRET" in message and "32 bytes" in message and weak not in message
    assert build_verifier({"EIDOS_JWT_SECRET": "x" * 32})._algorithms == ("HS256",)  # exactly the least is enough
    with pytest.raises(ConfigurationError):
        build_verifier({"EIDOS_JWT_SECRET": "x" * 31})
