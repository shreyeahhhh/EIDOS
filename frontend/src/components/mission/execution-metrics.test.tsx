import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { makeCounters } from "@/lib/api/test-fixtures";
import { ExecutionMetrics } from "./execution-metrics";

describe("ExecutionMetrics", () => {
  it("always states the agent-call count, even at zero", () => {
    render(<ExecutionMetrics counters={makeCounters({ agent_calls_used: 0 })} />);
    expect(screen.getByText(/0 agent calls/)).toBeInTheDocument();
  });

  it("omits a counter that is zero, other than agent calls", () => {
    render(<ExecutionMetrics counters={makeCounters({ retries_used: 0, replans_used: 0, tool_calls_used: 0 })} />);
    expect(screen.queryByText(/retr/)).toBeNull();
    expect(screen.queryByText(/replan/)).toBeNull();
    expect(screen.queryByText(/tool/)).toBeNull();
  });

  it("shows every nonzero counter, and marks tokens as a lower bound", () => {
    render(
      <ExecutionMetrics
        counters={makeCounters({ agent_calls_used: 2, tool_calls_used: 1, retries_used: 1, replans_used: 1, tokens_used: 300, execution_time_used_ms: 4500 })}
      />,
    );
    expect(screen.getByText(/2 agent calls/)).toBeInTheDocument();
    expect(screen.getByText(/1 tool call/)).toBeInTheDocument();
    expect(screen.getByText(/1 retry/)).toBeInTheDocument();
    expect(screen.getByText(/1 replan/)).toBeInTheDocument();
    expect(screen.getByText(/300\+ tokens/)).toBeInTheDocument();
    expect(screen.getByText(/completed in 4.5s/)).toBeInTheDocument();
  });
});
