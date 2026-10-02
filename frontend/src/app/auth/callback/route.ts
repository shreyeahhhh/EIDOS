import { NextResponse, type NextRequest } from "next/server";

import { safeNext } from "@/lib/auth-redirect";
import { createClient } from "@/lib/supabase/server";

/**
 * Where the confirmation link in a sign-up email lands. Supabase sends the visitor here with a one-time
 * `code`; exchanging it writes the session into this app's cookies, exactly as signing in does, and the
 * visitor continues to where they were headed. An invalid or expired code never creates a session: it sends
 * them to the sign-in page with a plain notice.
 */
export async function GET(request: NextRequest) {
  const { searchParams, origin } = request.nextUrl;
  const code = searchParams.get("code");
  const next = safeNext(searchParams.get("next"));

  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) return NextResponse.redirect(new URL(next, origin));
  }

  return NextResponse.redirect(new URL("/login?notice=confirmation_failed", origin));
}
