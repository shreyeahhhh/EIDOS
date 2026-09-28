"""The composition root: the one place the service is wired to PostgreSQL, a model provider and the JWT key material, from the environment (decisions.md D-233, D-234; ``docs/13`` section 9).

    uvicorn eidos.api.main:create_app_from_environment --factory

**Nothing here has a hidden default that matters.** The model, its generation parameters and its timeout are required (D-135); so are the database and the endpoint of the model provider. The
provisional ceilings, the provisional ``SystemLimits`` and the runner bounds come from ``eidos.service`` and are labelled provisional there. A missing or malformed variable stops the process
before it serves anything and names the *variable*, never a value: no connection string, secret or token is ever logged or echoed.

Authentication is one of two mutually exclusive settings: ``EIDOS_JWKS_URL`` (Supabase's asymmetric signing keys, the default choice) or ``EIDOS_JWT_SECRET`` (the legacy shared HS256 secret).
Knowledge is not configured here: it is optional and no production knowledge base is chosen in V1.4 (D-234, D-227).

``EIDOS_MODEL_PROVIDER`` is ``ollama`` (a local development runtime) or ``groq`` (a hosted, OpenAI-compatible
provider — V1.6). ``GROQ_API_KEY`` is read here and only here; it is required, and startup fails, if and
only if the provider is ``groq`` — ``ollama`` needs no key and this variable is simply ignored for it.
"""

import os
from collections.abc import Mapping

from fastapi import FastAPI

from eidos.agents import GenerationParameters, ModelSettings
from eidos.persistence import PostgresStorage
from eidos.providers import model_port
from eidos.service import Composition, MissionService, RunManager, RunnerConfig, ServiceConfig, provisional_system_limits

from .app import create_app
from .auth import ASYMMETRIC_ALGORITHMS, SYMMETRIC_ALGORITHMS, JwksKeys, JwtSettings, JwtVerifier, StaticKey


class ConfigurationError(ValueError):
    """A setting is missing or malformed. The message names the variable and never its value."""


def _required(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name, "").strip()
    if not value:
        raise ConfigurationError(f"{name} is required")
    return value


def _number(environ: Mapping[str, str], name: str, kind: type, *, required: bool = True, default=None):
    raw = environ.get(name, "").strip()
    if not raw:
        if required:
            raise ConfigurationError(f"{name} is required")
        return default
    try:
        return kind(raw)
    except ValueError:
        raise ConfigurationError(f"{name} is not a valid {kind.__name__}") from None


def build_verifier(environ: Mapping[str, str]) -> JwtVerifier:
    jwks_url, secret = environ.get("EIDOS_JWKS_URL", "").strip(), environ.get("EIDOS_JWT_SECRET", "")
    if bool(jwks_url) == bool(secret):
        raise ConfigurationError("exactly one of EIDOS_JWKS_URL and EIDOS_JWT_SECRET is required")
    audience = environ.get("EIDOS_JWT_AUDIENCE", "").strip() or "authenticated"  # Supabase's audience for a signed-in user
    issuer = environ.get("EIDOS_JWT_ISSUER", "").strip() or None
    if secret and len(secret.encode("utf-8")) < 32:
        raise ConfigurationError("EIDOS_JWT_SECRET is shorter than 32 bytes, the least an HS256 key may be (RFC 7518 section 3.2)")  # a weak shared secret is forgeable: refuse it at startup
    try:
        if jwks_url:
            return JwtVerifier(keys=JwksKeys(jwks_url), settings=JwtSettings(audience=audience, algorithms=ASYMMETRIC_ALGORITHMS, issuer=issuer))
        return JwtVerifier(keys=StaticKey(secret), settings=JwtSettings(audience=audience, algorithms=SYMMETRIC_ALGORITHMS, issuer=issuer))
    except ValueError as error:
        raise ConfigurationError(str(error)) from None


def create_app_from_environment(environ: Mapping[str, str] | None = None) -> FastAPI:
    environ = os.environ if environ is None else environ
    model_settings = ModelSettings(
        model=_required(environ, "EIDOS_MODEL_NAME"),
        parameters=GenerationParameters(
            temperature=_number(environ, "EIDOS_MODEL_TEMPERATURE", float), seed=_number(environ, "EIDOS_MODEL_SEED", int),
            max_output_tokens=_number(environ, "EIDOS_MODEL_MAX_OUTPUT_TOKENS", int),
        ),
        timeout_seconds=_number(environ, "EIDOS_MODEL_TIMEOUT_SECONDS", float),
    )
    try:
        model = model_port(
            _required(environ, "EIDOS_MODEL_PROVIDER"),
            base_url=_required(environ, "EIDOS_MODEL_BASE_URL"),
            # Only the 'groq' provider needs this (D-234, V1.6); 'ollama' ignores it, exactly as before.
            api_key=environ.get("GROQ_API_KEY", "").strip() or None,
        )
    except ValueError as error:
        raise ConfigurationError(str(error)) from None
    defaults = RunnerConfig()
    runner_config = RunnerConfig(
        worker_pool_size=_number(environ, "EIDOS_WORKER_POOL_SIZE", int, required=False, default=defaults.worker_pool_size),
        max_queued_runs=_number(environ, "EIDOS_MAX_QUEUED_RUNS", int, required=False, default=defaults.max_queued_runs),
        max_active_runs_per_tenant=_number(environ, "EIDOS_MAX_ACTIVE_RUNS_PER_TENANT", int, required=False, default=defaults.max_active_runs_per_tenant),
    )
    config = ServiceConfig(
        limits=provisional_system_limits(), model_settings=model_settings, runner=runner_config,
        allowed_actions=frozenset(item.strip() for item in environ.get("EIDOS_ALLOWED_ACTIONS", "").split(",") if item.strip()),
    )
    verifier = build_verifier(environ)
    storage = PostgresStorage.open(_required(environ, "EIDOS_DATABASE_URL"))
    repositories = storage.repositories()
    composition = Composition(config=config, model=model, events=repositories.events)
    runner = RunManager(repositories=repositories, composition=composition, config=config.runner)
    service = MissionService(repositories=repositories, runner=runner, composition=composition, config=config)
    return create_app(service=service, verifier=verifier, max_body_bytes=config.ceilings.max_request_body_bytes, closers=(storage.close,))
