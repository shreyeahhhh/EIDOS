"use client";

import { clearStoredTenantId } from "@/lib/tenant";
import { Button } from "@/components/ui/button";
import { signOut } from "./sign-out-action";

/**
 * Signing out is a server action, which cannot reach this browser's storage, so the remembered workspace id is forgotten here first:
 * `onSubmit` runs before React hands the form to the action, and the action's redirect then leaves the page.
 */
export function SignOutButton() {
  return (
    <form action={signOut} onSubmit={clearStoredTenantId}>
      <Button type="submit" variant="ghost" size="sm">
        Sign out
      </Button>
    </form>
  );
}
