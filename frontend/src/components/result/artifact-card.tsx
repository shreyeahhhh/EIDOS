import type { ResultArtifact } from "@/lib/api/types";

export function ArtifactCard({ artifact }: { artifact: ResultArtifact }) {
  return (
    <div className="rounded-md border border-border bg-surface-raised p-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <span className="font-mono text-xs text-ink-faint">{artifact.ref}</span>
        <span className="font-mono text-xs text-ink-faint">{artifact.content_type}</span>
      </div>
      <p className="text-sm leading-relaxed whitespace-pre-wrap text-ink">{artifact.content}</p>
      {artifact.source_refs.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5 border-t border-border pt-3">
          {artifact.source_refs.map((ref) => (
            <span key={ref} className="rounded-full bg-surface-sunken px-2 py-0.5 font-mono text-xs text-ink-muted">
              {ref}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
