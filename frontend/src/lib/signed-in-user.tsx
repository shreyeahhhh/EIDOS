"use client";

import { createContext, useContext, type ReactNode } from "react";

/**
 * The signed-in user's id (Supabase's user id, the backend's `user_id`), as the server checked it when it rendered the page
 * (`app/missions/layout.tsx`). What this browser remembers for a user — the workspace id it sends (`lib/tenant.ts`) and the missions it
 * lists (`lib/mission-index.ts`) — is kept under this id, so a second account signing in on the same browser neither sends the first
 * one's workspace nor prunes the first one's missions (D-249). It is a storage key, never authorization: the backend decides everything
 * from the session's own token.
 */
const SignedInUserContext = createContext<string | null>(null);

export function SignedInUserProvider({ userId, children }: { userId: string; children: ReactNode }) {
  return <SignedInUserContext value={userId}>{children}</SignedInUserContext>;
}

/** Throws outside `SignedInUserProvider`: a page that forgot it must fail loudly, not quietly remember things under no one. */
export function useSignedInUserId(): string {
  const userId = useContext(SignedInUserContext);
  if (userId === null) throw new Error("useSignedInUserId is used outside SignedInUserProvider (app/missions/layout.tsx)");
  return userId;
}
