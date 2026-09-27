import type { ApiErrorBody, ApiErrorCode, ApiErrorEnvelope } from "./types";

function isApiErrorEnvelope(value: unknown): value is ApiErrorEnvelope {
  return (
    typeof value === "object" &&
    value !== null &&
    "error" in value &&
    typeof (value as { error?: unknown }).error === "object"
  );
}

/**
 * The backend's one error shape, thrown as a real `Error`. `code` is the thing to switch on in the
 * UI (`docs/13_product_backend.md` section 8) — `message`/`status` are for logging and for the
 * generic fallback, never for building UI copy that should instead read `code`.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: ApiErrorCode;
  readonly details: ApiErrorBody["details"];

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.details = body.details;
  }
}

/** Parses a `Response` that was not `ok` into an `ApiError`. Never throws itself: an unparseable body becomes a generic `internal_error`. */
export async function toApiError(response: Response): Promise<ApiError> {
  try {
    const parsed: unknown = await response.json();
    if (isApiErrorEnvelope(parsed)) {
      return new ApiError(response.status, parsed.error);
    }
  } catch {
    // fall through
  }
  return new ApiError(response.status, {
    code: "internal_error",
    message: "The service gave an answer this app could not read.",
  });
}
