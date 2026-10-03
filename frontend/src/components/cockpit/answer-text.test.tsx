import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AnswerText } from "./answer-text";

function show(content: string, numbers: [string, number][] = [], activeRef: string | null = null) {
  const onCite = vi.fn();
  const view = render(<AnswerText content={content} numbers={new Map(numbers)} activeRef={activeRef} onCite={onCite} />);
  return { onCite, ...view };
}

describe("AnswerText", () => {
  it("reads headings, paragraphs, bullet and numbered lists as a person would", () => {
    show("# Title\n\nFirst line\nsecond line.\n\n## Part\n\n- one\n- two\n\n1. first\n2. second");
    expect(screen.getByRole("heading", { level: 3, name: "Title" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 4, name: "Part" })).toBeInTheDocument();
    expect(screen.getByText("First line second line.")).toBeInTheDocument(); // wrapped lines join into one paragraph
    expect(within(screen.getAllByRole("list")[0]).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["one", "two"]);
    expect(screen.getAllByRole("list")[1].tagName).toBe("OL");
  });

  it("makes **bold** and `code` and leaves other asterisks and backticks alone", () => {
    show("A **strong** word, some `code`, 2 * 3 and a lone ` tick.");
    expect(screen.getByText("strong").tagName).toBe("STRONG");
    expect(screen.getByText("code").tagName).toBe("CODE");
    expect(screen.getByText(/2 \* 3 and a lone ` tick\./)).toBeInTheDocument();
  });

  it("turns each citation into a numbered chip that names its source and opens it", () => {
    const { onCite } = show("It says so [[tool:web/fetch:449a47084cc8:example.com-f83a719872]] and so [[doc:notes.txt]].", [
      ["tool:web/fetch:449a47084cc8:example.com-f83a719872", 1], ["doc:notes.txt", 2],
    ]);
    const web = screen.getByRole("button", { name: "Source 1: Web page, example.com" });
    const doc = screen.getByRole("button", { name: "Source 2: Your document, notes.txt" });
    expect(web).toHaveTextContent("1");
    expect(doc).toHaveTextContent("2");
    fireEvent.click(doc);
    expect(onCite).toHaveBeenCalledWith("doc:notes.txt");
  });

  it("marks the chip of the source being read", () => {
    show("A [[doc:a.txt]] B [[doc:b.txt]]", [["doc:a.txt", 1], ["doc:b.txt", 2]], "doc:b.txt");
    const classes = (name: RegExp) => screen.getByRole("button", { name }).className.split(/\s+/);
    expect(classes(/Source 2/)).toContain("bg-accent");
    expect(classes(/Source 1/)).not.toContain("bg-accent"); // (it only turns accent-coloured on hover)
  });

  it("shows a citation the answer numbers nowhere as a plain dot chip, still named", () => {
    show("Unnumbered [[doc:x.txt]].");
    expect(screen.getByRole("button", { name: "Source: Your document, x.txt" })).toHaveTextContent("•");
  });

  it("never turns text into markup: HTML in an answer is shown as the plain text it is", () => {
    const { container } = show('<script>alert(1)</script> <img src=x onerror="alert(1)"> **<b>bold</b>** [link](javascript:alert(1))');
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(container).toHaveTextContent('<script>alert(1)</script>');
    expect(container).toHaveTextContent("[link](javascript:alert(1))");
  });

  it("copes with an empty answer and with blank lines only", () => {
    const { container } = show("\n\n   \n");
    expect(container.textContent).toBe("");
  });
});
