"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { getMission } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { MissionSummary, RunStatus } from "@/lib/api/types";
import { forgetMission, listIndexedMissions } from "@/lib/mission-index";
import { RUN_STATUS_LABEL } from "@/lib/status";
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

/** Only worth showing once there's enough to actually search or sort through. */
const FILTER_THRESHOLD = 6;
const RUN_STATUS_OPTIONS: RunStatus[] = ["created", "queued", "running", "finished", "rejected", "interrupted", "error"];

/**
 * Lists this browser's remembered missions (`lib/mission-index`), fetching each live from the
 * backend — the index only says *which ids to ask about*, never a mission's actual state. An id the
 * backend genuinely no longer has (a real 404) is pruned silently, not shown as an error.
 */
export function MissionDashboard() {
  const router = useRouter();
  const [state, setState] = useState<LoadState>({ name: "loading" });
  const [reloadToken, setReloadToken] = useState(0);
  const [query, setQuery] = useState("");
  const [runFilter, setRunFilter] = useState<RunStatus | "all">("all");

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
      let unauthenticated = false;

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
          if (error.code === "unauthenticated") unauthenticated = true;
          else if (error.code === "no_tenant_membership") accessIssue = { name: "no_membership" };
          else if (error.code === "tenant_required") accessIssue = { name: "tenant_required" };
          else backendIssue = error.message;
        } else {
          backendIssue = "Something unexpected went wrong.";
        }
      });

      // A session that expired between page load and this fetch (rare — `proxy.ts` already refreshes
      // it on the way in) sends the visitor back to sign in, exactly like the mission workspace does.
      if (unauthenticated) {
        router.push("/login?next=/missions");
        return;
      }

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
  }, [reloadToken, router]);

  const filtered = useMemo(() => {
    if (state.name !== "ready") return [];
    return state.missions.filter((mission) => {
      if (runFilter !== "all" && mission.run_status !== runFilter) return false;
      if (query.trim() && !mission.goal.toLowerCase().includes(query.trim().toLowerCase())) return false;
      return true;
    });
  }, [state, query, runFilter]);

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

  const showFilters = state.missions.length >= FILTER_THRESHOLD;

  return (
    <div className="flex flex-col">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        {showFilters ? (
          <div className="flex flex-1 flex-wrap items-center gap-3">
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search by objective…"
              aria-label="Search missions by objective"
              className="w-full max-w-xs rounded-md border border-border-strong bg-surface-raised px-3 py-1.5 text-sm text-ink placeholder:text-ink-faint focus-visible:border-accent"
            />
            <select
              value={runFilter}
              onChange={(event) => setRunFilter(event.target.value as RunStatus | "all")}
              aria-label="Filter by run status"
              className="rounded-md border border-border-strong bg-surface-raised px-3 py-1.5 text-sm text-ink focus-visible:border-accent"
            >
              <option value="all">Every run status</option>
              {RUN_STATUS_OPTIONS.map((status) => (
                <option key={status} value={status}>
                  {RUN_STATUS_LABEL[status]}
                </option>
              ))}
            </select>
          </div>
        ) : (
          <span />
        )}
        <Button variant="ghost" size="sm" onClick={() => setReloadToken((token) => token + 1)}>
          Refresh
        </Button>
      </div>
      {filtered.length === 0 ? (
        <EmptyState title="No missions match">Try a different search or run status.</EmptyState>
      ) : (
        <div className="border-t border-border">
          {filtered.map((mission) => (
            <MissionCard key={mission.mission_id} mission={mission} />
          ))}
        </div>
      )}
    </div>
  );
}
