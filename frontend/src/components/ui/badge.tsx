import type { HTMLAttributes } from "react";

import { cn } from "@/lib/cn";
import type { Tone } from "@/lib/status";

const toneClasses: Record<Tone, string> = {
  neutral: "bg-surface-sunken text-ink-muted",
  info: "bg-info-soft text-info",
  success: "bg-success-soft text-success",
  warning: "bg-warning-soft text-warning",
  error: "bg-error-soft text-error",
};

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
}

export function Badge({ tone = "neutral", className, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium tracking-wide",
        toneClasses[tone],
        className,
      )}
      {...props}
    />
  );
}
