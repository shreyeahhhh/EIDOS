import { failureCauseLabel } from "@/lib/status";
import type { EventRecord } from "@/lib/api/types";

interface PlanVersion {
  planId: string;
  version: number;
}

/**
 * Shows why a mission is on its current plan, when it is not the first one. Read entirely from the
 * recorded log (`PLAN_GENERATED`, `REPLAN_TRIGGERED`) — a version is never visually mutated into the
 * next: each keeps its own identity, joined only by the recorded reason a replan happened.
 */
export function ReplanLineage({ events }: { events: EventRecord[] }) {
  const plans: PlanVersion[] = [];
  const reasons = new Map<string, string>(); // failed_plan_id -> human reason

  for (const record of events) {
    // `in`, not `event_type ===`, is what actually narrows: the fallback member's `event_type: string`
    // is compatible with every literal, so equality alone cannot exclude it (see execution-timeline.tsx).
    if ("plan" in record.payload) {
      plans.push({ planId: record.payload.plan.plan_id, version: record.payload.plan.version });
    }
    if ("failed_plan_id" in record.payload) {
      reasons.set(record.payload.failed_plan_id, failureCauseLabel(record.payload.cause));
    }
  }

  if (plans.length <= 1) return null;
  plans.sort((a, b) => a.version - b.version);

  return (
    <div className="flex flex-wrap items-center gap-x-1.5 gap-y-3 text-sm">
      {plans.map((plan, index) => {
        const isCurrent = index === plans.length - 1;
        const reason = reasons.get(plan.planId);
        return (
          <span key={plan.planId} className="flex items-center gap-1.5">
            <span
              className={
                isCurrent
                  ? "rounded-md border border-accent bg-accent-soft px-2.5 py-1 font-medium text-accent-strong"
                  : "rounded-md border border-border px-2.5 py-1 text-ink-faint"
              }
            >
              Plan v{plan.version}
              {isCurrent && " (current)"}
            </span>
            {reason && (
              <>
                <span aria-hidden="true" className="text-ink-faint">
                  →
                </span>
                <span className="rounded-md border border-error/30 bg-error-soft px-2.5 py-1 text-xs text-error">{reason}</span>
                <span aria-hidden="true" className="text-ink-faint">
                  →
                </span>
              </>
            )}
          </span>
        );
      })}
    </div>
  );
}
