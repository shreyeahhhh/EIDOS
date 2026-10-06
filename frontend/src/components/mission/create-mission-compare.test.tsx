import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
const createMission = vi.fn();
const startMission = vi.fn();

vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/lib/api/client", () => ({
  createMission: (spec: unknown) => createMission(spec),
  startMission: (id: string, options: unknown) => startMission(id, options),
}));
vi.mock("@/lib/mission-index", () => ({ rememberMission: vi.fn() }));

import { ApiError } from "@/lib/api/errors";
import { CreateMissionForm } from "./create-mission-form";

const KEY_A = "sk-test-AAAAAAAAAAAA";
const KEY_B = "key-gemini-BBBBBBBBBB";

let counter = 0;
beforeEach(() => {
  push.mockReset();
  createMission.mockReset();
  startMission.mockReset();
  counter = 0;
  createMission.mockImplementation(() => {
    counter += 1;
    return Promise.resolve({ mission_id: `0b0d6e4c-5a39-4b0e-8e6e-1d3c6d8f9a0${counter}`, created_at: "2026-10-06T00:00:00Z" });
  });
  startMission.mockResolvedValue({ mission_id: "x", run_status: "queued" });
});

function fillGoal() {
  fireEvent.change(screen.getByLabelText(/what do you want eidos/i), { target: { value: "Review my page" } });
  fireEvent.click(screen.getByLabelText("Research"));
}
function choose(provider: string, model: string, key: string) {
  fireEvent.click(screen.getByRole("checkbox", { name: new RegExp(provider) }));
  fireEvent.change(screen.getByLabelText(`${provider} model`), { target: { value: model } });
  fireEvent.change(screen.getByLabelText(`${provider} API key`), { target: { value: key } });
}

describe("CreateMissionForm — on the person's own models", () => {
  it("offers three providers, hides the fields until one is ticked, and keeps the key in a password field", () => {
    render(<CreateMissionForm />);
    for (const name of ["OpenAI", "Google Gemini", "Groq"]) expect(screen.getByRole("checkbox", { name: new RegExp(name) })).not.toBeChecked();
    expect(screen.queryByLabelText("OpenAI API key")).toBeNull();
    fireEvent.click(screen.getByRole("checkbox", { name: /OpenAI/ }));
    expect(screen.getByLabelText("OpenAI API key")).toHaveAttribute("type", "password");
    expect(screen.getByLabelText("OpenAI API key")).toHaveAttribute("autocomplete", "off");
    expect(screen.getByText(/never saved,/)).toBeInTheDocument(); // the plain statement about the key
  });

  it("with no model ticked, does exactly what it always did: one mission, no start, no key", async () => {
    render(<CreateMissionForm />);
    fillGoal();
    fireEvent.click(screen.getByRole("button", { name: "Create mission" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/missions/0b0d6e4c-5a39-4b0e-8e6e-1d3c6d8f9a01"));
    expect(startMission).not.toHaveBeenCalled();
  });

  it("with one model ticked, starts that mission on it and opens the mission's own page", async () => {
    render(<CreateMissionForm />);
    fillGoal();
    choose("OpenAI", " gpt-4o-mini ", KEY_A);
    fireEvent.click(screen.getByRole("button", { name: "Create mission" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/missions/0b0d6e4c-5a39-4b0e-8e6e-1d3c6d8f9a01"));
    expect(startMission).toHaveBeenCalledWith("0b0d6e4c-5a39-4b0e-8e6e-1d3c6d8f9a01", { model: { provider: "openai", model: "gpt-4o-mini", api_key: KEY_A } });
  });

  it("with two ticked, creates and starts one mission per model and opens the side-by-side page, whose address holds no key", async () => {
    render(<CreateMissionForm />);
    fillGoal();
    choose("OpenAI", "gpt-4o-mini", KEY_A);
    choose("Google Gemini", "gemini-test", KEY_B);
    expect(screen.getByRole("status")).toHaveTextContent("once on each of the 2 models");
    fireEvent.click(screen.getByRole("button", { name: "Compare 2 models" }));

    await waitFor(() => expect(push).toHaveBeenCalledTimes(1));
    expect(createMission).toHaveBeenCalledTimes(2);
    expect(createMission.mock.calls[0][0]).toEqual(createMission.mock.calls[1][0]); // the very same goal, spec and documents on each
    expect(startMission).toHaveBeenNthCalledWith(1, "0b0d6e4c-5a39-4b0e-8e6e-1d3c6d8f9a01", { model: { provider: "openai", model: "gpt-4o-mini", api_key: KEY_A } });
    expect(startMission).toHaveBeenNthCalledWith(2, "0b0d6e4c-5a39-4b0e-8e6e-1d3c6d8f9a02", { model: { provider: "gemini", model: "gemini-test", api_key: KEY_B } });
    const address = push.mock.calls[0][0] as string;
    expect(address.startsWith("/missions/compare?")).toBe(true);
    expect(decodeURIComponent(address)).toContain("0b0d6e4c-5a39-4b0e-8e6e-1d3c6d8f9a01~openai~gpt-4o-mini");
    expect(address).not.toContain(KEY_A);
    expect(address).not.toContain(KEY_B);
  });

  it("checks the model and the key before anything is created, and never repeats the key in its message", async () => {
    render(<CreateMissionForm />);
    fillGoal();
    choose("OpenAI", "has space", "bad key 12345678");
    fireEvent.click(screen.getByRole("button", { name: "Create mission" }));
    expect((await screen.findAllByText(/only letters, digits/)).length).toBe(2); // under its field, and in the summary beside the button
    expect(screen.getAllByText(/no spaces or line breaks/).length).toBe(2);
    expect(document.body.textContent).not.toContain("bad key 12345678");
    expect(createMission).not.toHaveBeenCalled();
    expect(startMission).not.toHaveBeenCalled();
  });

  it("forgets every key once the runs have them", async () => {
    render(<CreateMissionForm />);
    fillGoal();
    choose("OpenAI", "m1", KEY_A);
    choose("Groq", "m2", KEY_B);
    fireEvent.click(screen.getByRole("button", { name: "Compare 2 models" }));
    await waitFor(() => expect(push).toHaveBeenCalled());
    expect(document.body.innerHTML).not.toContain(KEY_A);
    expect((screen.queryByLabelText("OpenAI API key") as HTMLInputElement | null)?.value ?? "").toBe("");
  });

  it("says what the server said when it refuses a model of one's own, and what had already started", async () => {
    startMission.mockResolvedValueOnce({ mission_id: "x", run_status: "queued" });
    startMission.mockRejectedValueOnce(new ApiError(422, { code: "invalid_request", message: "provider must be one of: gemini" }));
    render(<CreateMissionForm />);
    fillGoal();
    choose("OpenAI", "m1", KEY_A);
    choose("Groq", "m2", KEY_B);
    fireEvent.click(screen.getByRole("button", { name: "Compare 2 models" }));
    expect(await screen.findByText("provider must be one of: gemini")).toBeInTheDocument();
    expect(screen.getByText(/A run already started \(OpenAI\)/)).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
    expect(document.body.innerHTML).not.toContain(KEY_A); // the started run holds its key on the server: this page let go of it
  });

  it("when the button refuses to send, says why right beside it — not only up beside the field — and takes the person to the first problem", async () => {
    render(<CreateMissionForm />);
    // the exact situation: two models ticked and keys typed, but no goal and no capability chosen
    choose("OpenAI", "gpt-4o-mini", KEY_A);
    choose("Google Gemini", "gemini-test", KEY_B);
    const button = screen.getByRole("button", { name: "Compare 2 models" });
    fireEvent.click(button);

    const summary = (await screen.findByText("Not sent yet — a few things need fixing")).closest("div")!;
    expect(summary).toHaveTextContent("Write what you want EIDOS to accomplish.");
    expect(summary).toHaveTextContent("Choose at least one capability.");
    // it sits after the model panel and directly before the button the person just pressed
    expect(button.compareDocumentPosition(summary) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy();
    expect(screen.getByRole("group", { name: /Use my own models/ }).compareDocumentPosition(summary) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(createMission).not.toHaveBeenCalled();
    await waitFor(() => expect(document.activeElement).toBe(screen.getByLabelText(/what do you want eidos/i))); // focus goes to the first thing to fix
    expect(document.body.textContent).not.toContain(KEY_A);
  });

  it("reports every problem at once — the goal, the capability and each model and key — not one per click", async () => {
    render(<CreateMissionForm />);
    fireEvent.click(screen.getByRole("checkbox", { name: /OpenAI/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /Groq/ }));
    fireEvent.click(screen.getByRole("button", { name: "Compare 2 models" }));
    const summary = (await screen.findByText("Not sent yet — a few things need fixing")).closest("div")!;
    for (const expected of ["Write what you want EIDOS", "Choose at least one capability", "OpenAI model:", "OpenAI API key:", "Groq model:", "Groq API key:"]) {
      expect(summary.textContent, expected).toContain(expected);
    }
  });

  it("clears the summary on the next try, and a refusal from the server is shown beside the button too", async () => {
    startMission.mockRejectedValueOnce(new ApiError(422, { code: "invalid_request", message: "this service runs missions on its own model and does not accept one of your own" }));
    render(<CreateMissionForm />);
    fireEvent.click(screen.getByRole("button", { name: "Create mission" })); // nothing filled: the summary appears
    expect(await screen.findByText("Not sent yet — a few things need fixing")).toBeInTheDocument();

    fillGoal();
    choose("OpenAI", "m1", KEY_A);
    choose("Groq", "m2", KEY_B);
    const button = screen.getByRole("button", { name: "Compare 2 models" });
    fireEvent.click(button);
    const refusal = (await screen.findByText("This request was refused")).closest("div")!;
    expect(screen.queryByText("Not sent yet — a few things need fixing")).toBeNull();
    expect(refusal).toHaveTextContent("does not accept one of your own");
    expect(button.compareDocumentPosition(refusal) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy(); // beside the button, not at the top of a long form
  });
});
