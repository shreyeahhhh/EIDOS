import { Badge } from "@/components/ui/badge";
import { Callout } from "@/components/ui/callout";
import { EmptyState } from "@/components/ui/empty-state";
import type { CitationKind, EvidenceView } from "@/lib/api/types";
import type { Tone } from "@/lib/status";

const KIND_LABEL: Record<CitationKind, string> = {
  resolved: "Evidence",
  unresolved: "Unresolved",
  ambiguous: "Ambiguous",
  not_evidence: "Not evidence",
};

const KIND_TONE: Record<CitationKind, Tone> = {
  resolved: "success",
  unresolved: "error",
  ambiguous: "warning",
  not_evidence: "neutral",
};

/**
 * Every citation a work step made, traced against what a knowledge base actually retrieved
 * (`audit_evidence`, D-209/D-228). Honest about the current deployment: with no knowledge base
 * configured, a citation of a supplied document is real but is not evidence in this sense — that is
 * stated plainly, never hidden and never presented as if retrieval had happened.
 */
export function EvidencePanel({ evidence }: { evidence: EvidenceView }) {
  const { traces, cited } = evidence.audit;

  if (traces.length === 0) {
    return <EmptyState title="No citations were recorded">This execution&apos;s artifacts cited nothing.</EmptyState>;
  }

  const allNotEvidence = traces.every((trace) => trace.kind === "not_evidence");
  const textByRef = new Map(evidence.evidence.map((item) => [item.ref, item.content]));
  const isFetchedPage = (ref: string) => ref.startsWith("tool:") && textByRef.has(ref);
  const anyFetchedPage = traces.some((trace) => isFetchedPage(trace.ref));

  return (
    <div className="flex flex-col gap-5">
      {allNotEvidence && (
        <Callout tone="neutral">
          This execution didn&apos;t use a knowledge base. Its citations point at{" "}
          {anyFetchedPage ? "supplied documents and web pages EIDOS fetched" : "supplied documents"}, not retrieved evidence.
        </Callout>
      )}
      <ul className="flex flex-col gap-3">
        {traces.map((trace, index) => (
          <li key={`${trace.step_id}-${trace.ref}-${index}`} className="rounded-md border border-border p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-mono text-xs break-all text-ink-muted">{trace.ref}</span>
              {isFetchedPage(trace.ref) ? <Badge tone="info">Web page</Badge> : <Badge tone={KIND_TONE[trace.kind]}>{KIND_LABEL[trace.kind]}</Badge>}
            </div>
            {trace.kind === "resolved" && textByRef.has(trace.ref) && (
              <p className="mt-2 text-sm whitespace-pre-wrap text-ink-muted">{textByRef.get(trace.ref)}</p>
            )}
            {isFetchedPage(trace.ref) && (
              <details className="mt-2">
                <summary className="cursor-pointer text-xs font-medium text-ink-muted hover:text-ink">The text EIDOS read from this page</summary>
                <p className="mt-2 max-h-96 overflow-auto text-sm whitespace-pre-wrap text-ink-muted">{textByRef.get(trace.ref)}</p>
              </details>
            )}
          </li>
        ))}
      </ul>
      {cited.length > 0 && (
        <p className="text-xs text-ink-faint">
          {cited.length} distinct {cited.length === 1 ? "source" : "sources"} behind the resolved citations.
        </p>
      )}
    </div>
  );
}
