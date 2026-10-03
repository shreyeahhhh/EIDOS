import { EvidencePanel } from "@/components/evidence/evidence-panel";
import { ExecutionTimeline } from "@/components/execution/execution-timeline";
import type { EventRecord, EvidenceView, StepRecord } from "@/lib/api/types";

interface TechnicalDetailsProps {
  events: EventRecord[] | null;
  steps: StepRecord[];
  evidence: EvidenceView | null;
}

/** Everything an engineer might want and nobody else needs, folded away by default: the raw record of what happened, and the citation audit. */
export function TechnicalDetails({ events, steps, evidence }: TechnicalDetailsProps) {
  return (
    <details className="group rounded-2xl border border-border bg-surface-raised px-5 py-4">
      <summary className="cursor-pointer text-sm font-medium text-ink-muted select-none hover:text-ink">Technical details</summary>
      <div className="mt-4 flex flex-col gap-3">
        <details className="rounded-lg border border-border px-4 py-3">
          <summary className="cursor-pointer text-sm text-ink-muted select-none hover:text-ink">Every recorded event</summary>
          <div className="mt-3">
            {events && events.length > 0 ? <ExecutionTimeline events={events} steps={steps} /> : <p className="text-sm text-ink-faint">Nothing has been recorded yet.</p>}
          </div>
        </details>
        <details className="rounded-lg border border-border px-4 py-3">
          <summary className="cursor-pointer text-sm text-ink-muted select-none hover:text-ink">Citation audit</summary>
          <div className="mt-3">{evidence ? <EvidencePanel evidence={evidence} /> : <p className="text-sm text-ink-faint">Not available yet.</p>}</div>
        </details>
      </div>
    </details>
  );
}
