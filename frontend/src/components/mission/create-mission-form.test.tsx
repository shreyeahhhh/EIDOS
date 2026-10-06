import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
const createMission = vi.fn();

vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/lib/signed-in-user", () => ({ useSignedInUserId: () => "user-a" }));
vi.mock("@/lib/api/client", () => ({ createMission: (spec: unknown) => createMission(spec) }));
vi.mock("@/lib/mission-index", () => ({ rememberMission: vi.fn() }));

import { CreateMissionForm } from "./create-mission-form";

function chooseFiles(files: File[]) {
  const input = screen.getByLabelText("Choose text files to attach") as HTMLInputElement;
  fireEvent.change(input, { target: { files } });
}

function file(name: string, text: string): File {
  const made = new File([text], name, { type: "text/plain" });
  // jsdom's File has no text() in every version; the form only needs the contents.
  if (typeof made.text !== "function") Object.defineProperty(made, "text", { value: () => Promise.resolve(text) });
  return made;
}

beforeEach(() => {
  push.mockReset();
  createMission.mockReset();
});

describe("CreateMissionForm — documents", () => {
  it("lists the files chosen, and removes one on request", async () => {
    render(<CreateMissionForm />);
    chooseFiles([file("index.html", "<h1>Hi</h1>"), file("style.css", "body{}")]);

    expect(await screen.findByText("index.html")).toBeInTheDocument();
    expect(screen.getByText("style.css")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Remove index.html" }));
    expect(screen.queryByText("index.html")).not.toBeInTheDocument();
    expect(screen.getByText("style.css")).toBeInTheDocument();
  });

  it("says why a file cannot be used and keeps the ones that can", async () => {
    render(<CreateMissionForm />);
    chooseFiles([file("cv.pdf", "x"), file("notes.md", "# Notes")]);

    expect(await screen.findByRole("alert")).toHaveTextContent("cv.pdf: only text files can be used");
    expect(screen.getByText("notes.md")).toBeInTheDocument();
    expect(screen.queryByText("cv.pdf")).not.toBeInTheDocument();
  });

  it("sends the chosen files as the mission's supplied documents", async () => {
    createMission.mockResolvedValue({ mission_id: "m1", created_at: "2026-10-02T00:00:00Z" });
    render(<CreateMissionForm />);

    fireEvent.change(screen.getByLabelText(/what do you want eidos/i), { target: { value: "Review my page" } });
    fireEvent.click(screen.getByLabelText("Research"));
    chooseFiles([file("index.html", "<h1>Hi</h1>"), file("notes.md", "# Notes")]);
    await screen.findByText("notes.md");
    fireEvent.click(screen.getByRole("button", { name: "Create mission" }));

    await waitFor(() => expect(createMission).toHaveBeenCalledTimes(1));
    expect(createMission.mock.calls[0][0].supplied_documents).toEqual([
      { ref: "doc:index.html", content_type: "text/plain", content: "<h1>Hi</h1>" },
      { ref: "doc:notes.md", content_type: "text/markdown", content: "# Notes" },
    ]);
    await waitFor(() => expect(push).toHaveBeenCalledWith("/missions/m1"));
  });

  it("asks for web access only when the box is ticked: the action and a tool budget, and nothing otherwise", async () => {
    createMission.mockResolvedValue({ mission_id: "m3", created_at: "2026-10-02T00:00:00Z" });
    render(<CreateMissionForm />);
    fireEvent.change(screen.getByLabelText(/what do you want eidos/i), { target: { value: "Review https://example.com/ for faults" } });
    fireEvent.click(screen.getByLabelText("Research"));
    fireEvent.click(screen.getByRole("button", { name: "Create mission" }));
    await waitFor(() => expect(createMission).toHaveBeenCalledTimes(1));
    expect(createMission.mock.calls[0][0].allowed_actions).toEqual([]);
    expect(createMission.mock.calls[0][0].reliability.max_tool_calls).toBeUndefined();
  });

  it("sends the web_fetch action and a budget of three tool calls when the box is ticked", async () => {
    createMission.mockResolvedValue({ mission_id: "m4", created_at: "2026-10-02T00:00:00Z" });
    render(<CreateMissionForm />);
    fireEvent.change(screen.getByLabelText(/what do you want eidos/i), { target: { value: "Review https://example.com/ for faults" } });
    fireEvent.click(screen.getByLabelText("Research"));
    fireEvent.click(screen.getByLabelText("Let EIDOS read the web pages named in my goal"));
    fireEvent.click(screen.getByRole("button", { name: "Create mission" }));
    await waitFor(() => expect(createMission).toHaveBeenCalledTimes(1));
    expect(createMission.mock.calls[0][0].allowed_actions).toEqual(["web_fetch"]);
    expect(createMission.mock.calls[0][0].reliability.max_tool_calls).toBe(3);
  });

  it("tells the visitor, before sending, when the goal names no address to read", () => {
    render(<CreateMissionForm />);
    fireEvent.change(screen.getByLabelText(/what do you want eidos/i), { target: { value: "Review my portfolio" } });
    expect(screen.queryByRole("status")).toBeNull();
    fireEvent.click(screen.getByLabelText("Let EIDOS read the web pages named in my goal"));
    expect(screen.getByRole("status")).toHaveTextContent(/full https:\/\/ address/);
  });

  it("sends no documents when none were chosen", async () => {
    createMission.mockResolvedValue({ mission_id: "m2", created_at: "2026-10-02T00:00:00Z" });
    render(<CreateMissionForm />);
    fireEvent.change(screen.getByLabelText(/what do you want eidos/i), { target: { value: "Goal" } });
    fireEvent.click(screen.getByLabelText("Research"));
    fireEvent.click(screen.getByRole("button", { name: "Create mission" }));

    await waitFor(() => expect(createMission).toHaveBeenCalledTimes(1));
    expect(createMission.mock.calls[0][0].supplied_documents).toEqual([]);
  });
});
