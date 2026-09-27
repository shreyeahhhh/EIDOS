"""The FastAPI application: the HTTP boundary of the product backend (decisions.md D-233, D-234; ``docs/13`` sections 5, 7 and 8).

The whole surface, and nothing else (list, cancel, replay and strategy-view endpoints are deferred):

    POST /v1/missions                   create (no event is written)         GET /v1/missions/{id}/execution   the existing ExecutionRecord
    POST /v1/missions/{id}/start        queue one run                        GET /v1/missions/{id}/events      the recorded events, paged by sequence
    GET  /v1/missions/{id}              run_status and, once events exist,   GET /v1/missions/{id}/result      the verdict, the sink artifacts, the failure
                                        what the folded log says             GET /v1/missions/{id}/evidence    the evidence audit and the cited evidence text
    GET  /v1/healthz                    liveness, unauthenticated

**FastAPI never mutates ``MissionState``.** A route authenticates, resolves the tenant, and calls ``MissionService``; this module imports nothing of the runtime, the log or the reducer, and
returns the service's own response models as JSON. Handlers are plain ``def``: the runtime is synchronous, so FastAPI runs them in its thread pool. The one ``async`` piece reads the request
body under a hard size limit before anything parses it. A request body is parsed with ``MissionSpec.model_validate_json``, because the EIDOS contracts are strict and only the JSON form
of a strict model accepts JSON's own types.
"""

from collections.abc import Callable, Sequence
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from eidos.contracts import MissionId
from eidos.service import InvalidSpec, MissionService, MissionSpec, NotFound, PayloadTooLarge, RequestContext, ServiceError

from .auth import AuthUnavailable, JwtVerifier, Unauthenticated
from .errors import error_response


def _json(model, status: int = 200) -> Response:
    return Response(content=model.model_dump_json(), media_type="application/json", status_code=status)


def _mission_id(value: str) -> MissionId:
    try:
        return MissionId(UUID(value))
    except ValueError:
        raise NotFound("no such mission") from None


def _details(error) -> tuple[dict, ...]:
    return tuple({"field": ".".join(str(part) for part in item["loc"]), "message": item["msg"]} for item in error.errors())


def create_app(*, service: MissionService, verifier: JwtVerifier, max_body_bytes: int, closers: Sequence[Callable[[], None]] = ()) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        service.startup()  # a previous process's active runs become `interrupted` before a request is served; no event is written
        try:
            yield
        finally:
            service.shutdown()
            for close in closers:
                close()

    app = FastAPI(title="EIDOS", version="1", docs_url=None, redoc_url=None, openapi_url="/v1/openapi.json", lifespan=lifespan)

    # --- errors ------------------------------------------------------------------------------------------------------------------

    @app.exception_handler(ServiceError)
    async def _service_error(request: Request, error: ServiceError) -> JSONResponse:
        return error_response(error.code, error.message, error.details)

    @app.exception_handler(Unauthenticated)
    async def _unauthenticated(request: Request, error: Unauthenticated) -> JSONResponse:
        return error_response("unauthenticated", "authentication is required, and the token must be acceptable")

    @app.exception_handler(AuthUnavailable)
    async def _auth_unavailable(request: Request, error: AuthUnavailable) -> JSONResponse:
        return error_response("auth_unavailable", "the token could not be checked right now")

    @app.exception_handler(RequestValidationError)
    async def _bad_request(request: Request, error: RequestValidationError) -> JSONResponse:
        return error_response("invalid_request", "the request is not valid", _details(error))

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, error: Exception) -> JSONResponse:
        return error_response("internal_error", "the service failed to answer this request")

    # --- dependencies ------------------------------------------------------------------------------------------------------------

    def bearer(authorization: str | None = Header(default=None)) -> str:
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise Unauthenticated("no bearer token")
        return token.strip()

    def context(token: str = Depends(bearer), x_tenant_id: str | None = Header(default=None)) -> RequestContext:
        return service.resolve_context(verifier.verify(token), x_tenant_id)

    async def raw_body(request: Request) -> bytes:
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > max_body_bytes:
            raise PayloadTooLarge(f"the request body is over {max_body_bytes} bytes")
        chunks, total = [], 0
        async for chunk in request.stream():
            total += len(chunk)
            if total > max_body_bytes:
                raise PayloadTooLarge(f"the request body is over {max_body_bytes} bytes")
            chunks.append(chunk)
        return b"".join(chunks)

    # --- routes ------------------------------------------------------------------------------------------------------------------

    @app.get("/v1/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.post("/v1/missions")
    def create_mission(ctx: RequestContext = Depends(context), body: bytes = Depends(raw_body), idempotency_key: str | None = Header(default=None)) -> Response:
        try:
            spec = MissionSpec.model_validate_json(body)
        except ValidationError as error:
            raise InvalidSpec("the mission specification is not acceptable", details=_details(error)) from error
        created, is_new = service.create_mission(ctx, spec, idempotency_key)
        return _json(created, 201 if is_new else 200)

    @app.post("/v1/missions/{mission_id}/start")
    def start_mission(mission_id: str, ctx: RequestContext = Depends(context)) -> Response:
        return _json(service.start_mission(ctx, _mission_id(mission_id)), 202)

    @app.get("/v1/missions/{mission_id}")
    def get_mission(mission_id: str, ctx: RequestContext = Depends(context)) -> Response:
        return _json(service.get_mission(ctx, _mission_id(mission_id)))

    @app.get("/v1/missions/{mission_id}/execution")
    def get_execution(mission_id: str, ctx: RequestContext = Depends(context)) -> Response:
        return _json(service.execution(ctx, _mission_id(mission_id)))

    @app.get("/v1/missions/{mission_id}/events")
    def get_events(mission_id: str, after: int = 0, limit: int | None = None, ctx: RequestContext = Depends(context)) -> Response:
        return _json(service.events(ctx, _mission_id(mission_id), after=after, limit=limit))

    @app.get("/v1/missions/{mission_id}/result")
    def get_result(mission_id: str, ctx: RequestContext = Depends(context)) -> Response:
        return _json(service.result(ctx, _mission_id(mission_id)))

    @app.get("/v1/missions/{mission_id}/evidence")
    def get_evidence(mission_id: str, ctx: RequestContext = Depends(context)) -> Response:
        return _json(service.evidence(ctx, _mission_id(mission_id)))

    return app
