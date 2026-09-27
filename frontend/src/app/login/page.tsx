import type { Metadata } from "next";

import { Card } from "@/components/ui/card";
import { LoginForm } from "@/components/auth/login-form";

export const metadata: Metadata = { title: "Sign in" };

function safeNext(value: string | undefined): string {
  // Only ever redirect within this app: an absolute or protocol-relative value is never followed.
  if (value && value.startsWith("/") && !value.startsWith("//")) return value;
  return "/missions/new";
}

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const { next } = await searchParams;

  return (
    <div className="mx-auto flex min-h-[calc(100vh-8rem)] max-w-sm flex-col justify-center gap-8 px-6 py-16">
      <div>
        <p className="text-xs font-medium tracking-[0.2em] text-accent uppercase">EIDOS</p>
        <h1 className="mt-3 font-display text-3xl text-ink">Sign in</h1>
        <p className="mt-2 text-sm text-ink-muted">Sign in with the account your workspace administrator set up for you.</p>
      </div>
      <Card className="p-6 sm:p-7">
        <LoginForm next={safeNext(next)} />
      </Card>
    </div>
  );
}
