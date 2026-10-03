"use client";

import { useState, type ReactNode } from "react";

import { describeSource } from "@/lib/citations";
import { cn } from "@/lib/cn";
import {
  citationsIn,
  inlineText,
  parseAnswer,
  splitLead,
  type Block,
  type Inline,
  type ListBlock,
  type TableBlock,
} from "@/lib/answer-markdown";

/**
 * An answer, set for reading. It never shows Markdown: headings are headings, lists are lists, a table becomes cards (one per row, the evidence
 * folded away) with a switch to the plain table, numbered recommendations with bold titles become steps, and `[[reference]]` becomes a numbered
 * source chip. Elements are built from the parsed model only (`lib/answer-markdown.ts`), so nothing in an answer can become markup.
 */

interface CiteProps {
  numbers: ReadonlyMap<string, number>;
  activeRef: string | null;
  onCite: (ref: string) => void;
}

function CiteChip({ reference, numbers, activeRef, onCite }: CiteProps & { reference: string }) {
  const number = numbers.get(reference);
  const info = describeSource(reference);
  return (
    <button
      type="button"
      onClick={() => onCite(reference)}
      aria-label={`Source ${number ?? ""}: ${info.kindLabel}, ${info.label}`.replace("Source : ", "Source: ")}
      title={`${info.kindLabel}: ${info.label}`}
      className={cn(
        "mx-0.5 inline-flex h-6 min-w-6 -translate-y-0.5 items-center justify-center rounded-full px-1 align-baseline text-xs leading-none font-semibold transition-colors",
        activeRef === reference ? "bg-accent text-on-accent" : "bg-accent-soft text-accent-strong hover:bg-accent hover:text-on-accent",
      )}
    >
      {number ?? "•"}
    </button>
  );
}

function Inlines({ nodes, cite }: { nodes: Inline[]; cite: CiteProps }): ReactNode {
  return nodes.map((node, index) => {
    switch (node.t) {
      case "text":
        return node.v;
      case "br":
        return <br key={index} />;
      case "bold":
        return <strong key={index} className="font-semibold text-ink"><Inlines nodes={node.c} cite={cite} /></strong>;
      case "italic":
        return <em key={index}><Inlines nodes={node.c} cite={cite} /></em>;
      case "strike":
        return <s key={index} className="text-ink-faint"><Inlines nodes={node.c} cite={cite} /></s>;
      case "code":
        return <code key={index} className="rounded bg-surface-sunken px-1 py-0.5 font-mono text-[0.85em] break-words text-ink">{node.v}</code>;
      case "link":
        return (
          <a key={index} href={node.href} target="_blank" rel="noopener noreferrer nofollow" className="font-medium text-accent-strong underline underline-offset-4 break-words">
            <Inlines nodes={node.c} cite={cite} />
          </a>
        );
      case "cite":
        return <CiteChip key={index} reference={node.ref} {...cite} />;
    }
  });
}

// --- lists -----------------------------------------------------------------------------------------------------------------------

function ListView({ list, cite, depth = 0 }: { list: ListBlock; cite: CiteProps; depth?: number }) {
  const leads = list.items.map((item) => splitLead(item.inline));
  // Numbered recommendations whose items open with a bold phrase read best as steps. An item that splits into a title and its explanation shows both;
  // one that is a single sentence with a bold start shows the sentence, so the whole list keeps one look.
  if (list.ordered && depth === 0 && list.items.length > 1 && list.items.every((item, index) => leads[index] !== null || item.inline[0]?.t === "bold")) {
    return (
      <ol className="flex flex-col gap-3">
        {list.items.map((item, index) => {
          const lead = leads[index];
          return (
            <li key={index} className="flex gap-3 rounded-xl border border-border bg-surface-raised p-3.5">
              <span aria-hidden="true" className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent-soft text-sm font-semibold text-accent-strong">
                {index + 1}
              </span>
              <div className="min-w-0">
                {lead ? (
                  <>
                    <p className="font-medium text-ink"><Inlines nodes={lead.lead} cite={cite} /></p>
                    <p className="mt-0.5 text-ink-muted"><Inlines nodes={lead.rest} cite={cite} /></p>
                  </>
                ) : (
                  <p className="text-ink"><Inlines nodes={item.inline} cite={cite} /></p>
                )}
                {item.children && <div className="mt-2"><ListView list={item.children} cite={cite} depth={depth + 1} /></div>}
              </div>
            </li>
          );
        })}
      </ol>
    );
  }
  const Tag = list.ordered ? "ol" : "ul";
  return (
    <Tag className={cn("flex flex-col gap-1.5 pl-5 marker:text-ink-faint", list.ordered ? "list-decimal" : "list-disc", depth > 0 && "mt-1.5")}>
      {list.items.map((item, index) => {
        const lead = leads[index];
        return (
          <li key={index} className="pl-1">
            {lead ? (
              <>
                <strong className="font-semibold text-ink"><Inlines nodes={lead.lead} cite={cite} /></strong>
                {" — "}
                <Inlines nodes={lead.rest} cite={cite} />
              </>
            ) : (
              <Inlines nodes={item.inline} cite={cite} />
            )}
            {item.children && <ListView list={item.children} cite={cite} depth={depth + 1} />}
          </li>
        );
      })}
    </Tag>
  );
}

// --- tables ----------------------------------------------------------------------------------------------------------------------

const EVIDENCE_HEADER = /evidence|source|quote|proof|reference|citation|excerpt/i;

function TableView({ table, cite }: { table: TableBlock; cite: CiteProps }) {
  const columns = table.header.length;
  const evidenceColumn = table.header.findIndex((cell, index) => index > 0 && EVIDENCE_HEADER.test(inlineText(cell)));
  const detailColumns = table.header.map((_, index) => index).filter((index) => index !== 0 && index !== evidenceColumn);
  const [asTable, setAsTable] = useState(columns > 5);

  const toggle = (
    <div className="flex items-center justify-between gap-3">
      <p className="text-xs text-ink-muted">{table.rows.length} {table.rows.length === 1 ? "row" : "rows"}</p>
      <button type="button" aria-pressed={asTable} onClick={() => setAsTable((current) => !current)} className="rounded-md border border-border px-2.5 py-1 text-xs font-medium text-ink-muted transition-colors hover:border-border-strong hover:text-ink">
        {asTable ? "Show as cards" : "Show as table"}
      </button>
    </div>
  );

  if (asTable) {
    return (
      <div className="flex flex-col gap-2">
        {toggle}
        <div className="overflow-x-auto rounded-xl border border-border">
          <table className="w-full min-w-[32rem] border-collapse text-left text-sm">
            <thead className="bg-surface-sunken text-xs text-ink-muted">
              <tr>
                {table.header.map((cell, index) => (
                  <th key={index} scope="col" className="px-3 py-2 font-semibold"><Inlines nodes={cell} cite={cite} /></th>
                ))}
              </tr>
            </thead>
            <tbody>
              {table.rows.map((row, rowIndex) => (
                <tr key={rowIndex} className="border-t border-border align-top">
                  {table.header.map((_, column) => (
                    <td key={column} className="px-3 py-2.5 text-ink-muted">{row[column] ? <Inlines nodes={row[column]} cite={cite} /> : null}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {toggle}
      <ol className="flex flex-col gap-3">
        {table.rows.map((row, rowIndex) => {
          const sources = [...new Set(row.flatMap((cell) => citationsIn(cell)))];
          const evidence = evidenceColumn >= 0 ? row[evidenceColumn] : undefined;
          return (
            <li key={rowIndex} className="flex gap-3 rounded-xl border border-border bg-surface-raised p-4">
              <span aria-hidden="true" className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-surface-sunken text-sm font-semibold text-ink-muted">{rowIndex + 1}</span>
              <div className="flex min-w-0 flex-1 flex-col gap-2.5">
                <h5 className="font-display text-base leading-snug text-ink"><Inlines nodes={row[0] ?? []} cite={cite} /></h5>
                {detailColumns.map((column) =>
                  row[column] && inlineText(row[column]).trim() ? (
                    <div key={column}>
                      {detailColumns.length > 1 && <p className="text-xs font-medium tracking-wide text-ink-muted uppercase">{inlineText(table.header[column])}</p>}
                      <p className="leading-relaxed text-ink"><Inlines nodes={row[column]} cite={cite} /></p>
                    </div>
                  ) : null,
                )}
                {(sources.length > 0 || (evidence && inlineText(evidence).replace(/\[[^\]]*\]/g, "").trim())) && (
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-border pt-2.5">
                    {sources.length > 0 && (
                      <span className="flex items-center text-xs text-ink-muted">
                        {sources.length === 1 ? "Source" : "Sources"}
                        {sources.map((reference) => <CiteChip key={reference} reference={reference} {...cite} />)}
                      </span>
                    )}
                    {evidence && inlineText(evidence).replace(/\[[^\]]*\]/g, "").trim() && (
                      <details data-evidence className="min-w-0 flex-1 basis-full text-sm">
                        <summary className="cursor-pointer text-xs font-medium text-ink-muted select-none hover:text-ink">Show the evidence</summary>
                        <blockquote className="mt-2 border-l-2 border-border-strong pl-3 text-ink-muted"><Inlines nodes={evidence} cite={cite} /></blockquote>
                      </details>
                    )}
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

// --- blocks ----------------------------------------------------------------------------------------------------------------------

const HEADING_STYLE = {
  1: "font-display text-2xl text-ink",
  2: "font-display text-xl text-ink",
  3: "font-display text-lg text-ink",
  4: "text-xs font-semibold tracking-wide text-ink-muted uppercase",
} as const;

function BlockView({ block, cite, first }: { block: Block; cite: CiteProps; first: boolean }) {
  switch (block.t) {
    case "heading":
      return (
        <p id={block.id} role="heading" aria-level={block.level + 2} className={cn("scroll-mt-24", HEADING_STYLE[block.level], !first && "mt-2")}>
          <Inlines nodes={block.inline} cite={cite} />
        </p>
      );
    case "paragraph":
      return <p className="leading-relaxed text-ink"><Inlines nodes={block.inline} cite={cite} /></p>;
    case "list":
      return <ListView list={block} cite={cite} />;
    case "table":
      return <TableView table={block} cite={cite} />;
    case "quote":
      return (
        <blockquote className="flex flex-col gap-3 border-l-2 border-border-strong pl-4 text-ink-muted">
          {block.blocks.map((inner, index) => <BlockView key={index} block={inner} cite={cite} first={false} />)}
        </blockquote>
      );
    case "rule":
      return <hr className="border-border" />;
    case "code":
      return <pre className="overflow-x-auto rounded-lg bg-surface-sunken p-3 font-mono text-xs leading-relaxed text-ink">{block.text}</pre>;
  }
}

export function AnswerBlocks({ blocks, ...cite }: { blocks: Block[] } & CiteProps) {
  return (
    <div className="flex flex-col gap-4 text-[0.95rem]">
      {blocks.map((block, index) => (
        <BlockView key={index} block={block} cite={cite} first={index === 0} />
      ))}
    </div>
  );
}

/** Parses and sets one answer's text. */
export function AnswerText({ content, ...cite }: { content: string } & CiteProps) {
  return <AnswerBlocks blocks={parseAnswer(content)} {...cite} />;
}
