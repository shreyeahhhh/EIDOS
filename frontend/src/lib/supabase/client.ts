import { createBrowserClient } from "@supabase/ssr";

/**
 * The browser-side Supabase client. It holds only the public URL and the publishable
 * (anon-scoped) key — both are meant to be visible to the browser and carry no
 * privileged access on their own; `NEXT_PUBLIC_*` variables are inlined at build time.
 *
 * This client never talks to the EIDOS backend directly (no CORS is added to FastAPI,
 * per the approved architecture): it is used only to sign in/out and to keep the
 * session's cookies in sync, so the server-side layer (`lib/supabase/server.ts`,
 * `middleware.ts`) can read the same session and forward its access token to FastAPI.
 */
export function createClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const publishableKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;

  if (!url || !publishableKey) {
    throw new Error(
      "NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY are required (see .env.local.example).",
    );
  }

  return createBrowserClient(url, publishableKey);
}
