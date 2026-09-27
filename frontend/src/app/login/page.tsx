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
    <div className="mx-auto flex max-w-sm flex-col gap-8 px-6 py-24">
      <div>
        <h1 className="font-display text-3xl text-ink">Sign in</h1>
        <p className="mt-2 text-sm text-ink-muted">Sign in with the account your workspace administrator set up for you.</p>
      </div>
      <Card>
        <LoginForm next={safeNext(next)} />
      </Card>
    </div>
  );
}
