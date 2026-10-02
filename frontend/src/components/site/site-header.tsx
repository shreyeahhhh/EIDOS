import Link from "next/link";

import { createClient } from "@/lib/supabase/server";
import { buttonClassName } from "@/components/ui/button";
import { SignOutButton } from "./sign-out-button";

const MARKETING_LINKS = [
  { href: "/#product", label: "Product" },
  { href: "/#how-it-works", label: "How it works" },
  { href: "/#architecture", label: "Architecture" },
];

export async function SiteHeader() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  return (
    <header className="sticky top-0 z-20 border-b border-border bg-[var(--color-surface-elevated)] backdrop-blur-sm">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
        <Link href="/" className="font-display text-lg tracking-tight text-ink">
          EIDOS
        </Link>

        {user ? (
          <nav className="flex items-center gap-4 text-sm sm:gap-6">
            <Link href="/missions" className="text-ink-muted transition-colors hover:text-ink">
              Missions
            </Link>
            <Link href="/missions/new" className="hidden text-ink-muted transition-colors hover:text-ink sm:inline">
              New mission
            </Link>
            <span className="hidden font-mono text-xs text-ink-faint sm:inline">{user.email}</span>
            <SignOutButton />
          </nav>
        ) : (
          <nav className="flex items-center gap-6">
            <div className="hidden items-center gap-6 text-sm text-ink-muted md:flex">
              {MARKETING_LINKS.map((link) => (
                <Link key={link.href} href={link.href} className="transition-colors hover:text-ink">
                  {link.label}
                </Link>
              ))}
            </div>
            <div className="flex items-center gap-4">
              <Link href="/login" className="hidden text-sm font-medium text-ink-muted transition-colors hover:text-ink sm:inline">
                Sign in
              </Link>
              <Link href="/signup" className={buttonClassName("primary", "sm")}>
                Get started →
              </Link>
            </div>
          </nav>
        )}
      </div>
    </header>
  );
}
