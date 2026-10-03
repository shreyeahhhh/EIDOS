import type { Metadata } from "next";
import Link from "next/link";

import { safeNext } from "@/lib/auth-redirect";
import { Card } from "@/components/ui/card";
import { SignupForm } from "@/components/auth/signup-form";

export const metadata: Metadata = { title: "Create account" };

export default async function SignupPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const { next } = await searchParams;
  const target = safeNext(next);

  return (
    <div className="mx-auto flex min-h-[calc(100vh-8rem)] max-w-sm flex-col justify-center gap-8 px-6 py-16">
      <div>
        <p className="text-xs font-medium tracking-[0.2em] text-accent-strong uppercase">EIDOS</p>
        <h1 className="mt-3 font-display text-3xl text-ink">Create your account</h1>
        <p className="mt-2 text-sm text-ink-muted">You get a workspace of your own as soon as you sign in.</p>
      </div>
      <Card className="p-6 sm:p-7">
        <SignupForm next={target} />
      </Card>
      <p className="text-sm text-ink-muted">
        Already have an account?{" "}
        <Link href={target === "/missions/new" ? "/login" : `/login?next=${encodeURIComponent(target)}`} className="font-medium text-ink underline underline-offset-4">
          Sign in
        </Link>
      </p>
    </div>
  );
}
