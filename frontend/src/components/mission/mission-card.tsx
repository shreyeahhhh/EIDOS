import Link from "next/link";

import { formatDateTime } from "@/lib/status";
import type { MissionSummary } from "@/lib/api/types";
import { MissionStatusPair } from "./mission-status-pair";

export function MissionCard({ mission }: { mission: MissionSummary }) {
  return (
    <Link
      href={`/missions/${mission.mission_id}`}
      className="flex flex-col gap-3 border-b border-border py-5 transition-colors hover:bg-surface-sunken sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-ink">{mission.goal}</p>
        <p className="mt-1 font-mono text-xs text-ink-faint">{formatDateTime(mission.created_at)}</p>
      </div>
      <MissionStatusPair runStatus={mission.run_status} missionStatus={mission.mission_status} />
    </Link>
  );
}
