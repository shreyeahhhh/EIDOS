import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Badge } from "./badge";
import { Callout } from "./callout";

describe("Badge", () => {
  it("renders its content and a tone-specific class", () => {
    render(<Badge tone="error">Failed</Badge>);
    const badge = screen.getByText("Failed");
    expect(badge.className).toMatch(/error/);
  });

  it("defaults to a neutral tone", () => {
    render(<Badge>Created</Badge>);
    expect(screen.getByText("Created").className).toMatch(/ink-muted/);
  });

  it("carries its tone in the label text, not only in color — the dot is a scanning aid, never the only signal", () => {
    const { container } = render(<Badge tone="success">Succeeded</Badge>);
    expect(screen.getByText("Succeeded")).toBeInTheDocument();
    expect(container.querySelector("[aria-hidden='true']")).toBeTruthy();
  });
});

describe("Callout", () => {
  it("marks an error callout as an alert for assistive technology", () => {
    render(<Callout tone="error">Something failed.</Callout>);
    expect(screen.getByRole("alert")).toHaveTextContent("Something failed.");
  });

  it("does not mark a neutral callout as an alert", () => {
    render(<Callout>Informational text.</Callout>);
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
