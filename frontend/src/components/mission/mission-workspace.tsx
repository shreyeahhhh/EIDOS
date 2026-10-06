"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { getEvents, getEvidence, getExecution, getResult, startMission } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { forgetMission } from "@/lib/mission-index";
import { useSignedInUserId } from "@/lib/signed-in-user";
import { useApiResource } from "@/lib/use-api-resource";
import { useMissionStatus } from "@/lib/use-mission-status";
import { MissionCockpit } from "@/components/cockpit/mission-cockpit";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { NoWorkspaceAccess } from "./no-workspace-access";
import { TenantRequiredForm } from "./tenant-required-form";

/**
 * Fetches everything one mission is made of and hands it to the cockpit. This is where authentication, workspace access and loading failures
 * are handled; how the mission is *shown* is the cockpit's business.
 */
export function MissionWorkspace({ missionId }: { missionId: string }) {
  const router = useRouter();
  const userId = useSignedInUserId();
  const missionState = useMissionStatus(missionId);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [tenantRetry, setTenantRetry] = useState(0);

  const mission = missionState.status === "ready" ? missionState.mission : null;
  const hasEvents = (mission?.last_sequence ?? 0) > 0;
  const runKey = mission ? `${mission.last_sequence}-${mission.run_status}` : undefined;
  // While the run is in flight there is no result to ask for: the backend would answer 409 `not_finished` every time, so the page says so itself and asks only once the run has ended.
  const runIsActive = mission !== null && (mission.run_status === "queued" || mission.run_status === "running");

  const execution = useApiResource(() => getExecution(missionId, { userId }), { enabled: hasEvents, key: runKey, notReadyCodes: ["no_events"] });
  const events = useApiResource(() => getEvents(missionId, { limit: 500 }, { userId }), { enabled: hasEvents, key: runKey });
  const result = useApiResource(() => getResult(missionId, { userId }), { enabled: hasEvents && !runIsActive, key: runKey, notReadyCodes: ["not_finished"] });
  const evidence = useApiResource(() => getEvidence(missionId, { userId }), { enabled: hasEvents, key: runKey, notReadyCodes: ["no_events"] });

  useEffect(() => {
    if (missionState.status === "error" && missionState.error instanceof ApiError) {
      if (missionState.error.code === "unauthenticated") router.push(`/login?next=/missions/${missionId}`);
      if (missionState.error.code === "not_found") forgetMission(userId, missionId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [missionState.status]);

  async function handleStart() {
    setStarting(true);
    setStartError(null);
    try {
      await startMission(missionId, { userId });
      missionState.reload();
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.code === "unauthenticated") {
          router.push(`/login?next=/missions/${missionId}`);
          return;
        }
        setStartError(error.message);
      } else {
        setStartError("Something unexpected went wrong.");
      }
    } finally {
      setStarting(false);
    }
  }

  if (missionState.status === "loading") {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-6 w-1/3" />
        <Skeleton className="mt-6 h-40 w-full" />
      </div>
    );
  }

  if (missionState.status === "error") {
    const { error } = missionState;
    if (error instanceof ApiError) {
      if (error.code === "not_found") {
        return (
          <EmptyState title="Mission not found">
            It doesn&apos;t exist, or it belongs to a different workspace than the one you&apos;re signed in as.
          </EmptyState>
        );
      }
      if (error.code === "no_tenant_membership") return <NoWorkspaceAccess />;
      if (error.code === "tenant_required") {
        return (
          <TenantRequiredForm
            key={tenantRetry}
            onSubmitted={() => {
              setTenantRetry((t) => t + 1);
              missionState.reload();
            }}
          />
        );
      }
      if (error.code === "unauthenticated") return null; // redirected in the effect above
    }
    return <ErrorState message={error.message} onRetry={missionState.reload} />;
  }

  if (!mission) return null;

  // A part that could not be loaded is said so once, with one way to try again, and the rest of the cockpit still shows what it has.
  const failures = [events, execution, result, evidence].filter((resource) => resource.status === "error");

  return (
    <div className="flex flex-col gap-5">
      {failures.length > 0 && (
        <Callout tone="warning" title="Some details couldn't be loaded">
          <p>The rest of the page still shows what it has. {failures.map((resource) => (resource.status === "error" ? resource.error.message : "")).filter(Boolean)[0]}</p>
          <Button variant="secondary" size="sm" className="mt-3" onClick={() => failures.forEach((resource) => resource.reload())}>
            Try again
          </Button>
        </Callout>
      )}
      <MissionCockpit
        mission={mission}
        events={events.status === "ready" ? events.data.events : null}
        execution={execution.status === "ready" ? execution.data : null}
        result={result.status === "ready" ? result.data : null}
        resultLoading={hasEvents && !runIsActive && result.status === "loading"}
        evidence={evidence.status === "ready" ? evidence.data : null}
        starting={starting}
        startError={startError}
        onStart={handleStart}
      />
    </div>
  );
}
