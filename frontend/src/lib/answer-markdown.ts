/**
 * Reads an answer's Markdown the way a person would want to see it, so no `*`, `|`, `#` or backtick is ever left showing. A small, deliberate
 * subset — what models actually write: headings, paragraphs, nested bullet and numbered lists, GitHub-style tables, quotes, rules, code,
 * and inline **bold**, *italic*, ~~strike~~, `code`, [links](https://…) and `[[reference]]` citations. It builds a plain data model only; nothing
 * here produces HTML, so what an answer contains can never become markup (the renderer builds elements from this model).
 */

export type Inline =
  | { t: "text"; v: string }
  | { t: "bold"; c: Inline[] }
  | { t: "italic"; c: Inline[] }
  | { t: "strike"; c: Inline[] }
  | { t: "code"; v: string }
  | { t: "link"; href: string; c: Inline[] }
  | { t: "cite"; ref: string }
  | { t: "br" };

export interface ListItem {
  inline: Inline[];
  children: ListBlock | null;
}
export interface ListBlock {
  t: "list";
  ordered: boolean;
  items: ListItem[];
}
export interface TableBlock {
  t: "table";
  header: Inline[][];
  rows: Inline[][][];
}
export type Block =
  | { t: "heading"; level: 1 | 2 | 3 | 4; inline: Inline[]; id: string }
  | { t: "paragraph"; inline: Inline[] }
  | ListBlock
  | TableBlock
  | { t: "quote"; blocks: Block[] }
  | { t: "rule" }
  | { t: "code"; text: string };

const MAX_DEPTH = 4;

// --- inline ----------------------------------------------------------------------------------------------------------------------

const isWordChar = (char: string | undefined) => char !== undefined && /[\p{L}\p{N}]/u.test(char);

function pushText(out: Inline[], value: string) {
  if (!value) return;
  const last = out[out.length - 1];
  if (last && last.t === "text") last.v += value;
  else out.push({ t: "text", v: value });
}

/** Parses emphasis, code, links, citations and line breaks. A marker with no partner is dropped (`**` alone shows nothing), never printed as clutter. */
export function parseInline(source: string, depth = 0): Inline[] {
  const out: Inline[] = [];
  let i = 0;
  scan: while (i < source.length) {
    const rest = source.slice(i);
    const char = source[i];

    if (char === "\\" && i + 1 < source.length && /[\\`*_{}[\]()#+\-.!|~>]/.test(source[i + 1])) {
      pushText(out, source[i + 1]);
      i += 2;
      continue;
    }
    if (rest.startsWith("\n")) {
      out.push({ t: "br" });
      i += 1;
      continue;
    }
    if (rest.startsWith("[[")) {
      const end = rest.indexOf("]]");
      if (end > 2 && !rest.slice(2, end).includes("\n")) {
        out.push({ t: "cite", ref: rest.slice(2, end).trim() });
        i += end + 2;
        continue;
      }
    }
    if (char === "`") {
      const end = source.indexOf("`", i + 1);
      if (end > i + 1) {
        out.push({ t: "code", v: source.slice(i + 1, end) });
        i = end + 1;
        continue;
      }
    }
    if (char === "[" && depth < MAX_DEPTH) {
      const link = /^\[([^\]\n]+)\]\(((?:[^()\s]|\([^()\s]*\))+)\)/.exec(rest); // the target may hold one level of balanced parentheses, so `alert(1)` is swallowed whole
      if (link) {
        const safe = /^https?:\/\//i.test(link[2]);
        const inner = parseInline(link[1], depth + 1);
        if (safe) out.push({ t: "link", href: link[2], c: inner });
        else out.push(...inner); // a link that is not plain http(s) is only its text
        i += link[0].length;
        continue;
      }
    }
    if (rest.startsWith("***") && depth < MAX_DEPTH) {
      const close = source.indexOf("***", i + 3);
      if (close > i + 3 && !/\s/.test(source[i + 3]) && !/\s/.test(source[close - 1])) {
        out.push({ t: "bold", c: [{ t: "italic", c: parseInline(source.slice(i + 3, close), depth + 2) }] });
        i = close + 3;
        continue;
      }
    }
    for (const [marker, kind] of [["**", "bold"], ["~~", "strike"], ["*", "italic"], ["_", "italic"]] as const) {
      if (!rest.startsWith(marker) || depth >= MAX_DEPTH) continue;
      const after = source[i + marker.length];
      const before = source[i - 1];
      if (marker === "_" && (isWordChar(before) || !after || /\s/.test(after))) continue; // snake_case and lone underscores are text
      if (marker === "*" && (rest.startsWith("**") || !after || /\s/.test(after))) continue; // a lone * between spaces is a multiplication sign, not emphasis
      if (marker !== "*" && marker !== "_" && (!after || /\s/.test(after))) continue;
      let end = source.indexOf(marker, i + marker.length);
      while (end !== -1 && (marker === "_" && isWordChar(source[end + 1]))) end = source.indexOf(marker, end + 1);
      while (end !== -1 && (/\s/.test(source[end - 1] ?? " ") || (marker === "*" && source[end + 1] === "*"))) {
        end = source.indexOf(marker, end + 1);
      }
      if (end > i + marker.length) {
        const content = parseInline(source.slice(i + marker.length, end), depth + 1);
        out.push({ t: kind, c: content } as Inline);
        i = end + marker.length;
        continue scan;
      }
      if (marker === "**" || marker === "~~") {
        i += marker.length; // an opening bold or strike with nothing to close it: drop the marker
        continue scan;
      }
    }
    pushText(out, char);
    i += 1;
  }
  return out;
}

/** The text of inline content with every marker removed and citations as `[n]` (or `[ref]` when unnumbered). */
export function inlineText(inline: Inline[], numbers?: ReadonlyMap<string, number>): string {
  return inline
    .map((node): string => {
      switch (node.t) {
        case "text":
        case "code":
          return node.v;
        case "br":
          return " ";
        case "cite":
          return `[${numbers?.get(node.ref) ?? "•"}]`;
        case "link":
          return `${inlineText(node.c, numbers)} (${node.href})`;
        default:
          return inlineText(node.c, numbers);
      }
    })
    .join("");
}

/** The citations inside inline content, in order. */
export function citationsIn(inline: Inline[]): string[] {
  return inline.flatMap((node): string[] => {
    if (node.t === "cite") return [node.ref];
    if (node.t === "bold" || node.t === "italic" || node.t === "strike" || node.t === "link") return citationsIn(node.c);
    return [];
  });
}

// --- blocks ----------------------------------------------------------------------------------------------------------------------

const RULE = /^\s*([-*_])(\s*\1){2,}\s*$/;
const HEADING = /^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/;
const FENCE = /^\s*(```|~~~)/;
const LIST_ITEM = /^(\s*)([-*+]|\d{1,3}[.)])\s+(.*)$/;
const TABLE_SEPARATOR = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;

function splitRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  const cells: string[] = [];
  let current = "";
  for (let i = 0; i < trimmed.length; i += 1) {
    if (trimmed[i] === "\\" && trimmed[i + 1] === "|") {
      current += "|";
      i += 1;
    } else if (trimmed[i] === "|") {
      cells.push(current.trim());
      current = "";
    } else {
      current += trimmed[i];
    }
  }
  cells.push(current.trim());
  return cells;
}

function slug(text: string, used: Set<string>): string {
  const base = text.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-+|-+$/g, "").slice(0, 48) || "section";
  let id = base;
  for (let n = 2; used.has(id); n += 1) id = `${base}-${n}`;
  used.add(id);
  return id;
}

/** A paragraph that is nothing but one bold phrase is a heading in everything but its `#`s. */
function boldOnly(inline: Inline[]): Inline[] | null {
  const meaningful = inline.filter((node) => !(node.t === "text" && !node.v.trim()) && node.t !== "br");
  if (meaningful.length === 1 && meaningful[0].t === "bold") return meaningful[0].c;
  if (meaningful.length === 2 && meaningful[0].t === "bold" && meaningful[1].t === "text" && /^[\s:：.]*$/.test(meaningful[1].v)) return meaningful[0].c;
  return null;
}

function listFrom(lines: { indent: number; ordered: boolean; text: string }[]): ListBlock {
  const root: ListBlock = { t: "list", ordered: lines[0].ordered, items: [] };
  const stack: { indent: number; list: ListBlock }[] = [{ indent: lines[0].indent, list: root }];
  for (const line of lines) {
    while (stack.length > 1 && line.indent < stack[stack.length - 1].indent) stack.pop();
    let top = stack[stack.length - 1];
    if (line.indent > top.indent) {
      const parent = top.list.items[top.list.items.length - 1];
      if (parent) {
        const child: ListBlock = { t: "list", ordered: line.ordered, items: [] };
        parent.children = parent.children ?? child;
        stack.push({ indent: line.indent, list: parent.children });
        top = stack[stack.length - 1];
      }
    }
    top.list.items.push({ inline: parseInline(line.text), children: null });
  }
  return root;
}

export function parseAnswer(content: string): Block[] {
  const lines = content.replace(/\r\n?/g, "\n").split("\n");
  const used = new Set<string>();
  return parseBlocks(lines, used);
}

function parseBlocks(lines: string[], used: Set<string>): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: { indent: number; ordered: boolean; text: string }[] = [];

  const flushParagraph = () => {
    if (paragraph.length === 0) return;
    const text = paragraph.map((line, index) => (index < paragraph.length - 1 && / {2,}$/.test(line) ? `${line.trimEnd()}\n` : `${line.trim()} `)).join("").trimEnd();
    const inline = parseInline(text);
    const heading = boldOnly(inline);
    if (heading) blocks.push({ t: "heading", level: 2, inline: heading, id: slug(inlineText(heading), used) });
    else blocks.push({ t: "paragraph", inline });
    paragraph = [];
  };
  const flushList = () => {
    if (list.length > 0) blocks.push(listFrom(list));
    list = [];
  };
  const flush = () => {
    flushParagraph();
    flushList();
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();

    if (FENCE.test(line)) {
      flush();
      const body: string[] = [];
      index += 1;
      while (index < lines.length && !FENCE.test(lines[index])) body.push(lines[index++]);
      blocks.push({ t: "code", text: body.join("\n") });
      continue;
    }
    if (!trimmed) {
      flush();
      continue;
    }
    const heading = HEADING.exec(line);
    if (heading) {
      flush();
      const inline = parseInline(heading[2]);
      blocks.push({ t: "heading", level: Math.min(4, heading[1].length) as 1 | 2 | 3 | 4, inline, id: slug(inlineText(inline), used) });
      continue;
    }
    if (RULE.test(line)) {
      flush();
      blocks.push({ t: "rule" });
      continue;
    }
    if (line.includes("|") && index + 1 < lines.length && TABLE_SEPARATOR.test(lines[index + 1]) && lines[index + 1].includes("-")) {
      flush();
      const header = splitRow(line).map((cell) => parseInline(cell));
      const rows: Inline[][][] = [];
      index += 2;
      while (index < lines.length && lines[index].trim() && lines[index].includes("|")) rows.push(splitRow(lines[index++]).map((cell) => parseInline(cell)));
      index -= 1;
      blocks.push({ t: "table", header, rows });
      continue;
    }
    if (trimmed.startsWith(">")) {
      flush();
      const quoted: string[] = [];
      while (index < lines.length && lines[index].trim().startsWith(">")) quoted.push(lines[index++].trim().replace(/^>\s?/, ""));
      index -= 1;
      blocks.push({ t: "quote", blocks: parseBlocks(quoted, used) });
      continue;
    }
    const item = LIST_ITEM.exec(line);
    if (item) {
      flushParagraph();
      const indent = item[1].replace(/\t/g, "    ").length;
      list.push({ indent, ordered: /\d/.test(item[2]), text: item[3] });
      continue;
    }
    if (list.length > 0 && /^\s+\S/.test(line)) {
      list[list.length - 1].text += ` ${trimmed}`; // a wrapped line of a list item
      continue;
    }
    flushList();
    paragraph.push(line);
  }
  flush();
  return blocks;
}

// --- plain text ------------------------------------------------------------------------------------------------------------------

function listText(list: ListBlock, numbers: ReadonlyMap<string, number> | undefined, depth: number): string[] {
  return list.items.flatMap((item, index) => {
    const marker = list.ordered ? `${index + 1}.` : "-";
    const line = `${"  ".repeat(depth)}${marker} ${inlineText(item.inline, numbers)}`;
    return [line, ...(item.children ? listText(item.children, numbers, depth + 1) : [])];
  });
}

/** The answer as clean plain text for copying: no Markdown symbols, tables as "Label: value" lines, citations as [n]. */
export function plainText(blocks: Block[], numbers?: ReadonlyMap<string, number>): string {
  const parts = blocks.map((block): string => {
    switch (block.t) {
      case "heading":
      case "paragraph":
        return inlineText(block.inline, numbers);
      case "list":
        return listText(block, numbers, 0).join("\n");
      case "table":
        return block.rows
          .map((row) => row.map((cell, column) => `${inlineText(block.header[column] ?? [], numbers) || `Column ${column + 1}`}: ${inlineText(cell, numbers)}`).join("\n"))
          .join("\n\n");
      case "quote":
        return plainText(block.blocks, numbers).split("\n").map((line) => `> ${line}`).join("\n");
      case "rule":
        return "—";
      case "code":
        return block.text;
    }
  });
  return parts.filter((part) => part.length > 0).join("\n\n");
}

/** The headings of an answer, in order, for an outline. */
export function headingsOf(blocks: Block[]): { id: string; text: string; level: number }[] {
  return blocks.flatMap((block) => (block.t === "heading" ? [{ id: block.id, text: inlineText(block.inline), level: block.level }] : []));
}

/**
 * A list item that opens with a bold phrase and then a separator ("**Fix the nav** – keep one copy", "**Name:** Shreya"): the phrase and the rest,
 * so they can be set as a title and its explanation. Bold in the middle of a sentence is not a lead-in and gives `null`.
 */
export function splitLead(inline: Inline[]): { lead: Inline[]; rest: Inline[] } | null {
  const first = inline[0];
  if (!first || first.t !== "bold") return null;
  const rest = inline.slice(1);
  if (rest.length === 0) return null;
  const lead = first.c.map((node) => ({ ...node })) as Inline[];
  const lastLead = lead[lead.length - 1];
  const colonInside = lastLead && lastLead.t === "text" && /[:：]\s*$/.test(lastLead.v);
  if (colonInside && lastLead.t === "text") lastLead.v = lastLead.v.replace(/\s*[:：]\s*$/, "");
  const head = rest[0];
  if (head.t === "text") {
    const separator = /^\s*(?:[–—:：-])\s*/.exec(head.v);
    if (separator) return { lead, rest: [{ t: "text", v: head.v.slice(separator[0].length) }, ...rest.slice(1)] };
  }
  if (!colonInside) return null;
  const next = rest[0];
  return { lead, rest: next.t === "text" ? [{ t: "text", v: next.v.trimStart() }, ...rest.slice(1)] : rest };
}
