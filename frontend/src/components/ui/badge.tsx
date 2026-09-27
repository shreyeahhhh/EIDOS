import type { HTMLAttributes } from "react";

import { cn } from "@/lib/cn";
import type { Tone } from "@/lib/status";

const dotTone: Record<Tone, string> = {
  neutral: "bg-ink-faint",
  info: "bg-info",
  success: "bg-success",
  warning: "bg-warning",
  error: "bg-error",
};

const textTone: Record<Tone, string> = {
  neutral: "text-ink-muted",
  info: "text-info",
  success: "text-success",
  warning: "text-warning",
  error: "text-error",
};

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
}

/**
 * A status: a small colored dot plus its label, never a filled pill. Color and text always carry the
 * same information (the label alone is enough for a screen reader or a color-blind reader) — the dot
 * is a scanning aid, not the only signal.
 */
export function Badge({ tone = "neutral", className, children, ...props }: BadgeProps) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs font-medium", textTone[tone], className)} {...props}>
      <span aria-hidden="true" className={cn("h-1.5 w-1.5 shrink-0 rounded-full", dotTone[tone])} />
      {children}
    </span>
  );
}
