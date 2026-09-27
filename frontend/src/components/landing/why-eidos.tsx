const PROBLEMS = [
  { problem: "AI can generate.", caveat: "But generation isn't execution.", resolves: "Plan" },
  { problem: "Agents can act.", caveat: "But action needs control.", resolves: "Execute" },
  { problem: "Results can look right.", caveat: "But they still need verification.", resolves: "Verify" },
];

export function WhyEidos() {
  return (
    <div className="flex flex-col divide-y divide-border border-t border-border">
      {PROBLEMS.map((item) => (
        <div key={item.problem} className="flex flex-col gap-3 py-6 sm:flex-row sm:items-center sm:justify-between">
          <p className="font-display text-xl text-ink sm:text-2xl">
            {item.problem} <span className="text-ink-faint">{item.caveat}</span>
          </p>
          <span className="inline-flex w-fit items-center gap-2 rounded-md border border-border-strong px-3 py-1 font-mono text-xs text-ink-muted">
            {item.resolves}
          </span>
        </div>
      ))}
    </div>
  );
}
