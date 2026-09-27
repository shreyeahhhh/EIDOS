import { Callout } from "@/components/ui/callout";
import { EmptyState } from "@/components/ui/empty-state";
import { failureCauseLabel } from "@/lib/status";
import type { MissionResult } from "@/lib/api/types";
import { ArtifactCard } from "./artifact-card";
import { VerificationPanel } from "./verification-panel";

/** RESULT and VERIFICATION, kept visually distinct: an artifact existing is never presented as the same fact as it having been verified. */
export function ResultPanel({ result }: { result: MissionResult }) {
  if (result.failure) {
    return (
      <Callout tone="error" title={failureCauseLabel(result.failure.cause)}>
        {result.failure.reason && <p>{result.failure.reason}</p>}
      </Callout>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h3 className="mb-3 text-sm font-medium text-ink-faint uppercase tracking-wide">Result</h3>
        {result.artifacts.length === 0 ? (
          <EmptyState title="No artifacts">This mission completed with nothing to show as a result.</EmptyState>
        ) : (
          <div className="flex flex-col gap-3">
            {result.artifacts.map((artifact) => (
              <ArtifactCard key={artifact.ref} artifact={artifact} />
            ))}
          </div>
        )}
      </div>

      <div>
        <h3 className="mb-3 text-sm font-medium text-ink-faint uppercase tracking-wide">Verification</h3>
        {result.verdict ? (
          <VerificationPanel verdict={result.verdict} />
        ) : (
          <p className="text-sm text-ink-faint">This mission completed with no verification step.</p>
        )}
      </div>
    </div>
  );
}
