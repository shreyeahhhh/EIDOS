"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { getEvents, getEvidence, getExecution, getResult, startMission } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { forgetMission } from "@/lib/mission-index";
import { useApiResource } from "@/lib/use-api-resource";
import { useMissionStatus } from "@/lib/use-mission-status";
import { Section } from "@/components/layout/section";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { ExecutionTimeline } from "@/components/execution/execution-timeline";
import { PlanGraph } from "@/components/plan/plan-graph";
import { ReplanLineage } from "@/components/plan/replan-lineage";
import { EvidencePanel } from "@/components/evidence/evidence-panel";
import { ResultPanel } from "@/components/result/result-panel";
import { MissionHeader } from "./mission-header";
import { NoWorkspaceAccess } from "./no-workspace-access";
import { TenantRequiredForm } from "./tenant-required-form";

const SECTIONS = [
  { id: "timeline", label: "Timeline" },
  { id: "plan", label: "Plan" },
  { id: "result", label: "Result" },
  { id: "evidence", label: "Evidence" },
] as const;

export function MissionWorkspace({ missionId }: { missionId: string }) {
  const router = useRouter();
  const missionState = useMissionStatus(missionId);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [tenantRetry, setTenantRetry] = useState(0);

  const mission = missionState.status === "ready" ? missionState.mission : null;
  const hasEvents = (mission?.last_sequence ?? 0) > 0;
  const runKey = mission ? `${mission.last_sequence}-${mission.run_status}` : undefined;
  // While the run is in flight there is no result to ask for: the backend would answer 409 `not_finished` every time, so the page says so itself and asks only once the run has ended.
  const runIsActive = mission !== null && (mission.run_status === "queued" || mission.run_status === "running");

  const execution = useApiResource(() => getExecution(missionId), { enabled: hasEvents, key: runKey, notReadyCodes: ["no_events"] });
  const events = useApiResource(() => getEvents(missionId, { limit: 500 }), { enabled: hasEvents, key: runKey });
  const result = useApiResource(() => getResult(missionId), { enabled: hasEvents && !runIsActive, key: runKey, notReadyCodes: ["not_finished"] });
  const evidence = useApiResource(() => getEvidence(missionId), { enabled: hasEvents, key: runKey, notReadyCodes: ["no_events"] });

  useEffect(() => {
    if (missionState.status === "error" && missionState.error instanceof ApiError) {
      if (missionState.error.code === "unauthenticated") router.push(`/login?next=/missions/${missionId}`);
      if (missionState.error.code === "not_found") forgetMission(missionId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [missionState.status]);

  async function handleStart() {
    setStarting(true);
    setStartError(null);
    try {
      await startMission(missionId);
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

  return (
    <div className="flex flex-col">
      <MissionHeader mission={mission} hasEvents={hasEvents} starting={starting} startError={startError} onStart={handleStart} />

      {hasEvents && (
        <nav aria-label="Mission sections" className="mt-6 flex gap-1 overflow-x-auto border-b border-border">
          {SECTIONS.map((section) => (
            <a
              key={section.id}
              href={`#${section.id}`}
              className="shrink-0 border-b-2 border-transparent px-3 py-3 text-sm text-ink-muted transition-colors hover:border-border-strong hover:text-ink"
            >
              {section.label}
            </a>
          ))}
        </nav>
      )}

      <Section id="timeline" title="Timeline">
        {!hasEvents ? (
          <EmptyState title="Nothing has happened yet">
            {mission.run_status === "created" ? "Start the mission to see its execution here." : "This run ended before anything was recorded."}
          </EmptyState>
        ) : events.status === "loading" ? (
          <Skeleton className="h-32 w-full" />
        ) : events.status === "error" ? (
          <ErrorState message={events.error.message} onRetry={events.reload} />
        ) : events.status === "ready" ? (
          <ExecutionTimeline events={events.data.events} steps={execution.status === "ready" ? execution.data.steps : []} />
        ) : null}
      </Section>

      <Section id="plan" title="Plan" description="The steps EIDOS decided to execute, and how they depend on one another.">
        {!hasEvents ? (
          <EmptyState title="No plan yet">A plan appears here once the mission starts.</EmptyState>
        ) : execution.status === "loading" ? (
          <Skeleton className="h-40 w-full" />
        ) : execution.status === "error" ? (
          <ErrorState message={execution.error.message} onRetry={execution.reload} />
        ) : execution.status === "ready" ? (
          <div className="flex flex-col gap-6">
            {events.status === "ready" && <ReplanLineage events={events.data.events} />}
            <PlanGraph steps={execution.data.steps} />
          </div>
        ) : null}
      </Section>

      <Section id="result" title="Result">
        {!hasEvents ? (
          <EmptyState title="No result yet">A result appears here once the mission finishes.</EmptyState>
        ) : runIsActive ? (
          <EmptyState title="Not finished yet">This mission is still running.</EmptyState>
        ) : result.status === "loading" ? (
          <Skeleton className="h-32 w-full" />
        ) : result.status === "not_ready" ? (
          <EmptyState title="No result was recorded">
            {mission.run_status === "interrupted" || mission.run_status === "error"
              ? "This run ended before it produced a result."
              : "This mission has no result yet."}
          </EmptyState>
        ) : result.status === "error" ? (
          <ErrorState message={result.error.message} onRetry={result.reload} />
        ) : result.status === "ready" ? (
          <ResultPanel result={result.data} />
        ) : null}
      </Section>

      <Section id="evidence" title="Evidence" description="Provenance for what each work step cited.">
        {!hasEvents ? (
          <EmptyState title="No evidence yet">Evidence appears here once the mission has run.</EmptyState>
        ) : evidence.status === "loading" ? (
          <Skeleton className="h-32 w-full" />
        ) : evidence.status === "error" ? (
          <ErrorState message={evidence.error.message} onRetry={evidence.reload} />
        ) : evidence.status === "ready" ? (
          <EvidencePanel evidence={evidence.data} />
        ) : null}
      </Section>
    </div>
  );
}
