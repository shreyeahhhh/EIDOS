"use client";

import type { ReactNode } from "react";

import { Field, fieldInputClassName } from "@/components/ui/field";
import { PROVIDERS, type ProviderId } from "@/lib/compare";

export interface ChoiceState {
  on: boolean;
  model: string;
  key: string;
}
export type Choices = Record<ProviderId, ChoiceState>;
export type ChoiceErrors = Partial<Record<ProviderId, { model?: string; key?: string }>>;

export const EMPTY_CHOICES: Choices = { openai: { on: false, model: "", key: "" }, gemini: { on: false, model: "", key: "" }, groq: { on: false, model: "", key: "" } };

interface ModelChoicesProps {
  choices: Choices;
  errors: ChoiceErrors;
  onChange: (provider: ProviderId, patch: Partial<ChoiceState>) => void;
  /** The heading and the sentence under it; the defaults are the mission form's. */
  legend?: string;
  intro?: ReactNode;
  /** The sentence shown once two or more are ticked; the default describes a comparison of missions. */
  comparing?: (picked: number) => ReactNode;
  /** Marks the panel as what needs attention (nothing is ticked yet), so a refused click can take the person here. */
  invalid?: boolean;
}

const MISSION_INTRO =
  "Run this goal on your own account at OpenAI, Google Gemini or Groq. Choose two or three to compare their answers side by side. Leave all unticked to use this site's own model.";

const MISSION_COMPARING = (picked: number) =>
  `EIDOS will run this goal once on each of the ${picked} models and show the answers side by side, each with its own sources. It checks each answer's sources, not which answer is right — you decide that.`;

/**
 * Run the goal on the person's own account at one or more providers; two or more is a comparison. The keys exist only in this form's state: they are sent once, when the runs are started, and are
 * forgotten here the moment they are (D-246). Nothing is written to the browser's storage, so a reload empties them.
 */
export function ModelChoices({ choices, errors, onChange, legend = "Use my own models (optional)", intro = MISSION_INTRO, comparing = MISSION_COMPARING, invalid }: ModelChoicesProps) {
  const picked = PROVIDERS.filter((provider) => choices[provider.id].on).length;

  return (
    <fieldset className="flex flex-col gap-3" data-invalid={invalid ? "true" : undefined}>
      <legend className="text-sm font-medium text-ink">{legend}</legend>
      <p id="own-models-hint" className="text-xs text-ink-faint">
        {intro}
      </p>
      <p className="rounded-md border border-border bg-surface-sunken px-3 py-2 text-xs leading-relaxed text-ink-muted">
        <span className="font-medium text-ink">About your key.</span> It goes from this page to EIDOS over HTTPS when you press the button, is kept in the server&apos;s memory only while your run is going, and is never saved,
        logged or shown again. It stays in this page only: reload and it is gone. Use a key you can revoke, and the provider bills your own account.
      </p>

      {PROVIDERS.map((provider) => {
        const choice = choices[provider.id];
        const problems = errors[provider.id];
        return (
          <div key={provider.id} className="flex flex-col gap-3 rounded-md border border-border px-4 py-3">
            <label className="flex items-center gap-2 text-sm text-ink">
              <input
                type="checkbox"
                checked={choice.on}
                onChange={(event) => onChange(provider.id, { on: event.target.checked })}
                aria-describedby="own-models-hint"
                className="h-4 w-4 rounded border-border-strong accent-[var(--color-accent)]"
              />
              <span className="font-medium">{provider.label}</span>
              <span className="text-xs text-ink-faint">{provider.note}</span>
            </label>
            {choice.on && (
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label={`${provider.label} model`} hint="A model id from your provider's current list" error={problems?.model}>
                  {(id, describedBy) => (
                    <input
                      id={id}
                      type="text"
                      value={choice.model}
                      onChange={(event) => onChange(provider.id, { model: event.target.value })}
                      aria-invalid={Boolean(problems?.model)}
                      aria-describedby={describedBy}
                      autoComplete="off"
                      spellCheck={false}
                      className={`${fieldInputClassName(Boolean(problems?.model))} font-mono`}
                    />
                  )}
                </Field>
                <Field label={`${provider.label} API key`} error={problems?.key}>
                  {(id, describedBy) => (
                    <input
                      id={id}
                      type="password"
                      value={choice.key}
                      onChange={(event) => onChange(provider.id, { key: event.target.value })}
                      aria-invalid={Boolean(problems?.key)}
                      aria-describedby={describedBy}
                      autoComplete="off"
                      spellCheck={false}
                      className={`${fieldInputClassName(Boolean(problems?.key))} font-mono`}
                    />
                  )}
                </Field>
              </div>
            )}
          </div>
        );
      })}

      {picked >= 2 && (
        <p role="status" className="text-xs text-ink-muted">
          {comparing(picked)}
        </p>
      )}
    </fieldset>
  );
}
