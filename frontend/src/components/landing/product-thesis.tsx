const STAGES = [
  { index: "01", title: "Your goal", detail: "Tell EIDOS what you need." },
  { index: "02", title: "Execution", detail: "EIDOS decides how the work should happen, and runs it under limits." },
  { index: "03", title: "Verified result", detail: "The system checks what actually happened before calling it done." },
];

export function ProductThesis() {
  return (
    <div className="grid gap-8 sm:grid-cols-3 sm:gap-6">
      {STAGES.map((stage, index) => (
        <div key={stage.index} className="relative flex flex-col gap-3 pt-6">
          <span aria-hidden="true" className="absolute top-0 left-0 h-px w-12 bg-accent" />
          <span className="font-mono text-xs text-ink-faint">{stage.index}</span>
          <h3 className="font-display text-2xl text-ink">{stage.title}</h3>
          <p className="text-sm leading-relaxed text-ink-muted">{stage.detail}</p>
          {index < STAGES.length - 1 && (
            <span aria-hidden="true" className="absolute top-6 -right-4 hidden text-ink-faint sm:block">
              →
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
