import { describe, expect, it } from "vitest";

import {
  addDocument,
  MAX_DOCUMENT_BYTES,
  MAX_DOCUMENTS,
  MAX_TOTAL_DOCUMENT_BYTES,
  toSuppliedDocuments,
  totalBytes,
  type PickedDocument,
} from "./documents";

function added(existing: PickedDocument[], name: string, text: string): PickedDocument[] {
  const result = addDocument(existing, name, text);
  if ("error" in result) throw new Error(result.error);
  return result.documents;
}

describe("addDocument", () => {
  it("keeps a text file as a supplied document named after the file", () => {
    const [document] = added([], "index.html", "<h1>Hi</h1>");
    expect(document).toMatchObject({ ref: "doc:index.html", name: "index.html", content_type: "text/plain", content: "<h1>Hi</h1>" });
  });

  it("marks markdown as markdown", () => {
    expect(added([], "notes.MD", "# Notes")[0].content_type).toBe("text/markdown");
  });

  it("gives a second file of the same name a different reference, and keeps the first", () => {
    const two = added(added([], "a.txt", "one"), "a.txt", "two");
    expect(new Set(two.map((d) => d.ref)).size).toBe(2);
    expect(two[0].ref).toBe("doc:a.txt");
  });

  it("makes a reference the backend accepts out of an awkward name", () => {
    const [document] = added([], "my résumé (final).txt", "text");
    expect(document.ref).toMatch(/^[A-Za-z0-9][A-Za-z0-9:._/-]{0,127}$/);
  });

  it("refuses a file that is not plain text", () => {
    expect(addDocument([], "cv.pdf", "x")).toEqual({ error: expect.stringContaining("only text files") });
    expect(addDocument([], "pic", "x")).toEqual({ error: expect.stringContaining("only text files") });
  });

  it("refuses binary content, an empty file, and an oversized one", () => {
    expect(addDocument([], "a.txt", "a\u0000b")).toEqual({ error: expect.stringContaining("text file") });
    expect(addDocument([], "a.txt", "   \n")).toEqual({ error: expect.stringContaining("empty") });
    expect(addDocument([], "a.txt", "x".repeat(MAX_DOCUMENT_BYTES + 1))).toEqual({ error: expect.stringContaining("limit for one document") });
  });

  it("counts bytes, not characters", () => {
    const text = "é".repeat(MAX_DOCUMENT_BYTES / 2 + 1); // two bytes each
    expect(addDocument([], "a.txt", text)).toEqual({ error: expect.stringContaining("limit for one document") });
  });

  it("stops at the document count and at the total size, and leaves the list as it was", () => {
    let list: PickedDocument[] = [];
    for (let i = 0; i < MAX_DOCUMENTS; i += 1) list = added(list, `f${i}.txt`, "x");
    expect(addDocument(list, "extra.txt", "x")).toEqual({ error: expect.stringContaining("at most") });

    let big: PickedDocument[] = [];
    const chunk = "x".repeat(MAX_DOCUMENT_BYTES);
    for (let i = 0; i < MAX_TOTAL_DOCUMENT_BYTES / MAX_DOCUMENT_BYTES; i += 1) big = added(big, `b${i}.txt`, chunk);
    expect(totalBytes(big)).toBe(MAX_TOTAL_DOCUMENT_BYTES);
    expect(addDocument(big, "more.txt", "x")).toEqual({ error: expect.stringContaining("total") });
    expect(big).toHaveLength(MAX_TOTAL_DOCUMENT_BYTES / MAX_DOCUMENT_BYTES);
  });
});

describe("toSuppliedDocuments", () => {
  it("sends only the backend's own three fields", () => {
    const sent = toSuppliedDocuments(added([], "a.txt", "hello"));
    expect(sent).toEqual([{ ref: "doc:a.txt", content_type: "text/plain", content: "hello" }]);
  });
});
