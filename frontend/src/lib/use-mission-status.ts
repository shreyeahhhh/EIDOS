"use client";

import { useEffect, useRef, useState } from "react";

import { getMission } from "./api/client";
import { ApiError } from "./api/errors";
import type { MissionSummary } from "./api/types";
import { useSignedInUserId } from "./signed-in-user";

const POLL_INTERVAL_MS = 1500;
/** A safety bound, not a real timeout: 5 minutes of polling is generously past how long this bounded
 * runner ever takes. If it is ever hit, a manual refresh (reloading the page) still works. */
const MAX_POLLS = 200;
const ACTIVE_RUN_STATUSES = new Set(["queued", "running"]);

export type MissionStatusState =
  | { status: "loading" }
  | { status: "error"; error: ApiError | Error }
  | { status: "ready"; mission: MissionSummary };

/** Fetches a mission's summary, and keeps polling only while its run is genuinely in flight (`queued`/`running`). Stops the moment it reaches a terminal `run_status`, or after the safety bound. */
export function useMissionStatus(missionId: string): MissionStatusState & { reload: () => void } {
  const userId = useSignedInUserId();
  const [state, setState] = useState<MissionStatusState>({ status: "loading" });
  const [reloadToken, setReloadToken] = useState(0);

  // Resetting to "loading" the instant the mission id (or a manual reload) changes is a render-time
  // adjustment, not an effect: React's own pattern for "state that resets when a prop changes".
  const identity = `${missionId}:${reloadToken}`;
  const [trackedIdentity, setTrackedIdentity] = useState(identity);
  if (identity !== trackedIdentity) {
    setTrackedIdentity(identity);
    setState({ status: "loading" });
  }

  const pollCount = useRef(0);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    pollCount.current = 0;

    async function tick() {
      try {
        const mission = await getMission(missionId, { userId });
        if (cancelled) return;
        setState({ status: "ready", mission });
        pollCount.current += 1;
        if (ACTIVE_RUN_STATUSES.has(mission.run_status) && pollCount.current < MAX_POLLS) {
          timer = setTimeout(tick, POLL_INTERVAL_MS);
        }
      } catch (error) {
        if (cancelled) return;
        setState({ status: "error", error: error instanceof Error ? error : new Error("Something unexpected went wrong.") });
      }
    }

    tick();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [missionId, reloadToken, userId]);

  return { ...state, reload: () => setReloadToken((token) => token + 1) };
}
