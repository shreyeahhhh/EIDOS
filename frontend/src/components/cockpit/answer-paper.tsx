"use client";

import Link from "next/link";
import { useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Callout } from "@/components/ui/callout";
import { headingsOf, parseAnswer, plainText } from "@/lib/answer-markdown";
import type { MissionResult, MissionSummary } from "@/lib/api/types";
import { failureCauseLabel, VERDICT_LABEL, VERDICT_TONE } from "@/lib/status";
import { AnswerBlocks } from "./answer-text";

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

const OUTLINE_LABEL_CHARS = 38;

function clip(text: string): string {
  return text.length > OUTLINE_LABEL_CHARS ? `${text.slice(0, OUTLINE_LABEL_CHARS - 1).trimEnd()}…` : text;
}

/**
 * The answer, set like a page you would want to read: an outline when there is more than one part, the text itself (never Markdown symbols — tables
 * become cards, recommendations become steps, sources become numbered chips), a Copy button, and — beneath it — whether the checks passed and what the
 * checks are. The text exactly as written is one fold away. A failed mission says plainly that it failed and why, in the recorded words, and never
 * shows a made-up answer.
 */
export function AnswerPaper({ mission, result, loading, numbers, activeRef, onCite }: AnswerPaperProps) {
  const running = mission.run_status === "queued" || mission.run_status === "running";
  const body = useRef<HTMLDivElement>(null);
  const [copied, setCopied] = useState<"idle" | "done" | "failed">("idle");
  const [evidenceOpen, setEvidenceOpen] = useState(false);

  const parsed = result && !result.failure ? result.artifacts.map((artifact) => ({ artifact, blocks: parseAnswer(artifact.content) })) : [];
  const outline = parsed.flatMap(({ blocks }) => headingsOf(blocks)).filter((heading) => heading.level <= 3);
  const hasEvidence = parsed.some(({ blocks }) => blocks.some((block) => block.t === "table"));

  async function copy() {
    try {
      await navigator.clipboard.writeText(parsed.map(({ blocks }) => plainText(blocks, numbers)).join("\n\n"));
      setCopied("done");
    } catch {
      setCopied("failed");
    }
    setTimeout(() => setCopied("idle"), 2500);
  }

  function toggleEvidence() {
    const next = !evidenceOpen;
    body.current?.querySelectorAll("details[data-evidence]").forEach((details) => ((details as HTMLDetailsElement).open = next));
    setEvidenceOpen(next);
  }

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
            <>
              <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-border pb-3">
                {outline.length > 1 ? (
                  <nav aria-label="In this answer" className="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-1 text-xs">
                    <span className="text-ink-muted">In this answer:</span>
                    {outline.map((heading) => (
                      <a key={heading.id} href={`#${heading.id}`} title={heading.text} className="rounded-full border border-border px-2.5 py-1 text-ink-muted transition-colors hover:border-accent hover:text-accent-strong">
                        {clip(heading.text)}
                      </a>
                    ))}
                  </nav>
                ) : (
                  <span />
                )}
                <div className="flex items-center gap-2">
                  {hasEvidence && (
                    <button type="button" aria-pressed={evidenceOpen} onClick={toggleEvidence} className="rounded-md border border-border px-2.5 py-1 text-xs font-medium text-ink-muted transition-colors hover:border-border-strong hover:text-ink">
                      {evidenceOpen ? "Hide all evidence" : "Show all evidence"}
                    </button>
                  )}
                  <button type="button" onClick={copy} className="rounded-md border border-border px-2.5 py-1 text-xs font-medium text-ink-muted transition-colors hover:border-border-strong hover:text-ink">
                    {copied === "done" ? "Copied" : copied === "failed" ? "Couldn't copy" : "Copy answer"}
                  </button>
                  <span role="status" className="sr-only">
                    {copied === "done" ? "The answer was copied." : copied === "failed" ? "The answer could not be copied. Use Original text below." : ""}
                  </span>
                </div>
              </div>

              <div ref={body} data-testid="answer-body" className="flex flex-col gap-6">
                {parsed.map(({ artifact, blocks }) => (
                  <AnswerBlocks key={artifact.ref} blocks={blocks} numbers={numbers} activeRef={activeRef} onCite={onCite} />
                ))}
              </div>
            </>
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

          {result.artifacts.length > 0 && (
            <details className="group rounded-lg border border-border px-4 py-3">
              <summary className="cursor-pointer text-sm font-medium text-ink-muted select-none hover:text-ink">Original text</summary>
              <div className="mt-3 flex flex-col gap-2">
                <p className="text-xs text-ink-muted">Exactly what EIDOS wrote, before it was formatted for reading.</p>
                {result.artifacts.map((artifact) => (
                  <pre key={artifact.ref} className="max-h-96 overflow-auto rounded-lg bg-surface-sunken p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap text-ink-muted">{artifact.content}</pre>
                ))}
              </div>
            </details>
          )}
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
