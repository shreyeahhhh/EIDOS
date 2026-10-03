import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Callout } from "@/components/ui/callout";
import type { MissionResult, MissionSummary } from "@/lib/api/types";
import { failureCauseLabel, VERDICT_LABEL, VERDICT_TONE } from "@/lib/status";
import { AnswerText } from "./answer-text";

interface AnswerPaperProps {
  mission: MissionSummary;
  /** The result, once the backend has one. `null`: not available (yet). */
  result: MissionResult | null;
  /** True while the result is being asked for. */
  loading: boolean;
  numbers: ReadonlyMap<string, number>;
  activeRef: string | null;
  onCite: (ref: string) => void;
}

/**
 * The answer, set like a page you would want to read: its text, numbered sources you can open, and — beneath it — whether the checks passed
 * and what the checks are. A failed mission says plainly that it failed and why, in the recorded words, and never shows a made-up answer.
 */
export function AnswerPaper({ mission, result, loading, numbers, activeRef, onCite }: AnswerPaperProps) {
  const running = mission.run_status === "queued" || mission.run_status === "running";

  return (
    <article aria-labelledby="answer-title" className="flex flex-col gap-5 rounded-2xl border border-border bg-surface-raised p-5 shadow-[var(--shadow-raised)] sm:p-7">
      <header className="flex items-center justify-between gap-3">
        <h2 id="answer-title" className="font-display text-2xl text-ink">
          The answer
        </h2>
        {result && !result.failure && result.verdict && <Badge tone={VERDICT_TONE[result.verdict.verdict]}>{VERDICT_LABEL[result.verdict.verdict]}</Badge>}
      </header>

      {result?.failure ? (
        <Callout tone="error" title={failureCauseLabel(result.failure.cause)}>
          {result.failure.reason ? <p className="break-words">{result.failure.reason}</p> : <p>No further reason was recorded.</p>}
          <p className="mt-3">
            Nothing was made up to fill the gap. Open a step in the plan to see where it stopped, or{" "}
            <Link href="/missions/new" className="font-medium underline underline-offset-4">
              start a new mission
            </Link>
            .
          </p>
        </Callout>
      ) : result ? (
        <>
          {result.artifacts.length === 0 ? (
            <p className="text-sm text-ink-muted">This mission finished with nothing to show.</p>
          ) : (
            <div className="flex flex-col gap-6">
              {result.artifacts.map((artifact) => (
                <AnswerText key={artifact.ref} content={artifact.content} numbers={numbers} activeRef={activeRef} onCite={onCite} />
              ))}
            </div>
          )}

          <details className="group rounded-lg border border-border bg-surface-sunken/50 px-4 py-3">
            <summary className="cursor-pointer text-sm font-medium text-ink-muted select-none hover:text-ink">How was this checked?</summary>
            <div className="mt-3 flex flex-col gap-3 text-sm leading-relaxed text-ink-muted">
              <p>
                EIDOS checks that the answer is well-formed, that it cites its sources, and that every source it cites really exists. It does <strong className="font-semibold text-ink">not</strong> judge whether
                the answer is correct — read it with that in mind.
              </p>
              {result.verdict ? <p className="font-mono text-xs break-words text-ink-muted">{result.verdict.reason}</p> : <p>This mission had no checking step.</p>}
            </div>
          </details>
        </>
      ) : loading || running ? (
        <div aria-live="polite" className="flex flex-col gap-3">
          <p className="text-sm text-ink-muted">{running ? "EIDOS is still working. The answer will appear here as soon as it is ready." : "Looking for the answer…"}</p>
          <div aria-hidden="true" className="flex flex-col gap-2.5">
            {[92, 100, 78, 96, 64].map((width, index) => (
              <div key={index} className="h-3 animate-pulse rounded-full bg-surface-sunken" style={{ width: `${width}%` }} />
            ))}
          </div>
        </div>
      ) : mission.run_status === "created" ? (
        <p className="text-sm text-ink-muted">Start the mission and the answer will appear here.</p>
      ) : (
        <p className="text-sm text-ink-muted">This run ended before it produced an answer.</p>
      )}
    </article>
  );
}
