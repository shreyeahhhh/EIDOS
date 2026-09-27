"use client";

import { useState, type FormEvent } from "react";

import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Field, fieldInputClassName } from "@/components/ui/field";

/**
 * Signs a real person in through the real Supabase project (`signInWithPassword`) — no fake token, no
 * demo user, no local replacement. On success the Supabase browser client has already written the
 * session into cookies; a full navigation (rather than client-side routing) is used so the server
 * side of the app — middleware, Server Components, the API proxy — reads that session immediately.
 */
export function LoginForm({ next }: { next: string }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    const supabase = createClient();
    const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });

    if (signInError) {
      setError("That email and password were not accepted. Check them and try again.");
      setSubmitting(false);
      return;
    }

    window.location.href = next;
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5" noValidate>
      <Field label="Email">
        {(id, describedBy) => (
          <input
            id={id}
            aria-describedby={describedBy}
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className={fieldInputClassName(false)}
          />
        )}
      </Field>
      <Field label="Password">
        {(id, describedBy) => (
          <input
            id={id}
            aria-describedby={describedBy}
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className={fieldInputClassName(false)}
          />
        )}
      </Field>

      {error && <Callout tone="error">{error}</Callout>}

      <Button type="submit" disabled={submitting} className="mt-1">
        {submitting ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}
