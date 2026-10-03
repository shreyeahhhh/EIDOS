import type { PlanStepKind } from "@/lib/api/types";

const PATHS: Record<string, string> = {
  // magnifier
  research: "M11 4a7 7 0 1 0 4.2 12.6l3.6 3.6 1.4-1.4-3.6-3.6A7 7 0 0 0 11 4Zm0 2a5 5 0 1 1 0 10 5 5 0 0 1 0-10Z",
  // stacked layers
  architecture: "M12 3 3 8l9 5 9-5-9-5Zm-7.2 8.6L3 12.6l9 5 9-5-1.8-1-7.2 4-7.2-4Zm0 4L3 16.6l9 5 9-5-1.8-1-7.2 4-7.2-4Z",
  // shield
  security: "M12 2 4 5v6c0 5 3.4 9.3 8 10.9 4.6-1.6 8-5.9 8-10.9V5l-8-3Zm0 2.1 6 2.2V11c0 3.9-2.5 7.3-6 8.8-3.5-1.5-6-4.9-6-8.8V6.3l6-2.2Z",
  // coin
  cost: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 2a7 7 0 1 1 0 14 7 7 0 0 1 0-14Zm-.9 2.5v1.1c-1.3.2-2.1 1-2.1 2.1 0 2.4 4 1.8 4 3 0 .4-.4.7-1.1.7-.7 0-1.3-.3-1.5-.9l-1.3.6c.3.8 1 1.3 2 1.5v1.1h1.4v-1.1c1.3-.2 2.1-1 2.1-2.1 0-2.4-4-1.8-4-3 0-.3.4-.6 1-.6s1 .3 1.3.8l1.2-.7c-.4-.7-1-1.1-1.9-1.3V7.5h-1.1Z",
  // check in a badge
  verify: "M12 2 9.5 4.5H6v3.5L3.5 10.5 6 13v3.5h3.5L12 19l2.5-2.5H18V13l2.5-2.5L18 8V4.5h-3.5L12 2Zm-1 12.4-3-3 1.4-1.4 1.6 1.6 4-4L16.4 9 11 14.4Z",
  // fallback: a ringed dot
  other: "M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16Zm0 3.5a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9Z",
};

export function iconKeyOf(kind: PlanStepKind, capability: string | null): string {
  if (kind === "VERIFY") return "verify";
  if (kind === "agent" && capability && capability in PATHS) return capability;
  return "other";
}

/** A small glyph for what a step is (its capability, or its control-flow role). Decorative: the step's label always sits beside it. */
export function StepIcon({ kind, capability, className }: { kind: PlanStepKind; capability: string | null; className?: string }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className={className ?? "h-5 w-5"} fill="currentColor">
      <path d={PATHS[iconKeyOf(kind, capability)]} fillRule="evenodd" />
    </svg>
  );
}
