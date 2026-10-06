import { redirect } from "next/navigation";

import { SignedInUserProvider } from "@/lib/signed-in-user";
import { getSignedInUser } from "@/lib/supabase/server";

/**
 * Tells every page under `/missions` which account is signed in, so what the browser remembers is kept per account (D-249).
 * `proxy.ts` has already sent a visitor with no session to sign in; the redirect here only covers a session that ended in between.
 */
export default async function MissionsLayout({ children }: LayoutProps<"/missions">) {
  const user = await getSignedInUser();
  if (!user) redirect("/login");
  return <SignedInUserProvider userId={user.id}>{children}</SignedInUserProvider>;
}
