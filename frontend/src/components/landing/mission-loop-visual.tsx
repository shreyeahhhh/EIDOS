"use client";

import { useEffect, useState } from "react";

interface Stage {
  label: string;
  detail: string;
}

const STAGES: Stage[] = [
  { label: "Mission", detail: "“Research the current AI agent landscape”" },
  { label: "Plan", detail: "Research → Analyze → Verify" },
  { label: "Execute", detail: "Researching… 3 sources" },
  { label: "Verify", detail: "Evidence checked" },
  { label: "Result", detail: "Completed" },
];

const STEP_MS = 2400;

/**
 * The hero's live demonstration: the same five words a mission actually moves through, one lighting up
 * at a time. Purely illustrative motion (no network call, no fabricated metric) — the point is to show
 * the shape of the loop, not a real run. Auto-advances; pauses under reduced motion on the last stage.
 */
function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function MissionLoopVisual() {
  // Lazy initial state (computed once, during the first render) rather than an effect: a reduced-motion
  // visitor should never see the cycle start at step one and jump to the end a moment later.
  const [active, setActive] = useState(() => (prefersReducedMotion() ? STAGES.length - 1 : 0));
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (prefersReducedMotion() || paused) return;
    const timer = setInterval(() => setActive((current) => (current + 1) % STAGES.length), STEP_MS);
    return () => clearInterval(timer);
  }, [paused]);

  return (
    <div
      className="rounded-xl border border-border bg-surface-raised p-6 shadow-[var(--shadow-raised)] sm:p-8"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      role="group"
      aria-label="How a mission moves through EIDOS"
    >
      <ol className="flex flex-col">
        {STAGES.map((stage, index) => {
          const isActive = index === active;
          const isPast = index < active;
          return (
            <li key={stage.label} className="flex gap-4">
              <div className="flex flex-col items-center">
                <span
                  className={`flex h-2.5 w-2.5 shrink-0 rounded-full transition-colors duration-500 ${
                    isActive ? "bg-accent" : isPast ? "bg-ink-faint" : "bg-border-strong"
                  }`}
                  aria-hidden="true"
                />
                {index < STAGES.length - 1 && (
                  <span
                    className={`my-1 w-px flex-1 transition-colors duration-500 ${isPast ? "bg-ink-faint" : "bg-border"}`}
                    aria-hidden="true"
                  />
                )}
              </div>
              <div className={`min-w-0 pb-6 last:pb-0 ${index === STAGES.length - 1 ? "" : ""}`}>
                <p
                  className={`font-mono text-xs tracking-[0.15em] uppercase transition-colors duration-500 ${
                    isActive ? "text-accent-strong" : "text-ink-faint"
                  }`}
                >
                  {stage.label}
                </p>
                <p className={`mt-1 text-sm transition-colors duration-500 ${isActive ? "text-ink" : "text-ink-muted"}`}>
                  {stage.detail}
                </p>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
