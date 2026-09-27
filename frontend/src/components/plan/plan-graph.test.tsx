import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { makeNodeResult, makeStep } from "@/lib/api/test-fixtures";
import { PlanGraph } from "./plan-graph";

describe("PlanGraph", () => {
  it("shows every step once, by its capability, with a Pending badge before it has settled", () => {
    render(<PlanGraph steps={[makeStep({ step_id: "a", capability: "research" })]} />);
    expect(screen.getAllByText("Research").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Pending").length).toBeGreaterThan(0);
  });

  it("reflects a step's real recorded outcome, not an invented one", () => {
    render(<PlanGraph steps={[makeStep({ step_id: "a", capability: "cost", result: makeNodeResult({ step_id: "a", status: "succeeded" }) })]} />);
    expect(screen.getAllByText("Succeeded").length).toBeGreaterThan(0);
  });

  it("describes real dependencies in its text alternative, for a step that depends on another", () => {
    const steps = [makeStep({ step_id: "research", capability: "research" }), makeStep({ step_id: "verify", kind: "VERIFY", capability: null, depends_on: ["research"] })];
    render(<PlanGraph steps={steps} />);
    expect(screen.getAllByText(/Depends on research/).length).toBeGreaterThan(0);
  });

  it("never shows a dependency relationship that was not recorded", () => {
    render(<PlanGraph steps={[makeStep({ step_id: "a", depends_on: [] })]} />);
    expect(screen.queryByText(/Depends on/)).toBeNull();
    expect(screen.getAllByText(/No dependencies/).length).toBeGreaterThan(0);
  });
});
