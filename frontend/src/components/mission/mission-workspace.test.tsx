import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/errors";
import type { MissionSummary } from "@/lib/api/types";

const getMission = vi.fn();
const getExecution = vi.fn();
const getEvents = vi.fn();
const getResult = vi.fn();
const getEvidence = vi.fn();

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/signed-in-user", () => ({ useSignedInUserId: () => "user-a" }));
vi.mock("@/lib/api/client", () => ({
  getMission: (...args: unknown[]) => getMission(...args),
  getExecution: (...args: unknown[]) => getExecution(...args),
  getEvents: (...args: unknown[]) => getEvents(...args),
  getResult: (...args: unknown[]) => getResult(...args),
  getEvidence: (...args: unknown[]) => getEvidence(...args),
  startMission: vi.fn(),
}));
vi.mock("@/lib/mission-index", () => ({ forgetMission: vi.fn() }));
// The cockpit has its own tests; here only what the workspace asks the backend for, and what it hands the cockpit, matters.
vi.mock("@/components/cockpit/mission-cockpit", () => ({
  MissionCockpit: (props: Record<string, unknown>) => (
    <div
      data-testid="cockpit"
      data-events={props.events === null ? "none" : "loaded"}
      data-execution={props.execution === null ? "none" : "loaded"}
      data-result={props.result === null ? "none" : "loaded"}
      data-evidence={props.evidence === null ? "none" : "loaded"}
      data-result-loading={String(props.resultLoading)}
    />
  ),
}));

import { MissionWorkspace } from "./mission-workspace";

function summary(overrides: Partial<MissionSummary>): MissionSummary {
  return {
    mission_id: "m1", tenant_id: "t1", created_by: "u1", created_at: "2026-10-02T00:00:00Z", goal: "Goal", run_status: "running", run_status_reason: null,
    mission_status: null, status_reason: null, failure_cause: null, verified: null, plan_version: null, counters: null, last_sequence: 3, ...overrides,
  };
}

beforeEach(() => {
  for (const mock of [getMission, getExecution, getEvents, getResult, getEvidence]) mock.mockReset();
  getExecution.mockResolvedValue({ steps: [] });
  getEvents.mockResolvedValue({ events: [] });
  getEvidence.mockResolvedValue({ audit: { traces: [], cited: [] }, evidence: [] });
  getResult.mockResolvedValue({ mission_status: "completed", verified: true, verdict: null, artifacts: [], failure: null });
});

describe("MissionWorkspace — what it asks the backend for", () => {
  it("does not ask for a result while the run is in flight, and hands the cockpit the rest", async () => {
    getMission.mockResolvedValue(summary({ run_status: "running" }));
    render(<MissionWorkspace missionId="m1" />);

    const cockpit = await screen.findByTestId("cockpit");
    await waitFor(() => expect(cockpit).toHaveAttribute("data-events", "loaded")); // the live parts still load
    expect(cockpit).toHaveAttribute("data-execution", "loaded");
    expect(cockpit).toHaveAttribute("data-evidence", "loaded");
    expect(cockpit).toHaveAttribute("data-result", "none");
    expect(cockpit).toHaveAttribute("data-result-loading", "false"); // it is not loading: there is nothing to ask for yet
    expect(getResult).not.toHaveBeenCalled(); // it would only be a 409 every time
  });

  it("asks for the result once the run has ended, and hands it over", async () => {
    getMission.mockResolvedValue(summary({ run_status: "finished", mission_status: "completed" }));
    render(<MissionWorkspace missionId="m1" />);
    await waitFor(() => expect(screen.getByTestId("cockpit")).toHaveAttribute("data-result", "loaded"));
    expect(getResult).toHaveBeenCalledTimes(1);
  });

  it("hands over no result for an interrupted run whose backend has none, without calling it an error", async () => {
    getMission.mockResolvedValue(summary({ run_status: "interrupted" }));
    getResult.mockRejectedValue(new ApiError(409, { code: "not_finished", message: "not finished" }));
    render(<MissionWorkspace missionId="m1" />);
    await waitFor(() => expect(getResult).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByTestId("cockpit")).toHaveAttribute("data-result-loading", "false"));
    expect(screen.getByTestId("cockpit")).toHaveAttribute("data-result", "none");
    expect(screen.queryByText("Some details couldn't be loaded")).toBeNull(); // a documented "not yet" is not a failure
  });

  it("asks for none of the four resources for a mission that has not started", async () => {
    getMission.mockResolvedValue(summary({ run_status: "created", last_sequence: 0 }));
    render(<MissionWorkspace missionId="m1" />);
    await screen.findByTestId("cockpit");
    expect([getExecution, getEvents, getResult, getEvidence].every((mock) => mock.mock.calls.length === 0)).toBe(true);
  });
});

describe("MissionWorkspace — when a part cannot be loaded", () => {
  it("says so once, keeps the rest of the cockpit, and tries again on request", async () => {
    getMission.mockResolvedValue(summary({ run_status: "finished", mission_status: "completed" }));
    getEvents.mockRejectedValueOnce(new ApiError(503, { code: "storage_unavailable", message: "The service could not be reached right now." }));
    render(<MissionWorkspace missionId="m1" />);

    expect(await screen.findByText("Some details couldn't be loaded")).toBeInTheDocument();
    expect(screen.getByText(/The service could not be reached right now\./)).toBeInTheDocument();
    expect(screen.getByTestId("cockpit")).toHaveAttribute("data-events", "none"); // the cockpit still renders what it has
    expect(screen.getByTestId("cockpit")).toHaveAttribute("data-result", "loaded");

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.queryByText("Some details couldn't be loaded")).toBeNull());
    expect(getEvents).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(screen.getByTestId("cockpit")).toHaveAttribute("data-events", "loaded"));
  });
});

describe("MissionWorkspace — the mission itself", () => {
  it("says a mission that is not there is not found", async () => {
    getMission.mockRejectedValue(new ApiError(404, { code: "not_found", message: "no such mission" }));
    render(<MissionWorkspace missionId="m1" />);
    expect(await screen.findByText("Mission not found")).toBeInTheDocument();
    expect(screen.queryByTestId("cockpit")).toBeNull();
  });
});
