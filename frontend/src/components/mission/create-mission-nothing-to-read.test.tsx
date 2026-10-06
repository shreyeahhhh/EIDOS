import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/api/client", () => ({ createMission: vi.fn(), startMission: vi.fn() }));
vi.mock("@/lib/mission-index", () => ({ rememberMission: vi.fn() }));

import { CreateMissionForm } from "./create-mission-form";

const TITLE = "Nothing for EIDOS to read yet";

function typeGoal(text: string) {
  fireEvent.change(screen.getByLabelText(/what do you want eidos/i), { target: { value: text } });
}

function attach(name: string, text: string) {
  const file = new File([text], name, { type: "text/plain" });
  if (typeof file.text !== "function") Object.defineProperty(file, "text", { value: () => Promise.resolve(text) });
  fireEvent.change(screen.getByLabelText("Choose text files to attach"), { target: { files: [file] } });
}

describe("CreateMissionForm — saying so before a mission with nothing to read is sent", () => {
  it("stays quiet on an empty form, and warns once a goal is written with nothing attached and no page to read", () => {
    render(<CreateMissionForm />);
    expect(screen.queryByText(TITLE)).toBeNull();
    typeGoal("Which is the best time for a beginner to buy and sell stocks?"); // the owner's own mission
    expect(screen.getByText(TITLE)).toBeInTheDocument();
    expect(screen.getByText(/does not answer from its own memory/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ask them directly" })).toHaveAttribute("href", "/missions/ask"); // the way to get the models' own answers instead
  });

  it("goes away when a document is attached, and comes back when it is removed", async () => {
    render(<CreateMissionForm />);
    typeGoal("Summarise my notes");
    attach("notes.md", "# Notes");
    await screen.findByText("notes.md");
    expect(screen.queryByText(TITLE)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Remove notes.md" }));
    expect(screen.getByText(TITLE)).toBeInTheDocument();
  });

  it("goes away only when web reading is ticked AND the goal names a page; ticking it with no address still warns", () => {
    render(<CreateMissionForm />);
    typeGoal("Review my portfolio");
    fireEvent.click(screen.getByLabelText(/Let EIDOS read the web pages/));
    expect(screen.getByText(TITLE)).toBeInTheDocument(); // ticked, but no address in the goal: still nothing to read
    typeGoal("Review https://example.com/portfolio for faults");
    expect(screen.queryByText(TITLE)).toBeNull();
    fireEvent.click(screen.getByLabelText(/Let EIDOS read the web pages/)); // untick: an address in the goal is not read unless asked
    expect(screen.getByText(TITLE)).toBeInTheDocument();
  });

  it("only warns: the mission can still be sent", () => {
    render(<CreateMissionForm />);
    typeGoal("A question with nothing attached");
    expect(screen.getByRole("button", { name: "Create mission" })).toBeEnabled();
  });
});
