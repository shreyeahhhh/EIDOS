"use client";

import { cn } from "@/lib/cn";
import { describeSource, type SourceKind } from "@/lib/citations";

/** When a source's own text is not available to show, say why — by what kind of source it is, never a guess. */
function unavailableNote(kind: SourceKind): string {
  switch (kind) {
    case "document":
      return "You supplied this document and EIDOS read it, but a copy of its text isn't kept here to show.";
    case "notes":
      return "These are notes written by an earlier step, not an outside source.";
    case "knowledge":
      return "This came from a knowledge base. Open Technical details → Citation audit to see where.";
    default:
      return "The text of this source isn't available to show here.";
  }
}

interface SourcesShelfProps {
  /** The sources, in the order they are numbered. */
  refs: string[];
  /** The text of the sources the backend can show (fetched pages, retrieved evidence), by reference. */
  texts: ReadonlyMap<string, string>;
  /** Which steps read each source, by reference (labels, for display). */
  readBy: ReadonlyMap<string, string[]>;
  openRef: string | null;
  onOpen: (ref: string | null) => void;
}

/** Everything the answer leans on, as numbered cards. Opening one shows what EIDOS actually read, who read it, and nothing it can't back up. */
export function SourcesShelf({ refs, texts, readBy, openRef, onOpen }: SourcesShelfProps) {
  if (refs.length === 0) {
    return (
      <section aria-labelledby="sources-title" className="rounded-2xl border border-dashed border-border-strong p-5">
        <h2 id="sources-title" className="font-display text-lg text-ink">
          Sources
        </h2>
        <p className="mt-1 text-sm text-ink-muted">Nothing was cited yet. When the answer cites a page or a document, it appears here.</p>
      </section>
    );
  }
  const open = openRef && refs.includes(openRef) ? openRef : null;
  const openInfo = open ? describeSource(open) : null;
  const text = open ? texts.get(open) : undefined;

  return (
    <section aria-labelledby="sources-title" className="flex flex-col gap-3 rounded-2xl border border-border bg-surface-raised p-5">
      <h2 id="sources-title" className="font-display text-lg text-ink">
        Sources <span className="font-sans text-sm text-ink-faint">({refs.length})</span>
      </h2>
      <ul className="flex flex-wrap gap-2">
        {refs.map((ref, index) => {
          const info = describeSource(ref);
          const active = ref === open;
          return (
            <li key={ref} className="max-w-full">
              <button
                type="button"
                onClick={() => onOpen(active ? null : ref)}
                aria-expanded={active}
                aria-controls="source-reader"
                title={info.label}
                className={cn(
                  "flex max-w-full items-center gap-2 rounded-xl border px-3 py-2 text-left text-sm transition-colors",
                  active ? "border-accent bg-accent-soft text-accent-strong" : "border-border text-ink-muted hover:border-accent hover:text-ink",
                )}
              >
                <span aria-hidden="true" className="flex h-5 w-5 items-center justify-center rounded-full bg-surface-sunken text-[11px] font-semibold text-ink-muted">{index + 1}</span>
                <span className="min-w-0">
                  <span className="block truncate font-medium">{info.label}</span>
                  <span className="block text-xs text-ink-muted">{info.kindLabel}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>

      <div id="source-reader" aria-live="polite">
        {open && openInfo && (
          <div className="flex flex-col gap-3 rounded-xl border border-border bg-surface-sunken/50 p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs font-medium tracking-wide text-ink-muted uppercase">{openInfo.kindLabel}</p>
                <p className="font-display text-base break-words text-ink">{openInfo.label}</p>
                {(readBy.get(open)?.length ?? 0) > 0 && <p className="mt-1 text-xs text-ink-muted">Read by: {readBy.get(open)!.join(", ")}</p>}
              </div>
              <button type="button" onClick={() => onOpen(null)} className="shrink-0 rounded-md border border-border px-2.5 py-1 text-xs text-ink-muted hover:border-border-strong hover:text-ink">
                Close
              </button>
            </div>
            {text !== undefined ? (
              <>
                <p className="text-xs text-ink-muted">This is the text EIDOS read:</p>
                <pre className="max-h-72 overflow-auto rounded-lg bg-surface-raised p-3 font-sans text-sm leading-relaxed whitespace-pre-wrap text-ink-muted">{text}</pre>
              </>
            ) : (
              <p className="text-sm text-ink-muted">{unavailableNote(openInfo.kind)}</p>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
