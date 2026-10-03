import { Badge } from "@/components/ui/badge";
import { Callout } from "@/components/ui/callout";
import { cn } from "@/lib/cn";
import { describeSource } from "@/lib/citations";
import type { StepRecord } from "@/lib/api/types";
import { formatDuration, STEP_STATE_LABEL, STEP_STATE_TONE, type PlanVersion, type StepSnapshot } from "@/lib/run-model";
import { StepIcon } from "./step-icon";

/** What each kind of step is for, in a sentence: a description of the agent's job, not a claim about this run. */
function purposeOf(kind: string, capability: string | null): string {
  if (kind === "VERIFY") return "Checks the answer: that it is well-formed, and that every source it cites really exists. It does not judge whether the answer is correct.";
  switch (capability) {
    case "research":
      return "Reads the documents and web pages it was given and notes what matters for your goal, citing each source.";
    case "architecture":
      return "Looks at what was found and analyses how it is put together.";
    case "security":
      return "Looks at what was found for security risks and weaknesses.";
    case "cost":
      return "Looks at what was found for what it would cost.";
    default:
      return "One step of the plan.";
  }
}

function formatClock(iso: string | null): string | null {
  return iso ? new Intl.DateTimeFormat(undefined, { timeStyle: "medium" }).format(new Date(iso)) : null;
}

interface StepInspectorProps {
  plan: PlanVersion;
  stepId: string | null;
  steps: Record<string, StepSnapshot>;
  /** The recorded detail for this step, when the step belongs to the current plan (earlier plans' details are not kept by the backend). */
  record: StepRecord | null;
  /** The sources the page lists; a step's other recorded citations are not offered here, as there would be nothing to open. */
  listedSources: ReadonlySet<string>;
  onSelect: (stepId: string) => void;
  onOpenSource: (ref: string) => void;
}

/**
 * One step, explained: what it is for, what it did at the moment being shown, what went wrong if something did, and which sources it used.
 * Everything technical (ids, token counts, tool calls) is behind one collapsed disclosure.
 */
export function StepInspector({ plan, stepId, steps, record, listedSources, onSelect, onOpenSource }: StepInspectorProps) {
  const step = plan.steps.find((candidate) => candidate.id === stepId);
  if (!step || !stepId) {
    return (
      <div className="flex h-full min-h-40 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border-strong p-6 text-center">
        <p className="font-display text-lg text-ink">Pick a step</p>
        <p className="max-w-56 text-sm text-ink-muted">Choose any step in the plan to see what it did, why, and what it used.</p>
      </div>
    );
  }
  const snapshot = steps[stepId];
  const state = snapshot?.state ?? "pending";
  const duration = formatDuration(snapshot?.durationMs ?? null);
  const dependencies = step.dependsOn.map((id) => plan.steps.find((candidate) => candidate.id === id)).filter((dependency) => dependency !== undefined);
  const blockedBy = dependencies.filter((dependency) => ["failed", "skipped"].includes(steps[dependency.id]?.state ?? "pending"));
  // Only sources the page lists, so every chip here opens something (a string a step recorded that EIDOS cannot place is left to the citation audit).
  const used = [...new Set(record?.citations ?? [])].filter((ref) => listedSources.has(ref));
  const started = formatClock(snapshot?.startedAt ?? null);
  const settled = formatClock(snapshot?.settledAt ?? null);

  return (
    <div className="flex flex-col gap-4 rounded-lg border border-border bg-surface-raised p-4 sm:p-5" aria-live="polite">
      <div className="flex items-start gap-3">
        <span className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-full", state === "done" ? "bg-success-soft text-success" : state === "failed" ? "bg-error-soft text-error" : state === "running" ? "bg-info-soft text-info" : "bg-surface-sunken text-ink-muted")}>
          <StepIcon kind={step.kind} capability={step.capability} />
        </span>
        <div className="min-w-0">
          <h3 className="font-display text-lg text-ink">{step.label}</h3>
          <Badge tone={STEP_STATE_TONE[state]}>{STEP_STATE_LABEL[state]}</Badge>
        </div>
      </div>

      <p className="text-sm leading-relaxed text-ink-muted">{purposeOf(step.kind, step.capability)}</p>

      {state === "failed" && (
        <Callout tone="error" title="What went wrong">
          {snapshot?.reason ? <p className="break-words">{snapshot.reason}</p> : <p>This step didn&apos;t produce a result, and no reason was recorded.</p>}
        </Callout>
      )}
      {state === "skipped" && (
        <Callout tone="neutral" title="Why it was skipped">
          {blockedBy.length > 0 ? (
            <p>It needs {blockedBy.map((dependency) => dependency.label).join(" and ")}, which didn&apos;t work, so EIDOS didn&apos;t run it.</p>
          ) : (
            <p>EIDOS didn&apos;t run it in this plan.</p>
          )}
        </Callout>
      )}
      {state === "unsure" && (
        <Callout tone="warning" title="Not confirmed">
          <p>{snapshot?.reason ?? "The checks couldn't confirm this step either way."}</p>
        </Callout>
      )}
      {state === "done" && snapshot?.artifact && <p className="text-sm text-ink-muted">It wrote notes for the next step.</p>}
      {state === "running" && <p className="text-sm text-info">It is working on this right now.</p>}

      {(started || duration) && (
        <p className="font-mono text-xs text-ink-faint">
          {started && <>Started {started}</>}
          {settled && <> · finished {settled}</>}
          {duration && <> · took {duration}</>}
        </p>
      )}

      {used.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-medium tracking-wide text-ink-faint uppercase">Sources it used</p>
          <div className="flex flex-wrap gap-2">
            {used.map((ref) => {
              const info = describeSource(ref);
              return (
                <button key={ref} type="button" onClick={() => onOpenSource(ref)} className="rounded-full border border-border px-3 py-1 text-xs text-ink-muted transition-colors hover:border-accent hover:text-accent-strong">
                  {info.kindLabel}: {info.label}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {dependencies.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-medium tracking-wide text-ink-faint uppercase">Needs</p>
          <div className="flex flex-wrap gap-2">
            {dependencies.map((dependency) => (
              <button key={dependency.id} type="button" onClick={() => onSelect(dependency.id)} className="rounded-full border border-border px-3 py-1 text-xs text-ink-muted transition-colors hover:border-accent hover:text-accent-strong">
                {dependency.label}
              </button>
            ))}
          </div>
        </div>
      )}

      <details className="group border-t border-border pt-3">
        <summary className="cursor-pointer text-xs font-medium text-ink-faint select-none hover:text-ink-muted">Technical details</summary>
        <dl className="mt-3 flex flex-col gap-2 font-mono text-xs text-ink-muted">
          <div className="flex gap-2"><dt className="text-ink-faint">step id</dt><dd className="break-all">{step.id}</dd></div>
          {snapshot?.artifact && <div className="flex gap-2"><dt className="text-ink-faint">output</dt><dd className="break-all">{snapshot.artifact}</dd></div>}
          {record?.model_calls.map((call, index) => (
            <div key={`m${index}`} className="flex gap-2"><dt className="text-ink-faint">model call</dt><dd>{call.outcome}{call.prompt_tokens !== null && ` · ${call.prompt_tokens} in`}{call.output_tokens !== null && ` · ${call.output_tokens} out`}{call.elapsed_seconds !== null && ` · ${call.elapsed_seconds.toFixed(1)} s`}</dd></div>
          ))}
          {record?.tool_calls.map((call, index) => (
            <div key={`t${index}`} className="flex gap-2"><dt className="text-ink-faint">tool call</dt><dd className="break-all">{call.tool_id} · {call.outcome}{call.result_bytes !== null && ` · ${call.result_bytes} bytes`}{call.elapsed_ms !== null && ` · ${call.elapsed_ms} ms`}</dd></div>
          ))}
          {!record && <p className="text-ink-faint">Model and tool details are kept only for the plan that ran last.</p>}
        </dl>
      </details>
    </div>
  );
}
