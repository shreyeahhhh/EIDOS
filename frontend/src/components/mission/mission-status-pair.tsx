import { Badge } from "@/components/ui/badge";
import { MISSION_STATUS_LABEL, MISSION_STATUS_TONE, RUN_STATUS_LABEL, RUN_STATUS_TONE } from "@/lib/status";
import type { MissionStatus, RunStatus } from "@/lib/api/types";

/**
 * The one place `run_status` and `mission_status` are shown together, everywhere a mission's state
 * appears. They are never merged into one word: RUN is this API's own job lifecycle; MISSION is what
 * the recorded log says happened. A "finished" run is not itself success — MISSION carries that.
 */
export function MissionStatusPair({
  runStatus,
  missionStatus,
}: {
  runStatus: RunStatus;
  missionStatus: MissionStatus | null;
}) {
  return (
    <dl className="flex items-center gap-5 text-sm">
      <div className="flex items-center gap-2">
        <dt className="text-xs font-medium tracking-wide text-ink-faint uppercase">Run</dt>
        <dd>
          <Badge tone={RUN_STATUS_TONE[runStatus]}>{RUN_STATUS_LABEL[runStatus]}</Badge>
        </dd>
      </div>
      <div className="flex items-center gap-2">
        <dt className="text-xs font-medium tracking-wide text-ink-faint uppercase">Mission</dt>
        <dd>
          {missionStatus ? (
            <Badge tone={MISSION_STATUS_TONE[missionStatus]}>{MISSION_STATUS_LABEL[missionStatus]}</Badge>
          ) : (
            <span className="text-ink-faint">—</span>
          )}
        </dd>
      </div>
    </dl>
  );
}
