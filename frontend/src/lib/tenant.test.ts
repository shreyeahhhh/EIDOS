import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getStoredTenantId, setStoredTenantId } from "./tenant";

const ALICE = "aaaaaaaa-0000-0000-0000-000000000001";
const BOB = "bbbbbbbb-0000-0000-0000-000000000002";
const WORKSPACE_A = "11111111-1111-1111-1111-111111111111";
const WORKSPACE_B = "22222222-2222-2222-2222-222222222222";

describe("tenant id remembered per account in this browser", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("is absent until the person enters one", () => {
    expect(getStoredTenantId(ALICE)).toBeNull();
  });

  it("remembers exactly what was entered", () => {
    setStoredTenantId(ALICE, WORKSPACE_A);
    expect(getStoredTenantId(ALICE)).toBe(WORKSPACE_A);
  });

  it("is never another account's: each account on the browser has its own, and keeps it", () => {
    setStoredTenantId(ALICE, WORKSPACE_A);
    expect(getStoredTenantId(BOB)).toBeNull();

    setStoredTenantId(BOB, WORKSPACE_B);
    expect(getStoredTenantId(BOB)).toBe(WORKSPACE_B);
    expect(getStoredTenantId(ALICE)).toBe(WORKSPACE_A);
  });

  it("never uses the one id kept for every account before D-249, and removes it", () => {
    window.localStorage.setItem("eidos.tenantId", WORKSPACE_A);
    expect(getStoredTenantId(BOB)).toBeNull();
    expect(window.localStorage.getItem("eidos.tenantId")).toBeNull();
  });

  it("reads as absent, and storing does not throw, when storage is unavailable", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    expect(getStoredTenantId(ALICE)).toBeNull();
    expect(() => setStoredTenantId(ALICE, WORKSPACE_A)).not.toThrow();
  });
});
