import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PORTFOLIO_ANSWER } from "@/lib/__fixtures__/portfolio-answer";
import type { ExecutionRecord, MissionResult, MissionSummary } from "@/lib/api/types";
import { EXAMPLE_EVENTS, EXAMPLE_EVIDENCE, EXAMPLE_EXECUTION, EXAMPLE_MISSION, EXAMPLE_RESULT } from "@/lib/__fixtures__/example-run";
import { MissionCockpit, type MissionCockpitProps } from "./mission-cockpit";

function cockpit(overrides: Partial<MissionCockpitProps> = {}) {
  const props: MissionCockpitProps = {
    mission: EXAMPLE_MISSION, events: EXAMPLE_EVENTS, execution: EXAMPLE_EXECUTION, result: EXAMPLE_RESULT, resultLoading: false, evidence: EXAMPLE_EVIDENCE,
    starting: false, startError: null, onStart: vi.fn(), ...overrides,
  };
  return { props, ...render(<MissionCockpit {...props} />) };
}

const planGroup = () => screen.getByRole("group", { name: /^Plan version [0-9]+:/ });
const nodes = () => within(planGroup()).getAllByRole("button");
const nodeNamed = (label: RegExp) => within(planGroup()).getByRole("button", { name: label });
const slider = () => screen.getByRole("slider", { name: "Replay position" });
const caption = () => screen.getByTestId("replay-caption");
const tick = (steps: number) => {
  for (let step = 0; step < steps; step += 1) act(() => void vi.advanceTimersByTime(750));
};

describe("MissionCockpit — a finished, verified mission", () => {
  it("opens with the story, the plan as touchable steps, the answer and its sources", () => {
    cockpit();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Review the page at https://example.com/ and tell me what it says.");
    expect(screen.getByText("Done — and the checks passed.")).toBeInTheDocument();
    expect(nodes().map((node) => node.getAttribute("aria-label"))).toEqual(["Research: Done, took 4.8 s", "Architecture: Done, took 5.2 s", "Verify: Done, took 40 ms"]);
    expect(screen.getByRole("heading", { name: "The answer" })).toBeInTheDocument();
    expect(screen.getByText("Passed verification")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /^Sources/ })).toHaveTextContent("Sources (1)");
    expect(screen.getByText("Tried 2 plans")).toBeInTheDocument();
    expect(screen.getByText("Read 1 web page")).toBeInTheDocument();
  });

  it("shows the answer as readable text with numbered source chips, not raw markup", () => {
    cockpit();
    const answer = within(screen.getByTestId("answer-body"));
    expect(answer.getByText("What the page says")).toBeInTheDocument();
    expect(screen.getByTestId("answer-body").textContent).not.toMatch(/\[\[|\*\*|\||###/);
    // the example's table has three rows: each card names its source, and each folded evidence repeats the chip
    expect(answer.getAllByRole("button", { name: "Source 1: Web page, example.com" })).toHaveLength(6);
    expect(answer.getAllByText("Show the evidence")).toHaveLength(3);
  });

  it("keeps everything technical folded away until it is asked for", () => {
    cockpit();
    // the page's own drawer and the inspector's (now open on the last step that ran by default) are both folded
    const technical = screen.getAllByText("Technical details").map((summary) => summary.closest("details")!);
    expect(technical.length).toBeGreaterThanOrEqual(2);
    expect(technical.every((fold) => !fold.hasAttribute("open"))).toBe(true);
    expect(screen.getByText("More about this mission").closest("details")).not.toHaveAttribute("open");
    expect(screen.getByText("How was this checked?").closest("details")).not.toHaveAttribute("open");
    expect(screen.getByText("Every recorded event").closest("details")).not.toHaveAttribute("open");
  });

  it("says plainly what the checks are, and what they are not", () => {
    cockpit();
    const checks = screen.getByText("How was this checked?").closest("details")!;
    expect(checks.textContent).toContain("every source it cites really exists");
    expect(checks.textContent).toMatch(/does not judge whether the answer is correct/);
  });

  it("opens the inspector on the last step that ran when nothing has gone wrong, instead of an empty prompt", () => {
    cockpit();
    expect(screen.queryByText("Pick a step")).toBeNull();
    expect(screen.getByRole("heading", { name: "Verify" })).toBeInTheDocument();
  });

  it("explains the step you pick, and which steps it needs", () => {
    cockpit();
    fireEvent.click(nodeNamed(/^Architecture/));
    expect(screen.getByRole("heading", { name: "Architecture" })).toBeInTheDocument();
    expect(screen.getByText(/Looks at what was found and analyses how it is put together/)).toBeInTheDocument();
    expect(nodeNamed(/^Architecture/)).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Research" })); // the "Needs" chip selects that step
    expect(nodeNamed(/^Research/)).toHaveAttribute("aria-pressed", "true");
  });

  it("lists the sources a step used and opens the reader with the page text", () => {
    cockpit();
    fireEvent.click(nodeNamed(/^Research/));
    fireEvent.click(screen.getByRole("button", { name: "Web page: example.com" }));
    const reader = document.getElementById("source-reader")!;
    expect(within(reader).getByText("Read by: Research, Architecture")).toBeInTheDocument();
    expect(within(reader).getByText(/Title: Example Domain/)).toBeInTheDocument();
    fireEvent.click(within(reader).getByRole("button", { name: "Close" }));
    expect(within(reader).queryByText(/Title: Example Domain/)).toBeNull();
  });

  it("clicking a citation in the answer opens that source, and lights the steps that read it", () => {
    cockpit();
    fireEvent.click(within(screen.getByRole("article")).getAllByRole("button", { name: /^Source 1/ })[0]);
    expect(within(document.getElementById("source-reader")!).getByText(/This is the text EIDOS read/)).toBeInTheDocument();
    expect(nodeNamed(/^Research/).className).toContain("ring-accent");
    expect(nodeNamed(/^Architecture/).className).toContain("ring-accent");
    expect(nodeNamed(/^Verify/).className).not.toContain("ring-accent");
  });

  it("shows only the plain-text note when a source's own text is not kept", () => {
    const withDocument: MissionResult = {
      ...EXAMPLE_RESULT, artifacts: [{ ...EXAMPLE_RESULT.artifacts[0], content: "Your file says so [[doc:notes.txt]]." }],
    };
    cockpit({ result: withDocument, evidence: { audit: { traces: [], cited: [] }, evidence: [] }, execution: { ...EXAMPLE_EXECUTION, steps: [] } });
    fireEvent.click(screen.getByRole("button", { name: /^Source 1: Your document/ }));
    expect(within(document.getElementById("source-reader")!).getByText(/You supplied this document/)).toBeInTheDocument();
  });
});

describe("MissionCockpit — how the page is laid out, so a long answer leaves nothing blank", () => {
  const panel = (name: "plan" | "answer" | "sources") => document.getElementById(`panel-${name}`)!;
  const stage = () => panel("plan").querySelector("section")!;

  /** The nearest element that holds both: where the two stop being siblings in one row. */
  const sharedAncestor = (a: HTMLElement, b: HTMLElement) => {
    let node: HTMLElement | null = a;
    while (node && !node.contains(b)) node = node.parentElement;
    return node!;
  };

  it("keeps the answer out of the plan's band, so its length cannot leave an empty column beside the plan", () => {
    cockpit();
    expect(panel("plan").contains(panel("answer"))).toBe(false);
    // they meet only in the page's own stack, one band under the other — never in a grid row where the taller one leaves the shorter's side empty
    expect(sharedAncestor(panel("plan"), panel("answer")).className).not.toContain("grid-cols");
    expect(panel("plan").className).toContain("xl:grid"); // the flow and the step inspector share the first band (stacked below `xl`)
    expect(panel("plan").contains(screen.getByRole("heading", { name: "Verify" }))).toBe(true);
  });

  it("lets only the sources ride beside the answer, and follow the reader down", () => {
    cockpit();
    expect(sharedAncestor(panel("answer"), panel("sources")).className).toContain("lg:grid-cols"); // one row: the answer and, beside it, the sources
    expect(panel("sources").className).toContain("lg:sticky");
    expect(panel("sources").className).toContain("lg:overflow-y-auto"); // a tall open source can still be scrolled to its end
    expect(panel("answer").className).not.toContain("sticky"); // the long part is never pinned: its bottom could not be reached
  });

  it("gives the flow the whole width while there is no step inspector beside it, and shares the band once there is one", () => {
    const created: MissionSummary = { ...EXAMPLE_MISSION, run_status: "created", mission_status: null, verified: null, counters: null, last_sequence: 0 };
    const { unmount } = cockpit({ mission: created, events: [], execution: null, result: null, evidence: null });
    expect(stage().className).toContain("xl:col-span-2");
    unmount();
    cockpit();
    expect(stage().className).not.toContain("xl:col-span-2");
  });

  it("sets a long answer in the same layout, with its length only in its own band", () => {
    const long: MissionResult = { ...EXAMPLE_RESULT, artifacts: [{ ...EXAMPLE_RESULT.artifacts[0], content: PORTFOLIO_ANSWER }] };
    cockpit({ result: long });
    expect(panel("answer").querySelectorAll("h5")).toHaveLength(3); // one card per row of the answer's table
    expect(panel("plan").querySelector("[data-testid='answer-body']")).toBeNull();
  });

  it("points a finished mission at its answer, which now sits below the plan, and a mission without one at nothing", () => {
    const { unmount } = cockpit();
    const link = screen.getByRole("link", { name: /Read the answer/ });
    expect(link).toHaveAttribute("href", "#panel-answer");
    expect(document.getElementById("panel-answer")).not.toBeNull(); // the link has somewhere to go
    expect(link.parentElement!.className).toMatch(/\bhidden\b.*\blg:block\b/); // shown only where the answer is a section; below `lg` it is a tab
    expect(link.className).not.toMatch(/\bhidden\b/); // (a `hidden` here would lose to the button's own `display`)
    unmount();
    cockpit({ mission: { ...EXAMPLE_MISSION, run_status: "running", mission_status: null }, events: EXAMPLE_EVENTS.slice(0, 11), execution: null, result: null, evidence: null });
    expect(screen.queryByRole("link", { name: /Read the answer/ })).toBeNull();
  });
});

describe("MissionCockpit — sources a step recorded that EIDOS cannot place", () => {
  // as seen on a real mission: the research step's own notes carried a bare number and a tool reference with its "tool:" front cut off
  const NOISE = ["1", "web/fetch:449a47084cc8:example.com-f83a719872"];
  const withNoise: ExecutionRecord = {
    ...EXAMPLE_EXECUTION,
    steps: EXAMPLE_EXECUTION.steps.map((step) => (step.step_id === "p2_research" ? { ...step, citations: [...step.citations, ...NOISE] } : step)),
  };
  const shelf = () => within(document.getElementById("panel-sources")!);

  it("leaves them out of the sources, so the count and the list are only what can be opened", () => {
    cockpit({ execution: withNoise });
    expect(screen.getByRole("heading", { name: /^Sources/ })).toHaveTextContent("Sources (1)");
    expect(shelf().getAllByRole("listitem")).toHaveLength(1);
    expect(shelf().getByRole("button", { name: /example\.com/ })).toBeInTheDocument();
    expect(shelf().queryByText(NOISE[1])).toBeNull();
  });

  it("leaves them out of the step's own list of sources too, so no chip there opens nothing", () => {
    cockpit({ execution: withNoise });
    fireEvent.click(nodeNamed(/^Research/));
    const used = screen.getByText("Sources it used").parentElement!;
    expect(within(used).getAllByRole("button").map((chip) => chip.textContent)).toEqual(["Web page: example.com"]);
  });

  it("hides the step's 'Sources it used' altogether when none of what it recorded can be placed", () => {
    const onlyNoise: ExecutionRecord = { ...withNoise, steps: withNoise.steps.map((step) => (step.step_id === "p2_research" ? { ...step, citations: NOISE } : step)) };
    cockpit({ execution: onlyNoise, result: { ...EXAMPLE_RESULT, artifacts: [{ ...EXAMPLE_RESULT.artifacts[0], content: "Plain answer [[doc:a.txt]]." }] }, evidence: null });
    fireEvent.click(nodeNamed(/^Research/));
    expect(screen.queryByText("Sources it used")).toBeNull();
  });

  it("still lists one the answer itself cites, because its numbered chip has to open something", () => {
    const cites: MissionResult = { ...EXAMPLE_RESULT, artifacts: [{ ...EXAMPLE_RESULT.artifacts[0], content: "It says so [[1]]." }] };
    cockpit({ execution: withNoise, result: cites });
    expect(screen.getByRole("heading", { name: /^Sources/ })).toHaveTextContent("Sources (2)"); // the cited "1" and the recognised page; the other string stays out
    fireEvent.click(within(screen.getByTestId("answer-body")).getByRole("button", { name: /^Source 1/ }));
    expect(within(document.getElementById("source-reader")!).getByText(/isn't available to show here/)).toBeInTheDocument();
  });
});

describe("MissionCockpit — the replay", () => {
  it("scrubbing the strip changes the whole picture to how things stood then, and says what that moment was", () => {
    cockpit();
    fireEvent.change(slider(), { target: { value: "10" } });
    expect(caption()).toHaveTextContent("+9.0 s");
    expect(caption()).toHaveTextContent("Research started.");
    expect(nodes().map((node) => node.getAttribute("aria-label"))).toEqual(["Research: Working", "Architecture: Waiting its turn", "Verify: Waiting its turn"]);
    expect(slider()).toHaveAttribute("aria-valuetext", "Moment 11 of 17: Research started.");
  });

  it("goes back to the first plan on its own while scrubbing before the second was drawn, and the version chips follow", () => {
    cockpit();
    expect(screen.getByRole("button", { name: "Plan 1" })).toBeInTheDocument();
    fireEvent.change(slider(), { target: { value: "3" } });
    expect(screen.queryByRole("button", { name: "Plan 2" })).toBeNull(); // not drawn yet at that moment
    expect(screen.queryByRole("button", { name: "Plan 1" })).toBeNull(); // and with one plan there is nothing to choose between
    expect(nodeNamed(/^Research: Working/)).toBeInTheDocument();
  });

  it("looking at an earlier plan shows how it ended, including what went wrong in the recorded words", () => {
    cockpit();
    fireEvent.click(screen.getByRole("button", { name: "Plan 1" }));
    expect(nodes().map((node) => node.getAttribute("aria-label"))).toEqual(["Research: Didn't work, took 1.9 s", "Architecture: Skipped", "Verify: Skipped"]);
    expect(screen.getByText("Why this plan was replaced:")).toBeInTheDocument();
    expect(screen.getByText(/the research step's model call failed\./)).toBeInTheDocument();
    // the failed step is explained straight away, with the provider's own reason
    expect(screen.getByRole("heading", { name: "Research" })).toBeInTheDocument();
    expect(within(screen.getByRole("alert")).getByText(/HTTP status 429/)).toBeInTheDocument();
    fireEvent.click(nodeNamed(/^Architecture/));
    expect(screen.getByText(/It needs Research, which didn't work/)).toBeInTheDocument();
  });

  describe("playing", () => {
    beforeEach(() => vi.useFakeTimers());
    afterEach(() => vi.useRealTimers());

    it("plays from the start through every moment, then stops at the end", () => {
      cockpit();
      fireEvent.click(screen.getByRole("button", { name: "Play the replay" }));
      expect(screen.getByRole("button", { name: "Pause the replay" })).toBeInTheDocument();
      expect(caption()).toHaveTextContent("Mission created.");
      tick(2);
      expect(caption()).toHaveTextContent("The plan passed EIDOS's checks and is ready to run.");
      tick(20);
      expect(caption()).toHaveTextContent("Finished — the checks passed.");
      expect(screen.getByRole("button", { name: "Play the replay" })).toBeInTheDocument(); // it stopped by itself
    });

    it("pauses where it is", () => {
      cockpit();
      fireEvent.click(screen.getByRole("button", { name: "Play the replay" }));
      tick(2);
      fireEvent.click(screen.getByRole("button", { name: "Pause the replay" }));
      const stopped = caption().textContent;
      tick(5);
      expect(caption().textContent).toBe(stopped);
    });
  });
});

describe("MissionCockpit — a run that is still going", () => {
  const running: MissionSummary = { ...EXAMPLE_MISSION, run_status: "running", mission_status: null, verified: null, counters: null };
  const partial = EXAMPLE_EVENTS.slice(0, 11); // research has just started in plan 2

  it("says what is happening now, follows the newest moment, and shows no answer yet", () => {
    cockpit({ mission: running, events: partial, execution: null, result: null, evidence: null });
    expect(screen.getByText("EIDOS is working on it.")).toBeInTheDocument();
    expect(screen.getByText("Right now: Research.")).toBeInTheDocument();
    expect(screen.getByText("Live")).toBeInTheDocument();
    expect(screen.getByText(/The answer will appear here as soon as it is ready/)).toBeInTheDocument();
    expect(screen.queryByText("Passed verification")).toBeNull();
  });

  it("lets you look back, and one click returns to live", () => {
    cockpit({ mission: running, events: partial, execution: null, result: null, evidence: null });
    fireEvent.change(slider(), { target: { value: "2" } });
    expect(screen.queryByText("Live")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Jump to live" }));
    expect(screen.getByText("Live")).toBeInTheDocument();
    expect(caption()).toHaveTextContent("Research started.");
  });
});

describe("MissionCockpit — a mission that did not work out", () => {
  const failed: MissionSummary = { ...EXAMPLE_MISSION, mission_status: "failed", verified: null, failure_cause: "execution_failed", status_reason: "the model call failed (unavailable)" };
  const failedResult: MissionResult = { mission_status: "failed", verified: null, verdict: null, artifacts: [], failure: { cause: "execution_failed", reason: "the model call failed (unavailable): the provider answered HTTP status 404: The model `x` does not exist" } };

  it("says it failed and why in the recorded words, shows no answer, and offers a way on", () => {
    cockpit({ mission: failed, result: failedResult, evidence: null, execution: null });
    expect(screen.getByText("It didn't work out.")).toBeInTheDocument();
    expect(within(screen.getByRole("article")).getByText(/HTTP status 404: The model `x` does not exist/)).toBeInTheDocument();
    expect(screen.getByText(/Nothing was made up to fill the gap/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "start a new mission" })).toHaveAttribute("href", "/missions/new");
    expect(screen.queryByText("Passed verification")).toBeNull();
  });
});

describe("MissionCockpit — a mission that has not started", () => {
  const created: MissionSummary = { ...EXAMPLE_MISSION, run_status: "created", mission_status: null, verified: null, counters: null, last_sequence: 0 };

  it("explains what will happen and starts when asked", () => {
    const { props } = cockpit({ mission: created, events: [], execution: null, result: null, evidence: null });
    expect(screen.getByText("Ready when you are.")).toBeInTheDocument();
    for (const step of ["Do", "Check"]) expect(screen.getByText(step)).toBeInTheDocument();
    expect(screen.getAllByText("Plan").length).toBeGreaterThan(1); // the explainer card and the tab
    expect(screen.queryByRole("slider")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Start mission" }));
    expect(props.onStart).toHaveBeenCalledTimes(1);
  });

  it("does not offer a second start while one is under way, and shows a start error", () => {
    cockpit({ mission: created, events: [], execution: null, result: null, evidence: null, starting: true, startError: "Too many runs are active." });
    expect(screen.getByRole("button", { name: "Starting…" })).toBeDisabled();
    expect(screen.getByText("Too many runs are active.")).toBeInTheDocument();
  });
});

describe("MissionCockpit — while the run is still being loaded", () => {
  it("says it is loading instead of showing what a mission that has not started looks like", () => {
    cockpit({ events: null, execution: null, result: null, evidence: null, resultLoading: true });
    expect(screen.getByText("Loading how it went…")).toBeInTheDocument();
    expect(screen.queryByText("Check")).toBeNull(); // the "what will happen" cards are for a mission that has not run
    expect(screen.queryByRole("slider")).toBeNull();
    expect(screen.getByText("Looking for the answer…")).toBeInTheDocument();
  });
});

describe("MissionCockpit — on a small screen", () => {
  it("offers the plan, the answer and the sources as tabs, opening on the answer for a finished mission", () => {
    cockpit();
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((tab) => tab.textContent)).toEqual(["Plan", "Answer", "Sources"]);
    expect(screen.getByRole("tab", { name: "Answer" })).toHaveAttribute("aria-selected", "true");
    expect(document.getElementById("panel-plan")!.className).toContain("hidden");
    fireEvent.click(screen.getByRole("tab", { name: "Plan" }));
    expect(screen.getByRole("tab", { name: "Plan" })).toHaveAttribute("aria-selected", "true");
    expect(document.getElementById("panel-plan")!.className).not.toContain("hidden");
    expect(document.getElementById("panel-answer")!.className).toContain("hidden");
  });

  it("moves between the tabs with the arrow keys, Home and End, and keeps only the selected tab in the tab order", () => {
    cockpit();
    const tab = (name: string) => screen.getByRole("tab", { name });
    expect(tab("Answer")).toHaveAttribute("tabindex", "0");
    expect(tab("Plan")).toHaveAttribute("tabindex", "-1");
    fireEvent.keyDown(tab("Answer"), { key: "ArrowRight" });
    expect(tab("Sources")).toHaveAttribute("aria-selected", "true");
    expect(document.activeElement).toBe(tab("Sources"));
    fireEvent.keyDown(tab("Sources"), { key: "ArrowRight" }); // wraps
    expect(tab("Plan")).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(tab("Plan"), { key: "ArrowLeft" }); // wraps back
    expect(tab("Sources")).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(tab("Sources"), { key: "Home" });
    expect(tab("Plan")).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(tab("Plan"), { key: "End" });
    expect(tab("Sources")).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(tab("Sources"), { key: "x" }); // any other key does nothing
    expect(tab("Sources")).toHaveAttribute("aria-selected", "true");
  });

  it("jumps to the sources tab when a citation is tapped", () => {
    cockpit();
    fireEvent.click(within(screen.getByRole("article")).getAllByRole("button", { name: /^Source 1/ })[0]);
    expect(screen.getByRole("tab", { name: "Sources" })).toHaveAttribute("aria-selected", "true");
  });

  it("opens on the plan while a mission has not finished", () => {
    cockpit({ mission: { ...EXAMPLE_MISSION, run_status: "running", mission_status: null }, events: EXAMPLE_EVENTS.slice(0, 11), execution: null, result: null, evidence: null });
    expect(screen.getByRole("tab", { name: "Plan" })).toHaveAttribute("aria-selected", "true");
  });
});

describe("MissionCockpit — the plan canvas", () => {
  it("lights the path through a step and dims the rest while it is in focus", () => {
    cockpit();
    fireEvent.focus(nodeNamed(/^Research/));
    // every step of this plan is on the one path, so none is dimmed; a branching plan would dim the unrelated ones (see the unit test of the layout)
    expect(nodes().every((node) => !node.className.includes("opacity-40"))).toBe(true);
    fireEvent.blur(nodeNamed(/^Research/));
  });

  it("gives every step an accessible name that carries its state, never colour alone", () => {
    cockpit();
    for (const node of nodes()) expect(node.getAttribute("aria-label")).toMatch(/: (Done|Working|Waiting its turn|Didn't work|Skipped|Unsure|Waiting for a person)/);
  });

  it("keeps the source reference exact for the technical record", () => {
    cockpit();
    fireEvent.click(nodeNamed(/^Research/));
    expect(screen.getByText("p2_research")).toBeInTheDocument(); // the step id, in the inspector's own folded technical details
    expect(screen.getByText(/web\/fetch · result · 1523 bytes · 640 ms/)).toBeInTheDocument();
  });
});
