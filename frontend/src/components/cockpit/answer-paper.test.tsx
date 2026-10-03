import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PORTFOLIO_ANSWER, PORTFOLIO_REF } from "@/lib/__fixtures__/portfolio-answer";
import type { MissionResult } from "@/lib/api/types";
import { EXAMPLE_MISSION } from "@/lib/__fixtures__/example-run";
import { AnswerPaper } from "./answer-paper";

function resultWith(content: string): MissionResult {
  return {
    mission_status: "completed", verified: true, verdict: { verdict: "pass", reason: "schema_validity satisfied." }, failure: null,
    artifacts: [{ ref: "artifact:a", content_type: "text/markdown", content, source_refs: [] }],
  };
}

function paper(content = PORTFOLIO_ANSWER, onCite = vi.fn()) {
  const view = render(<AnswerPaper mission={EXAMPLE_MISSION} result={resultWith(content)} loading={false} numbers={new Map([[PORTFOLIO_REF, 1]])} activeRef={null} onCite={onCite} />);
  return { onCite, ...view };
}
const body = () => screen.getByTestId("answer-body");
const cardTitles = () => [...body().querySelectorAll("h5")].map((title) => title.textContent); // one card per table row

describe("AnswerPaper — a real answer from a model", () => {
  it("shows no Markdown symbol anywhere in the text that is read", () => {
    paper();
    const text = body().textContent ?? "";
    for (const symbol of ["**", "|", "###", "`", "[[", "]]", "|---"]) expect(text, symbol).not.toContain(symbol);
    expect(text).toContain("Redundant / duplicated navigation");
    expect(text).toContain("keep a single navigation bar.");
  });

  it("sets the bold title line as a heading and the ### line as a section, with an outline to jump between them", () => {
    paper();
    expect(within(body()).getByRole("heading", { name: /^Findings from the portfolio page/ })).toBeInTheDocument();
    expect(within(body()).getByRole("heading", { name: "Summary & Recommendations" })).toBeInTheDocument();
    const outline = screen.getByRole("navigation", { name: "In this answer" });
    const links = within(outline).getAllByRole("link");
    expect(links).toHaveLength(2);
    expect(links[1]).toHaveAttribute("href", "#summary-recommendations");
    expect(document.getElementById("summary-recommendations")).not.toBeNull();
  });

  it("turns the table into one card per row, each with its title, its observation and its sources visible", () => {
    paper();
    expect(cardTitles()).toEqual(["Redundant / duplicated navigation", "Unclear placeholder", "Unexplained “SM.” label"]);
    expect(within(body()).getByText(/The main navigation items appear twice in the markup/)).toBeInTheDocument();
    expect(within(body()).getByText("About Experience Work").tagName).toBe("CODE"); // code stays code
    expect(screen.getByText("3 rows")).toBeInTheDocument();
    // each card names its source up front, before any evidence is opened
    expect(within(body()).getAllByText("Source")).toHaveLength(3);
  });

  it("lets the cards flow into two columns once the answer itself is wide, so a long table is not a long scroll", () => {
    paper();
    const cards = body().querySelector("h5")!.closest("ol")!;
    expect(cards.className).toContain("@2xl:grid-cols-2"); // by the answer's own width (a container query), not the screen's
    expect(cards.className).toContain("@2xl:items-start"); // opening one card's evidence does not stretch its neighbour
    expect(body().querySelector("[class~='@container']")).not.toBeNull(); // the element whose width that query reads
  });

  it("folds the evidence away on each card, and opens it for one card or for all", () => {
    paper();
    const folds = [...document.querySelectorAll("details[data-evidence]")] as HTMLDetailsElement[];
    expect(folds).toHaveLength(3);
    expect(folds.every((fold) => !fold.open)).toBe(true);
    expect(within(body()).getAllByText("Show the evidence")).toHaveLength(3);

    fireEvent.click(screen.getByRole("button", { name: "Show all evidence" }));
    expect(folds.every((fold) => fold.open)).toBe(true);
    expect(screen.getByRole("button", { name: "Hide all evidence" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Hide all evidence" }));
    expect(folds.every((fold) => !fold.open)).toBe(true);
  });

  it("offers the plain table as a switch, and switches back", () => {
    paper();
    fireEvent.click(screen.getByRole("button", { name: "Show as table" }));
    const table = within(body()).getByRole("table");
    expect(within(table).getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual(["Area", "Observation (potential fault)", "Evidence from the page"]);
    expect(within(table).getAllByRole("row")).toHaveLength(4); // the header and three rows
    expect(table.textContent).not.toContain("**");
    expect(table.textContent).not.toContain("|");
    fireEvent.click(screen.getByRole("button", { name: "Show as cards" }));
    expect(within(body()).queryByRole("table")).toBeNull();
    expect(cardTitles()).toHaveLength(3);
  });

  it("sets the numbered recommendations as steps, the whole list in one style", () => {
    paper();
    const steps = within(body()).getAllByRole("listitem").filter((item) => /duplicated navigation and skill lists|stray UI elements|descriptive/.test(item.textContent ?? ""));
    expect(steps).toHaveLength(3);
    expect(steps[0]).toHaveTextContent("Clean up duplicated navigation and skill lists");
    expect(steps[0]).toHaveTextContent("keep a single navigation bar.");
    expect(steps[2]).toHaveTextContent("Add descriptive alt attributes to all images and icons.");
    expect(steps.every((step) => step.className.includes("rounded-xl"))).toBe(true);
  });

  it("opens a source when its chip is clicked, from a card as from a sentence", () => {
    const { onCite } = paper();
    fireEvent.click(within(body()).getAllByRole("button", { name: "Source 1: Web page, portfolio-g9av.onrender.com" })[0]);
    expect(onCite).toHaveBeenCalledWith(PORTFOLIO_REF);
  });

  it("keeps the text exactly as written one fold away, closed until asked for", () => {
    paper();
    const original = screen.getByText("Original text").closest("details")!;
    expect(original).not.toHaveAttribute("open");
    expect(within(original).getByText(/^\*\*Findings from the portfolio page/)).toBeInTheDocument(); // the raw Markdown, for anyone who wants it
    expect(screen.getByText("How was this checked?").closest("details")).not.toHaveAttribute("open");
  });
});

describe("AnswerPaper — copying", () => {
  const writeText = vi.fn();
  beforeEach(() => {
    writeText.mockReset();
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
  });
  afterEach(() => vi.useRealTimers());

  it("copies the answer as clean text with the sources as numbers, and says it did", async () => {
    writeText.mockResolvedValue(undefined);
    paper();
    fireEvent.click(screen.getByRole("button", { name: "Copy answer" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Copied" })).toBeInTheDocument());
    const copied = writeText.mock.calls[0][0] as string;
    for (const symbol of ["**", "|", "###", "`", "[["]) expect(copied, symbol).not.toContain(symbol);
    expect(copied).toContain("Area: Redundant / duplicated navigation");
    expect(copied).toContain("Evidence from the page: “0%” at the start of the document [1]");
    expect(copied).toContain("1. Clean up duplicated navigation and skill lists – keep a single navigation bar.");
  });

  it("says plainly when it could not copy, and points to the original text", async () => {
    writeText.mockRejectedValue(new Error("denied"));
    paper();
    fireEvent.click(screen.getByRole("button", { name: "Copy answer" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Couldn't copy" })).toBeInTheDocument());
    expect(screen.getByRole("status")).toHaveTextContent("Use Original text below");
  });
});

describe("AnswerPaper — simpler answers", () => {
  it("shows a plain answer without an outline or an evidence control it has no use for", () => {
    paper("Just one paragraph with a **bold** word and a source [[doc:a.txt]].");
    expect(screen.queryByRole("navigation", { name: "In this answer" })).toBeNull();
    expect(screen.queryByRole("button", { name: /evidence/i })).toBeNull();
    expect(within(body()).getByText("bold").tagName).toBe("STRONG");
    expect(screen.getByRole("button", { name: "Copy answer" })).toBeInTheDocument();
  });

  it("sets a two-column table as cards with the detail beneath the title and no evidence fold", () => {
    paper("| Name | Value |\n|---|---|\n| **Port** | 443 |\n| **Host** | example.com |");
    expect(cardTitles()).toEqual(["Port", "Host"]);
    expect(within(body()).getByText("443")).toBeInTheDocument();
    expect(document.querySelectorAll("details[data-evidence]")).toHaveLength(0);
    expect(screen.queryByRole("button", { name: /all evidence/i })).toBeTruthy(); // a table is present, so the control is offered; with nothing to open it is harmless
  });

  it("falls back to the real table when there are many columns", () => {
    paper("| a | b | c | d | e | f |\n|---|---|---|---|---|---|\n| 1 | 2 | 3 | 4 | 5 | 6 |");
    expect(within(body()).getByRole("table")).toBeInTheDocument();
  });

  it("shows a bullet list with bold lead-ins as a tidy list, and nested items beneath", () => {
    paper("- **Name**: Shreya\n- **Role** – engineer\n  - hobby one\n  - hobby two");
    const items = within(body()).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Name — Shreya");
    expect(items[1]).toHaveTextContent("Role — engineer");
    expect(within(items[1]).getAllByRole("listitem").map((item) => item.textContent)).toEqual(["hobby one", "hobby two"]);
  });

  it("never turns a hostile link or markup in an answer into a live element", () => {
    const { container } = paper('[click](javascript:alert(1)) <script>alert(1)</script> [ok](https://example.com/page)');
    expect(container.querySelector("script")).toBeNull();
    const links = within(body()).getAllByRole("link");
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute("href", "https://example.com/page");
    expect(links[0]).toHaveAttribute("rel", "noopener noreferrer nofollow");
    expect(links[0]).toHaveAttribute("target", "_blank");
    expect(body()).toHaveTextContent("click"); // the hostile link is only its text
    expect(body()).toHaveTextContent("<script>alert(1)</script>");
  });
});
