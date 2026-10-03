import { describe, expect, it } from "vitest";

import { citationsIn, headingsOf, inlineText, parseAnswer, parseInline, plainText, splitLead, type Block, type TableBlock } from "./answer-markdown";

const REF = "tool:web/fetch:b837a4efce56:portfolio-g9av.onrender.com-f83a719872";

// The shape of a real answer a model wrote for this product: a bold line as a title, a three-column table with bold labels, code and citations in its cells, a ### heading,
// a numbered list with bold lead-ins, lines ending in two spaces, and a closing paragraph.
const REAL = `**Findings from the portfolio page (https://portfolio-g9av.onrender.com/)**

| Area | Observation (potential fault) | Evidence from the page |
|------|------------------------------|------------------------|
| **Redundant / duplicated navigation** | The main navigation items appear twice in the markup (\`About Experience Work\`). This can confuse screen‑readers. | “About Experience Work … About Experience Work” [[${REF}]] |
| **Unclear placeholder** | A stray “0%” appears at the very top of the page. | “0%” at the start of the document [[${REF}]] |
| **Unexplained “SM.” label** | The text “SM.” appears under the title. | “SM.” appears right after the title [[${REF}]] |

### Summary & Recommendations

1. **Clean up duplicated navigation and skill lists** – keep a single navigation bar.
2. **Remove or fix stray UI elements** – the “0%” and “SM.” texts should be removed.
3. **Add descriptive \`alt\` attributes** to all images and icons.

Because the source does not contain any CSS, we cannot assess the colours.`;

const blocks = parseAnswer(REAL);
const table = blocks.find((block): block is TableBlock => block.t === "table")!;

describe("parseAnswer — a real answer", () => {
  it("reads it as a title, a table, a heading, a numbered list and a paragraph", () => {
    expect(blocks.map((block) => block.t)).toEqual(["heading", "table", "heading", "list", "paragraph"]);
  });

  it("treats a line that is only bold as the heading it is", () => {
    const heading = blocks[0];
    expect(heading).toMatchObject({ t: "heading", level: 2 });
    expect(inlineText((heading as Extract<Block, { t: "heading" }>).inline)).toBe("Findings from the portfolio page (https://portfolio-g9av.onrender.com/)");
    expect(blocks[2]).toMatchObject({ t: "heading", level: 3 });
  });

  it("reads the table's header, rows and cells, with bold, code and citations inside them", () => {
    expect(table.header.map((cell) => inlineText(cell))).toEqual(["Area", "Observation (potential fault)", "Evidence from the page"]);
    expect(table.rows).toHaveLength(3);
    expect(inlineText(table.rows[0][0])).toBe("Redundant / duplicated navigation");
    expect(table.rows[0][0][0].t).toBe("bold");
    expect(table.rows[0][1].some((node) => node.t === "code" && node.v === "About Experience Work")).toBe(true);
    expect(citationsIn(table.rows[1][2])).toEqual([REF]);
    expect(table.rows.every((row) => row.length === 3)).toBe(true);
  });

  it("reads the numbered recommendations, each with its bold lead-in", () => {
    const list = blocks[3];
    expect(list).toMatchObject({ t: "list", ordered: true });
    if (list.t !== "list") throw new Error("not a list");
    expect(list.items).toHaveLength(3);
    const lead = splitLead(list.items[0].inline)!;
    expect(inlineText(lead.lead)).toBe("Clean up duplicated navigation and skill lists");
    expect(inlineText(lead.rest)).toBe("keep a single navigation bar.");
    // bold followed by plain words is emphasis inside a sentence, not a lead-in: it stays one line
    expect(splitLead(list.items[2].inline)).toBeNull();
    expect(inlineText(list.items[2].inline)).toBe("Add descriptive alt attributes to all images and icons.");
  });

  it("leaves no Markdown symbol anywhere in the text a person reads or copies", () => {
    const text = plainText(blocks, new Map([[REF, 1]]));
    for (const symbol of ["**", "|", "###", "`", "[[", "]]", "- Area"]) expect(text, symbol).not.toContain(symbol);
    expect(text).toContain("Area: Redundant / duplicated navigation");
    expect(text).toContain("Evidence from the page: “0%” at the start of the document [1]");
    expect(text).toContain("1. Clean up duplicated navigation and skill lists – keep a single navigation bar.");
    expect(text).toContain("About Experience Work"); // code is kept as its text
  });

  it("gives each heading a stable, unique anchor for an outline", () => {
    const outline = headingsOf(blocks);
    expect(outline.map((heading) => heading.level)).toEqual([2, 3]);
    expect(new Set(outline.map((heading) => heading.id)).size).toBe(2);
    expect(outline[1].id).toBe("summary-recommendations");
  });
});

describe("parseInline", () => {
  const show = (source: string) => inlineText(parseInline(source));

  it("reads bold, italic, strike and code, and shows only their text", () => {
    expect(show("a **bold** and *italic* and _also italic_ and ~~gone~~ and `code`")).toBe("a bold and italic and also italic and gone and code");
    expect(parseInline("**b**")[0]).toMatchObject({ t: "bold" });
    expect(parseInline("*i*")[0]).toMatchObject({ t: "italic" });
    expect(parseInline("`c`")[0]).toEqual({ t: "code", v: "c" });
  });

  it("nests emphasis and keeps citations inside it", () => {
    const [bold] = parseInline("**see [[doc:a.txt]] and `x`**");
    expect(bold.t).toBe("bold");
    expect(citationsIn([bold])).toEqual(["doc:a.txt"]);
    expect(show("***both***")).toBe("both");
  });

  it("does not mistake arithmetic, snake_case or a lone star for emphasis, and never prints a marker with no partner", () => {
    expect(show("2 * 3 = 6")).toBe("2 * 3 = 6");
    expect(show("use some_snake_case_name here")).toBe("use some_snake_case_name here");
    expect(show("**an opening bold with no end")).toBe("an opening bold with no end");
    expect(show("a ~~tilde pair")).toBe("a tilde pair");
    expect(show("5 stars * * * *")).toContain("5 stars");
  });

  it("honours a backslash escape", () => {
    expect(show("a \\*literal\\* star and a \\| pipe")).toBe("a *literal* star and a | pipe");
  });

  it("makes a link only of plain http(s), and otherwise shows just its text", () => {
    expect(parseInline("[site](https://example.com/a)")[0]).toMatchObject({ t: "link", href: "https://example.com/a" });
    for (const hostile of ["[x](javascript:alert(1))", "[x](data:text/html,<b>)", "[x](//evil.example)", "[x](file:///etc/passwd)"]) {
      const nodes = parseInline(hostile);
      expect(nodes.some((node) => node.t === "link"), hostile).toBe(false);
      expect(inlineText(nodes)).toBe("x");
    }
  });

  it("never turns text into markup: HTML stays text", () => {
    expect(show('<script>alert(1)</script> <img src=x onerror="alert(1)">')).toBe('<script>alert(1)</script> <img src=x onerror="alert(1)">');
  });

  it("names a citation, trimmed, and ignores an unclosed or empty one", () => {
    expect(citationsIn(parseInline("a [[ doc:a.txt ]] b"))).toEqual(["doc:a.txt"]);
    expect(citationsIn(parseInline("a [[unclosed"))).toEqual([]);
    expect(show("a [[unclosed")).toBe("a [[unclosed");
  });

  it("is bounded: deeply nested emphasis cannot run away", () => {
    const nested = "*".repeat(40) + "x" + "*".repeat(40);
    expect(() => parseInline(nested)).not.toThrow();
  });
});

describe("parseAnswer — block shapes", () => {
  it("reads nested bullet and numbered lists by their indentation", () => {
    const [list] = parseAnswer("- one\n  - one a\n  - one b\n- two\n  1. two first\n- three");
    if (list.t !== "list") throw new Error("not a list");
    expect(list.items.map((item) => inlineText(item.inline))).toEqual(["one", "two", "three"]);
    expect(list.items[0].children!.items.map((item) => inlineText(item.inline))).toEqual(["one a", "one b"]);
    expect(list.items[1].children!.ordered).toBe(true);
    expect(list.items[2].children).toBeNull();
  });

  it("reads * and + bullets and 1) numbering the same way", () => {
    const [stars, plus, paren] = ["* a\n* b", "+ a\n+ b", "1) a\n2) b"].map((source) => parseAnswer(source)[0]);
    expect(stars).toMatchObject({ t: "list", ordered: false });
    expect(plus).toMatchObject({ t: "list", ordered: false });
    expect(paren).toMatchObject({ t: "list", ordered: true });
  });

  it("joins a wrapped list item and a wrapped paragraph, and keeps a deliberate line break", () => {
    const [list] = parseAnswer("- one that\n  wraps\n- two");
    if (list.t !== "list") throw new Error("not a list");
    expect(inlineText(list.items[0].inline)).toBe("one that wraps");
    const [paragraph] = parseAnswer("first line  \nsecond line\nthird");
    if (paragraph.t !== "paragraph") throw new Error("not a paragraph");
    expect(paragraph.inline.some((node) => node.t === "br")).toBe(true);
    expect(inlineText(paragraph.inline)).toBe("first line second line third");
  });

  it("reads #-headings of every depth, with a closing run of # removed", () => {
    const parsed = parseAnswer("# A\n## B ##\n### C\n#### D\n##### E");
    expect(parsed.map((block) => (block.t === "heading" ? [block.level, inlineText(block.inline)] : null))).toEqual([[1, "A"], [2, "B"], [3, "C"], [4, "D"], [4, "E"]]);
  });

  it("reads a rule, a quote and a code block", () => {
    const parsed = parseAnswer("above\n\n---\n\n> quoted **text**\n> more\n\n```js\nconst a = 1 * 2;\n```\n\nbelow");
    expect(parsed.map((block) => block.t)).toEqual(["paragraph", "rule", "quote", "code", "paragraph"]);
    expect(parsed[3]).toEqual({ t: "code", text: "const a = 1 * 2;" });
    const quote = parsed[2];
    if (quote.t !== "quote") throw new Error("not a quote");
    expect(inlineText((quote.blocks[0] as Extract<Block, { t: "paragraph" }>).inline)).toBe("quoted text more");
  });

  it("reads a table without outer pipes, with escaped pipes, short rows and alignment colons", () => {
    const [parsed] = parseAnswer("A | B | C\n:--- | :---: | ---:\none | two \\| pipe\nx | y | z");
    if (parsed.t !== "table") throw new Error("not a table");
    expect(parsed.header.map((cell) => inlineText(cell))).toEqual(["A", "B", "C"]);
    expect(parsed.rows.map((row) => row.map((cell) => inlineText(cell)))).toEqual([["one", "two | pipe"], ["x", "y", "z"]]);
  });

  it("does not mistake a lone pipe or a line of dashes for a table", () => {
    expect(parseAnswer("a | b").map((block) => block.t)).toEqual(["paragraph"]);
    expect(parseAnswer("a | b\nnot a separator").map((block) => block.t)).toEqual(["paragraph"]);
  });

  it("gives an empty answer, and one of only blank lines, no blocks", () => {
    expect(parseAnswer("")).toEqual([]);
    expect(parseAnswer("\n\n   \n")).toEqual([]);
  });

  it("makes anchors unique when two headings read alike", () => {
    const ids = headingsOf(parseAnswer("## Same\n\n## Same\n\n## Same")).map((heading) => heading.id);
    expect(new Set(ids).size).toBe(3);
  });

  it("copes with windows line endings", () => {
    expect(parseAnswer("# T\r\n\r\n- a\r\n- b\r\n").map((block) => block.t)).toEqual(["heading", "list"]);
  });
});

describe("splitLead", () => {
  const lead = (source: string) => {
    const split = splitLead(parseInline(source));
    return split ? [inlineText(split.lead), inlineText(split.rest)] : null;
  };

  it("splits a bold title from its explanation after a dash, an en dash, a colon or one inside the bold", () => {
    expect(lead("**Title** – explanation")).toEqual(["Title", "explanation"]);
    expect(lead("**Title** - explanation")).toEqual(["Title", "explanation"]);
    expect(lead("**Title**: explanation")).toEqual(["Title", "explanation"]);
    expect(lead("**Title:** explanation")).toEqual(["Title", "explanation"]);
  });

  it("leaves alone bold that is merely part of a sentence, or is the whole item", () => {
    expect(lead("**Bold** then more words")).toBeNull();
    expect(lead("plain **bold** later")).toBeNull();
    expect(lead("**Only bold**")).toBeNull();
  });
});

describe("plainText", () => {
  it("writes lists, quotes and rules as readable plain text", () => {
    const text = plainText(parseAnswer("# T\n\n- a **b**\n  - c\n\n> q\n\n---\n\n`x`"));
    expect(text).toBe("T\n\n- a b\n  - c\n\n> q\n\n—\n\nx");
  });

  it("writes an unnumbered citation as a dot", () => {
    expect(plainText(parseAnswer("see [[doc:a.txt]]"))).toBe("see [•]");
  });
});
