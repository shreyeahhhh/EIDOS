import type { ReactNode } from "react";

import { describeSource } from "@/lib/citations";
import { cn } from "@/lib/cn";

/**
 * Reads an answer's plain or Markdown-ish text as a person would: headings, bullet and numbered lists, paragraphs, **bold**, `code`, and
 * numbered source chips where the answer cites `[[a reference]]`. It builds React elements from text only — nothing in the answer is ever
 * inserted as HTML, so a page's markup that ended up in an answer is shown as the plain text it is.
 */

const INLINE = /(\*\*[^*\n]+\*\*|`[^`\n]+`|\[\[[^[\]\n]+\]\])/g;

interface CiteProps {
  numbers: ReadonlyMap<string, number>;
  activeRef: string | null;
  onCite: (ref: string) => void;
}

function inline(text: string, keyPrefix: string, cite: CiteProps): ReactNode[] {
  return text.split(INLINE).map((part, index) => {
    const key = `${keyPrefix}-${index}`;
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) return <strong key={key} className="font-semibold text-ink">{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) return <code key={key} className="rounded bg-surface-sunken px-1 py-0.5 font-mono text-[0.85em]">{part.slice(1, -1)}</code>;
    if (part.startsWith("[[") && part.endsWith("]]")) {
      const ref = part.slice(2, -2).trim();
      const number = cite.numbers.get(ref);
      const info = describeSource(ref);
      return (
        <button
          key={key}
          type="button"
          onClick={() => cite.onCite(ref)}
          aria-label={`Source ${number ?? ""}: ${info.kindLabel}, ${info.label}`.replace("Source : ", "Source: ")}
          title={`${info.kindLabel}: ${info.label}`}
          className={cn(
            "mx-0.5 inline-flex h-6 min-w-6 -translate-y-0.5 items-center justify-center rounded-full px-1 align-baseline text-[11px] leading-none font-semibold transition-colors",
            cite.activeRef === ref ? "bg-accent text-on-accent" : "bg-accent-soft text-accent-strong hover:bg-accent hover:text-on-accent",
          )}
        >
          {number ?? "•"}
        </button>
      );
    }
    return part;
  });
}

type Block = { type: "heading"; level: 1 | 2 | 3; text: string } | { type: "list"; ordered: boolean; items: string[] } | { type: "paragraph"; text: string };

function parse(content: string): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  const flush = () => {
    if (paragraph.length > 0) blocks.push({ type: "paragraph", text: paragraph.join(" ") });
    if (list) blocks.push({ type: "list", ...list });
    paragraph = [];
    list = null;
  };
  for (const raw of content.split("\n")) {
    const line = raw.trimEnd();
    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    const bullet = /^\s*[-*]\s+(.*)$/.exec(line);
    const numbered = /^\s*\d+[.)]\s+(.*)$/.exec(line);
    if (!line.trim()) {
      flush();
    } else if (heading) {
      flush();
      blocks.push({ type: "heading", level: heading[1].length as 1 | 2 | 3, text: heading[2] });
    } else if (bullet || numbered) {
      const ordered = Boolean(numbered);
      if (paragraph.length > 0 || (list && list.ordered !== ordered)) flush();
      list = list ?? { ordered, items: [] };
      list.items.push((bullet ?? numbered)![1]);
    } else {
      if (list) flush();
      paragraph.push(line.trim());
    }
  }
  flush();
  return blocks;
}

export function AnswerText({ content, numbers, activeRef, onCite }: { content: string } & CiteProps) {
  const cite = { numbers, activeRef, onCite };
  return (
    <div className="flex flex-col gap-4 text-[0.95rem] leading-relaxed text-ink-muted">
      {parse(content).map((block, index) => {
        const key = `b${index}`;
        if (block.type === "heading") {
          const size = block.level === 1 ? "text-xl" : block.level === 2 ? "text-lg" : "text-base";
          return <p key={key} role="heading" aria-level={block.level + 2} className={cn("font-display text-ink", size)}>{inline(block.text, key, cite)}</p>;
        }
        if (block.type === "list") {
          const Tag = block.ordered ? "ol" : "ul";
          return (
            <Tag key={key} className={cn("flex flex-col gap-1.5 pl-5", block.ordered ? "list-decimal" : "list-disc")}>
              {block.items.map((item, itemIndex) => <li key={`${key}-${itemIndex}`}>{inline(item, `${key}-${itemIndex}`, cite)}</li>)}
            </Tag>
          );
        }
        return <p key={key}>{inline(block.text, key, cite)}</p>;
      })}
    </div>
  );
}
