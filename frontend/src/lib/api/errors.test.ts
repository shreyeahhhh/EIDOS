import { describe, expect, it } from "vitest";

import { ApiError, toApiError } from "./errors";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

describe("ApiError / toApiError", () => {
  it("parses the backend's one error shape into a typed ApiError", async () => {
    const response = jsonResponse(422, { error: { code: "invalid_spec", message: "not acceptable", details: [{ field: "goal", message: "too short" }] } });
    const error = await toApiError(response);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(422);
    expect(error.code).toBe("invalid_spec");
    expect(error.details).toEqual([{ field: "goal", message: "too short" }]);
  });

  it("falls back to internal_error for a body that is not the expected envelope, without throwing", async () => {
    const error = await toApiError(jsonResponse(500, { detail: "Internal Server Error" }));
    expect(error.code).toBe("internal_error");
    expect(error.status).toBe(500);
  });

  it("falls back to internal_error for a body that is not even JSON", async () => {
    const response = new Response("not json", { status: 502 });
    const error = await toApiError(response);
    expect(error.code).toBe("internal_error");
    expect(error.status).toBe(502);
  });
});
