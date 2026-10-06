"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";

import { AnswerPaper } from "@/components/cockpit/answer-paper";
import { Badge } from "@/components/ui/badge";
import { buttonClassName } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Skeleton } from "@/components/ui/skeleton";
import { getResult } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { numberCitations } from "@/lib/citations";
import { decodeRuns, providerLabel, type Run } from "@/lib/compare";
import { formatDuration } from "@/lib/run-model";
import { RUN_STATUS_LABEL, RUN_STATUS_TONE } from "@/lib/status";
import { useApiResource } from "@/lib/use-api-resource";
import { useMissionStatus } from "@/lib/use-mission-status";

/**
 * The same goal run once on each model the person chose, side by side (D-246). Each column is an ordinary mission read through the same hooks the mission page uses, so nothing here is a second source of
 * truth; the page shows each run's own answer, its sources and whether its own checks passed, and **it ranks nothing**: EIDOS checks that an answer cites real sources, not which answer is right, and says so.
 * The runs this page shows come from its address, which holds mission ids, provider names and model names — never a key.
 */
export function CompareView() {
  const runs = decodeRuns(useSearchParams());

  if (runs.length < 2) {
    return (
      <Callout tone="neutral" title="Nothing to compare here">
        <p>
          This page shows two or three runs of one goal side by side. Start one from{" "}
          <Link href="/missions/new" className="font-medium underline underline-offset-4">
            a new mission
          </Link>{" "}
          by ticking two or more of your own models.
        </p>
      </Callout>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <p className="max-w-3xl text-sm leading-relaxed text-ink-muted">
        The same goal, run separately on each model. Read the answers and their sources side by side and decide for yourself: EIDOS checks that each answer cites sources that really exist, and does{" "}
        <strong className="font-semibold text-ink">not</strong> judge which answer is better or correct.
      </p>
      <div className={`grid gap-5 ${runs.length === 3 ? "lg:grid-cols-3" : "lg:grid-cols-2"}`}>
        {runs.map((run) => (
          <RunColumn key={run.id} run={run} />
        ))}
      </div>
    </div>
  );
}

function RunColumn({ run }: { run: Run }) {
  const router = useRouter();
  const status = useMissionStatus(run.id);
  const mission = status.status === "ready" ? status.mission : null;
  const hasEvents = (mission?.last_sequence ?? 0) > 0;
  const active = mission !== null && (mission.run_status === "queued" || mission.run_status === "running");
  const result = useApiResource(() => getResult(run.id), {
    enabled: hasEvents && !active,
    key: mission ? `${mission.last_sequence}-${mission.run_status}` : undefined,
    notReadyCodes: ["not_finished", "no_events"],
  });

  useEffect(() => {
    if (status.status === "error" && status.error instanceof ApiError && status.error.code === "unauthenticated") router.push("/login?next=/missions/new");
  }, [status, router]);

  const data = result.status === "ready" ? result.data : null;
  const numbers = numberCitations(data?.artifacts.map((artifact) => artifact.content) ?? []);
  const duration = formatDuration(mission?.counters?.execution_time_used_ms ?? null);

  return (
    <section aria-label={`${providerLabel(run.provider)} ${run.model}`} className="flex min-w-0 flex-col gap-4">
      <header className="flex flex-col gap-2 rounded-2xl border border-border bg-surface-raised p-4 shadow-[var(--shadow-card)]">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-display text-xl text-ink">{providerLabel(run.provider)}</h2>
          {mission && <Badge tone={RUN_STATUS_TONE[mission.run_status]}>{RUN_STATUS_LABEL[mission.run_status]}</Badge>}
        </div>
        <p className="font-mono text-xs break-all text-ink-muted">{run.model}</p>
        {mission && (
          <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-muted">
            {duration && <li>Took {duration}</li>}
            {data && !data.failure && <li>{numbers.size === 1 ? "1 source cited" : `${numbers.size} sources cited`}</li>}
            {mission.counters && <li>{mission.counters.agent_calls_used} model {mission.counters.agent_calls_used === 1 ? "call" : "calls"}</li>}
          </ul>
        )}
      </header>

      {status.status === "loading" && <Skeleton className="h-64 w-full" />}
      {status.status === "error" && (
        <Callout tone="error" title="This run could not be loaded">
          <p>{status.error.message}</p>
        </Callout>
      )}
      {mission && (
        <AnswerPaper
          mission={mission}
          result={data}
          loading={hasEvents && !active && result.status === "loading"}
          numbers={numbers}
          activeRef={null}
          onCite={() => router.push(`/missions/${run.id}`)}
          idPrefix={`run-${run.provider}-`}
        />
      )}

      <Link href={`/missions/${run.id}`} className={buttonClassName("secondary", "sm", "self-start")}>
        Open the full run — plan, replay, sources →
      </Link>
    </section>
  );
}
