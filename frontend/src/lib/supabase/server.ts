import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

/**
 * The server-side Supabase client, for Server Components, Route Handlers and Server
 * Actions. It reads the visitor's own session from their request cookies — the same
 * publishable key as the browser client, never a service-role credential — so it can
 * only ever act as the signed-in user, never as an administrator.
 *
 * Writing cookies from a Server Component is a no-op by design (Next.js forbids it
 * outside a Server Action or Route Handler); `middleware.ts` is what actually refreshes
 * an expiring session on every request, so that omission here is harmless.
 */
export async function createClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const publishableKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;

  if (!url || !publishableKey) {
    throw new Error(
      "NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY are required (see .env.local.example).",
    );
  }

  const cookieStore = await cookies();

  return createServerClient(url, publishableKey, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          for (const { name, value, options } of cookiesToSet) {
            cookieStore.set(name, value, options);
          }
        } catch {
          // Called from a Server Component during rendering: Next.js refuses the write.
          // middleware.ts refreshes the session cookie on the next request instead.
        }
      },
    },
  });
}

/** The signed-in user's access token (a Supabase-issued JWT), or `null` if there is no session. */
export async function getAccessToken(): Promise<string | null> {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return session?.access_token ?? null;
}
