import { describe, expect, it } from "vitest";

import { describeSource, isRecognisedReference, numberCitations, splitCitations } from "./citations";
import { EXAMPLE_EVENTS, EXAMPLE_MISSION, EXAMPLE_PAGE_REF, EXAMPLE_RESULT } from "./__fixtures__/example-run";
import { buildRunModel, formatDuration, formatOffset, plainReason, plansAt, snapshotAt, storyOf } from "./run-model";

const model = buildRunModel(EXAMPLE_EVENTS);
const at = (predicate: (moment: (typeof model.moments)[number]) => boolean) => model.moments.findIndex(predicate);

describe("buildRunModel", () => {
  it("makes one moment per recorded event, in order, each with a plain sentence", () => {
    expect(model.moments).toHaveLength(EXAMPLE_EVENTS.length);
    expect(model.moments.map((m) => m.sequence)).toEqual(EXAMPLE_EVENTS.map((e) => e.event.sequence));
    expect(model.moments[0].text).toBe("Mission created.");
    expect(model.moments[1].text).toBe("EIDOS drew up a plan with 3 steps.");
    expect(model.moments[8].text).toBe("EIDOS drew up a new plan (version 2) with 3 steps.");
    expect(model.moments.every((m) => m.text.length > 0)).toBe(true);
  });

  it("finds every plan version the log generated, with its steps and why it replaced the last", () => {
    expect(model.plans.map((p) => p.version)).toEqual([1, 2]);
    expect(model.plans[1].replanReason).toBe("the research step's model call failed");
    expect(model.plans[1].steps.map((s) => s.label)).toEqual(["Research", "Architecture", "Verify"]);
    expect(model.plans[1].steps[1].dependsOn).toEqual(["p2_research"]);
  });

  it("says what a failed, skipped and replanned moment means without a score or a guess", () => {
    const failed = model.moments.find((m) => m.stepId === "p1_research" && m.kind === "settled")!;
    expect(failed.text).toBe("Research didn't work.");
    expect(failed.tone).toBe("error");
    expect(failed.reason).toContain("429");
    expect(model.moments.find((m) => m.stepId === "p1_verify" && m.kind === "settled")!.text).toBe("The checks were skipped, because an earlier step didn't work.");
    expect(model.moments.find((m) => m.kind === "replan")!.text).toBe("That plan didn't work (execution failed). EIDOS is trying a different approach.");
    expect(model.moments.at(-1)!.text).toBe("Finished — the checks passed.");
    expect(model.moments.find((m) => m.stepId === "p2_verify" && m.kind === "settled")!.text).toBe("The answer passed its checks.");
  });

  it("measures each moment's time from the first event", () => {
    expect(model.moments[0].offsetMs).toBe(0);
    expect(model.moments[4].offsetMs).toBe(5000);
    expect(model.moments.at(-1)!.offsetMs).toBe(20_000);
  });

  it("reads an event type it does not know as a plain title instead of breaking", () => {
    const unknown = buildRunModel([{ ...EXAMPLE_EVENTS[0], payload: { event_type: "SOMETHING_NEW" } }]);
    expect(unknown.moments[0].text).toBe("Something New");
  });

  it("handles a mission with no events at all", () => {
    const empty = buildRunModel([]);
    expect(empty.moments).toEqual([]);
    expect(snapshotAt(empty, -1).plan).toBeNull();
  });
});

describe("snapshotAt", () => {
  it("before anything happened there is no plan and nothing has ended", () => {
    const before = snapshotAt(model, -1);
    expect(before.plan).toBeNull();
    expect(before.moment).toBeNull();
    expect(before.ended).toBe(false);
  });

  it("shows a step running between its start and its end", () => {
    const midResearch = at((m) => m.kind === "started" && m.stepId === "p2_research");
    const snap = snapshotAt(model, midResearch);
    expect(snap.plan!.version).toBe(2);
    expect(snap.steps.p2_research.state).toBe("running");
    expect(snap.steps.p2_analysis.state).toBe("pending");
    expect(snap.moment!.text).toBe("Research started.");
  });

  it("replays the first plan's failure and the skipped steps behind it", () => {
    const afterFailure = at((m) => m.kind === "settled" && m.stepId === "p1_verify");
    const snap = snapshotAt(model, afterFailure);
    expect(snap.plan!.version).toBe(1);
    expect(snap.steps.p1_research).toMatchObject({ state: "failed", durationMs: 1900 });
    expect(snap.steps.p1_research.reason).toContain("429");
    expect(snap.steps.p1_analysis.state).toBe("skipped");
    expect(snap.steps.p1_verify.state).toBe("skipped");
    expect(snap.ended).toBe(false); // a replan is not the end
  });

  it("moves to the new plan only once the log has generated it", () => {
    const justBefore = at((m) => m.kind === "plan" && m.planId === "plan-2") - 1;
    expect(snapshotAt(model, justBefore).plan!.version).toBe(1);
    expect(snapshotAt(model, justBefore + 1).plan!.version).toBe(2);
    expect(plansAt(model, justBefore).map((p) => p.version)).toEqual([1]);
  });

  it("can look back at an earlier plan version at the end of the run, exactly as it ended", () => {
    const end = model.moments.length - 1;
    const first = snapshotAt(model, end, "plan-1");
    expect(first.plan!.version).toBe(1);
    expect(first.steps.p1_research.state).toBe("failed");
    const current = snapshotAt(model, end);
    expect(current.plan!.version).toBe(2);
    expect(Object.values(current.steps).map((s) => s.state)).toEqual(["done", "done", "done"]);
    expect(current.ended).toBe(true);
  });

  it("ignores a requested version the log has not generated yet", () => {
    const early = at((m) => m.kind === "plan") ;
    expect(snapshotAt(model, early, "plan-2").plan!.version).toBe(1);
  });

  it("keeps each step's own recorded time and duration", () => {
    const end = snapshotAt(model, model.moments.length - 1);
    expect(end.steps.p2_research.durationMs).toBe(4800);
    expect(end.steps.p2_research.artifact).toBe("artifact:p2_research");
    expect(end.steps.p2_research.settledAt).not.toBeNull();
  });
});

describe("storyOf", () => {
  const story = (overrides: Partial<typeof EXAMPLE_MISSION>) => storyOf({ ...EXAMPLE_MISSION, ...overrides }, model);

  it("tells a finished, verified mission in one honest sentence", () => {
    const s = story({});
    expect(s).toMatchObject({ headline: "Done — and the checks passed.", tone: "success" });
    expect(s.detail).toContain("every source it cites exists"); // what the checks actually are, not that the answer is right
  });

  it("does not call an unverified mission a success", () => {
    expect(story({ verified: false })).toMatchObject({ headline: "Finished, but not verified.", tone: "warning" });
  });

  it("says a failed mission failed, and what kind of failure, leaving the recorded reason to the step and the answer card", () => {
    const s = story({ mission_status: "failed", verified: null, failure_cause: "execution_failed", status_reason: "execution_failed: the model call failed (unavailable)" });
    expect(s.headline).toBe("It didn't work out.");
    expect(s.detail).toBe("Execution failed");
    expect(s.tone).toBe("error");
    expect(story({ mission_status: "failed", verified: null, failure_cause: null, status_reason: null }).detail).toBeNull();
  });

  it.each([
    ["created", "Ready when you are."],
    ["queued", "Waiting for its turn."],
    ["running", "EIDOS is working on it."],
    ["interrupted", "The run was interrupted."],
    ["rejected", "This mission couldn't start."],
    ["error", "Something went wrong on our side."],
  ] as const)("a %s run reads %s", (run_status, headline) => {
    expect(story({ run_status, mission_status: null }).headline).toBe(headline);
  });

  it("names the step that is working right now", () => {
    const midResearch = buildRunModel(EXAMPLE_EVENTS.slice(0, 11));
    expect(storyOf({ ...EXAMPLE_MISSION, run_status: "running", mission_status: null }, midResearch).detail).toBe("Right now: Research.");
  });
});

describe("plainReason", () => {
  it("drops the backend's machine code from the front of a recorded reason, and nothing else", () => {
    expect(plainReason("execution_failed: the model call failed (unavailable)")).toBe("the model call failed (unavailable)");
    expect(plainReason("verification_failed: schema_validity violated")).toBe("schema_validity violated");
    expect(plainReason("the model call failed: something_else: kept")).toBe("the model call failed: something_else: kept");
    expect(plainReason("execution_failed:")).toBeNull();
    expect(plainReason(null)).toBeNull();
  });

  it("is applied to the reasons the cockpit shows for a replaced plan", () => {
    const events = EXAMPLE_EVENTS.map((e) =>
      "plan" in e.payload && e.payload.plan.version === 2 ? { ...e, payload: { ...e.payload, plan: { ...e.payload.plan, replan_reason: "execution_failed: the research step's model call failed" } } } : e,
    );
    expect(buildRunModel(events).plans[1].replanReason).toBe("the research step's model call failed");
  });
});

describe("formatting", () => {
  it("writes offsets and durations the way a person reads them", () => {
    expect(formatOffset(0)).toBe("+0 ms");
    expect(formatOffset(1200)).toBe("+1.2 s");
    expect(formatOffset(75_000)).toBe("+1 min 15 s");
    expect(formatDuration(null)).toBeNull();
    expect(formatDuration(0)).toBeNull();
    expect(formatDuration(450)).toBe("450 ms");
    expect(formatDuration(4800)).toBe("4.8 s");
  });
});

describe("citations", () => {
  it("cuts an answer into text and numbered citations in order", () => {
    const segments = splitCitations("A [[doc:one.txt]] and B [[doc:two.txt]][[doc:one.txt]].");
    expect(segments).toEqual([
      { type: "text", text: "A " }, { type: "cite", ref: "doc:one.txt" }, { type: "text", text: " and B " },
      { type: "cite", ref: "doc:two.txt" }, { type: "cite", ref: "doc:one.txt" }, { type: "text", text: "." },
    ]);
    expect([...numberCitations(["A [[doc:one.txt]] B [[doc:two.txt]]", "[[doc:one.txt]] [[x]]"])]).toEqual([["doc:one.txt", 1], ["doc:two.txt", 2], ["x", 3]]);
  });

  it("leaves text without citations alone, and does not treat stray brackets as one", () => {
    expect(splitCitations("no citations [here] or [[ ]]")).toEqual([{ type: "text", text: "no citations [here] or " }, { type: "cite", ref: "" }]);
    expect(splitCitations("plain")).toEqual([{ type: "text", text: "plain" }]);
    expect(splitCitations("")).toEqual([]);
  });

  it("says what a source is from its reference alone", () => {
    expect(describeSource(EXAMPLE_PAGE_REF)).toEqual({ kind: "web", label: "example.com", kindLabel: "Web page" });
    expect(describeSource("doc:index.html")).toEqual({ kind: "document", label: "index.html", kindLabel: "Your document" });
    expect(describeSource("evidence:0123456789abcdef")).toMatchObject({ kind: "knowledge" });
    expect(describeSource("artifact:p2_research")).toMatchObject({ kind: "notes" });
    expect(describeSource("tool:docs/search_documents:abc:doc-1")).toEqual({ kind: "other", label: "doc-1", kindLabel: "Tool result" });
    expect(describeSource("whatever")).toEqual({ kind: "other", label: "whatever", kindLabel: "Source" });
  });

  it("recognises every form EIDOS issues, and none it does not", () => {
    for (const ref of [EXAMPLE_PAGE_REF, "doc:index.html", "evidence:0123456789abcdef", "artifact:p2_research", "tool:docs/search_documents:abc:doc-1"]) expect(isRecognisedReference(ref), ref).toBe(true);
    // what a model wrote instead, seen on a real mission: a bare number, and a tool reference with its "tool:" front cut off
    for (const ref of ["1", "b837a4efce56:portfolio-g9av.onrender.com-f83a719872", "web/fetch:b837a4efce56:portfolio-g9av.onrender.com-f83a719872", "", "whatever"]) expect(isRecognisedReference(ref), ref).toBe(false);
  });

  it("numbers the example answer's one source", () => {
    expect([...numberCitations(EXAMPLE_RESULT.artifacts.map((a) => a.content))]).toEqual([[EXAMPLE_PAGE_REF, 1]]);
  });
});
