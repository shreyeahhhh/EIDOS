"use client";

import { useEffect, useMemo, useState, type KeyboardEvent } from "react";

import { cn } from "@/lib/cn";
import { numberCitations } from "@/lib/citations";
import type { EventRecord, EvidenceView, ExecutionRecord, MissionResult, MissionSummary } from "@/lib/api/types";
import { buildRunModel, plansAt, snapshotAt, storyOf } from "@/lib/run-model";
import { stepKindLabel } from "@/lib/status";
import { AnswerPaper } from "./answer-paper";
import { Filmstrip } from "./filmstrip";
import { RunCanvas } from "./run-canvas";
import { SourcesShelf } from "./sources-shelf";
import { StepInspector } from "./step-inspector";
import { StoryBand } from "./story-band";
import { TechnicalDetails } from "./technical-details";

const REPLAY_STEP_MS = 750;

type Tab = "plan" | "answer" | "sources";
const TABS: { id: Tab; label: string }[] = [
  { id: "plan", label: "Plan" },
  { id: "answer", label: "Answer" },
  { id: "sources", label: "Sources" },
];

export interface MissionCockpitProps {
  mission: MissionSummary;
  events: EventRecord[] | null;
  execution: ExecutionRecord | null;
  result: MissionResult | null;
  resultLoading: boolean;
  evidence: EvidenceView | null;
  starting: boolean;
  startError: string | null;
  onStart: () => void;
}

function WhatHappensNext() {
  const steps = [
    ["Plan", "EIDOS works out which steps your goal needs."],
    ["Do", "Each step runs in turn, reading what you gave it."],
    ["Check", "EIDOS checks the answer cites sources that exist."],
  ];
  return (
    <ol className="grid gap-3 sm:grid-cols-3">
      {steps.map(([title, text], index) => (
        <li key={title} className="flex flex-col gap-1.5 rounded-xl border border-dashed border-border-strong p-4">
          <span aria-hidden="true" className="font-mono text-xs text-ink-faint">{index + 1}</span>
          <span className="font-display text-lg text-ink">{title}</span>
          <span className="text-sm text-ink-muted">{text}</span>
        </li>
      ))}
    </ol>
  );
}

/**
 * The mission workspace as a cockpit rather than a document: the story on top; the plan as a flow you can touch with a replay strip under it
 * and an inspector for the step you pick; the answer set beside it, with numbered sources that open a reader; and everything technical folded
 * away. Every part is drawn from the recorded events, the execution record, the result and the evidence — nothing is invented, and a part with
 * nothing to show says so. Below `lg` the same pieces become three tabs instead of three columns.
 */
export function MissionCockpit({ mission, events, execution, result, resultLoading, evidence, starting, startError, onStart }: MissionCockpitProps) {
  const model = useMemo(() => buildRunModel(events ?? []), [events]);
  const last = model.moments.length - 1;
  const active = mission.run_status === "queued" || mission.run_status === "running";

  // The replay: following the newest moment (null), or parked on one the viewer chose.
  const [scrubbed, setScrubbed] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const cursor = scrubbed === null ? last : Math.min(scrubbed, last);
  const isPlaying = playing && scrubbed !== null && scrubbed < last;
  const live = active && scrubbed === null;

  useEffect(() => {
    if (!isPlaying || scrubbed === null) return;
    const timer = setTimeout(() => setScrubbed(scrubbed + 1), REPLAY_STEP_MS);
    return () => clearTimeout(timer);
  }, [isPlaying, scrubbed]);

  function togglePlay() {
    if (isPlaying) {
      setPlaying(false);
      return;
    }
    setScrubbed(cursor >= last ? 0 : cursor);
    setPlaying(true);
  }
  function scrub(index: number) {
    setPlaying(false);
    setScrubbed(index >= last && active ? null : index);
  }
  function goLive() {
    setPlaying(false);
    setScrubbed(null);
  }

  // What is in view: a plan version (the newest by default), the state of its steps at this moment, and the step being inspected.
  const [planChoice, setPlanChoice] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [openRef, setOpenRef] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>(() => (mission.mission_status === "completed" ? "answer" : "plan"));

  const snapshot = snapshotAt(model, cursor, planChoice);
  const latest = snapshotAt(model, last);
  const versions = plansAt(model, cursor);
  // Until one is picked, the inspector explains the step at the centre of the moment being shown (and, once a step has failed, that failure first).
  const inPlan = (id: string | null | undefined) => (id && snapshot.plan?.steps.some((step) => step.id === id) ? id : null);
  const failedStep = snapshot.plan?.steps.find((step) => snapshot.steps[step.id]?.state === "failed")?.id ?? null;
  const stepId = inPlan(selectedId) ?? failedStep ?? inPlan(snapshot.moment?.stepId);
  // A plan that EIDOS gave up on says why, once the replay has reached the point it did.
  const replacedBecause = snapshot.plan ? (model.moments.find((moment) => moment.kind === "replan" && moment.planId === snapshot.plan?.planId && moment.index <= cursor)?.reason ?? null) : null;
  const record = execution && snapshot.plan && execution.plan_id === snapshot.plan.planId ? (execution.steps.find((step) => step.step_id === stepId) ?? null) : null;

  // Sources: numbered in the order the answer first cites them, then any others that were read or audited.
  const numbers = numberCitations(result?.artifacts.map((artifact) => artifact.content) ?? []);
  const executionSteps = execution?.steps ?? [];
  const extras = [
    ...executionSteps.flatMap((step) => step.citations),
    ...(evidence?.audit.traces.map((trace) => trace.ref) ?? []),
  ];
  const refs = [...numbers.keys(), ...[...new Set(extras)].filter((ref) => !numbers.has(ref))];
  const allNumbers = new Map(refs.map((ref, index) => [ref, index + 1]));
  const texts = new Map((evidence?.evidence ?? []).map((item) => [item.ref, item.content]));
  const readBy = new Map<string, string[]>();
  for (const step of executionSteps) {
    for (const ref of new Set(step.citations)) readBy.set(ref, [...(readBy.get(ref) ?? []), stepKindLabel(step.kind, step.capability)]);
  }
  const citedBy = (ref: string | null): ReadonlySet<string> => new Set(ref ? executionSteps.filter((step) => step.citations.includes(ref)).map((step) => step.step_id) : []);
  const highlighted = snapshot.plan && execution && execution.plan_id === snapshot.plan.planId ? citedBy(openRef) : undefined;

  const webPagesRead = executionSteps.flatMap((step) => step.tool_calls).filter((call) => call.tool_id === "web/fetch" && call.outcome === "result").length;
  const story = storyOf(mission, model);

  function openSource(ref: string | null) {
    setOpenRef(ref);
    if (ref) setTab("sources");
  }

  const hasRun = model.moments.length > 0;

  function onTabKey(event: KeyboardEvent<HTMLButtonElement>, from: Tab) {
    const index = TABS.findIndex((candidate) => candidate.id === from);
    const target = event.key === "ArrowRight" ? (index + 1) % TABS.length : event.key === "ArrowLeft" ? (index + TABS.length - 1) % TABS.length : event.key === "Home" ? 0 : event.key === "End" ? TABS.length - 1 : null;
    if (target === null) return;
    event.preventDefault();
    setTab(TABS[target].id);
    document.getElementById(`tab-${TABS[target].id}`)?.focus();
  }

  return (
    <div className="flex flex-col gap-5">
      <StoryBand mission={mission} story={story} snapshot={latest} planCount={model.plans.length} webPagesRead={webPagesRead} starting={starting} startError={startError} onStart={onStart} />

      <div role="tablist" aria-label="Mission views" className="flex gap-1 rounded-xl border border-border bg-surface-sunken/60 p-1 lg:hidden">
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`tab-${id}`}
            aria-selected={tab === id}
            aria-controls={`panel-${id}`}
            tabIndex={tab === id ? 0 : -1}
            onClick={() => setTab(id)}
            onKeyDown={(event) => onTabKey(event, id)}
            className={cn("flex-1 rounded-lg px-3 py-2 text-sm font-medium transition-colors", tab === id ? "bg-surface-raised text-ink shadow-[var(--shadow-card)]" : "text-ink-muted hover:text-ink")}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)] lg:items-start">
        <div id="panel-plan" role="tabpanel" aria-labelledby="tab-plan" className={cn("flex-col gap-4 lg:flex", tab === "plan" ? "flex" : "hidden")}>
          <section aria-labelledby="plan-title" className="flex flex-col gap-4 rounded-2xl border border-border bg-surface-raised p-4 shadow-[var(--shadow-card)] sm:p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 id="plan-title" className="font-display text-xl text-ink">
                How EIDOS went about it
              </h2>
              {versions.length > 1 && (
                <div role="group" aria-label="Plan versions" className="flex gap-1.5">
                  {versions.map((version) => {
                    const shown = snapshot.plan?.planId === version.planId;
                    return (
                      <button
                        key={version.planId}
                        type="button"
                        aria-pressed={shown}
                        onClick={() => setPlanChoice(version.planId === versions[versions.length - 1].planId ? null : version.planId)}
                        className={cn("rounded-full border px-3 py-1 text-xs font-medium transition-colors", shown ? "border-accent bg-accent-soft text-accent-strong" : "border-border text-ink-muted hover:border-border-strong hover:text-ink")}
                      >
                        Plan {version.version}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            {snapshot.plan && snapshot.plan.replanReason && (
              <p className="text-sm text-ink-muted">
                <span className="font-medium text-ink">Why a new plan:</span> {snapshot.plan.replanReason}.
              </p>
            )}
            {replacedBecause && (
              <p className="text-sm text-ink-muted">
                <span className="font-medium text-ink">Why this plan was replaced:</span> {replacedBecause}.
              </p>
            )}

            {hasRun && snapshot.plan ? (
              <RunCanvas plan={snapshot.plan} steps={snapshot.steps} selectedId={stepId} onSelect={setSelectedId} highlighted={highlighted} />
            ) : hasRun ? (
              <p className="rounded-lg border border-dashed border-border-strong p-6 text-center text-sm text-ink-muted">The plan is being drawn up.</p>
            ) : mission.last_sequence > 0 ? (
              // the run has events but they have not arrived yet: say so, rather than showing what a mission that has not started looks like
              <div aria-live="polite" className="flex flex-col gap-3 rounded-lg border border-dashed border-border-strong p-6">
                <p className="text-sm text-ink-muted">Loading how it went…</p>
                <div aria-hidden="true" className="flex gap-3">
                  {[0, 1, 2].map((index) => (
                    <div key={index} className="h-16 flex-1 animate-pulse rounded-xl bg-surface-sunken" />
                  ))}
                </div>
              </div>
            ) : (
              <WhatHappensNext />
            )}

            {hasRun && <Filmstrip moments={model.moments} cursor={cursor} onScrub={scrub} playing={isPlaying} onTogglePlay={togglePlay} live={live} canGoLive={active && !live} onGoLive={goLive} />}
          </section>

          {hasRun && snapshot.plan && (
            <StepInspector plan={snapshot.plan} stepId={stepId} steps={snapshot.steps} record={record} onSelect={setSelectedId} onOpenSource={openSource} />
          )}
        </div>

        <div className="flex flex-col gap-5 lg:sticky lg:top-20">
          <div id="panel-answer" role="tabpanel" aria-labelledby="tab-answer" className={cn("lg:block", tab === "answer" ? "block" : "hidden")}>
            <AnswerPaper mission={mission} result={result} loading={resultLoading} numbers={allNumbers} activeRef={openRef} onCite={openSource} />
          </div>
          <div id="panel-sources" role="tabpanel" aria-labelledby="tab-sources" className={cn("lg:block", tab === "sources" ? "block" : "hidden")}>
            <SourcesShelf refs={refs} texts={texts} readBy={readBy} openRef={openRef} onOpen={setOpenRef} />
          </div>
        </div>
      </div>

      <TechnicalDetails events={events} steps={executionSteps} evidence={evidence} />
    </div>
  );
}

