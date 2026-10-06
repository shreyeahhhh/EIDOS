import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getStoredTenantId, setStoredTenantId } from "@/lib/tenant";

const signOut = vi.fn();

vi.mock("./sign-out-action", () => ({ signOut: () => signOut() }));

import { SignOutButton } from "./sign-out-button";

const WORKSPACE = "11111111-1111-1111-1111-111111111111";

beforeEach(() => {
  window.localStorage.clear();
  signOut.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("SignOutButton", () => {
  it("forgets the remembered workspace id before the server signs the account out", async () => {
    let storedWhenSigningOut: string | null | undefined;
    signOut.mockImplementation(() => {
      storedWhenSigningOut = getStoredTenantId();
    });
    setStoredTenantId(WORKSPACE);

    render(<SignOutButton />);
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

    await waitFor(() => expect(signOut).toHaveBeenCalledTimes(1));
    expect(storedWhenSigningOut).toBeNull();
    expect(getStoredTenantId()).toBeNull();
  });

  it("still signs out when no workspace id was remembered", async () => {
    render(<SignOutButton />);
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

    await waitFor(() => expect(signOut).toHaveBeenCalledTimes(1));
    expect(getStoredTenantId()).toBeNull();
  });

  it("still signs out when the browser's storage refuses to be touched", async () => {
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });

    render(<SignOutButton />);
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

    await waitFor(() => expect(signOut).toHaveBeenCalledTimes(1));
  });
});
