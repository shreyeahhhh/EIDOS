import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MissionStatusPair } from "./mission-status-pair";

describe("MissionStatusPair", () => {
  it("shows RUN and MISSION as two distinct facts, never merged into one word", () => {
    render(<MissionStatusPair runStatus="finished" missionStatus="completed" />);
    expect(screen.getByText("Run")).toBeInTheDocument();
    expect(screen.getByText("Mission")).toBeInTheDocument();
    expect(screen.getByText("Finished")).toBeInTheDocument();
    expect(screen.getByText("Completed")).toBeInTheDocument();
  });

  it("shows a dash for mission status before any event exists, never inventing one", () => {
    render(<MissionStatusPair runStatus="queued" missionStatus={null} />);
    expect(screen.getByText("Queued")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("a finished run and a failed mission are shown together, not collapsed into 'failed'", () => {
    render(<MissionStatusPair runStatus="finished" missionStatus="failed" />);
    expect(screen.getByText("Finished")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });
});
