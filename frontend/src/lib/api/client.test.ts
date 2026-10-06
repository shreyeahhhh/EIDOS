import { afterEach, describe, expect, it, vi } from "vitest";

import { setStoredTenantId } from "../tenant";
import { getMission } from "./client";

const USER = { userId: "aaaaaaaa-0000-0000-0000-000000000001" };
const OTHER_USER = { userId: "bbbbbbbb-0000-0000-0000-000000000002" };

/**
 * `request()` (the one function every call in this client funnels through) wraps `fetch` itself in
 * a try/catch — added in V1.5-C after a live QA pass found that a stalled or unreachable connection
 * surfaced as a raw, unhandled `TypeError`/`DOMException` instead of a message a person could read.
 * These exercise that wrapping directly, without waiting out the real timeout.
 */
describe("request() network-failure handling", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("turns a fetch rejection into a plain, readable error rather than a raw TypeError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
    );
    await expect(getMission("11111111-1111-1111-1111-111111111111", USER)).rejects.toThrow(
      /could not reach the server/i,
    );
  });

  it("gives a distinct, readable message when the request is aborted by the timeout", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new DOMException("The operation timed out.", "TimeoutError")),
    );
    await expect(getMission("11111111-1111-1111-1111-111111111111", USER)).rejects.toThrow(/took too long/i);
  });

  it("still resolves normally when the real request succeeds", async () => {
    const body = { mission_id: "1", tenant_id: "t", created_by: "u", created_at: "now", goal: "g", run_status: "created", run_status_reason: null, mission_status: null, status_reason: null, failure_cause: null, verified: null, plan_version: null, counters: null, last_sequence: 0 };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } })),
    );
    await expect(getMission("11111111-1111-1111-1111-111111111111", USER)).resolves.toEqual(body);
  });
});

describe("the workspace id a request carries (D-249)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  function stubFetch() {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response("{}", { status: 200, headers: { "content-type": "application/json" } })));
    vi.stubGlobal("fetch", fetchMock);
    return (call: number) => new Headers(fetchMock.mock.calls[call][1].headers).get("x-tenant-id");
  }

  it("is the one remembered for the signed-in account, never one another account on the browser remembered", async () => {
    const tenantHeader = stubFetch();
    setStoredTenantId(OTHER_USER.userId, "22222222-2222-2222-2222-222222222222");

    await getMission("11111111-1111-1111-1111-111111111111", USER);
    expect(tenantHeader(0)).toBeNull();

    setStoredTenantId(USER.userId, "33333333-3333-3333-3333-333333333333");
    await getMission("11111111-1111-1111-1111-111111111111", USER);
    expect(tenantHeader(1)).toBe("33333333-3333-3333-3333-333333333333");
  });

  it("is not the one id kept for every account before D-249", async () => {
    const tenantHeader = stubFetch();
    window.localStorage.setItem("eidos.tenantId", "22222222-2222-2222-2222-222222222222");
    await getMission("11111111-1111-1111-1111-111111111111", USER);
    expect(tenantHeader(0)).toBeNull();
  });
});
