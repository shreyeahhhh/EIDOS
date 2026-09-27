import Link from "next/link";

import { buttonClassName } from "@/components/ui/button";

const LOOP = ["Objective", "Strategy", "Plan", "Execute", "Verify", "Learn"];

const PRINCIPLE = [
  "The LLM proposes.",
  "The runtime validates.",
  "The agents execute.",
  "The evaluator measures.",
  "The system learns.",
];

export default function HomePage() {
  return (
    <div className="mx-auto max-w-5xl px-6">
      <section className="flex flex-col gap-6 py-24">
        <p className="text-sm font-medium tracking-[0.2em] text-accent uppercase">
          Execution Intelligence &amp; Dynamic Orchestration System
        </p>
        <h1 className="max-w-3xl font-display text-5xl leading-[1.05] tracking-tight text-ink sm:text-6xl">
          An execution-control architecture for verifiable AI work.
        </h1>
        <p className="max-w-2xl text-lg leading-relaxed text-ink-muted">
          EIDOS turns a stated objective into a validated plan, runs it through bounded agents, verifies
          what came back, and remembers what worked — so the next mission chooses better than the last.
        </p>
        <div className="mt-2 flex items-center gap-4">
          <Link href="/login" className={buttonClassName("primary", "md")}>
            Sign in
          </Link>
          <Link href="/missions/new" className="text-sm font-medium text-ink-muted hover:text-ink">
            Start a mission →
          </Link>
        </div>
      </section>

      <section className="grid gap-12 border-t border-border py-20 sm:grid-cols-[1fr_1.2fr]">
        <div>
          <h2 className="font-display text-2xl text-ink">The execution loop</h2>
          <p className="mt-3 text-sm leading-relaxed text-ink-muted">
            Every mission moves through the same bounded sequence, whether it succeeds, fails, or is
            replanned along the way.
          </p>
        </div>
        <ol className="flex flex-col">
          {LOOP.map((step, index) => (
            <li key={step} className="flex items-center gap-4 border-b border-border py-4 last:border-b-0">
              <span className="font-mono text-xs text-ink-faint">{String(index + 1).padStart(2, "0")}</span>
              <span className="font-display text-xl text-ink">{step}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="border-t border-border py-20">
        <blockquote className="mx-auto max-w-2xl border-l-2 border-accent pl-6">
          {PRINCIPLE.map((line) => (
            <p key={line} className="font-display text-2xl leading-snug text-ink sm:text-3xl">
              {line}
            </p>
          ))}
        </blockquote>
      </section>
    </div>
  );
}
