import type { SuppliedDocument } from "@/lib/api/types";

/**
 * Turns files the visitor picks into the `supplied_documents` the backend already accepts. Nothing is uploaded
 * to a separate store: the browser reads each file as text and it travels inside the mission request, so the
 * limits below are the backend's own (`ApiCeilings` — it rejects anything over them) checked early, with a
 * plain reason, instead of a refused request.
 */
export const MAX_DOCUMENTS = 8;
export const MAX_DOCUMENT_BYTES = 32_768;
export const MAX_TOTAL_DOCUMENT_BYTES = 131_072;

/** Plain-text formats only: a PDF or an image would need server-side extraction, which does not exist. */
export const ACCEPTED_EXTENSIONS = [".txt", ".md", ".markdown", ".html", ".htm", ".css", ".js", ".json", ".csv"] as const;

export interface PickedDocument extends SuppliedDocument {
  /** The file's own name, for display. */
  name: string;
  bytes: number;
}

export type AddResult = { documents: PickedDocument[] } | { error: string };

const encoder = new TextEncoder();

function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot === -1 ? "" : name.slice(dot).toLowerCase();
}

/** `doc:<file name>` — readable when EIDOS cites it, and inside the backend's reference pattern. */
function refFor(name: string, taken: ReadonlySet<string>): string {
  const base = `doc:${name.replace(/[^A-Za-z0-9._-]/g, "_")}`.slice(0, 120);
  let ref = base;
  for (let n = 2; taken.has(ref); n += 1) ref = `${base}-${n}`;
  return ref;
}

export function totalBytes(documents: readonly PickedDocument[]): number {
  return documents.reduce((sum, document) => sum + document.bytes, 0);
}

function kb(bytes: number): string {
  return `${Math.round(bytes / 1024)} KB`;
}

/** Adds one file's text to the list, or says why it cannot be. Never throws and never changes `existing`. */
export function addDocument(existing: readonly PickedDocument[], name: string, text: string): AddResult {
  const extension = extensionOf(name);
  if (!(ACCEPTED_EXTENSIONS as readonly string[]).includes(extension)) {
    return { error: `${name}: only text files can be used (${ACCEPTED_EXTENSIONS.join(", ")}).` };
  }
  if (existing.length >= MAX_DOCUMENTS) {
    return { error: `${name}: at most ${MAX_DOCUMENTS} documents can be attached.` };
  }
  if (text.includes("\u0000")) return { error: `${name}: this does not look like a text file.` };
  if (!text.trim()) return { error: `${name}: the file is empty.` };

  const bytes = encoder.encode(text).length;
  if (bytes > MAX_DOCUMENT_BYTES) {
    return { error: `${name}: ${kb(bytes)} is over the ${kb(MAX_DOCUMENT_BYTES)} limit for one document.` };
  }
  if (totalBytes(existing) + bytes > MAX_TOTAL_DOCUMENT_BYTES) {
    return { error: `${name}: adding it would pass the ${kb(MAX_TOTAL_DOCUMENT_BYTES)} total for all documents.` };
  }

  const taken = new Set(existing.map((document) => document.ref));
  const document: PickedDocument = {
    ref: refFor(name, taken),
    name,
    content_type: extension === ".md" || extension === ".markdown" ? "text/markdown" : "text/plain",
    content: text,
    bytes,
  };
  return { documents: [...existing, document] };
}

/** What goes into the request: the backend's own shape, without the display-only fields. */
export function toSuppliedDocuments(documents: readonly PickedDocument[]): SuppliedDocument[] {
  return documents.map(({ ref, content_type, content }) => ({ ref, content_type, content }));
}
