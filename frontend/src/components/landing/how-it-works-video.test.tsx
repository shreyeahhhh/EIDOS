import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SCENES, TOTAL_MS, formatClock } from "./how-it-works-scenes";
import { HowItWorksVideo, INITIAL, player } from "./how-it-works-video";

function video() {
  return render(<HowItWorksVideo ctaHref="/signup" ctaLabel="Try it yourself →" />);
}
const frame = () => screen.getByTestId("video-frame");
const current = () => screen.getByTestId("scene-current");
const part = () => screen.getByText(/^Part \d of 6/).textContent;
const control = (name: string) => screen.getByRole("button", { name });
// React listens for the animation-end event under the name this DOM supports — the same test React makes: browsers have `AnimationEvent` and use
// `animationend`; jsdom has none, so React falls back to the prefixed `webkitAnimationEnd` there. Fire whichever React is listening for.
const ANIMATION_END = "AnimationEvent" in window ? "animationend" : "WebkitAnimation" in document.createElement("div").style ? "webkitAnimationEnd" : "animationend";
const clockRunsOut = () => fireEvent(screen.getByTestId("scene-clock"), new Event(ANIMATION_END, { bubbles: true }));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the script", () => {
  it("tells one story in six short parts, about 40 seconds in all", () => {
    expect(SCENES.map((scene) => scene.chapter)).toEqual(["you ask", "it plans", "it works", "plot twist", "receipts", "you get it"]);
    expect(TOTAL_MS).toBe(SCENES.reduce((total, scene) => total + scene.durationMs, 0));
    expect(formatClock(TOTAL_MS)).toBe("0:40");
    expect(formatClock(65_000)).toBe("1:05");
  });

  it("highlights exactly one word of each headline", () => {
    for (const scene of SCENES) expect(scene.headline.split(" ").filter((word) => word.startsWith(scene.mark)), scene.id).toHaveLength(1);
  });

  it("claims only what a mission does today: it says the check is not a check of correctness, and it never mentions learning", () => {
    const all = SCENES.map((scene) => [scene.headline, scene.caption, scene.aside ?? ""].join(" ")).join(" ");
    expect(all).toContain("it checks the receipts, not whether the answer is right");
    expect(all).toContain("no made-up answer to fill the gap");
    expect(all).not.toMatch(/learn/i); // adaptive learning is deferred (D-202)
    expect(all).not.toMatch(/never makes (things|stuff) up|always right|guarantee/i);
  });
});

describe("the clock", () => {
  it("starts a part shown at rest from its top, and carries on a part paused part-way", () => {
    const playing = player(INITIAL, { type: "play", by: "viewer" });
    expect(playing).toMatchObject({ playing: true, animated: true, run: 1 });
    const paused = player(playing, { type: "pause", by: "viewer" });
    expect(player(paused, { type: "play", by: "viewer" }).run).toBe(1); // resumed, not restarted
    const jumped = player(paused, { type: "go", index: 3 });
    expect(jumped).toMatchObject({ index: 3, animated: false }); // chosen while paused: shown at rest
    expect(player(jumped, { type: "play", by: "viewer" })).toMatchObject({ animated: true, run: jumped.run + 1 });
  });

  it("does not let scrolling restart what the viewer paused, or what has ended", () => {
    const held = player(player(INITIAL, { type: "play", by: "view" }), { type: "pause", by: "viewer" });
    expect(player(held, { type: "play", by: "view" }).playing).toBe(false);
    const ended = { ...INITIAL, index: 5, ended: true };
    expect(player(ended, { type: "play", by: "view" })).toBe(ended);
    expect(player(ended, { type: "play", by: "viewer" })).toMatchObject({ index: 0, playing: true, ended: false });
  });

  it("ignores a part's clock running out while paused, and stops at the end", () => {
    expect(player({ ...INITIAL, animated: true }, { type: "sceneEnded" }).index).toBe(0);
    expect(player({ ...INITIAL, index: 5, playing: true, animated: true }, { type: "sceneEnded" })).toMatchObject({ playing: false, ended: true });
    expect(player(INITIAL, { type: "go", index: 99 }).index).toBe(5);
    expect(player(INITIAL, { type: "go", index: -4 }).index).toBe(0);
  });
});

describe("HowItWorksVideo", () => {
  it("opens at rest on the first part, with a play button that says how long it is", () => {
    video();
    expect(frame()).toHaveAttribute("data-paused");
    expect(frame()).toHaveAttribute("data-static");
    expect(frame()).toHaveAttribute("aria-roledescription", "video");
    expect(current().textContent).toContain("you ask a question.");
    expect(control("Play the video (0:40)")).toBeInTheDocument();
    expect(part()).toBe("Part 1 of 6 — you ask");
  });

  it("plays, moves on each time a part's clock runs out, and ends with a way to try it or watch again", () => {
    video();
    fireEvent.click(control("Play the video"));
    expect(frame()).not.toHaveAttribute("data-paused");
    expect(frame()).not.toHaveAttribute("data-static");
    expect(screen.getByTestId("scene-clock")).toHaveStyle({ animationDuration: "6000ms" });
    clockRunsOut();
    expect(part()).toBe("Part 2 of 6 — it plans");
    expect(current().textContent).toContain("EIDOS makes a plan.");
    for (let step = 0; step < 4; step += 1) clockRunsOut();
    expect(part()).toBe("Part 6 of 6 — you get it");
    clockRunsOut();
    expect(screen.getByRole("link", { name: "Try it yourself →" })).toHaveAttribute("href", "/signup");
    fireEvent.click(screen.getByRole("button", { name: "↺ Watch again" }));
    expect(part()).toBe("Part 1 of 6 — you ask");
    expect(frame()).not.toHaveAttribute("data-paused");
  });

  it("holds the part, and its clock, when paused", () => {
    video();
    fireEvent.click(control("Play the video"));
    fireEvent.click(control("Pause the video"));
    expect(frame()).toHaveAttribute("data-paused");
    expect(frame()).not.toHaveAttribute("data-static"); // frozen where it was, not reset
    clockRunsOut();
    expect(part()).toBe("Part 1 of 6 — you ask");
    expect(control("Resume the video")).toBeInTheDocument();
  });

  it("steps, jumps to a part, and shows a part chosen while paused at rest", () => {
    video();
    expect(control("Previous part")).toBeDisabled();
    fireEvent.click(control("Next part"));
    expect(part()).toBe("Part 2 of 6 — it plans");
    fireEvent.click(control("Previous part"));
    expect(part()).toBe("Part 1 of 6 — you ask");
    const chapters = within(screen.getByRole("list", { name: "Parts of the video" }));
    fireEvent.click(chapters.getByRole("button", { name: /receipts/ }));
    expect(part()).toBe("Part 5 of 6 — receipts");
    expect(chapters.getByRole("button", { name: /receipts/ })).toHaveAttribute("aria-current", "step");
    expect(frame()).toHaveAttribute("data-static");
    expect(current().textContent).toContain("Fine print: it checks the receipts, not whether the answer is right.");
    fireEvent.click(chapters.getByRole("button", { name: /you get it/ }));
    expect(control("Next part")).toBeDisabled();
  });

  it("is driven from the keyboard: space plays and pauses, the arrows move between parts", () => {
    video();
    fireEvent.keyDown(frame(), { key: " " });
    expect(frame()).not.toHaveAttribute("data-paused");
    fireEvent.keyDown(frame(), { key: "ArrowRight" });
    expect(part()).toBe("Part 2 of 6 — it plans");
    fireEvent.keyDown(frame(), { key: "ArrowLeft" });
    expect(part()).toBe("Part 1 of 6 — you ask");
    fireEvent.keyDown(frame(), { key: "k" });
    expect(frame()).toHaveAttribute("data-paused");
  });

  it("plays and pauses when the video itself is clicked, but its own buttons do only their own thing", () => {
    video();
    fireEvent.click(control("Play the video (0:40)")); // the button in the frame: plays once, not play-then-pause
    expect(frame()).not.toHaveAttribute("data-paused");
    fireEvent.click(frame());
    expect(frame()).toHaveAttribute("data-paused");
    fireEvent.click(frame());
    expect(frame()).not.toHaveAttribute("data-paused");
  });

  it("shows only the part on screen to assistive technology, and every part as text on request", () => {
    video();
    const hidden = [...frame().querySelectorAll("[aria-hidden='true'][inert]")];
    expect(hidden).toHaveLength(SCENES.length - 1);
    const transcript = within(screen.getByTestId("transcript"));
    expect(transcript.getAllByRole("listitem")).toHaveLength(SCENES.length);
    for (const scene of SCENES) expect(transcript.getByText(scene.caption)).toBeInTheDocument();
    expect(screen.getByText("Read it instead").closest("details")).not.toHaveAttribute("open");
  });
});

describe("HowItWorksVideo — playing by itself", () => {
  function stubObserver() {
    const observers: { callback: IntersectionObserverCallback }[] = [];
    class FakeObserver {
      constructor(callback: IntersectionObserverCallback) {
        observers.push({ callback });
      }
      observe() {}
      disconnect() {}
    }
    vi.stubGlobal("IntersectionObserver", FakeObserver);
    const scrollTo = (ratio: number) =>
      act(() => observers.at(-1)!.callback([{ isIntersecting: ratio > 0, intersectionRatio: ratio } as IntersectionObserverEntry], {} as IntersectionObserver));
    return { scrollTo, watching: () => observers.length };
  }

  it("starts once it is mostly on screen and pauses when it scrolls away, without overruling the viewer", () => {
    const { scrollTo } = stubObserver();
    video();
    scrollTo(0.3);
    expect(frame()).toHaveAttribute("data-paused");
    scrollTo(0.8);
    expect(frame()).not.toHaveAttribute("data-paused");
    scrollTo(0);
    expect(frame()).toHaveAttribute("data-paused");
    scrollTo(0.8);
    expect(frame()).not.toHaveAttribute("data-paused"); // it paused itself, so it resumes itself
    fireEvent.click(control("Pause the video"));
    scrollTo(0);
    scrollTo(0.8);
    expect(frame()).toHaveAttribute("data-paused"); // the viewer paused it: it stays paused
  });

  it("never plays by itself, and shows every part at rest, when the device asks for less motion", () => {
    const { watching } = stubObserver();
    vi.stubGlobal("matchMedia", (query: string) => ({ matches: query.includes("reduce"), addEventListener: vi.fn(), removeEventListener: vi.fn() }));
    video();
    expect(watching()).toBe(0); // it does not even watch the scroll
    expect(frame()).toHaveAttribute("data-static");
    expect(screen.queryByRole("button", { name: /^Play the video/ })).toBeNull();
    expect(screen.getByText(/Autoplay is off because your device asks for less motion/)).toBeInTheDocument();
    fireEvent.keyDown(frame(), { key: " " });
    expect(frame()).toHaveAttribute("data-static");
    fireEvent.click(control("Next part"));
    expect(part()).toBe("Part 2 of 6 — it plans");
  });
});
