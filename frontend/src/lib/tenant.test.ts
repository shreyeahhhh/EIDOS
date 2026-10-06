import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearStoredTenantId, getStoredTenantId, setStoredTenantId } from "./tenant";

describe("tenant id remembered per browser", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("is absent until the person enters one", () => {
    expect(getStoredTenantId()).toBeNull();
  });

  it("remembers exactly what was entered, and clearing removes it", () => {
    setStoredTenantId("11111111-1111-1111-1111-111111111111");
    expect(getStoredTenantId()).toBe("11111111-1111-1111-1111-111111111111");
    clearStoredTenantId();
    expect(getStoredTenantId()).toBeNull();
  });

  it("clearing leaves the browser's other remembered things alone", () => {
    window.localStorage.setItem("eidos.missionIndex", "[]");
    setStoredTenantId("11111111-1111-1111-1111-111111111111");
    clearStoredTenantId();
    expect(window.localStorage.getItem("eidos.missionIndex")).toBe("[]");
  });

  it("clearing does not throw when storage is unavailable", () => {
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    expect(() => clearStoredTenantId()).not.toThrow();
  });
});
