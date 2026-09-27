import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { MissionResult } from "@/lib/api/types";
import { ResultPanel } from "./result-panel";

describe("ResultPanel", () => {
  it("shows the failure cause and reason, with no artifacts or verdict section, for a failed mission", () => {
    const result: MissionResult = {
      mission_status: "failed",
      verified: null,
      verdict: null,
      artifacts: [],
      failure: { cause: "execution_failed", reason: "the model call failed" },
    };
    render(<ResultPanel result={result} />);
    expect(screen.getByText("the model call failed")).toBeInTheDocument();
    expect(screen.queryByText("Verification")).toBeNull();
  });

  it("keeps RESULT and VERIFICATION visually distinct for a completed, verified mission", () => {
    const result: MissionResult = {
      mission_status: "completed",
      verified: true,
      verdict: { verdict: "pass", reason: "every artifact cites sources that exist" },
      artifacts: [{ ref: "artifact:a", content_type: "text/markdown", content: "the finding", source_refs: ["doc:1"] }],
      failure: null,
    };
    render(<ResultPanel result={result} />);
    expect(screen.getByText("Result")).toBeInTheDocument();
    expect(screen.getByText("the finding")).toBeInTheDocument();
    expect(screen.getByText("Verification")).toBeInTheDocument();
    expect(screen.getByText("Passed verification")).toBeInTheDocument();
    expect(screen.getByText("every artifact cites sources that exist")).toBeInTheDocument();
  });

  it("never claims a verdict that was not recorded — a mission with no VERIFY step says so plainly", () => {
    const result: MissionResult = {
      mission_status: "completed",
      verified: null,
      verdict: null,
      artifacts: [{ ref: "artifact:a", content_type: "text/plain", content: "output", source_refs: [] }],
      failure: null,
    };
    render(<ResultPanel result={result} />);
    expect(screen.getByText(/no verification step/)).toBeInTheDocument();
  });
});
