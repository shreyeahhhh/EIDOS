import type { HTMLAttributes } from "react";

import { cn } from "@/lib/cn";
import type { Tone } from "@/lib/status";

const toneClasses: Record<Tone, string> = {
  neutral: "border-border bg-surface-sunken text-ink-muted",
  info: "border-info/30 bg-info-soft text-info",
  success: "border-success/30 bg-success-soft text-success",
  warning: "border-warning/30 bg-warning-soft text-warning",
  error: "border-error/30 bg-error-soft text-error",
};

interface CalloutProps extends HTMLAttributes<HTMLDivElement> {
  tone?: Tone;
  title?: string;
}

/** A bordered block for a state that needs the person's attention: an error, an access gate, an empty state. Never used for decoration. */
export function Callout({ tone = "neutral", title, className, children, ...props }: CalloutProps) {
  return (
    <div role={tone === "error" ? "alert" : undefined} className={cn("rounded-lg border p-4 text-sm", toneClasses[tone], className)} {...props}>
      {title && <p className="mb-1 font-medium text-ink">{title}</p>}
      <div>{children}</div>
    </div>
  );
}
