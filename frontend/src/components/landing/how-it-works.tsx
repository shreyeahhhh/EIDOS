"use client";

import { useState } from "react";

interface Stage {
  key: string;
  label: string;
  steps: string[];
}

const STAGES: Stage[] = [
  { key: "plan", label: "Plan", steps: ["Goal", "Strategy", "Plan"] },
  { key: "execute", label: "Execute", steps: ["Agents", "Tools", "Work"] },
  { key: "verify", label: "Verify", steps: ["Output", "Evidence", "Checks"] },
  { key: "learn", label: "Learn", steps: ["Outcome", "Experience", "Future strategy"] },
];

/**
 * The one place the Plan → Execute → Verify → Learn loop is explained — deliberately the only such
 * section on the page (the hero visual demonstrates it; the "why EIDOS" section motivates it; this is
 * the single place that names each stage's real internal steps).
 */
export function HowItWorks() {
  const [activeKey, setActiveKey] = useState(STAGES[0].key);
  const active = STAGES.find((stage) => stage.key === activeKey) ?? STAGES[0];

  return (
    <div>
      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Stage of the execution loop">
        {STAGES.map((stage, index) => (
          <button
            key={stage.key}
            type="button"
            role="tab"
            aria-selected={stage.key === activeKey}
            onClick={() => setActiveKey(stage.key)}
            className={`rounded-md border px-4 py-2 text-sm font-medium transition-colors ${
              stage.key === activeKey
                ? "border-accent bg-accent-soft text-accent-strong"
                : "border-border text-ink-muted hover:border-border-strong hover:text-ink"
            }`}
          >
            {String(index + 1).padStart(2, "0")} {stage.label}
          </button>
        ))}
      </div>

      <div role="tabpanel" className="mt-8 flex flex-col gap-6 sm:flex-row sm:items-center">
        <ol className="flex flex-1 flex-col gap-3 sm:flex-row sm:items-center sm:gap-0">
          {active.steps.map((step, index) => (
            <li key={step} className="flex items-center gap-3 sm:flex-1">
              <span className="flex items-center gap-3">
                <span className="font-mono text-xs text-ink-faint">{index + 1}</span>
                <span className="font-display text-xl text-ink sm:text-2xl">{step}</span>
              </span>
              {index < active.steps.length - 1 && (
                <span aria-hidden="true" className="hidden flex-1 border-t border-dashed border-border-strong sm:block" />
              )}
            </li>
          ))}
        </ol>
      </div>

      <p className="mt-8 flex items-center gap-2 text-sm text-ink-faint">
        <span>Learn feeds back into the next mission&apos;s plan</span>
        <span aria-hidden="true">↺</span>
      </p>
    </div>
  );
}
