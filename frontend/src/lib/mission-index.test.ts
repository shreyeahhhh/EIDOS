import { beforeEach, describe, expect, it } from "vitest";

import { forgetMission, listIndexedMissions, rememberMission } from "./mission-index";

describe("mission index (the dashboard's local navigation aid, never a source of truth)", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("is empty until a mission is remembered", () => {
    expect(listIndexedMissions()).toEqual([]);
  });

  it("lists remembered missions most-recently-created first", () => {
    rememberMission({ id: "a", goal: "first", createdAt: "2026-01-01T00:00:00Z" });
    rememberMission({ id: "b", goal: "second", createdAt: "2026-01-02T00:00:00Z" });
    expect(listIndexedMissions().map((m) => m.id)).toEqual(["b", "a"]);
  });

  it("does not duplicate an id remembered twice", () => {
    rememberMission({ id: "a", goal: "first", createdAt: "2026-01-01T00:00:00Z" });
    rememberMission({ id: "a", goal: "first (again)", createdAt: "2026-01-01T00:00:00Z" });
    expect(listIndexedMissions()).toHaveLength(1);
  });

  it("forgets an id the backend no longer has, and only that one", () => {
    rememberMission({ id: "a", goal: "keep", createdAt: "2026-01-01T00:00:00Z" });
    rememberMission({ id: "b", goal: "stale", createdAt: "2026-01-02T00:00:00Z" });
    forgetMission("b");
    expect(listIndexedMissions().map((m) => m.id)).toEqual(["a"]);
  });

  it("tolerates corrupted storage instead of throwing", () => {
    window.localStorage.setItem("eidos.missionIndex", "not json");
    expect(listIndexedMissions()).toEqual([]);
  });
});
