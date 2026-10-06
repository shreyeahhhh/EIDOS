import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { MissionResult, MissionSummary } from "@/lib/api/types";
import { EXAMPLE_MISSION, EXAMPLE_PAGE_REF, EXAMPLE_RESULT } from "@/lib/__fixtures__/example-run";

const ID_A = "0b0d6e4c-5a39-4b0e-8e6e-1d3c6d8f9a01";
const ID_B = "0b0d6e4c-5a39-4b0e-8e6e-1d3c6d8f9a02";
const ID_C = "0b0d6e4c-5a39-4b0e-8e6e-1d3c6d8f9a03";

let search = "";
const push = vi.fn();
const getMission = vi.fn();
const getResult = vi.fn();

vi.mock("next/navigation", () => ({ useRouter: () => ({ push }), useSearchParams: () => new URLSearchParams(search) }));
vi.mock("@/lib/signed-in-user", () => ({ useSignedInUserId: () => "user-a" }));
vi.mock("@/lib/api/client", () => ({ getMission: (id: string) => getMission(id), getResult: (id: string) => getResult(id) }));

import { CompareView } from "./compare-view";

function mission(id: string, overrides: Partial<MissionSummary> = {}): MissionSummary {
  return { ...EXAMPLE_MISSION, mission_id: id, ...overrides };
}

function answer(text: string): MissionResult {
  return { ...EXAMPLE_RESULT, artifacts: [{ ...EXAMPLE_RESULT.artifacts[0], content: text }] };
}

beforeEach(() => {
  push.mockReset();
  getMission.mockReset();
  getResult.mockReset();
  search = "";
});

describe("CompareView", () => {
  it("says what the page is for when there is nothing to compare, and links to starting one", () => {
    search = `r=${ID_A}~openai~gpt-x`; // one run is not a comparison
    render(<CompareView />);
    expect(screen.getByText("Nothing to compare here")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "a new mission" })).toHaveAttribute("href", "/missions/new");
    expect(getMission).not.toHaveBeenCalled();
  });

  it("shows each run in its own column with its own answer, and ranks nothing", async () => {
    search = new URLSearchParams([["r", `${ID_A}~openai~gpt-x`], ["r", `${ID_B}~gemini~gemini-y`], ["r", `${ID_C}~groq~openai/gpt-oss-120b`]]).toString();
    getMission.mockImplementation((id: string) => Promise.resolve(mission(id)));
    getResult.mockImplementation((id: string) => Promise.resolve(answer(id === ID_A ? "OpenAI says alpha." : id === ID_B ? "Gemini says beta." : "Groq says gamma.")));
    render(<CompareView />);

    const columns = await screen.findAllByRole("region");
    expect(columns).toHaveLength(3);
    expect(columns.map((column) => column.getAttribute("aria-label"))).toEqual(["OpenAI gpt-x", "Google Gemini gemini-y", "Groq openai/gpt-oss-120b"]);
    const bodyOf = async (column: HTMLElement) => within(await within(column).findByTestId("answer-body")); // (the text also sits in the "Original text" fold)
    expect(await (await bodyOf(columns[0])).findByText("OpenAI says alpha.")).toBeInTheDocument();
    expect(await (await bodyOf(columns[1])).findByText("Gemini says beta.")).toBeInTheDocument();
    expect(await (await bodyOf(columns[2])).findByText("Groq says gamma.")).toBeInTheDocument();
    for (const column of columns) expect(within(column).getByRole("link", { name: /Open the full run/ })).toBeInTheDocument();
    // no ranking, score, "winner" or "best" anywhere on the page, and the plain statement of what the checks are
    expect(document.body.textContent).not.toMatch(/winner|best answer|score|rank/i);
    expect(document.body.textContent).toMatch(/does not judge which answer is better or correct/);
  });

  it("gives each run its own element ids so two answers on one page never share one", async () => {
    search = new URLSearchParams([["r", `${ID_A}~openai~a`], ["r", `${ID_B}~groq~b`]]).toString();
    getMission.mockImplementation((id: string) => Promise.resolve(mission(id)));
    getResult.mockResolvedValue(answer("Same words in both."));
    render(<CompareView />);
    await screen.findAllByText("Same words in both.");
    const ids = [...document.querySelectorAll("[id]")].map((element) => element.id).filter(Boolean);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).toContain("run-openai-answer-title");
    expect(ids).toContain("run-groq-answer-title");
  });

  it("shows how many sources each answer cites, so the runs can be compared on something real", async () => {
    search = new URLSearchParams([["r", `${ID_A}~openai~a`], ["r", `${ID_B}~groq~b`]]).toString();
    getMission.mockImplementation((id: string) => Promise.resolve(mission(id)));
    getResult.mockImplementation((id: string) => Promise.resolve(answer(id === ID_A ? `Cited [[${EXAMPLE_PAGE_REF}]] and [[doc:b.txt]].` : "Cites nothing at all.")));
    render(<CompareView />);
    expect(await screen.findByText("2 sources cited")).toBeInTheDocument();
    expect(screen.getByText("0 sources cited")).toBeInTheDocument();
  });

  it("shows a run that is still going as going, asks for no result yet, and a failed run as failed in its own words", async () => {
    search = new URLSearchParams([["r", `${ID_A}~openai~a`], ["r", `${ID_B}~groq~b`]]).toString();
    getMission.mockImplementation((id: string) =>
      Promise.resolve(id === ID_A ? mission(id, { run_status: "running", mission_status: null, verified: null, counters: null }) : mission(id, { mission_status: "failed", verified: null, failure_cause: "execution_failed" })),
    );
    getResult.mockImplementation((id: string) =>
      id === ID_B
        ? Promise.resolve({ mission_status: "failed", verified: null, verdict: null, artifacts: [], failure: { cause: "execution_failed", reason: "the model call failed (unavailable): the provider answered HTTP status 401: Incorrect API key" } })
        : Promise.reject(new Error("a running mission has no result to ask for")),
    );
    render(<CompareView />);
    expect(await screen.findByText(/still working/)).toBeInTheDocument();
    expect(await screen.findByText(/HTTP status 401: Incorrect API key/)).toBeInTheDocument();
    expect(getResult).not.toHaveBeenCalledWith(ID_A); // the running one is not asked for a result
  });
});
