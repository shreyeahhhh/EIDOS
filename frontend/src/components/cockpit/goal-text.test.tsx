import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GoalText } from "./goal-text";

const LONG_URL_GOAL =
  "use this site and identify the key steps for the beginner using sip and investing : https://www.angelone.in/smart-money/stock-market-courses/know-how-to-start-investing-in-the-stock-market?gclsrc=aw.ds&utm_source=google&utm_medium=cpc&utm_campaign=B2C_Search_AI_Max";

afterEach(() => vi.unstubAllGlobals());

/** A browser that can measure: the title is cut off when `cutOff()` says so. */
function browserThatMeasures(cutOff: () => boolean) {
  const observers: (() => void)[] = [];
  class FakeResizeObserver {
    constructor(callback: () => void) {
      observers.push(callback);
    }
    observe() {}
    disconnect() {}
  }
  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockImplementation(() => (cutOff() ? 200 : 100));
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(100);
  return () => act(() => observers.forEach((callback) => callback()));
}

describe("GoalText", () => {
  it("shows the whole goal as the page title, and lets it break anywhere so a web address cannot push the page sideways", () => {
    render(<GoalText goal={LONG_URL_GOAL} />);
    const title = screen.getByRole("heading", { level: 1 });
    expect(title).toHaveTextContent(LONG_URL_GOAL); // all of it is in the page, for a screen reader and for copying
    expect(title.className).toContain("[overflow-wrap:anywhere]");
    expect(title.className).toContain("line-clamp-3"); // only the look is clamped
  });

  it("shows no toggle for a short goal", () => {
    render(<GoalText goal="Review my page" />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByRole("heading", { level: 1 }).className).toContain("line-clamp-3");
  });

  it("offers Read more for a long goal before the browser has measured, and Show less once opened", () => {
    render(<GoalText goal={LONG_URL_GOAL} />); // jsdom cannot measure: a goal over the length it assumes is long still gets the toggle
    const more = screen.getByRole("button", { name: "Read more" });
    expect(more).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(more);
    const less = screen.getByRole("button", { name: "Show less" });
    expect(less).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("heading", { level: 1 }).className).not.toContain("line-clamp-3");
    fireEvent.click(less);
    expect(screen.getByRole("heading", { level: 1 }).className).toContain("line-clamp-3");
    expect(screen.getByRole("button", { name: "Read more" })).toBeInTheDocument();
  });

  it("shows the toggle only when the browser measures that the text really is cut off", () => {
    let cutOff = false;
    const measure = browserThatMeasures(() => cutOff);
    render(<GoalText goal="Short enough to fit on its lines" />);
    measure();
    expect(screen.queryByRole("button")).toBeNull();
    cutOff = true; // the window got narrower: the same text no longer fits
    measure();
    expect(screen.getByRole("button", { name: "Read more" })).toBeInTheDocument();
    cutOff = false; // and wider again
    measure();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("keeps Show less while open, whatever the browser then measures", () => {
    const measure = browserThatMeasures(() => true);
    render(<GoalText goal={LONG_URL_GOAL} />);
    measure();
    fireEvent.click(screen.getByRole("button", { name: "Read more" }));
    measure();
    expect(screen.getByRole("button", { name: "Show less" })).toBeInTheDocument();
  });
});
