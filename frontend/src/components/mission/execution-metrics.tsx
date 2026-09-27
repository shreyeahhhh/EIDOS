import type { Counters } from "@/lib/api/types";

function formatDuration(ms: number): string | null {
  if (ms <= 0) return null;
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/**
 * A restrained, compact line of the mission's real recorded counters — never an analytics dashboard.
 * Only counters that are actually meaningful (nonzero, or always worth stating) are shown.
 * `tokens_used` is a lower bound (a call whose provider did not report tokens is not counted); this
 * is stated once here rather than implied as an exact figure.
 */
export function ExecutionMetrics({ counters }: { counters: Counters }) {
  const items: string[] = [`${counters.agent_calls_used} agent ${counters.agent_calls_used === 1 ? "call" : "calls"}`];
  if (counters.tool_calls_used > 0) items.push(`${counters.tool_calls_used} tool ${counters.tool_calls_used === 1 ? "call" : "calls"}`);
  if (counters.retries_used > 0) items.push(`${counters.retries_used} ${counters.retries_used === 1 ? "retry" : "retries"}`);
  if (counters.replans_used > 0) items.push(`${counters.replans_used} ${counters.replans_used === 1 ? "replan" : "replans"}`);
  if (counters.tokens_used > 0) items.push(`${counters.tokens_used.toLocaleString()}+ tokens`);
  const duration = formatDuration(counters.execution_time_used_ms);
  if (duration) items.push(`completed in ${duration}`);

  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-xs text-ink-faint">
      {items.map((item, index) => (
        <span key={item} className="flex items-center gap-2">
          {index > 0 && <span aria-hidden="true">·</span>}
          {item}
        </span>
      ))}
    </p>
  );
}
