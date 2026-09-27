"""The service's typed errors (decisions.md D-234; ``docs/13`` sections 7 and 8).

An error here is a failure of a *request* or of the *service*: it is never an event and never a mission outcome. A mission that failed or paused is a normal answer that
describes it; nothing in this module models one. Each error carries a stable ``code`` (what the API puts in its error body) and a message written for a person. The API
maps a code to an HTTP status; this module knows no HTTP.
"""


class ServiceError(Exception):
    """Base of every error the service raises on purpose."""

    code = "internal_error"

    def __init__(self, message: str, *, details: tuple[dict, ...] = ()) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFound(ServiceError):
    """The resource does not exist for this tenant. A resource of another tenant is indistinguishable from one that does not exist (D-233)."""

    code = "not_found"


class NoTenantMembership(ServiceError):
    code = "no_tenant_membership"


class TenantRequired(ServiceError):
    """The user belongs to several tenants and named none."""

    code = "tenant_required"


class InvalidSpec(ServiceError):
    """A mission specification that is malformed or over a server ceiling. ``details`` names each field and why."""

    code = "invalid_spec"


class InvalidRequest(ServiceError):
    """A request that is well-formed as a mission but wrong as a call: a bad query parameter, a bad header."""

    code = "invalid_request"


class PayloadTooLarge(ServiceError):
    code = "payload_too_large"


class NotStartable(ServiceError):
    """``start`` was asked of a mission whose ``run_status`` is not ``created``."""

    code = "not_startable"


class NoEvents(ServiceError):
    """The mission has no recorded event yet, so it has no execution and no evidence to show."""

    code = "no_events"


class NotFinished(ServiceError):
    """The mission has no terminal event yet, so it has no result."""

    code = "not_finished"


class TenantRunLimit(ServiceError):
    code = "tenant_run_limit"


class IdempotencyConflict(ServiceError):
    code = "idempotency_conflict"


class Busy(ServiceError):
    """The bounded runner cannot take another run now."""

    code = "busy"


class StorageUnavailable(ServiceError):
    """The durable store could not be reached or did not answer in time."""

    code = "storage_unavailable"


class IntegrityFailure(ServiceError):
    """What is stored does not replay. This is a fault of the store, never a mission outcome."""

    code = "integrity_error"
