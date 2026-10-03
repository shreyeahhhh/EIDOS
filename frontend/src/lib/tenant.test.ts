import { beforeEach, describe, expect, it } from "vitest";

import { getStoredTenantId, setStoredTenantId } from "./tenant";

describe("tenant id remembered per browser", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("is absent until the person enters one", () => {
    expect(getStoredTenantId()).toBeNull();
  });

  it("remembers exactly what was entered", () => {
    setStoredTenantId("11111111-1111-1111-1111-111111111111");
    expect(getStoredTenantId()).toBe("11111111-1111-1111-1111-111111111111");
  });
});
