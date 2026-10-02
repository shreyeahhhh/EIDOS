"use client";

import { useState, type FormEvent } from "react";

import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Field, fieldInputClassName } from "@/components/ui/field";

const MIN_PASSWORD_LENGTH = 8;

function messageFor(error: unknown): string {
  const code = typeof error === "object" && error !== null && "code" in error ? String((error as { code: unknown }).code) : "";
  if (code === "weak_password") return `That password is too weak. Use at least ${MIN_PASSWORD_LENGTH} characters, not a common word.`;
  if (code === "over_email_send_rate_limit" || code === "over_request_rate_limit") {
    return "Too many attempts right now. Wait a few minutes and try again.";
  }
  if (code === "signup_disabled") return "Creating accounts is not open right now.";
  return "We couldn't create that account. Check the details and try again.";
}

/**
 * Creates a real account in the real Supabase project (`signUp`) — nothing is stored here. Supabase sends a
 * confirmation email when the project requires one (it should); the link returns through `/auth/callback`.
 * Whether an address already has an account is never revealed: the "check your email" message is the same
 * either way, which is what Supabase itself returns for an existing address.
 */
export function SignupForm({ next }: { next: string }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sentTo, setSentTo] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Use a password of at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }

    setSubmitting(true);
    const supabase = createClient();
    const { data, error: signUpError } = await supabase.auth.signUp({
      email,
      password,
      options: { emailRedirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent(next)}` },
    });

    if (signUpError) {
      setError(messageFor(signUpError));
      setSubmitting(false);
      return;
    }

    if (data.session) {
      // The project does not require email confirmation: this is already a signed-in session.
      window.location.href = next;
      return;
    }

    setSentTo(email);
    setSubmitting(false);
  }

  if (sentTo) {
    return (
      <Callout tone="success" title="Check your email">
        If {sentTo} can be registered, a confirmation link is on its way. Open it on this device to finish and sign in.
      </Callout>
    );
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
      <Field label="Password" hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}>
        {(id, describedBy) => (
          <input
            id={id}
            aria-describedby={describedBy}
            type="password"
            autoComplete="new-password"
            required
            minLength={MIN_PASSWORD_LENGTH}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className={fieldInputClassName(false)}
          />
        )}
      </Field>

      {error && <Callout tone="error">{error}</Callout>}

      <Button type="submit" disabled={submitting} className="mt-1">
        {submitting ? "Creating account…" : "Create account"}
      </Button>
    </form>
  );
}
