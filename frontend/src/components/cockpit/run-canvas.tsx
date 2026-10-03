"use client";

import { useEffect, useId, useRef, useState } from "react";

import { cn } from "@/lib/cn";
import { formatDuration, STEP_STATE_LABEL, type PlanStepView, type PlanVersion, type StepSnapshot, type StepState } from "@/lib/run-model";
import { StepIcon } from "./step-icon";

const NODE_WIDTH = 176;
const NODE_HEIGHT = 74;
const H_GAP = 48;
const V_GAP = 22;
const PADDING = 20;

interface Placed {
  step: PlanStepView;
  x: number;
  y: number;
}

/** A step's column: one past the deepest of the steps it depends on (the plan is validated acyclic by the backend before it ever runs). */
function levelOf(id: string, byId: Map<string, PlanStepView>, cache: Map<string, number>): number {
  const known = cache.get(id);
  if (known !== undefined) return known;
  const step = byId.get(id);
  const level = !step || step.dependsOn.length === 0 ? 0 : 1 + Math.max(...step.dependsOn.map((dependency) => levelOf(dependency, byId, cache)));
  cache.set(id, level);
  return level;
}

type Orientation = "horizontal" | "vertical";

const V_ROW_GAP = 40;

function layout(steps: PlanStepView[], orientation: Orientation): { placed: Placed[]; width: number; height: number } {
  const byId = new Map(steps.map((step) => [step.id, step]));
  const cache = new Map<string, number>();
  const columns = new Map<number, PlanStepView[]>();
  for (const step of steps) {
    const level = levelOf(step.id, byId, cache);
    columns.set(level, [...(columns.get(level) ?? []), step]);
  }
  const tallest = Math.max(1, ...[...columns.values()].map((column) => column.length));
  const levels = columns.size;
  const placed: Placed[] = [];
  if (orientation === "horizontal") {
    const innerHeight = tallest * NODE_HEIGHT + (tallest - 1) * V_GAP;
    for (const [level, column] of columns) {
      const columnHeight = column.length * NODE_HEIGHT + (column.length - 1) * V_GAP;
      const top = PADDING + (innerHeight - columnHeight) / 2;
      column.forEach((step, index) => placed.push({ step, x: PADDING + level * (NODE_WIDTH + H_GAP), y: top + index * (NODE_HEIGHT + V_GAP) }));
    }
    return { placed, width: PADDING * 2 + levels * NODE_WIDTH + (levels - 1) * H_GAP, height: PADDING * 2 + innerHeight };
  }
  // vertical: each level is a row, centred, so a narrow column still shows the whole plan without sideways scrolling
  const innerWidth = tallest * NODE_WIDTH + (tallest - 1) * V_GAP;
  for (const [level, row] of columns) {
    const rowWidth = row.length * NODE_WIDTH + (row.length - 1) * V_GAP;
    const left = PADDING + (innerWidth - rowWidth) / 2;
    row.forEach((step, index) => placed.push({ step, x: left + index * (NODE_WIDTH + V_GAP), y: PADDING + level * (NODE_HEIGHT + V_ROW_GAP) }));
  }
  return { placed, width: PADDING * 2 + innerWidth, height: PADDING * 2 + levels * NODE_HEIGHT + (levels - 1) * V_ROW_GAP };
}

/** Left-to-right when the plan fits the space it has; top-to-bottom when it would not (a narrow column, a phone). */
function useOrientation(steps: PlanStepView[]) {
  const ref = useRef<HTMLDivElement>(null);
  const [available, setAvailable] = useState<number | null>(null);
  useEffect(() => {
    const node = ref.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => setAvailable(entries[0]?.contentRect.width ?? null));
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  const needed = layout(steps, "horizontal").width;
  const orientation: Orientation = available !== null && needed > available ? "vertical" : "horizontal";
  return { ref, orientation };
}

const NODE_STYLE: Record<StepState, { frame: string; badge: string; label: string }> = {
  pending: { frame: "border-dashed border-border-strong bg-surface-raised", badge: "bg-surface-sunken text-ink-faint", label: "text-ink-muted" },
  running: { frame: "border-info bg-info-soft/60 ring-2 ring-info/30", badge: "bg-info-soft text-info", label: "text-ink" },
  done: { frame: "border-success/40 bg-surface-raised", badge: "bg-success-soft text-success", label: "text-ink" },
  failed: { frame: "border-error/50 bg-error-soft/50", badge: "bg-error-soft text-error", label: "text-ink" },
  unsure: { frame: "border-warning/50 bg-warning-soft/50", badge: "bg-warning-soft text-warning", label: "text-ink" },
  skipped: { frame: "border-dashed border-border bg-surface-raised opacity-70", badge: "bg-surface-sunken text-ink-faint", label: "text-ink-muted" },
  waiting: { frame: "border-info/50 bg-surface-raised", badge: "bg-info-soft text-info", label: "text-ink" },
};

const STATE_GLYPH: Partial<Record<StepState, string>> = { done: "✓", failed: "✕", unsure: "?", waiting: "…" };

function edgeStroke(from: StepState | undefined, to: StepState | undefined): { stroke: string; dash?: string; width: number } {
  if (from === "failed" || from === "skipped") return { stroke: "var(--color-border-strong)", dash: "3 5", width: 1.5 };
  if (from === "done" && to === "running") return { stroke: "var(--color-info)", dash: "7 5", width: 2 };
  if (from === "done") return { stroke: "var(--color-success)", width: 2 };
  return { stroke: "var(--color-border-strong)", width: 1.5 };
}

interface RunCanvasProps {
  plan: PlanVersion;
  steps: Record<string, StepSnapshot>;
  selectedId: string | null;
  onSelect: (stepId: string) => void;
  /** Steps to draw attention to (for example, the ones that cited the source being read). */
  highlighted?: ReadonlySet<string>;
}

/**
 * The plan as a flow you can touch. Each step is a button: its colour and glyph say what it is doing at the moment being shown (never colour alone
 * — the state is also written on the card and in its accessible name), hovering or focusing one lights the path through it, and choosing one
 * opens it in the inspector. The steps and their dependencies are exactly the plan's recorded ones.
 */
export function RunCanvas({ plan, steps, selectedId, onSelect, highlighted }: RunCanvasProps) {
  const arrowId = useId();
  const [hoverId, setHoverId] = useState<string | null>(null);
  const { ref, orientation } = useOrientation(plan.steps);
  const { placed, width, height } = layout(plan.steps, orientation);
  const positionOf = new Map(placed.map((p) => [p.step.id, p]));

  // The path through the step in focus: everything it depends on, and everything that depends on it.
  const focusId = hoverId ?? selectedId;
  const related = new Set<string>();
  if (focusId) {
    const byId = new Map(plan.steps.map((step) => [step.id, step]));
    const up = (id: string) => byId.get(id)?.dependsOn.forEach((dependency) => !related.has(dependency) && (related.add(dependency), up(dependency)));
    const down = (id: string) => plan.steps.forEach((step) => step.dependsOn.includes(id) && !related.has(step.id) && (related.add(step.id), down(step.id)));
    related.add(focusId);
    up(focusId);
    down(focusId);
  }
  const dimmed = (id: string) => focusId !== null && !related.has(id);

  return (
    <div ref={ref} className="overflow-x-auto rounded-lg border border-border bg-surface-sunken/60 bg-[radial-gradient(var(--color-border)_1px,transparent_1px)] [background-size:18px_18px]">
      <div role="group" aria-label={`Plan version ${plan.version}: ${plan.steps.length} ${plan.steps.length === 1 ? "step" : "steps"}`} className="relative mx-auto" style={{ width, height }}>
        <svg className="absolute inset-0" width={width} height={height} aria-hidden="true">
          <defs>
            <marker id={arrowId} viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">
              <path d="M0 0 8 4 0 8z" fill="context-stroke" />
            </marker>
          </defs>
          {placed.flatMap(({ step, x, y }) =>
            step.dependsOn.map((dependencyId) => {
              const from = positionOf.get(dependencyId);
              if (!from) return null;
              const vertical = orientation === "vertical";
              const x1 = vertical ? from.x + NODE_WIDTH / 2 : from.x + NODE_WIDTH;
              const y1 = vertical ? from.y + NODE_HEIGHT : from.y + NODE_HEIGHT / 2;
              const x2 = vertical ? x + NODE_WIDTH / 2 : x;
              const y2 = vertical ? y : y + NODE_HEIGHT / 2;
              const mid = vertical ? (y1 + y2) / 2 : (x1 + x2) / 2;
              const style = edgeStroke(steps[dependencyId]?.state, steps[step.id]?.state);
              const lit = focusId !== null && related.has(dependencyId) && related.has(step.id);
              return (
                <path
                  key={`${dependencyId}->${step.id}`}
                  d={vertical ? `M ${x1} ${y1} C ${x1} ${mid}, ${x2} ${mid}, ${x2} ${y2 - 2}` : `M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2 - 2} ${y2}`}
                  fill="none"
                  stroke={style.stroke}
                  strokeWidth={lit ? style.width + 1 : style.width}
                  strokeDasharray={style.dash}
                  markerEnd={`url(#${arrowId})`}
                  opacity={focusId !== null && !lit ? 0.35 : 1}
                />
              );
            }),
          )}
        </svg>

        {placed.map(({ step, x, y }) => {
          const snapshot = steps[step.id];
          const state = snapshot?.state ?? "pending";
          const style = NODE_STYLE[state];
          const selected = selectedId === step.id;
          const duration = formatDuration(snapshot?.durationMs ?? null);
          return (
            <button
              key={step.id}
              type="button"
              onClick={() => onSelect(step.id)}
              onMouseEnter={() => setHoverId(step.id)}
              onMouseLeave={() => setHoverId(null)}
              onFocus={() => setHoverId(step.id)}
              onBlur={() => setHoverId(null)}
              aria-pressed={selected}
              aria-label={`${step.label}: ${STEP_STATE_LABEL[state]}${duration ? `, took ${duration}` : ""}`}
              className={cn(
                "absolute flex items-center gap-3 rounded-xl border px-3 text-left shadow-[var(--shadow-card)] transition-[opacity,box-shadow,transform] duration-200",
                style.frame,
                selected && "shadow-[var(--shadow-raised)] outline-2 outline-offset-2 outline-accent",
                highlighted?.has(step.id) && "ring-2 ring-accent",
                dimmed(step.id) && "opacity-40",
              )}
              style={{ left: x, top: y, width: NODE_WIDTH, height: NODE_HEIGHT }}
            >
              <span className={cn("relative flex h-10 w-10 shrink-0 items-center justify-center rounded-full", style.badge)}>
                <StepIcon kind={step.kind} capability={step.capability} />
                {state === "running" && <span aria-hidden="true" className="absolute inset-0 animate-ping rounded-full bg-info/25" />}
                {STATE_GLYPH[state] && (
                  <span aria-hidden="true" className={cn("absolute -right-1 -bottom-1 flex h-4 w-4 items-center justify-center rounded-full border border-surface-raised text-[10px] font-bold", style.badge)}>
                    {STATE_GLYPH[state]}
                  </span>
                )}
              </span>
              <span className="min-w-0">
                <span className={cn("block truncate text-sm font-medium", style.label)}>{step.label}</span>
                <span className="block truncate text-xs text-ink-muted">{STEP_STATE_LABEL[state]}{duration ? ` · ${duration}` : ""}</span>
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
