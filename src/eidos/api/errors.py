"""How the API answers a failure of the request or of the service (decisions.md D-234; ``docs/13`` section 8).

**An API failure and a mission failure never share a channel.** A mission that failed or paused is a normal ``200`` whose body describes it; an error here is about the *call*, and is never an
event and never a mission outcome. Every error has one shape, ``{"error": {"code": ..., "message": ..., "details": [...]}}`` (``details`` only for an invalid specification), and the message
of an unexpected fault is generic: nothing about the service's insides is told to a caller.
"""

from fastapi.responses import JSONResponse

STATUS_OF = {
    "unauthenticated": 401,
    "no_tenant_membership": 403,
    "not_found": 404,
    "method_not_allowed": 405,
    "tenant_required": 422,
    "invalid_spec": 422,
    "invalid_request": 422,
    "payload_too_large": 413,
    "not_startable": 409,
    "no_events": 409,
    "not_finished": 409,
    "tenant_run_limit": 409,
    "idempotency_conflict": 409,
    "busy": 503,
    "storage_unavailable": 503,
    "auth_unavailable": 503,
    "integrity_error": 500,
    "internal_error": 500,
}


# A fault of the service is told by a fixed sentence and never by the message it was raised with, which may name a host, a path or a value.
FAULT_MESSAGES = {
    "storage_unavailable": "the service could not reach its storage right now",
    "integrity_error": "the stored record of this mission could not be read",
    "auth_unavailable": "the token could not be checked right now",
    "internal_error": "the service failed to answer this request",
}


def error_response(code: str, message: str, details=(), *, headers: dict | None = None) -> JSONResponse:
    body: dict = {"code": code, "message": FAULT_MESSAGES.get(code, message)}
    if details:
        body["details"] = list(details)
    extra = {"WWW-Authenticate": "Bearer"} if code == "unauthenticated" else {}
    extra.update(headers or {})
    return JSONResponse({"error": body}, status_code=STATUS_OF[code], headers=extra or None)
