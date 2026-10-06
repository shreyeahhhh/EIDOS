import { beforeEach, describe, expect, it } from "vitest";

import { forgetMission, listIndexedMissions, rememberMission } from "./mission-index";

const ALICE = "aaaaaaaa-0000-0000-0000-000000000001";
const BOB = "bbbbbbbb-0000-0000-0000-000000000002";

describe("mission index (the dashboard's local navigation aid, never a source of truth)", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("is empty until a mission is remembered", () => {
    expect(listIndexedMissions(ALICE)).toEqual([]);
  });

  it("lists remembered missions most-recently-created first", () => {
    rememberMission(ALICE, { id: "a", goal: "first", createdAt: "2026-01-01T00:00:00Z" });
    rememberMission(ALICE, { id: "b", goal: "second", createdAt: "2026-01-02T00:00:00Z" });
    expect(listIndexedMissions(ALICE).map((m) => m.id)).toEqual(["b", "a"]);
  });

  it("does not duplicate an id remembered twice", () => {
    rememberMission(ALICE, { id: "a", goal: "first", createdAt: "2026-01-01T00:00:00Z" });
    rememberMission(ALICE, { id: "a", goal: "first (again)", createdAt: "2026-01-01T00:00:00Z" });
    expect(listIndexedMissions(ALICE)).toHaveLength(1);
  });

  it("forgets an id the backend no longer has, and only that one", () => {
    rememberMission(ALICE, { id: "a", goal: "keep", createdAt: "2026-01-01T00:00:00Z" });
    rememberMission(ALICE, { id: "b", goal: "stale", createdAt: "2026-01-02T00:00:00Z" });
    forgetMission(ALICE, "b");
    expect(listIndexedMissions(ALICE).map((m) => m.id)).toEqual(["a"]);
  });

  it("tolerates corrupted storage instead of throwing", () => {
    window.localStorage.setItem(`eidos.missionIndex:${ALICE}`, "not json");
    expect(listIndexedMissions(ALICE)).toEqual([]);
  });

  it("keeps each account's missions apart: another account neither lists them nor can prune them", () => {
    rememberMission(ALICE, { id: "alice-1", goal: "hers", createdAt: "2026-01-01T00:00:00Z" });
    rememberMission(BOB, { id: "bob-1", goal: "his", createdAt: "2026-01-02T00:00:00Z" });

    expect(listIndexedMissions(BOB).map((m) => m.id)).toEqual(["bob-1"]);
    forgetMission(BOB, "alice-1");
    expect(listIndexedMissions(ALICE).map((m) => m.id)).toEqual(["alice-1"]);
  });

  it("hands the index kept for every account before D-249 to the first account that reads its own, once", () => {
    window.localStorage.setItem("eidos.missionIndex", JSON.stringify([{ id: "old", goal: "from before", createdAt: "2026-01-01T00:00:00Z" }]));

    expect(listIndexedMissions(ALICE).map((m) => m.id)).toEqual(["old"]);
    expect(window.localStorage.getItem("eidos.missionIndex")).toBeNull();
    expect(listIndexedMissions(BOB)).toEqual([]);
  });

  it("does not let the old shared index overwrite an account's own", () => {
    rememberMission(ALICE, { id: "mine", goal: "kept", createdAt: "2026-01-02T00:00:00Z" });
    window.localStorage.setItem("eidos.missionIndex", JSON.stringify([{ id: "old", goal: "from before", createdAt: "2026-01-01T00:00:00Z" }]));

    expect(listIndexedMissions(ALICE).map((m) => m.id)).toEqual(["mine"]);
    expect(window.localStorage.getItem("eidos.missionIndex")).toBeNull();
  });
});
