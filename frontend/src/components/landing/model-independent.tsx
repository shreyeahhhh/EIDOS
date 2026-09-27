const BRANCHES = [
  { label: "Models", items: ["Ollama, today", "swapped behind one interface"] },
  { label: "Agents", items: ["Research", "Analysis"] },
  { label: "Tools", items: ["MCP"] },
];

/** No model, vendor or SDK name appears in planning, validation or the runtime — this is the one architectural fact this section states, honestly scoped to what's actually wired today. */
export function ModelIndependent() {
  return (
    <div className="grid gap-10 sm:grid-cols-[1fr_1.3fr] sm:items-center">
      <div>
        <h2 className="font-display text-2xl leading-snug text-ink sm:text-3xl">
          The model can change.
          <br />
          The execution layer doesn&apos;t have to.
        </h2>
        <p className="mt-4 max-w-md text-sm leading-relaxed text-ink-muted">
          Plans request capabilities, not named agents. Agents call models and tools through the same interface,
          whichever is behind it.
        </p>
      </div>
      <div className="rounded-xl border border-border bg-surface-raised p-6 shadow-[var(--shadow-card)]">
        <p className="text-center font-display text-lg text-ink">EIDOS</p>
        <div className="mt-6 grid grid-cols-3 gap-4">
          {BRANCHES.map((branch) => (
            <div key={branch.label} className="border-t-2 border-border-strong pt-3 text-center">
              <p className="text-xs font-medium tracking-wide text-ink-faint uppercase">{branch.label}</p>
              <ul className="mt-2 flex flex-col gap-1">
                {branch.items.map((item) => (
                  <li key={item} className="font-mono text-xs text-ink-muted">
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
