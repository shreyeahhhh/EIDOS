import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { ExecutionMetrics } from "@/components/mission/execution-metrics";
import { MissionStatusPair } from "@/components/mission/mission-status-pair";
import { cn } from "@/lib/cn";
import type { MissionSummary } from "@/lib/api/types";
import { formatDateTime, type Tone } from "@/lib/status";
import { formatDuration, STEP_STATE_LABEL, type PlanVersion, type Snapshot, type Story, type StepState } from "@/lib/run-model";

const TONE_RING: Record<Tone, string> = {
  neutral: "border-border-strong bg-surface-sunken text-ink-muted",
  info: "border-info/40 bg-info-soft text-info",
  success: "border-success/40 bg-success-soft text-success",
  warning: "border-warning/40 bg-warning-soft text-warning",
  error: "border-error/40 bg-error-soft text-error",
};
const TONE_GLYPH: Record<Tone, string> = { neutral: "·", info: "…", success: "✓", warning: "!", error: "✕" };

const SEGMENT: Record<StepState, string> = {
  pending: "bg-border-strong/50",
  running: "bg-info animate-pulse",
  done: "bg-success",
  failed: "bg-error",
  unsure: "bg-warning",
  skipped: "bg-border-strong",
  waiting: "bg-info/60",
};

interface StoryBandProps {
  mission: MissionSummary;
  story: Story;
  /** How the run stands now (its newest moment), for the progress bar. */
  snapshot: Snapshot;
  planCount: number;
  webPagesRead: number;
  starting: boolean;
  startError: string | null;
  onStart: () => void;
}

function Progress({ plan, snapshot }: { plan: PlanVersion; snapshot: Snapshot }) {
  const states = plan.steps.map((step) => snapshot.steps[step.id]?.state ?? "pending");
  const done = states.filter((state) => state === "done").length;
  return (
    <div className="flex flex-col gap-2" role="group" aria-label={`${done} of ${plan.steps.length} steps done`}>
      <div className="flex gap-1.5">
        {plan.steps.map((step, index) => (
          <span key={step.id} title={`${step.label}: ${STEP_STATE_LABEL[states[index]]}`} className={cn("h-1.5 flex-1 rounded-full transition-colors", SEGMENT[states[index]])} />
        ))}
      </div>
      <p className="text-xs text-ink-faint">
        {done} of {plan.steps.length} steps done
      </p>
    </div>
  );
}

/**
 * The top of the cockpit: your goal, the whole run in one sentence, a few facts worth a glance, and — folded away — everything else.
 * The headline is the same story whether the run is going, done or failed, so the first thing you read is always what happened.
 */
export function StoryBand({ mission, story, snapshot, planCount, webPagesRead, starting, startError, onStart }: StoryBandProps) {
  const duration = formatDuration(mission.counters?.execution_time_used_ms ?? null);
  const facts = [
    duration ? `Took ${duration}` : null,
    planCount > 1 ? `Tried ${planCount} plans` : null,
    webPagesRead > 0 ? `Read ${webPagesRead} web ${webPagesRead === 1 ? "page" : "pages"}` : null,
  ].filter((fact): fact is string => fact !== null);

  return (
    <header className="flex flex-col gap-5 rounded-2xl border border-border bg-surface-raised p-5 shadow-[var(--shadow-card)] sm:p-7">
      <div className="flex flex-col gap-1">
        <p className="text-xs font-medium tracking-[0.18em] text-ink-faint uppercase">Your mission</p>
        <h1 className="font-display text-2xl leading-snug text-ink sm:text-3xl">{mission.goal}</h1>
      </div>

      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-4">
          <span aria-hidden="true" className={cn("flex h-12 w-12 shrink-0 items-center justify-center rounded-full border text-xl font-semibold", TONE_RING[story.tone])}>
            {TONE_GLYPH[story.tone]}
          </span>
          <div className="min-w-0">
            <p role="status" className="font-display text-xl text-ink">
              {story.headline}
            </p>
            {story.detail && <p className="mt-1 max-w-2xl text-sm leading-relaxed break-words text-ink-muted">{story.detail}</p>}
          </div>
        </div>
        {mission.run_status === "created" && (
          <Button onClick={onStart} disabled={starting} className="shrink-0 self-start px-6 sm:self-center">
            {starting ? "Starting…" : "Start mission"}
          </Button>
        )}
      </div>

      {snapshot.plan && <Progress plan={snapshot.plan} snapshot={snapshot} />}

      {facts.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {facts.map((fact) => (
            <li key={fact} className="rounded-full bg-surface-sunken px-3 py-1 text-xs font-medium text-ink-muted">
              {fact}
            </li>
          ))}
        </ul>
      )}

      {startError && <Callout tone="error">{startError}</Callout>}

      <details className="group border-t border-border pt-3">
        <summary className="cursor-pointer text-xs font-medium text-ink-faint select-none hover:text-ink-muted">More about this mission</summary>
        <div className="mt-3 flex flex-col gap-3">
          <MissionStatusPair runStatus={mission.run_status} missionStatus={mission.mission_status} />
          {mission.counters && <ExecutionMetrics counters={mission.counters} />}
          <p className="font-mono text-xs text-ink-faint">
            Created {formatDateTime(mission.created_at)} · mission {mission.mission_id}
          </p>
        </div>
      </details>
    </header>
  );
}
