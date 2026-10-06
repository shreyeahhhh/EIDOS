import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SignedInUserProvider, useSignedInUserId } from "./signed-in-user";

function ShowsUser() {
  return <p>{useSignedInUserId()}</p>;
}

describe("the signed-in user a page was rendered for", () => {
  it("is the id the server gave the provider", () => {
    render(
      <SignedInUserProvider userId="aaaaaaaa-0000-0000-0000-000000000001">
        <ShowsUser />
      </SignedInUserProvider>,
    );
    expect(screen.getByText("aaaaaaaa-0000-0000-0000-000000000001")).toBeInTheDocument();
  });

  it("fails loudly outside the provider rather than remembering things under no one", () => {
    vi.spyOn(console, "error").mockImplementation(() => {}); // React reports the thrown render error too
    expect(() => render(<ShowsUser />)).toThrow(/outside SignedInUserProvider/);
    vi.restoreAllMocks();
  });
});
