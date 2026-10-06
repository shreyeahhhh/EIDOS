import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const getMission = vi.fn();
const router = { push: vi.fn() }; // one object, as Next's own router is: the dashboard's effect depends on it

vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/lib/api/client", () => ({ getMission: (id: string, options: unknown) => getMission(id, options) }));

import { ApiError } from "@/lib/api/errors";
import type { MissionSummary } from "@/lib/api/types";
import { listIndexedMissions, rememberMission } from "@/lib/mission-index";
import { SignedInUserProvider } from "@/lib/signed-in-user";
import { MissionDashboard } from "./mission-dashboard";

const ALICE = "aaaaaaaa-0000-0000-0000-000000000001";
const BOB = "bbbbbbbb-0000-0000-0000-000000000002";

function summary(id: string, goal: string): MissionSummary {
  return {
    mission_id: id,
    tenant_id: "22222222-2222-2222-2222-222222222222",
    created_by: BOB,
    created_at: "2026-10-06T10:00:00Z",
    goal,
    run_status: "created",
    run_status_reason: null,
    mission_status: null,
    status_reason: null,
    failure_cause: null,
    verified: null,
    plan_version: null,
    counters: null,
    last_sequence: 0,
  };
}

function renderFor(userId: string) {
  return render(
    <SignedInUserProvider userId={userId}>
      <MissionDashboard />
    </SignedInUserProvider>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  getMission.mockReset();
});

describe("MissionDashboard on a browser two accounts have used (D-249)", () => {
  it("lists only the signed-in account's missions and leaves another account's list untouched", async () => {
    rememberMission(ALICE, { id: "alice-1", goal: "Alice's mission", createdAt: "2026-10-05T10:00:00Z" });
    rememberMission(BOB, { id: "bob-1", goal: "Bob's mission", createdAt: "2026-10-06T10:00:00Z" });
    getMission.mockImplementation((id: string) =>
      id === "bob-1" ? Promise.resolve(summary("bob-1", "Bob's mission")) : Promise.reject(new ApiError(404, { code: "not_found", message: "no such mission" })),
    );

    renderFor(BOB);

    expect(await screen.findByText("Bob's mission")).toBeInTheDocument();
    expect(getMission).toHaveBeenCalledTimes(1);
    expect(getMission).toHaveBeenCalledWith("bob-1", { userId: BOB });
    expect(listIndexedMissions(ALICE).map((m) => m.id)).toEqual(["alice-1"]);
  });

  it("prunes a mission the backend no longer has from the signed-in account's own list only", async () => {
    rememberMission(ALICE, { id: "shared-id", goal: "Alice's copy", createdAt: "2026-10-05T10:00:00Z" });
    rememberMission(BOB, { id: "shared-id", goal: "Bob's copy", createdAt: "2026-10-06T10:00:00Z" });
    getMission.mockRejectedValue(new ApiError(404, { code: "not_found", message: "no such mission" }));

    renderFor(BOB);

    expect(await screen.findByText("No missions yet")).toBeInTheDocument();
    await waitFor(() => expect(listIndexedMissions(BOB)).toEqual([]));
    expect(listIndexedMissions(ALICE).map((m) => m.id)).toEqual(["shared-id"]);
  });
});
