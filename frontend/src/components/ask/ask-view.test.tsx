import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
const askModels = vi.fn();

vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/lib/signed-in-user", () => ({ useSignedInUserId: () => "user-a" }));
vi.mock("@/lib/api/client", () => ({ askModels: (body: unknown) => askModels(body) }));

import { ApiError } from "@/lib/api/errors";
import type { AskedAnswer, AskResult } from "@/lib/api/types";
import { AskView } from "./ask-view";

const KEY_GEMINI = "key-gemini-0123456789";
const KEY_GROQ = "key-groq-9876543210";
const QUESTION = "Which is the best time for a beginner to buy and sell stocks?";
const NOTE = "These answers are each model's own words, from its own knowledge. EIDOS found no sources, cited none and checked none of it. Treat them as unverified.";

function answer(provider: string, model: string, text: string, extra: Partial<AskedAnswer> = {}): AskedAnswer {
  return { provider, model, ok: true, text, failure: null, elapsed_seconds: 2.1, prompt_tokens: 11, output_tokens: 7, ...extra };
}
function result(...answers: AskedAnswer[]): AskResult {
  return { answers, verified: false, note: NOTE };
}

beforeEach(() => {
  push.mockReset();
  askModels.mockReset();
});

function typeQuestion(text = QUESTION) {
  fireEvent.change(screen.getByLabelText(/what do you want to ask/i), { target: { value: text } });
}
function choose(provider: string, model: string, key: string) {
  fireEvent.click(screen.getByRole("checkbox", { name: new RegExp(provider) }));
  fireEvent.change(screen.getByLabelText(`${provider} model`), { target: { value: model } });
  fireEvent.change(screen.getByLabelText(`${provider} API key`), { target: { value: key } });
}

describe("AskView — one question to several models, side by side", () => {
  it("sends the question as written, once, with each ticked model and its own key, and shows each answer in its own column", async () => {
    askModels.mockResolvedValue(result(answer("gemini", "gemini-test", "Gemini: spread your buying over time."), answer("groq", "groq-test", "Groq: avoid timing the market.")));
    render(<AskView />);
    typeQuestion();
    choose("Google Gemini", " gemini-test ", KEY_GEMINI);
    choose("Groq", "groq-test", KEY_GROQ);
    expect(screen.getByRole("status")).toHaveTextContent("each of the 2 models at the same time");
    fireEvent.click(screen.getByRole("button", { name: "Ask 2 models" }));

    const columns = await screen.findAllByRole("article");
    expect(columns.map((column) => column.getAttribute("aria-label"))).toEqual(["Google Gemini gemini-test", "Groq groq-test"]);
    expect(within(columns[0]).getByTestId("asked-answer")).toHaveTextContent("Gemini: spread your buying over time.");
    expect(within(columns[1]).getByTestId("asked-answer")).toHaveTextContent("Groq: avoid timing the market.");
    expect(askModels).toHaveBeenCalledTimes(1);
    expect(askModels).toHaveBeenCalledWith({
      question: QUESTION,
      models: [{ provider: "gemini", model: "gemini-test", api_key: KEY_GEMINI }, { provider: "groq", model: "groq-test", api_key: KEY_GROQ }],
    });
  });

  it("says before and beside the answers that they are unverified and have no sources, and ranks nothing", async () => {
    askModels.mockResolvedValue(result(answer("gemini", "g", "One answer."), answer("groq", "q", "Another answer.")));
    render(<AskView />);
    typeQuestion();
    choose("Google Gemini", "g", KEY_GEMINI);
    choose("Groq", "q", KEY_GROQ);
    fireEvent.click(screen.getByRole("button", { name: "Ask 2 models" }));
    expect(await screen.findByText("Unverified — these answers have no sources")).toBeInTheDocument();
    expect(screen.getByText(NOTE)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/winner|best answer|verified by|passed verification|score|rank/i);
    expect(screen.getByRole("link", { name: "mission" })).toHaveAttribute("href", "/missions/new"); // the way to get sources behind an answer
  });

  it("shows a model that could not answer in the provider's own words, beside the one that did", async () => {
    askModels.mockResolvedValue(result(answer("gemini", "g", "It answered."), answer("groq", "q", "", { ok: false, text: null, failure: "the provider answered HTTP status 401: Invalid API Key" })));
    render(<AskView />);
    typeQuestion();
    choose("Google Gemini", "g", KEY_GEMINI);
    choose("Groq", "q", KEY_GROQ);
    fireEvent.click(screen.getByRole("button", { name: "Ask 2 models" }));
    const [good, bad] = await screen.findAllByRole("article");
    expect(within(good).getByTestId("asked-answer")).toHaveTextContent("It answered.");
    expect(within(bad).getByText("This model did not answer")).toBeInTheDocument();
    expect(within(bad).getByText(/HTTP status 401: Invalid API Key/)).toBeInTheDocument();
  });

  it("renders an answer written in Markdown as readable text, with no stray symbols", async () => {
    askModels.mockResolvedValue(result(answer("gemini", "g", "**Short answer:** invest a little, often.\n\n- Start small\n- Keep it simple")));
    render(<AskView />);
    typeQuestion();
    choose("Google Gemini", "g", KEY_GEMINI);
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    const body = await screen.findByTestId("asked-answer");
    expect(body.textContent).not.toContain("**");
    expect(within(body).getByText("Short answer:").tagName).toBe("STRONG");
    expect(within(body).getAllByRole("listitem")).toHaveLength(2);
  });

  it("when the button refuses to send, lists every problem beside it, takes the person to the first, and sends nothing", async () => {
    render(<AskView />);
    fireEvent.click(screen.getByRole("checkbox", { name: /Groq/ })); // ticked, but no model, no key, and no question
    const button = screen.getByRole("button", { name: "Ask" });
    fireEvent.click(button);
    const summary = (await screen.findByText("Not sent yet — a few things need fixing")).closest("div")!;
    for (const expected of ["Write your question.", "Groq model:", "Groq API key:"]) expect(summary.textContent, expected).toContain(expected);
    expect(button.compareDocumentPosition(summary) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy();
    await waitFor(() => expect(document.activeElement).toBe(screen.getByLabelText(/what do you want to ask/i)));
    expect(askModels).not.toHaveBeenCalled();
  });

  it("asks for at least one model when none is ticked, and refuses a question that is too long", async () => {
    render(<AskView />);
    typeQuestion("q".repeat(2001));
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    const summary = (await screen.findByText("Not sent yet — a few things need fixing")).closest("div")!;
    expect(summary).toHaveTextContent("Tick at least one model to ask.");
    expect(summary).toHaveTextContent("under 2,000 characters");
    expect(askModels).not.toHaveBeenCalled();
  });

  it("never repeats a key in a message, and keeps no key anywhere in the page text", async () => {
    render(<AskView />);
    typeQuestion();
    choose("Google Gemini", "has space", "bad key 12345678");
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText("Not sent yet — a few things need fixing");
    expect(document.body.textContent).not.toContain("bad key 12345678");
    expect(askModels).not.toHaveBeenCalled();
  });

  it("says what the server said when it refuses, beside the button, and leaves the form as it was", async () => {
    askModels.mockRejectedValue(new ApiError(422, { code: "invalid_request", message: "this service runs missions on its own model and does not accept one of your own" }));
    render(<AskView />);
    typeQuestion();
    choose("Groq", "q", KEY_GROQ);
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    const refusal = (await screen.findByText("This request was refused")).closest("div")!;
    expect(refusal).toHaveTextContent("does not accept one of your own");
    expect((screen.getByLabelText("Groq API key") as HTMLInputElement).value).toBe(KEY_GROQ); // nothing lost: one more try needs no retyping
    expect(screen.getByRole("button", { name: "Ask" })).toBeEnabled();
  });

  it("goes to sign-in when the session has ended", async () => {
    askModels.mockRejectedValue(new ApiError(401, { code: "unauthenticated", message: "Sign in to continue." }));
    render(<AskView />);
    typeQuestion();
    choose("Groq", "q", KEY_GROQ);
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/login?next=/missions/ask"));
  });

  it("shows a waiting state in each column while the models think, and the button cannot be pressed twice", async () => {
    let finish: (value: AskResult) => void = () => {};
    askModels.mockReturnValue(new Promise<AskResult>((resolve) => (finish = resolve)));
    render(<AskView />);
    typeQuestion();
    choose("Google Gemini", "g", KEY_GEMINI);
    choose("Groq", "q", KEY_GROQ);
    fireEvent.click(screen.getByRole("button", { name: "Ask 2 models" }));
    expect(await screen.findByRole("button", { name: "Asking…" })).toBeDisabled();
    expect(screen.getAllByText("Thinking…")).toHaveLength(2);
    finish(result(answer("gemini", "g", "done"), answer("groq", "q", "done too")));
    expect(await screen.findAllByRole("article")).toHaveLength(2);
    expect(screen.queryByText("Thinking…")).toBeNull();
  });
});
