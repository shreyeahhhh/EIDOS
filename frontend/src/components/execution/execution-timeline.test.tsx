import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { makeEventRecord, makeNodeResult, makeStep } from "@/lib/api/test-fixtures";
import type { EventRecord } from "@/lib/api/types";
import { ExecutionTimeline } from "./execution-timeline";

describe("ExecutionTimeline", () => {
  it("translates recorded event types into plain language, using the step's real capability", () => {
    const steps = [makeStep({ step_id: "s1", capability: "research" })];
    const events: EventRecord[] = [
      makeEventRecord({ payload: { event_type: "MISSION_CREATED", task_genome: {} as never, reliability_contract: {} as never, execution_id: "e" } }),
      makeEventRecord({ payload: { event_type: "NODE_STARTED", plan_id: "p", step_id: "s1", kind: "agent", capability: "research", agent_id: null } }),
      makeEventRecord({ payload: { event_type: "NODE_SETTLED", plan_id: "p", result: makeNodeResult({ step_id: "s1", status: "succeeded" }), dispatched: true, duration_ms: 10 } }),
      makeEventRecord({ payload: { event_type: "MISSION_COMPLETED", plan_id: "p", verified: true } }),
    ];
    render(<ExecutionTimeline events={events} steps={steps} />);
    expect(screen.getByText("Mission created")).toBeInTheDocument();
    expect(screen.getByText("Research started")).toBeInTheDocument();
    expect(screen.getByText("Research succeeded")).toBeInTheDocument();
    expect(screen.getByText("Mission completed, verified")).toBeInTheDocument();
  });

  it("never fabricates a lifecycle stage: an event type it does not specifically know still renders, generically", () => {
    const events: EventRecord[] = [makeEventRecord({ payload: { event_type: "RAG_SEARCH" } })];
    render(<ExecutionTimeline events={events} steps={[]} />);
    expect(screen.getByText("Rag Search")).toBeInTheDocument();
  });

  it("keeps the raw event behind a closed technical disclosure rather than showing it by default", () => {
    const events: EventRecord[] = [makeEventRecord({ payload: { event_type: "MISSION_CREATED", task_genome: {} as never, reliability_contract: {} as never, execution_id: "e" } })];
    render(<ExecutionTimeline events={events} steps={[]} />);
    const summary = screen.getByText("Technical detail");
    expect(summary.closest("details")).not.toHaveAttribute("open");
  });
});
