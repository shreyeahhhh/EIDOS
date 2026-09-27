"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { getMission } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { MissionSummary } from "@/lib/api/types";
import { forgetMission, listIndexedMissions } from "@/lib/mission-index";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { NoWorkspaceAccess } from "./no-workspace-access";
import { TenantRequiredForm } from "./tenant-required-form";
import { MissionCard } from "./mission-card";

type LoadState =
  | { name: "loading" }
  | { name: "no_membership" }
  | { name: "tenant_required" }
  | { name: "error"; message: string }
  | { name: "ready"; missions: MissionSummary[] };

/**
 * Lists this browser's remembered missions (`lib/mission-index`), fetching each live from the
 * backend — the index only says *which ids to ask about*, never a mission's actual state. An id the
 * backend genuinely no longer has (a real 404) is pruned silently, not shown as an error.
 */
export function MissionDashboard() {
  const [state, setState] = useState<LoadState>({ name: "loading" });
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setState({ name: "loading" });
      const index = listIndexedMissions();
      if (index.length === 0) {
        if (!cancelled) setState({ name: "ready", missions: [] });
        return;
      }

      const results = await Promise.allSettled(index.map((entry) => getMission(entry.id)));
      if (cancelled) return;

      const missions: MissionSummary[] = [];
      let accessIssue: LoadState | null = null;
      let backendIssue: string | null = null;

      results.forEach((result, position) => {
        if (result.status === "fulfilled") {
          missions.push(result.value);
          return;
        }
        const error = result.reason;
        if (error instanceof ApiError) {
          if (error.code === "not_found") {
            forgetMission(index[position].id);
            return;
          }
          if (error.code === "no_tenant_membership") accessIssue = { name: "no_membership" };
          else if (error.code === "tenant_required") accessIssue = { name: "tenant_required" };
          else backendIssue = error.message;
        } else {
          backendIssue = "Something unexpected went wrong.";
        }
      });

      if (accessIssue) {
        setState(accessIssue);
      } else if (missions.length === 0 && backendIssue) {
        setState({ name: "error", message: backendIssue });
      } else {
        missions.sort((a, b) => b.created_at.localeCompare(a.created_at));
        setState({ name: "ready", missions });
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  if (state.name === "loading") {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  }

  if (state.name === "no_membership") return <NoWorkspaceAccess />;
  if (state.name === "tenant_required") {
    return <TenantRequiredForm onSubmitted={() => setReloadToken((token) => token + 1)} />;
  }
  if (state.name === "error") {
    return <ErrorState message={state.message} onRetry={() => setReloadToken((token) => token + 1)} />;
  }

  if (state.missions.length === 0) {
    return (
      <EmptyState title="No missions yet">
        <p>
          Missions you create in this browser appear here.{" "}
          <Link href="/missions/new" className="font-medium text-accent hover:text-accent-strong">
            Create the first one →
          </Link>
        </p>
      </EmptyState>
    );
  }

  return (
    <div className="flex flex-col">
      <div className="mb-2 flex justify-end">
        <Button variant="ghost" size="sm" onClick={() => setReloadToken((token) => token + 1)}>
          Refresh
        </Button>
      </div>
      <div className="border-t border-border">
        {state.missions.map((mission) => (
          <MissionCard key={mission.mission_id} mission={mission} />
        ))}
      </div>
    </div>
  );
}
