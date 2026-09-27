import { Badge } from "@/components/ui/badge";
import { VERDICT_LABEL, VERDICT_TONE } from "@/lib/status";
import type { VerificationFacts } from "@/lib/api/types";

/** The verifier's verdict, word for word — never turned into a score, a percentage, or "AI accuracy". */
export function VerificationPanel({ verdict }: { verdict: VerificationFacts }) {
  return (
    <div className="rounded-md border border-border bg-surface-raised p-4">
      <Badge tone={VERDICT_TONE[verdict.verdict]}>{VERDICT_LABEL[verdict.verdict]}</Badge>
      <p className="mt-3 text-sm leading-relaxed text-ink-muted">{verdict.reason}</p>
    </div>
  );
}
