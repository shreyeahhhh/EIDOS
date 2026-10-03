/**
 * Turns an answer's `[[reference]]` citations into numbered, labelled sources — the way a footnote works. The reference is exactly
 * what the backend recorded; this only decides how to *say* it ("a web page from example.com", "your document index.html") and never
 * guesses beyond the reference's own shape.
 */

export type Segment = { type: "text"; text: string } | { type: "cite"; ref: string };

const CITATION = /\[\[([^[\]\n]+)\]\]/g;

/** The answer's text, cut into plain text and citations, in order. */
export function splitCitations(content: string): Segment[] {
  const segments: Segment[] = [];
  let last = 0;
  for (const match of content.matchAll(CITATION)) {
    const start = match.index ?? 0;
    if (start > last) segments.push({ type: "text", text: content.slice(last, start) });
    segments.push({ type: "cite", ref: match[1].trim() });
    last = start + match[0].length;
  }
  if (last < content.length) segments.push({ type: "text", text: content.slice(last) });
  return segments;
}

export type SourceKind = "web" | "document" | "knowledge" | "notes" | "other";

export interface SourceInfo {
  kind: SourceKind;
  /** A short name for the source, for a chip or a heading. */
  label: string;
  /** What kind of thing it is, in a few words. */
  kindLabel: string;
}

/** A source's number and meaning, from its reference alone. */
export function describeSource(ref: string): SourceInfo {
  if (ref.startsWith("tool:")) {
    const parts = ref.split(":");
    const documentId = parts.slice(3).join(":");
    if (ref.startsWith("tool:web/fetch:")) {
      const host = documentId.replace(/-[0-9a-f]{10}$/, "");
      return { kind: "web", label: host || "a web page", kindLabel: "Web page" };
    }
    return { kind: "other", label: documentId || ref, kindLabel: "Tool result" };
  }
  if (ref.startsWith("doc:")) return { kind: "document", label: ref.slice(4) || ref, kindLabel: "Your document" };
  if (ref.startsWith("evidence:")) return { kind: "knowledge", label: "Knowledge base", kindLabel: "Knowledge base" };
  if (ref.startsWith("artifact:")) return { kind: "notes", label: "Notes from an earlier step", kindLabel: "Earlier step" };
  return { kind: "other", label: ref, kindLabel: "Source" };
}

/** The distinct references an answer cites, in the order they first appear, numbered from 1. */
export function numberCitations(contents: string[]): Map<string, number> {
  const numbers = new Map<string, number>();
  for (const content of contents) {
    for (const segment of splitCitations(content)) {
      if (segment.type === "cite" && !numbers.has(segment.ref)) numbers.set(segment.ref, numbers.size + 1);
    }
  }
  return numbers;
}
