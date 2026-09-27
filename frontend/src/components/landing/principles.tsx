interface Principle {
  title: string;
  detail: string;
}

/** Drawn directly from the project's own architecture invariants (CLAUDE.md) — not marketing language invented for this page. */
const PRINCIPLES: Principle[] = [
  {
    title: "Deterministic core",
    detail: "The validator, compiler, reducer and policy engine make no network call, no LLM call and have no wall-clock dependence. The same input always produces the same decision.",
  },
  {
    title: "Replayable execution",
    detail: "A completed mission can be reconstructed from its recorded events alone, without re-running any agent.",
  },
  {
    title: "Auditable events",
    detail: "Every meaningful execution step emits a structured, idempotent event carrying its own identity, ordering and timestamp.",
  },
  {
    title: "Model-independent",
    detail: "No model, vendor or SDK name appears in contracts, planning, validation, the compiler, the runtime or state. Models sit behind a capability interface.",
  },
  {
    title: "Bounded execution",
    detail: "Every mission has hard limits on nodes, depth, retries, replans and calls. Exhaustion pauses the mission for review — it never loops, and never retries forever.",
  },
  {
    title: "Evidence traceability",
    detail: "A conclusion traces to its evidence, to a source, to the retrieval query, to the agent, to the tool, to the verification that checked it.",
  },
];

export function Principles() {
  return (
    <dl className="divide-y divide-border border-t border-border">
      {PRINCIPLES.map((principle) => (
        <details key={principle.title} className="group py-4">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-4 select-none">
            <dt className="font-display text-lg text-ink">{principle.title}</dt>
            <span aria-hidden="true" className="shrink-0 text-ink-faint transition-transform group-open:rotate-45">
              +
            </span>
          </summary>
          <dd className="mt-2 max-w-2xl text-sm leading-relaxed text-ink-muted">{principle.detail}</dd>
        </details>
      ))}
    </dl>
  );
}
