import type { Metadata } from "next";
import Link from "next/link";

import { safeNext } from "@/lib/auth-redirect";
import { Callout } from "@/components/ui/callout";
import { Card } from "@/components/ui/card";
import { LoginForm } from "@/components/auth/login-form";

export const metadata: Metadata = { title: "Sign in" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string; notice?: string }>;
}) {
  const { next, notice } = await searchParams;
  const target = safeNext(next);

  return (
    <div className="mx-auto flex min-h-[calc(100vh-8rem)] max-w-sm flex-col justify-center gap-8 px-6 py-16">
      <div>
        <p className="text-xs font-medium tracking-[0.2em] text-accent uppercase">EIDOS</p>
        <h1 className="mt-3 font-display text-3xl text-ink">Sign in</h1>
        <p className="mt-2 text-sm text-ink-muted">Sign in to your workspace.</p>
      </div>
      {notice === "confirmation_failed" && (
        <Callout tone="warning">
          That confirmation link is invalid or has expired. Sign in if you already confirmed, or create the account again.
        </Callout>
      )}
      <Card className="p-6 sm:p-7">
        <LoginForm next={target} />
      </Card>
      <p className="text-sm text-ink-muted">
        New to EIDOS?{" "}
        <Link href={target === "/missions/new" ? "/signup" : `/signup?next=${encodeURIComponent(target)}`} className="font-medium text-ink underline underline-offset-4">
          Create an account
        </Link>
      </p>
    </div>
  );
}
