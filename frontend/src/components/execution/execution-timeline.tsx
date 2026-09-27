import { NODE_STATUS_LABEL, formatDateTime, stepKindLabel } from "@/lib/status";
import type { EventRecord, StepRecord } from "@/lib/api/types";

function titleCase(screamingSnake: string): string {
  return screamingSnake
    .toLowerCase()
    .split("_")
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(" ");
}

/** The event's plain-language headline. Falls back to a Title Cased version of its own type for anything not spelled out here, so an event type this deployment cannot yet produce still reads sensibly rather than breaking. */
function describe(record: EventRecord, stepLabel: (stepId: string) => string): string {
  const { payload } = record;
  // A plain `switch`/`===` narrows nothing here: the fallback member's `event_type: string` is
  // compatible with every literal, so TypeScript cannot exclude it from any case. `in` narrows on
  // real structural presence instead, which does work, so field access below always goes through it.
  if ("plan" in payload) return `Plan generated (v${payload.plan.version})`;
  if ("step_id" in payload) return `${stepLabel(payload.step_id)} started`;
  if ("result" in payload) return `${stepLabel(payload.result.step_id)} ${NODE_STATUS_LABEL[payload.result.status].toLowerCase()}`;
  if ("failed_plan_id" in payload) return "Replanning triggered";
  if ("verified" in payload) return `Mission completed, ${payload.verified ? "verified" : "unverified"}`;
  if ("halt" in payload) return "Mission paused";
  if ("task_genome" in payload) return "Mission created";
  if ("cause" in payload && "reason" in payload) return "Mission failed";
  if ("stage" in payload) return "Plan rejected";
  // PLAN_COMPILED shares every field name with other variants (`plan_id`, `plan_version`), so it has
  // no key of its own to narrow on with `in` — its literal equality check is fine here precisely
  // because this branch needs no field access, only the static label.
  if (payload.event_type === "PLAN_COMPILED") return "Plan validated";
  return titleCase(payload.event_type);
}

export function ExecutionTimeline({ events, steps }: { events: EventRecord[]; steps: StepRecord[] }) {
  const labelOf = (stepId: string): string => {
    const step = steps.find((candidate) => candidate.step_id === stepId);
    return step ? stepKindLabel(step.kind, step.capability) : stepId;
  };

  return (
    <ol className="flex flex-col">
      {events.map((record) => (
        <li key={record.event.event_id} className="flex gap-4 border-b border-border py-3 last:border-b-0">
          <span className="w-20 shrink-0 pt-0.5 font-mono text-xs text-ink-faint">
            {new Intl.DateTimeFormat(undefined, { timeStyle: "medium" }).format(new Date(record.event.occurred_at))}
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm text-ink">{describe(record, labelOf)}</p>
            <details className="mt-1 group">
              <summary className="cursor-pointer text-xs text-ink-faint select-none hover:text-ink-muted">
                Technical detail
              </summary>
              <div className="mt-2 flex flex-col gap-1 rounded-md bg-surface-sunken p-3 font-mono text-xs text-ink-muted">
                <p>{record.event.type} · sequence {record.event.sequence} · {formatDateTime(record.event.occurred_at)}</p>
                <pre className="overflow-x-auto whitespace-pre-wrap break-all">{JSON.stringify(record.payload, null, 2)}</pre>
              </div>
            </details>
          </div>
        </li>
      ))}
    </ol>
  );
}
