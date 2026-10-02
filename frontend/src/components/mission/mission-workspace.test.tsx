import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/errors";
import type { MissionSummary } from "@/lib/api/types";

const getMission = vi.fn();
const getExecution = vi.fn();
const getEvents = vi.fn();
const getResult = vi.fn();
const getEvidence = vi.fn();

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/api/client", () => ({
  getMission: (...args: unknown[]) => getMission(...args),
  getExecution: (...args: unknown[]) => getExecution(...args),
  getEvents: (...args: unknown[]) => getEvents(...args),
  getResult: (...args: unknown[]) => getResult(...args),
  getEvidence: (...args: unknown[]) => getEvidence(...args),
  startMission: vi.fn(),
}));
vi.mock("@/lib/mission-index", () => ({ forgetMission: vi.fn() }));
// The panels have their own tests; here only what the workspace asks the backend for matters.
vi.mock("@/components/execution/execution-timeline", () => ({ ExecutionTimeline: () => <div>timeline</div> }));
vi.mock("@/components/plan/plan-graph", () => ({ PlanGraph: () => <div>plan</div> }));
vi.mock("@/components/plan/replan-lineage", () => ({ ReplanLineage: () => null }));
vi.mock("@/components/evidence/evidence-panel", () => ({ EvidencePanel: () => <div>evidence</div> }));
vi.mock("@/components/result/result-panel", () => ({ ResultPanel: () => <div>the result</div> }));
vi.mock("./mission-header", () => ({ MissionHeader: () => <div>header</div> }));

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
  it("does not ask for a result while the run is in flight, and says so itself", async () => {
    getMission.mockResolvedValue(summary({ run_status: "running" }));
    render(<MissionWorkspace missionId="m1" />);

    expect(await screen.findByText("Not finished yet")).toBeInTheDocument();
    await waitFor(() => expect(getEvents).toHaveBeenCalled()); // the live parts still load
    expect(getExecution).toHaveBeenCalled();
    expect(getEvidence).toHaveBeenCalled();
    expect(getResult).not.toHaveBeenCalled(); // it would only be a 409 every time
  });

  it("asks for the result once the run has ended, and shows it", async () => {
    getMission.mockResolvedValue(summary({ run_status: "finished", mission_status: "completed" }));
    render(<MissionWorkspace missionId="m1" />);
    expect(await screen.findByText("the result")).toBeInTheDocument();
    expect(getResult).toHaveBeenCalledTimes(1);
  });

  it("says an interrupted run ended without a result instead of claiming it is still running", async () => {
    getMission.mockResolvedValue(summary({ run_status: "interrupted" }));
    getResult.mockRejectedValue(new ApiError(409, { code: "not_finished", message: "not finished" }));
    render(<MissionWorkspace missionId="m1" />);
    expect(await screen.findByText("This run ended before it produced a result.")).toBeInTheDocument();
    expect(screen.queryByText("This mission is still running.")).toBeNull();
  });

  it("asks for none of the four resources for a mission that has not started", async () => {
    getMission.mockResolvedValue(summary({ run_status: "created", last_sequence: 0 }));
    render(<MissionWorkspace missionId="m1" />);
    expect(await screen.findByText("Nothing has happened yet")).toBeInTheDocument();
    expect([getExecution, getEvents, getResult, getEvidence].every((mock) => mock.mock.calls.length === 0)).toBe(true);
  });
});
