import { formatDateTime } from "@/lib/status";
import type { MissionSummary } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { ExecutionMetrics } from "./execution-metrics";
import { MissionStatusPair } from "./mission-status-pair";

interface MissionHeaderProps {
  mission: MissionSummary;
  hasEvents: boolean;
  starting: boolean;
  startError: string | null;
  onStart: () => void;
}

/** The one place a mission's identity (its goal) and its two independent statuses meet — sticky under the site header so they stay visible while the rest of the workspace scrolls. */
export function MissionHeader({ mission, hasEvents, starting, startError, onStart }: MissionHeaderProps) {
  return (
    <header className="sticky top-16 z-10 -mx-6 border-b border-border bg-[var(--color-surface-elevated)] px-6 py-6 backdrop-blur-sm sm:mx-0 sm:rounded-b-lg">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h1 className="font-display text-2xl text-ink sm:text-3xl">{mission.goal}</h1>
          <p className="mt-1 font-mono text-xs text-ink-faint">Created {formatDateTime(mission.created_at)}</p>
        </div>
        {mission.run_status === "created" && (
          <Button onClick={onStart} disabled={starting} className="shrink-0">
            {starting ? "Starting…" : "Start mission"}
          </Button>
        )}
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2">
        <MissionStatusPair runStatus={mission.run_status} missionStatus={mission.mission_status} />
        {mission.counters && <ExecutionMetrics counters={mission.counters} />}
      </div>
      {startError && (
        <Callout tone="error" className="mt-4">
          {startError}
        </Callout>
      )}
      {mission.run_status_reason && !hasEvents && (
        <Callout tone={mission.run_status === "rejected" ? "warning" : "error"} className="mt-4">
          {mission.run_status_reason}
        </Callout>
      )}
    </header>
  );
}
