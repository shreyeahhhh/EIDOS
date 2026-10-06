import { afterEach, describe, expect, it, vi } from "vitest";

import { startMission } from "./client";

const ID = "11111111-1111-1111-1111-111111111111";
const KEY = "sk-test-0123456789ABCDEF";

function stubFetch() {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ mission_id: ID, run_status: "queued" }), { status: 202, headers: { "content-type": "application/json" } }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe("startMission", () => {
  it("sends no body at all when the run is on the service's own model, as it always did", async () => {
    const fetchMock = stubFetch();
    await startMission(ID);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`/api/eidos/missions/${ID}/start`);
    expect(init.method).toBe("POST");
    expect(init.body).toBeUndefined();
  });

  it("sends the user's own model and key in the request body only — never in the address or a header", async () => {
    const fetchMock = stubFetch();
    await startMission(ID, { model: { provider: "openai", model: "gpt-4o-mini", api_key: KEY } });
    const [url, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init.body)).toEqual({ model: { provider: "openai", model: "gpt-4o-mini", api_key: KEY } });
    expect(url).not.toContain(KEY);
    expect(JSON.stringify([...new Headers(init.headers).entries()])).not.toContain(KEY);
    expect(new Headers(init.headers).get("content-type")).toBe("application/json");
  });

  it("still carries the workspace id for a start that names a model", async () => {
    const fetchMock = stubFetch();
    await startMission(ID, { tenantId: "tenant-1", model: { provider: "groq", model: "m", api_key: KEY } });
    expect(new Headers(fetchMock.mock.calls[0][1].headers).get("x-tenant-id")).toBe("tenant-1");
    expect(fetchMock.mock.calls[0][1].body).not.toContain("tenant-1"); // the option is a header, not part of the model body
  });
});
