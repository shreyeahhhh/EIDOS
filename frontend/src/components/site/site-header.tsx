import Link from "next/link";

import { createClient } from "@/lib/supabase/server";
import { buttonClassName } from "@/components/ui/button";
import { SignOutButton } from "./sign-out-button";

export async function SiteHeader() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  return (
    <header className="border-b border-border">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-5">
        <Link href="/" className="font-display text-lg tracking-tight text-ink">
          EIDOS
        </Link>
        <nav className="flex items-center gap-6 text-sm">
          {user ? (
            <>
              <Link href="/missions/new" className="text-ink-muted hover:text-ink">
                New mission
              </Link>
              <span className="hidden text-ink-faint sm:inline">{user.email}</span>
              <SignOutButton />
            </>
          ) : (
            <Link href="/login" className={buttonClassName("primary", "sm")}>
              Sign in
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}
