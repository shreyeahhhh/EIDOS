import { Badge } from "@/components/ui/badge";
import { NODE_STATUS_LABEL, NODE_STATUS_TONE, stepKindLabel } from "@/lib/status";
import type { StepRecord } from "@/lib/api/types";

const NODE_WIDTH = 168;
const NODE_HEIGHT = 60;
const H_GAP = 28;
const V_GAP = 44;

interface Positioned {
  step: StepRecord;
  x: number;
  y: number;
}

/** Levels a DAG by longest path from a root: a node's level is one past the deepest of its dependencies. Stable within a level (the plan's own step order), because `depends_on` is already validated acyclic by the backend. */
function levelOf(stepId: string, byId: Map<string, StepRecord>, cache: Map<string, number>): number {
  const cached = cache.get(stepId);
  if (cached !== undefined) return cached;
  const step = byId.get(stepId);
  if (!step || step.depends_on.length === 0) {
    cache.set(stepId, 0);
    return 0;
  }
  const level = 1 + Math.max(...step.depends_on.map((dependency) => levelOf(dependency, byId, cache)));
  cache.set(stepId, level);
  return level;
}

function layout(steps: StepRecord[]): { positions: Positioned[]; width: number; height: number } {
  const byId = new Map(steps.map((step) => [step.step_id, step]));
  const cache = new Map<string, number>();
  const rows = new Map<number, StepRecord[]>();
  for (const step of steps) {
    const level = levelOf(step.step_id, byId, cache);
    const row = rows.get(level) ?? [];
    row.push(step);
    rows.set(level, row);
  }
  const rowCount = rows.size;
  const maxRowWidth = Math.max(...[...rows.values()].map((row) => row.length * NODE_WIDTH + (row.length - 1) * H_GAP));

  const positions: Positioned[] = [];
  for (const [level, row] of rows) {
    const rowWidth = row.length * NODE_WIDTH + (row.length - 1) * H_GAP;
    const startX = (maxRowWidth - rowWidth) / 2;
    row.forEach((step, index) => {
      positions.push({ step, x: startX + index * (NODE_WIDTH + H_GAP), y: level * (NODE_HEIGHT + V_GAP) });
    });
  }
  return { positions, width: maxRowWidth, height: rowCount * NODE_HEIGHT + (rowCount - 1) * V_GAP };
}

function PlanNode({ step }: { step: StepRecord }) {
  const tone = step.result ? NODE_STATUS_TONE[step.result.status] : "neutral";
  return (
    <div className="flex h-full flex-col justify-center gap-1 rounded-md border border-border bg-surface-raised px-3 py-2 shadow-[var(--shadow-card)]">
      <p className="truncate text-sm font-medium text-ink">{stepKindLabel(step.kind, step.capability)}</p>
      <Badge tone={tone} className="w-fit">
        {step.result ? NODE_STATUS_LABEL[step.result.status] : "Pending"}
      </Badge>
    </div>
  );
}

/**
 * The plan's actual dependency structure — the steps EIDOS decided to execute, and how they depend on
 * one another — built by hand from `depends_on` (no graph library: the shapes this backend produces
 * are never complex enough to need force-layout). Below `sm`, a dependency-ordered list replaces the
 * 2-D graph rather than squeezing it into a narrow viewport; both describe the same real data.
 */
export function PlanGraph({ steps }: { steps: StepRecord[] }) {
  const { positions, width, height } = layout(steps);

  return (
    <div>
      <div className="hidden overflow-x-auto sm:block">
        <div className="relative" style={{ width, height }}>
          <svg className="absolute inset-0" width={width} height={height} aria-hidden="true">
            {positions.map(({ step, x, y }) =>
              step.depends_on.map((dependencyId) => {
                const from = positions.find((p) => p.step.step_id === dependencyId);
                if (!from) return null;
                const x1 = from.x + NODE_WIDTH / 2;
                const y1 = from.y + NODE_HEIGHT;
                const x2 = x + NODE_WIDTH / 2;
                const y2 = y;
                const midY = (y1 + y2) / 2;
                return (
                  <path
                    key={`${dependencyId}->${step.step_id}`}
                    d={`M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}`}
                    fill="none"
                    stroke="var(--color-border-strong)"
                    strokeWidth={1.5}
                  />
                );
              }),
            )}
          </svg>
          {positions.map(({ step, x, y }) => (
            <div key={step.step_id} className="absolute" style={{ left: x, top: y, width: NODE_WIDTH, height: NODE_HEIGHT }}>
              <PlanNode step={step} />
            </div>
          ))}
        </div>
      </div>

      {/* A text alternative to the graph above, always present for assistive technology (the graph itself is `aria-hidden`-adjacent decorative connectors over plain HTML nodes, but a linear reading order cannot convey a 2-D dependency layout). */}
      <ul className="sr-only">
        {positions.map(({ step }) => (
          <li key={step.step_id}>
            {stepKindLabel(step.kind, step.capability)}: {step.result ? NODE_STATUS_LABEL[step.result.status] : "Pending"}.{" "}
            {step.depends_on.length > 0 ? `Depends on ${step.depends_on.join(", ")}.` : "No dependencies."}
          </li>
        ))}
      </ul>

      <ol className="flex flex-col gap-2 sm:hidden">
        {positions.map(({ step }) => (
          <li key={step.step_id} className="rounded-md border border-border bg-surface-raised p-3">
            <PlanNode step={step} />
            {step.depends_on.length > 0 && (
              <p className="mt-2 text-xs text-ink-faint">
                Depends on: {step.depends_on.map((id) => stepKindLabel(steps.find((s) => s.step_id === id)?.kind ?? "agent", steps.find((s) => s.step_id === id)?.capability ?? null)).join(", ")}
              </p>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
