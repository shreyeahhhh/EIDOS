import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { makeEventRecord } from "@/lib/api/test-fixtures";
import type { EventRecord, Plan } from "@/lib/api/types";
import { ReplanLineage } from "./replan-lineage";

function plan(overrides: Partial<Plan>): Plan {
  return {
    tenant_id: "t",
    plan_id: "plan-1",
    mission_id: "m",
    version: 1,
    parent_plan_id: null,
    replan_reason: null,
    steps: [],
    ...overrides,
  };
}

describe("ReplanLineage", () => {
  it("renders nothing for a mission on its first plan — there is no lineage to show", () => {
    const events: EventRecord[] = [makeEventRecord({ payload: { event_type: "PLAN_GENERATED", plan: plan({ plan_id: "p1", version: 1 }) } })];
    const { container } = render(<ReplanLineage events={events} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows both plan versions and why the mission moved on, without mutating v1 into v2", () => {
    const events: EventRecord[] = [
      makeEventRecord({ payload: { event_type: "PLAN_GENERATED", plan: plan({ plan_id: "p1", version: 1 }) } }),
      makeEventRecord({
        payload: { event_type: "REPLAN_TRIGGERED", failed_plan_id: "p1", cause: "execution_failed", reason: "the model call failed", next_plan_id: "p2" },
      }),
      makeEventRecord({ payload: { event_type: "PLAN_GENERATED", plan: plan({ plan_id: "p2", version: 2, parent_plan_id: "p1" }) } }),
    ];
    render(<ReplanLineage events={events} />);
    expect(screen.getByText("Plan v1")).toBeInTheDocument();
    expect(screen.getByText(/Plan v2/)).toHaveTextContent("Plan v2 (current)");
    expect(screen.getByText(/execution failed/i)).toBeInTheDocument();
  });
});
